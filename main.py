"""
main.py
-------
Point d'entrée principal du projet ERP-AI.
Modes disponibles :
  python main.py                    → Traite le dossier invoices/
  python main.py facture.pdf        → Traite un fichier
  python main.py --search "query"   → Lance l'agent de recherche
  python main.py --search-cli       → Mode interactif de recherche
"""

import os
import sys
import json

from extractor.pdf_extractor import extract_from_file
from extractor.ai_parser     import parse_invoice
from extractor.db_handler    import save_invoice


# ---------------------------------------------------------------------------
# Traitement d'une facture
# ---------------------------------------------------------------------------

def process_invoice(file_path: str) -> int:
    print(f"\n📄 Traitement : {file_path}")

    print("  → Extraction du contenu...")
    extracted = extract_from_file(file_path)

    if not extracted["text"] and not extracted["images_b64"]:
        raise ValueError("Impossible d'extraire du contenu de ce fichier.")

    print("  → Analyse avec Mistral AI...")
    invoice_data = parse_invoice(extracted)

    print(f"  ✅ Facture N°  : {invoice_data.get('invoice_number') or 'N/A'}")
    print(f"     Fournisseur : {invoice_data.get('vendor_name')    or 'N/A'}")
    print(f"     Client      : {invoice_data.get('client_name')    or 'N/A'}")
    print(f"     Total       : {invoice_data.get('total_amount')} {invoice_data.get('currency') or ''}")
    print(f"     Lignes      : {len(invoice_data.get('items', []))}")

    print("  → Sauvegarde en base de données...")
    invoice_id = save_invoice(
        data=invoice_data,
        raw_text=extracted.get("text", ""),
        source_file=os.path.basename(file_path),
    )
    print(f"  💾 Sauvegardé avec ID : {invoice_id}")
    return invoice_id


def process_folder(folder_path: str):
    extensions = (".pdf", ".jpg", ".jpeg", ".png", ".webp")
    files = [
        os.path.join(folder_path, f)
        for f in sorted(os.listdir(folder_path))
        if f.lower().endswith(extensions)
    ]

    if not files:
        print(f"Aucune facture trouvée dans '{folder_path}'.")
        return

    print(f"🔍 {len(files)} facture(s) trouvée(s)")
    success, errors = 0, 0

    for file_path in files:
        try:
            process_invoice(file_path)
            success += 1
        except Exception as e:
            print(f"  ❌ Erreur sur {os.path.basename(file_path)}: {e}")
            errors += 1

    print(f"\n{'='*45}")
    print(f"✅ Terminé : {success} réussi(s), {errors} erreur(s)")


# ---------------------------------------------------------------------------
# Mode recherche
# ---------------------------------------------------------------------------

def run_search(query: str):
    """Exécute l'agent de recherche sur une requête unique."""
    from extractor.search_agent import run_search_agent

    result = run_search_agent(query)

    print(f"\n{'='*50}")
    print(f"🤖 Réponse de l'agent :")
    print(f"{'='*50}")
    print(result["natural_response"])
    print(f"{'─'*50}")
    print(f"   Intent    : {result['intent']}")
    print(f"   Stratégie : {result['strategy']}")
    print(f"   Résultats : {result['count']}")

    if result["results"]:
        print(f"\n📋 Détail des résultats :")
        for i, r in enumerate(result["results"][:10], 1):
            score = r.get("_score", "?")
            print(f"\n  [{i}] ID:{r.get('id')} | Score:{score}%")
            print(f"       N° Facture  : {r.get('invoice_number') or 'N/A'}")
            print(f"       Fournisseur : {r.get('vendor_name')    or 'N/A'}")
            print(f"       Client      : {r.get('client_name')    or 'N/A'}")
            print(f"       Montant     : {r.get('total_amount')} {r.get('currency') or ''}")
            print(f"       Date        : {r.get('invoice_date')   or 'N/A'}")


def run_search_cli():
    """Mode interactif : l'utilisateur tape ses recherches en boucle."""
    from extractor.search_agent import run_search_agent

    print("\n" + "="*50)
    print("🤖  Agent de Recherche ERP-AI  (Mistral AI)")
    print("="*50)
    print("Tapez votre recherche (ex: 'tunisie telecom', 'FAC-2024-001')")
    print("Commandes : 'quitter' ou 'exit' pour arrêter\n")

    while True:
        try:
            query = input("🔎 Recherche > ").strip()
        except (KeyboardInterrupt, EOFError):
            print("\n👋 Au revoir !")
            break

        if not query:
            continue
        if query.lower() in ("quitter", "exit", "quit", "q"):
            print("👋 Au revoir !")
            break

        try:
            run_search(query)
        except Exception as e:
            print(f"❌ Erreur : {e}")

        print()


# ---------------------------------------------------------------------------
# CLI principal
# ---------------------------------------------------------------------------

if __name__ == "__main__":
    args = sys.argv[1:]

    if not args:
        process_folder("invoices/")

    elif args[0] == "--search" and len(args) >= 2:
        run_search(" ".join(args[1:]))

    elif args[0] == "--search-cli":
        run_search_cli()

    elif os.path.isdir(args[0]):
        process_folder(args[0])

    elif os.path.isfile(args[0]):
        process_invoice(args[0])

    else:
        print(f"❌ Argument invalide : '{args[0]}'")
        print()
        print("Usage :")
        print("  python main.py                        → Dossier invoices/")
        print("  python main.py facture.pdf            → Fichier unique")
        print("  python main.py chemin/dossier/        → Dossier personnalisé")
        print("  python main.py --search 'tunisie tel' → Recherche directe")
        print("  python main.py --search-cli           → Mode interactif")
        sys.exit(1)