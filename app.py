import os, sqlite3, datetime, secrets
from pathlib import Path
from functools import wraps
from flask import (
    Flask, render_template, redirect, url_for, request,
    session, flash, jsonify
)
from werkzeug.security import generate_password_hash, check_password_hash

app = Flask(__name__)
app.secret_key = os.environ.get("SECRET_KEY", "dev-key")  # change in prod

# ---- DB path from env (Render) ----
DB = os.environ.get("DB_PATH", "grab.db")   # e.g. /var/data/grab.db

def db():
    conn = sqlite3.connect(DB)
    conn.row_factory = sqlite3.Row
    return conn

def is_admin():
    return session.get("is_admin") == 1

def get_restaurant_id():
    rid = request.args.get("r", type=int)
    if rid:
        session["rid"] = rid
    return session.get("rid", 1)

# ========== CORS HEADERS (for mobile apps / APIs) ==========
@app.after_request
def add_cors_headers(resp):
    # Simple, permissive CORS for demo/testing
    resp.headers["Access-Control-Allow-Origin"] = "*"
    resp.headers["Access-Control-Allow-Headers"] = "Content-Type, Authorization"
    resp.headers["Access-Control-Allow-Methods"] = "GET, POST, OPTIONS"
    return resp

def row_to_dict(row):
    return {k: row[k] for k in row.keys()} if row else None

# ========== API TOKEN TABLE + AUTH DECORATOR ==========
def ensure_api_tables():
    with db() as conn:
        conn.execute("""
          CREATE TABLE IF NOT EXISTS api_tokens(
            token TEXT PRIMARY KEY,
            user_id INTEGER NOT NULL,
            created_at TEXT NOT NULL
          )
        """)
        conn.commit()
ensure_api_tables()

def require_token(f):
    @wraps(f)
    def wrapper(*args, **kwargs):
        auth = request.headers.get("Authorization","")
        if not auth.startswith("Bearer "):
            return jsonify({"error":"missing_token"}), 401
        token = auth.split(" ",1)[1].strip()
        with db() as conn:
            row = conn.execute("""
                SELECT u.* FROM api_tokens t
                JOIN users u ON u.id=t.user_id
                WHERE t.token=?
            """, (token,)).fetchone()
        if not row:
            return jsonify({"error":"invalid_token"}), 401
        # attach to request context if needed later
        request.current_user = row
        return f(*args, **kwargs)
    return wrapper

# ------------------------------------------------------
@app.route("/healthz")
def healthz(): return "ok", 200

@app.route("/")
def home(): return redirect(url_for("menu"))

# ---------- AUTH ----------
@app.route("/register", methods=["GET","POST"])
def register():
    if request.method == "POST":
        name = request.form.get("name","").strip()
        email = request.form.get("email","").strip().lower()
        password = request.form.get("password","")
        if not name or not email or not password:
            flash("All fields are required","error"); return render_template("register.html")
        try:
            with db() as conn:
                conn.execute(
                    "INSERT INTO users(name,email,password_hash) VALUES (?,?,?)",
                    (name, email, generate_password_hash(password))
                )
                conn.commit()
            flash("Account created. Please login.","success")
            return redirect(url_for("login"))
        except sqlite3.IntegrityError:
            flash("Email already registered.","error")
            return redirect(url_for("login"))
    return render_template("register.html")

@app.route("/login", methods=["GET","POST"])
def login():
    if request.method == "POST":
        email = request.form.get("email","").strip().lower()
        password = request.form.get("password","")
        with db() as conn:
            u = conn.execute("SELECT * FROM users WHERE email=?", (email,)).fetchone()
        if not u or not check_password_hash(u["password_hash"], password):
            flash("Invalid email or password","error"); return render_template("login.html")
        session["uid"] = u["id"]; session["name"] = u["name"]; session["is_admin"] = u["is_admin"]
        flash(f"Welcome, { 'Admin' if u['is_admin']==1 else u['name'] }!","success")
        return redirect(url_for("menu"))
    return render_template("login.html")

@app.route("/logout")
def logout():
    session.clear(); flash("Logged out","info"); return redirect(url_for("login"))

# ---------- MENU ----------
@app.route("/menu")
def menu():
    rid = get_restaurant_id()
    with db() as conn:
        items = conn.execute(
            "SELECT * FROM menu_items WHERE restaurant_id=? ORDER BY id DESC",(rid,)
        ).fetchall()
        restaurants = conn.execute("SELECT id,name FROM restaurants").fetchall()
    return render_template("menu.html", items=items, restaurants=restaurants, rid=rid)

# ---------- ORDER ----------
@app.route("/order", methods=["GET","POST"])
def order():
    rid = get_restaurant_id()
    with db() as conn:
        if request.method == "POST":
            uid = session.get("uid")
            if not uid:
                flash("Please login first.","error"); return redirect(url_for("login"))
            item_id = request.form.get("item_id", type=int)
            qty = request.form.get("qty", type=int)
            item = conn.execute(
                "SELECT * FROM menu_items WHERE id=? AND restaurant_id=?",
                (item_id, rid)
            ).fetchone()
            if not item or not qty or qty <= 0:
                flash("Invalid order.","error"); return redirect(url_for("menu"))
            total = float(item["price"]) * qty
            cur = conn.execute(
                "INSERT INTO orders(user_id,restaurant_id,total,status) VALUES (?,?,?,?)",
                (uid, rid, total, "pending")
            )
            oid = cur.lastrowid
            conn.execute(
                "INSERT INTO order_items(order_id,item_id,qty,price) VALUES (?,?,?,?)",
                (oid, item_id, qty, float(item["price"]))
            )
            conn.commit()
            flash(f"Order #{oid} placed!","success")
            return redirect(url_for("menu"))
        # GET
        item_id = request.values.get("item_id", type=int)
        chosen = None
        if item_id:
            chosen = conn.execute(
                "SELECT * FROM menu_items WHERE id=? AND restaurant_id=?",
                (item_id, rid)
            ).fetchone()
    return render_template("order.html", chosen=chosen)

# ---------- ADMIN ----------
@app.route("/admin")
def admin():
    if not is_admin():
        flash("Admin only.","error"); return redirect(url_for("menu"))
    with db() as conn:
        orders = conn.execute("""
          SELECT o.id,o.total,o.status,o.created_at,o.driver_id,
                 u.name AS customer, r.name AS rest
          FROM orders o
          LEFT JOIN users u ON u.id=o.user_id
          LEFT JOIN restaurants r ON r.id=o.restaurant_id
          ORDER BY o.id DESC
        """).fetchall()
        drivers = conn.execute("SELECT id,name FROM drivers").fetchall()
    return render_template("admin-dashboard.html", orders=orders, drivers=drivers)

@app.route("/admin/order/<int:oid>/status/<status>")
def admin_order_status(oid, status):
    if not is_admin():
        flash("Admin only.","error"); return redirect(url_for("menu"))
    if status not in ("pending","preparing","ready","picked_up","delivered","cancelled"):
        flash("Invalid status.","error"); return redirect(url_for("admin"))
    with db() as conn:
        conn.execute("UPDATE orders SET status=? WHERE id=?", (status, oid)); conn.commit()
    flash(f"Order #{oid} → {status}","success")
    return redirect(url_for("admin"))

@app.route("/admin/assign/<int:oid>/<int:driver_id>")
def admin_assign_driver(oid, driver_id):
    if not is_admin():
        flash("Admin only.","error"); return redirect(url_for("menu"))
    with db() as conn:
        conn.execute("UPDATE orders SET driver_id=?, status='picked_up' WHERE id=?",
                     (driver_id, oid)); conn.commit()
    flash(f"Order #{oid} assigned","success")
    return redirect(url_for("admin"))

# ---------- DRIVER (simple list) ----------
@app.route("/driver")
def driver_home():
    with db() as conn:
        jobs = conn.execute("""
          SELECT o.id,o.total,o.status,o.created_at, r.name AS rest
          FROM orders o
          LEFT JOIN restaurants r ON r.id=o.restaurant_id
          WHERE o.status IN ('ready','picked_up') ORDER BY o.id DESC
        """).fetchall()
    return render_template("driver.html", jobs=jobs)

# ---------- ADMIN: MENU CRUD ----------
def _parse_price(val):
    try:
        return float(str(val).replace(",", "").strip())
    except:
        return None

@app.route("/admin/menu")
def admin_menu():
    if not is_admin():
        flash("Admin only.", "error"); return redirect(url_for("menu"))
    rid = get_restaurant_id()
    with db() as conn:
        restaurants = conn.execute("SELECT id,name FROM restaurants ORDER BY id").fetchall()
        items = conn.execute(
            "SELECT * FROM menu_items WHERE restaurant_id=? ORDER BY id DESC", (rid,)
        ).fetchall()
    return render_template("admin-menu.html", items=items, restaurants=restaurants, rid=rid)

@app.route("/admin/menu/add", methods=["POST"])
def admin_menu_add():
    if not is_admin():
        flash("Admin only.", "error"); return redirect(url_for("menu"))
    name = request.form.get("name","").strip()
    desc = request.form.get("description","").strip()
    price = _parse_price(request.form.get("price",""))
    restaurant_id = request.form.get("restaurant_id", type=int) or get_restaurant_id()
    if not name or price is None or price <= 0:
        flash("Name & valid price required.", "error")
        return redirect(url_for("admin_menu"), 303)
    with db() as conn:
        conn.execute(
            "INSERT INTO menu_items(restaurant_id,name,description,price) VALUES (?,?,?,?)",
            (restaurant_id, name, desc, price)
        ); conn.commit()
    flash("Item added.", "success")
    return redirect(url_for("admin_menu", r=restaurant_id), 303)

@app.route("/admin/menu/edit/<int:item_id>", methods=["GET","POST"])
def admin_menu_edit(item_id):
    if not is_admin():
        flash("Admin only.", "error"); return redirect(url_for("menu"))
    with db() as conn:
        if request.method == "POST":
            name = request.form.get("name","").strip()
            desc = request.form.get("description","").strip()
            price = _parse_price(request.form.get("price",""))
            restaurant_id = request.form.get("restaurant_id", type=int) or get_restaurant_id()
            if not name or price is None or price <= 0:
                flash("Name & valid price required.", "error")
                return redirect(url_for("admin_menu_edit", item_id=item_id), 303)
            conn.execute(
                "UPDATE menu_items SET restaurant_id=?, name=?, description=?, price=? WHERE id=?",
                (restaurant_id, name, desc, price, item_id)
            ); conn.commit()
            flash("Item updated.", "success")
            return redirect(url_for("admin_menu", r=restaurant_id), 303)
        # GET
        item = conn.execute("SELECT * FROM menu_items WHERE id=?", (item_id,)).fetchone()
        restaurants = conn.execute("SELECT id,name FROM restaurants ORDER BY id").fetchall()
    if not item:
        flash("Item not found.", "error"); return redirect(url_for("admin_menu"))
    return render_template("admin-menu-edit.html", item=item, restaurants=restaurants)

@app.route("/admin/menu/delete/<int:item_id>", methods=["POST"])
def admin_menu_delete(item_id):
    if not is_admin():
        flash("Admin only.", "error"); return redirect(url_for("menu"))
    with db() as conn:
        conn.execute("DELETE FROM menu_items WHERE id=?", (item_id,))
        conn.commit()
    flash(f"Item #{item_id} deleted.", "info")
    return redirect(url_for("admin_menu"), 303)

# ========== PUBLIC/SECURE JSON API (for mobile apps) ==========
@app.route("/api/health")
def api_health():
    return jsonify({"status":"ok"}), 200

@app.route("/api/login", methods=["POST"])
def api_login():
    data = request.get_json(silent=True) or {}
    email = (data.get("email","") or "").strip().lower()
    password = data.get("password","") or ""
    if not email or not password:
        return jsonify({"error":"email_password_required"}), 400

    with db() as conn:
        u = conn.execute("SELECT * FROM users WHERE email=?", (email,)).fetchone()
    if not u or not check_password_hash(u["password_hash"], password):
        return jsonify({"error":"invalid_credentials"}), 401

    token = secrets.token_urlsafe(32)
    with db() as conn:
        conn.execute(
            "INSERT INTO api_tokens(token,user_id,created_at) VALUES (?,?,?)",
            (token, u["id"], datetime.datetime.utcnow().isoformat()+"Z")
        )
        conn.commit()

    return jsonify({
        "token": token,
        "user": {"id": u["id"], "name": u["name"], "email": u["email"], "is_admin": u["is_admin"]}
    }), 200

@app.route("/api/menu", methods=["GET"])
def api_menu():
    rid = request.args.get("r", type=int) or get_restaurant_id()
    with db() as conn:
        items = conn.execute("""
          SELECT id, restaurant_id, name, description, price
          FROM menu_items
          WHERE restaurant_id=?
          ORDER BY id DESC
        """, (rid,)).fetchall()
        rest = conn.execute("SELECT id,name FROM restaurants WHERE id=?", (rid,)).fetchone()
    return jsonify({
        "restaurant": row_to_dict(rest) if rest else {"id": rid},
        "items": [row_to_dict(x) for x in items]
    }), 200

@app.route("/api/order", methods=["POST"])
@require_token
def api_place_order():
    data = request.get_json(silent=True) or {}
    item_id = data.get("item_id")
    qty = data.get("qty")
    rid = data.get("restaurant_id") or get_restaurant_id()
    if not item_id or not qty:
        return jsonify({"error":"item_id_and_qty_required"}), 400
    with db() as conn:
        item = conn.execute(
            "SELECT * FROM menu_items WHERE id=? AND restaurant_id=?",
            (item_id, rid)
        ).fetchone()
        if not item:
            return jsonify({"error":"invalid_item"}), 400
        qty = int(qty)
        if qty <= 0:
            return jsonify({"error":"invalid_qty"}), 400
        total = float(item["price"]) * qty
        cur = conn.execute(
            "INSERT INTO orders(user_id,restaurant_id,total,status) VALUES (?,?,?,?)",
            (request.current_user["id"], rid, total, "pending")
        )
        oid = cur.lastrowid
        conn.execute(
            "INSERT INTO order_items(order_id,item_id,qty,price) VALUES (?,?,?,?)",
            (oid, item_id, qty, float(item["price"]))
        )
        conn.commit()
    return jsonify({"ok": True, "order_id": oid, "status":"pending", "total": total}), 201

@app.route("/api/orders", methods=["GET"])
@require_token
def api_my_orders():
    with db() as conn:
        rows = conn.execute("""
          SELECT o.id,o.total,o.status,o.created_at,r.name AS restaurant
          FROM orders o
          LEFT JOIN restaurants r ON r.id=o.restaurant_id
          WHERE o.user_id=? ORDER BY o.id DESC
        """, (request.current_user["id"],)).fetchall()
    return jsonify({"orders":[row_to_dict(r) for r in rows]}), 200

# ------------------------------------------------------
if __name__ == "__main__":
    app.run(debug=True)