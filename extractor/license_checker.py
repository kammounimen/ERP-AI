"""
license_checker.py
-------------------
Vérifie la validité d'une licence_key auprès de la base de l'éditeur
(invoices_db.licences), qui reste sur le serveur privé de la société.

Ce module est appelé par l'API avant chaque action IA (extraction,
recherche) demandée depuis l'ERP Laminas du client.
"""

import datetime
import pymysql
import pymysql.cursors
from config import LICENSE_DB_CONFIG


def _get_license_connection():
    """Connexion dédiée à la base des licences (invoices_db, côté éditeur)."""
    return pymysql.connect(**LICENSE_DB_CONFIG)


def check_license(licence_key: str) -> dict:
    """
    Vérifie si une licence_key est valide.

    Une licence est considérée VALIDE si :
    - elle existe dans la table `licences`
    - son `status` est 'active'
    - sa `end_date` n'est pas dépassée (date du jour <= end_date)

    Retourne
    --------
    dict {
        'valid': bool,
        'reason': str | None,        # raison de l'invalidité, si applicable
        'company_name': str | None,
        'end_date': str | None,
        'max_users': int | None,
    }
    """
    if not licence_key or not licence_key.strip():
        return {"valid": False, "reason": "Aucune clé de licence fournie."}

    conn = _get_license_connection()
    try:
        with conn.cursor(pymysql.cursors.DictCursor) as cur:
            cur.execute(
                "SELECT * FROM licences WHERE licence_key = %s",
                (licence_key.strip(),)
            )
            licence = cur.fetchone()

        if not licence:
            return {"valid": False, "reason": "Licence introuvable."}

        if licence["status"] != "active":
            return {
                "valid": False,
                "reason": f"Licence {licence['status']}.",
                "company_name": licence["company_name"],
            }

        today = datetime.date.today()
        end_date = licence["end_date"]
        if isinstance(end_date, datetime.datetime):
            end_date = end_date.date()

        if end_date and today > end_date:
            return {
                "valid": False,
                "reason": "Licence expirée.",
                "company_name": licence["company_name"],
                "end_date": str(end_date),
            }

        return {
            "valid": True,
            "reason": None,
            "company_name": licence["company_name"],
            "end_date": str(end_date) if end_date else None,
            "max_users": licence["max_users"],
        }

    finally:
        conn.close()