import os
import sys
from extractor.pdf_extractor import extract_from_file   
from extractor.ai_parser import parse_invoice           
from extractor.db_handler import save_invoice           


def process_invoice(file_path: str) -> int:
    """Traite une facture : extraction → IA → BDD."""
    print(f"\n📄 Traitement : {file_path}")

    # 1. Extraire le contenu (texte + images)
    print("  → Extraction du contenu...")
    extracted = extract_from_file(file_path)

    if not extracted["text"] and not extracted["images_b64"]:
        raise ValueError("Impossible d'extraire du contenu de ce fichier.")

    # 2. Analyser avec Mistral
    print("  → Analyse avec Mistral AI...")
    invoice_data = parse_invoice(extracted)

    # 3. Afficher un aperçu
    print(f"  ✅ Facture N° : {invoice_data.get('invoice_number') or 'N/A'}")
    print(f"     Fournisseur : {invoice_data.get('vendor_name') or 'N/A'}")
    print(f"     Client      : {invoice_data.get('client_name') or 'N/A'}")
    print(f"     Total       : {invoice_data.get('total_amount')} {invoice_data.get('currency') or ''}")
    print(f"     Lignes      : {len(invoice_data.get('items', []))}")

    # 4. Sauvegarder en BDD
    print("  → Sauvegarde en base de données...")
    invoice_id = save_invoice(
        data=invoice_data,
        raw_text=extracted.get("text", ""),
        source_file=os.path.basename(file_path)
    )
    print(f"  💾 Sauvegardé avec ID : {invoice_id}")
    return invoice_id


def process_folder(folder_path: str):
    """Traite tous les fichiers d'un dossier."""
    extensions = (".pdf", ".jpg", ".jpeg", ".png", ".webp")
    files = [
        os.path.join(folder_path, f)
        for f in sorted(os.listdir(folder_path))
        if f.lower().endswith(extensions)
    ]

    if not files:
        print(f"Aucune facture trouvée dans '{folder_path}'.")
        return

    print(f"🔍 {len(files)} facture(s) trouvée(s) dans '{folder_path}'")
    success, errors = 0, 0

    for file_path in files:
        try:
            process_invoice(file_path)
            success += 1
        except Exception as e:
            print(f"  ❌ Erreur sur {os.path.basename(file_path)}: {e}")
            errors += 1

    print(f"\n{'='*40}")
    print(f"✅ Terminé : {success} réussi(s), {errors} erreur(s)")


if __name__ == "__main__":
    if len(sys.argv) < 2:
        # Mode dossier par défaut
        process_folder("invoices/")
    else:
        path = sys.argv[1]
        if os.path.isdir(path):
            process_folder(path)
        elif os.path.isfile(path):
            process_invoice(path)
        else:
            print(f"❌ Chemin introuvable : {path}")
            sys.exit(1)