import sqlite3, json, pathlib
db = pathlib.Path(__file__).with_name("grab.db")
con = sqlite3.connect(db)
rows = con.execute("SELECT name FROM sqlite_master WHERE type='table'").fetchall()
print("Tables:", [r[0] for r in rows])
rows = con.execute("PRAGMA table_info(users)").fetchall()
print("users columns:", [r[1] for r in rows])
con.close()