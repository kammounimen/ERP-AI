import json
import base64
import requests
from config import MISTRAL_API_KEY, MISTRAL_MODEL

MISTRAL_API_URL = "https://api.mistral.ai/v1/chat/completions"

SYSTEM_PROMPT = """
Tu es un expert en extraction de données de factures.
Analyse la facture fournie et retourne UNIQUEMENT un JSON valide avec cette structure exacte,
sans aucun texte avant ou après, sans backticks, sans markdown :

{
  "invoice_number": "string ou null",
  "invoice_date": "YYYY-MM-DD ou null",
  "due_date": "YYYY-MM-DD ou null",
  "vendor_name": "string ou null",
  "vendor_address": "string ou null",
  "vendor_email": "string ou null",
  "vendor_phone": "string ou null",
  "client_name": "string ou null",
  "client_address": "string ou null",
  "subtotal": nombre_décimal_ou_null,
  "tax_rate": nombre_décimal_ou_null,
  "tax_amount": nombre_décimal_ou_null,
  "total_amount": nombre_décimal_ou_null,
  "currency": "TND/EUR/USD/etc ou null",
  "payment_method": "string ou null",
  "notes": "string ou null",
  "items": [
    {
      "description": "string",
      "quantity": nombre_ou_null,
      "unit_price": nombre_ou_null,
      "total_price": nombre_ou_null
    }
  ]
}

Règles strictes :
- Retourne UNIQUEMENT le JSON brut, rien d'autre.
- Si une information est absente, mets null.
- Ne jamais inventer des données.
- Les dates doivent être au format YYYY-MM-DD.
- Les montants doivent être des nombres (pas des strings).
"""


def _clean_json_response(raw: str) -> str:
    """Nettoie la réponse du LLM pour extraire le JSON pur."""
    raw = raw.strip()

    # Supprimer les blocs ```json ... ``` ou ``` ... ```
    if "```" in raw:
        # Extraire le contenu entre les backticks
        parts = raw.split("```")
        for part in parts:
            part = part.strip()
            if part.startswith("json"):
                part = part[4:].strip()
            if part.startswith("{"):
                return part.strip()

    # Si ça commence directement par {, c'est bon
    if raw.startswith("{"):
        return raw

    # Chercher le premier { et le dernier }
    start = raw.find("{")
    end = raw.rfind("}")
    if start != -1 and end != -1:
        return raw[start:end + 1]

    return raw


def _build_messages(extracted: dict) -> list:
    """Construit les messages pour l'API Mistral."""
    messages = [{"role": "system", "content": SYSTEM_PROMPT}]

    user_content = []

    # Mistral vision : ajouter les images si disponibles
    for b64_img in extracted.get("images_b64", []):
        user_content.append({
            "type": "image_url",
            "image_url": {
                "url": f"data:image/jpeg;base64,{b64_img}"
            }
        })

    # Ajouter le texte extrait
    if extracted.get("text"):
        user_content.append({
            "type": "text",
            "text": f"Voici le texte extrait de la facture :\n\n{extracted['text']}\n\nAnalyse et retourne le JSON."
        })
    else:
        user_content.append({
            "type": "text",
            "text": "Analyse cette facture et retourne le JSON structuré."
        })

    # Si pas d'images, envoyer comme message texte simple (plus compatible)
    if not extracted.get("images_b64"):
        messages.append({
            "role": "user",
            "content": user_content[0]["text"] if len(user_content) == 1 else str(user_content)
        })
    else:
        # Avec images : utiliser le format multimodal
        # Note: nécessite mistral-large ou pixtral-large pour la vision
        messages.append({
            "role": "user",
            "content": user_content
        })

    return messages


def parse_invoice(extracted: dict) -> dict:
    """
    Envoie le contenu extrait à Mistral et retourne les données structurées.
    extracted = {'text': '...', 'images_b64': [...]}
    """
    if not extracted.get("text") and not extracted.get("images_b64"):
        raise ValueError("Aucun contenu à analyser")

    if not MISTRAL_API_KEY:
        raise ValueError("MISTRAL_API_KEY manquante dans le fichier .env")

    # Choisir le bon modèle selon le contenu
    # pixtral-large-latest supporte les images, mistral-large-latest pour le texte
    model = "pixtral-large-latest" if extracted.get("images_b64") else MISTRAL_MODEL

    messages = _build_messages(extracted)

    headers = {
        "Authorization": f"Bearer {MISTRAL_API_KEY}",
        "Content-Type": "application/json"
    }

    payload = {
        "model": model,
        "messages": messages,
        "max_tokens": 2000,
        "temperature": 0.0,       # 0 = déterministe, parfait pour l'extraction
        "response_format": {"type": "json_object"}  # Force le JSON pur ✅
    }

    response = requests.post(MISTRAL_API_URL, headers=headers, json=payload, timeout=60)

    if response.status_code != 200:
        raise RuntimeError(
            f"Erreur API Mistral {response.status_code}: {response.text}"
        )

    data = response.json()
    raw_json = data["choices"][0]["message"]["content"]

    # Nettoyage défensif même avec response_format=json_object
    cleaned = _clean_json_response(raw_json)

    try:
        return json.loads(cleaned)
    except json.JSONDecodeError as e:
        raise ValueError(f"JSON invalide reçu du LLM:\n{cleaned}\n\nErreur: {e}")