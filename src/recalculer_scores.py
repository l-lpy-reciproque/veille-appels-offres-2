"""Recalcule les scores d'une table (annonces_boamp par défaut, ou annonces_ted
avec --table ted) — usage ponctuel, en local.

Deux étapes indépendantes :
    python src/recalculer_scores.py similarite [--table ted]
        Recalcule score_similarite pour toutes les annonces (manifeste court).
        TED : les avis non francophones qui passent désormais
        SEUIL_SCORE_TRADUCTION sans avoir été traduits sont traduits et
        re-taggés (les autres tags restent figés).
    python src/recalculer_scores.py llm --reinitialiser [--table ted]
        Efface les analyses LLM existantes de la table puis ré-analyse les
        annonces qui passent le filtre de restitution (restitution.py), et elles seules.
    python src/recalculer_scores.py llm [--table ted]
        Reprise : n'analyse que, parmi les annonces retenues par le filtre,
        celles qui n'ont pas encore de note (utile si un run précédent s'est
        arrêté en route, par exemple sur un quota Groq).

Le filtre de restitution s'appuie sur score_similarite et total_poles tels
qu'ils sont en base : lancez d'abord l'étape 'similarite' si les scores sont
périmés. Les anciennes valeurs sont écrasées. Les analyses sont enregistrées
par lots de 25, donc une interruption ne fait perdre que le lot en cours.
Ce script ne touche pas à `rapporte` (voir recalculer_rapporte.py) et n'est
pas branché sur la pipeline : il se lance à la main.
"""

import argparse
import os

from dotenv import load_dotenv

from analyse import analyser_annonces
from db import (
    COLONNES_TAGS,
    TABLE_BOAMP,
    TABLE_TED,
    enregistrer_analyses,
    obtenir_connexion,
    recuperer_toutes_les_lignes,
)
from profil import charger_manifeste
from restitution import SEUIL_SCORE_TRADUCTION, est_non_francophone, filtrer_trier_lignes
from scoring import charger_modele, scorer_annonces
from tagging import CHAMPS_RECHERCHES_TED, tagger_annonces
from traduction import traduire_annonces

TAILLE_LOT = 25

# Option --table -> (table, format du prompt LLM).
TABLES = {"boamp": (TABLE_BOAMP, "boamp"), "ted": (TABLE_TED, "ted")}


def recalculer_similarite(conn, table: str) -> None:
    lignes = [l for l in recuperer_toutes_les_lignes(conn, table) if l.get("objet")]
    print(f"Recalcul du score de similarité pour {len(lignes)} annonce(s) de {table}...")

    resultats = scorer_annonces(charger_modele(), charger_manifeste(), lignes)

    with conn.cursor() as cur:
        for annonce, score in resultats:
            cur.execute(
                f"UPDATE {table} SET score_similarite = %s WHERE idweb = %s;",
                (score, annonce["idweb"]),
            )
    conn.commit()
    print("Scores de similarité mis à jour.")

    if table == TABLE_TED:
        traduire_nouveaux(conn, resultats)


def traduire_nouveaux(conn, resultats: list[tuple[dict, float]]) -> None:
    """Traduit et re-tagge les avis TED non francophones qui passent désormais
    le seuil de traduction sans avoir encore été traduits."""
    a_traduire = [
        ligne for ligne, score in resultats
        if est_non_francophone(ligne) and score > SEUIL_SCORE_TRADUCTION and not ligne.get("objet_fr")
    ]
    if not a_traduire:
        return
    traduire_annonces(a_traduire)
    tagger_annonces(a_traduire, CHAMPS_RECHERCHES_TED)

    colonnes = ["objet_fr", "nomacheteur_fr"] + COLONNES_TAGS
    affectations = ", ".join(f"{c} = %s" for c in colonnes)
    with conn.cursor() as cur:
        for ligne in a_traduire:
            cur.execute(
                f"UPDATE {TABLE_TED} SET {affectations} WHERE idweb = %s;",
                [ligne.get(c) for c in colonnes] + [ligne["idweb"]],
            )
    conn.commit()
    print(f"{len(a_traduire)} avis traduits et re-taggés. "
          "Lancez recalculer_rapporte.py --table ted pour mettre à jour la sélection.")


def recalculer_llm(conn, table: str, source: str, reinitialiser: bool) -> None:
    if not os.environ.get("GROQ_API_KEY"):
        print("GROQ_API_KEY absent : rien n'a été modifié.")
        return

    toutes = recuperer_toutes_les_lignes(conn, table)
    # Même filtre que la pipeline (colonne rapporte) ; le tri place en premier les annonces les
    # plus prometteuses (nb de tags puis score), utile si le quota s'épuise.
    retenues = [l for l in filtrer_trier_lignes(toutes) if l.get("idweb")]
    print(f"{len(retenues)} annonce(s) sur {len(toutes)} passent le filtre de restitution ({table}).")
    if not retenues:
        return
    ids_retenues = {l["idweb"] for l in retenues}

    if reinitialiser:
        # Garde-fou : on ne supprime les anciennes analyses que si l'API répond.
        print("Essai sur une annonce avant d'effacer les analyses existantes...")
        if not analyser_annonces(retenues[:1], source):
            print("L'essai a échoué : aucune analyse n'a été effacée.")
            return
        with conn.cursor() as cur:
            cur.execute(
                f"UPDATE {table} SET analyse_pertinence = NULL, analyse_note = NULL;"
            )
        conn.commit()
        print("Analyses existantes effacées.")
        a_analyser = retenues
    else:
        a_analyser = [l for l in retenues if l.get("analyse_note") is None]

    print(f"{len(a_analyser)} annonce(s) à analyser...")

    for debut in range(0, len(a_analyser), TAILLE_LOT):
        lot = a_analyser[debut:debut + TAILLE_LOT]
        analyses = analyser_annonces(lot, source)
        enregistrer_analyses(conn, analyses, table)
        print(f"Lot {debut // TAILLE_LOT + 1} : {len(analyses)}/{len(lot)} analysée(s).")

    restantes = sum(
        1
        for l in recuperer_toutes_les_lignes(conn, table)
        if l.get("idweb") in ids_retenues and l.get("analyse_note") is None
    )
    if restantes:
        print(
            f"{restantes} annonce(s) retenue(s) sans note. Relancez 'llm' "
            "(sans --reinitialiser) pour reprendre celles-ci."
        )
    else:
        print("Toutes les annonces retenues ont une note.")


def main():
    load_dotenv()

    parser = argparse.ArgumentParser(description="Recalcul des scores de la base.")
    parser.add_argument("etape", choices=["similarite", "llm"])
    parser.add_argument("--table", choices=TABLES, default="boamp")
    parser.add_argument(
        "--reinitialiser",
        action="store_true",
        help="(llm) efface d'abord toutes les analyses existantes de la table",
    )
    args = parser.parse_args()
    table, source = TABLES[args.table]

    conn = obtenir_connexion()
    try:
        if args.etape == "similarite":
            recalculer_similarite(conn, table)
        else:
            recalculer_llm(conn, table, source, args.reinitialiser)
    finally:
        conn.close()


if __name__ == "__main__":
    main()
