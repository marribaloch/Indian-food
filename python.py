import sqlite3

# Database se connection
conn = sqlite3.connect('orders.db')
cursor = conn.cursor()

# Orders fetch karna
cursor.execute("SELECT * FROM orders")
rows = cursor.fetchall()

# Connection close
conn.close()

# Result print karna
if rows:
    for row in rows:
        print(row)
else:
    print("❌ Koi order nahi mila database mein.")