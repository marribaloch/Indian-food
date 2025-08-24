import os
import sqlite3
from flask import Flask, request, render_template, redirect, session
from werkzeug.security import check_password_hash

app = Flask(__name__)

# Secret key: set via ENV on Render, defaults locally
app.config["SECRET_KEY"] = os.environ.get("SECRET_KEY", "change-this")

# Database path: Render uses sqlite:////var/data/app.db, locally fallback to grab.db
DATABASE_URL = os.environ.get("DATABASE_URL", "sqlite:///grab.db")

def _sqlite_path_from_url(url: str) -> str:
    if url.startswith("sqlite:////"):
        return url.replace("sqlite:////", "/")
    if url.startswith("sqlite:///"):
        return url.replace("sqlite:///", "")
    return url

DB_PATH = _sqlite_path_from_url(DATABASE_URL)

def get_db_connection():
    conn = sqlite3.connect(DB_PATH, check_same_thread=False)
    conn.row_factory = sqlite3.Row
    return conn


# ---------------- Routes ----------------

@app.route('/login', methods=['GET', 'POST'])
def login():
    if request.method == 'POST':
        username = request.form['username']
        password = request.form['password']

        conn = get_db_connection()
        user = conn.execute("SELECT * FROM users WHERE username = ?", (username,)).fetchone()
        conn.close()

        if user and check_password_hash(user['password'], password):
            session['user_id'] = user['id']
            session['username'] = user['username']
            session['role'] = user['role']

            # Redirect based on role
            if user['role'] == 'admin':
                return redirect('/admin-dashboard')
            elif user['role'] == 'delivery':
                return redirect('/delivery-dashboard')
            else:
                return redirect('/dashboard')
        else:
            return "Invalid username or password"

    return render_template('login.html')


# Health check route
@app.route("/healthz")
def healthz():
    return "ok", 200


# ---------------- Run ----------------
if __name__ == "__main__":
    app.run()