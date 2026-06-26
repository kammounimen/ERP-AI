"""
extractor/file_security.py
--------------------------
Couche de sécurité complète pour la validation des fichiers uploadés.

Protections implémentées :
  1. Limite de taille (avant tout traitement)
  2. Détection du vrai type par magic bytes (pas par extension)
  3. Images : verify() + réencodage complet Pillow (détruit polyglottes/EXIF)
  4. Images : limite dimensions et nombre de pixels (decompression bomb)
  5. PDF : vérification structure PyMuPDF
  6. PDF : détection JavaScript embarqué
  7. PDF : limite nombre de pages
  8. PDF : refus des PDF chiffrés/protégés
  9. Scan antivirus ClamAV (optionnel — activé si clamd est disponible)
 10. Renommage UUID systématique (jamais le nom original)
 11. Journalisation des rejets

Usage dans api.py :
    from extractor.file_security import validate_and_sanitize_file, SecurityError

    safe_path = validate_and_sanitize_file(raw_tmp_path, original_filename)
    # safe_path est le chemin vers le fichier nettoyé, prêt pour extract_from_file()
"""

import io
import logging
import os
import shutil
import tempfile
import uuid
from datetime import datetime
from pathlib import Path

# ---------------------------------------------------------------------------
# Configuration — modifier ces constantes selon tes besoins
# ---------------------------------------------------------------------------

MAX_FILE_SIZE_BYTES   = 50 * 1024 * 1024   # 50 Mo
MAX_IMAGE_WIDTH_PX    = 10_000             # pixels
MAX_IMAGE_HEIGHT_PX   = 10_000             # pixels
MAX_IMAGE_PIXELS      = 50_000_000         # 50 Mpx (width × height)
MAX_PDF_PAGES         = 300
ENABLE_CLAMAV         = False            # mettre False pour désactiver ClamAV

# Extensions déclarées acceptées → types MIME réels attendus
# Choix volontairement restrictif : formats utiles pour les factures uniquement
ALLOWED_MIME = {
    ".pdf":  "application/pdf",
    ".jpg":  "image/jpeg",
    ".jpeg": "image/jpeg",
    ".png":  "image/png",
    ".tif":  "image/tiff",
    ".tiff": "image/tiff",
    # .webp, .bmp, .heic : non acceptés (surface d'attaque inutile pour les factures)
    # .gif, .svg, .exe, .php, .zip ... : refusés implicitement (pas dans cette liste)
}

# Familles de MIME (utilisées dans _check_magic_bytes)
IMAGE_MIMES = {"image/jpeg", "image/png", "image/tiff"}
PDF_MIMES   = {"application/pdf"}

# Signatures binaires (magic bytes) pour chaque MIME
MAGIC_SIGNATURES: dict[str, list[bytes]] = {
    "application/pdf": [b"%PDF"],
    "image/jpeg":      [b"\xff\xd8\xff"],
    "image/png":       [b"\x89PNG\r\n\x1a\n"],
    "image/tiff":      [b"II*\x00", b"MM\x00*"],  # little-endian et big-endian
}

# ---------------------------------------------------------------------------
# Logger dédié — écrit dans le fichier de log applicatif
# ---------------------------------------------------------------------------

logger = logging.getLogger("file_security")
if not logger.handlers:
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    )

# Fichier de log des rejets (en plus du logger applicatif)
REJECTION_LOG_PATH = os.environ.get("SECURITY_REJECTION_LOG", "/tmp/erp_rejected_uploads.log")


# ---------------------------------------------------------------------------
# Exception dédiée
# ---------------------------------------------------------------------------

class SecurityError(Exception):
    """Levée quand un fichier échoue à la validation de sécurité."""


# ---------------------------------------------------------------------------
# Helpers internes
# ---------------------------------------------------------------------------

def _log_rejection(filename: str, reason: str) -> None:
    """Journalise chaque rejet dans le fichier de log dédié ET dans le logger."""
    entry = f"{datetime.utcnow().isoformat()} | REJECTED | file={filename!r} | reason={reason}\n"
    logger.warning("Upload rejeté — %s — %s", filename, reason)
    try:
        with open(REJECTION_LOG_PATH, "a", encoding="utf-8") as fh:
            fh.write(entry)
    except OSError:
        pass  # ne pas planter si le log est inaccessible


def _detect_mime_by_magic(file_path: str) -> str | None:
    """
    Lit les premiers octets du fichier et retourne le MIME détecté,
    ou None si la signature n est pas reconnue (script, executable, archive...).
    """
    with open(file_path, "rb") as fh:
        header = fh.read(16)

    for mime, sigs in MAGIC_SIGNATURES.items():
        for sig in sigs:
            if header.startswith(sig):
                return mime
    return None


# ---------------------------------------------------------------------------
# Validations par type
# ---------------------------------------------------------------------------

def _check_file_size(file_path: str, filename: str) -> None:
    size = os.path.getsize(file_path)
    if size == 0:
        _log_rejection(filename, "fichier vide (0 octet)")
        raise SecurityError("Le fichier est vide.")
    if size > MAX_FILE_SIZE_BYTES:
        _log_rejection(filename, f"taille {size} > limite {MAX_FILE_SIZE_BYTES}")
        raise SecurityError(
            f"Fichier trop volumineux ({size // (1024*1024)} Mo). "
            f"Limite : {MAX_FILE_SIZE_BYTES // (1024*1024)} Mo."
        )


def _check_magic_bytes(file_path: str, declared_ext: str, filename: str) -> str:
    """
    Vérifie que le contenu réel du fichier est bien une image ou un PDF.

    Règle :
      - Si l'extension est .pdf  → le contenu DOIT être un PDF (strict)
      - Si l'extension est image → le contenu DOIT être une image valide,
        peu importe le format exact (jpg déclaré mais tiff réel = OK, fréquent
        avec les scanners professionnels)
      - Contenu non reconnu (script, exe, archive...) → rejeté systématiquement
    """
    expected_mime = ALLOWED_MIME.get(declared_ext)
    real_mime     = _detect_mime_by_magic(file_path)

    # Contenu non reconnu → rejeté (PHP, EXE, ZIP, etc.)
    if real_mime is None:
        _log_rejection(filename, "signature binaire inconnue — ni image ni PDF reconnu")
        raise SecurityError(
            "Type de fichier non reconnu. "
            "Formats acceptés : PDF, JPEG, PNG, TIFF."
        )

    # PDF déclaré → doit être un vrai PDF
    if expected_mime in PDF_MIMES:
        if real_mime not in PDF_MIMES:
            _log_rejection(filename, f"extension .pdf mais contenu réel = {real_mime}")
            raise SecurityError(
                "Ce fichier a l'extension .pdf mais n'est pas un PDF valide. Fichier rejeté."
            )

    # Image déclarée → doit être une image (format exact peu importe)
    elif expected_mime in IMAGE_MIMES:
        if real_mime not in IMAGE_MIMES:
            _log_rejection(filename, f"extension image {declared_ext!r} mais contenu = {real_mime}")
            raise SecurityError(
                f"Ce fichier a une extension image ({declared_ext}) "
                f"mais son contenu réel est '{real_mime}'. Fichier rejeté."
            )
        if real_mime != expected_mime:
            logger.warning(
                "Extension %r != format réel %r pour '%s' — toléré (même famille image)",
                declared_ext, real_mime, filename
            )

    return real_mime


def _sanitize_image(file_path: str, filename: str, output_path: str) -> None:
    """
    Ouvre l'image avec Pillow, vérifie son intégrité, contrôle ses dimensions,
    puis la réencode dans un nouveau fichier propre (élimine tout payload caché).
    """
    try:
        from PIL import Image, UnidentifiedImageError
    except ImportError:
        raise RuntimeError("Pillow non installé. pip install pillow --break-system-packages")

    try:
        with Image.open(file_path) as img:
            # verify() détecte les fichiers tronqués/corrompus
            img.verify()

        # Après verify(), l'image doit être réouverte (Pillow la ferme en interne)
        with Image.open(file_path) as img:
            width, height = img.size

            # --- Vérification des dimensions ---
            if width > MAX_IMAGE_WIDTH_PX or height > MAX_IMAGE_HEIGHT_PX:
                _log_rejection(filename, f"dimensions {width}×{height} dépassent la limite")
                raise SecurityError(
                    f"Image trop grande ({width}×{height} px). "
                    f"Maximum autorisé : {MAX_IMAGE_WIDTH_PX}×{MAX_IMAGE_HEIGHT_PX} px."
                )

            total_pixels = width * height
            if total_pixels > MAX_IMAGE_PIXELS:
                _log_rejection(filename, f"{total_pixels} pixels > limite {MAX_IMAGE_PIXELS}")
                raise SecurityError(
                    f"Image trop lourde ({total_pixels:,} pixels). "
                    f"Limite : {MAX_IMAGE_PIXELS:,} pixels."
                )

            # --- Réencodage complet : on recrée l'image pixel par pixel ---
            # Convertir en RGB (élimine les couches alpha, les métadonnées, les profils ICC…)
            clean_img = img.convert("RGB")

        # Sauvegarde sans métadonnées (pas de exif=, pas de icc_profile=)
        ext = os.path.splitext(output_path)[1].lower()
        # Choisir le format de sortie selon l'extension déclarée
        # TIFF → TIFF (qualité maximale, utilisé par les scanners pro)
        # JPG/JPEG → JPEG
        # PNG et tout autre → PNG (sans perte)
        if ext in (".tif", ".tiff"):
            fmt = "TIFF"
            clean_img.save(output_path, format=fmt, compression="tiff_lzw")
        elif ext in (".jpg", ".jpeg"):
            fmt = "JPEG"
            clean_img.save(output_path, format=fmt, quality=92)
        else:
            fmt = "PNG"
            clean_img.save(output_path, format=fmt)

    except SecurityError:
        raise
    except Exception as exc:
        _log_rejection(filename, f"image invalide ou corrompue : {exc}")
        raise SecurityError(f"Fichier image invalide ou corrompu : {exc}")


def _validate_pdf(file_path: str, filename: str, output_path: str) -> None:
    """
    Valide un PDF avec PyMuPDF :
      - Refuse les PDF chiffrés/protégés
      - Limite le nombre de pages
      - Détecte le JavaScript embarqué
    Copie le fichier validé vers output_path (pas de réencodage PDF possible sans perte).
    """
    try:
        import fitz  # PyMuPDF
    except ImportError:
        raise RuntimeError("PyMuPDF non installé. pip install pymupdf --break-system-packages")

    try:
        doc = fitz.open(file_path)
    except Exception as exc:
        _log_rejection(filename, f"PDF illisible : {exc}")
        raise SecurityError(f"PDF invalide ou corrompu : {exc}")

    try:
        # --- Refus des PDF chiffrés ---
        if doc.is_encrypted:
            _log_rejection(filename, "PDF chiffré / protégé par mot de passe")
            raise SecurityError(
                "Les PDF chiffrés ou protégés par mot de passe ne sont pas acceptés."
            )

        # --- Limite du nombre de pages ---
        nb_pages = len(doc)
        if nb_pages > MAX_PDF_PAGES:
            _log_rejection(filename, f"{nb_pages} pages > limite {MAX_PDF_PAGES}")
            raise SecurityError(
                f"PDF trop long ({nb_pages} pages). Limite : {MAX_PDF_PAGES} pages."
            )

        # --- Détection du JavaScript embarqué ---
        # PyMuPDF expose les actions et scripts via get_page_xobjects / get_pdf_catalog
        # La méthode la plus complète : chercher /JS ou /JavaScript dans le catalogue PDF
        try:
            catalog = doc.pdf_catalog()           # dict Python des entrées du catalogue
            _check_pdf_dict_for_js(catalog, filename)
        except SecurityError:
            raise
        except Exception:
            pass  # si le catalogue n'est pas parsable, on continue (pas de JS détectable)

        # Vérification complémentaire : parcourir les objets PDF à la recherche de /JS
        for xref in range(1, doc.xref_length()):
            try:
                keys = doc.xref_get_keys(xref)
                if "JS" in keys or "JavaScript" in keys:
                    _log_rejection(filename, f"JavaScript embarqué détecté (xref={xref})")
                    raise SecurityError(
                        "Ce PDF contient du JavaScript embarqué et a été rejeté pour raison de sécurité."
                    )
                # Détecter les actions /Launch (exécution de commande OS)
                if "S" in keys:
                    s_val = doc.xref_get_key(xref, "S")
                    if "Launch" in str(s_val) or "SubmitForm" in str(s_val):
                        _log_rejection(filename, f"action dangereuse dans PDF (xref={xref}): {s_val}")
                        raise SecurityError(
                            "Ce PDF contient des actions dangereuses (Launch/SubmitForm) et a été rejeté."
                        )
            except SecurityError:
                raise
            except Exception:
                continue  # objet illisible → on ignore

    finally:
        doc.close()

    # PDF validé → copie simple (pas de réencodage pour ne pas altérer le contenu)
    shutil.copy2(file_path, output_path)


def _check_pdf_dict_for_js(obj: object, filename: str, depth: int = 0) -> None:
    """Parcourt récursivement un dict/list PyMuPDF à la recherche de clés JS."""
    if depth > 10:
        return
    if isinstance(obj, dict):
        for key, val in obj.items():
            if key in ("JS", "JavaScript"):
                _log_rejection(filename, f"JavaScript dans le catalogue PDF (clé={key!r})")
                raise SecurityError(
                    "Ce PDF contient du JavaScript embarqué et a été rejeté pour raison de sécurité."
                )
            _check_pdf_dict_for_js(val, filename, depth + 1)
    elif isinstance(obj, (list, tuple)):
        for item in obj:
            _check_pdf_dict_for_js(item, filename, depth + 1)


def _scan_with_clamav(file_path: str, filename: str) -> None:
    """
    Scan antivirus via clamd (socket Unix).
    Si ClamAV n'est pas disponible, on logue un avertissement et on continue.
    """
    if not ENABLE_CLAMAV:
        return
    try:
        import clamd  # pip install clamd --break-system-packages
    except ImportError:
        logger.warning("Module 'clamd' non installé — scan antivirus ignoré.")
        return

    try:
        cd = clamd.ClamdUnixSocket()  # ou ClamdNetworkSocket(host='127.0.0.1', port=3310)
        result = cd.scan(file_path)
        # result = {file_path: ('OK', None)} ou {file_path: ('FOUND', 'Eicar-Test-Signature')}
        status, virus_name = result.get(file_path, ("UNKNOWN", None))
        if status == "FOUND":
            _log_rejection(filename, f"virus détecté par ClamAV : {virus_name}")
            raise SecurityError(f"Fichier infecté détecté ({virus_name}). Upload refusé.")
        elif status not in ("OK", "UNKNOWN"):
            _log_rejection(filename, f"ClamAV a retourné un statut inattendu : {status}")
            raise SecurityError("L'analyse antivirus a échoué. Upload refusé par précaution.")
    except SecurityError:
        raise
    except Exception as exc:
        logger.warning("ClamAV indisponible (%s) — scan ignoré.", exc)


# ---------------------------------------------------------------------------
# Point d'entrée public
# ---------------------------------------------------------------------------

def validate_and_sanitize_file(raw_path: str, original_filename: str) -> str:
    """
    Valide et nettoie un fichier uploadé.

    Paramètres :
        raw_path           : chemin du fichier brut tel que reçu de FastAPI
        original_filename  : nom original déclaré par l'utilisateur (pour l'extension)

    Retourne :
        Le chemin du fichier sécurisé (dans un nouveau dossier tmp, avec nom UUID),
        prêt à être passé à extract_from_file().

    Lève :
        SecurityError si le fichier est suspect ou invalide.
        RuntimeError  si une dépendance requise est manquante.
    """
    # Nom sécurisé (UUID) — jamais le nom original
    declared_ext = os.path.splitext(original_filename)[1].lower()
    safe_name    = f"{uuid.uuid4().hex}{declared_ext}"

    # Dossier de sortie temporaire isolé
    out_dir  = tempfile.mkdtemp(prefix="erp_safe_")
    out_path = os.path.join(out_dir, safe_name)

    try:
        # Étape 1 — Taille
        _check_file_size(raw_path, original_filename)

        # Étape 2 — Magic bytes
        real_mime = _check_magic_bytes(raw_path, declared_ext, original_filename)

        # Étape 3 — Scan antivirus (avant d'ouvrir le fichier avec des parsers)
        _scan_with_clamav(raw_path, original_filename)

        # Étape 4 — Validation et nettoyage selon le type
        if real_mime == "application/pdf":
            _validate_pdf(raw_path, original_filename, out_path)
        else:
            # JPEG, PNG, WebP
            _sanitize_image(raw_path, original_filename, out_path)

        logger.info("Fichier accepté : %r → %r", original_filename, safe_name)
        return out_path

    except SecurityError:
        shutil.rmtree(out_dir, ignore_errors=True)
        raise
    except Exception as exc:
        shutil.rmtree(out_dir, ignore_errors=True)
        _log_rejection(original_filename, f"erreur inattendue : {exc}")
        raise SecurityError(f"Erreur lors de la validation du fichier : {exc}") from exc