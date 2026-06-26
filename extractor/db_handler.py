"""
db_handler.py
-------------
Gestion de la connexion et des opérations sur la base de données MySQL.
"""

import pymysql
import pymysql.cursors
from config import DB_CONFIG


def get_connection():
    """Retourne une connexion MySQL active."""
    return pymysql.connect(**DB_CONFIG)


# ---------------------------------------------------------------------------
# Sauvegarde de facture
# ---------------------------------------------------------------------------

def save_invoice(data: dict, raw_text: str = "", source_file: str = "", created_by: int | None = None) -> int:
    """Sauvegarde la facture et ses lignes dans la BDD. Retourne l'ID."""
    conn = get_connection()
    try:
        with conn.cursor() as cursor:
            sql = """
                INSERT INTO invoices (
                    created_by,
                    invoice_number, invoice_date, due_date,
                    vendor_name, vendor_address, vendor_email, vendor_phone,
                    client_name, client_address,
                    subtotal, tax_rate, tax_amount, total_amount,
                    currency, payment_method, notes,
                    raw_text, source_file
                ) VALUES (
                    %(created_by)s,
                    %(invoice_number)s, %(invoice_date)s, %(due_date)s,
                    %(vendor_name)s, %(vendor_address)s, %(vendor_email)s, %(vendor_phone)s,
                    %(client_name)s, %(client_address)s,
                    %(subtotal)s, %(tax_rate)s, %(tax_amount)s, %(total_amount)s,
                    %(currency)s, %(payment_method)s, %(notes)s,
                    %(raw_text)s, %(source_file)s
                )
            """
            params = {
                "created_by":     created_by,
                "invoice_number": data.get("invoice_number"),
                "invoice_date":   data.get("invoice_date"),
                "due_date":       data.get("due_date"),
                "vendor_name":    data.get("vendor_name"),
                "vendor_address": data.get("vendor_address"),
                "vendor_email":   data.get("vendor_email"),
                "vendor_phone":   data.get("vendor_phone"),
                "client_name":    data.get("client_name"),
                "client_address": data.get("client_address"),
                "subtotal":       data.get("subtotal"),
                "tax_rate":       data.get("tax_rate"),
                "tax_amount":     data.get("tax_amount"),
                "total_amount":   data.get("total_amount"),
                "currency":       data.get("currency", "TND"),
                "payment_method": data.get("payment_method"),
                "notes":          data.get("notes"),
                "raw_text":       raw_text,
                "source_file":    source_file,
            }
            cursor.execute(sql, params)
            invoice_id = cursor.lastrowid

            items = data.get("items", [])
            if items:
                items_sql = """
                    INSERT INTO invoice_items
                    (invoice_id, description, quantity, unit_price, total_price)
                    VALUES (%s, %s, %s, %s, %s)
                """
                for item in items:
                    cursor.execute(items_sql, (
                        invoice_id,
                        item.get("description"),
                        item.get("quantity"),
                        item.get("unit_price"),
                        item.get("total_price"),
                    ))

        conn.commit()
        return invoice_id

    except Exception as e:
        conn.rollback()
        raise e
    finally:
        conn.close()


# ---------------------------------------------------------------------------
# Récupération de factures (utilisé par search_engine)
# ---------------------------------------------------------------------------

def get_invoice_by_id(invoice_id: int, user_id: int | None = None, role: str | None = None) -> dict | None:
    """
    Retourne une facture complète avec ses lignes d'articles.

    Si role != 'admin', la facture n'est retournée que si elle appartient
    à user_id (created_by = user_id). Sinon, on retourne None (équivalent
    à "introuvable" du point de vue de l'appelant, pour ne pas révéler
    l'existence de factures d'autres utilisateurs).
    """
    conn = get_connection()
    try:
        with conn.cursor(pymysql.cursors.DictCursor) as cur:
            cur.execute("SELECT * FROM invoices WHERE id = %s", (invoice_id,))
            invoice = cur.fetchone()
            if not invoice:
                return None

            if role != "admin" and invoice.get("created_by") != user_id:
                return None

            cur.execute(
                "SELECT * FROM invoice_items WHERE invoice_id = %s",
                (invoice_id,)
            )
            invoice["items"] = cur.fetchall()
            return invoice
    finally:
        conn.close()


def list_invoices(limit: int = 100, offset: int = 0, user_id: int | None = None, role: str | None = None) -> list[dict]:
    """
    Liste les factures avec pagination.

    Si role == 'admin' (ou role non précisé, pour compatibilité avec les
    appels existants comme main.py), retourne toutes les factures.
    Sinon, ne retourne que celles créées par user_id.
    """
    conn = get_connection()
    try:
        with conn.cursor(pymysql.cursors.DictCursor) as cur:
            if role is not None and role != "admin":
                cur.execute(
                    "SELECT * FROM invoices WHERE created_by = %s ORDER BY created_at DESC LIMIT %s OFFSET %s",
                    (user_id, limit, offset)
                )
            else:
                cur.execute(
                    "SELECT * FROM invoices ORDER BY created_at DESC LIMIT %s OFFSET %s",
                    (limit, offset)
                )
            return cur.fetchall()
    finally:
        conn.close()


def count_invoices(user_id: int | None = None, role: str | None = None) -> int:
    """Compte total de factures visibles par cet utilisateur (pour la pagination)."""
    conn = get_connection()
    try:
        with conn.cursor() as cur:
            if role is not None and role != "admin":
                cur.execute("SELECT COUNT(*) FROM invoices WHERE created_by = %s", (user_id,))
            else:
                cur.execute("SELECT COUNT(*) FROM invoices")
            return cur.fetchone()[0]
    finally:
        conn.close()