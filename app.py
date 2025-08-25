from flask import Flask, render_template, request, redirect, url_for
import sqlite3
from pathlib import Path

app = Flask(__name__)
DB_PATH = Path(__file__).with_name("grab.db")

# Health check
@app.route("/healthz")
def healthz():
    return "ok", 200

# Home -> Login
@app.route("/")
def home():
    return redirect(url_for("login"))

# Login page
@app.route("/login", methods=["GET", "POST"])
def login():
    if request.method == "POST":
        email = request.form.get("email")
        password = request.form.get("password")
        return f"Login attempt: {email}, {password}"
    return render_template("login.html")

# Register page
@app.route("/register", methods=["GET", "POST"])
def register():
    if request.method == "POST":
        name = request.form.get("name")
        email = request.form.get("email")
        password = request.form.get("password")

        conn = sqlite3.connect(DB_PATH)
        conn.execute("INSERT INTO users (name, email, password_hash) VALUES (?, ?, ?)", (name, email, password))
        conn.commit()
        conn.close()

        return f"Registered: {name}, {email}"
    return render_template("register.html")

# Menu page
@app.route("/menu")
def menu():
    return render_template("menu.html")

# Order page
@app.route("/order")
def order():
    return render_template("order.html")

# Admin dashboard
@app.route("/admin")
def admin():
    return render_template("admin-dashboard.html")

# Run Flask app
if __name__ == "__main__":
    app.run(debug=True)