import sqlite3

db = sqlite3.connect("grab.db")
db.row_factory = sqlite3.Row

# show all tables
tables = [r[0] for r in db.execute("SELECT name FROM sqlite_master WHERE type='table'")]
print("Tables:", tables)

# show row count in menu_items
count = db.execute("SELECT COUNT(*) FROM menu_items").fetchone()[0]
print("menu_items rows:", count)

# print menu items
for row in db.execute("SELECT id, name, price FROM menu_items"):
    print(dict(row))