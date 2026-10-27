# 🧾 ERP-AI — Extraction & Recherche Intelligente de Factures

> Backend IA d'un ERP : extraction automatique de données de factures (PDF, images), recherche avancée multi-stratégie et API REST consommée par le frontend **Laminas (PHP)**, le tout propulsé par **Mistral AI**.

![Python](https://img.shields.io/badge/Python-3.11+-3776AB?logo=python&logoColor=white)
![FastAPI](https://img.shields.io/badge/FastAPI-API%20REST-009688?logo=fastapi&logoColor=white)
![MySQL](https://img.shields.io/badge/MySQL-8.0+-4479A1?logo=mysql&logoColor=white)
![Mistral AI](https://img.shields.io/badge/Mistral%20AI-LLM%20%2B%20Vision-FF7000)
![Frontend](https://img.shields.io/badge/Frontend-Laminas%20(PHP)-2B6CB0)

---

## 📌 Table des matières

1. [Vue d'ensemble](#vue-densemble)
2. [Écosystème : lien avec le frontend Laminas](#écosystème--lien-avec-le-frontend-laminas)
3. [Fonctionnalités](#fonctionnalités)
4. [Architecture du projet](#architecture-du-projet)
5. [Prérequis](#prérequis)
6. [Installation](#installation)
7. [Configuration](#configuration)
8. [Base de données](#base-de-données)
9. [Lancement de l'API REST](#lancement-de-lapi-rest)
10. [Référence des endpoints](#référence-des-endpoints)
11. [Sécurité](#sécurité)
12. [Utilisation en ligne de commande (CLI)](#utilisation-en-ligne-de-commande-cli)
13. [Agent de recherche intelligente](#agent-de-recherche-intelligente)
14. [Exemples de recherche](#exemples-de-recherche)
15. [Flux de traitement](#flux-de-traitement)
16. [Gestion des erreurs](#gestion-des-erreurs)
17. [Technologies utilisées](#technologies-utilisées)
18. [Dépannage](#dépannage)
19. [Feuille de route](#feuille-de-route)
20. [Auteur](#auteur)

---

## Vue d'ensemble

**ERP-AI** est un système Python qui automatise trois besoins critiques en entreprise :

**1. Extraction automatique** — Lit des factures PDF ou image, extrait les données structurées (fournisseur, client, montants, articles, dates…) grâce à Mistral AI.

**2. Recherche intelligente** — Retrouve n'importe quelle facture par une requête en langage naturel, tolérante aux fautes de frappe, à la casse et aux accents, grâce à un agent IA à 3 niveaux de recherche.

**3. API REST (FastAPI)** — Expose ces agents sous forme d'endpoints HTTP, afin que le frontend ERP Laminas puisse les appeler, avec **vérification de licence**, **contrôle d'accès par rôle** et **validation sécurisée des fichiers**.

```
Facture PDF/Image → Extraction IA → Validation humaine (Laminas) → MySQL → Recherche Agent IA
```

---

## Écosystème : lien avec le frontend Laminas

Ce dépôt est la partie **IA / backend** de la solution. L'interface utilisateur est dans le dépôt [`erp-ai-laminas`](https://github.com/kammounimen/erp-ai-laminas).

```
┌──────────────────────────┐   HTTP / JSON    ┌───────────────────────────┐
│  Frontend ERP (Laminas)  │ ───────────────► │  ERP-AI  (FastAPI :8001)  │
│  • Auth (JWT, sessions)  │                  │  • Extraction (Mistral)   │
│  • Formulaire de         │ ◄─────────────── │  • Agent de recherche     │
│    validation            │                  │  • Licences / Produits    │
│  • Dashboard/Historique  │                  └────────────┬──────────────┘
└──────────────────────────┘                               │
                                                           ▼
                                                  ┌─────────────────┐
                                                  │  MySQL          │
                                                  └─────────────────┘
```

**Principe clé — l'humain valide avant l'enregistrement :** l'endpoint d'extraction ne sauvegarde **rien** en base. Laminas affiche le JSON dans un formulaire éditable ; l'utilisateur corrige, puis Laminas envoie la facture validée à `POST /api/invoices`.

---

## Fonctionnalités

### 🔍 Extraction de factures

- Lecture de **PDF natifs** (couche texte) et de **PDF scannés** (conversion en images via PyMuPDF)
- Lecture d'**images** directes (JPG, PNG, TIFF)
- Extraction structurée via **Mistral AI** (numéro, dates, fournisseur, client, articles, montants, TVA, devise…)
- Sauvegarde en **MySQL** après validation utilisateur
- Traitement **unitaire** ou **par lot** (CLI)

### 🤖 Agent de recherche intelligente

- **Détection automatique de l'intention** (fournisseur ? client ? numéro ? montant ?)
- **3 stratégies en cascade** : Exacte → Partielle → Floue (fuzzy)
- **Tolérance** à la casse, aux accents, aux fautes de frappe et aux mots partiels
- **Réponse en langage naturel** générée par Mistral AI
- **Fallback local** si l'API est indisponible, et **retry avec backoff exponentiel** sur erreur 429

### 🏢 Fonctions ERP (API)

- 🔑 **Licences** : chaque action IA (extraction, recherche) exige une `licence_key` valide
- 👥 **Contrôle d'accès par rôle** : un `admin` voit toutes les factures, un employé uniquement les siennes
- 📦 **Gestion des produits** : détection des produits existants et suggestions de produits similaires avant création
- 🛡️ **Pipeline de sécurité des fichiers** (taille, magic bytes, antivirus, PDF/images assainis)

---

## Architecture du projet

```
ERP-AI/
│
├── 🌐 api.py                         # API FastAPI (endpoints consommés par Laminas)
├── 📄 main.py                        # Point d'entrée CLI
├── ⚙️  config.py                      # Configuration (DB, clés API)
├── 📋 requirements.txt               # Dépendances Python
├── 🔐 auth/                          # Module d'authentification
├── 📁 invoices/                      # Dossier des factures à traiter (CLI)
│
└── 📦 extractor/                     # Package principal
    ├── pdf_extractor.py              # Extraction texte/images depuis PDF & images
    ├── ai_parser.py                  # Analyse IA via Mistral → JSON structuré
    ├── db_handler.py                 # Opérations MySQL (factures, produits)
    ├── search_engine.py              # Moteur de recherche (exact / partiel / fuzzy)
    ├── search_normalizer.py          # Normalisation (accents, casse, espaces)
    ├── search_agent.py               # Agent IA de recherche (orchestration Mistral)
    ├── license_checker.py            # Vérification des licences clients
    └── file_security.py              # Validation & assainissement des fichiers uploadés
```

### Rôle de chaque fichier

| Fichier | Rôle |
|---|---|
| `api.py` | Expose les agents en endpoints HTTP (FastAPI + CORS + Swagger auto) |
| `main.py` | CLI : traite un fichier, un dossier, ou lance la recherche |
| `config.py` | Lit les variables d'environnement (`.env`) |
| `pdf_extractor.py` | Extrait texte et/ou images d'un PDF ou d'une image |
| `ai_parser.py` | Envoie le contenu à Mistral, retourne un JSON structuré |
| `db_handler.py` | Sauvegarde/lit factures et produits en MySQL |
| `license_checker.py` | Valide une `licence_key` auprès de la base éditeur |
| `file_security.py` | Valide et assainit tout fichier uploadé (voir [Sécurité](#sécurité)) |
| `search_normalizer.py` | Supprime accents, normalise la casse, tokenise |
| `search_engine.py` | Exécute les 3 stratégies de recherche |
| `search_agent.py` | Intention + recherche + réponse naturelle |

---

## Prérequis

- Python **3.11+**
- MySQL **8.0+** (ou MariaDB 10.6+)
- Compte **Mistral AI** avec clé API → [console.mistral.ai](https://console.mistral.ai)
- Tesseract OCR *(optionnel, fallback pour PDF scannés)*
- ClamAV *(optionnel, scan antivirus des fichiers uploadés)*

---

## Installation

```bash
# 1. Cloner le projet
git clone https://github.com/kammounimen/ERP-AI.git
cd ERP-AI

# 2. Environnement virtuel
python -m venv venv
# Windows
venv\Scripts\activate
# Linux / macOS
source venv/bin/activate

# 3. Dépendances
pip install -r requirements.txt

# 4. Dépendances de l'API REST
pip install fastapi uvicorn python-multipart
```

---

## Configuration

Créez un fichier **`.env`** à la racine :

```env
# ── Mistral AI ─────────────────────────────────────────
MISTRAL_API_KEY=votre_cle_mistral_ici

# ── Base de données MySQL ──────────────────────────────
DB_HOST=localhost
DB_USER=root
DB_PASSWORD=votre_mot_de_passe
DB_NAME=invoices_db
```

> ⚠️ Ne committez jamais `.env` : vérifiez qu'il figure dans `.gitignore`.

---

## Base de données

Créez la base et les tables (script SQL fourni par le projet) :

```bash
mysql -u root -p < schema.sql
```

**`invoices`** — données principales

```
id, invoice_number, invoice_date, due_date,
vendor_name, vendor_address, vendor_email, vendor_phone,
client_name, client_address,
subtotal, tax_rate, tax_amount, total_amount,
currency, payment_method, notes,
raw_text, source_file, created_by, created_at
```

**`invoice_items`** — lignes articles

```
id, invoice_id, description, quantity, unit_price, total_price, product_id
```

**Autres tables utilisées par l'API :** `licences` (base éditeur `invoices_db`) et la table des produits. La base client (`erp_client_db`) est séparée de la base éditeur.

> ✏️ Les colonnes `created_by` et `product_id` sont déduites du code de l'API ; vérifiez-les par rapport à votre `schema.sql`.

---

## Lancement de l'API REST

```bash
uvicorn api:app --reload --port 8001
```

| Ressource | URL |
|---|---|
| API | http://127.0.0.1:8001 |
| Documentation Swagger (interactive) | http://127.0.0.1:8001/docs |
| Healthcheck | http://127.0.0.1:8001/api/health |

---

## Référence des endpoints

| Méthode | Route | Description |
|---|---|---|
| `POST` | `/api/extract` | Upload d'un fichier (+ `licence_key`) → JSON extrait par l'IA. **Ne sauvegarde rien.** |
| `POST` | `/api/invoices` | Enregistre une facture **validée** par l'utilisateur |
| `GET` | `/api/invoices` | Liste paginée (`limit` ≤ 200, `offset`, `user_id`, `role`) |
| `GET` | `/api/invoices/{id}` | Détail d'une facture avec ses articles |
| `POST` | `/api/search` | Agent de recherche intelligente (licence requise) |
| `POST` | `/api/license/verify` | Vérifie la validité d'une licence |
| `POST` | `/api/products/check` | Produit existant ou suggestions de produits similaires |
| `GET` | `/api/health` | État du service |

### Exemples

**Extraction**

```bash
curl -X POST http://127.0.0.1:8001/api/extract \
  -F "file=@facture.pdf" \
  -F "licence_key=VOTRE_LICENCE"
```

```json
{
  "success": true,
  "source_file": "facture.pdf",
  "raw_text": "...",
  "data": { "invoice_number": "INV-2026-001", "vendor_name": "Tech Store Tunisia", "...": "..." }
}
```

**Sauvegarde d'une facture validée**

```bash
curl -X POST http://127.0.0.1:8001/api/invoices \
  -H "Content-Type: application/json" \
  -d '{
    "created_by": 1,
    "invoice_number": "INV-2026-001",
    "invoice_date": "2026-01-15",
    "vendor_name": "Tech Store Tunisia",
    "client_name": "Imen Kammoun",
    "total_amount": 1190.0,
    "currency": "TND",
    "items": [
      { "description": "Clavier", "quantity": 2, "unit_price": 95.0,
        "total_price": 190.0, "product_id": null, "new_product": true }
    ]
  }'
```

**Recherche**

```bash
curl -X POST http://127.0.0.1:8001/api/search \
  -H "Content-Type: application/json" \
  -d '{ "query": "teck store tunisie", "licence_key": "VOTRE_LICENCE", "user_id": 1, "role": "admin" }'
```

**Résolution des produits (`new_product` / `product_id`)** — avant l'envoi, Laminas interroge `/api/products/check` pour chaque ligne :
- `product_id` renseigné → produit existant, réutilisé tel quel
- `new_product = true` → aucun produit ne correspondait, il sera créé

**Codes d'erreur courants**

| Code | Signification |
|---|---|
| `400` | Format non supporté, requête vide, ou fichier rejeté par la couche sécurité |
| `403` | Licence invalide |
| `404` | Facture introuvable (ou appartenant à un autre utilisateur) |
| `422` | Aucun contenu exploitable dans le fichier |
| `500` | Erreur interne (extraction, lecture ou sauvegarde) |

---

## Sécurité

### Pipeline de validation des fichiers uploadés

Chaque fichier envoyé à `/api/extract` traverse ces étapes, dans l'ordre :

1. **Vérification de la licence**
2. **Contrôle de l'extension** déclarée (`.pdf`, `.jpg`, `.jpeg`, `.png`, `.tif`, `.tiff`)
3. **Sauvegarde temporaire** sous un nom neutre (le nom utilisateur n'est jamais utilisé sur disque)
4. **`validate_and_sanitize_file()`** :
   - limite de taille
   - **magic bytes** : le vrai type doit correspondre à l'extension
   - **scan ClamAV** (si disponible)
   - **images** : `verify()` + réencodage complet avec Pillow
   - **PDF** : refus des PDF chiffrés, limite de pages, détection de JavaScript/Launch
   - renommage **UUID**
5. **Extraction IA** sur le fichier assaini uniquement
6. **Nettoyage systématique** des dossiers temporaires (même en cas d'erreur)

### Autres mesures

- **Licences** vérifiées avant chaque action IA
- **Isolation des données par rôle** : un employé ne peut ni lister ni ouvrir les factures des autres (retour `404`, pour ne pas révéler leur existence)
- **Validation humaine** obligatoire avant toute écriture en base

### ⚠️ Avant la mise en production

- Restreindre le **CORS** (`allow_origins=["*"]` est réservé au développement) à l'URL réelle de Laminas
- Ne jamais exposer l'API directement : la placer derrière **Nginx/HTTPS** et limiter la taille des uploads en amont
- Les paramètres `user_id` et `role` sont transmis par le client Laminas : prévoir une **authentification de service à service** (ex. jeton/clé partagée ou JWT vérifié côté API) pour qu'un tiers ne puisse pas s'octroyer le rôle `admin`
- Stocker les secrets (`.env`, clés API) hors du dépôt

---

## Utilisation en ligne de commande (CLI)

### Traiter une facture

```bash
python main.py facture.pdf
python main.py facture.jpg
python main.py invoices/facture2.png
```

### Traiter un dossier

```bash
python main.py                      # dossier par défaut : invoices/
python main.py chemin/vers/dossier/
```

### Recherche directe

```bash
python main.py --search "tech store tunisia"
python main.py --search "INV-2026-001"
python main.py --search "client Imen Kammoun"
```

### Mode interactif

```bash
python main.py --search-cli
```

---

## Agent de recherche intelligente

L'agent travaille en **3 étapes automatiques** :

```
Requête utilisateur
       │
       ▼
┌─────────────────────────────────────────┐
│  ÉTAPE 1 — Analyse de l'intention       │
│  Mistral AI détecte :                   │
│  · Type de recherche (vendeur, client,  │
│    numéro, montant, date…)              │
│  · Champs MySQL à interroger            │
│  · Texte normalisé                      │
│  [Fallback local si API indisponible]   │
└─────────────────────────────────────────┘
       │
       ▼
┌─────────────────────────────────────────┐
│  ÉTAPE 2 — Recherche en cascade         │
│  1. Exacte    → LOWER(champ) = query    │
│     ↓ si aucun résultat                 │
│  2. Partielle → LIKE '%token%'          │
│     + filtre qualité (≥ 80 % tokens)    │
│     ↓ si aucun résultat                 │
│  3. Floue     → RapidFuzz (score ≥ 78%) │
│     ratio / partial / token_sort /      │
│     token_set                           │
└─────────────────────────────────────────┘
       │
       ▼
┌─────────────────────────────────────────┐
│  ÉTAPE 3 — Réponse naturelle            │
│  Mistral formate les résultats          │
│  [Fallback texte si API indisponible]   │
└─────────────────────────────────────────┘
       │
       ▼
  Résultats + détail des factures
  (filtrés selon user_id / role)
```

### Normalisation du texte

| Étape | Exemple |
|---|---|
| Minuscules | `TUNISIE TÉLÉCOM` → `tunisie télécom` |
| Suppression des accents | `tunisie télécom` → `tunisie telecom` |
| Nettoyage ponctuation | `S.A.R.L.` → `sarl` |
| Normalisation des espaces | `tech   store` → `tech store` |

---

## Exemples de recherche

Base d'exemple : **Tech Store Tunisia** (INV-2026-001), **TECH SOLUTIONS** (INV-2025-0458), **ABC Rénovations SARL** (ID 3).

| Type | Requête | Résultat |
|---|---|---|
| Exacte | `tech store tunisia` | Tech Store Tunisia ✅ |
| Exacte | `INV-2026-001` | Tech Store Tunisia ✅ |
| Partielle | `tech` | Tech Store Tunisia + TECH SOLUTIONS ✅ |
| Partielle | `renovations` | ABC Rénovations SARL ✅ |
| Floue | `teck store tunisie` | Tech Store Tunisia (91,4 %) ✅ |
| Floue | `tec solutions` | TECH SOLUTIONS (96,3 %) ✅ |
| Client | `client Imen Kammoun` | INV-2026-001 ✅ |
| Numéro | `INV-2025` | TECH SOLUTIONS ✅ |

**Mode interactif**

```
🔎 Recherche > tech
  → 2 factures trouvées (Tech Store Tunisia + TECH SOLUTIONS)

🔎 Recherche > teck store tunisie
  → 1 facture trouvée (fuzzy 91.4 % — Tech Store Tunisia)

🔎 Recherche > exit
  → 👋 Au revoir !
```

---

## Flux de traitement

### Via l'ERP (production)

```
Utilisateur ──► Laminas ──► POST /api/extract
                              │ 1. licence      2. extension
                              │ 3. file_security (magic bytes, ClamAV, PDF/images)
                              │ 4. pdf_extractor → ai_parser (Mistral)
                              ▼
                     JSON extrait (non sauvegardé)
                              │
Laminas : formulaire éditable ◄┘   (l'utilisateur vérifie / corrige)
        │
        ├─► POST /api/products/check   (produit existant ou nouveau ?)
        └─► POST /api/invoices         (sauvegarde en MySQL)
```

### Extraction d'un fichier (cœur du pipeline)

```
Fichier (PDF / JPG / PNG / TIFF)
        │
        ▼
 pdf_extractor.py   PDF natif → texte | PDF scanné → images base64 | Image → base64
        │
        ▼
 ai_parser.py       Envoi à Mistral (texte + images) → JSON structuré
        │
        ▼
 db_handler.py      INSERT invoices + invoice_items → invoice_id
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

### Rate limit API (429) — retry exponentiel

```
Tentative 1 échoue → attente  3 s
Tentative 2 échoue → attente  8 s
Tentative 3 échoue → attente 20 s
Tentative 4 échoue → attente 40 s → bascule sur le fallback local
```

### Fallback local

Si Mistral est totalement indisponible :

- l'**analyse d'intention** passe par des règles regex locales
- la **réponse** est un texte structuré sans LLM
- la **recherche en base** continue de fonctionner normalement

### Formats supportés

- **API REST** : `.pdf`, `.jpg`, `.jpeg`, `.png`, `.tif`, `.tiff`
- **CLI** : `.pdf`, `.jpg`, `.jpeg`, `.png`, `.webp`

---

## Technologies utilisées

| Technologie | Usage |
|---|---|
| **Python 3.11+** | Langage principal |
| **FastAPI + Uvicorn** | API REST, documentation Swagger automatique |
| **Pydantic** | Validation des entrées/sorties de l'API |
| **Mistral AI** (`mistral-large-latest`) | Extraction & agent de recherche |
| **Pixtral** (`pixtral-large-latest`) | Vision (PDF scannés & images) |
| **MySQL 8.0+** (PyMySQL) | Stockage des factures |
| **PyMuPDF** (fitz) | Conversion PDF → images |
| **pdfplumber** | Extraction de texte PDF natif |
| **RapidFuzz** | Recherche floue (Levenshtein) |
| **Pillow** | Traitement et réencodage sécurisé d'images |
| **pytesseract** | OCR de secours |
| **ClamAV** *(optionnel)* | Scan antivirus des uploads |
| **python-dotenv** | Variables d'environnement |
| **requests** | Appels HTTP vers l'API Mistral |

---

## Dépannage

| Problème | Piste de solution |
|---|---|
| `ModuleNotFoundError: fastapi` | `pip install fastapi uvicorn python-multipart` |
| `403 Licence invalide` | Vérifier la `licence_key` et la table `licences` |
| `400` à l'upload d'un fichier valide | Le fichier a été rejeté par `file_security` (taille, type réel, PDF chiffré…) |
| Erreur CORS depuis Laminas | Ajouter l'URL de Laminas dans `allow_origins` |
| Réponses lentes ou erreur 429 | Limite de débit Mistral : le retry et le fallback s'activent automatiquement |
| `Can't connect to MySQL` | Vérifier `DB_HOST`, `DB_USER`, `DB_PASSWORD`, `DB_NAME` dans `.env` |

---

## Feuille de route

- [ ] Authentification de service à service entre Laminas et l'API
- [ ] Restriction du CORS en production
- [ ] Tests unitaires et d'intégration
- [ ] Dockerfile / docker-compose (API + MySQL)
- [ ] Extraction d'autres documents (devis, bons de commande)

---

## Auteur

Projet développé dans le cadre d'un système ERP intelligent pour l'automatisation du traitement et de la gestion des factures.

**kammounimen** — [github.com/kammounimen](https://github.com/kammounimen)
