import os
from dotenv import load_dotenv

load_dotenv()

# ── Base "FACTURES" du client (erp_client_db) ──────────────────────────────
# Contient les factures du client + son propre login Laminas.
DB_CONFIG = {
    "host":     os.getenv("DB_HOST", "localhost"),
    "user":     os.getenv("DB_USER", "root"),
    "password": os.getenv("DB_PASSWORD", ""),
    "database": os.getenv("DB_NAME", "erp_client_db"),   # ← changé de invoices_db
    "charset":  "utf8mb4"
}

# ── Base "LICENCES" de l'éditeur (invoices_db) ──────────────────────────────
# Reste sur le serveur privé de l'éditeur. Sert UNIQUEMENT à vérifier
# la validité d'une licence_key envoyée par Laminas avant un scan/recherche.
LICENSE_DB_CONFIG = {
    "host":     os.getenv("LICENSE_DB_HOST", "localhost"),
    "user":     os.getenv("LICENSE_DB_USER", "root"),
    "password": os.getenv("LICENSE_DB_PASSWORD", ""),
    "database": os.getenv("LICENSE_DB_NAME", "invoices_db"),
    "charset":  "utf8mb4"
}

# --- Clé Mistral (à mettre dans .env) ---
MISTRAL_API_KEY = os.getenv("MISTRAL_API_KEY", "")

# Modèle Mistral recommandé pour l'extraction de factures
MISTRAL_MODEL = "mistral-large-latest"