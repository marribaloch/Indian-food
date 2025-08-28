from flask import Flask, request, jsonify, render_template, redirect, url_for
from flask_cors import CORS
import sqlite3, datetime
from werkzeug.security import check_password_hash

# ----- Config -----
DB_FILE = "grab.db"   # Yahi file aapke project me maujood hai

app = Flask(__name__)
CORS(app)

def get_db():
    con = sqlite3.connect(DB_FILE)
    con.row_factory = sqlite3.Row
    return con

# ------------------ Pages ------------------

@app.route("/")
def home():
    return redirect(url_for("menu"))

@app.route("/menu")
def menu():
    con = get_db()
    try:
        cur = con.cursor()
        # safety: table exists
        cur.execute("""
            CREATE TABLE IF NOT EXISTS menu_items (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                name TEXT NOT NULL,
                price INTEGER NOT NULL
            )
        """)
        cur.execute("SELECT id, name, price FROM menu_items ORDER BY id ASC")
        items = [{"id": r["id"], "name": r["name"], "price": r["price"]} for r in cur.fetchall()]
    finally:
        con.close()
    return render_template("menu.html", items=items)

@app.route("/order")
def order_page():
    """Order page ko DB se items de kar render karein (dropdown fill hoga)."""
    con = get_db()
    try:
        cur = con.cursor()
        cur.execute("""
            CREATE TABLE IF NOT EXISTS menu_items (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                name TEXT NOT NULL,
                price INTEGER NOT NULL
            )
        """)
        cur.execute("SELECT id, name, price FROM menu_items ORDER BY id ASC")
        items = [{"id": r["id"], "name": r["name"], "price": r["price"]} for r in cur.fetchall()]
    finally:
        con.close()
    return render_template("order.html", items=items)

@app.route("/login")
def login_page():
    return ("OK", 200)

# ------------------ APIs ------------------

@app.route("/api/items")
def api_items():
    con = get_db()
    try:
        cur = con.cursor()
        cur.execute("SELECT id, name, price FROM menu_items ORDER BY id")
        rows = cur.fetchall()
        return jsonify([{"id": r["id"], "name": r["name"], "price": r["price"]} for r in rows])
    finally:
        con.close()

@app.route("/api/orders", methods=["POST"])
def api_create_order():
    """Order create + customer name/phone support."""
    data = request.get_json(silent=True) or {}
    items = data.get("items") or []         # [{menu_item_id, qty}]
    customer_name = (data.get("customer_name") or "").strip()
    phone = (data.get("phone") or "").strip()
    customer_id = data.get("customer_id")

    if not items:
        return jsonify({"message": "No items provided"}), 400

    con = get_db()
    try:
        cur = con.cursor()
        # ensure schema
        cur.execute("""CREATE TABLE IF NOT EXISTS customers (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            name TEXT NOT NULL,
            phone TEXT UNIQUE
        )""")
        cur.execute("""CREATE TABLE IF NOT EXISTS orders (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            customer_id INTEGER,
            total INTEGER DEFAULT 0,
            created_at TEXT NOT NULL,
            FOREIGN KEY(customer_id) REFERENCES customers(id)
        )""")
        cur.execute("""CREATE TABLE IF NOT EXISTS order_items (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            order_id INTEGER NOT NULL,
            menu_item_id INTEGER NOT NULL,
            qty INTEGER NOT NULL,
            price_each INTEGER NOT NULL,
            FOREIGN KEY(order_id) REFERENCES orders(id),
            FOREIGN KEY(menu_item_id) REFERENCES menu_items(id)
        )""")
        cur.execute("""CREATE TABLE IF NOT EXISTS menu_items (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            name TEXT NOT NULL,
            price INTEGER NOT NULL
        )""")

        # resolve customer
        if not customer_id:
            if phone:
                cur.execute("SELECT id FROM customers WHERE phone = ?", (phone,))
                r = cur.fetchone()
                if r:
                    customer_id = r["id"]
                    if customer_name:
                        cur.execute("UPDATE customers SET name=? WHERE id=?", (customer_name, customer_id))
                else:
                    cur.execute("INSERT INTO customers(name, phone) VALUES(?,?)",
                                (customer_name or "Walk-in", phone))
                    customer_id = cur.lastrowid
            elif customer_name:
                cur.execute("SELECT id FROM customers WHERE name=?", (customer_name,))
                r = cur.fetchone()
                if r:
                    customer_id = r["id"]
                else:
                    cur.execute("INSERT INTO customers(name, phone) VALUES(?,?)", (customer_name, None))
                    customer_id = cur.lastrowid
            else:
                cur.execute("SELECT id FROM customers WHERE name='Walk-in'")
                r = cur.fetchone()
                if r:
                    customer_id = r["id"]
                else:
                    cur.execute("INSERT INTO customers(name, phone) VALUES('Walk-in', NULL)")
                    customer_id = cur.lastrowid

        # create order
        now = datetime.datetime.now().isoformat(timespec="seconds")
        cur.execute("INSERT INTO orders(customer_id, total, created_at) VALUES(?,?,?)",
                    (customer_id, 0, now))
        order_id = cur.lastrowid

        # items + total
        total = 0
        for it in items:
            mid = int(it.get("menu_item_id"))
            qty = int(it.get("qty") or 0)
            if qty <= 0:
                continue
            cur.execute("SELECT price FROM menu_items WHERE id=?", (mid,))
            row = cur.fetchone()
            if not row:
                continue
            price_each = int(row["price"])
            cur.execute("""INSERT INTO order_items(order_id, menu_item_id, qty, price_each)
                           VALUES(?,?,?,?)""", (order_id, mid, qty, price_each))
            total += qty * price_each

        cur.execute("UPDATE orders SET total=? WHERE id=?", (total, order_id))
        con.commit()
        return jsonify({"ok": True, "order_id": order_id, "total": total})
    except Exception as e:
        con.rollback()
        return jsonify({"ok": False, "error": str(e)}), 500
    finally:
        con.close()

@app.route("/admin")
def admin_view():
    con = get_db()
    try:
        cur = con.cursor()
        # ensure schema
        cur.execute("""CREATE TABLE IF NOT EXISTS customers (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            name TEXT NOT NULL,
            phone TEXT UNIQUE
        )""")
        cur.execute("""CREATE TABLE IF NOT EXISTS orders (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            customer_id INTEGER,
            total INTEGER DEFAULT 0,
            created_at TEXT NOT NULL,
            FOREIGN KEY(customer_id) REFERENCES customers(id)
        )""")
        cur.execute("""CREATE TABLE IF NOT EXISTS order_items (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            order_id INTEGER NOT NULL,
            menu_item_id INTEGER NOT NULL,
            qty INTEGER NOT NULL,
            price_each INTEGER NOT NULL,
            FOREIGN KEY(order_id) REFERENCES orders(id),
            FOREIGN KEY(menu_item_id) REFERENCES menu_items(id)
        )""")
        cur.execute("""CREATE TABLE IF NOT EXISTS menu_items (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            name TEXT NOT NULL,
            price INTEGER NOT NULL
        )""")

        cur.execute("""
          SELECT
            o.id AS order_id,
            COALESCE(c.name, 'Walk-in') AS customer_name,
            c.phone AS phone,
            COALESCE(o.total, 0) AS total_vnd,
            o.created_at AS created_at,
            GROUP_CONCAT(mi.name || ' x' || oi.qty, ', ') AS items_summary
          FROM orders o
          LEFT JOIN customers   c  ON c.id = o.customer_id
          LEFT JOIN order_items oi ON oi.order_id = o.id
          LEFT JOIN menu_items  mi ON mi.id = oi.menu_item_id
          GROUP BY o.id
          ORDER BY o.id DESC
        """)
        rows = cur.fetchall()
        orders = [{
            "order_id": r["order_id"],
            "customer_name": r["customer_name"],
            "phone": r["phone"] or "",
            "total_vnd": r["total_vnd"] or 0,
            "created_at": r["created_at"],
            "items_summary": r["items_summary"] or ""
        } for r in rows]
    finally:
        con.close()
    return render_template("admin.html", orders=orders)
# --- NEW: Customers list page (/customers) ---
@app.route("/customers")
def customers_view():
    con = get_db()
    cur = con.cursor()
    # Customers + unke orders ka summary (count + last order time)
    cur.execute("""
        SELECT
            c.id,
            COALESCE(NULLIF(TRIM(c.name), ''), 'Walk-in') AS name,
            c.phone,
            COUNT(o.id)            AS total_orders,
            MAX(o.created_at)      AS last_order_at
        FROM customers c
        LEFT JOIN orders o ON o.customer_id = c.id
        GROUP BY c.id
        ORDER BY total_orders DESC, name ASC
    """)
    rows = [dict(r) for r in cur.fetchall()]
    con.close()
    return render_template("customers.html", rows=rows)
# ----- Health -----
@app.route("/api/healthz")
def healthz():
    con = get_db()
    con.execute("SELECT 1")
    con.close()
    return jsonify({"ok": True})

if __name__ == "__main__":
    app.run(host="0.0.0.0", port=5000, debug=True)