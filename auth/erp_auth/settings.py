"""
erp_auth/settings.py — Configuration Django
Remplace toute la config Flask de auth_server.py
"""

import os
from pathlib import Path
from dotenv import load_dotenv

load_dotenv()

BASE_DIR = Path(__file__).resolve().parent.parent

# ── Sécurité ──────────────────────────────────────────────────────────────────
SECRET_KEY = os.getenv("DJANGO_SECRET", "changez-moi-en-production-svp")
DEBUG = True
ALLOWED_HOSTS = ["*"]

# ── Applications installées ───────────────────────────────────────────────────
INSTALLED_APPS = [
    "django.contrib.contenttypes",
    "django.contrib.sessions",        # gestion des sessions
    "django.contrib.staticfiles",
    "rest_framework",                 # Django REST Framework
    "corsheaders",                    # CORS (remplace flask-cors)
    "authentication",                 # notre application
]

# ── Middleware ─────────────────────────────────────────────────────────────────
MIDDLEWARE = [
    "corsheaders.middleware.CorsMiddleware",          # doit être EN PREMIER
    "django.middleware.common.CommonMiddleware",
    "django.contrib.sessions.middleware.SessionMiddleware",
]

# ── Base de données MySQL ──────────────────────────────────────────────────────
# Remplace DB_CONFIG + pymysql.connect() de Flask
# On se connecte à ta base existante invoices_db — Django ne recrée rien
DATABASES = {
    "default": {
        "ENGINE": "django.db.backends.mysql",
        "NAME":     os.getenv("DB_NAME",     "invoices_db"),
        "USER":     os.getenv("DB_USER",     "root"),
        "PASSWORD": os.getenv("DB_PASSWORD", ""),
        "HOST":     os.getenv("DB_HOST",     "localhost"),
        "PORT":     "3306",
        "OPTIONS": {
            "charset": "utf8mb4",
            "init_command": "SET sql_mode='STRICT_TRANS_TABLES'",
        },
    }
}

# ── Sessions (remplace Flask session + secret_key) ────────────────────────────
SESSION_ENGINE         = "django.contrib.sessions.backends.db"
SESSION_COOKIE_NAME    = "erp_session"
SESSION_COOKIE_HTTPONLY = True
SESSION_COOKIE_SAMESITE = "Lax"
SESSION_COOKIE_AGE     = 86400   # 24 heures

# ── CORS (remplace CORS(app, supports_credentials=True)) ─────────────────────
CORS_ALLOW_CREDENTIALS = True
CORS_ALLOWED_ORIGINS = [
    "http://localhost:5500",
    "http://127.0.0.1:5500",
    "http://localhost:3000",
    "http://127.0.0.1:3000",
]

# ── Fichiers statiques (tes HTML index, users, licences) ─────────────────────
STATIC_URL = "/static/"
STATICFILES_DIRS = [BASE_DIR / "static"]

# ── URLs ───────────────────────────────────────────────────────────────────────
ROOT_URLCONF = "erp_auth.urls"

# ── Templates (pour servir les HTML) ─────────────────────────────────────────
TEMPLATES = [
    {
        "BACKEND": "django.template.backends.django.DjangoTemplates",
        "DIRS": [BASE_DIR / "static"],
        "APP_DIRS": False,
        "OPTIONS": {"context_processors": []},
    },
]

DEFAULT_AUTO_FIELD = "django.db.models.BigAutoField"
# ── JWT partagé pour le SSO Django ↔ Laminas ──────────────────────────────────
# Cette clé doit être EXACTEMENT identique côté Laminas (config/autoload/jwt.global.php)
JWT_SECRET = os.getenv("JWT_SECRET", "erp-ai-shared-secret-2026-change-moi-en-prod")
JWT_ALGORITHM = "HS256"
JWT_EXPIRATION_SECONDS = 60  # le token n'est valide que 60s — juste le temps de la redirection