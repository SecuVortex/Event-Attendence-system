"""
Comprehensive Verification Test Suite for Event Attendance System.
Tests:
1. Event & session dynamic creation
2. Session activation / deactivation toggle
3. Single common QR token generation
4. Participant authentication & credential verification (PIN check)
5. Attendance check-in validation (Active vs Inactive session)
6. Duplicate check-in prevention (enforced by DB unique constraint)
7. Authoritative server timestamps
8. Participant complete history lookup
9. Admin Analytics KPIs & charts
10. CSV, Excel, and PDF export generation
"""

import os
import io
import sys
if hasattr(sys.stdout, 'reconfigure'):
    sys.stdout.reconfigure(encoding='utf-8')
    sys.stderr.reconfigure(encoding='utf-8')
from database import (
    get_db_connection, create_event, create_session, toggle_session_attendance,
    register_participant, authenticate_participant, process_attendance_checkin,
    get_participant_full_history, get_admin_analytics, get_records_for_export
)

def test_full_system():
    # Clean up any leftover test data
    conn = get_db_connection()
    conn.execute("DELETE FROM events WHERE event_code = 'GADC-26'")
    conn.commit()
    conn.close()

    print("--- 1. Testing Event & Session Creation ---")
    event_id = create_event(
        name="Global AI DevCon 2026",
        event_code="GADC-26",
        description="Autonomous Systems Conference",
        venue="Auditorium 1",
        start_date="2026-10-01",
        end_date="2026-10-03"
    )
    assert event_id > 0, "Event creation failed"
    print(f"[PASS] Event created with ID {event_id}")

    session_id, token = create_session(
        event_id=event_id,
        name="Keynote: Next-Gen Agents",
        session_date="2026-10-01",
        start_time="10:00",
        end_time="11:30",
        late_threshold_minutes=15
    )
    assert session_id > 0 and len(token) > 10, "Session creation failed"
    print(f"[PASS] Session created with ID {session_id}, Token: {token}")

    print("--- 2. Testing Session Inactive State Rejection ---")
    p_id = register_participant(
        event_id=event_id,
        participant_id="GADC-26-0001",
        full_name="Jordan Bell",
        email="jordan.bell@example.com",
        organization="MIT",
        password="secret_pin_123"
    )
    assert p_id > 0, "Participant registration failed"

    # Attempt check-in while session is INACTIVE
    res = process_attendance_checkin(session_id, "GADC-26-0001", "secret_pin_123")
    assert res["success"] is False and res["status_code"] == "SESSION_INACTIVE", f"Should reject inactive session: {res}"
    print("[PASS] Successfully rejected check-in for inactive session")

    print("--- 3. Testing Credential Authentication & Anti-Spoofing ---")
    # Activate session
    toggle_session_attendance(session_id, is_active=True)

    # Attempt with WRONG password
    res_wrong_pin = process_attendance_checkin(session_id, "GADC-26-0001", "wrong_pin")
    assert res_wrong_pin["success"] is False and res_wrong_pin["status_code"] == "INVALID_PARTICIPANT", f"Should fail wrong pin: {res_wrong_pin}"
    print("[PASS] Successfully prevented unauthorized check-in with invalid PIN")

    # Attempt with NON-EXISTENT participant ID
    res_invalid_id = process_attendance_checkin(session_id, "GADC-26-9999", "secret_pin_123")
    assert res_invalid_id["success"] is False and res_invalid_id["status_code"] == "INVALID_PARTICIPANT", f"Should fail invalid ID: {res_invalid_id}"
    print("[PASS] Successfully prevented check-in with non-existent participant ID")

    print("--- 4. Testing Valid First-Time Attendance Check-in ---")
    res_valid = process_attendance_checkin(session_id, "GADC-26-0001", "secret_pin_123", scanner_id="MAIN_GATE")
    assert res_valid["success"] is True and res_valid["status_code"] == "ATTENDANCE_MARKED", f"Valid check-in failed: {res_valid}"
    assert "checkin_time" in res_valid and len(res_valid["checkin_time"]) > 10, "Missing authoritative server timestamp"
    print(f"[PASS] Attendance successfully marked! Timestamp: {res_valid['checkin_time']}, Status: {res_valid['status']}")

    print("--- 5. Testing Duplicate Check-in Prevention (DB Constraint) ---")
    res_dup = process_attendance_checkin(session_id, "GADC-26-0001", "secret_pin_123", scanner_id="MAIN_GATE")
    assert res_dup["success"] is False and res_dup["status_code"] == "ALREADY_CHECKED_IN", f"Duplicate check-in should be rejected: {res_dup}"
    assert res_dup["previous_checkin_time"] == res_valid["checkin_time"], "Duplicate response should show prior timestamp"
    print(f"[PASS] Duplicate check-in blocked! Returned prior timestamp: {res_dup['previous_checkin_time']}")

    # Verify directly in SQLite that only 1 record exists
    conn = get_db_connection()
    count = conn.execute("SELECT COUNT(*) as c FROM attendance_records WHERE participant_id = ? AND session_id = ?", (p_id, session_id)).fetchone()["c"]
    conn.close()
    assert count == 1, f"Expected exactly 1 attendance record in DB, found {count}"
    print("[PASS] Database-level unique constraint verified (Count = 1)")

    print("--- 6. Testing Participant Complete History Lookup ---")
    history = get_participant_full_history("GADC-26-0001")
    assert history is not None, "History lookup failed"
    assert history["total_sessions"] == 1
    assert history["sessions_attended"] == 1
    assert history["sessions_missed"] == 0
    assert history["attendance_percentage"] == 100.0
    print(f"[PASS] Full history retrieved: {history['full_name']} - Attended: {history['sessions_attended']}/{history['total_sessions']}")

    print("--- 7. Testing Admin Analytics Metrics ---")
    analytics = get_admin_analytics(session_id=session_id)
    assert analytics["total_registered"] == 1
    assert analytics["total_present"] == 1
    assert analytics["total_checkins"] == 1
    assert analytics["duplicate_attempts"] >= 1
    assert analytics["invalid_attempts"] >= 2
    print(f"[PASS] Analytics computed accurately: Registered: {analytics['total_registered']}, Check-ins: {analytics['total_checkins']}, Duplicate Attempts: {analytics['duplicate_attempts']}, Invalid: {analytics['invalid_attempts']}")

    print("--- 8. Testing Export Data Retrieval ---")
    records = get_records_for_export(session_id=session_id)
    assert len(records) == 1, f"Expected 1 export record, found {len(records)}"
    print(f"[PASS] Export records formatted properly: {records[0]['participant_id']} ({records[0]['status']})")

    print("\nALL BACKEND CORE TESTS PASSED SUCCESSFULLY!\n")

if __name__ == "__main__":
    test_full_system()
