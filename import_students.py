"""
Student Bulk Generator & Credential Provisioning Tool
Event Attendance Management System (Cyber-Attend)

Usage Examples:
1. Generate a blank CSV template:
   python import_students.py --template

2. Generate N sample student credentials automatically:
   python import_students.py --generate 50 --event-code TECHSTAR-26 --prefix TECHSTAR-26 --default-pin 2026

3. Import students from your own CSV / Excel file:
   python import_students.py --file my_students.csv --event-code TECHSTAR-26
"""

import os
import sys
import csv
import secrets
import argparse

if hasattr(sys.stdout, 'reconfigure'):
    sys.stdout.reconfigure(encoding='utf-8')
    sys.stderr.reconfigure(encoding='utf-8')

from database import (
    get_db_connection, get_all_events, register_participant,
    get_participant_by_code, hash_password
)


def create_csv_template(filename="student_roster_template.csv"):
    """Create a sample CSV template for bulk student registration."""
    fieldnames = ["participant_id", "full_name", "email", "organization", "password"]
    rows = [
        {
            "participant_id": "TECHSTAR-26-0001",
            "full_name": "Aarav Sharma",
            "email": "aarav.sharma@example.com",
            "organization": "GLA University - Dept of CSE",
            "password": "2026"
        },
        {
            "participant_id": "TECHSTAR-26-0002",
            "full_name": "Diya Patel",
            "email": "diya.patel@example.com",
            "organization": "GLA University - Dept of ECE",
            "password": "4589"
        },
        {
            "participant_id": "TECHSTAR-26-0003",
            "full_name": "Rohan Verma",
            "email": "rohan.verma@example.com",
            "organization": "E-Cell GLA",
            "password": "7812"
        }
    ]
    with open(filename, "w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(rows)
    print(f"✓ Sample template created: {filename}")
    print("Fill in this file and run:")
    print(f"   python import_students.py --file {filename} --event-code <YOUR_EVENT_CODE>\n")


def generate_students(event_code, count=25, prefix="TECHSTAR-26", default_pin=None):
    """Generate N student credentials with custom IDs and PINs."""
    conn = get_db_connection()
    event = conn.execute("SELECT * FROM events WHERE UPPER(event_code) = UPPER(?)", (event_code.strip(),)).fetchone()
    conn.close()

    if not event:
        print(f"Error: Event with code '{event_code}' not found in database.")
        print("Existing events:")
        for ev in get_all_events():
            print(f"  - [{ev['event_code']}] {ev['name']}")
        return

    event_id = event["id"]
    print(f"Target Event: [{event['event_code']}] {event['name']} (ID: {event_id})")
    print(f"Generating {count} student credentials...\n")

    handout_records = []
    success_count = 0

    first_names = ["Aarav", "Vivaan", "Aditya", "Vihaan", "Arjun", "Sai", "Reyansh", "Ayaan", "Krishna", "Ishaan",
                   "Diya", "Saanvi", "Ananya", "Aadhya", "Pari", "Chiara", "Riya", "Myra", "Isha", "Tara"]
    last_names = ["Sharma", "Verma", "Gupta", "Patel", "Singh", "Kumar", "Mishra", "Yadav", "Chauhan", "Joshi"]

    for i in range(1, count + 1):
        custom_id = f"{prefix}-{i:04d}"
        first = first_names[(i - 1) % len(first_names)]
        last = last_names[((i - 1) // len(first_names)) % len(last_names)]
        full_name = f"{first} {last}"
        email = f"{first.lower()}.{last.lower()}{i}@gla.ac.in"
        dept = "Computer Science & Engineering" if i % 2 == 0 else "Electronics & Communication"

        # Assign PIN: custom default or random 4-digit
        pin = default_pin if default_pin else f"{secrets.randbelow(9000) + 1000}"

        try:
            # Check if participant already exists
            existing = get_participant_by_code(custom_id)
            if existing:
                print(f"  [Skip] {custom_id} already exists.")
                continue

            p_id = register_participant(
                event_id=event_id,
                participant_id=custom_id,
                full_name=full_name,
                email=email,
                organization=dept,
                password=pin
            )
            success_count += 1
            handout_records.append({
                "participant_id": custom_id,
                "full_name": full_name,
                "email": email,
                "organization": dept,
                "access_pin": pin
            })
            print(f"  ✓ Created: {custom_id} | {full_name} | PIN: {pin}")
        except Exception as e:
            print(f"  ✗ Failed for {custom_id}: {e}")

    # Export handout sheet for students
    if handout_records:
        export_filename = f"student_credentials_{event_code.lower()}.csv"
        with open(export_filename, "w", newline="", encoding="utf-8") as f:
            writer = csv.DictWriter(f, fieldnames=["participant_id", "full_name", "email", "organization", "access_pin"])
            writer.writeheader()
            writer.writerows(handout_records)
        print(f"\n=======================================================")
        print(f"✓ Successfully provisioned {success_count} students in Supabase!")
        print(f"✓ Student handout saved to: {export_filename}")
        print(f"Share this file with your team or students before the event.")
        print(f"=======================================================\n")


def import_from_csv(filename, event_code):
    """Import participants from an existing CSV file into Supabase."""
    if not os.path.isfile(filename):
        print(f"Error: File '{filename}' not found.")
        return

    conn = get_db_connection()
    event = conn.execute("SELECT * FROM events WHERE UPPER(event_code) = UPPER(?)", (event_code.strip(),)).fetchone()
    conn.close()

    if not event:
        print(f"Error: Event with code '{event_code}' not found.")
        return

    event_id = event["id"]
    print(f"Importing students from '{filename}' into Event '{event['name']}'...")

    imported = 0
    errors = 0

    with open(filename, "r", encoding="utf-8-sig") as f:
        reader = csv.DictReader(f)
        for row in reader:
            pid = (row.get("participant_id") or row.get("roll_no") or row.get("id") or "").strip().upper()
            name = (row.get("full_name") or row.get("name") or "").strip()
            email = (row.get("email") or "").strip().lower()
            org = (row.get("organization") or row.get("department") or row.get("branch") or "GLA University").strip()
            pin = (row.get("password") or row.get("pin") or "").strip()

            if not pid or not name:
                continue

            if not email:
                email = f"{pid.lower()}@participant.local"

            if not pin:
                pin = f"{secrets.randbelow(9000) + 1000}"

            try:
                register_participant(event_id, pid, name, email, org, pin)
                imported += 1
                print(f"  ✓ Registered: {pid} ({name}) - PIN: {pin}")
            except Exception as e:
                errors += 1
                print(f"  ✗ Skipped {pid}: {e}")

    print(f"\nImport Finished: {imported} participants registered, {errors} skipped.")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Student Bulk Generator & Provisioning Tool for Supabase")
    parser.add_argument("--template", action="store_true", help="Generate a blank CSV roster template")
    parser.add_argument("--generate", type=int, help="Number of students to generate automatically")
    parser.add_argument("--event-code", type=str, default="TECHSTAR-26", help="Target event code (e.g. TECHSTAR-26)")
    parser.add_argument("--prefix", type=str, default="TECHSTAR-26", help="Participant ID prefix (e.g. TECHSTAR-26 or GLA)")
    parser.add_argument("--default-pin", type=str, help="Common default PIN (e.g. 2026), or leave empty for random 4-digit PINs")
    parser.add_argument("--file", type=str, help="Path to CSV file to import")

    args = parser.parse_args()

    if args.template:
        create_csv_template()
    elif args.file:
        import_from_csv(args.file, args.event_code)
    elif args.generate:
        generate_students(args.event_code, count=args.generate, prefix=args.prefix, default_pin=args.default_pin)
    else:
        parser.print_help()
