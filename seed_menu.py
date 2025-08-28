import sqlite3

DB = "grab.db"

ITEMS = [
    ("Butter Chicken", 159000),
    ("Chicken Biryani", 129000),
    ("Garlic Naan", 25000),
    ("Paneer Tikka", 139000),
    ("Masala Chai", 29000),
]

def seed_menu():
    conn = sqlite3.connect(DB)
    cur = conn.cursor()

    # Use restaurant_id = 1 (Main Restaurant)
    restaurant_id = 1

    # Clear current items (optional)
    cur.execute("DELETE FROM menu_items")

    cur.executemany(
        "INSERT INTO menu_items (name, price, restaurant_id) VALUES (?, ?, ?)",
        [(n, p, restaurant_id) for (n, p) in ITEMS]
    )

    conn.commit()
    conn.close()
    print(f"[seed_menu] Inserted {len(ITEMS)} items into {DB}")

if __name__ == "__main__":
    seed_menu()