"""
api.py
------
API FastAPI qui expose les agents Python existants (extraction, recherche, BDD)
sous forme d'endpoints HTTP, afin que le frontend Laminas (PHP) puisse les appeler.

Lancement (depuis la racine du projet ERP-AI, où se trouve déjà main.py) :
    pip install fastapi uvicorn python-multipart --break-system-packages
    uvicorn api:app --reload --port 8001

Documentation interactive auto-générée disponible sur :
    http://127.0.0.1:8001/docs
"""

import os
import shutil
import tempfile
from typing import Optional

from fastapi import FastAPI, UploadFile, File, Form, HTTPException, Query
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel

from extractor.pdf_extractor import extract_from_file
from extractor.ai_parser import parse_invoice
from extractor.db_handler import (
    save_invoice,
    list_invoices,
    get_invoice_by_id,
    count_invoices,
    find_product,
    search_similar_products
)
from extractor.search_agent import run_search_agent
from extractor.license_checker import check_license
from extractor.file_security import validate_and_sanitize_file, SecurityError   # ← nouveau


# ---------------------------------------------------------------------------
# Initialisation de l'application
# ---------------------------------------------------------------------------

app = FastAPI(
    title="ERP-AI Agents API",
    description="API exposant les agents d'extraction et de recherche de factures",
    version="1.0.0",
)

# Laminas (PHP) tournera sur un autre port/domaine (ex: localhost:8000 via Laragon)
# → il faut autoriser les requêtes cross-origin pendant le développement.
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],          # à restreindre en production (ex: ["http://erp-ai.local"])
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


# ---------------------------------------------------------------------------
# Schémas Pydantic (validation automatique des entrées/sorties)
# ---------------------------------------------------------------------------

class InvoiceItem(BaseModel):
    description: Optional[str] = None
    quantity: Optional[float] = None
    unit_price: Optional[float] = None
    total_price: Optional[float] = None
    # Résolus côté Laminas via /api/products/check avant l'envoi :
    # - product_id renseigné  → produit existant choisi par l'utilisateur, à réutiliser tel quel
    # - new_product = True    → aucun produit ne correspondait, à créer en base
    product_id: Optional[int] = None
    new_product: bool = False


class InvoiceValidated(BaseModel):
    """
    Données envoyées par Laminas APRÈS que l'utilisateur ait vérifié/corrigé
    le formulaire dans l'interface ERP.
    """
    created_by: Optional[int] = None
    invoice_number: Optional[str] = None
    invoice_date: Optional[str] = None     # format YYYY-MM-DD
    due_date: Optional[str] = None
    vendor_name: Optional[str] = None
    vendor_address: Optional[str] = None
    vendor_email: Optional[str] = None
    vendor_phone: Optional[str] = None
    client_name: Optional[str] = None
    client_address: Optional[str] = None
    subtotal: Optional[float] = None
    tax_rate: Optional[float] = None
    tax_amount: Optional[float] = None
    total_amount: Optional[float] = None
    currency: Optional[str] = "TND"
    payment_method: Optional[str] = None
    notes: Optional[str] = None
    raw_text: Optional[str] = ""
    source_file: Optional[str] = ""
    items: list[InvoiceItem] = []


class SearchQuery(BaseModel):
    query: str
    licence_key: str
    user_id: Optional[int] = None
    role: Optional[str] = None


class LicenseCheckRequest(BaseModel):
    licence_key: str

class ProductRequest(BaseModel):
    description: str

# ---------------------------------------------------------------------------
# 1. Endpoint d'extraction : upload PDF/image → JSON brut extrait par l'IA
#    (Laminas affichera ce JSON dans un formulaire éditable, PAS encore sauvegardé)
# ---------------------------------------------------------------------------

@app.post("/api/extract")
async def extract_invoice(file: UploadFile = File(...), licence_key: str = Form(...)):
    """
    Reçoit un fichier (PDF/JPG/PNG) + la licence_key du client, vérifie la
    licence, puis lance l'extraction + l'analyse Mistral.
    Ne sauvegarde RIEN en base à cette étape.

    Couche de sécurité (dans l'ordre d'exécution) :
      1. Vérification de la licence
      2. Vérification de l'extension déclarée
      3. Sauvegarde brute temporaire
      4. validate_and_sanitize_file() :
           - limite de taille
           - magic bytes (vrai type ≠ extension mensongère)
           - scan ClamAV (si disponible)
           - images : verify() + réencodage complet Pillow
           - PDF : refus chiffré, limite pages, détection JS/Launch
           - renommage UUID
      5. extract_from_file() sur le fichier sécurisé
    """
    # --- Vérification de la licence ---
    license_status = check_license(licence_key)
    if not license_status["valid"]:
        raise HTTPException(
            status_code=403,
            detail=f"Licence invalide : {license_status['reason']}",
        )

    # --- Première validation légère : extension déclarée ---
    allowed_ext = (".pdf", ".jpg", ".jpeg", ".png", ".tif", ".tiff")
    ext = os.path.splitext(file.filename)[1].lower()
    if ext not in allowed_ext:
        raise HTTPException(
            status_code=400,
            detail=f"Format non supporté : {ext}. Acceptés : {', '.join(allowed_ext)}",
        )

    # --- Répertoires temporaires ---
    raw_dir  = tempfile.mkdtemp(prefix="erp_raw_")      # fichier brut reçu
    safe_dir = None                                       # sera créé par validate_and_sanitize_file

    raw_path  = os.path.join(raw_dir, "upload" + ext)   # nom neutre, pas le nom utilisateur
    safe_path = None

    try:
        # Sauvegarde brute (taille limitée par FastAPI / Nginx upstream en prod)
        with open(raw_path, "wb") as f:
            shutil.copyfileobj(file.file, f)

        # --- COUCHE DE SÉCURITÉ PRINCIPALE ---
        # Lève SecurityError si le fichier est suspect
        safe_path = validate_and_sanitize_file(raw_path, file.filename)
        safe_dir  = os.path.dirname(safe_path)

        # Le fichier brut n'est plus nécessaire — on le supprime immédiatement
        shutil.rmtree(raw_dir, ignore_errors=True)
        raw_dir = None

        # --- Extraction IA sur le fichier sécurisé ---
        extracted = extract_from_file(safe_path)

        if not extracted["text"] and not extracted["images_b64"]:
            raise HTTPException(
                status_code=422,
                detail="Impossible d'extraire du contenu de ce fichier.",
            )

        invoice_data = parse_invoice(extracted)

        return {
            "success": True,
            "source_file": file.filename,   # nom original retourné à l'UI (affichage seulement)
            "raw_text": extracted.get("text", ""),
            "data": invoice_data,
        }

    except SecurityError as exc:
        # Rejet sécurité → 400 Bad Request avec message explicite
        raise HTTPException(status_code=400, detail=str(exc))

    except HTTPException:
        raise

    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Erreur d'extraction : {e}")

    finally:
        # Nettoyage systématique des deux dossiers temporaires
        if raw_dir:
            shutil.rmtree(raw_dir, ignore_errors=True)
        if safe_dir:
            shutil.rmtree(safe_dir, ignore_errors=True)


# ---------------------------------------------------------------------------
# 2. Endpoint de sauvegarde : enregistre la facture VALIDÉE par l'utilisateur
# ---------------------------------------------------------------------------

@app.post("/api/invoices")
async def create_invoice(invoice: InvoiceValidated):
    """
    Sauvegarde en base de données une facture après validation/correction
    par l'utilisateur dans le formulaire Laminas.
    """
    try:
        data = invoice.model_dump()
        items = data.pop("items", [])
        created_by = data.pop("created_by", None)
        data["items"] = items

        invoice_id = save_invoice(
            data=data,
            raw_text=data.get("raw_text", ""),
            source_file=data.get("source_file", ""),
            created_by=created_by,
        )
        return {"success": True, "invoice_id": invoice_id}

    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Erreur de sauvegarde : {e}")


# ---------------------------------------------------------------------------
# 3. Endpoints de lecture : liste + détail (pour Dashboard et Historique)
# ---------------------------------------------------------------------------

@app.get("/api/invoices")
async def get_invoices(
    limit: int = Query(50, le=200),
    offset: int = Query(0, ge=0),
    user_id: Optional[int] = Query(None),
    role: Optional[str] = Query(None),
):
    """
    Liste paginée des factures (utilisé par le Dashboard / Historique).

    - Si role == 'admin' : toutes les factures sont retournées.
    - Sinon : seules les factures créées par user_id sont retournées.
    """
    try:
        invoices = list_invoices(limit=limit, offset=offset, user_id=user_id, role=role)
        total = count_invoices(user_id=user_id, role=role)
        return {"success": True, "count": total, "results": invoices}
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Erreur de lecture : {e}")


@app.get("/api/invoices/{invoice_id}")
async def get_invoice(
    invoice_id: int,
    user_id: Optional[int] = Query(None),
    role: Optional[str] = Query(None),
):
    """
    Détail d'une facture (avec ses lignes d'articles).

    Si role != 'admin' et que la facture n'appartient pas à user_id,
    on renvoie 404 (comme si la facture n'existait pas), pour ne pas
    révéler à un employé l'existence de factures d'autres utilisateurs.
    """
    try:
        invoice = get_invoice_by_id(invoice_id, user_id=user_id, role=role)
        if not invoice:
            raise HTTPException(status_code=404, detail="Facture introuvable")
        return {"success": True, "invoice": invoice}
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Erreur de lecture : {e}")


# ---------------------------------------------------------------------------
# 4. Endpoint de recherche intelligente
# ---------------------------------------------------------------------------

@app.post("/api/search")
async def search(payload: SearchQuery):
    """
    Lance l'agent de recherche intelligente (intention + recherche multi-stratégie
    + réponse en langage naturel) sur la requête utilisateur.
    Nécessite une licence valide.
    """
    license_status = check_license(payload.licence_key)
    if not license_status["valid"]:
        raise HTTPException(
            status_code=403,
            detail=f"Licence invalide : {license_status['reason']}",
        )

    if not payload.query or not payload.query.strip():
        raise HTTPException(status_code=400, detail="Requête vide")

    try:
        result = run_search_agent(payload.query, user_id=payload.user_id, role=payload.role)
        return {"success": True, **result}
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Erreur de recherche : {e}")


# ---------------------------------------------------------------------------
# 5. Endpoint de vérification de licence
#    Appelé par Laminas AVANT chaque action IA (extraction, recherche)
# ---------------------------------------------------------------------------

@app.post("/api/license/verify")
async def verify_license(payload: LicenseCheckRequest):
    """
    Vérifie la validité d'une licence_key auprès de la base de l'éditeur
    (invoices_db.licences). Ne touche pas à erp_client_db.
    """
    result = check_license(payload.licence_key)
    return result


@app.post("/api/products/check")
async def check_product(product: ProductRequest):

    existing = find_product(product.description)

    if existing:

        return {
            "exists": True,
            "product_id": existing["id"],
            "product_name": existing["name"]
        }

    suggestions = search_similar_products(product.description)

    return {
        "exists": False,
        "suggestions": suggestions
    }
# ---------------------------------------------------------------------------
# 6. Healthcheck (pour vérifier que l'API tourne, utile pour Django/Laminas)
# ---------------------------------------------------------------------------

@app.get("/api/health")
async def health():
    return {"status": "ok", "service": "ERP-AI Agents API"}