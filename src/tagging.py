"""Calcul des tags thématiques par annonce, à partir des listes de mots-clés.

BOAMP : cherche dans la réunion de trois champs : objet, nomacheteur, descripteur_libelle.
TED : titre_fr (« Pays – libellé CPV – titre d'origine »), objet, nomacheteur,
leurs traductions automatiques (objet_fr, nomacheteur_fr : avis non francophones
proches du manifeste seulement, voir traduction.py) et libelles_cpv.
"""

from mots_cles import (
    MOTS_CLES_INSTITUTIONS,
    MOTS_CLES_PRESTATIONS,
    MOTS_CLES_MUSEO_SCENO,
    MOTS_CLES_NUMERIQUE_MULTIMEDIA,
    MOTS_CLES_SECTEURS_TRANSVERSES,
)
from utils import aplatir, normaliser

# Nom de colonne -> liste de mots-clés associée.
# L'ordre des clés ici détermine l'ordre des colonnes créées dans Supabase.
CLUSTERS = {
    "match_prestations": MOTS_CLES_PRESTATIONS,
    "match_numerique_multimedia": MOTS_CLES_NUMERIQUE_MULTIMEDIA,
    "match_museo_sceno": MOTS_CLES_MUSEO_SCENO,
    "match_secteurs_transverses": MOTS_CLES_SECTEURS_TRANSVERSES,
    "match_institutions": MOTS_CLES_INSTITUTIONS,
}

CHAMPS_RECHERCHES = ("objet", "nomacheteur", "descripteur_libelle")
CHAMPS_RECHERCHES_TED = (
    "titre_fr", "objet", "objet_fr", "nomacheteur", "nomacheteur_fr", "libelles_cpv",
)


def _contient_un_mot(texte: str, mots_cles: list[str]) -> bool:
    return any(mot in texte for mot in mots_cles)


def tagger_annonce(annonce: dict, champs: tuple[str, ...] = CHAMPS_RECHERCHES) -> dict:
    """Calcule les tags binaires par cluster + le total, pour une annonce."""
    texte_reuni = " ".join(
        normaliser(aplatir(annonce.get(champ))) for champ in champs
    )

    tags = {
        nom_colonne: int(_contient_un_mot(texte_reuni, mots_cles))
        for nom_colonne, mots_cles in CLUSTERS.items()
    }
    tags["total_poles"] = sum(tags.values())
    return tags


def tagger_annonces(annonces: list[dict], champs: tuple[str, ...] = CHAMPS_RECHERCHES) -> list[dict]:
    """Ajoute les champs de tags directement dans chaque dict annonce, en place."""
    for annonce in annonces:
        annonce.update(tagger_annonce(annonce, champs))
    return annonces
