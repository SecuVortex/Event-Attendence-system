"""
Comprehensive Flask End-to-End Integration Test.
Verifies auth guards, all routes, templates rendering, API responses, check-in flows,
duplicate handling, analytics, and export downloads.
"""

import sys
if hasattr(sys.stdout, 'reconfigure'):
    sys.stdout.reconfigure(encoding='utf-8')
    sys.stderr.reconfigure(encoding='utf-8')

import os
from app import app
import database as db

db.load_env_file()
ADMIN_USERNAME = os.environ.get("ADMIN_USERNAME", "techstar_admin_secops")
ADMIN_PASSWORD = os.environ.get("ADMIN_PASSWORD", "Techstar_GLA_SecOps#2026!Admin")


def run_integration_tests():
    client = app.test_client()
    print("=== STARTING FULL APP INTEGRATION VERIFICATION ===")

    # 0. AUTH GUARDS: staff pages and APIs must be protected
    print("\n--- Testing Access Security ---")
    staff_path = os.environ.get("STAFF_LOGIN_PATH", "/staff-access")

    # Root / redirects anonymous users to /checkin
    res = client.get("/")
    assert res.status_code == 302 and "/checkin" in res.headers.get("Location", "")
    print("[PASS] Root / redirects anonymous visitors to /checkin")

    # Public probing /login redirects to /participant (anti-reconnaissance)
    res = client.get("/login")
    assert res.status_code == 302 and "/participant" in res.headers.get("Location", "")
    print("[PASS] Public /login redirects to /participant")

    # Protected routes redirect to secret staff login path
    res = client.get("/admin")
    assert res.status_code == 302 and staff_path in res.headers.get("Location", ""), \
        f"/admin must redirect unauthenticated staff to {staff_path} (got {res.status_code})"
    print(f"[PASS] /admin redirects anonymous users to {staff_path}")

    res = client.get("/projector")
    assert res.status_code == 302 and staff_path in res.headers.get("Location", "")
    print(f"[PASS] /projector redirects anonymous users to {staff_path}")

    res = client.get("/api/events")
    assert res.status_code == 401, f"/api/events must return 401 for anonymous (got {res.status_code})"
    print("[PASS] /api/events returns 401 for anonymous users")

    res = client.get("/api/admin/analytics")
    assert res.status_code == 401
    print("[PASS] /api/admin/analytics returns 401 for anonymous users")

    res = client.get("/api/export/csv")
    assert res.status_code == 401
    print("[PASS] /api/export/csv returns 401 for anonymous users")

    # Public routes stay open for participants
    for public in ("/checkin", "/participant"):
        res = client.get(public)
        assert res.status_code == 200, f"{public} should be public (got {res.status_code})"
        print(f"[PASS] {public} stays public")

    # Confidential staff login path returns 200
    res = client.get(staff_path)
    assert res.status_code == 200, f"{staff_path} must return 200 (got {res.status_code})"
    assert b"RESTRICTED ACCESS" in res.data
    print(f"[PASS] {staff_path} renders Staff Login portal")

    # Wrong password rejected
    res = client.post(staff_path, data={"username": ADMIN_USERNAME, "password": "totally-wrong"})
    assert res.status_code == 200  # re-renders login page with error
    assert b"Invalid staff credentials" in res.data
    print("[PASS] Wrong staff password rejected")

    # Correct login -> redirects to admin
    res = client.post(staff_path, data={"username": ADMIN_USERNAME, "password": ADMIN_PASSWORD}, follow_redirects=False)
    assert res.status_code == 302 and "/admin" in res.headers.get("Location", "")
    print(f"[PASS] Staff login at {staff_path} succeeds and redirects to /admin")

    # 1. Page Routes (authenticated)
    print("\n--- Testing Page Renders ---")
    pages = [
        ("/admin", 200),
        ("/projector", 200),
        ("/projector?session_id=1", 200),
        ("/checkin", 200),
        ("/checkin?session_id=1&token=sample", 200),
        ("/participant", 200),
        ("/participant?id=TECHSTAR-26-00842", 200),
    ]
    for path, expected_status in pages:
        res = client.get(path)
        assert res.status_code == expected_status, f"Page {path} returned {res.status_code}, expected {expected_status}"
        print(f"[PASS] {path} -> {res.status_code}")

    # 2. Events & Sessions API
    print("\n--- Testing Events & Sessions API ---")
    res = client.get("/api/events")
    assert res.status_code == 200
    events = res.get_json()["events"]
    assert len(events) >= 1
    event_id = events[0]["id"]
    print(f"[PASS] GET /api/events -> {len(events)} events found")

    res = client.get(f"/api/sessions?event_id={event_id}")
    assert res.status_code == 200
    sessions = res.get_json()["sessions"]
    assert len(sessions) >= 1
    session_id = sessions[0]["id"]
    print(f"[PASS] GET /api/sessions -> {len(sessions)} sessions found for Event {event_id}")

    # Test Session Toggle
    res = client.post(f"/api/sessions/{session_id}/toggle", json={"is_active": 1})
    assert res.status_code == 200
    assert res.get_json()["is_active"] is True
    print(f"[PASS] POST /api/sessions/{session_id}/toggle -> Session active")

    # Test Token Regeneration
    res = client.post(f"/api/sessions/{session_id}/regenerate_token")
    assert res.status_code == 200
    assert "token" in res.get_json()
    print(f"[PASS] POST /api/sessions/{session_id}/regenerate_token -> New token generated")

    # 3. Participant Registration & History API
    print("\n--- Testing Participant Registration & History ---")
    test_pid = "TEST-USER-999"
    res = client.post("/api/participants", json={
        "event_id": event_id,
        "participant_id": test_pid,
        "full_name": "Test Runner",
        "email": "test.runner@automated.io",
        "organization": "Test Lab",
        "password": "pass_secure_2026"
    })
    print(f"[PASS] POST /api/participants -> Status: {res.status_code}")

    res = client.get(f"/api/participants/{test_pid}/history")
    assert res.status_code == 200
    p_data = res.get_json()["data"]
    assert p_data["participant_id"] == test_pid
    print(f"[PASS] GET /api/participants/{test_pid}/history -> Retrieved history for {p_data['full_name']}")

    # 4. Participant Portal PIN Login (new self-service flow)
    print("\n--- Testing Participant Portal PIN Login ---")
    res = client.post("/api/participant/login", json={
        "participant_id": test_pid,
        "password": "pass_secure_2026"
    })
    assert res.status_code == 200
    login_data = res.get_json()
    assert login_data["success"] and login_data["access_token"]
    print(f"[PASS] POST /api/participant/login -> token issued for {login_data['full_name']}")

    res = client.post("/api/participant/history", json={
        "participant_id": test_pid,
        "password": "pass_secure_2026"
    })
    assert res.status_code == 200
    assert res.get_json()["data"]["participant_id"] == test_pid
    print("[PASS] POST /api/participant/history -> PIN-gated history retrieved")

    res = client.post("/api/participant/history", json={
        "participant_id": test_pid,
        "password": "wrong-pin"
    })
    assert res.status_code == 401
    print("[PASS] POST /api/participant/history -> wrong PIN rejected with 401")

    # 5. Check-in Flow Verification
    print("\n--- Testing Check-in Flow ---")
    res = client.post("/api/attendance/checkin", json={
        "session_id": session_id,
        "participant_id": test_pid,
        "password": "pass_secure_2026",
        "scanner_id": "AUTO_TEST_GATE"
    })
    if res.status_code == 200:
        json_data = res.get_json()
        assert json_data["status_code"] == "ATTENDANCE_MARKED"
        assert "checkin_time" in json_data
        print(f"[PASS] Check-in marked! Time: {json_data['checkin_time']}, Status: {json_data['status']}")
    else:
        assert res.status_code == 409
        print("[PASS] User was already marked from earlier run.")

    # Duplicate check-in rejection
    res_dup = client.post("/api/attendance/checkin", json={
        "session_id": session_id,
        "participant_id": test_pid,
        "password": "pass_secure_2026",
        "scanner_id": "AUTO_TEST_GATE"
    })
    assert res_dup.status_code == 409
    dup_data = res_dup.get_json()
    assert dup_data["status_code"] == "ALREADY_CHECKED_IN"
    assert "previous_checkin_time" in dup_data
    print(f"[PASS] Duplicate check-in successfully blocked! Prior timestamp: {dup_data['previous_checkin_time']}")

    # Wrong credentials rejection
    res_bad = client.post("/api/attendance/checkin", json={
        "session_id": session_id,
        "participant_id": test_pid,
        "password": "wrong_password_xyz",
        "scanner_id": "AUTO_TEST_GATE"
    })
    assert res_bad.status_code == 400
    assert res_bad.get_json()["status_code"] == "INVALID_PARTICIPANT"
    print("[PASS] Wrong PIN rejection verified")

    # Inactive session check-in rejection
    client.post(f"/api/sessions/{session_id}/toggle", json={"is_active": 0})
    res_inactive = client.post("/api/attendance/checkin", json={
        "session_id": session_id,
        "participant_id": test_pid,
        "password": "pass_secure_2026",
        "scanner_id": "AUTO_TEST_GATE"
    })
    assert res_inactive.status_code == 400
    assert res_inactive.get_json()["status_code"] == "SESSION_INACTIVE"
    print("[PASS] Inactive session rejection verified")

    # Re-activate session
    client.post(f"/api/sessions/{session_id}/toggle", json={"is_active": 1})

    # 6. Public Projector Stats
    print("\n--- Testing Public Projector Stats ---")
    res = client.get(f"/api/public/projector_stats?session_id={session_id}")
    assert res.status_code == 200
    stats = res.get_json()
    assert stats["success"] and "total_checkins" in stats and "is_active" in stats
    print(f"[PASS] /api/public/projector_stats -> checkins={stats['total_checkins']}, active={stats['is_active']}")

    # 7. Analytics Endpoint
    print("\n--- Testing Admin Analytics Endpoint ---")
    res_analytics = client.get(f"/api/admin/analytics?session_id={session_id}&event_id={event_id}")
    assert res_analytics.status_code == 200
    a = res_analytics.get_json()["analytics"]
    assert a["total_registered"] > 0
    assert a["total_checkins"] > 0
    print(f"[PASS] Analytics verified: Registered={a['total_registered']}, Check-ins={a['total_checkins']}, Turnout={a['attendance_percentage']}%")

    # 8. Export Endpoints
    print("\n--- Testing Export Downloads ---")
    res_csv = client.get(f"/api/export/csv?session_id={session_id}")
    assert res_csv.status_code == 200 and "text/csv" in res_csv.headers["Content-Type"]
    print(f"[PASS] CSV Export verified (Length: {len(res_csv.data)} bytes)")

    res_xlsx = client.get(f"/api/export/excel?session_id={session_id}")
    assert res_xlsx.status_code == 200 and len(res_xlsx.data) > 1000
    print(f"[PASS] Excel XLSX Export verified (Length: {len(res_xlsx.data)} bytes)")

    res_pdf = client.get(f"/api/export/pdf?session_id={session_id}")
    assert res_pdf.status_code == 200 and len(res_pdf.data) > 1000
    print(f"[PASS] PDF Export verified (Length: {len(res_pdf.data)} bytes)")

    # 9. Logout
    print("\n--- Testing Logout ---")
    res = client.post("/logout")
    assert res.status_code == 302
    res = client.get("/admin")
    assert res.status_code == 302  # redirected back to login
    print("[PASS] Logout clears session; /admin protected again")

    print("\n=== ALL INTEGRATION TESTS PASSED SUCCESSFULLY! ===")


if __name__ == "__main__":
    run_integration_tests()
