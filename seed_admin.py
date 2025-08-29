# seed_admin.py
import sqlite3
from werkzeug.security import generate_password_hash

DB_FILE = "grab.db"

def seed():
    conn = sqlite3.connect(DB_FILE)
    cur = conn.cursor()
    cur.execute("SELECT id FROM users WHERE email=?", ("admin@example.com",))
    if cur.fetchone():
        print("Admin already exists.")
    else:
        cur.execute(
            "INSERT INTO users (name,email,password_hash,role) VALUES (?,?,?,?)",
            ("Admin", "admin@example.com", generate_password_hash("admin123"), "admin")
        )
        conn.commit()
        print("Admin created: admin@example.com / admin123")
    conn.close()

if __name__ == "__main__":
    seed()