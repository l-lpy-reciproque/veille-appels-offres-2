"""Point d'entrée du pipeline : collecte BOAMP -> tags -> scoring -> écriture en base
-> restitution -> analyse LLM -> suppression des annonces expirées depuis plus d'un mois.

Les annonces retenues (colonne `rapporte`) sont consultées sur la page web
(web/index.html), qui lit directement la base : aucun rapport n'est produit ici.

Exécution locale :  python src/main.py
"""

from datetime import date, timedelta

from dotenv import load_dotenv

from analyse import analyser_annonces
from db import (
    enregistrer_analyses,
    obtenir_connexion,
    obtenir_derniere_date_parution,
    supprimer_annonces_expirees,
    upsert_annonces,
)
from ingestion import recuperer_annonces
from profil import charger_manifeste
from restitution import est_retenue, restituer
from scoring import charger_modele, scorer_annonces
from tagging import tagger_annonces

JOURS_PAR_DEFAUT = 7


def main():
    load_dotenv()

    manifeste = charger_manifeste()

    conn = obtenir_connexion()

    valeur_par_defaut = (date.today() - timedelta(days=JOURS_PAR_DEFAUT)).isoformat()
    depuis = obtenir_derniere_date_parution(conn, valeur_par_defaut)
    print(f"Récupération des annonces publiées depuis le {depuis}.\n")

    annonces = recuperer_annonces(depuis=depuis)
    print(f"{len(annonces)} annonces récupérées.\n")

    if annonces:
        annonces = tagger_annonces(annonces)

        modele = charger_modele()
        resultats = scorer_annonces(modele, manifeste, annonces)

        for annonce, score in resultats:
            annonce["rapporte"] = est_retenue((annonce, score))
        
        upsert_annonces(conn, resultats)
        print(f"{len(resultats)} annonces enregistrées dans annonces_boamp.\n")

        a_restituer = restituer(resultats)
        print(f"Restitution : {len(a_restituer)} annonces retenues sur {len(resultats)}.\n")
        for annonce, score in a_restituer:
            print(f"[poles={annonce['total_poles']}] {score:.3f}  {annonce['objet']}")

        annonces_a_analyser = [annonce for annonce, _ in a_restituer]
        print(f"\nAnalyse LLM de {len(annonces_a_analyser)} annonces…")
        analyses = analyser_annonces(annonces_a_analyser)
        if analyses:
            enregistrer_analyses(conn, analyses)
            print(f"{len(analyses)} analyses enregistrées en base.")

    nb_supprimees = supprimer_annonces_expirees(conn)
    print(f"\nSuppression de {nb_supprimees} annonce(s) expirée(s) depuis plus d'un mois."
          "(les annonces évaluées sont conservées).")

    conn.close()


if __name__ == "__main__":
    main()