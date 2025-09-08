# app.py — Indian Food App (+ Sections/Categories support)
import os, json, sqlite3, datetime, smtplib, shutil, math, urllib.parse, urllib.request
from email.message import EmailMessage
from functools import wraps

from flask import (
    Flask, request, render_template, redirect, url_for, jsonify,
    g, flash, session
)
from werkzeug.security import generate_password_hash, check_password_hash
from flask_wtf import CSRFProtect
from flask_wtf.csrf import generate_csrf

from flask_limiter import Limiter
from flask_limiter.util import get_remote_address

try:
    from dotenv import load_dotenv
    load_dotenv()
except Exception:
    pass

BASE_DIR = os.path.abspath(os.path.dirname(__file__))
DB_NAME  = os.environ.get("DB_NAME", "app.db")
DATA_DIR = os.environ.get("DATA_DIR", "/var/data")

if DATA_DIR:
    try:
        os.makedirs(DATA_DIR, exist_ok=True)
    except Exception:
        pass
    DB_PATH = os.path.join(DATA_DIR, DB_NAME)
    legacy_db = os.path.join(BASE_DIR, DB_NAME)
    if (not os.path.exists(DB_PATH)) and os.path.exists(legacy_db):
        try:
            shutil.copy2(legacy_db, DB_PATH)
        except Exception:
            pass
else:
    DB_PATH = os.path.join(BASE_DIR, DB_NAME)

app = Flask(__name__, template_folder="templates", static_folder="static")
app.secret_key = os.environ.get("SECRET_KEY", "dev-secret-change-me")

app.config.update(
    SESSION_COOKIE_HTTPONLY=True,
    SESSION_COOKIE_SAMESITE="Lax",
    SESSION_COOKIE_SECURE=True,
    WTF_CSRF_TIME_LIMIT=None,
)

csrf = CSRFProtect(app)

@app.context_processor
def inject_csrf():
    return dict(csrf_token=generate_csrf)

limiter = Limiter(get_remote_address, app=app, default_limits=["200 per day", "50 per hour"])

ALLOWED_ORIGINS = [o.strip() for o in os.getenv("ALLOWED_ORIGINS", "").split(",") if o.strip()]
if not ALLOWED_ORIGINS:
    ALLOWED_ORIGINS = ["http://localhost:3000", "http://127.0.0.1:3000"]

@app.after_request
def add_cors_headers(resp):
    try:
        if request.path.startswith("/api/"):
            origin = request.headers.get("Origin", "")
            allow = origin if (origin in ALLOWED_ORIGINS or "*" in ALLOWED_ORIGINS) else None
            if allow:
                resp.headers["Access-Control-Allow-Origin"] = allow
                resp.headers["Vary"] = "Origin"
                resp.headers["Access-Control-Allow-Credentials"] = "true"
                resp.headers["Access-Control-Allow-Headers"] = request.headers.get(
                    "Access-Control-Request-Headers", "Content-Type, Authorization"
                )
                resp.headers["Access-Control-Allow-Methods"] = "GET,POST,PUT,PATCH,DELETE,OPTIONS"
    except Exception:
        pass
    return resp

EMAIL_HOST = os.getenv("EMAIL_HOST") or os.getenv("EMAIL_SERVER") or os.getenv("SMTP_HOST") or "smtp.gmail.com"
EMAIL_PORT = int(os.getenv("EMAIL_PORT") or os.getenv("SMTP_PORT") or 587)
EMAIL_USER = os.getenv("EMAIL_USER") or os.getenv("SMTP_USER")
EMAIL_PASS = os.getenv("EMAIL_PASSWORD") or os.getenv("SMTP_PASS")
FROM_EMAIL = os.getenv("FROM_EMAIL") or (EMAIL_USER or "no-reply@example.com")
ADMIN_EMAIL_DEFAULT = os.getenv("ADMIN_EMAIL") or (EMAIL_USER or "admin@example.com")

DELIVERY_FEE_MODE    = (os.getenv("DELIVERY_FEE_MODE") or "flat").lower()
DELIVERY_FEE_FLAT    = float(os.getenv("DELIVERY_FEE_FLAT") or 0)
SERVICE_FEE_PERCENT  = float(os.getenv("SERVICE_FEE_PERCENT") or 0)

DELIVERY_BASE_FEE = float(os.getenv("DELIVERY_BASE_FEE") or 0)
DELIVERY_PER_KM   = float(os.getenv("DELIVERY_PER_KM") or 0)
DELIVERY_PER_MIN  = float(os.getenv("DELIVERY_PER_MIN") or 0)
DELIVERY_MIN_FEE  = float(os.getenv("DELIVERY_MIN_FEE") or 0)
DELIVERY_MAX_FEE  = float(os.getenv("DELIVERY_MAX_FEE") or 0)
GOOGLE_MAPS_API_KEY = os.getenv("GOOGLE_MAPS_API_KEY")

# ----------------------------- DB Helpers
def get_db():
    if "db" not in g:
        g.db = sqlite3.connect(DB_PATH, detect_types=sqlite3.PARSE_DECLTYPES)
    g.db.row_factory = sqlite3.Row
    return g.db

@app.teardown_appcontext
def close_db(_exc):
    db = g.pop("db", None)
    if db:
        db.close()

def _safe_alter(db, sql):
    try:
        db.execute(sql)
        db.commit()
    except Exception:
        pass

def init_db():
    db = get_db()
    # Users
    db.execute("""
        CREATE TABLE IF NOT EXISTS users (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            name TEXT NOT NULL,
            email TEXT UNIQUE NOT NULL,
            password_hash TEXT NOT NULL,
            is_admin INTEGER DEFAULT 0,
            is_driver INTEGER DEFAULT 0,
            created_at TEXT DEFAULT CURRENT_TIMESTAMP
        );
    """)
    # Sections (NEW)
    db.execute("""
        CREATE TABLE IF NOT EXISTS sections (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            name TEXT NOT NULL,
            description TEXT,
            image_url TEXT,
            sort_order INTEGER DEFAULT 0,
            is_active INTEGER DEFAULT 1,
            created_at TEXT DEFAULT CURRENT_TIMESTAMP
        );
    """)
    # Menu items + section_id (NEW)
    db.execute("""
        CREATE TABLE IF NOT EXISTS menu_items (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            name TEXT NOT NULL,
            description TEXT,
            price REAL NOT NULL,
            image_url TEXT,
            is_active INTEGER DEFAULT 1,
            section_id INTEGER,
            created_at TEXT DEFAULT CURRENT_TIMESTAMP
        );
    """)
    _safe_alter(db, "ALTER TABLE menu_items ADD COLUMN section_id INTEGER")

    # Orders
    db.execute("""
        CREATE TABLE IF NOT EXISTS orders (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id INTEGER,
            items_json TEXT NOT NULL,
            total REAL NOT NULL,
            status TEXT DEFAULT 'pending',
            created_at TEXT DEFAULT CURRENT_TIMESTAMP,
            driver_id INTEGER,
            driver_status TEXT,
            picked_up_at TEXT,
            delivered_at TEXT,
            driver_updates TEXT,
            items_total REAL DEFAULT 0,
            delivery_fee REAL DEFAULT 0,
            service_fee REAL DEFAULT 0,
            grand_total REAL DEFAULT 0,
            restaurant_id INTEGER,
            dropoff_lat REAL,
            dropoff_lng REAL,
            FOREIGN KEY(user_id) REFERENCES users(id)
        );
    """)

    # bootstrap admin
    cur = db.execute("SELECT COUNT(*) AS c FROM users WHERE is_admin = 1;").fetchone()
    if (cur["c"] or 0) == 0:
        db.execute(
            "INSERT INTO users (name, email, password_hash, is_admin) VALUES (?,?,?,1);",
            ("Admin", ADMIN_EMAIL_DEFAULT, generate_password_hash("admin123")),
        )
        db.commit()

    # migrations
    _safe_alter(db, "ALTER TABLE users ADD COLUMN is_driver INTEGER DEFAULT 0")
    _safe_alter(db, "ALTER TABLE orders ADD COLUMN driver_id INTEGER")
    _safe_alter(db, "ALTER TABLE orders ADD COLUMN driver_status TEXT")
    _safe_alter(db, "ALTER TABLE orders ADD COLUMN picked_up_at TEXT")
    _safe_alter(db, "ALTER TABLE orders ADD COLUMN delivered_at TEXT")
    _safe_alter(db, "ALTER TABLE orders ADD COLUMN driver_updates TEXT")
    _safe_alter(db, "ALTER TABLE orders ADD COLUMN items_total REAL DEFAULT 0")
    _safe_alter(db, "ALTER TABLE orders ADD COLUMN delivery_fee REAL DEFAULT 0")
    _safe_alter(db, "ALTER TABLE orders ADD COLUMN service_fee REAL DEFAULT 0")
    _safe_alter(db, "ALTER TABLE orders ADD COLUMN grand_total REAL DEFAULT 0")
    _safe_alter(db, "ALTER TABLE orders ADD COLUMN restaurant_id INTEGER")
    _safe_alter(db, "ALTER TABLE orders ADD COLUMN dropoff_lat REAL")
    _safe_alter(db, "ALTER TABLE orders ADD COLUMN dropoff_lng REAL")

    # Driver presence
    db.execute("""
        CREATE TABLE IF NOT EXISTS driver_presence (
            driver_id INTEGER PRIMARY KEY,
            available INTEGER DEFAULT 0,
            lat REAL,
            lng REAL,
            updated_at TEXT
        );
    """)

    # Restaurants
    db.execute("""
        CREATE TABLE IF NOT EXISTS restaurants (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            name TEXT NOT NULL,
            lat REAL NOT NULL,
            lng REAL NOT NULL,
            created_at TEXT DEFAULT CURRENT_TIMESTAMP
        );
    """)

    db.commit()

# ---- DB init should happen AFTER app is created (Render & local both)
@app.before_first_request
def startup_init():
    try:
        init_db()
    except Exception as e:
        try:
            app.logger.warning("DB init failed: %s", e)
        except Exception:
            print("DB init failed:", e)

@app.route("/plain")
def plain():
    return "<!doctype html><title>Plain</title><h1>Plain OK</h1>"

# >>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>
# NEW: safely wire in the separate drivers_api module (no break by default)
try:
    from drivers_api import init_driver_api as _init_driver_api
    # Enable only when you set:  ENABLE_NEW_DRIVER_API=1
    if os.getenv("ENABLE_NEW_DRIVER_API") in ("1", "true", "True", "yes", "on"):
        _init_driver_api(app, get_db)
except Exception as _e:
    # Silently ignore if file missing or import fails
    pass
# <<<<<<<<<<<<<<<<<<<<<<<<<<<<<<<<<<<<<<<<<<<<<<<<<<<<<<<<<<<<<<<<<<<<<<<<<<

# ----------------------------- Auth Helpers
def login_required(f):
    @wraps(f)
    def _wrap(*args, **kwargs):
        if not session.get("user_id"):
            flash("Please log in first.", "warning")
            return redirect(url_for("login"))
        return f(*args, **kwargs)
    return _wrap

def admin_required(f):
    @wraps(f)
    def _wrap(*args, **kwargs):
        if not session.get("user_id"):
            flash("Please log in first.", "warning")
            return redirect(url_for("login"))
        if not session.get("is_admin"):
            flash("Admin access required.", "danger")
            return redirect(url_for("menu"))
        return f(*args, **kwargs)
    return _wrap

def _get_page_per_page(default_per_page=50, max_per_page=100):
    page = max(1, request.args.get("page", 1, type=int) or 1)
    per_page = min(max(1, request.args.get("per_page", default_per_page, type=int) or default_per_page), max_per_page)
    offset = (page - 1) * per_page
    return page, per_page, offset

# ----------------------------- Jinja Utils
def format_vnd(value):
    try:
        n = float(value)
    except Exception:
        return value
    return f"{int(round(n)):,} VND"

app.jinja_env.filters["vnd"] = format_vnd
app.jinja_env.globals["loads"] = json.loads

# ----------------------------- Email Helper
def send_email_safe(to_addr, subject, body_html_or_text, text_fallback: str | None = None):
    try:
        if not (EMAIL_HOST and EMAIL_PORT and EMAIL_USER and EMAIL_PASS):
            raise RuntimeError("Missing SMTP env vars")
        if not to_addr:
            raise RuntimeError("Missing recipient")
        msg = EmailMessage()
        msg["Subject"] = subject
        msg["From"] = FROM_EMAIL or EMAIL_USER
        msg["To"] = to_addr
        content = body_html_or_text or ""
        is_html = ("<" in content and ">" in content)
        if is_html:
            fallback = text_fallback or "This is an HTML email. Please view in an HTML-capable mail app."
            msg.set_content(fallback)
            msg.add_alternative(content, subtype="html")
        else:
            msg.set_content(content)
        with smtplib.SMTP(EMAIL_HOST, EMAIL_PORT, timeout=20) as s:
            s.ehlo(); s.starttls(); s.ehlo()
            s.login(EMAIL_USER, EMAIL_PASS)
            s.send_message(msg)
        return True, None
    except Exception as e:
        return False, f"{type(e).__name__}: {e}"

# ----------------------------- Delivery helpers
def haversine_km(lat1, lng1, lat2, lng2):
    try:
        R = 6371.0
        dlat = math.radians(lat2 - lat1)
        dlng = math.radians(lng2 - lng1)
        a = math.sin(dlat/2)**2 + math.cos(math.radians(lat1))*math.cos(math.radians(lat2))*math.sin(dlng/2)**2
        c = 2 * math.atan2(math.sqrt(a), math.sqrt(1 - a))
        return R * c
    except Exception:
        return 0.0

def google_drive_time_distance(lat_o, lng_o, lat_d, lng_d, api_key):
    try:
        params = {
            "origins": f"{lat_o},{lng_o}",
            "destinations": f"{lat_d},{lng_d}",
            "key": api_key,
            "departure_time": "now",
            "mode": "driving",
        }
        url = "https://maps.googleapis.com/maps/api/distancematrix/json?" + urllib.parse.urlencode(params)
        with urllib.request.urlopen(url, timeout=8) as resp:
            data = json.loads(resp.read().decode("utf-8"))
        row = data["rows"][0]["elements"][0]
        dist_km = (row.get("distance", {}).get("value", 0) or 0) / 1000.0
        dur_sec = (row.get("duration_in_traffic", {}).get("value") or row.get("duration", {}).get("value") or 0)
        return dist_km, dur_sec / 60.0
    except Exception:
        return None, None

def time_of_day_multiplier(now=None):
    now = now or datetime.datetime.now()
    hr = now.hour
    if 7 <= hr <= 9 or 16 <= hr <= 19:
        return 1.3
    if 11 <= hr <= 13:
        return 1.15
    return 1.0

def compute_dynamic_delivery_fee(pu_lat, pu_lng, do_lat, do_lng):
    base    = float(os.getenv("DELIVERY_BASE_FEE") or DELIVERY_BASE_FEE or 0)
    per_km  = float(os.getenv("DELIVERY_PER_KM")   or DELIVERY_PER_KM   or 0)
    per_min = float(os.getenv("DELIVERY_PER_MIN")  or DELIVERY_PER_MIN  or 0)
    min_fee = float(os.getenv("DELIVERY_MIN_FEE")  or DELIVERY_MIN_FEE  or 0)
    max_fee = float(os.getenv("DELIVERY_MAX_FEE")  or DELIVERY_MAX_FEE  or 0)
    api_key = os.getenv("GOOGLE_MAPS_API_KEY") or GOOGLE_MAPS_API_KEY
    dist_km, dur_min = (None, None)
    if api_key:
        dist_km, dur_min = google_drive_time_distance(pu_lat, pu_lng, do_lat, do_lng, api_key)
    if dist_km is None:
        dist_km = haversine_km(pu_lat, pu_lng, do_lat, do_lng)
        dur_min = (dist_km * 3.0) * time_of_day_multiplier()
    fee = base + (per_km * max(dist_km, 0)) + (per_min * max(dur_min, 0))
    if min_fee > 0:
        fee = max(fee, min_fee)
    if max_fee > 0:
        fee = min(fee, max_fee)
    return round(fee)

# ----------------------------- Safe Home + Health
@app.route("/", methods=["GET"])
def home():
    return redirect(url_for("menu"))

@csrf.exempt
@app.route("/healthz", methods=["GET"])
def healthz():
    return "ok", 200

# ----------------------------- Pages
@csrf.exempt
@limiter.limit("5 per minute")
@app.route("/login", methods=["GET", "POST"])
def login():
    if request.method == "POST":
        email = (request.form.get("email") or "").strip().lower()
        password = (request.form.get("password") or "")
        db = get_db()
        user = db.execute("SELECT * FROM users WHERE email=?;", (email,)).fetchone()
        if user and check_password_hash(user["password_hash"], password):
            session.update({
                "user_id": user["id"],
                "name": user["name"],
                "email": user["email"],
                "is_admin": bool(user["is_admin"]),
                "is_driver": bool(user["is_driver"] or 0),
            })
            return redirect(url_for("admin" if user["is_admin"] else "menu"))
        flash("Invalid credentials.", "danger")
    return render_template("login.html")

@app.route("/logout", methods=["GET"])
def logout():
    session.clear()
    flash("Logged out.", "info")
    return redirect(url_for("login"))

@app.route("/menu", methods=["GET"])
def menu():
    db = get_db()
    sections = db.execute("""
        SELECT * FROM sections
        WHERE is_active = 1
        ORDER BY sort_order DESC, id DESC;
    """).fetchall()
    rows = db.execute("""
        SELECT * FROM menu_items
        WHERE is_active = 1
        ORDER BY section_id IS NOT NULL DESC, section_id, id DESC;
    """).fetchall()

    items_by_section = {}
    uncategorized = []
    for r in rows:
        sid = r["section_id"]
        if sid:
            items_by_section.setdefault(sid, []).append(r)
        else:
            uncategorized.append(r)

    return render_template(
        "menu.html",
        sections=sections,
        items_by_section=items_by_section,
        uncategorized=uncategorized,
    )

@csrf.exempt
@app.route("/order", methods=["GET", "POST"])
@login_required
def order():
    db = get_db()
    if request.method == "POST":
        try:
            items_json = request.form.get("items_json") or (request.json and request.json.get("items_json"))
            items = json.loads(items_json) if isinstance(items_json, str) else (items_json or [])
        except Exception:
            items = []
        items_total = sum((float(i.get("price", 0)) * float(i.get("qty", 1))) for i in items)
        service_fee = (items_total * (SERVICE_FEE_PERCENT/100.0)) if SERVICE_FEE_PERCENT > 0 else 0.0
        delivery_fee = DELIVERY_FEE_FLAT if DELIVERY_FEE_FLAT > 0 else 0.0
        grand_total = items_total + service_fee + delivery_fee
        db.execute("""
            INSERT INTO orders (user_id, items_json, total, status, items_total, service_fee, delivery_fee, grand_total)
            VALUES (?,?,?,?,?,?,?,?);
        """, (session["user_id"], json.dumps(items), grand_total, "pending",
              items_total, service_fee, delivery_fee, grand_total))
        db.commit()
        flash("Order placed successfully!", "success")
        return redirect(url_for("menu"))

    items = db.execute("SELECT * FROM menu_items WHERE is_active = 1 ORDER BY id DESC;").fetchall()
    return render_template("order.html", items=items)

# ----------------------------- Change Password
@csrf.exempt
@app.route("/change_password", methods=["GET", "POST"])
@login_required
def change_password():
    db = get_db()
    uid = session.get("user_id")
    if not uid:
        flash("Please log in first.", "warning")
        return redirect(url_for("login"))

    user = db.execute("SELECT id, password_hash FROM users WHERE id=?;", (uid,)).fetchone()
    if not user:
        session.clear()
        flash("User not found. Please log in again.", "danger")
        return redirect(url_for("login"))

    if request.method == "POST":
        current_password = (request.form.get("current_password") or "").strip()
        new_password     = (request.form.get("new_password") or "").strip()
        confirm_password = (request.form.get("confirm_password") or "").strip()

        if not current_password or not new_password or not confirm_password:
            flash("All fields are required.", "warning")
            return redirect(url_for("change_password"))

        if not check_password_hash(user["password_hash"], current_password):
            flash("Current password is incorrect.", "danger")
            return redirect(url_for("change_password"))

        if new_password != confirm_password:
            flash("New passwords do not match.", "danger")
            return redirect(url_for("change_password"))
        if len(new_password) < 6:
            flash("New password must be at least 6 characters.", "warning")
            return redirect(url_for("change_password"))

        new_hash = generate_password_hash(new_password)
        db.execute("UPDATE users SET password_hash=? WHERE id=?;", (new_hash, user["id"]))
        db.commit()

        flash("Password updated successfully!", "success")
        return redirect(url_for("admin" if session.get("is_admin") else "menu"))

    return render_template("change_password.html")

# ----------------------------- My Orders (paginated)
@app.route("/my_orders", methods=["GET"])
@login_required
def my_orders():
    db = get_db()
    uid = session["user_id"]
    page, per_page, offset = _get_page_per_page(default_per_page=20, max_per_page=100)
    total_rows = db.execute("SELECT COUNT(*) AS c FROM orders WHERE user_id=?;", (uid,)).fetchone()["c"]
    rows = db.execute("""
        SELECT id, items_json, total, status, created_at, items_total, delivery_fee, service_fee, grand_total
        FROM orders
        WHERE user_id = ?
        ORDER BY id DESC
        LIMIT ? OFFSET ?;
    """, (uid, per_page, offset)).fetchall()

    orders = []
    for r in rows:
        try:
            items = json.loads(r["items_json"]) if r["items_json"] else []
        except Exception:
            items = []
        items_total = float(r["items_total"] or 0)
        if (items_total == 0) and items:
            items_total = sum(float(i.get("price",0))*float(i.get("qty",1)) for i in items)
        delivery_fee = float(r["delivery_fee"] or 0)
        service_fee  = float(r["service_fee"] or 0)
        grand_total  = float(r["grand_total"] or 0) or (items_total + delivery_fee + service_fee)
        orders.append({
            "id": r["id"], "items": items, "status": (r["status"] or ""), "created_at": r["created_at"],
            "items_total": items_total, "delivery_fee": delivery_fee, "service_fee": service_fee, "total": grand_total
        })

    paid_states = {"confirmed", "ready", "delivered"}
    total_spent = sum(float(o["total"]) for o in orders if str(o["status"]).lower() in paid_states)
    total_pages = max(1, (total_rows + per_page - 1) // per_page)

    return render_template("orders_my.html",
                           orders=orders, total_spent=total_spent,
                           page=page, per_page=per_page, total_pages=total_pages, total_rows=total_rows)

# ----------------------------- Order detail
@app.route("/order/<int:order_id>", methods=["GET"])
@login_required
def order_detail(order_id):
    db = get_db()
    row = db.execute("""
        SELECT o.*, u.name as user_name, u.email as user_email
          FROM orders o LEFT JOIN users u ON u.id=o.user_id
         WHERE o.id=?
    """, (order_id,)).fetchone()
    if not row:
        flash("Order not found.", "warning")
        return redirect(url_for("my_orders"))
    if (not session.get("is_admin")) and (row["user_id"] != session.get("user_id")):
        flash("You cannot view this order.", "danger")
        return redirect(url_for("my_orders"))

    try:
        items = json.loads(row["items_json"]) if row["items_json"] else []
    except Exception:
        items = []
    items_total = float(row["items_total"] or 0)
    if (items_total == 0) and items:
        items_total = sum(float(i.get("price",0))*float(i.get("qty",1)) for i in items)
    delivery_fee = float(row["delivery_fee"] or 0)
    service_fee  = float(row["service_fee"] or 0)
    total        = float(row["grand_total"] or 0) or (items_total + delivery_fee + service_fee)

    order_obj = {
        "id": row["id"], "status": row["status"], "created_at": row["created_at"],
        "items": items, "items_total": items_total, "delivery_fee": delivery_fee,
        "service_fee": service_fee, "total": total,
        "user_name": row["user_name"], "user_email": row["user_email"],
    }
    return render_template("order_detail.html", order=order_obj)

# ----------------------------- Admin panel
@app.route("/admin", methods=["GET"])
@admin_required
def admin():
    db = get_db()
    items = db.execute("SELECT * FROM menu_items ORDER BY id DESC;").fetchall()
    page, per_page, offset = _get_page_per_page(default_per_page=50, max_per_page=100)
    total_orders = db.execute("SELECT COUNT(*) AS c FROM orders;").fetchone()["c"]
    orders = db.execute(
        "SELECT o.*, u.name AS user_name, u.email AS email FROM orders o LEFT JOIN users u ON u.id=o.user_id ORDER BY o.id DESC LIMIT ? OFFSET ?;",
        (per_page, offset)
    ).fetchall()
    total_pages = max(1, (total_orders + per_page - 1) // per_page)
    return render_template("admin.html",
                           items=items, orders=orders,
                           page=page, per_page=per_page, total_pages=total_pages, total_orders=total_orders)

# ----------------------------- Admin: Sections CRUD (NEW)
@app.route("/admin/sections", methods=["GET"])
@admin_required
def admin_sections():
    db = get_db()
    rows = db.execute("SELECT * FROM sections ORDER BY sort_order DESC, id DESC;").fetchall()
    return render_template("sections_list.html", rows=rows)

@csrf.exempt
@app.route("/admin/sections/new", methods=["GET","POST"])
@admin_required
def admin_sections_new():
    db = get_db()
    if request.method == "POST":
        name = (request.form.get("name") or "").strip()
        desc = (request.form.get("description") or "").strip()
        image_url = (request.form.get("image_url") or "").strip()
        sort_order = request.form.get("sort_order", type=int) or 0
        is_active = 1 if (request.form.get("is_active") == "on") else 0
        if not name:
            flash("Name is required.", "warning")
            return redirect(url_for("admin_sections_new"))
        db.execute("""
            INSERT INTO sections (name, description, image_url, sort_order, is_active)
            VALUES (?,?,?,?,?)
        """, (name, desc, image_url, sort_order, is_active))
        db.commit()
        flash("Section created.", "success")
        return redirect(url_for("admin_sections"))
    return render_template("section_form.html", mode="new", item=None)

@csrf.exempt
@app.route("/admin/sections/<int:section_id>/edit", methods=["GET","POST"])
@admin_required
def admin_sections_edit(section_id):
    db = get_db()
    if request.method == "POST":
        name = (request.form.get("name") or "").strip()
        desc = (request.form.get("description") or "").strip()
        image_url = (request.form.get("image_url") or "").strip()
        sort_order = request.form.get("sort_order", type=int) or 0
        is_active = 1 if (request.form.get("is_active") == "on") else 0
        if not name:
            flash("Name is required.", "warning")
            return redirect(url_for("admin_sections_edit", section_id=section_id))
        db.execute("""
            UPDATE sections SET name=?, description=?, image_url=?, sort_order=?, is_active=? WHERE id=?
        """, (name, desc, image_url, sort_order, is_active, section_id))
        db.commit()
        flash("Section updated.", "success")
        return redirect(url_for("admin_sections"))
    row = db.execute("SELECT * FROM sections WHERE id=?;", (section_id,)).fetchone()
    if not row:
        flash("Section not found.", "danger")
        return redirect(url_for("admin_sections"))
    return render_template("section_form.html", mode="edit", item=row)

@csrf.exempt
@app.route("/admin/sections/<int:section_id>/delete", methods=["POST"])
@admin_required
def admin_sections_delete(section_id):
    db = get_db()
    db.execute("UPDATE menu_items SET section_id=NULL WHERE section_id=?;", (section_id,))
    db.execute("DELETE FROM sections WHERE id=?;", (section_id,))
    db.commit()
    flash("Section deleted.", "info")
    return redirect(url_for("admin_sections"))

# ----------------------------- Admin: Menu CRUD (add section_id support)
@csrf.exempt
@app.route("/admin/menu/new", methods=["GET", "POST"])
@admin_required
def admin_menu_new():
    db = get_db()
    if request.method == "POST":
        name = (request.form.get("name") or "").strip()
        desc = (request.form.get("description") or "").strip()
        price = request.form.get("price", type=float) or 0.0
        image_url = (request.form.get("image_url") or "").strip()
        section_id = request.form.get("section_id", type=int)
        is_active = 1 if (request.form.get("is_active") == "on") else 0
        if not name or price <= 0:
            flash("Name and positive price are required.", "warning")
            return redirect(url_for("admin_menu_new"))
        db.execute("""
            INSERT INTO menu_items (name, description, price, image_url, is_active, section_id)
            VALUES (?,?,?,?,?,?)
        """, (name, desc, price, image_url, is_active, section_id))
        db.commit()
        flash("Menu item created.", "success")
        return redirect(url_for("admin"))
    sections = db.execute("SELECT * FROM sections WHERE is_active=1 ORDER BY sort_order DESC, id DESC;").fetchall()
    item = {"name":"", "description":"", "price":"", "image_url":"", "is_active":1, "section_id":None}
    return render_template("item_form.html", mode="new", item=item, sections=sections)

@csrf.exempt
@app.route("/admin/menu/<int:item_id>/edit", methods=["GET", "POST"])
@admin_required
def admin_menu_edit(item_id):
    db = get_db()
    if request.method == "POST":
        name = (request.form.get("name") or "").strip()
        desc = (request.form.get("description") or "").strip()
        price = request.form.get("price", type=float) or 0.0
        image_url = (request.form.get("image_url") or "").strip()
        section_id = request.form.get("section_id", type=int)
        is_active = 1 if (request.form.get("is_active") == "on") else 0
        if not name or price <= 0:
            flash("Name and positive price are required.", "warning")
            return redirect(url_for("admin_menu_edit", item_id=item_id))
        db.execute("""
            UPDATE menu_items
               SET name=?, description=?, price=?, image_url=?, is_active=?, section_id=?
             WHERE id=?
        """, (name, desc, price, image_url, is_active, section_id, item_id))
        db.commit()
        flash("Menu item updated.", "success")
        return redirect(url_for("admin"))
    item = db.execute("SELECT * FROM menu_items WHERE id=?", (item_id,)).fetchone()
    if not item:
        flash("Item not found.", "danger")
        return redirect(url_for("admin"))
    sections = db.execute("SELECT * FROM sections WHERE is_active=1 ORDER BY sort_order DESC, id DESC;").fetchall()
    return render_template("item_form.html", mode="edit", item=item, sections=sections)

@csrf.exempt
@app.route("/admin/menu/<int:item_id>/delete", methods=["POST"])
@admin_required
def admin_menu_delete(item_id):
    db = get_db()
    db.execute("DELETE FROM menu_items WHERE id=?", (item_id,))
    db.commit()
    flash(f"Item #{item_id} deleted.", "info")
    return redirect(url_for("admin"))

# ----------------------------- Admin: order status & email
@csrf.exempt
@app.route("/admin/orders/<int:order_id>/status", methods=["POST"])
@admin_required
def admin_order_status(order_id):
    new_status = (request.form.get("status") or "").strip().lower()
    allowed = {"pending","confirmed","preparing","out_for_delivery","ready","delivered","cancelled"}
    if new_status not in allowed:
        flash("Invalid status.", "danger")
        return redirect(url_for("admin"))
    db = get_db()
    db.execute("UPDATE orders SET status=? WHERE id=?;", (new_status, order_id))
    db.commit()
    row = db.execute("""
        SELECT o.id, o.total, o.items_json, o.status, o.created_at, u.name AS user_name, u.email AS email
          FROM orders o LEFT JOIN users u ON u.id = o.user_id
         WHERE o.id = ?;
    """, (order_id,)).fetchone()
    to_email = (row["email"] if row and row["email"] else None) or ADMIN_EMAIL_DEFAULT
    nice = {
        "pending":"Pending","confirmed":"Confirmed","preparing":"Preparing",
        "out_for_delivery":"Out for Delivery","ready":"Ready for Pickup",
        "delivered":"Delivered","cancelled":"Cancelled"
    }
    subject = f"🍽️ Order #{order_id} Status: {nice.get(new_status, new_status.title())}"
    html = None
    try:
        html = render_template(
            "email_order_status.html",
            order_id=order_id,
            status_label=nice.get(new_status, new_status.title()),
            total=row["total"] if row else 0,
            items=json.loads(row["items_json"]) if (row and row["items_json"]) else [],
            at=datetime.datetime.now(),
            app_name="Indian Food App",
            reply_to=EMAIL_USER
        )
    except Exception:
        html = None
    text_fallback = (
        f"Hello,\n\nYour order #{order_id} status is now: "
        f"{nice.get(new_status, new_status.title())}.\n"
        f"Time: {datetime.datetime.now().isoformat()}\n\nThank you!"
    )
    ok, err = send_email_safe(to_email, subject, html or text_fallback, text_fallback=text_fallback)
    flash_msg = f"Order {order_id} → {new_status}" + (" (email sent)" if ok else f" (email failed: {err})")
    flash(flash_msg, "success" if ok else "warning")
    return redirect(url_for("admin"))

@csrf.exempt
@app.route("/admin/orders/<int:order_id>/delete", methods=["POST"])
@admin_required
def admin_order_delete(order_id):
    db = get_db()
    db.execute("DELETE FROM orders WHERE id=?;", (order_id,))
    db.commit()
    flash(f"Order {order_id} deleted.", "info")
    return redirect(url_for("admin"))

@csrf.exempt
@app.route("/admin/test_email", methods=["POST"])
@admin_required
def admin_test_email():
    sample_html = None
    try:
        sample_html = render_template(
            "email_order_status.html",
            order_id=999,
            status_label="Confirmed",
            total=111000,
            items=[{"name":"Butter Chicken","qty":1,"price":99000}],
            at=datetime.datetime.now(),
            app_name="Indian Food App",
            reply_to=EMAIL_USER
        )
    except Exception:
        sample_html = None
    text = "This is a test email from Indian Food App."
    ok, err = send_email_safe(ADMIN_EMAIL_DEFAULT, "Test Email", sample_html or text, text_fallback=text)
    flash("Test email sent!" if ok else f"Email error: {err}", "success" if ok else "danger")
    return redirect(url_for("admin"))

# ----------------------------- Public JSON APIs
@app.route("/api/config", methods=["GET"])
@csrf.exempt
def api_config():
    return jsonify({
        "ok": True,
        "delivery_fee_mode": DELIVERY_FEE_MODE,
        "delivery_fee_flat": DELIVERY_FEE_FLAT,
        "service_fee_percent": SERVICE_FEE_PERCENT,
        "dynamic": {
            "base": DELIVERY_BASE_FEE,
            "per_km": DELIVERY_PER_KM,
            "per_min": DELIVERY_PER_MIN,
            "min_fee": DELIVERY_MIN_FEE,
            "max_fee": DELIVERY_MAX_FEE,
        }
    })

@limiter.limit("10 per minute")
@app.route("/api/login", methods=["POST"])
@csrf.exempt
def api_login():
    data = request.get_json(silent=True) or {}
    email = (data.get("email") or "").strip().lower()
    password = (data.get("password") or "").strip()
    if not email or not password:
        return jsonify({"ok": False, "error": "email & password required"}), 400
    db = get_db()
    user = db.execute(
        "SELECT id, name, email, is_admin, is_driver, password_hash FROM users WHERE email=?",
        (email,)
    ).fetchone()
    if (not user) or (not check_password_hash(user["password_hash"], password)):
        return jsonify({"ok": False, "error": "invalid credentials"}), 401
    return jsonify({"ok": True, "user": {
        "id": user["id"], "name": user["name"], "email": user["email"],
        "is_admin": bool(user["is_admin"]), "is_driver": bool(user["is_driver"] or 0)
    }})

@limiter.limit("10 per minute")
@app.route("/api/register", methods=["POST"])
@csrf.exempt
def api_register():
    data = request.get_json(silent=True) or {}
    name = (data.get("name") or "").strip() or "User"
    email = (data.get("email") or "").strip().lower()
    password = (data.get("password") or "").strip()
    if not email or not password:
        return jsonify({"ok": False, "error": "email & password required"}), 400
    db = get_db()
    exists = db.execute("SELECT id FROM users WHERE email=?", (email,)).fetchone()
    if exists:
        return jsonify({"ok": False, "error": "email already registered"}), 409
    db.execute(
        "INSERT INTO users (name, email, password_hash, is_admin) VALUES (?,?,?,0)",
        (name, email, generate_password_hash(password))
    )
    db.commit()
    user = db.execute("SELECT id, name, email, is_admin FROM users WHERE email=?", (email,)).fetchone()
    return jsonify({"ok": True, "user": dict(user)}), 201

@app.route("/api/driver/register", methods=["POST"])
@csrf.exempt
def api_driver_register():
    data = request.get_json(silent=True) or {}
    name = (data.get("name") or "").strip() or "Driver"
    email = (data.get("email") or "").strip().lower()
    password = (data.get("password") or "").strip()
    if not email or not password:
        return jsonify({"ok": False, "error": "email & password required"}), 400
    db = get_db()
    exists = db.execute("SELECT id FROM users WHERE email=?", (email,)).fetchone()
    if exists:
        return jsonify({"ok": False, "error": "email already registered"}), 409
    db.execute(
        "INSERT INTO users (name, email, password_hash, is_admin, is_driver) VALUES (?,?,?,?,?)",
        (name, email, generate_password_hash(password), 0, 1)
    )
    db.commit()
    user = db.execute("SELECT id, name, email, is_driver FROM users WHERE email=?", (email,)).fetchone()
    return jsonify({"ok": True, "user": dict(user)}), 201

@app.route("/api/driver/login", methods=["POST"])
@csrf.exempt
def api_driver_login():
    data = request.get_json(silent=True) or {}
    email = (data.get("email") or "").strip().lower()
    password = (data.get("password") or "").strip()
    db = get_db()
    user = db.execute("SELECT id, name, email, is_driver, password_hash FROM users WHERE email=?", (email,)).fetchone()
    if (not user) or (not check_password_hash(user["password_hash"], password)) or (not user["is_driver"]):
        return jsonify({"ok": False, "error": "invalid driver credentials"}), 401
    return jsonify({"ok": True, "driver": {"id": user["id"], "name": user["name"], "email": user["email"]}})

@app.route("/api/driver/available", methods=["POST"])
@csrf.exempt
def api_driver_available():
    data = request.get_json(silent=True) or {}
    driver_id = int(data.get("driver_id") or 0)
    if not driver_id:
        return jsonify({"ok": False, "error": "driver_id required"}), 400
    available = 1 if (data.get("available") in (True, 1, "true", "yes", "on")) else 0
    lat = data.get("lat"); lng = data.get("lng")
    db = get_db()
    db.execute("""
        INSERT INTO driver_presence (driver_id, available, lat, lng, updated_at)
        VALUES (?,?,?,?,?)
        ON CONFLICT(driver_id) DO UPDATE SET
          available=excluded.available, lat=excluded.lat, lng=excluded.lng, updated_at=excluded.updated_at
    """, (driver_id, available, lat, lng, datetime.datetime.now().isoformat()))
    db.commit()
    return jsonify({"ok": True})

@app.route("/api/my_orders", methods=["GET"])
@csrf.exempt
def api_my_orders():
    email = (request.args.get("email") or "").strip().lower()
    user_id = request.args.get("user_id", type=int)
    db = get_db()
    if not user_id and email:
        u = db.execute("SELECT id FROM users WHERE email=?", (email,)).fetchone()
        if not u:
            return jsonify({"ok": True, "orders": []})
        user_id = u["id"]
    if not user_id:
        return jsonify({"ok": False, "error": "email or user_id required"}), 400
    rows = db.execute("""
        SELECT id, items_json, total, status, created_at, driver_id, driver_status,
               items_total, delivery_fee, service_fee, grand_total
        FROM orders
        WHERE user_id = ?
        ORDER BY id DESC
    """, (user_id,)).fetchall()
    out = []
    for r in rows:
        try:
            items = json.loads(r["items_json"]) if r["items_json"] else []
        except Exception:
            items = []
        items_total = float(r["items_total"] or 0)
        if (items_total == 0) and items:
            items_total = sum(float(i.get("price",0))*float(i.get("qty",1)) for i in items)
        delivery_fee = float(r["delivery_fee"] or 0)
        service_fee  = float(r["service_fee"] or 0)
        grand_total  = float(r["grand_total"] or 0) or (items_total + delivery_fee + service_fee)
        out.append({
            "id": r["id"], "status": r["status"], "created_at": r["created_at"],
            "items": items, "items_total": items_total,
            "delivery_fee": delivery_fee, "service_fee": service_fee,
            "total": grand_total, "driver_id": r["driver_id"], "driver_status": r["driver_status"]
        })
    return jsonify({"ok": True, "orders": out})

@app.route("/api/open_orders", methods=["GET"])
@csrf.exempt
def api_open_orders():
    db = get_db()
    rows = db.execute("""
        SELECT id, total, status, created_at FROM orders
        WHERE (driver_id IS NULL OR driver_id = 0)
          AND status IN ('confirmed','preparing','ready')
        ORDER BY id ASC
        LIMIT 50
    """).fetchall()
    return jsonify({"ok": True, "orders": [dict(r) for r in rows]})

@limiter.limit("20 per minute")
@app.route("/api/order", methods=["POST"])
@csrf.exempt
def api_order():
    data = request.get_json(silent=True) or {}
    email = (data.get("email") or "").strip().lower()
    items = data.get("items") or []
    if not items:
        return jsonify({"ok": False, "error": "No items"}), 400
    items_total = sum(float(i["price"]) * int(i.get("qty",1)) for i in items)
    drop_lat = float((data.get("dropoff_lat") or 0))
    drop_lng = float((data.get("dropoff_lng") or 0))
    rest_lat = float((data.get("restaurant_lat") or 0))
    rest_lng = float((data.get("restaurant_lng") or 0))
    mode = (os.getenv("DELIVERY_FEE_MODE") or DELIVERY_FEE_MODE).lower()
    if mode == "dynamic" and all([rest_lat, rest_lng, drop_lat, drop_lng]):
        delivery_fee = compute_dynamic_delivery_fee(rest_lat, rest_lng, drop_lat, drop_lng)
    else:
        delivery_fee = float(os.getenv("DELIVERY_FEE_FLAT") or DELIVERY_FEE_FLAT or 0)
    service_fee = (items_total * (SERVICE_FEE_PERCENT/100.0)) if SERVICE_FEE_PERCENT > 0 else 0.0
    grand_total = items_total + service_fee + delivery_fee
    db = get_db()
    user_id = None
    if email:
        u = db.execute("SELECT id, name FROM users WHERE email=?;", (email,)).fetchone()
        if not u:
            db.execute(
                "INSERT INTO users (name,email, password_hash) VALUES (?,?,?);",
                ((email.split('@')[0] or "Guest"), email, generate_password_hash(os.urandom(8).hex()))
            )
            db.commit()
            u = db.execute("SELECT id, name FROM users WHERE email=?;", (email,)).fetchone()
        user_id = u["id"]
    cur = db.execute("""
        INSERT INTO orders (user_id, items_json, total, status,
                            items_total, service_fee, delivery_fee, grand_total,
                            restaurant_id, dropoff_lat, dropoff_lng)
        VALUES (?,?,?,?,?,?,?,?,?,?,?);
    """, (user_id, json.dumps(items), grand_total, "pending",
          items_total, service_fee, delivery_fee, grand_total,
          (int(data.get("restaurant_id")) if data.get("restaurant_id") else None),
          drop_lat, drop_lng))
    db.commit()
    order_id = cur.lastrowid
    if email:
        html = None
        try:
            html = render_template(
                "email_order_confirmation.html",
                order_id=order_id, total=grand_total, items=items,
                at=datetime.datetime.now(),
                customer_name=(u["name"] if user_id else "Customer"),
                app_name="Indian Food App", reply_to=EMAIL_USER
            )
        except Exception:
            html = None
        text = (f"Thanks! We received your order #{order_id} at "
                f"{datetime.datetime.now().isoformat()}. Total: {int(grand_total)} VND")
        send_email_safe(email, f"🧾 Order #{order_id} received", html or text, text_fallback=text)
    return jsonify({"ok": True, "order_id": order_id, "total": grand_total})

@app.route("/api/order/<int:order_id>/status", methods=["GET"])
@csrf.exempt
def api_order_status(order_id):
    db = get_db()
    row = db.execute("SELECT status, driver_status, driver_id FROM orders WHERE id=?;", (order_id,)).fetchone()
    if not row:
        return jsonify({"ok": False, "error": "Not found"}), 404
    return jsonify({"ok": True, "order_id": order_id,
                    "status": row["status"], "driver_status": row["driver_status"], "driver_id": row["driver_id"]})

# ----------------------------- Register page
@csrf.exempt
@limiter.limit("5 per minute")
@app.route("/register", methods=["GET", "POST"], endpoint="register")
def register():
    if request.method == "POST":
        name = (request.form.get("name") or "").strip() or "User"
        email = (request.form.get("email") or "").strip().lower()
        password = (request.form.get("password") or "").strip()
        if not email or not password:
            flash("Email & password required.", "warning")
            return redirect(url_for("register"))
        db = get_db()
        exists = db.execute("SELECT id FROM users WHERE email=?;", (email,)).fetchone()
        if exists:
            flash("Email already registered. Please log in.", "info")
            return redirect(url_for("login"))
        db.execute("INSERT INTO users (name, email, password_hash, is_admin) VALUES (?,?,?,0);",
                   (name, email, generate_password_hash(password)))
        db.commit()
        flash("Account created. Please log in.", "success")
        return redirect(url_for("login"))
    return render_template("register.html")

app.add_url_rule("/register", endpoint="register_page", view_func=register, methods=["GET", "POST"])

# ----------------------------- Errors
@app.errorhandler(404)
def page_not_found(e):
    return render_template("404.html"), 404

@app.errorhandler(500)
def internal_error(e):
    return render_template("500.html"), 500

if __name__ == "__main__":
    with app.app_context():
        init_db()
    app.run(host="0.0.0.0", port=5000, debug=True, use_reloader=False)
