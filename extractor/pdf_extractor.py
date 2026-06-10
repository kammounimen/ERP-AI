import os
import base64
import pdfplumber
import fitz  # PyMuPDF — pip install pymupdf


def extract_text_from_pdf(file_path: str) -> str:
    """Extrait le texte d'un PDF natif (avec couche texte)."""
    text = ""
    with pdfplumber.open(file_path) as pdf:
        for page in pdf.pages:
            page_text = page.extract_text()
            if page_text:
                text += page_text + "\n"
    return text.strip()


def extract_text_from_image_ocr(file_path: str) -> str:
    """Extrait le texte d'une image via OCR (Tesseract). Fallback uniquement."""
    try:
        import pytesseract
        from PIL import Image
        img = Image.open(file_path)
        text = pytesseract.image_to_string(img, lang='fra+eng')
        return text.strip()
    except ImportError:
        raise ImportError(
            "pytesseract ou Pillow non installé. "
            "Installe avec : pip install pytesseract pillow"
        )


def pdf_page_to_base64(file_path: str, page_num: int = 0, dpi: int = 200) -> str:
    """
    Convertit une page PDF en image base64 (JPEG) pour l'envoyer au LLM.
    dpi=200 donne un bon équilibre qualité/taille.
    """
    doc = fitz.open(file_path)

    if page_num >= len(doc):
        raise IndexError(f"Page {page_num} inexistante (total: {len(doc)} pages)")

    page = doc[page_num]
    # matrix pour le DPI (72 DPI natif PDF → scale = dpi/72)
    mat = fitz.Matrix(dpi / 72, dpi / 72)
    pix = page.get_pixmap(matrix=mat)
    img_bytes = pix.tobytes("jpeg")
    doc.close()

    return base64.b64encode(img_bytes).decode("utf-8")


def extract_from_file(file_path: str) -> dict:
    """
    Point d'entrée principal.
    Retourne {'text': str, 'images_b64': [str, ...]}

    Stratégie :
    - PDF avec texte → extrait le texte directement (plus fiable)
    - PDF scanné (pas de texte) → convertit les pages en images pour le LLM vision
    - Image (jpg/png/webp) → encode en base64 pour le LLM vision
    """
    if not os.path.exists(file_path):
        raise FileNotFoundError(f"Fichier introuvable : {file_path}")

    ext = os.path.splitext(file_path)[1].lower()
    result = {"text": "", "images_b64": []}

    if ext == ".pdf":
        # 1. Essayer d'extraire le texte natif
        text = extract_text_from_pdf(file_path)

        if len(text) > 50:  # PDF avec une couche texte exploitable
            result["text"] = text
            print(f"     [PDF texte] {len(text)} caractères extraits")
        else:
            # PDF scanné → convertir en images pour le LLM vision
            print("     [PDF scanné] Conversion en images...")
            doc = fitz.open(file_path)
            nb_pages = min(len(doc), 5)  # max 5 pages pour éviter les timeouts
            doc.close()

            for i in range(nb_pages):
                b64 = pdf_page_to_base64(file_path, i)
                result["images_b64"].append(b64)
                print(f"     [PDF scanné] Page {i+1}/{nb_pages} convertie")

    elif ext in (".jpg", ".jpeg", ".png", ".webp"):
        with open(file_path, "rb") as f:
            result["images_b64"].append(base64.b64encode(f.read()).decode("utf-8"))
        print(f"     [Image] Encodée en base64")

    else:
        raise ValueError(f"Format non supporté : {ext} (accepté : pdf, jpg, jpeg, png, webp)")

    return result