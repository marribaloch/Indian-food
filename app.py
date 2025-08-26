import os, sqlite3
from flask import Flask, render_template, redirect, url_for, request, session, flash
from werkzeug.security import generate_password_hash, check_password_hash

app = Flask(__name__)
app.secret_key = os.environ.get("SECRET_KEY", "dev-key")  # change in prod
DB = os.environ.get("DB_PATH", "grab.db")  # e.g. /var/data/grab.db on Render

# ---- DB helper ----
def db():
    conn = sqlite3.connect(DB)
    conn.row_factory = sqlite3.Row
    return conn

# ---- handy helpers ----
def is_admin():
    return 1 if session.get("is_admin") == 1 else 0

def get_restaurant_id():
    rid = request.args.get("r", type=int)
    if rid:
        session["rid"] = rid
    return session.get("rid", 1)

# --- VND price formatter (for templates) ---
def vnd(amount):
    try:
        return f"{int(round(float(amount))):,} ₫"
    except Exception:
        return "0 ₫"

# --- Inject globals into ALL templates (SAFE when logged out) ---
@app.context_processor
def inject_globals():
    cu = {"id": session.get("uid"), "name": session.get("name")} if session.get("uid") else None
    return {"is_admin": is_admin(), "current_user": cu, "rid": session.get("rid"), "vnd": vnd}

# ---------- HEALTH ----------
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
            flash("All fields are required","error"); return render_template("register.html"), 400
        try:
            with db() as conn:
                conn.execute(
                    "INSERT INTO users(name,email,password_hash) VALUES (?,?,?)",
                    (name, email, generate_password_hash(password))
                ); conn.commit()
            flash("Account created. Please login.","success")
            return redirect(url_for("login"), 303)
        except sqlite3.IntegrityError:
            flash("Email already registered.","error")
            return redirect(url_for("login"), 303)
    return render_template("register.html")

@app.route("/login", methods=["GET","POST"])
def login():
    if request.method == "POST":
        email = request.form.get("email","").strip().lower()
        password = request.form.get("password","")
        with db() as conn:
            u = conn.execute("SELECT * FROM users WHERE email=?", (email,)).fetchone()
        if not u or not check_password_hash(u["password_hash"], password):
            flash("Invalid email or password","error"); return render_template("login.html"), 401
        session["uid"] = int(u["id"])
        session["name"] = u["name"]
        session["is_admin"] = 1 if int(u["is_admin"]) == 1 else 0
        flash(f"Welcome, {u['name']}!","success")
        return redirect(url_for("menu"), 303)
    return render_template("login.html")

@app.route("/logout")
def logout():
    session.clear(); flash("Logged out","info"); return redirect(url_for("login"))

# ---------- MENU ----------
@app.route("/menu")
def menu():
    rid = get_restaurant_id()
    with db() as conn:
        items = conn.execute("SELECT * FROM menu_items WHERE restaurant_id=? ORDER BY id DESC",(rid,)).fetchall()
        restaurants = conn.execute("SELECT id,name FROM restaurants ORDER BY id").fetchall()
    return render_template("menu.html", items=items, restaurants=restaurants, rid=rid)

# ---------- ORDER ----------
@app.route("/order", methods=["GET","POST"])
def order():
    rid = get_restaurant_id()
    with db() as conn:
        if request.method == "POST":
            uid = session.get("uid")
            if not uid:
                flash("Please login first.","error"); return redirect(url_for("login"), 303)
            item_id = request.form.get("item_id", type=int)
            qty = request.form.get("qty", type=int)
            if not item_id or not qty or qty <= 0:
                flash("Invalid order.","error"); return redirect(url_for("menu"), 303)
            item = conn.execute("SELECT * FROM menu_items WHERE id=? AND restaurant_id=?", (item_id, rid)).fetchone()
            if not item:
                flash("Item not found.","error"); return redirect(url_for("menu"), 303)
            price = float(item["price"]); total = price * qty
            cur = conn.execute("INSERT INTO orders(user_id,restaurant_id,total,status) VALUES (?,?,?,?)",
                               (uid, rid, total, "pending"))
            oid = cur.lastrowid
            conn.execute("INSERT INTO order_items(order_id,item_id,qty,price) VALUES (?,?,?,?)",
                         (oid, item_id, qty, price))
            conn.commit()
            flash(f"Order #{oid} placed!","success"); return redirect(url_for("menu"), 303)
        # GET
        item_id = request.values.get("item_id", type=int); chosen = None
        if item_id:
            chosen = conn.execute("SELECT * FROM menu_items WHERE id=? AND restaurant_id=?", (item_id, rid)).fetchone()
    return render_template("order.html", chosen=chosen)

# ---------- ADMIN DASHBOARD ----------
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
        drivers = conn.execute("SELECT id,name FROM drivers ORDER BY id").fetchall()
    return render_template("admin-dashboard.html", orders=orders, drivers=drivers)

@app.route("/admin/order/<int:oid>/status/<status>")
def admin_order_status(oid, status):
    if not is_admin():
        flash("Admin only.","error"); return redirect(url_for("menu"))
    if status not in ("pending","preparing","ready","picked_up","delivered","cancelled"):
        flash("Invalid status.","error"); return redirect(url_for("admin"))
    with db() as conn:
        conn.execute("UPDATE orders SET status=? WHERE id=?", (status, oid)); conn.commit()
    flash(f"Order #{oid} → {status}","success"); return redirect(url_for("admin"), 303)

@app.route("/admin/assign/<int:oid>/<int:driver_id>")
def admin_assign_driver(oid, driver_id):
    if not is_admin():
        flash("Admin only.","error"); return redirect(url_for("menu"))
    with db() as conn:
        conn.execute("UPDATE orders SET driver_id=?, status='picked_up' WHERE id=?", (driver_id, oid)); conn.commit()
    flash(f"Order #{oid} assigned","success"); return redirect(url_for("admin"), 303)

# ---------- DRIVER ----------
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
    try: return float(str(val).replace(",", "").strip())
    except: return None

@app.route("/admin/menu")
def admin_menu():
    if not is_admin():
        flash("Admin only.","error"); return redirect(url_for("menu"))
    rid = get_restaurant_id()
    with db() as conn:
        restaurants = conn.execute("SELECT id,name FROM restaurants ORDER BY id").fetchall()
        items = conn.execute("SELECT * FROM menu_items WHERE restaurant_id=? ORDER BY id DESC", (rid,)).fetchall()
    return render_template("admin-menu.html", items=items, restaurants=restaurants, rid=rid)

@app.route("/admin/menu/add", methods=["POST"])
def admin_menu_add():
    if not is_admin():
        flash("Admin only.","error"); return redirect(url_for("menu"))
    name = request.form.get("name","").strip()
    desc = request.form.get("description","").strip()
    price = _parse_price(request.form.get("price",""))
    restaurant_id = request.form.get("restaurant_id", type=int) or get_restaurant_id()
    if not name or price is None or price <= 0:
        flash("Name & valid price required.","error"); return redirect(url_for("admin_menu"), 303)
    with db() as conn:
        conn.execute("INSERT INTO menu_items(restaurant_id,name,description,price) VALUES (?,?,?,?)",
                     (restaurant_id, name, desc, price)); conn.commit()
    flash("Item added.","success"); return redirect(url_for("admin_menu", r=restaurant_id), 303)

@app.route("/admin/menu/edit/<int:item_id>", methods=["GET","POST"])
def admin_menu_edit(item_id):
    if not is_admin():
        flash("Admin only.","error"); return redirect(url_for("menu"))
    with db() as conn:
        if request.method == "POST":
            name = request.form.get("name","").strip()
            desc = request.form.get("description","").strip()
            price = _parse_price(request.form.get("price",""))
            restaurant_id = request.form.get("restaurant_id", type=int) or get_restaurant_id()
            if not name or price is None or price <= 0:
                flash("Name & valid price required.","error"); return redirect(url_for("admin_menu_edit", item_id=item_id), 303)
            conn.execute("UPDATE menu_items SET restaurant_id=?, name=?, description=?, price=? WHERE id=?",
                         (restaurant_id, name, desc, price, item_id)); conn.commit()
            flash("Item updated.","success"); return redirect(url_for("admin_menu", r=restaurant_id), 303)
        item = conn.execute("SELECT * FROM menu_items WHERE id=?", (item_id,)).fetchone()
        restaurants = conn.execute("SELECT id,name FROM restaurants ORDER BY id").fetchall()
    if not item:
        flash("Item not found.","error"); return redirect(url_for("admin_menu"))
    return render_template("admin-menu-edit.html", item=item, restaurants=restaurants)

@app.route("/admin/menu/delete/<int:item_id>", methods=["POST"])
def admin_menu_delete(item_id):
    if not is_admin():
        flash("Admin only.","error"); return redirect(url_for("menu"))
    with db() as conn:
        conn.execute("DELETE FROM menu_items WHERE id=?", (item_id,)); conn.commit()
    flash(f"Item #{item_id} deleted.","info"); return redirect(url_for("admin_menu"), 303)

# ---------- MAIN ----------
if __name__ == "__main__":
    # Local dev: python app.py
    # Production: python db_setup.py && gunicorn app:app -w 2 -b 0.0.0.0:$PORT
    app.run(debug=True)