"""Chargement des textes de profil de l'agence.

Deux fichiers distincts, car ils servent deux usages différents :
- le manifeste court (embeddings) est comparé aux annonces par similarité
  sémantique ; le modèle ne lit que ~128 tokens, donc il doit rester bref et
  descriptif, sans critères d'exclusion ;
- le manifeste détaillé (LLM) est fourni en contexte au LLM d'analyse, qui peut
  lire un texte long comprenant des critères d'appréciation.
"""

from pathlib import Path

DOSSIER_PROFIL = Path(__file__).parent.parent / "profil"
CHEMIN_MANIFESTE = DOSSIER_PROFIL / "manifeste_reciproque_1.txt"
CHEMIN_MANIFESTE_LLM = DOSSIER_PROFIL / "manifeste_reciproque_llm.txt"


def charger_manifeste() -> str:
    """Manifeste court, utilisé pour le calcul de similarité (embeddings)."""
    return CHEMIN_MANIFESTE.read_text(encoding="utf-8")


def charger_manifeste_llm() -> str:
    """Manifeste détaillé, utilisé comme contexte par le LLM d'analyse."""
    return CHEMIN_MANIFESTE_LLM.read_text(encoding="utf-8")
