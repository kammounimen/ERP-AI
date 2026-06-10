# 🧾 ERP-AI — Extraction & Recherche Intelligente de Factures

> Système intelligent d'extraction automatique de données de factures (PDF, images)
> et de recherche avancée multi-stratégie propulsé par **Mistral AI**.

---

## 📌 Table des matières

1. [Vue d'ensemble](#vue-densemble)
2. [Fonctionnalités](#fonctionnalités)
3. [Architecture du projet](#architecture-du-projet)
4. [Prérequis](#prérequis)
5. [Installation](#installation)
6. [Configuration](#configuration)
7. [Base de données](#base-de-données)
8. [Utilisation](#utilisation)
9. [Agent de recherche intelligente](#agent-de-recherche-intelligente)
10. [Exemples de recherche](#exemples-de-recherche)
11. [Flux de traitement](#flux-de-traitement)
12. [Gestion des erreurs](#gestion-des-erreurs)
13. [Technologies utilisées](#technologies-utilisées)

---

## Vue d'ensemble

**ERP-AI** est un système Python qui automatise deux tâches critiques en entreprise :

**1. Extraction automatique** — Lit des factures au format PDF ou image, extrait toutes les données structurées (fournisseur, client, montants, articles, dates...) en utilisant l'IA Mistral, et les stocke en base de données MySQL.

**2. Recherche intelligente** — Permet de retrouver n'importe quelle facture par une recherche en langage naturel, tolérante aux fautes de frappe, aux variations de casse et aux accents, grâce à un agent IA à 3 niveaux de recherche.

```
Facture PDF/Image  →  Extraction IA  →  Base MySQL  →  Recherche Agent IA
```

---

## Fonctionnalités

### 🔍 Extraction de factures
- Lecture de **PDF natifs** (avec couche texte)
- Lecture de **PDF scannés** (conversion en images via PyMuPDF)
- Lecture d'**images** directes (JPG, PNG, WEBP)
- Extraction structurée via **Mistral AI** (numéro, dates, fournisseur, client, articles, montants, TVA, devise...)
- Sauvegarde automatique en **base de données MySQL**
- Traitement **unitaire** ou en **lot** (dossier entier)

### 🤖 Agent de recherche intelligente
- **Détection automatique de l'intention** (fournisseur ? client ? numéro ? montant ?)
- **3 stratégies de recherche en cascade** :
  - Exacte → Partielle → Floue (Fuzzy)
- **Tolérance aux variations** :
  - Casse (`TECH SOLUTIONS` = `tech solutions`)
  - Accents (`Rénovations` = `renovations`)
  - Fautes de frappe (`teck store` → `Tech Store Tunisia`)
  - Mots partiels (`tech store` → `Tech Store Tunisia`)
- **Réponse en langage naturel** générée par Mistral AI
- **Fallback local** automatique si l'API est indisponible (Rate Limit)
- **Retry automatique** avec backoff exponentiel sur erreur 429

---

## Architecture du projet

```
ERP-AI/
│
├── 📄 main.py                        # Point d'entrée principal (CLI)
├── ⚙️  config.py                      # Configuration (DB, clés API)
├── 📋 requirements.txt               # Dépendances Python
├── 🗄️  schema.sql                     # Schéma de la base de données MySQL
├── 📁 invoices/                      # Dossier des factures à traiter
│   ├── facture1.jpg
│   ├── facture2.jpg
│   └── facture3.jpg
│
└── 📦 extractor/                     # Package principal
    ├── __init__.py
    ├── 📄 pdf_extractor.py           # Extraction texte/images depuis PDF & images
    ├── 🤖 ai_parser.py               # Analyse IA via Mistral API → JSON structuré
    ├── 🗃️  db_handler.py              # Opérations base de données MySQL
    ├── 🔎 search_engine.py           # Moteur de recherche (exact / partiel / fuzzy)
    ├── 🧹 search_normalizer.py       # Normalisation texte (accents, casse, espaces)
    └── 🕵️  search_agent.py            # Agent IA de recherche (orchestration Mistral)
```

### Rôle de chaque fichier

| Fichier | Rôle |
|---|---|
| `main.py` | CLI : traite un fichier, un dossier, ou lance la recherche |
| `config.py` | Lit les variables d'environnement (`.env`) |
| `pdf_extractor.py` | Extrait le texte et/ou les images d'un PDF ou d'une image |
| `ai_parser.py` | Envoie le contenu à Mistral et retourne un JSON structuré |
| `db_handler.py` | Sauvegarde et récupère les factures en MySQL |
| `search_normalizer.py` | Supprime accents, normalise la casse, tokenise |
| `search_engine.py` | Exécute les 3 stratégies de recherche sur la BDD |
| `search_agent.py` | Orchestre l'analyse d'intention + recherche + réponse naturelle |

---

## Prérequis

- Python **3.11+**
- MySQL **8.0+** (ou MariaDB 10.6+)
- Tesseract OCR (optionnel, pour PDF scannés en fallback)
- Compte **Mistral AI** avec clé API → [console.mistral.ai](https://console.mistral.ai)

---

## Installation

**1. Cloner le projet**
```bash
git clone https://github.com/votre-user/ERP-AI.git
cd ERP-AI
```

**2. Créer et activer l'environnement virtuel**
```bash
python -m venv venv

# Windows
venv\Scripts\activate

# Linux / macOS
source venv/bin/activate
```

**3. Installer les dépendances**
```bash
pip install -r requirements.txt
```

---

## Configuration

**Créer le fichier `.env`** à la racine du projet :

```env
# ── Mistral AI ─────────────────────────────────────────
# Obtenir la clé sur : https://console.mistral.ai → API Keys
MISTRAL_API_KEY=votre_cle_mistral_ici

# ── Base de données MySQL ───────────────────────────────
DB_HOST=localhost
DB_USER=root
DB_PASSWORD=votre_mot_de_passe
DB_NAME=invoices_db
```

> ⚠️ Ne jamais committer le fichier `.env`. Ajoutez-le à votre `.gitignore`.

---

## Base de données

**Créer la base de données et les tables :**

```bash
mysql -u root -p < schema.sql
```

Cela crée deux tables :

**`invoices`** — Données principales de la facture
```
id, invoice_number, invoice_date, due_date,
vendor_name, vendor_address, vendor_email, vendor_phone,
client_name, client_address,
subtotal, tax_rate, tax_amount, total_amount,
currency, payment_method, notes,
raw_text, source_file, created_at
```

**`invoice_items`** — Lignes articles de chaque facture
```
id, invoice_id, description, quantity, unit_price, total_price
```

---

## Utilisation

### Traiter une facture unique
```bash
python main.py facture.pdf
python main.py facture.jpg
python main.py invoices/facture2.png
```

### Traiter un dossier entier
```bash
# Dossier par défaut : invoices/
python main.py

# Dossier personnalisé
python main.py chemin/vers/dossier/
```

### Recherche directe (une requête)
```bash
python main.py --search "tech store tunisia"
python main.py --search "INV-2026-001"
python main.py --search "client Imen Kammoun"
```

### Mode interactif (recherches en boucle)
```bash
python main.py --search-cli
```

---

## Agent de recherche intelligente

L'agent fonctionne en **3 étapes automatiques** à chaque recherche :

```
Requête utilisateur
       │
       ▼
┌─────────────────────────────────────────┐
│  ÉTAPE 1 — Analyse de l'intention       │
│  Mistral AI détecte :                   │
│  · Type de recherche (vendeur, client,  │
│    numéro, montant, date...)            │
│  · Champs MySQL à interroger            │
│  · Texte normalisé pour la recherche   │
│  [Fallback local si API indisponible]   │
└─────────────────────────────────────────┘
       │
       ▼
┌─────────────────────────────────────────┐
│  ÉTAPE 2 — Recherche en cascade         │
│                                         │
│  1. Exacte    → LOWER(champ) = query    │
│     ↓ si aucun résultat                 │
│  2. Partielle → LIKE '%token%'          │
│     + filtre qualité (≥80% tokens)      │
│     ↓ si aucun résultat                 │
│  3. Floue     → RapidFuzz (score ≥78%) │
│     ratio / partial / token_sort /      │
│     token_set                           │
└─────────────────────────────────────────┘
       │
       ▼
┌─────────────────────────────────────────┐
│  ÉTAPE 3 — Réponse naturelle            │
│  Mistral formate les résultats en       │
│  langage naturel clair et professionnel │
│  [Fallback texte si API indisponible]   │
└─────────────────────────────────────────┘
       │
       ▼
  Résultats affichés + détail factures
```

### Normalisation du texte

Avant toute comparaison, le texte est normalisé :

| Étape | Exemple |
|---|---|
| Minuscules | `TUNISIE TÉLÉCOM` → `tunisie télécom` |
| Suppression accents | `tunisie télécom` → `tunisie telecom` |
| Nettoyage ponctuation | `S.A.R.L.` → `sarl` |
| Normalisation espaces | `tech  store` → `tech store` |

---

## Exemples de recherche

Les exemples ci-dessous sont basés sur une base contenant :
- **Tech Store Tunisia** (INV-2026-001)
- **TECH SOLUTIONS** (INV-2025-0458)
- **ABC Rénovations SARL** (ID: 3)

### Recherches exactes (score 100%)
```bash
python main.py --search "tech store tunisia"    # → Tech Store Tunisia ✅
python main.py --search "TECH SOLUTIONS"        # → TECH SOLUTIONS ✅
python main.py --search "INV-2026-001"          # → Tech Store Tunisia ✅
```

### Recherches partielles
```bash
python main.py --search "tech"                  # → Tech Store Tunisia + TECH SOLUTIONS ✅
python main.py --search "tech store"            # → Tech Store Tunisia ✅
python main.py --search "abc renovations"       # → ABC Rénovations SARL ✅
python main.py --search "renovations"           # → ABC Rénovations SARL ✅
```

### Recherches avec fautes de frappe (fuzzy)
```bash
python main.py --search "teck store tunisie"    # → Tech Store Tunisia (91.4%) ✅
python main.py --search "tech stor tunisa"      # → Tech Store Tunisia (85%) ✅
python main.py --search "tec solutions"         # → TECH SOLUTIONS (96.3%) ✅
python main.py --search "abc renovation"        # → ABC Rénovations SARL ✅
```

### Recherches par client
```bash
python main.py --search "client Imen Kammoun"   # → INV-2026-001 ✅
python main.py --search "Imen"                  # → INV-2026-001 ✅
```

### Recherches par numéro
```bash
python main.py --search "INV-2025"              # → TECH SOLUTIONS ✅
python main.py --search "2026"                  # → Tech Store Tunisia ✅
```

### Mode interactif
```
🔎 Recherche > tech
  → 2 factures trouvées (Tech Store Tunisia + TECH SOLUTIONS)

🔎 Recherche > teck store tunisie
  → 1 facture trouvée (fuzzy 91.4% — Tech Store Tunisia)

🔎 Recherche > INV-2026-001
  → 1 facture trouvée (exacte 100%)

🔎 Recherche > exit
  → 👋 Au revoir !
```

---

## Flux de traitement

### Extraction d'une facture

```
Fichier (PDF / JPG / PNG)
         │
         ▼
   pdf_extractor.py
   ┌─────────────────────────────┐
   │ PDF natif  → texte brut     │
   │ PDF scanné → images base64  │
   │ Image      → base64         │
   └─────────────────────────────┘
         │
         ▼
    ai_parser.py
   ┌─────────────────────────────┐
   │ Envoi à Mistral AI          │
   │ (texte + images)            │
   │ Retour JSON structuré       │
   └─────────────────────────────┘
         │
         ▼
   db_handler.py
   ┌─────────────────────────────┐
   │ INSERT INTO invoices        │
   │ INSERT INTO invoice_items   │
   │ Retourne invoice_id         │
   └─────────────────────────────┘
```

### Modèles Mistral utilisés

| Usage | Modèle |
|---|---|
| Extraction PDF texte | `mistral-large-latest` |
| Extraction PDF scanné / image | `pixtral-large-latest` (vision) |
| Analyse d'intention de recherche | `mistral-large-latest` |
| Formulation de la réponse | `mistral-large-latest` |

---

## Gestion des erreurs

### Rate Limit API (erreur 429)
L'agent retente automatiquement avec un délai croissant :

```
Tentative 1 échoue → attente  3 secondes
Tentative 2 échoue → attente  8 secondes
Tentative 3 échoue → attente 20 secondes
Tentative 4 échoue → attente 40 secondes
                   → Bascule sur fallback local
```

### Fallback local
Si Mistral AI est totalement indisponible :
- L'**analyse d'intention** est faite par règles regex locales
- La **réponse** est formatée en texte structuré sans LLM
- La **recherche en BDD** continue de fonctionner normalement

### Formats non supportés
Seuls les formats suivants sont acceptés : `.pdf`, `.jpg`, `.jpeg`, `.png`, `.webp`

---

## Technologies utilisées

| Technologie | Version | Usage |
|---|---|---|
| **Python** | 3.11+ | Langage principal |
| **Mistral AI API** | `mistral-large-latest` | Extraction & agent recherche |
| **Pixtral** | `pixtral-large-latest` | Vision (PDF scannés & images) |
| **MySQL** | 8.0+ | Stockage des factures |
| **PyMuPDF** (fitz) | 1.24+ | Conversion PDF → images |
| **pdfplumber** | 0.11+ | Extraction texte PDF natif |
| **RapidFuzz** | 3.6+ | Recherche floue (Levenshtein) |
| **PyMySQL** | 1.1+ | Connecteur MySQL Python |
| **Pillow** | 10.0+ | Traitement d'images |
| **pytesseract** | 0.3+ | OCR fallback |
| **python-dotenv** | 1.0+ | Gestion variables d'environnement |
| **requests** | 2.31+ | Appels HTTP vers Mistral API |

---

## Auteur

Projet développé dans le cadre d'un système ERP intelligent pour l'automatisation
du traitement et de la gestion des factures.