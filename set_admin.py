import os
import database as db

# Load .env directly
db.load_env_file()
username = os.environ.get("ADMIN_USERNAME", "admin").strip()
password = os.environ.get("ADMIN_PASSWORD", "").strip()

if not password:
    print("ERROR: ADMIN_PASSWORD environment variable must be configured in .env!")
    exit(1)

print(f"Loading credentials from .env:")
print(f"  ADMIN_USERNAME = {username}")

conn = db.get_db_connection()
# Clean all staff accounts
conn.execute("DELETE FROM staff_users;")
conn.commit()

# Create fresh staff user
db.create_staff_user(username, password, display_name="Lead SecOps Administrator")

# Verify password authentication
user = db.get_staff_user_by_username(username)
if not user:
    print("ERROR: User not found in database after creation!")
    exit(1)

ok, _ = db.verify_password(user["password_hash"], password)
print(f"Database verify result: {ok}")

if ok:
    print(f"\n[PASS] SUCCESS: Staff user '{username}' is active in Supabase and verified with the password!")
else:
    print("\n[FAIL] FAILED: Verification failed.")
    exit(1)

conn.close()
