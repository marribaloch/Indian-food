import sqlite3

def create_tables():
    conn = sqlite3.connect('app.db')
    c = conn.cursor()

    # Create users table with role column
    c.execute('''
        CREATE TABLE IF NOT EXISTS users (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            username TEXT UNIQUE NOT NULL,
            password TEXT NOT NULL,
            role TEXT DEFAULT 'customer'
        )
    ''')

    # Create orders table (optional - included for completeness)
    c.execute('''
        CREATE TABLE IF NOT EXISTS orders (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            name TEXT NOT NULL,
            food TEXT NOT NULL
        )
    ''')

    conn.commit()
    conn.close()

# Run it once to create tables
create_tables()