import sqlite3
from werkzeug.security import generate_password_hash

EMAIL = "admin@example.com"
PASSWORD = "admin123"
NAME = "Admin"
ROLE = "admin"

con = sqlite3.connect("app.db")
cur = con.cursor()

# ensure users table exists
cur.execute("""CREATE TABLE IF NOT EXISTS users (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  name TEXT NOT NULL,
  phone TEXT UNIQUE,
  email TEXT UNIQUE,
  password_hash TEXT NOT NULL,
  role TEXT DEFAULT 'customer'
)""")

# upsert simple
cur.execute("SELECT id FROM users WHERE email = ?", (EMAIL,))
row = cur.fetchone()
if row:
    cur.execute("UPDATE users SET password_hash=?, name=?, role=? WHERE id=?",
                (generate_password_hash(PASSWORD), NAME, ROLE, row[0]))
    print("Updated existing admin:", EMAIL)
else:
    cur.execute("INSERT INTO users (name, email, password_hash, role) VALUES (?,?,?,?)",
                (NAME, EMAIL, generate_password_hash(PASSWORD), ROLE))
    print("Inserted admin:", EMAIL)

con.commit()
con.close()