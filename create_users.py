import sqlite3

conn = sqlite3.connect('grab.db')
cursor = conn.cursor()

# ✅ Users table banaye agar na ho to
cursor.execute('''
CREATE TABLE IF NOT EXISTS users (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    username TEXT NOT NULL UNIQUE,
    password TEXT NOT NULL
)
''')

# ✅ Admin user daalein
cursor.execute("INSERT OR IGNORE INTO users (username, password) VALUES (?, ?)",
               ('admin', 'admin123'))

conn.commit()
conn.close()

print("✅ Users table created & admin user added.")