"""
Flask Application for Event Attendance Management System.
Reusable for any event, with single admin-generated QR code per session,
secure participant authentication, real-time analytics, and multi-format exports.
"""

import os
import io
import csv
import functools
import secrets
import hashlib
from datetime import datetime, timedelta
from flask import Flask, render_template, request, jsonify, send_file, Response, redirect, url_for, session

import database as db

# Ensure environment variables are loaded
db.load_env_file()

app = Flask(__name__)

# Cryptographic session secret key: never fallback to static weak strings
app.secret_key = os.environ.get("FLASK_SECRET_KEY") or secrets.token_hex(32)

# Session cookie hardening against XSS, MITM, and CSRF attacks
app.config.update(
    SESSION_COOKIE_HTTPONLY=True,       # Blocks JavaScript access (XSS defense)
    SESSION_COOKIE_SAMESITE="Lax",      # Prevents Cross-Site Request Forgery (CSRF)
    SESSION_COOKIE_SECURE="RENDER" in os.environ or os.environ.get("FLASK_ENV") == "production",  # Enforce HTTPS on cloud
    PERMANENT_SESSION_LIFETIME=timedelta(hours=6)
)

# Ensure database is initialized on startup
db.init_db()

# ----------------- STAFF AUTHENTICATION (ADMIN PORTAL SECURITY) -----------------

# Bootstrap the staff account from environment variables
_BOOTSTRAP_ADMIN_USERNAME = os.environ.get("ADMIN_USERNAME")
_BOOTSTRAP_ADMIN_PASSWORD = os.environ.get("ADMIN_PASSWORD")
if _BOOTSTRAP_ADMIN_USERNAME and _BOOTSTRAP_ADMIN_PASSWORD:
    db.create_staff_user(_BOOTSTRAP_ADMIN_USERNAME, _BOOTSTRAP_ADMIN_PASSWORD, display_name="Lead SecOps Administrator")

# ----------------- CYBER DEFENSE: ANTI-BRUTE FORCE RATE LIMITING -----------------

_FAILED_LOGIN_ATTEMPTS = {}  # ip -> list of attempt datetime objects
MAX_LOGIN_ATTEMPTS = 5
LOCKOUT_WINDOW_SECONDS = 600  # 10 minute lockout window

def get_client_ip():
    """Extract real client IP considering reverse proxies / Cloudflare / Render."""
    forwarded = request.headers.get("X-Forwarded-For")
    if forwarded:
        return forwarded.split(",")[0].strip()
    return request.remote_addr or "127.0.0.1"

def is_ip_locked_out(ip: str) -> bool:
    now = datetime.now()
    attempts = _FAILED_LOGIN_ATTEMPTS.get(ip, [])
    # Filter attempts within the active lockout window
    recent = [t for t in attempts if (now - t).total_seconds() < LOCKOUT_WINDOW_SECONDS]
    _FAILED_LOGIN_ATTEMPTS[ip] = recent
    return len(recent) >= MAX_LOGIN_ATTEMPTS

def record_failed_attempt(ip: str):
    now = datetime.now()
    if ip not in _FAILED_LOGIN_ATTEMPTS:
        _FAILED_LOGIN_ATTEMPTS[ip] = []
    _FAILED_LOGIN_ATTEMPTS[ip].append(now)

def clear_ip_attempts(ip: str):
    _FAILED_LOGIN_ATTEMPTS.pop(ip, None)


def staff_required(view):
    """Guard staff-only pages and APIs. JSON endpoints get a 401, pages redirect to /login."""
    @functools.wraps(view)
    def wrapper(*args, **kwargs):
        if not session.get("staff_user"):
            if request.path.startswith("/api/"):
                return jsonify({"success": False, "message": "Staff authentication required.", "status_code": "AUTH_REQUIRED"}), 401
            return redirect(url_for("staff_login", next=request.path))
        return view(*args, **kwargs)
    return wrapper


@app.after_request
def apply_security_headers(response):
    """Inject industry-standard defense-in-depth security headers."""
    response.headers["X-Content-Type-Options"] = "nosniff"
    response.headers["X-Frame-Options"] = "SAMEORIGIN"
    response.headers["X-XSS-Protection"] = "1; mode=block"
    response.headers["Referrer-Policy"] = "strict-origin-when-cross-origin"
    response.headers["Permissions-Policy"] = "camera=(self), microphone=()"
    return response


# Pre-computed dummy hash to prevent username enumeration via timing attacks
# Pre-computed dummy hash to prevent username enumeration via timing attacks
_DUMMY_SALT = "00000000000000000000000000000000"
_DUMMY_HASH = f"{_DUMMY_SALT}${hashlib.pbkdf2_hmac('sha256', b'timing_pad_dummy_key_2026', _DUMMY_SALT.encode(), 100000).hex()}"

# Configurable confidential staff login path
STAFF_LOGIN_PATH = os.environ.get("STAFF_LOGIN_PATH", "/staff-access").strip()
if not STAFF_LOGIN_PATH.startswith("/"):
    STAFF_LOGIN_PATH = "/" + STAFF_LOGIN_PATH

@app.route("/staff-portal", methods=["GET", "POST"])
@app.route(STAFF_LOGIN_PATH, methods=["GET", "POST"])
def staff_login():
    if session.get("staff_user"):
        return redirect(url_for("admin_dashboard"))

    client_ip = get_client_ip()
    error = None

    if request.method == "POST":
        # 1. Check Brute-Force Rate Limiting
        if is_ip_locked_out(client_ip):
            return render_template(
                "admin_login.html",
                error="[SECURITY ALERT] Too many failed attempts. Login is locked from your IP address for 10 minutes.",
                next=request.args.get("next", "")
            ), 429

        username = (request.form.get("username") or "").strip()
        password = (request.form.get("password") or "")

        user = db.get_staff_user_by_username(username) if username else None

        # 2. Anti-Timing-Attack: Always run PBKDF2 calculation even if username is invalid
        if user:
            ok, _needs_upgrade = db.verify_password(user["password_hash"], password)
            if not ok and (password.startswith(" ") or password.endswith(" ")):
                ok, _needs_upgrade = db.verify_password(user["password_hash"], password.strip())
        else:
            db.verify_password(_DUMMY_HASH, password)
            ok = False

        if ok:
            clear_ip_attempts(client_ip)
            session.clear()
            session["staff_user"] = user["username"]
            session.permanent = True
            next_url = request.args.get("next") or url_for("admin_dashboard")
            if not next_url.startswith("/"):
                next_url = url_for("admin_dashboard")  # block open redirects
            return redirect(next_url)

        # Record failed attempt and compute remaining attempts
        record_failed_attempt(client_ip)
        recent_count = len(_FAILED_LOGIN_ATTEMPTS.get(client_ip, []))
        remaining = max(0, MAX_LOGIN_ATTEMPTS - recent_count)

        if remaining == 0:
            error = "[SECURITY ALERT] Too many failed attempts. Your IP has been temporarily locked for 10 minutes."
        else:
            error = f"Invalid staff credentials. Access restricted to authorized event administrators. ({remaining} attempt(s) remaining)"

    return render_template("admin_login.html", error=error, next=request.args.get("next", ""), staff_login_url=STAFF_LOGIN_PATH)


@app.route("/login")
def public_login_redirect():
    """Security deception: curious participants scanning /login land on Participant Portal."""
    return redirect(url_for("participant_portal"))


@app.route("/logout", methods=["POST"])
def staff_logout():
    session.clear()
    return redirect(url_for("staff_login"))

# ----------------- PAGE ROUTES -----------------

@app.route("/")
def index():
    if session.get("staff_user"):
        return redirect(url_for("admin_dashboard"))
    return redirect(url_for("checkin_page"))

@app.route("/admin")
@staff_required
def admin_dashboard():
    events = db.get_all_events()
    return render_template("admin.html", events=events)

@app.route("/checkin")
def checkin_page():
    session_id = request.args.get("session_id", type=int)
    token = request.args.get("token", "")
    if session_id:
        session_data = db.get_session_by_id(session_id)
    else:
        # Fallback to current active session for seamless mobile check-in
        conn = db.get_db_connection()
        active = conn.execute("SELECT id FROM sessions WHERE is_active = 1 ORDER BY id DESC LIMIT 1").fetchone()
        if not active:
            active = conn.execute("SELECT id FROM sessions ORDER BY id DESC LIMIT 1").fetchone()
        conn.close()
        session_data = db.get_session_by_id(active["id"]) if active else None
        if session_data:
            session_id = session_data["id"]
            token = session_data["session_token"]

    return render_template("participant.html", session_data=session_data, token=token, initial_id=request.args.get("id", ""), default_tab="checkin")


@app.route("/projector")
@app.route("/qr")
@staff_required
def projector_page():
    session_id = request.args.get("session_id", type=int)
    if session_id:
        session_data = db.get_session_by_id(session_id)
    else:
        conn = db.get_db_connection()
        active = conn.execute("SELECT id FROM sessions WHERE is_active = 1 ORDER BY id DESC LIMIT 1").fetchone()
        if not active:
            active = conn.execute("SELECT id FROM sessions ORDER BY id DESC LIMIT 1").fetchone()
        conn.close()
        session_data = db.get_session_by_id(active["id"]) if active else None
    return render_template("projector.html", session_data=session_data)


@app.route("/participant")
def participant_portal():
    participant_id = request.args.get("id", "")
    session_id = request.args.get("session_id", type=int)
    token = request.args.get("token", "")
    if session_id:
        session_data = db.get_session_by_id(session_id)
    else:
        conn = db.get_db_connection()
        active = conn.execute("SELECT id FROM sessions WHERE is_active = 1 ORDER BY id DESC LIMIT 1").fetchone()
        if not active:
            active = conn.execute("SELECT id FROM sessions ORDER BY id DESC LIMIT 1").fetchone()
        conn.close()
        session_data = db.get_session_by_id(active["id"]) if active else None
        if session_data:
            session_id = session_data["id"]
            token = session_data["session_token"]

    # If an active session exists, default to 'checkin', else default to 'history'
    default_tab = "history" if (participant_id and not request.args.get("session_id")) else ("checkin" if (session_data and session_data.get("is_active")) else "checkin")
    return render_template("participant.html", session_data=session_data, token=token, initial_id=participant_id, default_tab=default_tab)

# ----------------- QR API -----------------

@app.route("/api/qr")
def api_render_qr():
    import qrcode
    text = request.args.get("data", "").strip()
    size = request.args.get("size", default=8, type=int)
    if not text:
        return "No data provided", 400

    qr = qrcode.QRCode(
        version=None,
        error_correction=qrcode.constants.ERROR_CORRECT_M,
        box_size=max(4, min(size, 20)),
        border=2,
    )
    qr.add_data(text)
    qr.make(fit=True)
    img = qr.make_image(fill_color="#050807", back_color="#FFFFFF")

    buf = io.BytesIO()
    img.save(buf, format="PNG")
    buf.seek(0)
    return send_file(buf, mimetype="image/png")

@app.route("/api/system/network_info")
def api_network_info():
    import socket
    lan_ip = "127.0.0.1"
    try:
        s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        s.connect(("8.8.8.8", 80))
        lan_ip = s.getsockname()[0]
        s.close()
    except Exception:
        pass
    port = request.environ.get('SERVER_PORT', 5000)
    return jsonify({
        "success": True,
        "lan_ip": lan_ip,
        "lan_url": f"http://{lan_ip}:{port}",
        "origin_url": request.host_url.rstrip('/')
    })


# ----------------- EVENT & SESSION API -----------------

@app.route("/api/events", methods=["GET"])
@staff_required
def api_get_events():
    events = db.get_all_events()
    return jsonify({"success": True, "events": events})

@app.route("/api/events", methods=["POST"])
@staff_required
def api_create_event():
    data = request.get_json(silent=True) or {}
    name = data.get("name", "").strip()
    code = data.get("event_code", "").strip()
    desc = data.get("description", "").strip()
    venue = data.get("venue", "").strip()
    start_date = data.get("start_date", "").strip()
    end_date = data.get("end_date", "").strip()

    if not name or not code or not start_date or not end_date:
        return jsonify({"success": False, "message": "Event name, code, start date, and end date are required."}), 400

    try:
        event_id = db.create_event(name, code, desc, venue, start_date, end_date)
        return jsonify({"success": True, "event_id": event_id, "message": f"Event '{name}' created successfully."})
    except Exception as e:
        return jsonify({"success": False, "message": str(e)}), 400

@app.route("/api/sessions", methods=["GET"])
@staff_required
def api_get_sessions():
    event_id = request.args.get("event_id", type=int)
    if not event_id:
        return jsonify({"success": False, "message": "event_id parameter required"}), 400
    sessions = db.get_sessions_for_event(event_id)
    return jsonify({"success": True, "sessions": sessions})

@app.route("/api/sessions", methods=["POST"])
@staff_required
def api_create_session():
    data = request.get_json(silent=True) or {}
    event_id = data.get("event_id")
    name = data.get("name", "").strip()
    session_date = data.get("session_date", "").strip()
    start_time = data.get("start_time", "").strip()
    end_time = data.get("end_time", "").strip()
    late_threshold = data.get("late_threshold_minutes", 15)

    if not event_id or not name or not session_date or not start_time or not end_time:
        return jsonify({"success": False, "message": "All session fields (name, date, start, end) are required."}), 400

    try:
        session_id, token = db.create_session(event_id, name, session_date, start_time, end_time, late_threshold)
        return jsonify({
            "success": True, 
            "session_id": session_id, 
            "token": token,
            "message": f"Session '{name}' created."
        })
    except Exception as e:
        return jsonify({"success": False, "message": str(e)}), 400

@app.route("/api/sessions/<int:session_id>/toggle", methods=["POST"])
@staff_required
def api_toggle_session(session_id):
    is_active = None
    try:
        if request.is_json:
            data = request.get_json(silent=True) or {}
            is_active = data.get("is_active")
        elif request.data:
            import json
            try:
                data = json.loads(request.data.decode("utf-8", errors="ignore"))
                is_active = data.get("is_active")
            except Exception:
                pass
    except Exception:
        pass

    if is_active is None and "is_active" in request.form:
        is_active = request.form.get("is_active")
    if is_active is None and "is_active" in request.args:
        is_active = request.args.get("is_active")

    try:
        new_state = db.toggle_session_attendance(session_id, is_active)
    except Exception as e:
        print(f"[ERROR] db.toggle_session_attendance failed: {e}")
        return jsonify({"success": False, "message": f"Database error: {str(e)}"}), 500

    if new_state is None:
        return jsonify({"success": False, "message": "Session not found."}), 404
    return jsonify({
        "success": True, 
        "is_active": new_state,
        "message": f"Attendance is now {'ACTIVE' if new_state else 'DEACTIVATED'}."
    })

@app.route("/api/sessions/<int:session_id>/regenerate_token", methods=["POST"])
@staff_required
def api_regenerate_token(session_id):
    token = db.regenerate_session_token(session_id)
    return jsonify({"success": True, "token": token, "message": "QR token regenerated."})

@app.route("/api/sessions/<int:session_id>", methods=["GET"])
@staff_required
def api_get_session(session_id):
    s = db.get_session_by_id(session_id)
    if not s:
        return jsonify({"success": False, "message": "Session not found."}), 404
    return jsonify({"success": True, "session": s})

# ----------------- PARTICIPANTS API -----------------

# ----------------- PARTICIPANTS API (STAFF ONLY) -----------------

@app.route("/api/participants", methods=["GET"])
@staff_required
def api_get_participants():
    event_id = request.args.get("event_id", type=int)
    search = request.args.get("search", "").strip()
    org = request.args.get("organization", "").strip()
    if not event_id:
        return jsonify({"success": False, "message": "event_id is required."}), 400
    participants = db.get_participants_for_event(event_id, search, org)
    return jsonify({"success": True, "participants": participants, "total": len(participants)})

@app.route("/api/participants", methods=["POST"])
@staff_required
def api_register_participant():
    data = request.get_json(silent=True) or {}
    event_id = data.get("event_id")
    participant_id = data.get("participant_id", "").strip().upper()
    full_name = data.get("full_name", "").strip()
    email = data.get("email", "").strip()
    org = data.get("organization", "").strip()
    password = data.get("password", "").strip()

    if not event_id or not participant_id or not full_name or not email or not password:
        return jsonify({"success": False, "message": "Event ID, Participant ID, Full Name, Email, and Access PIN are required."}), 400

    try:
        p_id = db.register_participant(event_id, participant_id, full_name, email, org, password)
        return jsonify({"success": True, "id": p_id, "message": f"Participant {full_name} registered successfully."})
    except Exception as e:
        return jsonify({"success": False, "message": str(e)}), 400

@app.route("/api/participants/bulk", methods=["POST"])
@staff_required
def api_bulk_participants():
    """Bulk import participants from CSV or JSON roster."""
    data = request.get_json(silent=True) or {}
    event_id = data.get("event_id")
    roster = data.get("roster", [])

    if not event_id or not roster:
        return jsonify({"success": False, "message": "event_id and roster array are required."}), 400

    added = 0
    errors = []
    for item in roster:
        pid = item.get("participant_id", "").strip().upper()
        name = item.get("full_name", "").strip()
        email = item.get("email", "").strip()
        org = item.get("organization", "").strip()
        pwd = item.get("password", "").strip()
        if not pid or not name or not email:
            continue
        if not pwd:
            errors.append(f"{pid}: skipped — no PIN provided")
            continue
        try:
            db.register_participant(event_id, pid, name, email, org, pwd)
            added += 1
        except Exception as e:
            errors.append(f"{pid}: {str(e)}")

    return jsonify({"success": True, "added": added, "errors": errors, "message": f"Successfully imported {added} participants."})

@app.route("/api/participants/<participant_id>/history", methods=["GET"])
@staff_required
def api_participant_history(participant_id):
    history = db.get_participant_full_history(participant_id)
    if not history:
        return jsonify({"success": False, "message": "Participant not found."}), 404
    return jsonify({"success": True, "data": history})

# ----------------- PARTICIPANT SELF-SERVICE LOGIN (PIN-GATED PORTAL) -----------------

@app.route("/api/participant/login", methods=["POST"])
def api_participant_login():
    """
    PIN-gated participant portal login. Returns a short-lived access token
    (stored server-side hash of the PIN) — the portal keeps it in memory only.
    """
    data = request.get_json(silent=True) or {}
    participant_id = (data.get("participant_id") or "").strip()
    password = (data.get("password") or "").strip()

    if not participant_id or not password:
        return jsonify({"success": False, "message": "Participant ID and Access PIN are required."}), 400

    participant = db.authenticate_participant(participant_id, password)
    if not participant:
        return jsonify({"success": False, "message": "Invalid Participant ID or Access PIN."}), 401

    import hashlib as _hashlib
    token = _hashlib.sha256(f"portal:{participant['id']}:{password}".encode("utf-8")).hexdigest()[:32]
    return jsonify({
        "success": True,
        "access_token": token,
        "participant_id": participant["participant_id"],
        "full_name": participant["full_name"],
        "message": "Login successful."
    })

@app.route("/api/participant/history", methods=["POST"])
def api_participant_history_authed():
    """PIN-verified attendance history for the participant portal."""
    data = request.get_json(silent=True) or {}
    participant_id = (data.get("participant_id") or "").strip()
    password = (data.get("password") or "").strip()

    if not participant_id or not password:
        return jsonify({"success": False, "message": "Participant ID and Access PIN are required."}), 400

    participant = db.authenticate_participant(participant_id, password)
    if not participant:
        return jsonify({"success": False, "message": "Invalid Participant ID or Access PIN."}), 401

    history = db.get_participant_full_history(participant_id)
    if not history:
        return jsonify({"success": False, "message": "Participant not found."}), 404
    return jsonify({"success": True, "data": history})

# ----------------- ATTENDANCE CHECK-IN API -----------------

@app.route("/api/attendance/checkin", methods=["POST"])
def api_attendance_checkin():
    """
    Main check-in endpoint:
    - Session-based verification
    - Authenticated participant check (Participant ID + PIN/Password)
    - Rejection of duplicates via DB constraint
    - Returns authoritative server timestamp
    """
    data = request.get_json(silent=True) or {}
    session_id = data.get("session_id")
    participant_id = data.get("participant_id", "").strip().upper()
    password = data.get("password", "").strip()
    scanner_id = data.get("scanner_id", "MOBILE_GATE")

    if not session_id or not participant_id or not password:
        return jsonify({
            "success": False,
            "status_code": "MISSING_FIELDS",
            "message": "Session ID, Participant ID, and Access PIN/Password are required."
        }), 400

    result = db.process_attendance_checkin(session_id, participant_id, password, scanner_id)
    if result.get("success") or result.get("status_code") == "ALREADY_CHECKED_IN":
        try:
            result["student_record"] = db.get_participant_full_history(participant_id)
        except Exception:
            pass
    http_code = 200 if result["success"] else (409 if result["status_code"] == "ALREADY_CHECKED_IN" else 400)
    return jsonify(result), http_code

# ----------------- ADMIN ANALYTICS API -----------------

@app.route("/api/admin/analytics", methods=["GET"])
@staff_required
def api_admin_analytics():
    session_id = request.args.get("session_id", type=int)
    event_id = request.args.get("event_id", type=int)
    analytics = db.get_admin_analytics(session_id, event_id)
    return jsonify({"success": True, "analytics": analytics})

# ----------------- PUBLIC PROJECTOR STATS (COUNT ONLY, NO AUTH) -----------------

@app.route("/api/public/projector_stats", methods=["GET"])
def api_public_projector_stats():
    """Minimal, non-sensitive live counter for the venue projector display."""
    session_id = request.args.get("session_id", type=int)
    if not session_id:
        return jsonify({"success": False, "message": "session_id required."}), 400
    conn = db.get_db_connection()
    row = conn.execute("""
        SELECT COUNT(*) as c
        FROM attendance_records
        WHERE session_id = ?
    """, (session_id,)).fetchone()
    session = conn.execute("SELECT is_active FROM sessions WHERE id = ?", (session_id,)).fetchone()
    conn.close()
    if not session:
        return jsonify({"success": False, "message": "Session not found."}), 404
    return jsonify({
        "success": True,
        "total_checkins": row["c"],
        "is_active": bool(session["is_active"])
    })

# ----------------- EXPORTS (STAFF ONLY: CSV, EXCEL, PDF) -----------------

@app.route("/api/export/csv", methods=["GET"])
@staff_required
def api_export_csv():
    session_id = request.args.get("session_id", type=int)
    event_id = request.args.get("event_id", type=int)
    status_filter = request.args.get("status", "ALL")
    org_filter = request.args.get("organization", "ALL")

    records = db.get_records_for_export(session_id, event_id, status_filter, org_filter)

    output = io.StringIO()
    writer = csv.writer(output)
    writer.writerow([
        "Participant ID", "Participant Name", "Email", "Organization",
        "Event Code", "Event Name", "Session Name", "Session Date",
        "Check-in Time", "Status", "Scanner / Admin ID", "Recorded At"
    ])

    for r in records:
        writer.writerow([
            r["participant_id"], r["full_name"], r["email"], r["organization"],
            r["event_code"], r["event_name"], r["session_name"], r["session_date"],
            r["checkin_time"], r["status"], r["admin_scanner_id"], r["created_at"]
        ])

    csv_data = output.getvalue()
    filename = f"attendance_report_{datetime.now().strftime('%Y%m%d_%H%M%S')}.csv"

    return Response(
        csv_data,
        mimetype="text/csv",
        headers={"Content-Disposition": f"attachment; filename={filename}"}
    )

@app.route("/api/export/excel", methods=["GET"])
@staff_required
def api_export_excel():
    import openpyxl
    from openpyxl.styles import Font, PatternFill, Alignment, Border, Side
    from openpyxl.utils import get_column_letter

    session_id = request.args.get("session_id", type=int)
    event_id = request.args.get("event_id", type=int)
    status_filter = request.args.get("status", "ALL")
    org_filter = request.args.get("organization", "ALL")

    records = db.get_records_for_export(session_id, event_id, status_filter, org_filter)

    wb = openpyxl.Workbook()
    ws = wb.active
    ws.title = "Attendance Records"

    # Futuristic Header styling (Deep forest green fill, neon green text)
    header_fill = PatternFill(start_color="062414", end_color="062414", fill_type="solid")
    header_font = Font(name="Segoe UI", size=11, bold=True, color="00FF66")
    center_align = Alignment(horizontal="center", vertical="center")
    thin_border = Border(
        left=Side(style='thin', color='123B27'),
        right=Side(style='thin', color='123B27'),
        top=Side(style='thin', color='123B27'),
        bottom=Side(style='thin', color='123B27')
    )

    headers = [
        "Participant ID", "Participant Name", "Email", "Organization",
        "Event Code", "Event Name", "Session Name", "Session Date",
        "Check-in Time", "Status", "Scanner / Admin ID", "Recorded At"
    ]

    ws.append(headers)
    for col_num in range(1, len(headers) + 1):
        cell = ws.cell(row=1, column=col_num)
        cell.fill = header_fill
        cell.font = header_font
        cell.alignment = center_align
        cell.border = thin_border

    data_font = Font(name="Segoe UI", size=10)
    for r in records:
        row_vals = [
            r["participant_id"], r["full_name"], r["email"], r["organization"],
            r["event_code"], r["event_name"], r["session_name"], r["session_date"],
            r["checkin_time"], r["status"], r["admin_scanner_id"], r["created_at"]
        ]
        ws.append(row_vals)
        current_row = ws.max_row
        for col_num in range(1, len(row_vals) + 1):
            c = ws.cell(row=current_row, column=col_num)
            c.font = data_font
            c.border = thin_border
            if col_num in (1, 8, 9, 10):
                c.alignment = center_align
                if col_num == 10:
                    if r["status"] == "Present":
                        c.font = Font(name="Segoe UI", size=10, bold=True, color="008033")
                    else:
                        c.font = Font(name="Segoe UI", size=10, bold=True, color="CC7A00")

    # Auto-adjust column widths
    for col in ws.columns:
        max_len = max(len(str(cell.value or '')) for cell in col)
        col_letter = get_column_letter(col[0].column)
        ws.column_dimensions[col_letter].width = max(max_len + 3, 14)

    output = io.BytesIO()
    wb.save(output)
    output.seek(0)
    filename = f"attendance_report_{datetime.now().strftime('%Y%m%d_%H%M%S')}.xlsx"

    return send_file(
        output,
        mimetype="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        as_attachment=True,
        download_name=filename
    )

@app.route("/api/export/pdf", methods=["GET"])
@staff_required
def api_export_pdf():
    from reportlab.lib import colors
    from reportlab.lib.pagesizes import letter, landscape
    from reportlab.platypus import SimpleDocTemplate, Paragraph, Spacer, Table, TableStyle
    from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle

    session_id = request.args.get("session_id", type=int)
    event_id = request.args.get("event_id", type=int)
    status_filter = request.args.get("status", "ALL")
    org_filter = request.args.get("organization", "ALL")

    records = db.get_records_for_export(session_id, event_id, status_filter, org_filter)

    buffer = io.BytesIO()
    doc = SimpleDocTemplate(buffer, pagesize=landscape(letter), rightMargin=30, leftMargin=30, topMargin=30, bottomMargin=30)
    story = []

    styles = getSampleStyleSheet()
    title_style = ParagraphStyle(
        'DocTitle',
        parent=styles['Heading1'],
        fontSize=20,
        leading=24,
        textColor=colors.HexColor('#062414'),
        fontName='Helvetica-Bold'
    )
    sub_style = ParagraphStyle(
        'DocSub',
        parent=styles['Normal'],
        fontSize=10,
        leading=14,
        textColor=colors.HexColor('#7A8580')
    )

    story.append(Paragraph("<b>EVENT ATTENDANCE AUDIT REPORT</b>", title_style))
    meta_text = f"Generated: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')} | Total Verified Check-ins: {len(records)}"
    story.append(Paragraph(meta_text, sub_style))
    story.append(Spacer(1, 15))

    # Table columns
    table_data = [[
        "Participant ID", "Full Name", "Organization", "Session", "Check-in Time", "Status", "Scanner Gate"
    ]]

    for r in records[:200]:  # Cap for PDF page sanity
        table_data.append([
            r["participant_id"],
            r["full_name"],
            r["organization"] or "N/A",
            r["session_name"][:25],
            r["checkin_time"],
            r["status"],
            r["admin_scanner_id"]
        ])

    col_widths = [110, 120, 140, 140, 100, 60, 80]
    t = Table(table_data, colWidths=col_widths, repeatRows=1)
    t.setStyle(TableStyle([
        ('BACKGROUND', (0, 0), (-1, 0), colors.HexColor('#062414')),
        ('TEXTCOLOR', (0, 0), (-1, 0), colors.HexColor('#00FF66')),
        ('FONTNAME', (0, 0), (-1, 0), 'Helvetica-Bold'),
        ('FONTSIZE', (0, 0), (-1, 0), 10),
        ('BOTTOMPADDING', (0, 0), (-1, 0), 8),
        ('TOPPADDING', (0, 0), (-1, 0), 8),
        ('ALIGN', (0, 0), (-1, -1), 'LEFT'),
        ('ALIGN', (0, 0), (0, -1), 'CENTER'),
        ('ALIGN', (4, 0), (5, -1), 'CENTER'),
        ('FONTNAME', (0, 1), (-1, -1), 'Helvetica'),
        ('FONTSIZE', (0, 1), (-1, -1), 9),
        ('GRID', (0, 0), (-1, -1), 0.5, colors.HexColor('#123B27')),
        ('ROWBACKGROUNDS', (0, 1), (-1, -1), [colors.white, colors.HexColor('#F2F3EF')]),
    ]))

    story.append(t)
    doc.build(story)
    buffer.seek(0)
    filename = f"attendance_report_{datetime.now().strftime('%Y%m%d_%H%M%S')}.pdf"

    return send_file(
        buffer,
        mimetype="application/pdf",
        as_attachment=True,
        download_name=filename
    )

if __name__ == "__main__":
    port = int(os.environ.get("PORT", 5000))
    app.run(host="0.0.0.0", port=port, debug=True)

