# db_setup.py
import sqlite3, os
from werkzeug.security import generate_password_hash

DB = "grab.db"

schema = """
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

def seed(conn):
    cur = conn.cursor()
    # restaurants
    cur.execute("INSERT INTO restaurants(name) VALUES (?)", ("Grills & Gravy",))
    cur.execute("INSERT INTO restaurants(name) VALUES (?)", ("RK Spice",))
    # menu for both
    cur.executemany(
        "INSERT INTO menu_items(restaurant_id,name,description,price) VALUES (?,?,?,?)",
        [
            (1,"Chicken Biryani","Fragrant basmati, tender chicken", 75_000),
            (1,"Butter Chicken","Tomato-butter gravy, creamy", 95_000),
            (1,"Garlic Naan","Tandoor, garlic butter", 25_000),
            (2,"Mutton Karahi","Spiced mutton, wok tossed", 120_000),
            (2,"Dal Tadka","Yellow lentils, ghee tempering", 55_000),
            (2,"Plain Naan","Classic tandoor bread", 20_000),
        ],
    )
    # admin user
    cur.execute(
        "INSERT INTO users(name,email,password_hash,is_admin) VALUES (?,?,?,1)",
        ("Admin", "admin@example.com", generate_password_hash("admin123")),
    )
    # sample drivers
    cur.executemany(
        "INSERT INTO drivers(name) VALUES (?)",
        [("Ahmed",), ("Vinh",), ("Sita",)],
    )
    conn.commit()

if __name__ == "__main__":
    conn = sqlite3.connect(DB)
    conn.executescript(schema)
    # only seed if fresh
    have_any = conn.execute("SELECT COUNT(*) FROM restaurants").fetchone()[0]
    if have_any == 0:
        seed(conn)
        print("DB created & seeded. Admin: admin@example.com / admin123")
    else:
        print("Schema ensured. Data already present.")
    conn.close()