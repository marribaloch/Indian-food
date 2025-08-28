from flask import Flask, request, jsonify, render_template, redirect, url_for
from flask_cors import CORS
import sqlite3, datetime
from werkzeug.security import check_password_hash

app = Flask(__name__)
CORS(app)  # Allow calls from Expo/React Native

def get_db():
    con = sqlite3.connect("app.db")
    con.row_factory = sqlite3.Row
    return con

@app.route("/")
def home():
    return redirect(url_for("login_page"))

@app.route("/login")
def login_page():
    # If you want to serve an HTML page later, switch this to render_template("login.html")
    return ("OK", 200)

# --- MENU (read-only) ---
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

# --- ORDER (page to build an order) ---
@app.route("/order")
def order_page():
    con = get_db()
    try:
        cur = con.cursor()
        cur.execute("SELECT id, name, price FROM menu_items ORDER BY id ASC")
        items = [{"id": r["id"], "name": r["name"], "price": r["price"]} for r in cur.fetchall()]
    finally:
        con.close()
    return render_template("order.html", items=items)

# --- API: create order ---
@app.route("/api/orders", methods=["POST"])
def api_create_order():
    data = request.get_json(silent=True) or {}
    items = data.get("items") or []  # [{menu_item_id, qty}]
    customer_id = data.get("customer_id")  # optional

    if not items:
        return jsonify({"message": "No items provided"}), 400

    con = get_db()
    try:
        cur = con.cursor()

        # Ensure minimal tables exist
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

        # Default customer = Walk-in
        if not customer_id:
            cur.execute("SELECT id FROM customers WHERE name = 'Walk-in'")
            row = cur.fetchone()
            if row: customer_id = row["id"]
            else:
                cur.execute("INSERT INTO customers(name, phone) VALUES(?,?)", ("Walk-in", None))
                customer_id = cur.lastrowid

        # Create order shell
        now = datetime.datetime.now().isoformat(timespec="seconds")
        cur.execute("INSERT INTO orders(customer_id, total, created_at) VALUES(?,?,?)",
                    (customer_id, 0, now))
        order_id = cur.lastrowid

        # Insert order items with price snapshots
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

        # Update total
        cur.execute("UPDATE orders SET total = ? WHERE id = ?", (total, order_id))
        con.commit()

        return jsonify({"ok": True, "order_id": order_id, "total": total})
    except Exception as e:
        con.rollback()
        return jsonify({"ok": False, "error": str(e)}), 500
    finally:
        con.close()

# --- API: health & login (unchanged) ---
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

    # If you currently store plain-text passwords, temporarily compare directly:
    # if row["password_hash"] != password: return jsonify({"message": "Invalid credentials"}), 401

    if not check_password_hash(row["password_hash"], password):
        return jsonify({"message": "Invalid credentials"}), 401

    token = f"tok_{row['id']}"
    return jsonify({
        "token": token,
        "user": {"id": row["id"], "name": row["name"], "email": row["email"], "role": row["role"]}
    })

if __name__ == "__main__":
    app.run(host="0.0.0.0", port=5000, debug=True)