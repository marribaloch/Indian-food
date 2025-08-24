import sqlite3

conn = sqlite3.connect('grab.db')
cursor = conn.cursor()

cursor.execute('''
CREATE TABLE IF NOT EXISTS orders (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    customer_name TEXT NOT NULL,
    item TEXT NOT NULL,
    quantity INTEGER NOT NULL
)
''')

conn.commit()
conn.close()
print("✅ Database created successfully.")
cursor.execute('''
CREATE TABLE IF NOT EXISTS users (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    username TEXT NOT NULL UNIQUE,
    password TEXT NOT NULL
)
''')

# Default admin user
cursor.execute('''
INSERT OR IGNORE INTO users (username, password)
VALUES (?, ?)
''', ('admin', 'admin123'))