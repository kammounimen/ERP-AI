"""
auth_server.py — ERP-AI Authentication & System Control Server
Flask backend : login, session, dashboard API
"""

from flask import Flask, request, jsonify, session, send_from_directory
from flask_cors import CORS
import pymysql
import hashlib
import secrets
import os
import datetime
import platform
from functools import wraps
from dotenv import load_dotenv

load_dotenv()

app = Flask(__name__, static_folder="static")
app.secret_key = os.getenv("FLASK_SECRET", secrets.token_hex(32))
CORS(app, supports_credentials=True)

# ── DB Config ────────────────────────────────────────────────────────────────
DB_CONFIG = {
    "host":     os.getenv("DB_HOST", "localhost"),
    "user":     os.getenv("DB_USER", "root"),
    "password": os.getenv("DB_PASSWORD", "imenemnamariam123"),
    "database": os.getenv("DB_NAME", "invoices_db"),
    "charset":  "utf8mb4",
    "cursorclass": pymysql.cursors.DictCursor,
}

# ─────────────────────────────────────────────────────────────────────────────
# Helpers
# ─────────────────────────────────────────────────────────────────────────────

def get_db():
    return pymysql.connect(**DB_CONFIG)

def hash_password(password: str) -> str:
    return hashlib.sha256(password.encode()).hexdigest()

def login_required(f):
    @wraps(f)
    def decorated(*args, **kwargs):
        if not session.get("user_id"):
            return jsonify({"success": False, "error": "Non authentifié"}), 401
        return f(*args, **kwargs)
    return decorated

def add_log(level: str, message: str):
    try:
        conn = get_db()
        with conn.cursor() as cur:
            cur.execute(
                "INSERT INTO system_logs (level, message) VALUES (%s, %s)",
                (level, message)
            )
        conn.commit()
        conn.close()
    except Exception:
        pass

# ─────────────────────────────────────────────────────────────────────────────
# Routes statiques
# ─────────────────────────────────────────────────────────────────────────────

@app.route("/")
def index():
    return send_from_directory("static", "index.html")

@app.route("/licences")
@login_required
def licences_page():

    if session.get("role") != "admin":
        return "Accès refusé", 403

    return send_from_directory("static", "licences.html")

# ─────────────────────────────────────────────────────────────────────────────
# AUTH — Login / Logout / Session
# ─────────────────────────────────────────────────────────────────────────────

@app.route("/api/auth/login", methods=["POST"])
def login():
    data = request.get_json() or {}
    username = (data.get("username") or "").strip()
    password = data.get("password", "")

    if not username or not password:
        return jsonify({
            "success": False,
            "error": "Tous les champs sont requis"
        }), 400

    try:
        conn = get_db()

        with conn.cursor() as cur:
            cur.execute(
                "SELECT * FROM users WHERE (username=%s OR email=%s) AND is_active=1",
                (username, username)
            )
            user = cur.fetchone()

    except Exception as e:
        return jsonify({
            "success": False,
            "error": f"Erreur BDD : {e}"
        }), 500

    if not user or user["password_hash"] != hash_password(password):
        add_log("WARNING", f"Échec login pour: {username}")
        return jsonify({
            "success": False,
            "error": "Identifiants incorrects"
        }), 401

# Vérification licence liée à l'utilisateur
    with conn.cursor() as cur:
        cur.execute("""
            SELECT l.*
            FROM licences l
            JOIN users u ON u.license_id = l.id
            WHERE u.id = %s
        """, (user["id"],))

        licence = cur.fetchone()

    if not licence:
        conn.close()
        return jsonify({
            "success": False,
            "error": "Aucune licence associée à cet utilisateur"
        }), 403

    if licence["status"] != "active":
        conn.close()
        return jsonify({
            "success": False,
            "error": "Licence bloquée ou expirée"
        }), 403

    if licence["end_date"] < datetime.date.today():
        conn.close()
        return jsonify({
            "success": False,
            "error": "Licence expirée"
        }), 403
    conn.close()

    session.permanent = True
    session["user_id"] = user["id"]
    session["username"] = user["username"]
    session["role"] = user["role"]

    add_log("INFO", f"Connexion réussie : {username}")

    return jsonify({
        "success": True,
        "user": {
            "id": user["id"],
            "username": user["username"],
            "email": user["email"],
            "role": user["role"],
            "fullname": user.get("fullname", username),
        }
    })


@app.route("/api/auth/logout", methods=["POST"])
@login_required
def logout():
    username = session.get("username", "?")
    session.clear()
    add_log("INFO", f"Déconnexion : {username}")
    return jsonify({"success": True})


@app.route("/api/auth/me", methods=["GET"])
@login_required
def me():
    return jsonify({
        "success": True,
        "user_id": session["user_id"],
        "username": session["username"],
        "role": session["role"]
    })

# ─────────────────────────────────────────────────────────────────────────────
# SYSTEM STATUS
# ─────────────────────────────────────────────────────────────────────────────

@app.route("/api/system/status", methods=["GET"])
@login_required
def system_status():
    import urllib.request
    import psutil

    api_url = os.getenv("AGENT_API_URL", "http://localhost:8000")

    # DB check
    db_ok = False
    try:
        conn = get_db()
        with conn.cursor() as cur:
            cur.execute("SELECT 1")
        conn.close()
        db_ok = True
    except:
        pass

    # API check
    api_ok = False
    try:
        urllib.request.urlopen(f"{api_url}/health", timeout=2)
        api_ok = True
    except:
        pass

    # system stats
    try:
        cpu = psutil.cpu_percent(interval=0.2)
        mem = psutil.virtual_memory().percent
        disk = psutil.disk_usage("/").percent
    except:
        cpu = mem = disk = 0

    return jsonify({
        "success": True,
        "server": {
            "status": "online",
            "os": platform.system() + " " + platform.release(),
            "cpu": cpu,
            "memory": mem,
            "disk": disk,
            "timestamp": datetime.datetime.now().isoformat(),
        },
        "database": {"status": "online" if db_ok else "offline"},
        "api_ia": {"status": "online" if api_ok else "offline", "url": api_url},
    })

# ─────────────────────────────────────────────────────────────────────────────
# SYSTEM CONTROL
# ─────────────────────────────────────────────────────────────────────────────

@app.route("/api/system/control", methods=["POST"])
@login_required
def system_control():
    if session.get("role") not in ("admin", "superadmin"):
        return jsonify({"success": False, "error": "Droits insuffisants"}), 403

    data = request.get_json() or {}
    action = data.get("action", "")
    username = session.get("username", "?")

    messages = {
        "start": "Système démarré",
        "stop": "Système arrêté",
        "restart": "API redémarrée",
    }

    if action not in messages:
        return jsonify({"success": False, "error": "Action inconnue"}), 400

    add_log("INFO", f"{messages[action]} par {username}")

    return jsonify({"success": True, "message": messages[action]})

# ─────────────────────────────────────────────────────────────────────────────
# LOGS
# ─────────────────────────────────────────────────────────────────────────────

@app.route("/api/system/logs", methods=["GET"])
@login_required
def get_logs():
    limit = min(int(request.args.get("limit", 50)), 200)

    try:
        conn = get_db()
        with conn.cursor() as cur:
            cur.execute(
                "SELECT * FROM system_logs ORDER BY created_at DESC LIMIT %s",
                (limit,)
            )
            logs = cur.fetchall()
        conn.close()

        for log in logs:
            if isinstance(log.get("created_at"), datetime.datetime):
                log["created_at"] = log["created_at"].isoformat()

        return jsonify({"success": True, "logs": logs})

    except Exception as e:
        return jsonify({"success": False, "error": str(e)}), 500

# ─────────────────────────────────────────────────────────────────────────────
# STATS
# ─────────────────────────────────────────────────────────────────────────────

@app.route("/api/stats", methods=["GET"])
@login_required
def stats():
    try:
        conn = get_db()
        with conn.cursor() as cur:
            cur.execute("SELECT COUNT(*) AS total FROM invoices")
            total = cur.fetchone()["total"]

            cur.execute("SELECT COUNT(*) AS today FROM invoices WHERE DATE(created_at)=CURDATE()")
            today = cur.fetchone()["today"]

            cur.execute("SELECT SUM(total_amount) AS revenue FROM invoices")
            revenue = cur.fetchone()["revenue"] or 0

        conn.close()

        return jsonify({
            "success": True,
            "total_invoices": total,
            "today_invoices": today,
            "total_revenue": float(revenue)
        })

    except Exception as e:
        return jsonify({"success": False, "error": str(e)}), 500

@app.route("/api/licences", methods=["GET"])
@login_required
def get_licences():

    conn = get_db()

    with conn.cursor() as cur:
        cur.execute("""
            SELECT
                l.*,
                u.username,
                u.password_hash
            FROM licences l
            LEFT JOIN users u
            ON l.user_id = u.id
            ORDER BY l.id DESC
        """)

        licences = cur.fetchall()

    conn.close()

    return jsonify({
        "success": True,
        "licences": licences
    })


@app.route("/api/licences", methods=["POST"])
@login_required
def create_licence():

    data = request.get_json()

    conn = get_db()

    with conn.cursor() as cur:
        cur.execute("""
            INSERT INTO licences
            (
                company_name,
                licence_key,
                status,
                start_date,
                end_date,
                max_users
            )
            VALUES (%s,%s,%s,%s,%s,%s)
        """,
        (
            data["company_name"],
            data["licence_key"],
            data["status"],
            data["start_date"],
            data["end_date"],
            data["max_users"]
        ))

    conn.commit()
    conn.close()

    return jsonify({
        "success": True
    })


@app.route("/api/licences/<int:id>", methods=["DELETE"])
@login_required
def delete_licence(id):

    conn = get_db()

    with conn.cursor() as cur:
        cur.execute(
            "DELETE FROM licences WHERE id=%s",
            (id,)
        )

    conn.commit()
    conn.close()

    return jsonify({
        "success": True
    })


@app.route("/api/licences/<int:id>", methods=["PUT"])
@login_required
def update_licence(id):

    data = request.get_json()

    conn = get_db()

    with conn.cursor() as cur:
        cur.execute("""
            UPDATE licences
            SET
                company_name=%s,
                status=%s,
                end_date=%s,
                max_users=%s
            WHERE id=%s
        """,
        (
            data["company_name"],
            data["status"],
            data["end_date"],
            data["max_users"],
            id
        ))

    conn.commit()
    conn.close()

    return jsonify({
        "success": True
    })


@app.route("/api/debug/company-check")
def company_check():
    conn = get_db()
    with conn.cursor() as cur:
        cur.execute("SELECT COUNT(DISTINCT license_id) AS nb FROM users")
        nb = cur.fetchone()["nb"]

    return jsonify({
        "single_company": nb == 1,
        "nb_companies": nb
    })


# ─────────────────────────────────────────────────────────────────────────────
# À AJOUTER dans auth_server.py  (juste avant la ligne  if __name__ == "__main__")
# ─────────────────────────────────────────────────────────────────────────────

# Route page HTML (protégée admin)
@app.route("/users")
@login_required
def users_page():
    if session.get("role") != "admin":
        return "Accès refusé", 403
    return send_from_directory("static", "users.html")


# ── GET  /api/users  ── liste complète ───────────────────────────────────────
@app.route("/api/users", methods=["GET"])
@login_required
def get_users():
    if session.get("role") != "admin":
        return jsonify({"success": False, "error": "Droits insuffisants"}), 403

    conn = get_db()
    with conn.cursor() as cur:
        cur.execute("""
            SELECT
                u.id,
                u.username,
                u.email,
                u.fullname,
                u.role,
                u.is_active,
                u.license_id,
                u.last_login,
                u.created_at,
                l.company_name
            FROM users u
            LEFT JOIN licences l ON u.license_id = l.id
            ORDER BY u.id DESC
        """)
        users = cur.fetchall()
    conn.close()

    # Sérialiser les dates
    for u in users:
        for k in ("last_login", "created_at"):
            if isinstance(u.get(k), (datetime.datetime, datetime.date)):
                u[k] = u[k].isoformat()

    return jsonify({"success": True, "users": users})


# ── POST  /api/users  ── créer un utilisateur ────────────────────────────────
@app.route("/api/users", methods=["POST"])
@login_required
def create_user():
    if session.get("role") != "admin":
        return jsonify({"success": False, "error": "Droits insuffisants"}), 403

    data       = request.get_json() or {}
    username   = (data.get("username") or "").strip()
    email      = (data.get("email")    or "").strip()
    password   = data.get("password",  "")
    fullname   = (data.get("fullname") or "").strip()
    role       = data.get("role",      "operator")
    is_active  = int(data.get("is_active", 1))
    license_id = data.get("license_id") or None

    if not username or not email or not password:
        return jsonify({"success": False, "error": "username, email et password sont obligatoires"}), 400

    if role not in ("admin", "operator", "viewer"):
        return jsonify({"success": False, "error": "Rôle invalide"}), 400

    try:
        conn = get_db()
        with conn.cursor() as cur:
            cur.execute("""
                INSERT INTO users
                    (username, email, password_hash, fullname, role, is_active, license_id)
                VALUES (%s, %s, %s, %s, %s, %s, %s)
            """, (username, email, hash_password(password), fullname, role, is_active, license_id))
        conn.commit()
        conn.close()
        add_log("INFO", f"Utilisateur créé : {username} (par {session.get('username')})")
        return jsonify({"success": True})

    except pymysql.err.IntegrityError as e:
        if "username" in str(e):
            return jsonify({"success": False, "error": f"Le nom d'utilisateur « {username} » est déjà pris"}), 409
        if "email" in str(e):
            return jsonify({"success": False, "error": f"L'email « {email} » est déjà utilisé"}), 409
        return jsonify({"success": False, "error": str(e)}), 409

    except Exception as e:
        return jsonify({"success": False, "error": str(e)}), 500


# ── PUT  /api/users/<id>  ── modifier un utilisateur ─────────────────────────
@app.route("/api/users/<int:user_id>", methods=["PUT"])
@login_required
def update_user(user_id):
    if session.get("role") != "admin":
        return jsonify({"success": False, "error": "Droits insuffisants"}), 403

    data       = request.get_json() or {}
    username   = (data.get("username") or "").strip()
    email      = (data.get("email")    or "").strip()
    fullname   = (data.get("fullname") or "").strip()
    role       = data.get("role",      "operator")
    is_active  = int(data.get("is_active", 1))
    license_id = data.get("license_id") or None
    password   = data.get("password",  "")          # optionnel

    if not username or not email:
        return jsonify({"success": False, "error": "username et email sont obligatoires"}), 400

    if role not in ("admin", "operator", "viewer"):
        return jsonify({"success": False, "error": "Rôle invalide"}), 400

    try:
        conn = get_db()
        with conn.cursor() as cur:
            if password:
                cur.execute("""
                    UPDATE users
                    SET username=%s, email=%s, fullname=%s, role=%s,
                        is_active=%s, license_id=%s, password_hash=%s
                    WHERE id=%s
                """, (username, email, fullname, role, is_active, license_id, hash_password(password), user_id))
            else:
                cur.execute("""
                    UPDATE users
                    SET username=%s, email=%s, fullname=%s, role=%s,
                        is_active=%s, license_id=%s
                    WHERE id=%s
                """, (username, email, fullname, role, is_active, license_id, user_id))
        conn.commit()
        conn.close()
        add_log("INFO", f"Utilisateur modifié : {username} (par {session.get('username')})")
        return jsonify({"success": True})

    except pymysql.err.IntegrityError as e:
        if "username" in str(e):
            return jsonify({"success": False, "error": f"Le nom d'utilisateur « {username} » est déjà pris"}), 409
        if "email" in str(e):
            return jsonify({"success": False, "error": f"L'email « {email} » est déjà utilisé"}), 409
        return jsonify({"success": False, "error": str(e)}), 409

    except Exception as e:
        return jsonify({"success": False, "error": str(e)}), 500


# ── DELETE  /api/users/<id>  ── supprimer un utilisateur ─────────────────────
@app.route("/api/users/<int:user_id>", methods=["DELETE"])
@login_required
def delete_user(user_id):
    if session.get("role") != "admin":
        return jsonify({"success": False, "error": "Droits insuffisants"}), 403

    # Empêcher la suppression de son propre compte
    if session.get("user_id") == user_id:
        return jsonify({"success": False, "error": "Vous ne pouvez pas supprimer votre propre compte"}), 400

    try:
        conn = get_db()
        with conn.cursor() as cur:
            cur.execute("SELECT username FROM users WHERE id=%s", (user_id,))
            row = cur.fetchone()
            if not row:
                return jsonify({"success": False, "error": "Utilisateur introuvable"}), 404
            cur.execute("DELETE FROM users WHERE id=%s", (user_id,))
        conn.commit()
        conn.close()
        add_log("INFO", f"Utilisateur supprimé : {row['username']} (par {session.get('username')})")
        return jsonify({"success": True})

    except Exception as e:
        return jsonify({"success": False, "error": str(e)}), 500


@app.route("/api/licences/<int:id>/renew", methods=["POST"])
@login_required
def renew_licence(id):
    data = request.get_json() or {}
    months = int(data.get("months", 12))   # durée en mois (défaut 12)
    notes  = data.get("notes", "")

    conn = get_db()
    with conn.cursor() as cur:
        # Récupérer la licence
        cur.execute("SELECT * FROM licences WHERE id=%s", (id,))
        lic = cur.fetchone()
        if not lic:
            conn.close()
            return jsonify({"success": False, "error": "Licence introuvable"}), 404

        # Date de base = end_date actuelle (ou aujourd'hui si déjà expirée)
        base = lic["end_date"]
        if isinstance(base, str):
            base = datetime.date.fromisoformat(base)
        if base < datetime.date.today():
            base = datetime.date.today()   # on repart d'aujourd'hui si expirée

        # Calculer la nouvelle end_date
        month = base.month - 1 + months
        new_end = base.replace(
            year  = base.year + month // 12,
            month = month % 12 + 1,
            day   = base.day
        )

        old_end = lic["end_date"]

        # Mettre à jour la licence
        cur.execute("""
            UPDATE licences
            SET end_date=%s, status='active'
            WHERE id=%s
        """, (new_end, id))

        # Enregistrer dans l'historique
        cur.execute("""
            INSERT INTO licence_renewals
                (licence_id, old_end_date, new_end_date, renewed_by, notes)
            VALUES (%s, %s, %s, %s, %s)
        """, (id, old_end, new_end, session.get("username"), notes))

    conn.commit()
    conn.close()

    add_log("INFO", f"Licence #{id} renouvelée jusqu'au {new_end} par {session.get('username')}")
    return jsonify({
        "success": True,
        "new_end_date": str(new_end),
        "old_end_date": str(old_end)
    })


@app.route("/api/licences/<int:id>/renewals", methods=["GET"])
@login_required
def get_renewals(id):
    conn = get_db()
    with conn.cursor() as cur:
        cur.execute("""
            SELECT * FROM licence_renewals
            WHERE licence_id=%s
            ORDER BY renewed_at DESC
        """, (id,))
        rows = cur.fetchall()
    conn.close()
    for r in rows:
        if isinstance(r.get("renewed_at"), datetime.datetime):
            r["renewed_at"] = r["renewed_at"].isoformat()
        if isinstance(r.get("old_end_date"), datetime.date):
            r["old_end_date"] = r["old_end_date"].isoformat()
        if isinstance(r.get("new_end_date"), datetime.date):
            r["new_end_date"] = r["new_end_date"].isoformat()
    return jsonify({"success": True, "renewals": rows})
# ─────────────────────────────────────────────────────────────────────────────

if __name__ == "__main__":
    app.run(
        host="0.0.0.0",
        port=5000,
        debug=True
    )