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

def save_invoice(data: dict, raw_text: str = "", source_file: str = "") -> int:
    """Sauvegarde la facture et ses lignes dans la BDD. Retourne l'ID."""
    conn = get_connection()
    try:
        with conn.cursor() as cursor:
            sql = """
                INSERT INTO invoices (
                    invoice_number, invoice_date, due_date,
                    vendor_name, vendor_address, vendor_email, vendor_phone,
                    client_name, client_address,
                    subtotal, tax_rate, tax_amount, total_amount,
                    currency, payment_method, notes,
                    raw_text, source_file
                ) VALUES (
                    %(invoice_number)s, %(invoice_date)s, %(due_date)s,
                    %(vendor_name)s, %(vendor_address)s, %(vendor_email)s, %(vendor_phone)s,
                    %(client_name)s, %(client_address)s,
                    %(subtotal)s, %(tax_rate)s, %(tax_amount)s, %(total_amount)s,
                    %(currency)s, %(payment_method)s, %(notes)s,
                    %(raw_text)s, %(source_file)s
                )
            """
            params = {
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

def get_invoice_by_id(invoice_id: int) -> dict | None:
    """Retourne une facture complète avec ses lignes d'articles."""
    conn = get_connection()
    try:
        with conn.cursor(pymysql.cursors.DictCursor) as cur:
            cur.execute("SELECT * FROM invoices WHERE id = %s", (invoice_id,))
            invoice = cur.fetchone()
            if not invoice:
                return None

            cur.execute(
                "SELECT * FROM invoice_items WHERE invoice_id = %s",
                (invoice_id,)
            )
            invoice["items"] = cur.fetchall()
            return invoice
    finally:
        conn.close()


def list_invoices(limit: int = 100, offset: int = 0) -> list[dict]:
    """Liste les factures avec pagination."""
    conn = get_connection()
    try:
        with conn.cursor(pymysql.cursors.DictCursor) as cur:
            cur.execute(
                "SELECT * FROM invoices ORDER BY created_at DESC LIMIT %s OFFSET %s",
                (limit, offset)
            )
            return cur.fetchall()
    finally:
        conn.close()