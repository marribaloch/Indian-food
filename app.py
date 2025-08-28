from flask import Flask, request, jsonify, render_template, redirect, url_for
from flask_cors import CORS
import sqlite3, datetime
from werkzeug.security import check_password_hash

app = Flask(__name__)
CORS(app)

def get_db():
    con = sqlite3.connect("app.db")
    con.row_factory = sqlite3.Row
    return con

@app.route("/")
def home():
    return redirect(url_for("login_page"))

@app.route("/login")
def login_page():
    return ("OK", 200)

# ----- SEED & DEBUG -----
@app.route("/seed")
def seed_menu():
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
        cur.execute("SELECT COUNT(*) AS c FROM menu_items")
        c = cur.fetchone()["c"]
        if c == 0:
            cur.executemany("INSERT INTO menu_items(name, price) VALUES(?,?)", [
                ("Butter Chicken", 159000),
                ("Chicken Biryani", 129000),
                ("Garlic Naan", 25000),
                ("Paneer Tikka", 139000),
                ("Masala Chai", 29000),
            ])
            con.commit()
            return jsonify({"ok": True, "seeded": 5})
        else:
            return jsonify({"ok": True, "message": "items already exist", "count": c})
    finally:
        con.close()

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

# ----- MENU (read-only) -----
@app.route("/menu")
def menu():
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
        rows = cur.fetchall()
        items = [{"id": r["id"], "name": r["name"], "price": r["price"]} for r in rows]
    finally:
        con.close()
    return render_template("menu.html", items=items)

# ----- ORDER (page) -----
@app.route("/order")
def order_page():
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

# ----- API: create order -----
@app.route("/api/orders", methods=["POST"])
def api_create_order():
    data = request.get_json(silent=True) or {}
    items = data.get("items") or []
    customer_id = data.get("customer_id")

    if not items:
        return jsonify({"message": "No items provided"}), 400

    con = get_db()
    try:
        cur = con.cursor()
        # Ensure tables exist
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

        # Default customer = Walk-in
        if not customer_id:
            cur.execute("SELECT id FROM customers WHERE name = 'Walk-in'")
            r = cur.fetchone()
            customer_id = r["id"] if r else None
            if not customer_id:
                cur.execute("INSERT INTO customers(name, phone) VALUES(?,?)", ("Walk-in", None))
                customer_id = cur.lastrowid

        # Create order
        now = datetime.datetime.now().isoformat(timespec="seconds")
        cur.execute("INSERT INTO orders(customer_id, total, created_at) VALUES(?,?,?)",
                    (customer_id, 0, now))
        order_id = cur.lastrowid

        total = 0
        for it in items:
            mid = int(it.get("menu_item_id"))
            qty = int(it.get("qty") or 0)
            if qty <= 0: 
                continue
            cur.execute("SELECT price FROM menu_items WHERE id = ?", (mid,))
            row = cur.fetchone()
            if not row:
                continue
            price_each = int(row["price"])
            cur.execute("""INSERT INTO order_items(order_id, menu_item_id, qty, price_each)
                           VALUES(?,?,?,?)""", (order_id, mid, qty, price_each))
            total += qty * price_each

        cur.execute("UPDATE orders SET total = ? WHERE id = ?", (total, order_id))
        con.commit()
        return jsonify({"ok": True, "order_id": order_id, "total": total})
    except Exception as e:
        con.rollback()
        return jsonify({"ok": False, "error": str(e)}), 500
    finally:
        con.close()

# ----- ADMIN: orders list (with total) -----
@app.route("/admin")
def admin_view():
    con = get_db()
    try:
        cur = con.cursor()
        # Ensure ALL tables exist
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

        # Orders summary (includes total)
        cur.execute("""
            SELECT
              o.id            AS order_id,
              COALESCE(c.name, 'Walk-in') AS customer_name,
              COALESCE(o.total, 0) AS total_vnd,
              o.created_at    AS created_at,
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
            "total_vnd": r["total_vnd"] or 0,
            "created_at": r["created_at"],
            "items_summary": r["items_summary"] or ""
        } for r in rows]
    finally:
        con.close()
    return render_template("admin.html", orders=orders)

# ----- Health & Login -----
@app.route("/api/healthz")
def healthz():
    con = get_db()
    con.execute("SELECT 1")
    con.close()
    return jsonify({"ok": True})

@app.route("/api/login", methods=["POST"])
def api_login():
    data = request.get_json(silent=True) or {}
    email = (data.get("email") or "").strip().lower()
    password = data.get("password") or ""

    if not email or not password:
        return jsonify({"message": "Email and password required"}), 400

    con = get_db()
    cur = con.cursor()
    cur.execute("SELECT id, name, email, password_hash, role FROM users WHERE email = ?", (email,))
    row = cur.fetchone()
    con.close()

    if not row:
        return jsonify({"message": "Invalid credentials"}), 401

    if not check_password_hash(row["password_hash"], password):
        return jsonify({"message": "Invalid credentials"}), 401

    token = f"tok_{row['id']}"
    return jsonify({
        "token": token,
        "user": {"id": row["id"], "name": row["name"], "email": row["email"], "role": row["role"]}
    })

if __name__ == "__main__":
    app.run(host="0.0.0.0", port=5000, debug=True)