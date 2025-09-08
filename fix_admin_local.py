import os, sqlite3
try:
    from dotenv import load_dotenv
    load_dotenv()
except Exception:
    pass

DB = "app.db"

# Target email: .env se lo; warna neeche apna Gmail daal do
TARGET_EMAIL = os.getenv("ADMIN_EMAIL") or os.getenv("EMAIL_USER") or "alimarribaloch@gmail.com"

conn = sqlite3.connect(DB)
conn.row_factory = sqlite3.Row
c = conn.cursor()

def rowcount(sql, args=()):
    c.execute(sql, args)
    return c.fetchone()[0]

print("Using target email:", TARGET_EMAIL)

# 1) admin@local user?
c.execute("SELECT * FROM users WHERE email='admin@local';")
old = c.fetchone()

if not old:
    print("✅ No user with email admin@local found. Nothing to do.")
    conn.close()
    raise SystemExit

old_id = old["id"]

# 2) Kya TARGET_EMAIL wala user already exists?
c.execute("SELECT * FROM users WHERE email=?;", (TARGET_EMAIL,))
target = c.fetchone()

if target:
    target_id = target["id"]
    print(f"↪ Found existing target user id={target_id} ({TARGET_EMAIL}). Merging orders...")

    # 2a) Orders ko merge karo (old_id -> target_id)
    c.execute("UPDATE orders SET user_id=? WHERE user_id=?;", (target_id, old_id))
    # 2b) Purana user delete
    c.execute("DELETE FROM users WHERE id=?;", (old_id,))
    conn.commit()
    print("✅ Merged orders and deleted admin@local user.")
else:
    # 3) Bas user ki email replace kar do
    print(f"↪ Updating admin@local -> {TARGET_EMAIL}")
    c.execute("UPDATE users SET email=? WHERE id=?;", (TARGET_EMAIL, old_id))
    conn.commit()
    print("✅ Updated user email to your Gmail.")

# Sanity check
cnt_admin_local = rowcount("SELECT COUNT(*) FROM users WHERE email='admin@local';")
cnt_orders_bad = rowcount("""
    SELECT COUNT(*) FROM orders
    WHERE user_id IN (SELECT id FROM users WHERE email='admin@local')
""")
print(f"Leftover users admin@local: {cnt_admin_local}, orders linked to admin@local: {cnt_orders_bad}")

conn.close()
print("🎉 Done. You can restart the server now.")