"""
Decoupled Seed Data Script for TECHSTAR 2026 Showcase.
This script is completely separated from the core application logic.
Run this script to initialize and populate sample data for testing and demonstration.
"""

from database import (
    init_db, create_event, create_session, register_participant,
    toggle_session_attendance, process_attendance_checkin, log_attempt,
    get_db_connection
)
from datetime import datetime, timedelta

def run_seed():
    print("Initializing database tables...")
    init_db()

    conn = get_db_connection()
    # Check if TECHSTAR already exists
    existing = conn.execute("SELECT id FROM events WHERE event_code = 'TECHSTAR-26'").fetchone()
    if existing:
        print("TECHSTAR 2026 event already seeded (ID: {}).".format(existing['id']))
        conn.close()
        return existing['id']
    conn.close()

    print("Seeding TECHSTAR 2026 Event...")
    event_id = create_event(
        name="TECHSTAR 2026 Global Innovation Summit",
        event_code="TECHSTAR-26",
        description="The premier gathering of global innovators, engineers, and founders in AI, hardware, and scalable systems.",
        venue="Hall A - Grand Convention Center & Innovation Lab",
        start_date="2026-09-09",
        end_date="2026-09-11"
    )

    print(f"Created Event: TECHSTAR-26 (ID: {event_id})")

    # 2. Create Realistic Sessions (Dynamic, not hardcoded into app)
    print("Creating dynamic event sessions...")
    s1_id, _ = create_session(
        event_id=event_id,
        name="Opening Ceremony & Keynote",
        session_date="2026-09-09",
        start_time="09:00",
        end_time="10:30",
        late_threshold_minutes=15
    )
    # Activate session 1 attendance by default for live testing
    toggle_session_attendance(s1_id, is_active=True)

    s2_id, _ = create_session(
        event_id=event_id,
        name="Workshop: Autonomous Agentic Architectures",
        session_date="2026-09-09",
        start_time="11:00",
        end_time="13:00",
        late_threshold_minutes=15
    )

    s3_id, _ = create_session(
        event_id=event_id,
        name="Hackathon Track & Mentorship Checkpoint",
        session_date="2026-09-09",
        start_time="14:30",
        end_time="17:00",
        late_threshold_minutes=20
    )

    s4_id, _ = create_session(
        event_id=event_id,
        name="Pitch Arena & Valedictory Showcase",
        session_date="2026-09-10",
        start_time="16:00",
        end_time="18:30",
        late_threshold_minutes=15
    )

    print("Created 4 sessions.")

    # 3. Register Sample Participants
    sample_roster = [
        ("TECHSTAR-26-00842", "Alex Morgan", "alex.morgan@techstar.io", "Stanford University", "2026"),
        ("TECHSTAR-26-00101", "Elena Vance", "elena.vance@blackmesa.org", "MIT Media Lab", "2026"),
        ("TECHSTAR-26-00102", "Marcus Brody", "marcus.brody@oxford.ac.uk", "Oxford Computing", "2026"),
        ("TECHSTAR-26-00103", "Priya Sharma", "priya.sharma@iitb.ac.in", "IIT Bombay", "2026"),
        ("TECHSTAR-26-00104", "Kenji Sato", "kenji.sato@u-tokyo.ac.jp", "University of Tokyo", "2026"),
        ("TECHSTAR-26-00105", "Devon Chen", "devon.chen@berkeley.edu", "UC Berkeley", "2026"),
        ("TECHSTAR-26-00106", "Sara Lindqvist", "sara.l@kth.se", "KTH Royal Institute", "2026"),
        ("TECHSTAR-26-00107", "Rahul Verma", "rahul.v@bits-pilani.ac.in", "BITS Pilani", "2026"),
        ("TECHSTAR-26-00108", "Amira Hassan", "amira.h@aucegypt.edu", "American University Cairo", "2026"),
        ("TECHSTAR-26-00109", "Lucas Dubois", "lucas.dubois@polytechnique.fr", "Ecole Polytechnique", "2026"),
        ("TECHSTAR-26-00110", "Chloe Martin", "chloe.m@cam.ac.uk", "University of Cambridge", "2026"),
        ("TECHSTAR-26-00111", "Vikram Malhotra", "vikram.m@iitd.ac.in", "IIT Delhi", "2026"),
        ("TECHSTAR-26-00112", "Hannah Schmidt", "hannah.s@tum.de", "TU Munich", "2026"),
        ("TECHSTAR-26-00113", "Gabriel Silva", "gabriel.silva@usp.br", "University of Sao Paulo", "2026"),
        ("TECHSTAR-26-00114", "Zack Snyder", "zack.s@cmu.edu", "Carnegie Mellon", "2026"),
        ("TECHSTAR-26-00115", "Aisha Khan", "aisha.k@lums.edu.pk", "LUMS Tech", "2026"),
        ("TECHSTAR-26-00116", "Mateo Rossi", "mateo.r@polimi.it", "Politecnico di Milano", "2026"),
        ("TECHSTAR-26-00117", "Ananya Deshmukh", "ananya.d@iitm.ac.in", "IIT Madras", "2026"),
        ("TECHSTAR-26-00118", "Liam O'Connor", "liam.oc@tcd.ie", "Trinity College Dublin", "2026"),
        ("TECHSTAR-26-00119", "Sophia Wang", "sophia.w@tsinghua.edu.cn", "Tsinghua University", "2026"),
        ("TECHSTAR-26-00120", "Julian Thorne", "julian.t@harvard.edu", "Harvard Innovation Lab", "2026"),
        ("TECHSTAR-26-00121", "Tanvi Agarwal", "tanvi.a@iiit.ac.in", "IIIT Hyderabad", "2026"),
        ("TECHSTAR-26-00122", "Arthur Pendelton", "arthur.p@imperial.ac.uk", "Imperial College London", "2026"),
        ("TECHSTAR-26-00123", "Fatima Al-Nuaimi", "fatima.n@kaust.edu.sa", "KAUST", "2026"),
        ("TECHSTAR-26-00124", "Rohan Gupta", "rohan.g@dtu.ac.in", "Delhi Tech University", "2026")
    ]

    participant_db_ids = {}
    print("Registering sample participants (Default PIN: 2026)...")
    for pid, name, email, org, pin in sample_roster:
        p_id = register_participant(event_id, pid, name, email, org, pin)
        participant_db_ids[pid] = p_id

    # 4. Seed some initial check-ins for Session 1 to provide immediate rich dashboard data
    print("Seeding initial verified check-in data...")
    conn = get_db_connection()
    c = conn.cursor()

    # Seed 16 check-ins for Session 1 with varying timestamps
    checkin_samples = [
        ("TECHSTAR-26-00842", "2026-09-09 09:04:12", "Present"),
        ("TECHSTAR-26-00101", "2026-09-09 09:07:45", "Present"),
        ("TECHSTAR-26-00102", "2026-09-09 09:09:18", "Present"),
        ("TECHSTAR-26-00103", "2026-09-09 09:11:02", "Present"),
        ("TECHSTAR-26-00104", "2026-09-09 09:12:30", "Present"),
        ("TECHSTAR-26-00105", "2026-09-09 09:14:50", "Present"),
        ("TECHSTAR-26-00106", "2026-09-09 09:15:21", "Late"),
        ("TECHSTAR-26-00107", "2026-09-09 09:18:40", "Late"),
        ("TECHSTAR-26-00108", "2026-09-09 09:22:15", "Late"),
        ("TECHSTAR-26-00109", "2026-09-09 09:23:55", "Late"),
        ("TECHSTAR-26-00110", "2026-09-09 09:05:33", "Present"),
        ("TECHSTAR-26-00111", "2026-09-09 09:08:14", "Present"),
        ("TECHSTAR-26-00112", "2026-09-09 09:13:42", "Present"),
        ("TECHSTAR-26-00113", "2026-09-09 09:27:01", "Late"),
        ("TECHSTAR-26-00114", "2026-09-09 09:06:50", "Present"),
        ("TECHSTAR-26-00115", "2026-09-09 09:10:19", "Present"),
    ]

    for pcode, tstamp, status in checkin_samples:
        p_db_id = participant_db_ids.get(pcode)
        if p_db_id:
            c.execute("""
                INSERT INTO attendance_records (participant_id, event_id, session_id, checkin_time, status, admin_scanner_id, created_at)
                VALUES (?, ?, ?, ?, ?, 'GATE_ALPHA_01', ?)
            """, (p_db_id, event_id, s1_id, tstamp, status, tstamp))

    # Also log a duplicate attempt and an invalid attempt for realistic telemetry
    c.execute("""
        INSERT INTO attendance_logs (session_id, participant_code_attempted, attempt_type, message, scanner_id, created_at)
        VALUES (?, 'TECHSTAR-26-00842', 'DUPLICATE', 'Duplicate check-in attempt by Alex Morgan', 'GATE_ALPHA_01', '2026-09-09 09:15:00')
    """, (s1_id,))

    c.execute("""
        INSERT INTO attendance_logs (session_id, participant_code_attempted, attempt_type, message, scanner_id, created_at)
        VALUES (?, 'TECHSTAR-26-99999', 'INVALID_CREDENTIALS', 'Invalid Participant ID or Access PIN', 'GATE_ALPHA_01', '2026-09-09 09:20:00')
    """, (s1_id,))

    conn.commit()
    conn.close()

    print("Seed complete! Sample participant Alex Morgan (ID: TECHSTAR-26-00842, PIN: 2026) is ready.")
    return event_id

if __name__ == "__main__":
    run_seed()
