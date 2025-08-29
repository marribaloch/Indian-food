from flask import Flask, render_template, redirect, url_for, request, flash
import sqlite3, os

app = Flask(__name__)
app.secret_key = "change-this"  # flash messages ke liye

# ---- Jinja filter: VND price formatting (59,000 VND)
def format_vnd(value):
    try:
        n = float(value)
    except:
        return value
    return f"{int(round(n)):,} VND"   # 59000 -> 59,000 VND

app.jinja_env.filters["vnd"] = format_vnd

# ----- DB PICK: prefer grab.db, else app.db
DB_FILE = "grab.db" if os.path.exists("grab.db") else "app.db"

# ----- DB helpers
def get_db():
    conn = sqlite3.connect(DB_FILE)
    conn.row_factory = sqlite3.Row
    return conn

def init_db():
    with get_db() as con:
        con.execute("""
            CREATE TABLE IF NOT EXISTS menu_items (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                name TEXT NOT NULL,
                price REAL NOT NULL,
                category TEXT DEFAULT '',
                available INTEGER DEFAULT 1
            )
        """)

init_db()

# ===== Public routes
@app.route("/")
def home():
    return redirect(url_for("login"))

@app.route("/login")
def login():
    return render_template("login.html")

@app.route("/register")
def register():
    return render_template("register.html")

@app.route("/menu")
def menu():
    with get_db() as con:
        rows = con.execute(
            "SELECT * FROM menu_items WHERE available=1 ORDER BY category, name"
        ).fetchall()
    return render_template("menu.html", items=rows)

@app.route("/order")
def order():
    return render_template("order.html")

@app.route("/admin")
def admin():
    # simple landing – redirect to admin_menu
    return redirect(url_for("admin_menu"))

@app.route("/healthz")
def healthz():
    return "OK", 200

# ===== ADMIN: Menu CRUD
@app.route("/admin_menu")
def admin_menu():
    with get_db() as con:
        rows = con.execute(
            "SELECT * FROM menu_items ORDER BY category, name"
        ).fetchall()
    return render_template("admin_menu.html", items=rows)

@app.route("/admin_menu/add", methods=["POST"])
def admin_menu_add():
    name = request.form.get("name","").strip()
    price = request.form.get("price","").strip()
    category = request.form.get("category","").strip()
    if not name or not price:
        flash("Name and price are required.")
        return redirect(url_for("admin_menu"))
    try:
        price_val = float(price)
    except:
        flash("Price must be a number.")
        return redirect(url_for("admin_menu"))
    with get_db() as con:
        con.execute(
            "INSERT INTO menu_items (name, price, category, available) VALUES (?,?,?,1)",
            (name, price_val, category)
        )
    flash("Item added.")
    return redirect(url_for("admin_menu"))

@app.route("/admin_menu/edit/<int:item_id>", methods=["GET","POST"])
def admin_menu_edit(item_id):
    if request.method == "POST":
        name = request.form.get("name","").strip()
        price = request.form.get("price","").strip()
        category = request.form.get("category","").strip()
        try:
            price_val = float(price)
        except:
            flash("Price must be a number.")
            return redirect(url_for("admin_menu_edit", item_id=item_id))
        with get_db() as con:
            con.execute(
                "UPDATE menu_items SET name=?, price=?, category=? WHERE id=?",
                (name, price_val, category, item_id)
            )
        flash("Item updated.")
        return redirect(url_for("admin_menu"))
    else:
        with get_db() as con:
            row = con.execute(
                "SELECT * FROM menu_items WHERE id=?", (item_id,)
            ).fetchone()
        if not row:
            flash("Item not found.")
            return redirect(url_for("admin_menu"))
        return render_template("edit_item.html", item=row)

@app.route("/admin_menu/delete/<int:item_id>", methods=["POST"])
def admin_menu_delete(item_id):
    with get_db() as con:
        con.execute("DELETE FROM menu_items WHERE id=?", (item_id,))
    flash("Item deleted.")
    return redirect(url_for("admin_menu"))

@app.route("/admin_menu/toggle/<int:item_id>", methods=["POST"])
def admin_menu_toggle(item_id):
    with get_db() as con:
        row = con.execute(
            "SELECT available FROM menu_items WHERE id=?", (item_id,)