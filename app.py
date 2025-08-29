# app.py — Indian Food App (clean, no duplicates)
import os
import sqlite3
from contextlib import contextmanager
from flask import (
    Flask, render_template, redirect, url_for,
    request, abort, flash
)

DB = os.environ.get("DB_PATH", "app.db")
SECRET_KEY = os.environ.get("SECRET_KEY", "dev-secret")

app = Flask(__name__)
app.secret_key = SECRET_KEY

# ---------- Jinja filter ----------
def format_vnd(value):
    try:
        n = float(value)
    except Exception:
        return value
    return f"{int(round(n)):,} VND"
app.jinja_env.filters["vnd"] = format_vnd

# ---------- DB helpers ----------
@contextmanager
def get_db():
    con = sqlite3.connect(DB)
    con.row_factory = sqlite3.Row
    try:
        con.execute("PRAGMA foreign_keys = ON;")
        yield con
    finally:
        con.close()

def table_has_column(con, table, col) -> bool:
    return any(r["name"] == col for r in con.execute(f"PRAGMA table_info({table});"))

def ensure_columns():
    with get_db() as con:
        con.execute("""
        CREATE TABLE IF NOT EXISTS menu_items(
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            name TEXT NOT NULL,
            price REAL NOT NULL DEFAULT 0,
            description TEXT DEFAULT '',
            photo_url TEXT DEFAULT '',
            category TEXT DEFAULT '',
            available INTEGER NOT NULL DEFAULT 1,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        );
        """)
        con.commit()
        for col, ddl in [
            ("description", "TEXT DEFAULT ''"),
            ("photo_url", "TEXT DEFAULT ''"),
            ("category", "TEXT DEFAULT ''"),
            ("available", "INTEGER NOT NULL DEFAULT 1"),
        ]:
            if not table_has_column(con, "menu_items", col):
                con.execute(f"ALTER TABLE menu_items ADD COLUMN {col} {ddl};")
        con.commit()

def to_float(v, default=0.0):
    try:
        return float(v)
    except Exception:
        return default

# ---------- Basic routes ----------
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
        if table_has_column(con, "menu_items", "available"):
            items = con.execute(
                "SELECT * FROM menu_items WHERE available=1 ORDER BY id DESC"
            ).fetchall()
        else:
            items = con.execute("SELECT * FROM menu_items ORDER BY id DESC").fetchall()
    return render_template("menu.html", items=items)

@app.route("/order")
def order():
    return render_template("order.html")

@app.route("/admin")
def admin():
    return redirect(url_for("admin_menu"))

@app.route("/healthz")
def healthz():
    return "ok", 200

# ---------- Admin list ----------
@app.route("/admin_menu")
def admin_menu():
    ensure_columns()
    with get_db() as con:
        items = con.execute("SELECT * FROM menu_items ORDER BY id DESC").fetchall()
    return render_template("admin_menu.html", items=items)

# ---------- Admin edit (SINGLE DEFINITON) ----------
@app.route("/admin/menu/<int:item_id>/edit", methods=["GET", "POST"])
def admin_menu_edit(item_id):
    ensure_columns()
    with get_db() as con:
        if request.method == "POST":
            name = (request.form.get("name") or "").strip()
            price_val = to_float(request.form.get("price"), 0)
            description = (request.form.get("description") or "").strip()
            photo_url = (request.form.get("photo_url") or "").strip()
            category = (request.form.get("category") or "").strip()

            cols = {r["name"] for r in con.execute("PRAGMA table_info(menu_items);")}
            payload = {
                "name": name, "price": price_val, "description": description,
                "photo_url": photo_url, "category": category
            }
            fields, values = [], []
            for k, v in payload.items():
                if k in cols:
                    fields.append(f"{k}=?")
                    values.append(v)

            if not fields:
                flash("No updatable columns found.", "error")
                return redirect(url_for("admin_menu"))

            values.append(item_id)
            con.execute(f"UPDATE menu_items SET {', '.join(fields)} WHERE id=?", tuple(values))
            con.commit()
            flash("Item updated.")
            return redirect(url_for("admin_menu"))

        # GET
        row = con.execute(
            "SELECT * FROM menu_items WHERE id=?", (item_id,)
        ).fetchone()

    if not row:
        flash("Item not found.")
        return redirect(url_for("admin_menu"))
    return render_template("edit_item.html", item=row)

# ---------- Admin delete ----------
@app.route("/admin_menu/delete/<int:item_id>", methods=["POST"])
def admin_menu_delete(item_id):
    with get_db() as con:
        con.execute("DELETE FROM menu_items WHERE id=?", (item_id,))
        con.commit()
    flash("Item deleted.")
    return redirect(url_for("admin_menu"))

# ---------- Admin toggle ----------
@app.route("/admin_menu/toggle/<int:item_id>", methods=["POST"])
def admin_menu_toggle(item_id):
    ensure_columns()
    with get_db() as con:
        if not table_has_column(con, "menu_items", "available"):
            flash("Toggle not supported (missing 'available' column).", "error")
            return redirect(url_for("admin_menu"))
        row = con.execute("SELECT available FROM menu_items WHERE id=?", (item_id,)).fetchone()
        if not row:
            flash("Item not found.", "error")
            return redirect(url_for("admin_menu"))
        new_val = 0 if int(row["available"] or 0) == 1 else 1
        con.execute("UPDATE menu_items SET available=? WHERE id=?", (new_val, item_id))
        con.commit()
    flash("Item availability updated.")
    return redirect(url_for("admin_menu"))

# ---------- Main ----------
if __name__ == "__main__":
    ensure_columns()
    port = int(os.environ.get("PORT", 5000))
    app.run(host="0.0.0.0", port=port, debug=True)