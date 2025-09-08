import os, sqlite3
from werkzeug.security import generate_password_hash

try:
    from dotenv import load_dotenv
    load_dotenv()
except Exception:
    pass

DB = "app.db"
TARGET_EMAIL = os.getenv("ADMIN_EMAIL") or os.getenv("EMAIL_USER") or "alimarribaloch@gmail.com"

conn = sqlite3.connect(DB)
conn.row_factory = sqlite3.Row
c = conn.cursor()

# 1) Target user ensure karo
c.execute("SELECT id FROM users WHERE email=?;", (TARGET_EMAIL,))
row = c.fetchone()

if row:
    target_id = row["id"]
else:
    c.execute(
        "INSERT INTO users (name, email, password_hash, is_admin) VALUES (?,?,?,1);",
        ("Admin", TARGET_EMAIL, generate_password_hash("admin123"))
    )
    conn.commit()
    target_id = c.lastrowid

print("✅ Target user id:", target_id, "email:", TARGET_EMAIL)

# 2) Koi orders jinka user_id invalid hai (ya null hai)?
c.execute("""
    UPDATE orders 
    SET user_id=? 
    WHERE user_id IS NULL 
       OR user_id NOT IN (SELECT id FROM users)
""", (target_id,))
conn.commit()

print("✅ Orders reassigned to:", TARGET_EMAIL)

conn.close()