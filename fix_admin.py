# fix_admin.py
import os, sqlite3
from werkzeug.security import generate_password_hash

# .env load (optional)
try:
    from dotenv import load_dotenv
    load_dotenv()
except Exception:
    pass

BASE_DIR = os.path.abspath(os.path.dirname(__file__))
DB_PATH  = os.path.join(BASE_DIR, os.environ.get("DB_NAME", "app.db"))

# kis email ko admin banana hai:
TARGET_EMAIL = (
    os.getenv("ADMIN_EMAIL")
    or os.getenv("EMAIL_USER")
    or "admin@example.com"
)

NEW_PASSWORD = "admin123"

def main():
    print(f"Using DB: {DB_PATH}")
    print(f"Target admin email: {TARGET_EMAIL}")

    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    cur = conn.cursor()

    # agar galti se admin@local bacha hai to hata do
    cur.execute("DELETE FROM users WHERE email = ?", ("admin@local",))
    if cur.rowcount:
        print("Removed stale user: admin@local")

    # check target admin
    cur.execute("SELECT id, email, is_admin FROM users WHERE email = ?", (TARGET_EMAIL,))
    row = cur.fetchone()

    pwd_hash = generate_password_hash(NEW_PASSWORD)

    if row:
        cur.execute(
            "UPDATE users SET password_hash=?, is_admin=1 WHERE id=?",
            (pwd_hash, row["id"])
        )
        print("Updated existing admin user + password reset.")
    else:
        cur.execute(
            "INSERT INTO users (name, email, password_hash, is_admin) VALUES (?,?,?,1)",
            ("Admin", TARGET_EMAIL, pwd_hash)
        )
        print("Created NEW admin user.")

    conn.commit()
    conn.close()

    print("\nDONE ✅")
    print(f"Login now with:\n  Email: {TARGET_EMAIL}\n  Password: {NEW_PASSWORD}")

if __name__ == "__main__":
    main()