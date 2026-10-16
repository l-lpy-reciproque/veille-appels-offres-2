"""Écarte les avis TED français déjà collectés via BOAMP (table annonces_boamp).

Les avis publiés au JOUE par un acheteur français paraissent aussi au BOAMP,
souvent avec le même objet. Un avis TED est considéré comme un doublon d'une
annonce BOAMP si, après normalisation (minuscules, sans accents ni ponctuation) :
- l'objet est presque identique et l'acheteur ressemblant
  (l'acheteur peut être abrégé : « DIR NO » / « DIR-NORD-OUEST ») ;
- ou l'acheteur est le même et l'objet proche
  (l'objet peut être complété : « … SOC) - accord-cadre en 3 lots »).

Seuils calés sur les avis TED français du 09 au 16/10/2026 : les vrais
doublons ont tous un objet ≥ 0.73 avec le même acheteur, les autres paires
de même acheteur un objet ≤ 0.57.
"""

import re
from difflib import SequenceMatcher

from utils import normaliser

SEUIL_OBJET_IDENTIQUE = 0.9
SEUIL_ACHETEUR_RESSEMBLANT = 0.5
SEUIL_OBJET_PROCHE = 0.65
SEUIL_ACHETEUR_IDENTIQUE = 0.9
# Pré-filtre : part minimale de mots communs (rapportée au texte le plus court)
# pour lancer la comparaison fine. Les vrais doublons partagent presque tout.
SEUIL_MOTS_COMMUNS = 0.5


def _nettoyer(texte) -> str:
    return re.sub(r"[^a-z0-9]+", " ", normaliser(texte)).strip()


def _ratio(a: str, b: str) -> float:
    return SequenceMatcher(None, a, b).ratio()


def _est_doublon(comparateur: SequenceMatcher, acheteur_ted: str, objet_boamp: str, acheteur_boamp: str) -> bool:
    """comparateur : SequenceMatcher dont seq2 est l'objet TED nettoyé (difflib met
    en cache l'analyse de seq2, on ne change que seq1 d'une paire à l'autre)."""
    comparateur.set_seq1(objet_boamp)
    # real_quick_ratio et quick_ratio sont des majorants bon marché de ratio :
    # évitent le calcul exact pour l'immense majorité des paires sans rapport.
    if comparateur.real_quick_ratio() < SEUIL_OBJET_PROCHE or comparateur.quick_ratio() < SEUIL_OBJET_PROCHE:
        return False
    score_objet = comparateur.ratio()
    if score_objet >= SEUIL_OBJET_IDENTIQUE:
        return _ratio(acheteur_ted, acheteur_boamp) >= SEUIL_ACHETEUR_RESSEMBLANT
    if score_objet >= SEUIL_OBJET_PROCHE:
        return _ratio(acheteur_ted, acheteur_boamp) >= SEUIL_ACHETEUR_IDENTIQUE
    return False


def _mots_communs(a: set, b: set) -> float:
    return len(a & b) / min(len(a), len(b)) if a and b else 0.0


def trouver_doublon(annonce_ted: dict, annonces_boamp: list[tuple]) -> str | None:
    """Retourne l'idweb de l'annonce BOAMP dont l'avis TED est le doublon, ou None.
    annonces_boamp : tuples (idweb, objet nettoyé, acheteur nettoyé, mots de
    l'objet), voir preparer_boamp."""
    objet = _nettoyer(annonce_ted.get("objet"))
    acheteur = _nettoyer(annonce_ted.get("nomacheteur"))
    mots = set(objet.split())
    # Cas le plus fréquent, traité d'abord : objet strictement identique.
    for idweb, objet_boamp, acheteur_boamp, _ in annonces_boamp:
        if objet == objet_boamp and _ratio(acheteur, acheteur_boamp) >= SEUIL_ACHETEUR_RESSEMBLANT:
            return idweb
    comparateur = SequenceMatcher(None, "", objet)
    for idweb, objet_boamp, acheteur_boamp, mots_boamp in annonces_boamp:
        if (_mots_communs(mots, mots_boamp) >= SEUIL_MOTS_COMMUNS
                and _est_doublon(comparateur, acheteur, objet_boamp, acheteur_boamp)):
            return idweb
    return None


def preparer_boamp(lignes: list[tuple[str, str, str]]) -> list[tuple]:
    """(idweb, objet, nomacheteur) bruts -> (idweb, objet nettoyé, acheteur
    nettoyé, mots de l'objet)."""
    resultat = []
    for idweb, objet, acheteur in lignes:
        objet = _nettoyer(objet)
        resultat.append((idweb, objet, _nettoyer(acheteur), set(objet.split())))
    return resultat


def ecarter_doublons_boamp(annonces_ted: list[dict], lignes_boamp: list[tuple[str, str, str]]) -> list[dict]:
    """Retire de annonces_ted les avis français déjà présents dans annonces_boamp.
    lignes_boamp : tuples (idweb, objet, nomacheteur) de toute la table."""
    boamp = preparer_boamp(lignes_boamp)
    conservees, nb_doublons = [], 0
    for annonce in annonces_ted:
        if "FRA" in (annonce.get("pays") or "") and trouver_doublon(annonce, boamp):
            nb_doublons += 1
        else:
            conservees.append(annonce)
    print(f"TED : {nb_doublons} avis français déjà collectés via BOAMP, écartés.")
    return conservees
