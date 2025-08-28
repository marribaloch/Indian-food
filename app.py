from flask import Flask, request, jsonify, render_template, redirect, url_for
from flask_cors import CORS
import sqlite3
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

# STEP 3.1: /menu reads menu_items from SQLite and renders the template
@app.route("/menu")
def menu():
    con = get_db()
    try:
        cur = con.cursor()
        # Ensure table exists (safe to keep)
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