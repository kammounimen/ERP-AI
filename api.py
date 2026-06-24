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

from fastapi import FastAPI, UploadFile, File, HTTPException, Query
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel

from extractor.pdf_extractor import extract_from_file
from extractor.ai_parser import parse_invoice
from extractor.db_handler import save_invoice, list_invoices, get_invoice_by_id
from extractor.search_agent import run_search_agent


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


class InvoiceValidated(BaseModel):
    """
    Données envoyées par Laminas APRÈS que l'utilisateur ait vérifié/corrigé
    le formulaire dans l'interface ERP.
    """
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


# ---------------------------------------------------------------------------
# 1. Endpoint d'extraction : upload PDF/image → JSON brut extrait par l'IA
#    (Laminas affichera ce JSON dans un formulaire éditable, PAS encore sauvegardé)
# ---------------------------------------------------------------------------

@app.post("/api/extract")
async def extract_invoice(file: UploadFile = File(...)):
    """
    Reçoit un fichier (PDF/JPG/PNG), lance l'extraction + l'analyse Mistral,
    et retourne les données structurées brutes pour que l'utilisateur les valide.
    Ne sauvegarde RIEN en base à cette étape.
    """
    allowed_ext = (".pdf", ".jpg", ".jpeg", ".png", ".webp")
    ext = os.path.splitext(file.filename)[1].lower()

    if ext not in allowed_ext:
        raise HTTPException(
            status_code=400,
            detail=f"Format non supporté : {ext}. Acceptés : {allowed_ext}",
        )

    # Sauvegarde temporaire du fichier uploadé sur le disque
    tmp_dir = tempfile.mkdtemp(prefix="erp_upload_")
    tmp_path = os.path.join(tmp_dir, file.filename)

    try:
        with open(tmp_path, "wb") as f:
            shutil.copyfileobj(file.file, f)

        extracted = extract_from_file(tmp_path)

        if not extracted["text"] and not extracted["images_b64"]:
            raise HTTPException(
                status_code=422,
                detail="Impossible d'extraire du contenu de ce fichier.",
            )

        invoice_data = parse_invoice(extracted)

        return {
            "success": True,
            "source_file": file.filename,
            "raw_text": extracted.get("text", ""),
            "data": invoice_data,
        }

    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Erreur d'extraction : {e}")
    finally:
        shutil.rmtree(tmp_dir, ignore_errors=True)


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
        data["items"] = items

        invoice_id = save_invoice(
            data=data,
            raw_text=data.get("raw_text", ""),
            source_file=data.get("source_file", ""),
        )
        return {"success": True, "invoice_id": invoice_id}

    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Erreur de sauvegarde : {e}")


# ---------------------------------------------------------------------------
# 3. Endpoints de lecture : liste + détail (pour Dashboard et Historique)
# ---------------------------------------------------------------------------

@app.get("/api/invoices")
async def get_invoices(limit: int = Query(50, le=200), offset: int = Query(0, ge=0)):
    """Liste paginée des factures (utilisé par le Dashboard / Historique)."""
    try:
        invoices = list_invoices(limit=limit, offset=offset)
        return {"success": True, "count": len(invoices), "results": invoices}
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Erreur de lecture : {e}")


@app.get("/api/invoices/{invoice_id}")
async def get_invoice(invoice_id: int):
    """Détail d'une facture (avec ses lignes d'articles)."""
    try:
        invoice = get_invoice_by_id(invoice_id)
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
    """
    if not payload.query or not payload.query.strip():
        raise HTTPException(status_code=400, detail="Requête vide")

    try:
        result = run_search_agent(payload.query)
        return {"success": True, **result}
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Erreur de recherche : {e}")


# ---------------------------------------------------------------------------
# 5. Healthcheck (pour vérifier que l'API tourne, utile pour Django/Laminas)
# ---------------------------------------------------------------------------

@app.get("/api/health")
async def health():
    return {"status": "ok", "service": "ERP-AI Agents API"}