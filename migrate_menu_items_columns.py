# migrate_menu_items_columns.py
import sqlite3

DB = "grab.db"
conn = sqlite3.connect(DB)
cur = conn.cursor()

# Dekhein kaun se columns already maujood hain
cur.execute("PRAGMA table_info(menu_items)")
existing = {row[1] for row in cur.fetchall()}

added = []

# Agar image_url missing hai to add karein
if "image_url" not in existing:
    cur.execute("ALTER TABLE menu_items ADD COLUMN image_url TEXT")
    added.append("image_url")

# Agar is_active missing hai to add karein (default 1)
if "is_active" not in existing:
    cur.execute("ALTER TABLE menu_items ADD COLUMN is_active INTEGER DEFAULT 1")
    cur.execute("UPDATE menu_items SET is_active=1 WHERE is_active IS NULL")
    added.append("is_active")

conn.commit()

cur.execute("PRAGMA table_info(menu_items)")
cols_now = [r[1] for r in cur.fetchall()]
print("menu_items columns now:", cols_now)
if added:
    print("Added columns:", added)
else:
    print("No columns were added (already up to date).")

conn.close()
print("Migration completed successfully.")