import sqlite3
DB="grab.db"
con=sqlite3.connect(DB); con.row_factory=sqlite3.Row; cur=con.cursor()

cur.execute("SELECT name FROM sqlite_master WHERE type='table' ORDER BY name")
print("Tables:", [r["name"] for r in cur.fetchall()])

cur.execute("PRAGMA table_info(orders)")
print("orders cols:", [r["name"] for r in cur.fetchall()])

cur.execute("SELECT id,name,price,restaurant_id FROM menu_items ORDER BY id")
print("menu_items:", [tuple(r) for r in cur.fetchall()])

con.close()