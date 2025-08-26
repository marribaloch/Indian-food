# db_setup.py — final
import os
import sqlite3
from werkzeug.security import generate_password_hash

DB = os.environ.get("DB_PATH", "grab.db")  # e.g. /var/data/grab.db
RESET = os.environ.get("RESET_DB", "0") == "1"

SCHEMA = """
PRAGMA foreign_keys = ON;

CREATE TABLE IF NOT EXISTS users (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  name TEXT NOT NULL,
  email TEXT NOT NULL UNIQUE,
  password_hash TEXT NOT NULL,
  is_admin INTEGER NOT NULL DEFAULT 0,
  created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE IF NOT EXISTS restaurants (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  name TEXT NOT NULL
);

-- NOTE: restaurant_id required by the app
CREATE TABLE IF NOT EXISTS menu_items (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  restaurant_id INTEGER NOT NULL,
  name TEXT NOT NULL,
  description TEXT,
  price REAL NOT NULL,
  FOREIGN KEY (restaurant_id) REFERENCES restaurants(id)
);

CREATE TABLE IF NOT EXISTS orders (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  user_id INTEGER,
  restaurant_id INTEGER NOT NULL,
  total REAL NOT NULL,
  status TEXT NOT NULL DEFAULT 'pending',
  driver_id INTEGER,
  created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
  FOREIGN KEY (user_id) REFERENCES users(id),
  FOREIGN KEY (restaurant_id) REFERENCES restaurants(id)
);

CREATE TABLE IF NOT EXISTS order_items (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  order_id INTEGER NOT NULL,
  item_id INTEGER NOT NULL,
  qty INTEGER NOT NULL,
  price REAL NOT NULL,
  FOREIGN KEY (order_id) REFERENCES orders(id),
  FOREIGN KEY (item_id) REFERENCES menu_items(id)
);

CREATE TABLE IF NOT EXISTS drivers (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  name TEXT NOT NULL
);
"""

SEED_MENU = [
    (1, "Chicken Biryani", "Fragrant basmati, tender chicken", 75000),
    (1, "Butter Chicken",  "Tomato-butter gravy, creamy",      95000),
    (1, "Garlic Naan",     "Tandoor, garlic butter",           25000),
    (2, "Mutton Karahi",   "Spiced mutton, wok tossed",       120000),
    (2, "Dal Tadka",       "Yellow lentils, ghee tempering",   55000),
    (2, "Plain Naan",      "Classic tandoor bread",            20000),
]

def ensure_dir():
    d = os.path.dirname(DB)
    if d:
        os.makedirs(d, exist_ok=True)

def connect():
    conn = sqlite3.connect(DB)
    conn.row_factory = sqlite3.Row
    # Helpful pragmas for SQLite on Render
    try:
        conn.execute("PRAGMA journal_mode=WAL;")
    except sqlite3.DatabaseError:
        pass
    conn.execute("PRAGMA foreign_keys = ON;")
    return conn

def drop_db_file_if_reset():
    if RESET and os.path.exists(DB):
        os.remove(DB)
        print(f"[db_setup] RESET_DB=1 → deleted DB file: {DB}")

def migrate_if_needed(conn):
    """If an old menu_items table exists without restaurant_id, add it."""
    cur = conn.execute("PRAGMA table_info(menu_items);")
    cols = [r["name"] for r in cur.fetchall()]
    if cols and "restaurant_id" not in cols:
        # Old schema → add missing column with a default
        conn.execute("ALTER TABLE menu_items ADD COLUMN restaurant_id INTEGER;")
        # Set a fallback restaurant_id = 1 for existing rows (create restaurant 1 if needed)
        have_r = conn.execute("SELECT COUNT(*) FROM restaurants WHERE id=1").fetchone()[0]
        if have_r == 0:
            conn.execute("INSERT INTO restaurants(id,name) VALUES (1,'Grills & Gravy');")
        conn.execute("UPDATE menu_items SET restaurant_id = COALESCE(restaurant_id, 1);")
        conn.commit()
        print("[db_setup] Migrated: added restaurant_id to menu_items")

def seed(conn):
    cur = conn.cursor()
    # Restaurants
    cur.execute("INSERT INTO restaurants(name) VALUES (?)", ("Grills & Gravy",))
    cur.execute("INSERT INTO restaurants(name) VALUES (?)", ("RK Spice",))
    # Menu items
    cur.executemany(
        "INSERT INTO menu_items(restaurant_id,name,description,price) VALUES (?,?,?,?)",
        SEED_MENU,
    )
    # Admin
    cur.execute(
        "INSERT INTO users(name,email,password_hash,is_admin) VALUES (?,?,?,1)",
        ("Admin", "admin@example.com", generate_password_hash("admin123")),
    )
    # Drivers
    cur.executemany(
        "INSERT INTO drivers(name) VALUES (?)",
        [("Ahmed",), ("Vinh",), ("Sita",)],
    )
    conn.commit()
    print("[db_setup] Seeded demo data. Admin: admin@example.com / admin123")

def ensure_schema_and_seed():
    ensure_dir()
    drop_db_file_if_reset()
    conn = connect()
    try:
        conn.executescript(SCHEMA)
        migrate_if_needed(conn)  # handles old DB without restaurant_id
        # Seed only if restaurants empty (fresh DB)
        r_count = conn.execute("SELECT COUNT(*) FROM restaurants").fetchone()[0]
        if r_count == 0:
            seed(conn)
        else:
            print("[db_setup] Schema ensured. Existing data kept.")
    finally:
        conn.close()
        print(f"[db_setup] Ready: {DB}")

if __name__ == "__main__":
    ensure_schema_and_seed()