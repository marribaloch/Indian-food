# seed_menu.py
import sqlite3

DB_FILE = "grab.db"

items = [
    ("Butter Chicken", 120000, "https://i.imgur.com/6w7Q2GQ.jpeg"),
    ("Dal Tadka", 85000, "https://i.imgur.com/1iJg4fT.jpeg"),
    ("Chicken Biryani", 130000, "https://i.imgur.com/0F2s3xP.jpeg"),
    ("Garlic Naan", 30000,  "https://i.imgur.com/jbO3CwY.jpeg"),
]

def seed():
    conn = sqlite3.connect(DB_FILE)
    cur = conn.cursor()
    for name, price, img in items:
        cur.execute("INSERT INTO menu_items (name, price, image_url, is_active) VALUES (?,?,?,1)", (name, price, img))
    conn.commit()
    conn.close()
    print("Menu seeded.")

if __name__ == "__main__":
    seed()