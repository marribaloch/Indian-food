import sqlite3
from werkzeug.security import generate_password_hash

DB = "app.db"

def seed():
    con = sqlite3.connect(DB)
    cur = con.cursor()

    # Users table create if not exists
    cur.execute("""
        CREATE TABLE IF NOT EXISTS users (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            email TEXT UNIQUE NOT NULL,
            password_hash TEXT NOT NULL,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
    """)

    # Menu table create if not exists
    cur.execute("""
        CREATE TABLE IF NOT EXISTS menu_items (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            name TEXT NOT NULL,
            price REAL NOT NULL DEFAULT 0,
            description TEXT DEFAULT '',
            photo_url TEXT DEFAULT '',
            category TEXT DEFAULT '',
            available INTEGER NOT NULL DEFAULT 1,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
    """)

    # Purane records clear karo (duplicate avoid)
    cur.execute("DELETE FROM users")
    cur.execute("DELETE FROM menu_items")

    # Users insert
    users = [
        ("admin@test.com", generate_password_hash("1234")),
        ("user@test.com", generate_password_hash("1234")),
    ]
    cur.executemany("INSERT INTO users(email, password_hash) VALUES (?, ?)", users)

    # Menu items insert
    items = [
        ("Chicken Biryani", 8.5, "Delicious spicy biryani"),
        ("Paneer Butter Masala", 7.0, "Paneer in creamy tomato gravy")
    ]
    cur.executemany("INSERT INTO menu_items(name, price, description) VALUES (?, ?, ?)", items)

    con.commit()
    con.close()
    print("✅ Database seeded successfully! Admin & User created + sample menu added.")

if __name__ == "__main__":
    seed()