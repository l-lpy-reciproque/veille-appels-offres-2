"""Fonctions utilitaires partagées par plusieurs modules du pipeline."""

import unicodedata


def normaliser(texte) -> str:
    """Minuscule + suppression des accents"""
    if not texte:
        return ""
    texte = str(texte).lower().strip()
    texte = unicodedata.normalize("NFD", texte)
    return "".join(c for c in texte if unicodedata.category(c) != "Mn")


def aplatir(valeur) -> str:
    """Convertit une valeur BOAMP potentiellement en liste (ex. descripteur_libelle,
    code_departement) en une chaîne simple, séparée par des virgules. Retourne une
    chaîne vide si la valeur est absente/None."""
    if isinstance(valeur, list):
        return ", ".join(str(v) for v in valeur) if valeur else ""
    return valeur or ""
