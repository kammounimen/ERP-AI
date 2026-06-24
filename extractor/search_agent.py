"""
search_agent.py
---------------
Agent IA de recherche intelligente sur les factures.
Utilise Mistral AI pour :
  - Comprendre l'intention de l'utilisateur (quel champ chercher ?)
  - Lancer la recherche multi-stratégie (exacte → partielle → fuzzy)
  - Formuler une réponse claire en langage naturel
  
Gestion automatique du Rate Limit 429 avec retry + backoff exponentiel.
"""

import json
import decimal
import datetime
import time
import requests
from extractor.search_engine import search_invoices, SEARCHABLE_FIELDS
from extractor.search_normalizer import normalize_text
from config import MISTRAL_API_KEY


# ---------------------------------------------------------------------------
# Sérialiseur JSON sûr (types MySQL → JSON)
# ---------------------------------------------------------------------------

class _SafeEncoder(json.JSONEncoder):
    """Convertit les types MySQL non-sérialisables (Decimal, date, datetime)."""
    def default(self, obj):
        if isinstance(obj, decimal.Decimal):
            return float(obj)
        if isinstance(obj, (datetime.date, datetime.datetime)):
            return str(obj)
        return super().default(obj)


MISTRAL_API_URL = "https://api.mistral.ai/v1/chat/completions"
MISTRAL_MODEL   = "mistral-large-latest"

# ── Retry config (Rate Limit 429) ───────────────────────────────────────────
_RETRY_MAX    = 4
_RETRY_DELAYS = [3, 8, 20, 40]   # secondes entre chaque tentative


# ---------------------------------------------------------------------------
# Prompts système
# ---------------------------------------------------------------------------

AGENT_SYSTEM_PROMPT = """
Tu es un assistant expert en gestion de factures pour un ERP (Enterprise Resource Planning).
Ton rôle est d'aider les utilisateurs à rechercher et retrouver des factures dans la base de données.

## Ta mission

Analyser la requête de l'utilisateur, déterminer son intention, et retourner un JSON structuré
qui indique comment effectuer la recherche dans la base de données.

## Base de données disponible

La table `invoices` contient les champs suivants :
- invoice_number  : Numéro de la facture (ex: "INV-2026-001", "FAC-2024-042")
- vendor_name     : Nom du fournisseur (ex: "Tech Store Tunisia", "STEG")
- vendor_email    : Email du fournisseur
- vendor_phone    : Téléphone du fournisseur
- client_name     : Nom du client
- client_address  : Adresse du client
- vendor_address  : Adresse du fournisseur
- currency        : Devise (TND, EUR, USD...)
- payment_method  : Mode de paiement
- invoice_date    : Date de la facture
- due_date        : Date d'échéance
- total_amount    : Montant total
- source_file     : Nom du fichier PDF/image source

## Format de réponse OBLIGATOIRE

Réponds UNIQUEMENT avec ce JSON valide, sans texte avant ou après :

{
  "intent": "search_vendor" | "search_client" | "search_invoice_number" | "search_amount" | "search_date" | "search_general" | "unknown",
  "fields": ["liste", "des", "champs", "à", "interroger"],
  "query_normalized": "texte nettoyé pour la recherche",
  "explanation": "Explication courte de ce que l'utilisateur cherche",
  "confidence": 0.0
}

## Règles de détection d'intention

- Nom de société / fournisseur → intent: "search_vendor", fields: ["vendor_name", "vendor_address"]
- Recherche client             → intent: "search_client",  fields: ["client_name", "client_address"]
- Numéro de facture (INV-, FAC-, numéro...) → intent: "search_invoice_number", fields: ["invoice_number"]
- Montant ou somme            → intent: "search_amount",  fields: ["total_amount", "subtotal"]
- Date                        → intent: "search_date",    fields: ["invoice_date", "due_date"]
- Requête générale/ambiguë    → intent: "search_general", fields: tous les champs texte
- Incompréhensible            → intent: "unknown"

## Exemples

Requête : "tech store tunisia"
→ {"intent": "search_vendor", "fields": ["vendor_name", "vendor_address"], "query_normalized": "tech store tunisia", "explanation": "Recherche du fournisseur Tech Store Tunisia", "confidence": 0.95}

Requête : "INV-2026-001"
→ {"intent": "search_invoice_number", "fields": ["invoice_number"], "query_normalized": "INV-2026-001", "explanation": "Recherche par numéro de facture exact", "confidence": 0.99}

Requête : "client Imen Kammoun"
→ {"intent": "search_client", "fields": ["client_name"], "query_normalized": "imen kammoun", "explanation": "Recherche du client Imen Kammoun", "confidence": 0.95}

Requête : "facture 261 TND"
→ {"intent": "search_amount", "fields": ["total_amount"], "query_normalized": "261", "explanation": "Recherche par montant approximatif 261 TND", "confidence": 0.80}
"""


RESPONSE_SYSTEM_PROMPT = """
Tu es un assistant ERP expert en gestion de factures.
Formule une réponse claire, professionnelle et concise en français
à partir des résultats de recherche fournis.

Règles :
- Si résultats trouvés : résume les informations clés (numéro, fournisseur, client, montant, date)
- Mentionne le nombre de factures trouvées
- Indique la stratégie : "exacte", "partielle" ou "approximative (fuzzy)"
- Si score fuzzy < 90% : précise que c'est une correspondance approximative
- Si aucun résultat : suggère des variantes de recherche concrètes
- Sois concis : 3 à 6 lignes maximum
- Ne répète jamais le JSON brut
"""


# ---------------------------------------------------------------------------
# Appel API Mistral avec retry automatique sur 429
# ---------------------------------------------------------------------------

def _call_mistral(system: str, user_message: str, temperature: float = 0.0) -> str:
    """
    Appel à l'API Mistral avec gestion automatique du Rate Limit (429).
    Retry jusqu'à _RETRY_MAX fois avec délai croissant.
    """
    if not MISTRAL_API_KEY:
        raise ValueError("MISTRAL_API_KEY manquante dans .env")

    headers = {
        "Authorization": f"Bearer {MISTRAL_API_KEY}",
        "Content-Type":  "application/json",
    }
    payload = {
        "model":       MISTRAL_MODEL,
        "messages":    [
            {"role": "system", "content": system},
            {"role": "user",   "content": user_message},
        ],
        "max_tokens":  800,
        "temperature": temperature,
    }

    last_error = None

    for attempt in range(_RETRY_MAX):
        try:
            resp = requests.post(
                MISTRAL_API_URL, headers=headers, json=payload, timeout=45
            )

            # ── Succès ──────────────────────────────────────────────────────
            if resp.status_code == 200:
                return resp.json()["choices"][0]["message"]["content"].strip()

            # ── Rate Limit : attendre et réessayer ──────────────────────────
            if resp.status_code == 429:
                wait = _RETRY_DELAYS[min(attempt, len(_RETRY_DELAYS) - 1)]

                # Respecter le Retry-After si l'API le fournit
                retry_after = resp.headers.get("Retry-After")
                if retry_after:
                    try:
                        wait = max(wait, int(retry_after))
                    except ValueError:
                        pass

                print(f"  ⏳ Rate limit Mistral — attente {wait}s "
                      f"(tentative {attempt + 1}/{_RETRY_MAX})...")
                time.sleep(wait)
                last_error = f"429 Rate Limit après {_RETRY_MAX} tentatives"
                continue

            # ── Autre erreur HTTP ────────────────────────────────────────────
            raise RuntimeError(
                f"Erreur API Mistral {resp.status_code}: {resp.text}"
            )

        except requests.exceptions.Timeout:
            wait = _RETRY_DELAYS[min(attempt, len(_RETRY_DELAYS) - 1)]
            print(f"  ⏳ Timeout Mistral — attente {wait}s "
                  f"(tentative {attempt + 1}/{_RETRY_MAX})...")
            time.sleep(wait)
            last_error = "Timeout réseau"

    raise RuntimeError(
        f"Mistral API inaccessible après {_RETRY_MAX} tentatives. "
        f"Dernière erreur : {last_error}"
    )


# ---------------------------------------------------------------------------
# Étape 1 : Analyse de l'intention (avec fallback local)
# ---------------------------------------------------------------------------

def _analyze_intent_local(user_query: str) -> dict:
    """
    Fallback local (sans LLM) quand Mistral est indisponible.
    Détecte l'intention par règles simples sur la requête.
    """
    q = user_query.strip().upper()
    all_text_fields = [
        "vendor_name", "vendor_address", "client_name",
        "client_address", "invoice_number", "vendor_email", "source_file"
    ]

    # Numéro de facture (INV-, FAC-, F-, etc.)
    import re
    if re.match(r"^(INV|FAC|F|FACT|N°|NO)[-\s]?\d", q):
        return {
            "intent":           "search_invoice_number",
            "fields":           ["invoice_number"],
            "query_normalized": user_query.strip(),
            "explanation":      f"Recherche par numéro de facture : {user_query}",
            "confidence":       0.95,
            "_source":          "local_fallback",
        }

    # Date (contient chiffres séparés par / ou -)
    if re.search(r"\d{2}[/-]\d{2}[/-]\d{2,4}", user_query):
        return {
            "intent":           "search_date",
            "fields":           ["invoice_date", "due_date"],
            "query_normalized": user_query.strip(),
            "explanation":      f"Recherche par date : {user_query}",
            "confidence":       0.85,
            "_source":          "local_fallback",
        }

    # Montant (contient des chiffres et TND/EUR/DT)
    if re.search(r"\d+[.,]\d+|\d{3,}", user_query) and re.search(
        r"tnd|eur|usd|dt|dinar|euro", user_query.lower()
    ):
        return {
            "intent":           "search_amount",
            "fields":           ["total_amount"],
            "query_normalized": re.sub(r"[^\d.,]", "", user_query),
            "explanation":      f"Recherche par montant : {user_query}",
            "confidence":       0.80,
            "_source":          "local_fallback",
        }

    # Mots-clés client
    if re.search(r"\bclient\b|\bacheteur\b", user_query.lower()):
        return {
            "intent":           "search_client",
            "fields":           ["client_name", "client_address"],
            "query_normalized": re.sub(r"\bclient\b|\bacheteur\b", "", user_query.lower()).strip(),
            "explanation":      f"Recherche client : {user_query}",
            "confidence":       0.80,
            "_source":          "local_fallback",
        }

    # Par défaut : recherche fournisseur / générale
    return {
        "intent":           "search_vendor",
        "fields":           ["vendor_name", "vendor_address", "client_name"],
        "query_normalized": user_query.strip(),
        "explanation":      f"Recherche générale : {user_query}",
        "confidence":       0.70,
        "_source":          "local_fallback",
    }


def _analyze_intent(user_query: str) -> dict:
    """
    Envoie la requête à Mistral pour détecter l'intention.
    En cas d'erreur (429, timeout), bascule sur le fallback local.
    """
    try:
        raw = _call_mistral(AGENT_SYSTEM_PROMPT, user_query, temperature=0.0)
    except RuntimeError as e:
        print(f"  ⚠️  Mistral indisponible ({e}) — analyse locale activée")
        return _analyze_intent_local(user_query)

    # Nettoyage défensif du JSON
    raw = raw.strip()
    if "```" in raw:
        for part in raw.split("```"):
            part = part.strip().lstrip("json").strip()
            if part.startswith("{"):
                raw = part
                break

    start, end = raw.find("{"), raw.rfind("}")
    if start != -1 and end != -1:
        raw = raw[start:end + 1]

    try:
        intent_data = json.loads(raw)
        intent_data["_source"] = "mistral"
    except json.JSONDecodeError:
        print("  ⚠️  JSON Mistral invalide — analyse locale activée")
        return _analyze_intent_local(user_query)

    # Validation des champs
    valid_fields = list(SEARCHABLE_FIELDS.keys())
    intent_data["fields"] = [
        f for f in intent_data.get("fields", valid_fields)
        if f in valid_fields
    ] or valid_fields

    return intent_data


# ---------------------------------------------------------------------------
# Étape 2 : Formulation de la réponse (avec fallback local)
# ---------------------------------------------------------------------------

def _format_response_local(user_query: str, search_result: dict) -> str:
    """Réponse formatée localement sans LLM (fallback)."""
    strategy_labels = {
        "exact":   "exacte",
        "partial": "partielle",
        "fuzzy":   "approximative (fuzzy)",
        "none":    "aucune",
    }
    label = strategy_labels.get(search_result["strategy"], search_result["strategy"])
    count = search_result["count"]

    if count == 0:
        return (
            f"Aucune facture trouvée pour « {user_query} ».\n"
            "Essayez une autre orthographe ou un terme plus court."
        )

    lines = [f"**{count} facture(s) trouvée(s)** — recherche {label}.\n"]
    for i, r in enumerate(search_result["results"][:5], 1):
        score = r.get("_score", "?")
        lines.append(
            f"[{i}] N°{r.get('invoice_number') or 'N/A'} | "
            f"{r.get('vendor_name') or 'N/A'} → {r.get('client_name') or 'N/A'} | "
            f"{r.get('total_amount')} {r.get('currency') or ''} | "
            f"{r.get('invoice_date') or 'N/A'} | score:{score}%"
        )
    return "\n".join(lines)


def _format_response(user_query: str, search_result: dict, intent_data: dict) -> str:
    """
    Génère une réponse en langage naturel via Mistral.
    En cas d'erreur, bascule sur le formatage local.
    """
    strategy_labels = {
        "exact":   "correspondance exacte",
        "partial": "correspondance partielle",
        "fuzzy":   "correspondance approximative (fuzzy)",
        "none":    "aucune correspondance",
    }
    strategy_label = strategy_labels.get(
        search_result["strategy"], search_result["strategy"]
    )

    results_summary = [
        {
            "id":             r.get("id"),
            "invoice_number": r.get("invoice_number"),
            "vendor_name":    r.get("vendor_name"),
            "client_name":    r.get("client_name"),
            "total_amount":   r.get("total_amount"),
            "currency":       r.get("currency"),
            "invoice_date":   str(r.get("invoice_date") or ""),
            "score":          r.get("_score"),
        }
        for r in search_result["results"][:5]
    ]

    context = (
        f'Requête utilisateur : "{user_query}"\n'
        f"Intention détectée : {intent_data.get('explanation', '')}\n"
        f"Stratégie de recherche utilisée : {strategy_label}\n"
        f"Nombre total de résultats : {search_result['count']}\n\n"
        f"Résultats (max 5 affichés) :\n"
        f"{json.dumps(results_summary, ensure_ascii=False, indent=2, cls=_SafeEncoder)}"
    )

    try:
        return _call_mistral(RESPONSE_SYSTEM_PROMPT, context, temperature=0.3)
    except RuntimeError as e:
        print(f"  ⚠️  Réponse Mistral indisponible ({e}) — formatage local activé")
        return _format_response_local(user_query, search_result)


# ---------------------------------------------------------------------------
# Point d'entrée public
# ---------------------------------------------------------------------------

def run_search_agent(user_query: str) -> dict:
    """
    Agent de recherche principal.

    Retourne
    --------
    dict {
        'query', 'intent', 'explanation', 'strategy',
        'count', 'results', 'natural_response'
    }
    """
    print(f"\n🔍 Requête : '{user_query}'")

    # Étape 1 : Analyser l'intention
    print("  [1/3] Analyse de l'intention...")
    intent_data = _analyze_intent(user_query)
    src = "🤖 Mistral" if intent_data.get("_source") == "mistral" else "🔧 Local"
    print(f"        Intent    : {intent_data['intent']}  ({src})")
    print(f"        Champs    : {intent_data['fields']}")
    print(f"        Confiance : {intent_data.get('confidence', '?')}")

    # Étape 2 : Recherche en BDD (ciblée sur les champs déduits de l'intention)
    print("  [2/3] Recherche en base de données...")
    search_query = intent_data.get("query_normalized") or normalize_text(user_query)
    search_result = search_invoices(query=search_query, fields=intent_data["fields"])
    print(f"        Stratégie : {search_result['strategy']}")
    print(f"        Résultats : {search_result['count']}")

    # ── Fallback élargi ──────────────────────────────────────────────────
    # L'intention détectée (ex: "search_client") peut être correcte en
    # apparence mais cibler les mauvais champs si le nom recherché se
    # trouve en réalité dans un autre champ (ex: un nom de personne utilisé
    # comme vendor_name plutôt que client_name).
    # Si la recherche ciblée ne donne RIEN, on retente sur TOUS les champs
    # texte disponibles avant de conclure à un échec.
    widened = False
    if search_result["count"] == 0:
        all_fields = list(SEARCHABLE_FIELDS.keys())
        if set(intent_data["fields"]) != set(all_fields):
            print("  [2bis/3] Aucun résultat ciblé — élargissement à tous les champs...")
            search_result = search_invoices(query=search_query, fields=all_fields)
            print(f"        Stratégie : {search_result['strategy']}")
            print(f"        Résultats : {search_result['count']}")
            if search_result["count"] > 0:
                widened = True
                # On garde une trace que l'élargissement a permis de trouver
                # le résultat, utile pour informer l'utilisateur dans la
                # réponse en langage naturel.
                intent_data["explanation"] = (
                    f"{intent_data.get('explanation', '')} "
                    "(recherche élargie à tous les champs après un premier essai infructueux)"
                ).strip()

    # Étape 3 : Formulation de la réponse
    print("  [3/3] Génération de la réponse...")
    natural_response = _format_response(user_query, search_result, intent_data)

    return {
        "query":            user_query,
        "intent":           intent_data.get("intent"),
        "explanation":      intent_data.get("explanation"),
        "strategy":         search_result["strategy"],
        "count":            search_result["count"],
        "results":          search_result["results"],
        "natural_response": natural_response,
        "widened_search":   widened,
    }