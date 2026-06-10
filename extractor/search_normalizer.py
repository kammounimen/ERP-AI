"""
search_normalizer.py
--------------------
Utilitaire de normalisation de texte pour la recherche intelligente.
Gère : accents, casse, espaces, caractères spéciaux, caractères arabes.
"""

import re
import unicodedata


# ---------------------------------------------------------------------------
# Normalisation de base
# ---------------------------------------------------------------------------

def remove_accents(text: str) -> str:
    """
    Supprime les accents et diacritiques.
    Ex: 'Télécom' → 'Telecom', 'naïve' → 'naive'
    """
    nfkd = unicodedata.normalize("NFKD", text)
    return "".join(c for c in nfkd if not unicodedata.combining(c))


def normalize_text(text: str) -> str:
    """
    Normalisation complète pour la recherche :
    1. Minuscules
    2. Suppression des accents
    3. Remplacement de la ponctuation/tirets par des espaces
    4. Suppression des caractères non alphanumériques (sauf espaces)
    5. Réduction des espaces multiples
    
    Ex: 'TUNISIE TÉLÉCOM S.A.' → 'tunisie telecom sa'
    Ex: 'Société Générale-Tunisie' → 'societe generale tunisie'
    """
    if not text:
        return ""

    text = str(text).lower()
    text = remove_accents(text)

    # Remplacer ponctuation et séparateurs par espace
    text = re.sub(r"[.\-_/\\|,;:!?()&@#$%*+=<>]", " ", text)

    # Supprimer les caractères restants non alphanumériques (sauf espace)
    text = re.sub(r"[^\w\s]", " ", text, flags=re.UNICODE)

    # Normaliser les espaces
    text = re.sub(r"\s+", " ", text).strip()

    return text


def tokenize(text: str) -> list[str]:
    """
    Découpe un texte normalisé en tokens (mots).
    Ex: 'tunisie telecom' → ['tunisie', 'telecom']
    """
    return normalize_text(text).split()


def build_search_variants(query: str) -> list[str]:
    """
    Génère plusieurs variantes de recherche depuis une requête utilisateur.
    Utile pour les recherches SQL LIKE.
    
    Ex: 'Tunisie Télécom' → ['tunisie telecom', 'tunisie', 'telecom']
    """
    normalized = normalize_text(query)
    tokens = tokenize(query)

    variants = [normalized]          # Texte complet normalisé
    variants.extend(tokens)          # Chaque mot individuellement
    variants = list(dict.fromkeys(variants))  # Dédoublonner en gardant l'ordre

    return variants