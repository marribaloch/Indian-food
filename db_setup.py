import sqlite3

DB = "grab.db"

conn = sqlite3.connect(DB)
cur = conn.cursor()

# --- Create tables (fresh) ---
cur.execute("""
CREATE TABLE IF NOT EXISTS restaurants (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    name TEXT NOT NULL
)
""")

cur.execute("""
CREATE TABLE IF NOT EXISTS customers (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    name TEXT NOT NULL,
    phone TEXT UNIQUE
)
""")

# IMPORTANT: customer_id, total, created_at must exist
cur.execute("""
CREATE TABLE IF NOT EXISTS orders (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    customer_id INTEGER,
    total INTEGER DEFAULT 0,
    created_at TEXT NOT NULL,
    FOREIGN KEY(customer_id) REFERENCES customers(id)
)
""")

# IMPORTANT: restaurant_id NOT NULL so we will seed with restaurant_id=1
cur.execute("""
CREATE TABLE IF NOT EXISTS menu_items (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    name TEXT NOT NULL,
    price INTEGER NOT NULL,
    restaurant_id INTEGER NOT NULL,
    FOREIGN KEY(restaurant_id) REFERENCES restaurants(id)
)
""")

# IMPORTANT: price_each column used by app
cur.execute("""
CREATE TABLE IF NOT EXISTS order_items (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    order_id INTEGER NOT NULL,
    menu_item_id INTEGER NOT NULL,
    qty INTEGER NOT NULL,
    price_each INTEGER NOT NULL,
    FOREIGN KEY(order_id) REFERENCES orders(id),
    FOREIGN KEY(menu_item_id) REFERENCES menu_items(id)
)
""")

# --- Seed base rows (if empty) ---
# restaurant #1
cur.execute("SELECT COUNT(*) FROM restaurants")
if cur.fetchone()[0] == 0:
    cur.execute("INSERT INTO restaurants(name) VALUES (?)", ("Main Restaurant",))

# default customer 'Walk-in'
cur.execute("SELECT COUNT(*) FROM customers WHERE name='Walk-in'")
if cur.fetchone()[0] == 0:
    cur.execute("INSERT INTO customers(name, phone) VALUES ('Walk-in', NULL)")

conn.commit()
conn.close()
print("[db_setup] Schema ensured. Ready:", DB)