"""Génère un rapport HTML des annonces BOAMP sélectionnées, depuis une date de
publication choisie — indépendant d'un run de collecte particulier.

Exécution locale :
    python src/generer_rapport.py 2026-09-01
    python src/generer_rapport.py          (sans argument : 7 derniers jours)
"""

import sys
from datetime import date, timedelta

import psycopg2.extras
from dotenv import load_dotenv

from db import obtenir_connexion
from rapport import generer_rapport
from restitution import filtrer_trier_lignes

JOURS_PAR_DEFAUT = 7


def recuperer_lignes(conn, depuis: str) -> list[dict]:
    """Récupère depuis Supabase toutes les annonces publiées à partir de la date donnée."""
    with conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cur:
        cur.execute(
            "SELECT * FROM annonces_boamp WHERE dateparution >= %s ORDER BY dateparution;",
            (depuis,),
        )
        return [dict(ligne) for ligne in cur.fetchall()]


def generer_et_ecrire(depuis: str) -> str:
    """Génère le rapport HTML pour la date donnée et l'écrit sur disque.

    Retourne le nom du fichier produit.
    """
    conn = obtenir_connexion()
    lignes = recuperer_lignes(conn, depuis)
    conn.close()
    print(f"{len(lignes)} annonces récupérées depuis le {depuis}.")

    lignes_retenues = filtrer_trier_lignes(lignes)
    print(f"{len(lignes_retenues)} annonce(s) retenue(s) après filtre.")

    contenu_html = generer_rapport(lignes, lignes_retenues, depuis)

    nom_fichier = f"rapport_boamp_{depuis}.html"
    with open(nom_fichier, "w", encoding="utf-8") as f:
        f.write(contenu_html)
    return nom_fichier


def main():
    load_dotenv()

    depuis = (
        sys.argv[1]
        if len(sys.argv) > 1
        else (date.today() - timedelta(days=JOURS_PAR_DEFAUT)).isoformat()
    )

    nom_fichier = generer_et_ecrire(depuis)
    print(f"Rapport généré : {nom_fichier}")


if __name__ == "__main__":
    main()