"""Recalcule les scores de la table annonces_boamp (usage ponctuel, en local).

Deux étapes indépendantes :
    python src/recalculer_scores.py similarite
        Recalcule score_similarite pour toutes les annonces (manifeste court).
    python src/recalculer_scores.py llm --reinitialiser
        Efface les analyses LLM existantes puis ré-analyse les annonces qui
        passent le filtre de restitution (restitution.py), et elles seules.
    python src/recalculer_scores.py llm
        Reprise : n'analyse que, parmi les annonces retenues par le filtre,
        celles qui n'ont pas encore de note (utile si un run précédent s'est
        arrêté en route, par exemple sur un quota Groq).

Le filtre de restitution s'appuie sur score_similarite et total_poles tels
qu'ils sont en base : lancez d'abord l'étape 'similarite' si les scores sont
périmés. Les anciennes valeurs sont écrasées. Les analyses sont enregistrées
par lots de 25, donc une interruption ne fait perdre que le lot en cours.
Ce script n'est pas branché sur la pipeline : il se lance à la main.
"""

import argparse
import os

from dotenv import load_dotenv

from analyse import analyser_annonces
from db import enregistrer_analyses, obtenir_connexion, recuperer_toutes_les_lignes
from profil import charger_manifeste
from restitution import filtrer_trier_lignes
from scoring import charger_modele, scorer_annonces

TAILLE_LOT = 25


def recalculer_similarite(conn) -> None:
    lignes = [l for l in recuperer_toutes_les_lignes(conn) if l.get("objet")]
    print(f"Recalcul du score de similarité pour {len(lignes)} annonce(s)...")

    resultats = scorer_annonces(charger_modele(), charger_manifeste(), lignes)

    with conn.cursor() as cur:
        for annonce, score in resultats:
            cur.execute(
                "UPDATE annonces_boamp SET score_similarite = %s WHERE idweb = %s;",
                (score, annonce["idweb"]),
            )
    conn.commit()
    print("Scores de similarité mis à jour.")


def recalculer_llm(conn, reinitialiser: bool) -> None:
    if not os.environ.get("GROQ_API_KEY"):
        print("GROQ_API_KEY absent : rien n'a été modifié.")
        return

    toutes = recuperer_toutes_les_lignes(conn)
    # Même filtre que la pipeline (colonne rapporte) ; le tri place en premier les annonces les
    # plus prometteuses (nb de tags puis score), utile si le quota s'épuise.
    retenues = [l for l in filtrer_trier_lignes(toutes) if l.get("idweb")]
    print(f"{len(retenues)} annonce(s) sur {len(toutes)} passent le filtre de restitution.")
    if not retenues:
        return
    ids_retenues = {l["idweb"] for l in retenues}

    if reinitialiser:
        # Garde-fou : on ne supprime les anciennes analyses que si l'API répond.
        print("Essai sur une annonce avant d'effacer les analyses existantes...")
        if not analyser_annonces(retenues[:1]):
            print("L'essai a échoué : aucune analyse n'a été effacée.")
            return
        with conn.cursor() as cur:
            cur.execute(
                "UPDATE annonces_boamp SET analyse_pertinence = NULL, analyse_note = NULL;"
            )
        conn.commit()
        print("Analyses existantes effacées.")
        a_analyser = retenues
    else:
        a_analyser = [l for l in retenues if l.get("analyse_note") is None]

    print(f"{len(a_analyser)} annonce(s) à analyser...")

    for debut in range(0, len(a_analyser), TAILLE_LOT):
        lot = a_analyser[debut:debut + TAILLE_LOT]
        analyses = analyser_annonces(lot)
        enregistrer_analyses(conn, analyses)
        print(f"Lot {debut // TAILLE_LOT + 1} : {len(analyses)}/{len(lot)} analysée(s).")

    restantes = sum(
        1
        for l in recuperer_toutes_les_lignes(conn)
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
    parser.add_argument(
        "--reinitialiser",
        action="store_true",
        help="(llm) efface d'abord toutes les analyses existantes",
    )
    args = parser.parse_args()

    conn = obtenir_connexion()
    try:
        if args.etape == "similarite":
            recalculer_similarite(conn)
        else:
            recalculer_llm(conn, args.reinitialiser)
    finally:
        conn.close()


if __name__ == "__main__":
    main()
