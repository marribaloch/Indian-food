from flask import Flask, render_template, redirect, url_for

app = Flask(__name__)

# health check (Render ke liye)
@app.route("/healthz")
def healthz():
    return "ok", 200

# Home ko login par bhej dein (ya menu chahen to url_for("menu"))
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
    return render_template("menu.html")

@app.route("/order")
def order():
    return render_template("order.html")

@app.route("/admin")
def admin():
    return render_template("admin-dashboard.html")