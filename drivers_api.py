"""
Drop-in Driver API for Indian Food App (Flask)
---------------------------------------------
This module adds driver authentication + order pickup/delivery workflow.

How to integrate (3 steps):
1) Save this file as `drivers_api.py` in your project root (same folder as app.py).
2) In your `app.py`, add:

    from drivers_api import init_driver_api
    init_driver_api(app, get_db)

   (Place after your Flask `app = Flask(...)` and after `get_db()` helper is defined.)

3) Restart:  `python app.py`

Includes:
- SQLite migrations (creates `drivers` table, adds `orders.driver_id` if missing)
- Endpoints:
    POST   /api/driver/register    {name, phone, password}
    POST   /api/driver/login       {phone, password}
    GET    /api/driver/me          (auth)
    GET    /api/driver/orders      (auth) → unassigned pending orders
    POST   /api/driver/accept/<order_id>   (auth)
    POST   /api/driver/update      (auth) → {lat, lng, status?}
    POST   /api/driver/complete/<order_id> (auth)

Auth:
- Send header `Authorization: Bearer <api_key>` OR `X-Driver-Key: <api_key>`

JSON format:
- success → {"ok": true, "data": ...}
- error   → {"ok": false, "error": "message"}
"""

import os, sqlite3, hashlib, secrets, datetime
from functools import wraps
from flask import request, jsonify

# Default DB path fallback if caller doesn't provide get_db
BASE_DIR = os.path.abspath(os.path.dirname(__file__))
DB_PATH  = os.path.join(BASE_DIR, os.environ.get("DB_NAME", "app.db"))

# -------------------------------
# Helpers
# -------------------------------

def _connect_default():
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    return conn


def _get_db_factory(get_db):
    """Return a function that yields a sqlite3 connection (Row factory set)."""
    if callable(get_db):
        def _wrapped():
            conn = get_db()
            try:
                # Ensure row_factory for dict-like access
                conn.row_factory = sqlite3.Row
            except Exception:
                pass
            return conn
        return _wrapped
    return _connect_default


def _now_iso():
    return datetime.datetime.utcnow().strftime("%Y-%m-%d %H:%M:%S")


def _hash_password(pw: str) -> str:
    # Lightweight SHA256 (since app already uses werkzeug for users, but we keep this self-contained)
    return hashlib.sha256((pw or "").encode("utf-8")).hexdigest()


def _make_key() -> str:
    return secrets.token_hex(24)  # 48 hex chars


def _resp_ok(data=None, **extra):
    out = {"ok": True}
    if data is not None:
        out["data"] = data
    out.update(extra)
    return jsonify(out)


def _resp_err(msg, status=400):
    return jsonify({"ok": False, "error": str(msg)}), status


# -------------------------------
# DB migrations
# -------------------------------

def _migrate(conn: sqlite3.Connection):
    cur = conn.cursor()
    # drivers table
    cur.execute(
        """
        CREATE TABLE IF NOT EXISTS drivers (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            name TEXT,
            phone TEXT UNIQUE,
            password_hash TEXT,
            api_key TEXT UNIQUE,
            lat REAL,
            lng REAL,
            is_active INTEGER DEFAULT 1,
            created_at TEXT DEFAULT CURRENT_TIMESTAMP
        )
        """
    )

    # Add driver_id column to orders if missing
    cur.execute("PRAGMA table_info(orders)")
    cols = [r[1] for r in cur.fetchall()]
    if "driver_id" not in cols:
        try:
            cur.execute("ALTER TABLE orders ADD COLUMN driver_id INTEGER")
        except Exception:
            pass

    # optional: index for faster filtering
    cur.execute("CREATE INDEX IF NOT EXISTS idx_orders_driver_status ON orders(driver_id, status)")

    conn.commit()


# -------------------------------
# Auth decorator for drivers
# -------------------------------

def _driver_required(get_db_conn):
    def decorator(fn):
        @wraps(fn)
        def wrapper(*args, **kwargs):
            token = None
            auth = request.headers.get("Authorization", "")
            if auth.lower().startswith("bearer "):
                token = auth.split(" ", 1)[1].strip()
            if not token:
                token = request.headers.get("X-Driver-Key")
            if not token:
                return _resp_err("Missing driver token", 401)
            conn = get_db_conn()
            try:
                row = conn.execute("SELECT * FROM drivers WHERE api_key=? AND is_active=1", (token,)).fetchone()
                if not row:
                    return _resp_err("Invalid driver token", 401)
                request.driver = row  # attach for downstream
                return fn(*args, **kwargs)
            finally:
                try:
                    conn.close()
                except Exception:
                    pass
        return wrapper
    return decorator


# -------------------------------
# Public API: init function
# -------------------------------

def init_driver_api(app, get_db_func=None):
    """Call from app.py to register routes."""
    get_db_conn = _get_db_factory(get_db_func)

    # Run lightweight migrations at import time
    conn = get_db_conn()
    try:
        _migrate(conn)
    finally:
        try:
            conn.close()
        except Exception:
            pass

    driver_required = _driver_required(get_db_conn)

    # --------- REGISTER ---------
    @app.post("/api/driver/register")
    def api_driver_register():
        data = request.get_json(silent=True) or request.form or {}
        name = (data.get("name") or "").strip()
        phone = (data.get("phone") or "").strip()
        password = data.get("password") or ""
        if not phone or not password:
            return _resp_err("phone and password required")
        api_key = _make_key()
        pw_hash = _hash_password(password)

        conn = get_db_conn()
        try:
            conn.execute(
                "INSERT INTO drivers(name, phone, password_hash, api_key, lat, lng) VALUES(?,?,?,?,NULL,NULL)",
                (name, phone, pw_hash, api_key)
            )
            conn.commit()
            driver = conn.execute("SELECT id, name, phone, api_key, is_active FROM drivers WHERE phone=?", (phone,)).fetchone()
            return _resp_ok({"id": driver["id"], "name": driver["name"], "phone": driver["phone"], "api_key": driver["api_key"], "is_active": driver["is_active"]})
        except sqlite3.IntegrityError:
            return _resp_err("Phone already registered", 409)
        finally:
            conn.close()

    # --------- LOGIN ---------
    @app.post("/api/driver/login")
    def api_driver_login():
        data = request.get_json(silent=True) or request.form or {}
        phone = (data.get("phone") or "").strip()
        password = data.get("password") or ""
        if not phone or not password:
            return _resp_err("phone and password required")
        conn = get_db_conn()
        try:
            row = conn.execute("SELECT * FROM drivers WHERE phone=? AND is_active=1", (phone,)).fetchone()
            if not row or row["password_hash"] != _hash_password(password):
                return _resp_err("Invalid phone or password", 401)
            return _resp_ok({"id": row["id"], "name": row["name"], "phone": row["phone"], "api_key": row["api_key"]})
        finally:
            conn.close()

    # --------- ME ---------
    @app.get("/api/driver/me")
    @driver_required
    def api_driver_me():
        d = request.driver
        return _resp_ok({"id": d["id"], "name": d["name"], "phone": d["phone"], "lat": d["lat"], "lng": d["lng"], "is_active": d["is_active"]})

    # --------- AVAILABLE ORDERS (unassigned + pending) ---------
    @app.get("/api/driver/orders")
    @driver_required
    def api_driver_orders():
        status = request.args.get("status")  # optional filter
        conn = get_db_conn()
        try:
            if status:
                rows = conn.execute(
                    "SELECT id, customer_name, name, phone, address, total, status, created_at FROM orders WHERE status=? AND (driver_id IS NULL) ORDER BY created_at DESC",
                    (status,)
                ).fetchall()
            else:
                rows = conn.execute(
                    "SELECT id, customer_name, name, phone, address, total, status, created_at FROM orders WHERE (status IN ('pending','preparing')) AND (driver_id IS NULL) ORDER BY created_at DESC"
                ).fetchall()
            data = [dict(r) for r in rows]
            return _resp_ok(data)
        finally:
            conn.close()

    # --------- ACCEPT ORDER ---------
    @app.post("/api/driver/accept/<int:order_id>")
    @driver_required
    def api_driver_accept(order_id):
        driver = request.driver
        conn = get_db_conn()
        try:
            # Ensure order exists, unassigned, not delivered/cancelled
            o = conn.execute("SELECT id, status, driver_id FROM orders WHERE id=?", (order_id,)).fetchone()
            if not o:
                return _resp_err("Order not found", 404)
            if o["driver_id"]:
                return _resp_err("Order already assigned")
            if o["status"] in ("delivered", "cancelled"):
                return _resp_err("Order already closed")

            # Assign and set status on_the_way (if still pending/preparing)
            new_status = "on_the_way" if o["status"] in ("pending", "preparing", "on_the_way") else o["status"]
            conn.execute("UPDATE orders SET driver_id=?, status=? WHERE id=?", (driver["id"], new_status, order_id))
            conn.commit()
            return _resp_ok({"order_id": order_id, "status": new_status})
        finally:
            conn.close()

    # --------- UPDATE DRIVER (and optional order status) ---------
    @app.post("/api/driver/update")
    @driver_required
    def api_driver_update():
        d = request.driver
        data = request.get_json(silent=True) or request.form or {}
        lat = data.get("lat")
        lng = data.get("lng")
        status = data.get("status")  # optional: 'picked_up' → set order to 'on_the_way'; 'delivered' → final
        order_id = data.get("order_id")

        conn = get_db_conn()
        try:
            # Update driver location if provided
            if lat is not None and lng is not None:
                try:
                    conn.execute("UPDATE drivers SET lat=?, lng=? WHERE id=?", (float(lat), float(lng), d["id"]))
                except Exception:
                    pass

            # Optionally update order status
            if order_id and status:
                o = conn.execute("SELECT id, status, driver_id FROM orders WHERE id=?", (order_id,)).fetchone()
                if not o:
                    return _resp_err("Order not found", 404)
                if o["driver_id"] != d["id"]:
                    return _resp_err("This order is assigned to another driver", 403)

                if status == "picked_up":
                    new_status = "on_the_way"
                elif status == "delivered":
                    new_status = "delivered"
                else:
                    new_status = o["status"]  # ignore unknown

                if new_status != o["status"]:
                    conn.execute("UPDATE orders SET status=? WHERE id=?", (new_status, order_id))

            conn.commit()
            return _resp_ok({"updated": True})
        finally:
            conn.close()

    # --------- COMPLETE (force delivered) ---------
    @app.post("/api/driver/complete/<int:order_id>")
    @driver_required
    def api_driver_complete(order_id):
        d = request.driver
        conn = get_db_conn()
        try:
            o = conn.execute("SELECT id, status, driver_id FROM orders WHERE id=?", (order_id,)).fetchone()
            if not o:
                return _resp_err("Order not found", 404)
            if o["driver_id"] != d["id"]:
                return _resp_err("This order is assigned to another driver", 403)
            if o["status"] == "delivered":
                return _resp_ok({"order_id": order_id, "status": "delivered"})

            conn.execute("UPDATE orders SET status='delivered' WHERE id=?", (order_id,))
            conn.commit()
            return _resp_ok({"order_id": order_id, "status": "delivered"})
        finally:
            conn.close()

    # Health ping for drivers API
    @app.get("/api/driver/health")
    def api_driver_health():
        return _resp_ok({"module": "drivers_api", "db": os.path.basename(DB_PATH), "time": _now_iso()})

    return app
