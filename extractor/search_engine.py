"""
search_engine.py
----------------
Moteur de recherche multi-stratégie sur la base de données invoices.
Stratégies : exacte → partielle (avec score minimum) → floue (fuzzy).
"""

import pymysql
from rapidfuzz import fuzz
from extractor.search_normalizer import normalize_text, tokenize

# Seuil minimum de score fuzzy pour accepter un résultat (0-100)
FUZZY_THRESHOLD = 78

# Score minimum pour la recherche partielle :
# proportion de tokens de la requête qui doivent matcher dans le champ
# Ex: "tunisie telecom" → 2 tokens → les 2 doivent être présents (ratio = 1.0)
PARTIAL_MIN_TOKEN_RATIO = 0.8   # 80% des tokens doivent matcher


# ---------------------------------------------------------------------------
# Champs de recherche disponibles (colonne DB → label lisible)
# ---------------------------------------------------------------------------

SEARCHABLE_FIELDS = {
    "invoice_number": "Numéro de facture",
    "vendor_name":    "Fournisseur",
    "vendor_email":   "Email fournisseur",
    "vendor_phone":   "Téléphone fournisseur",
    "client_name":    "Client",
    "client_address": "Adresse client",
    "vendor_address": "Adresse fournisseur",
    "currency":       "Devise",
    "payment_method": "Mode de paiement",
    "source_file":    "Fichier source",
}


# ---------------------------------------------------------------------------
# Connexion
# ---------------------------------------------------------------------------

def _get_conn():
    from extractor.db_handler import get_connection
    return get_connection()


# ---------------------------------------------------------------------------
# Helpers SQL
# ---------------------------------------------------------------------------

def _fetch_all_invoices(conn) -> list[dict]:
    """Récupère toutes les factures avec leurs lignes d'articles."""
    with conn.cursor(pymysql.cursors.DictCursor) as cur:
        cur.execute("""
            SELECT i.*,
                   GROUP_CONCAT(ii.description SEPARATOR ' | ') AS items_desc
            FROM invoices i
            LEFT JOIN invoice_items ii ON ii.invoice_id = i.id
            GROUP BY i.id
            ORDER BY i.created_at DESC
        """)
        return cur.fetchall()


def _fetch_invoices_sql(conn, where_clause: str, params: tuple) -> list[dict]:
    """Exécute une requête filtrée et retourne les factures."""
    sql = f"""
        SELECT i.*,
               GROUP_CONCAT(ii.description SEPARATOR ' | ') AS items_desc
        FROM invoices i
        LEFT JOIN invoice_items ii ON ii.invoice_id = i.id
        WHERE {where_clause}
        GROUP BY i.id
        ORDER BY i.created_at DESC
        LIMIT 50
    """
    with conn.cursor(pymysql.cursors.DictCursor) as cur:
        cur.execute(sql, params)
        return cur.fetchall()


# ---------------------------------------------------------------------------
# Stratégie 1 : Recherche exacte
# ---------------------------------------------------------------------------

def search_exact(query: str, fields: list[str], conn) -> list[dict]:
    """
    Recherche stricte : LOWER(champ) = query_normalisé.
    Insensible à la casse et aux accents.
    """
    norm = normalize_text(query)
    if not norm:
        return []

    conditions = []
    params = []
    for field in fields:
        conditions.append(f"LOWER({field}) = %s")
        params.append(norm)

    where = " OR ".join(conditions)
    results = _fetch_invoices_sql(conn, where, tuple(params))

    for r in results:
        r["_match_type"] = "exact"
        r["_score"] = 100
    return results


# ---------------------------------------------------------------------------
# Stratégie 2 : Recherche partielle (LIKE) avec filtre de qualité
# ---------------------------------------------------------------------------

def _token_match_ratio(tokens: list[str], field_value: str) -> float:
    """
    Calcule la proportion de tokens de la requête présents dans field_value.
    Ex: tokens=['tunisie','telecom'], value='TECH SOLUTIONS' → 0.0
    Ex: tokens=['tunisie','telecom'], value='Tunisie Telecom SA' → 1.0
    """
    if not tokens or not field_value:
        return 0.0
    norm_val = normalize_text(field_value)
    matched = sum(1 for t in tokens if t in norm_val)
    return matched / len(tokens)


def search_partial(query: str, fields: list[str], conn) -> list[dict]:
    """
    Recherche par sous-chaîne : LOWER(champ) LIKE '%token%'.
    
    IMPORTANT : après récupération SQL, on filtre les résultats selon
    PARTIAL_MIN_TOKEN_RATIO pour éliminer les faux positifs.
    Ex: 'tunisie telecom' → on rejette tout résultat où moins de 80%
    des tokens matchent dans le même champ.
    """
    tokens = tokenize(query)
    if not tokens:
        return []

    # Exclure les tokens trop courts (évite les faux positifs sur 'te', 'la'...)
    tokens = [t for t in tokens if len(t) >= 3]
    if not tokens:
        return []

    conditions = []
    params = []
    for token in tokens:
        for field in fields:
            conditions.append(f"LOWER({field}) LIKE %s")
            params.append(f"%{token}%")

    if not conditions:
        return []

    where = " OR ".join(conditions)
    candidates = _fetch_invoices_sql(conn, where, tuple(params))

    # ── Filtre qualité : garder seulement les vrais matchs ──────────────────
    results = []
    for r in candidates:
        best_ratio = 0.0
        for field in fields:
            val = r.get(field)
            if val:
                ratio = _token_match_ratio(tokens, str(val))
                if ratio > best_ratio:
                    best_ratio = ratio

        if best_ratio >= PARTIAL_MIN_TOKEN_RATIO:
            r["_match_type"] = "partial"
            r["_score"] = int(best_ratio * 85)
            results.append(r)

    return results


# ---------------------------------------------------------------------------
# Stratégie 3 : Recherche floue (Fuzzy / Levenshtein)
# ---------------------------------------------------------------------------

def search_fuzzy(query: str, fields: list[str], conn) -> list[dict]:
    """
    Recherche approximative avec RapidFuzz.
    Récupère tous les enregistrements et calcule la similarité
    entre la requête et les valeurs de chaque champ.
    """
    norm_query = normalize_text(query)
    if not norm_query:
        return []

    all_invoices = _fetch_all_invoices(conn)
    scored: list[tuple[float, dict]] = []

    for invoice in all_invoices:
        best_score = 0.0

        for field in fields:
            raw_val = invoice.get(field)
            if not raw_val:
                continue

            norm_val = normalize_text(str(raw_val))
            if not norm_val:
                continue

            # Plusieurs métriques fuzzy — on garde le meilleur score
            scores = [
                fuzz.ratio(norm_query, norm_val),
                fuzz.partial_ratio(norm_query, norm_val),
                fuzz.token_sort_ratio(norm_query, norm_val),
                fuzz.token_set_ratio(norm_query, norm_val),
            ]
            field_best = max(scores)

            if field_best > best_score:
                best_score = field_best

        if best_score >= FUZZY_THRESHOLD:
            invoice["_match_type"] = "fuzzy"
            invoice["_score"] = round(best_score, 1)
            scored.append((best_score, invoice))

    scored.sort(key=lambda x: x[0], reverse=True)
    return [item for _, item in scored]


# ---------------------------------------------------------------------------
# Moteur principal : cascade de stratégies
# ---------------------------------------------------------------------------

def search_invoices(
    query: str,
    fields: list[str] | None = None,
    max_results: int = 20,
) -> dict:
    """
    Recherche intelligente sur les factures en 3 passes :
    1. Exacte    → correspondance parfaite (insensible à la casse/accents)
    2. Partielle → tokens présents dans le champ (filtrée, pas de faux positifs)
    3. Floue     → Levenshtein/RapidFuzz pour les fautes de frappe

    Retourne
    --------
    dict { 'query', 'strategy', 'count', 'results' }
    """
    if fields is None:
        fields = list(SEARCHABLE_FIELDS.keys())

    conn = _get_conn()
    try:
        seen_ids: set[int] = set()

        def deduplicate(rows: list[dict]) -> list[dict]:
            unique = []
            for r in rows:
                if r["id"] not in seen_ids:
                    seen_ids.add(r["id"])
                    unique.append(r)
            return unique

        # Passe 1 : Exacte
        results = deduplicate(search_exact(query, fields, conn))
        if results:
            return _build_response(query, "exact", results[:max_results])

        # Passe 2 : Partielle (avec filtre qualité)
        results = deduplicate(search_partial(query, fields, conn))
        if results:
            return _build_response(query, "partial", results[:max_results])

        # Passe 3 : Floue
        results = deduplicate(search_fuzzy(query, fields, conn))
        if results:
            return _build_response(query, "fuzzy", results[:max_results])

        return _build_response(query, "none", [])

    finally:
        conn.close()


def _build_response(query: str, strategy: str, results: list[dict]) -> dict:
    return {
        "query":    query,
        "strategy": strategy,
        "count":    len(results),
        "results":  results,
    }