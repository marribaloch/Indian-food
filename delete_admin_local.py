import sqlite3

DB_PATH = "app.db"

try:
    conn = sqlite3.connect(DB_PATH)
    cur = conn.cursor()

    # Delete the dummy admin@local user
    cur.execute("DELETE FROM users WHERE email='admin@local';")
    conn.commit()

    print("✅ admin@local user deleted (if it existed).")

except Exception as e:
    print("❌ Error:", e)

finally:
    conn.close()