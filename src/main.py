"""Point d'entrée du pipeline, pour chaque source (BOAMP, puis TED) :
collecte -> scoring -> tags -> écriture en base -> restitution -> analyse LLM,
puis suppression des annonces expirées depuis plus d'un mois.

TED : les avis non francophones dont le score dépasse SEUIL_SCORE_TRADUCTION
sont traduits en français avant le tagging (traduction.py) ; les autres ne
peuvent pas être retenus (restitution.py).

Les avis TED français déjà collectés via BOAMP sont écartés avant traitement
(dedoublonnage.py). Une erreur côté TED n'empêche pas le traitement BOAMP.

Les annonces retenues (colonne `rapporte`) sont consultées sur la page web
(web/index.html), qui lit directement la base : aucun rapport n'est produit ici.

Exécution locale :  python src/main.py
"""

import sys
import traceback
from datetime import date, timedelta
from functools import cache

from dotenv import load_dotenv

import ingestion_boamp
import ingestion_ted
from analyse import analyser_annonces
from db import (
    TABLE_BOAMP,
    TABLE_TED,
    enregistrer_analyses,
    obtenir_connexion,
    obtenir_derniere_date_parution,
    recuperer_objets_boamp,
    supprimer_annonces_expirees,
    upsert_annonces,
)
from dedoublonnage import ecarter_doublons_boamp
from profil import charger_manifeste
from restitution import SEUIL_SCORE_TRADUCTION, est_non_francophone, est_retenue, restituer
from scoring import charger_modele, scorer_annonces
from tagging import CHAMPS_RECHERCHES, CHAMPS_RECHERCHES_TED, tagger_annonces
from traduction import traduire_annonces

JOURS_PAR_DEFAUT = 7


@cache
def modele():
    """Chargé une seule fois, et seulement s'il y a des annonces à scorer."""
    return charger_modele()


def date_de_depart(conn, table: str) -> str:
    valeur_par_defaut = (date.today() - timedelta(days=JOURS_PAR_DEFAUT)).isoformat()
    return obtenir_derniere_date_parution(conn, valeur_par_defaut, table)


def traiter(conn, annonces: list[dict], table: str, source: str, champs: tuple[str, ...]) -> None:
    """Score, tags, écriture en base, restitution et analyse LLM d'une source."""
    if not annonces:
        return
    resultats = scorer_annonces(modele(), charger_manifeste(), annonces)
    if source == "ted":
        traduire_annonces([
            annonce for annonce, score in resultats
            if est_non_francophone(annonce) and score > SEUIL_SCORE_TRADUCTION
        ])
    tagger_annonces(annonces, champs)

    for annonce, score in resultats:
        annonce["rapporte"] = est_retenue((annonce, score))

    upsert_annonces(conn, resultats, table)
    print(f"{len(resultats)} annonces enregistrées dans {table}.\n")

    a_restituer = restituer(resultats)
    print(f"Restitution : {len(a_restituer)} annonces retenues sur {len(resultats)}.\n")
    for annonce, score in a_restituer:
        print(f"[poles={annonce['total_poles']}] {score:.3f}  {annonce['objet']}")

    annonces_a_analyser = [annonce for annonce, _ in a_restituer]
    print(f"\nAnalyse LLM de {len(annonces_a_analyser)} annonces…")
    analyses = analyser_annonces(annonces_a_analyser, source)
    if analyses:
        enregistrer_analyses(conn, analyses, table)
        print(f"{len(analyses)} analyses enregistrées en base.")


def traiter_boamp(conn) -> None:
    depuis = date_de_depart(conn, TABLE_BOAMP)
    print(f"=== BOAMP : annonces publiées depuis le {depuis} ===\n")
    annonces = ingestion_boamp.recuperer_annonces(depuis=depuis)
    print(f"{len(annonces)} annonces récupérées.\n")
    traiter(conn, annonces, TABLE_BOAMP, "boamp", CHAMPS_RECHERCHES)


def jours_ted(conn) -> tuple[str, str] | None:
    """Jours complets de TED à traiter, (depuis, jusqua) inclus, ou None.

    TED publie chaque jour une édition complète : contrairement à BOAMP, on ne
    recollecte pas le dernier jour en base (ce qui retraduirait et renoterait
    ses avis), et on s'arrête à la veille. Table vide : la veille seulement,
    pas de rattrapage. Sinon : du lendemain du dernier jour en base à la
    veille (un seul jour en temps normal, davantage après une interruption)."""
    hier = date.today() - timedelta(days=1)
    dernier = obtenir_derniere_date_parution(conn, None, TABLE_TED)
    depuis = date.fromisoformat(dernier) + timedelta(days=1) if dernier else hier
    if depuis > hier:
        return None
    return depuis.isoformat(), hier.isoformat()


def traiter_ted(conn) -> None:
    jours = jours_ted(conn)
    if not jours:
        print("\n=== TED : déjà à jour ===")
        return
    depuis, jusqua = jours
    print(f"\n=== TED : avis publiés du {depuis} au {jusqua} ===\n")
    annonces = ingestion_ted.recuperer_annonces(depuis, jusqua)
    # Après BOAMP : les annonces BOAMP du jour comptent aussi.
    annonces = ecarter_doublons_boamp(annonces, recuperer_objets_boamp(conn))
    print(f"{len(annonces)} avis à traiter.\n")
    traiter(conn, annonces, TABLE_TED, "ted", CHAMPS_RECHERCHES_TED)


def main():
    load_dotenv()
    conn = obtenir_connexion()

    traiter_boamp(conn)

    echec_ted = False
    try:
        traiter_ted(conn)
    except Exception:
        echec_ted = True
        conn.rollback()
        print("\nÉchec du traitement TED (BOAMP n'est pas concerné) :")
        traceback.print_exc()

    for table in (TABLE_BOAMP, TABLE_TED):
        nb_supprimees = supprimer_annonces_expirees(conn, table=table)
        print(f"\n{table} : suppression de {nb_supprimees} annonce(s) expirée(s) "
              "(les annonces évaluées sont conservées).")

    conn.close()
    if echec_ted:
        sys.exit(1)  # run signalé en échec sur GitHub, après le nettoyage


if __name__ == "__main__":
    main()
