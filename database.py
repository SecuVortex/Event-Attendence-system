"""
Database module for the Event Attendance Management System.
Features:
- Generic multi-event architecture (zero hardcoded entities)
- Strict SQLite relational schema with UNIQUE(participant_id, session_id)
- Authoritative server timestamps
- PBKDF2 password/PIN hashing for secure participant authentication
- Attendance logging for audit, duplicate detection, and invalid attempts
"""

import sqlite3
import os
import hashlib
import secrets
from datetime import datetime, timezone

DB_PATH = os.path.join(os.path.dirname(os.path.abspath(__file__)), "attendance.db")

def get_db_connection():
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON;")
    conn.execute("PRAGMA journal_mode = WAL;")
    return conn

def hash_password(password: str, salt: str = None) -> str:
    """Hash password using PBKDF2-HMAC-SHA256 with salt."""
    if not salt:
        salt = secrets.token_hex(16)
    key = hashlib.pbkdf2_hmac("sha256", password.encode("utf-8"), salt.encode("utf-8"), 100000)
    return f"{salt}${key.hex()}"

def verify_password(stored_hash: str, password: str):
    """
    Verify password against a stored PBKDF2 salt$hash credential.
    Tolerates legacy plaintext rows (no salt$ prefix) from older databases so
    existing participants are not locked out; returns (ok, needs_upgrade) so the
    caller can transparently re-hash the credential on the next successful login.
    """
    if not stored_hash:
        return False, False
    try:
        if "$" in stored_hash:
            salt, key = stored_hash.split("$", 1)
            calculated = hashlib.pbkdf2_hmac("sha256", password.encode("utf-8"), salt.encode("utf-8"), 100000).hex()
            return secrets.compare_digest(key, calculated), False
        # Legacy plaintext credential: constant-time compare, flag for upgrade
        return secrets.compare_digest(stored_hash, password), True
    except Exception:
        return False, False

def init_db():
    """Create all required tables with database-level constraints."""
    conn = get_db_connection()
    cursor = conn.cursor()

    cursor.executescript("""
    -- Events table: generic container for any event
    CREATE TABLE IF NOT EXISTS events (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        event_code TEXT UNIQUE NOT NULL,
        name TEXT NOT NULL,
        description TEXT,
        venue TEXT,
        start_date TEXT NOT NULL,
        end_date TEXT NOT NULL,
        created_at TEXT NOT NULL
    );

    -- Sessions table: dynamic sessions under events
    CREATE TABLE IF NOT EXISTS sessions (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        event_id INTEGER NOT NULL,
        name TEXT NOT NULL,
        session_date TEXT NOT NULL,
        start_time TEXT NOT NULL,
        end_time TEXT NOT NULL,
        late_threshold_minutes INTEGER DEFAULT 15,
        is_active INTEGER DEFAULT 0,
        session_token TEXT UNIQUE NOT NULL,
        created_at TEXT NOT NULL,
        FOREIGN KEY (event_id) REFERENCES events(id) ON DELETE CASCADE
    );

    -- Participants table: registered participants
    CREATE TABLE IF NOT EXISTS participants (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        event_id INTEGER NOT NULL,
        participant_id TEXT UNIQUE NOT NULL,
        full_name TEXT NOT NULL,
        email TEXT UNIQUE NOT NULL,
        organization TEXT,
        password_hash TEXT NOT NULL,
        created_at TEXT NOT NULL,
        FOREIGN KEY (event_id) REFERENCES events(id) ON DELETE CASCADE
    );

    -- Attendance records: strictly 1 record per participant per session
    CREATE TABLE IF NOT EXISTS attendance_records (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        participant_id INTEGER NOT NULL,
        event_id INTEGER NOT NULL,
        session_id INTEGER NOT NULL,
        checkin_time TEXT NOT NULL,
        status TEXT NOT NULL CHECK(status IN ('Present', 'Late')),
        admin_scanner_id TEXT NOT NULL DEFAULT 'SYSTEM_GATE',
        created_at TEXT NOT NULL,
        FOREIGN KEY (participant_id) REFERENCES participants(id) ON DELETE CASCADE,
        FOREIGN KEY (event_id) REFERENCES events(id) ON DELETE CASCADE,
        FOREIGN KEY (session_id) REFERENCES sessions(id) ON DELETE CASCADE,
        UNIQUE(participant_id, session_id)
    );

    -- Attendance attempt logs for analytics (duplicates, invalid attempts, inactive session alerts)
    CREATE TABLE IF NOT EXISTS attendance_logs (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        session_id INTEGER,
        participant_code_attempted TEXT,
        attempt_type TEXT NOT NULL CHECK(attempt_type IN ('SUCCESS', 'DUPLICATE', 'INVALID_CREDENTIALS', 'SESSION_INACTIVE')),
        message TEXT,
        scanner_id TEXT DEFAULT 'SYSTEM_GATE',
        created_at TEXT NOT NULL
    );

    -- Staff accounts for admin console access (server-side bootstrap only)
    CREATE TABLE IF NOT EXISTS staff_users (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        username TEXT UNIQUE NOT NULL,
        password_hash TEXT NOT NULL,
        display_name TEXT NOT NULL DEFAULT 'Event Administrator',
        created_at TEXT NOT NULL
    );

    -- Indexes for high-performance lookups
    CREATE INDEX IF NOT EXISTS idx_sessions_event ON sessions(event_id);
    CREATE INDEX IF NOT EXISTS idx_participants_event ON participants(event_id);
    CREATE INDEX IF NOT EXISTS idx_participants_code ON participants(participant_id);
    CREATE INDEX IF NOT EXISTS idx_attendance_session ON attendance_records(session_id);
    CREATE INDEX IF NOT EXISTS idx_attendance_participant ON attendance_records(participant_id);
    CREATE INDEX IF NOT EXISTS idx_attendance_logs_session ON attendance_logs(session_id);
    """)

    conn.commit()
    conn.close()

# ----------------- EVENT OPERATIONS -----------------

def create_event(name, event_code, description, venue, start_date, end_date):
    conn = get_db_connection()
    now_str = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    cursor = conn.cursor()
    try:
        cursor.execute("""
            INSERT INTO events (name, event_code, description, venue, start_date, end_date, created_at)
            VALUES (?, ?, ?, ?, ?, ?, ?)
        """, (name, event_code.strip().upper(), description, venue, start_date, end_date, now_str))
        event_id = cursor.lastrowid
        conn.commit()
        return event_id
    finally:
        conn.close()

def get_all_events():
    conn = get_db_connection()
    events = conn.execute("SELECT * FROM events ORDER BY id DESC").fetchall()
    conn.close()
    return [dict(e) for e in events]

def get_event_by_id(event_id):
    conn = get_db_connection()
    event = conn.execute("SELECT * FROM events WHERE id = ?", (event_id,)).fetchone()
    conn.close()
    return dict(event) if event else None

# ----------------- SESSION OPERATIONS -----------------

def create_session(event_id, name, session_date, start_time, end_time, late_threshold_minutes=15):
    conn = get_db_connection()
    now_str = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    session_token = secrets.token_urlsafe(16)
    cursor = conn.cursor()
    try:
        cursor.execute("""
            INSERT INTO sessions (event_id, name, session_date, start_time, end_time, late_threshold_minutes, is_active, session_token, created_at)
            VALUES (?, ?, ?, ?, ?, ?, 0, ?, ?)
        """, (event_id, name, session_date, start_time, end_time, late_threshold_minutes, session_token, now_str))
        session_id = cursor.lastrowid
        conn.commit()
        return session_id, session_token
    finally:
        conn.close()

def get_sessions_for_event(event_id):
    conn = get_db_connection()
    sessions = conn.execute("""
        SELECT s.*, 
            (SELECT COUNT(*) FROM attendance_records WHERE session_id = s.id) as attendance_count
        FROM sessions s
        WHERE s.event_id = ?
        ORDER BY s.session_date ASC, s.start_time ASC
    """, (event_id,)).fetchall()
    conn.close()
    return [dict(s) for s in sessions]

def get_session_by_id(session_id):
    conn = get_db_connection()
    session = conn.execute("""
        SELECT s.*, e.name as event_name, e.event_code
        FROM sessions s
        JOIN events e ON s.event_id = e.id
        WHERE s.id = ?
    """, (session_id,)).fetchone()
    conn.close()
    return dict(session) if session else None

def toggle_session_attendance(session_id, is_active=None):
    conn = get_db_connection()
    cursor = conn.cursor()
    if is_active is None:
        row = cursor.execute("SELECT is_active FROM sessions WHERE id = ?", (session_id,)).fetchone()
        if not row:
            conn.close()
            return None
        new_state = 0 if row["is_active"] else 1
    else:
        new_state = 1 if is_active else 0

    cursor.execute("UPDATE sessions SET is_active = ? WHERE id = ?", (new_state, session_id))
    conn.commit()
    conn.close()
    return bool(new_state)

def regenerate_session_token(session_id):
    conn = get_db_connection()
    new_token = secrets.token_urlsafe(16)
    conn.execute("UPDATE sessions SET session_token = ? WHERE id = ?", (new_token, session_id))
    conn.commit()
    conn.close()
    return new_token

# ----------------- PARTICIPANT OPERATIONS -----------------

def register_participant(event_id, participant_id, full_name, email, organization, password):
    conn = get_db_connection()
    now_str = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    pwd_hash = hash_password(password)
    cursor = conn.cursor()
    try:
        cursor.execute("""
            INSERT INTO participants (event_id, participant_id, full_name, email, organization, password_hash, created_at)
            VALUES (?, ?, ?, ?, ?, ?, ?)
        """, (event_id, participant_id.strip().upper(), full_name.strip(), email.strip().lower(), organization.strip(), pwd_hash, now_str))
        p_id = cursor.lastrowid
        conn.commit()
        return p_id
    finally:
        conn.close()

def get_participant_by_code(participant_id):
    conn = get_db_connection()
    p = conn.execute("SELECT * FROM participants WHERE UPPER(participant_id) = UPPER(?)", (participant_id.strip(),)).fetchone()
    conn.close()
    return dict(p) if p else None

def get_participants_for_event(event_id, search=None, organization=None):
    conn = get_db_connection()
    query = "SELECT id, event_id, participant_id, full_name, email, organization, created_at FROM participants WHERE event_id = ?"
    params = [event_id]

    if search:
        query += " AND (UPPER(participant_id) LIKE ? OR UPPER(full_name) LIKE ? OR UPPER(email) LIKE ? OR UPPER(organization) LIKE ?)"
        s = f"%{search.strip().upper()}%"
        params.extend([s, s, s, s])

    if organization and organization != "ALL":
        query += " AND organization = ?"
        params.append(organization)

    query += " ORDER BY participant_id ASC"
    rows = conn.execute(query, params).fetchall()
    conn.close()
    return [dict(r) for r in rows]

def authenticate_participant(participant_id, password):
    """
    Authenticate participant using ID and password/PIN.
    Legacy plaintext credentials are re-hashed transparently on successful login.
    Returns the participant row (dict) or None on failure.
    """
    conn = get_db_connection()
    p = conn.execute("SELECT * FROM participants WHERE UPPER(participant_id) = UPPER(?)", (participant_id.strip(),)).fetchone()
    if not p:
        conn.close()
        return None
    ok, needs_upgrade = verify_password(p["password_hash"], password)
    if not ok:
        conn.close()
        return None
    if needs_upgrade:
        conn.execute("UPDATE participants SET password_hash = ? WHERE id = ?", (hash_password(password), p["id"]))
        conn.commit()
    participant = dict(p)
    conn.close()
    return participant

# ----------------- ATTENDANCE & VERIFICATION FLOW -----------------

def log_attempt(session_id, participant_code, attempt_type, message, scanner_id="SYSTEM_GATE"):
    conn = get_db_connection()
    now_str = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    conn.execute("""
        INSERT INTO attendance_logs (session_id, participant_code_attempted, attempt_type, message, scanner_id, created_at)
        VALUES (?, ?, ?, ?, ?, ?)
    """, (session_id, participant_code.strip() if participant_code else "", attempt_type, message, scanner_id, now_str))
    conn.commit()
    conn.close()

def process_attendance_checkin(session_id, participant_id_code, password, scanner_id="SYSTEM_GATE"):
    """
    Main attendance verification flow:
    1. Check if session exists and is ACTIVE.
    2. Authenticate participant credentials.
    3. Check if attendance already exists for (participant_id, session_id).
    4. If exists: return ALREADY CHECKED IN with prior timestamp.
    5. If first time: compute status (Present vs Late), save authoritative server timestamp, commit.
    Database-level UNIQUE constraint guarantees zero duplicate records.
    """
    conn = get_db_connection()
    cursor = conn.cursor()

    try:
        # 1. Verify session
        session = cursor.execute("""
            SELECT s.*, e.id as event_id, e.name as event_name 
            FROM sessions s
            JOIN events e ON s.event_id = e.id
            WHERE s.id = ?
        """, (session_id,)).fetchone()

        if not session:
            log_attempt(session_id, participant_id_code, "INVALID_CREDENTIALS", "Session does not exist", scanner_id)
            return {
                "success": False,
                "status_code": "SESSION_NOT_FOUND",
                "message": "Session not found."
            }

        if not session["is_active"]:
            log_attempt(session_id, participant_id_code, "SESSION_INACTIVE", f"Session '{session['name']}' is not active", scanner_id)
            return {
                "success": False,
                "status_code": "SESSION_INACTIVE",
                "message": "Attendance is currently closed for this session. Please ask the event admin to activate attendance."
            }

        # 2. Authenticate participant
        participant = cursor.execute("""
            SELECT * FROM participants 
            WHERE UPPER(participant_id) = UPPER(?) AND event_id = ?
        """, (participant_id_code.strip(), session["event_id"])).fetchone()

        if not participant:
            log_attempt(session_id, participant_id_code, "INVALID_CREDENTIALS", "Invalid Participant ID or Access PIN", scanner_id)
            return {
                "success": False,
                "status_code": "INVALID_PARTICIPANT",
                "message": "INVALID PARTICIPANT: Credentials verification failed for this event."
            }

        ok, needs_upgrade = verify_password(participant["password_hash"], password)
        if ok and needs_upgrade:
            # Transparently upgrade legacy plaintext credentials to PBKDF2
            cursor.execute("UPDATE participants SET password_hash = ? WHERE id = ?", (hash_password(password), participant["id"]))
            conn.commit()
        if not ok:
            log_attempt(session_id, participant_id_code, "INVALID_CREDENTIALS", "Invalid Participant ID or Access PIN", scanner_id)
            return {
                "success": False,
                "status_code": "INVALID_PARTICIPANT",
                "message": "INVALID PARTICIPANT: Credentials verification failed for this event."
            }

        # 3. Check if already marked (Duplicate Check)
        existing = cursor.execute("""
            SELECT * FROM attendance_records 
            WHERE participant_id = ? AND session_id = ?
        """, (participant["id"], session_id)).fetchone()

        if existing:
            log_attempt(session_id, participant_id_code, "DUPLICATE", f"Duplicate check-in attempt by {participant['full_name']}", scanner_id)
            return {
                "success": False,
                "status_code": "ALREADY_CHECKED_IN",
                "message": "ALREADY CHECKED IN: Attendance was already recorded for this session.",
                "participant_name": participant["full_name"],
                "participant_id": participant["participant_id"],
                "session_name": session["name"],
                "previous_checkin_time": existing["checkin_time"],
                "status": existing["status"]
            }

        # 4. Determine Server Timestamp & Status (Present vs Late)
        now = datetime.now()
        server_timestamp_str = now.strftime("%Y-%m-%d %H:%M:%S")
        status = "Present"

        # Check late arrival if session_date and start_time are available
        try:
            session_start_dt = datetime.strptime(f"{session['session_date']} {session['start_time']}", "%Y-%m-%d %H:%M")
            grace_minutes = session["late_threshold_minutes"] or 15
            if now > session_start_dt and (now - session_start_dt).total_seconds() > (grace_minutes * 60):
                status = "Late"
        except Exception:
            status = "Present"

        # 5. Insert Record with database UNIQUE constraint
        try:
            cursor.execute("""
                INSERT INTO attendance_records (participant_id, event_id, session_id, checkin_time, status, admin_scanner_id, created_at)
                VALUES (?, ?, ?, ?, ?, ?, ?)
            """, (participant["id"], session["event_id"], session_id, server_timestamp_str, status, scanner_id, server_timestamp_str))
            conn.commit()

            log_attempt(session_id, participant_id_code, "SUCCESS", f"Attendance verified for {participant['full_name']}", scanner_id)

            return {
                "success": True,
                "status_code": "ATTENDANCE_MARKED",
                "message": "✓ ATTENDANCE MARKED",
                "participant_name": participant["full_name"],
                "participant_id": participant["participant_id"],
                "session_name": session["name"],
                "event_name": session["event_name"],
                "checkin_time": server_timestamp_str,
                "status": status
            }
        except sqlite3.IntegrityError:
            conn.rollback()
            prior = cursor.execute("SELECT * FROM attendance_records WHERE participant_id = ? AND session_id = ?", 
                                   (participant["id"], session_id)).fetchone()
            log_attempt(session_id, participant_id_code, "DUPLICATE", "Race condition prevented duplicate record", scanner_id)
            return {
                "success": False,
                "status_code": "ALREADY_CHECKED_IN",
                "message": "ALREADY CHECKED IN: Attendance has already been marked.",
                "participant_name": participant["full_name"],
                "participant_id": participant["participant_id"],
                "session_name": session["name"],
                "previous_checkin_time": prior["checkin_time"] if prior else server_timestamp_str,
                "status": prior["status"] if prior else "Present"
            }

    finally:
        conn.close()

# ----------------- PARTICIPANT ATTENDANCE HISTORY -----------------

def get_participant_full_history(participant_id_code):
    """
    Look up complete session-by-session history for an individual participant:
    Name, ID, Event, Attendance %, Sessions Attended, Sessions Missed,
    and a complete chronological breakdown of each session with exact check-in time and status.
    """
    conn = get_db_connection()
    cursor = conn.cursor()

    p = cursor.execute("""
        SELECT p.*, e.name as event_name, e.event_code
        FROM participants p
        JOIN events e ON p.event_id = e.id
        WHERE UPPER(p.participant_id) = UPPER(?)
    """, (participant_id_code.strip(),)).fetchone()

    if not p:
        conn.close()
        return None

    sessions = cursor.execute("""
        SELECT * FROM sessions 
        WHERE event_id = ? 
        ORDER BY session_date ASC, start_time ASC
    """, (p["event_id"],)).fetchall()

    records = cursor.execute("""
        SELECT * FROM attendance_records 
        WHERE participant_id = ?
    """, (p["id"],)).fetchall()

    records_by_session = {r["session_id"]: dict(r) for r in records}

    session_history = []
    attended_count = 0

    for s in sessions:
        rec = records_by_session.get(s["id"])
        if rec:
            attended_count += 1
            status = rec["status"]
            checkin_time = rec["checkin_time"]
        else:
            status = "Absent"
            checkin_time = None

        session_history.append({
            "session_id": s["id"],
            "session_name": s["name"],
            "session_date": s["session_date"],
            "start_time": s["start_time"],
            "end_time": s["end_time"],
            "status": status,
            "checkin_time": checkin_time
        })

    total_sessions = len(sessions)
    missed_count = total_sessions - attended_count
    attendance_pct = round((attended_count / total_sessions * 100), 1) if total_sessions > 0 else 0.0

    conn.close()

    return {
        "participant_id": p["participant_id"],
        "full_name": p["full_name"],
        "email": p["email"],
        "organization": p["organization"],
        "event_id": p["event_id"],
        "event_name": p["event_name"],
        "event_code": p["event_code"],
        "total_sessions": total_sessions,
        "sessions_attended": attended_count,
        "sessions_missed": missed_count,
        "attendance_percentage": attendance_pct,
        "history": session_history
    }

# ----------------- STAFF / ADMIN ACCOUNT OPERATIONS -----------------

def create_staff_user(username, password, display_name="Event Administrator"):
    """Create or replace a staff account (used by the local bootstrap only)."""
    conn = get_db_connection()
    now_str = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    try:
        conn.execute("""
            INSERT INTO staff_users (username, password_hash, display_name, created_at)
            VALUES (?, ?, ?, ?)
            ON CONFLICT(username) DO UPDATE SET password_hash = excluded.password_hash
        """, (username.strip().lower(), hash_password(password), display_name, now_str))
        conn.commit()
    finally:
        conn.close()

def get_staff_user_by_username(username):
    conn = get_db_connection()
    row = conn.execute("SELECT * FROM staff_users WHERE username = ?", (username.strip().lower(),)).fetchone()
    conn.close()
    return dict(row) if row else None

# ----------------- ADMIN DASHBOARD ANALYTICS -----------------

def get_admin_analytics(session_id=None, event_id=None):
    """
    Computes precise, non-decorative metrics:
    - Total Registered
    - Total Present
    - Total Absent
    - Attendance %
    - Total Check-ins
    - Late Arrivals
    - Duplicate Attempts
    - Invalid Attempts
    Visualizations:
    - Attendance over time (binned by 15-min intervals)
    - Session-wise attendance
    - Present vs absent breakdown
    - Peak check-in period
    - Attendance trends
    """
    conn = get_db_connection()
    cursor = conn.cursor()

    if session_id:
        s_row = cursor.execute("SELECT event_id FROM sessions WHERE id = ?", (session_id,)).fetchone()
        event_id = s_row["event_id"] if s_row else event_id

    if not event_id:
        latest_event = cursor.execute("SELECT id FROM events ORDER BY id DESC LIMIT 1").fetchone()
        event_id = latest_event["id"] if latest_event else None

    if not event_id:
        conn.close()
        return {
            "total_registered": 0, "total_present": 0, "total_absent": 0,
            "attendance_percentage": 0, "total_checkins": 0, "late_arrivals": 0,
            "duplicate_attempts": 0, "invalid_attempts": 0,
            "attendance_over_time": [], "session_comparison": [],
            "present_vs_absent": {"present": 0, "absent": 0},
            "peak_period": "N/A", "live_feed": []
        }

    total_registered = cursor.execute("SELECT COUNT(*) as count FROM participants WHERE event_id = ?", (event_id,)).fetchone()["count"]

    if session_id:
        checkins_query = "SELECT * FROM attendance_records WHERE session_id = ? ORDER BY checkin_time DESC"
        checkin_records = cursor.execute(checkins_query, (session_id,)).fetchall()

        logs_query = "SELECT * FROM attendance_logs WHERE session_id = ?"
        attempt_logs = cursor.execute(logs_query, (session_id,)).fetchall()
    else:
        checkins_query = "SELECT * FROM attendance_records WHERE event_id = ? ORDER BY checkin_time DESC"
        checkin_records = cursor.execute(checkins_query, (event_id,)).fetchall()

        logs_query = """
            SELECT al.* FROM attendance_logs al
            JOIN sessions s ON al.session_id = s.id
            WHERE s.event_id = ?
        """
        attempt_logs = cursor.execute(logs_query, (event_id,)).fetchall()

    total_checkins = len(checkin_records)
    late_arrivals = sum(1 for r in checkin_records if r["status"] == "Late")
    present_on_time = sum(1 for r in checkin_records if r["status"] == "Present")
    total_present = total_checkins

    total_absent = max(0, total_registered - total_present) if session_id else 0
    sessions_in_event = cursor.execute("SELECT id FROM sessions WHERE event_id = ?", (event_id,)).fetchall()
    if not session_id and sessions_in_event:
        total_session_seats = total_registered * len(sessions_in_event)
        total_absent = max(0, total_session_seats - total_checkins)

    if total_registered > 0:
        if session_id:
            attendance_percentage = round((total_present / total_registered * 100), 1)
        else:
            total_seats = total_registered * max(1, len(sessions_in_event))
            attendance_percentage = round((total_checkins / total_seats * 100), 1)
    else:
        attendance_percentage = 0.0


    duplicate_attempts = sum(1 for log in attempt_logs if log["attempt_type"] == "DUPLICATE")
    invalid_attempts = sum(1 for log in attempt_logs if log["attempt_type"] in ("INVALID_CREDENTIALS", "SESSION_INACTIVE"))

    time_bins = {}
    for r in checkin_records:
        try:
            t = datetime.strptime(r["checkin_time"], "%Y-%m-%d %H:%M:%S")
            minute_bin = (t.minute // 15) * 15
            bin_label = f"{t.strftime('%H')}:{minute_bin:02d}"
            time_bins[bin_label] = time_bins.get(bin_label, 0) + 1
        except Exception:
            continue

    sorted_bins = sorted(time_bins.items(), key=lambda x: x[0])
    attendance_over_time = [{"time": k, "count": v} for k, v in sorted_bins]

    peak_period = max(sorted_bins, key=lambda x: x[1])[0] if sorted_bins else "N/A"
    if peak_period != "N/A":
        h, m = peak_period.split(":")
        end_m = int(m) + 15
        end_h = int(h)
        if end_m >= 60:
            end_m -= 60
            end_h = (end_h + 1) % 24
        peak_period = f"{peak_period} - {end_h:02d}:{end_m:02d}"

    session_comparison = []
    for s in sessions_in_event:
        s_obj = cursor.execute("SELECT id, name FROM sessions WHERE id = ?", (s["id"],)).fetchone()
        cnt = cursor.execute("SELECT COUNT(*) as c FROM attendance_records WHERE session_id = ?", (s["id"],)).fetchone()["c"]
        late_cnt = cursor.execute("SELECT COUNT(*) as c FROM attendance_records WHERE session_id = ? AND status = 'Late'", (s["id"],)).fetchone()["c"]
        pct = round((cnt / total_registered * 100), 1) if total_registered > 0 else 0
        session_comparison.append({
            "session_id": s_obj["id"],
            "session_name": s_obj["name"],
            "total_checkins": cnt,
            "late_checkins": late_cnt,
            "on_time_checkins": cnt - late_cnt,
            "attendance_percentage": pct
        })

    feed_query = """
        SELECT ar.id, ar.checkin_time, ar.status, ar.admin_scanner_id,
               p.participant_id, p.full_name, p.organization,
               s.name as session_name
        FROM attendance_records ar
        JOIN participants p ON ar.participant_id = p.id
        JOIN sessions s ON ar.session_id = s.id
        WHERE ar.event_id = ?
    """
    feed_params = [event_id]
    if session_id:
        feed_query += " AND ar.session_id = ?"
        feed_params.append(session_id)
    feed_query += " ORDER BY ar.checkin_time DESC LIMIT 25"

    live_feed_rows = cursor.execute(feed_query, feed_params).fetchall()
    live_feed = [dict(r) for r in live_feed_rows]

    conn.close()

    return {
        "event_id": event_id,
        "session_id": session_id,
        "total_registered": total_registered,
        "total_present": total_present,
        "total_absent": total_absent,
        "attendance_percentage": attendance_percentage,
        "total_checkins": total_checkins,
        "late_arrivals": late_arrivals,
        "present_on_time": present_on_time,
        "duplicate_attempts": duplicate_attempts,
        "invalid_attempts": invalid_attempts,
        "peak_period": peak_period,
        "attendance_over_time": attendance_over_time,
        "session_comparison": session_comparison,
        "present_vs_absent": {
            "present": total_present,
            "absent": total_absent
        },
        "live_feed": live_feed
    }

def get_records_for_export(session_id=None, event_id=None, status_filter=None, org_filter=None):
    """Retrieve full attendance records for CSV, Excel, and PDF reporting."""
    conn = get_db_connection()
    query = """
        SELECT ar.id, p.participant_id, p.full_name, p.email, p.organization,
               e.event_code, e.name as event_name,
               s.name as session_name, s.session_date,
               ar.checkin_time, ar.status, ar.admin_scanner_id, ar.created_at
        FROM attendance_records ar
        JOIN participants p ON ar.participant_id = p.id
        JOIN events e ON ar.event_id = e.id
        JOIN sessions s ON ar.session_id = s.id
        WHERE 1=1
    """
    params = []
    if session_id:
        query += " AND ar.session_id = ?"
        params.append(session_id)
    elif event_id:
        query += " AND ar.event_id = ?"
        params.append(event_id)

    if status_filter and status_filter != "ALL":
        query += " AND ar.status = ?"
        params.append(status_filter)

    if org_filter and org_filter != "ALL":
        query += " AND p.organization = ?"
        params.append(org_filter)

    query += " ORDER BY ar.checkin_time DESC"
    rows = conn.execute(query, params).fetchall()
    conn.close()
    return [dict(r) for r in rows]
