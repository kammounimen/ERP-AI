"""
authentication/views.py — ERP-AI Authentication & System Control
Migration Flask → Django : toutes les routes de auth_server.py converties.

CORRESPONDANCES FLASK → DJANGO :
  request.get_json()        →  json.loads(request.body)
  session["user_id"]        →  request.session["user_id"]
  session.get("role")       →  request.session.get("role")
  session.clear()           →  request.session.flush()
  return jsonify({})        →  return JsonResponse({})
  return jsonify({}), 403   →  return JsonResponse({}, status=403)
  pymysql.connect()         →  connection.cursor()  (ORM Django)
  send_from_directory()     →  FileResponse / TemplateResponse
"""

import json
import hashlib
import datetime
import os
import platform
import jwt as pyjwt
from django.http import JsonResponse, FileResponse, HttpResponse
from django.views.decorators.csrf import csrf_exempt
from django.views.decorators.http import require_http_methods
from django.db import connection
from django.conf import settings as django_settings

from .decorators import login_required, admin_required

"""
EXTRAIT À AJOUTER dans authentication/views.py
------------------------------------------------
1. Ajoute l'import en haut du fichier (avec les autres imports) :

    import jwt as pyjwt

2. Ajoute cette fonction n'importe où dans le fichier (par exemple juste
   après la fonction logout()) :
"""

@login_required
def erp_token(request):
    """
    GET /api/auth/erp-token

    Génère un token JWT signé à partir de la session Django active.
    Ce token sera passé en paramètre d'URL vers Laminas (?token=...)
    pour que l'utilisateur n'ait pas à se reconnecter (SSO).

    Le token est volontairement éphémère (60s) : il ne sert qu'au moment
    de la redirection, pas à maintenir une session longue.
    """
    import datetime as _dt

    payload = {
        "user_id":  request.session.get("user_id"),
        "username": request.session.get("username"),
        "role":     request.session.get("role"),
        "iat":      _dt.datetime.utcnow(),
        "exp":      _dt.datetime.utcnow() + _dt.timedelta(
            seconds=django_settings.JWT_EXPIRATION_SECONDS
        ),
    }

    token = pyjwt.encode(
        payload,
        django_settings.JWT_SECRET,
        algorithm=django_settings.JWT_ALGORITHM,
    )

    return JsonResponse({"success": True, "token": token})
# ─────────────────────────────────────────────────────────────────────────────
# HELPERS  (identiques à Flask, adaptés Django)
# ─────────────────────────────────────────────────────────────────────────────

def hash_password(password: str) -> str:
    """Identique à Flask : SHA-256"""
    return hashlib.sha256(password.encode()).hexdigest()


def add_log(level: str, message: str):
    """
    Remplace la fonction add_log Flask.
    Utilise connection.cursor() de Django au lieu de pymysql.connect()
    """
    try:
        with connection.cursor() as cur:
            cur.execute(
                "INSERT INTO system_logs (level, message) VALUES (%s, %s)",
                [level, message]
            )
    except Exception:
        pass


def fetch_one(query: str, params: list) -> dict | None:
    """Helper : exécute une requête et retourne un dict ou None."""
    with connection.cursor() as cur:
        cur.execute(query, params)
        row = cur.fetchone()
        if row is None:
            return None
        cols = [col[0] for col in cur.description]
        return dict(zip(cols, row))


def fetch_all(query: str, params: list = []) -> list[dict]:
    """Helper : exécute une requête et retourne une liste de dicts."""
    with connection.cursor() as cur:
        cur.execute(query, params)
        cols = [col[0] for col in cur.description]
        return [dict(zip(cols, row)) for row in cur.fetchall()]


def serialize_dates(obj: dict) -> dict:
    """Convertit les dates/datetime en string ISO pour JSON."""
    for key, val in obj.items():
        if isinstance(val, (datetime.datetime, datetime.date)):
            obj[key] = val.isoformat()
    return obj


# ─────────────────────────────────────────────────────────────────────────────
# PAGES HTML STATIQUES
# Remplace : send_from_directory("static", "index.html")
# ─────────────────────────────────────────────────────────────────────────────

def index(request):
    """Route : GET /"""
    path = django_settings.BASE_DIR / "static" / "index.html"
    return FileResponse(open(path, "rb"), content_type="text/html")


@login_required
def licences_page(request):
    """Route : GET /licences  (admin seulement)"""
    if request.session.get("role") != "admin":
        return HttpResponse("Accès refusé", status=403)
    path = django_settings.BASE_DIR / "static" / "licences.html"
    return FileResponse(open(path, "rb"), content_type="text/html")


@login_required
def users_page(request):
    """Route : GET /users  (admin seulement)"""
    if request.session.get("role") != "admin":
        return HttpResponse("Accès refusé", status=403)
    path = django_settings.BASE_DIR / "static" / "users.html"
    return FileResponse(open(path, "rb"), content_type="text/html")


# ─────────────────────────────────────────────────────────────────────────────
# AUTH — Login / Logout / Session
# ─────────────────────────────────────────────────────────────────────────────

@csrf_exempt
def login(request):
    """
    POST /api/auth/login
    Remplace : @app.route("/api/auth/login", methods=["POST"])
    """
    if request.method != "POST":
        return JsonResponse({"error": "Méthode non autorisée"}, status=405)

    try:
        data = json.loads(request.body)
    except json.JSONDecodeError:
        return JsonResponse({"success": False, "error": "JSON invalide"}, status=400)

    username = (data.get("username") or "").strip()
    password = data.get("password", "")

    if not username or not password:
        return JsonResponse(
            {"success": False, "error": "Tous les champs sont requis"},
            status=400
        )

    # Chercher l'utilisateur (username OU email)
    user = fetch_one(
        "SELECT * FROM users WHERE (username=%s OR email=%s) AND is_active=1",
        [username, username]
    )

    if not user or user["password_hash"] != hash_password(password):
        add_log("WARNING", f"Échec login pour: {username}")
        return JsonResponse(
            {"success": False, "error": "Identifiants incorrects"},
            status=401
        )

    # Vérification licence liée à l'utilisateur
    licence = fetch_one(
        """
        SELECT l.*
        FROM licences l
        JOIN users u ON u.license_id = l.id
        WHERE u.id = %s
        """,
        [user["id"]]
    )

    if not licence:
        return JsonResponse(
            {"success": False, "error": "Aucune licence associée à cet utilisateur"},
            status=403
        )

    if licence["status"] != "active":
        return JsonResponse(
            {"success": False, "error": "Licence bloquée ou expirée"},
            status=403
        )

    end_date = licence["end_date"]
    if isinstance(end_date, str):
        end_date = datetime.date.fromisoformat(end_date)
    if end_date < datetime.date.today():
        return JsonResponse(
            {"success": False, "error": "Licence expirée"},
            status=403
        )

    # Créer la session Django (remplace session["user_id"] = ... de Flask)
    request.session["user_id"]  = user["id"]
    request.session["username"] = user["username"]
    request.session["role"]     = user["role"]

    add_log("INFO", f"Connexion réussie : {username}")

    return JsonResponse({
        "success": True,
        "user": {
            "id":       user["id"],
            "username": user["username"],
            "email":    user["email"],
            "role":     user["role"],
            "fullname": user.get("fullname") or username,
        }
    })


@csrf_exempt
@login_required
def logout(request):
    """
    POST /api/auth/logout
    Remplace : session.clear()  →  request.session.flush()
    """
    if request.method != "POST":
        return JsonResponse({"error": "Méthode non autorisée"}, status=405)

    username = request.session.get("username", "?")
    request.session.flush()   # équivalent de session.clear() en Flask
    add_log("INFO", f"Déconnexion : {username}")
    return JsonResponse({"success": True})


@login_required
def me(request):
    """GET /api/auth/me"""
    return JsonResponse({
        "success":  True,
        "user_id":  request.session["user_id"],
        "username": request.session["username"],
        "role":     request.session["role"],
    })


# ─────────────────────────────────────────────────────────────────────────────
# SYSTEM STATUS
# ─────────────────────────────────────────────────────────────────────────────

@login_required
def system_status(request):
    """GET /api/system/status"""
    import urllib.request
    import psutil

    api_url = os.getenv("AGENT_API_URL", "http://localhost:8000")

    # DB check
    db_ok = False
    try:
        with connection.cursor() as cur:
            cur.execute("SELECT 1")
        db_ok = True
    except Exception:
        pass

    # API check
    api_ok = False
    try:
        urllib.request.urlopen(f"{api_url}/health", timeout=2)
        api_ok = True
    except Exception:
        pass

    # Statistiques système
    try:
        cpu  = psutil.cpu_percent(interval=0.2)
        mem  = psutil.virtual_memory().percent
        disk = psutil.disk_usage("/").percent
    except Exception:
        cpu = mem = disk = 0

    return JsonResponse({
        "success": True,
        "server": {
            "status":    "online",
            "os":        platform.system() + " " + platform.release(),
            "cpu":       cpu,
            "memory":    mem,
            "disk":      disk,
            "timestamp": datetime.datetime.now().isoformat(),
        },
        "database": {"status": "online" if db_ok else "offline"},
        "api_ia":   {"status": "online" if api_ok else "offline", "url": api_url},
    })


# ─────────────────────────────────────────────────────────────────────────────
# SYSTEM CONTROL
# ─────────────────────────────────────────────────────────────────────────────

@csrf_exempt
@login_required
def system_control(request):
    """POST /api/system/control"""
    if request.method != "POST":
        return JsonResponse({"error": "Méthode non autorisée"}, status=405)

    if request.session.get("role") not in ("admin", "superadmin"):
        return JsonResponse({"success": False, "error": "Droits insuffisants"}, status=403)

    data     = json.loads(request.body or "{}")
    action   = data.get("action", "")
    username = request.session.get("username", "?")

    messages = {
        "start":   "Système démarré",
        "stop":    "Système arrêté",
        "restart": "API redémarrée",
    }

    if action not in messages:
        return JsonResponse({"success": False, "error": "Action inconnue"}, status=400)

    add_log("INFO", f"{messages[action]} par {username}")
    return JsonResponse({"success": True, "message": messages[action]})


# ─────────────────────────────────────────────────────────────────────────────
# LOGS
# ─────────────────────────────────────────────────────────────────────────────

@login_required
def get_logs(request):
    """GET /api/system/logs"""
    limit = min(int(request.GET.get("limit", 50)), 200)

    try:
        logs = fetch_all(
            "SELECT * FROM system_logs ORDER BY created_at DESC LIMIT %s",
            [limit]
        )
        for log in logs:
            serialize_dates(log)
        return JsonResponse({"success": True, "logs": logs})
    except Exception as e:
        return JsonResponse({"success": False, "error": str(e)}, status=500)


# ─────────────────────────────────────────────────────────────────────────────
# STATS
# ─────────────────────────────────────────────────────────────────────────────

@login_required
def stats(request):
    """GET /api/stats"""
    try:
        total   = fetch_one("SELECT COUNT(*) AS total FROM invoices", [])["total"]
        today   = fetch_one("SELECT COUNT(*) AS today FROM invoices WHERE DATE(created_at)=CURDATE()", [])["today"]
        revenue = fetch_one("SELECT SUM(total_amount) AS revenue FROM invoices", [])["revenue"] or 0

        return JsonResponse({
            "success":        True,
            "total_invoices": total,
            "today_invoices": today,
            "total_revenue":  float(revenue),
        })
    except Exception as e:
        return JsonResponse({"success": False, "error": str(e)}, status=500)


# ─────────────────────────────────────────────────────────────────────────────
# LICENCES — CRUD complet
# ─────────────────────────────────────────────────────────────────────────────

@csrf_exempt
@login_required
def licences(request):
    """
    GET  /api/licences  → liste
    POST /api/licences  → créer
    """
    if request.method == "GET":
        rows = fetch_all("""
            SELECT l.*, u.username, u.password_hash
            FROM licences l
            LEFT JOIN users u ON l.user_id = u.id
            ORDER BY l.id DESC
        """)
        for r in rows:
            serialize_dates(r)
        return JsonResponse({"success": True, "licences": rows})

    if request.method == "POST":
        data = json.loads(request.body)
        with connection.cursor() as cur:
            cur.execute("""
                INSERT INTO licences
                    (company_name, licence_key, status, start_date, end_date, max_users)
                VALUES (%s, %s, %s, %s, %s, %s)
            """, [
                data["company_name"],
                data["licence_key"],
                data["status"],
                data["start_date"],
                data["end_date"],
                data["max_users"],
            ])
        return JsonResponse({"success": True})

    return JsonResponse({"error": "Méthode non autorisée"}, status=405)


@csrf_exempt
@login_required
def licence_detail(request, id):
    """
    PUT    /api/licences/<id>  → modifier
    DELETE /api/licences/<id>  → supprimer
    """
    if request.method == "PUT":
        data = json.loads(request.body)
        with connection.cursor() as cur:
            cur.execute("""
                UPDATE licences
                SET company_name=%s, status=%s, end_date=%s, max_users=%s
                WHERE id=%s
            """, [
                data["company_name"],
                data["status"],
                data["end_date"],
                data["max_users"],
                id,
            ])
        return JsonResponse({"success": True})

    if request.method == "DELETE":
        with connection.cursor() as cur:
            cur.execute("DELETE FROM licences WHERE id=%s", [id])
        return JsonResponse({"success": True})

    return JsonResponse({"error": "Méthode non autorisée"}, status=405)


@csrf_exempt
@login_required
def renew_licence(request, id):
    """POST /api/licences/<id>/renew"""
    if request.method != "POST":
        return JsonResponse({"error": "Méthode non autorisée"}, status=405)

    data   = json.loads(request.body or "{}")
    months = int(data.get("months", 12))
    notes  = data.get("notes", "")

    lic = fetch_one("SELECT * FROM licences WHERE id=%s", [id])
    if not lic:
        return JsonResponse({"success": False, "error": "Licence introuvable"}, status=404)

    base = lic["end_date"]
    if isinstance(base, str):
        base = datetime.date.fromisoformat(base)
    if base < datetime.date.today():
        base = datetime.date.today()

    month   = base.month - 1 + months
    new_end = base.replace(
        year  = base.year + month // 12,
        month = month % 12 + 1,
        day   = base.day,
    )
    old_end = lic["end_date"]

    with connection.cursor() as cur:
        cur.execute(
            "UPDATE licences SET end_date=%s, status='active' WHERE id=%s",
            [new_end, id]
        )
        cur.execute("""
            INSERT INTO licence_renewals
                (licence_id, old_end_date, new_end_date, renewed_by, notes)
            VALUES (%s, %s, %s, %s, %s)
        """, [id, old_end, new_end, request.session.get("username"), notes])

    add_log("INFO", f"Licence #{id} renouvelée jusqu'au {new_end} par {request.session.get('username')}")
    return JsonResponse({
        "success":      True,
        "new_end_date": str(new_end),
        "old_end_date": str(old_end),
    })


@login_required
def get_renewals(request, id):
    """GET /api/licences/<id>/renewals"""
    rows = fetch_all(
        "SELECT * FROM licence_renewals WHERE licence_id=%s ORDER BY renewed_at DESC",
        [id]
    )
    for r in rows:
        serialize_dates(r)
    return JsonResponse({"success": True, "renewals": rows})


# ─────────────────────────────────────────────────────────────────────────────
# USERS — CRUD complet
# ─────────────────────────────────────────────────────────────────────────────

@csrf_exempt
@login_required
def users(request):
    """
    GET  /api/users  → liste (admin)
    POST /api/users  → créer (admin)
    """
    if request.session.get("role") != "admin":
        return JsonResponse({"success": False, "error": "Droits insuffisants"}, status=403)

    if request.method == "GET":
        rows = fetch_all("""
            SELECT u.id, u.username, u.email, u.fullname, u.role,
                   u.is_active, u.license_id, u.last_login, u.created_at,
                   l.company_name
            FROM users u
            LEFT JOIN licences l ON u.license_id = l.id
            ORDER BY u.id DESC
        """)
        for u in rows:
            serialize_dates(u)
        return JsonResponse({"success": True, "users": rows})

    if request.method == "POST":
        data       = json.loads(request.body or "{}")
        username   = (data.get("username") or "").strip()
        email      = (data.get("email")    or "").strip()
        password   = data.get("password",  "")
        fullname   = (data.get("fullname") or "").strip()
        role       = data.get("role",      "operator")
        is_active  = int(data.get("is_active", 1))
        license_id = data.get("license_id") or None

        if not username or not email or not password:
            return JsonResponse(
                {"success": False, "error": "username, email et password sont obligatoires"},
                status=400
            )
        if role not in ("admin", "operator", "viewer"):
            return JsonResponse({"success": False, "error": "Rôle invalide"}, status=400)

        try:
            with connection.cursor() as cur:
                cur.execute("""
                    INSERT INTO users
                        (username, email, password_hash, fullname, role, is_active, license_id)
                    VALUES (%s, %s, %s, %s, %s, %s, %s)
                """, [username, email, hash_password(password), fullname, role, is_active, license_id])
            add_log("INFO", f"Utilisateur créé : {username} (par {request.session.get('username')})")
            return JsonResponse({"success": True})

        except Exception as e:
            err = str(e)
            if "username" in err:
                return JsonResponse({"success": False, "error": f"Username « {username} » déjà pris"}, status=409)
            if "email" in err:
                return JsonResponse({"success": False, "error": f"Email « {email} » déjà utilisé"}, status=409)
            return JsonResponse({"success": False, "error": err}, status=500)

    return JsonResponse({"error": "Méthode non autorisée"}, status=405)


@csrf_exempt
@login_required
def user_detail(request, user_id):
    """
    PUT    /api/users/<user_id>  → modifier
    DELETE /api/users/<user_id>  → supprimer
    """
    if request.session.get("role") != "admin":
        return JsonResponse({"success": False, "error": "Droits insuffisants"}, status=403)

    if request.method == "PUT":
        data       = json.loads(request.body or "{}")
        username   = (data.get("username") or "").strip()
        email      = (data.get("email")    or "").strip()
        fullname   = (data.get("fullname") or "").strip()
        role       = data.get("role",      "operator")
        is_active  = int(data.get("is_active", 1))
        license_id = data.get("license_id") or None
        password   = data.get("password",  "")

        if not username or not email:
            return JsonResponse(
                {"success": False, "error": "username et email sont obligatoires"},
                status=400
            )
        if role not in ("admin", "operator", "viewer"):
            return JsonResponse({"success": False, "error": "Rôle invalide"}, status=400)

        try:
            with connection.cursor() as cur:
                if password:
                    cur.execute("""
                        UPDATE users
                        SET username=%s, email=%s, fullname=%s, role=%s,
                            is_active=%s, license_id=%s, password_hash=%s
                        WHERE id=%s
                    """, [username, email, fullname, role, is_active, license_id, hash_password(password), user_id])
                else:
                    cur.execute("""
                        UPDATE users
                        SET username=%s, email=%s, fullname=%s, role=%s,
                            is_active=%s, license_id=%s
                        WHERE id=%s
                    """, [username, email, fullname, role, is_active, license_id, user_id])
            add_log("INFO", f"Utilisateur modifié : {username} (par {request.session.get('username')})")
            return JsonResponse({"success": True})

        except Exception as e:
            err = str(e)
            if "username" in err:
                return JsonResponse({"success": False, "error": f"Username « {username} » déjà pris"}, status=409)
            if "email" in err:
                return JsonResponse({"success": False, "error": f"Email « {email} » déjà utilisé"}, status=409)
            return JsonResponse({"success": False, "error": err}, status=500)

    if request.method == "DELETE":
        if request.session.get("user_id") == user_id:
            return JsonResponse(
                {"success": False, "error": "Vous ne pouvez pas supprimer votre propre compte"},
                status=400
            )
        row = fetch_one("SELECT username FROM users WHERE id=%s", [user_id])
        if not row:
            return JsonResponse({"success": False, "error": "Utilisateur introuvable"}, status=404)

        with connection.cursor() as cur:
            cur.execute("DELETE FROM users WHERE id=%s", [user_id])
        add_log("INFO", f"Utilisateur supprimé : {row['username']} (par {request.session.get('username')})")
        return JsonResponse({"success": True})

    return JsonResponse({"error": "Méthode non autorisée"}, status=405)


# ─────────────────────────────────────────────────────────────────────────────
# VERIFY TOKEN & UTILITAIRES
# ─────────────────────────────────────────────────────────────────────────────

def verify_token(request):
    """GET /api/verify-token"""
    auth  = request.headers.get("Authorization", "")
    token = auth.replace("Bearer ", "").strip()

    if not token:
        return JsonResponse({"success": False, "error": "Token manquant"}, status=401)

    lic = fetch_one(
        "SELECT * FROM licences WHERE licence_key=%s AND status='active' AND end_date >= CURDATE()",
        [token]
    )
    if not lic:
        return JsonResponse({"success": False, "error": "Token invalide ou licence expirée"}, status=403)

    serialize_dates(lic)
    return JsonResponse({"success": True, "licence": lic, "company_name": lic.get("company_name")})


def company_check(request):
    """GET /api/debug/company-check"""
    row = fetch_one("SELECT COUNT(DISTINCT license_id) AS nb FROM users", [])
    nb  = row["nb"] if row else 0
    return JsonResponse({"single_company": nb == 1, "nb_companies": nb})


def ping(request):
    """GET /ping"""
    return JsonResponse({"message": "Django OK"})
