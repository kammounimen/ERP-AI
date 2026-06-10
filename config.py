import os
from dotenv import load_dotenv

load_dotenv()

DB_CONFIG = {
    "host":     os.getenv("DB_HOST", "localhost"),
    "user":     os.getenv("DB_USER", "root"),
    "password": os.getenv("DB_PASSWORD", ""),       # ← plus jamais en dur ici !
    "database": os.getenv("DB_NAME", "invoices_db"),
    "charset":  "utf8mb4"
}

# --- Clé Mistral (à mettre dans .env) ---
MISTRAL_API_KEY = os.getenv("MISTRAL_API_KEY", "")

# Modèle Mistral recommandé pour l'extraction de factures
MISTRAL_MODEL = "mistral-large-latest"