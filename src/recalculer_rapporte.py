"""Recalcule la colonne `rapporte` de toute une table (annonces_boamp par défaut).

`rapporte` vaut vrai pour les annonces qui passent le filtre de restitution
(restitution.filtrer_trier_lignes). À lancer :
  - une fois après avoir ajouté la colonne, pour rattraper l'existant ;
  - chaque fois que vous modifiez les seuils de restitution.py ou les listes
    de mots-clés (les tags `total_poles` sont figés à l'ingestion).

`vue` et `note_humaine` ne sont jamais modifiées par ce script.

Exécution locale :  python src/recalculer_rapporte.py [--table boamp|ted]
"""

import argparse

from dotenv import load_dotenv

from db import TABLE_BOAMP, TABLE_TED, obtenir_connexion, recuperer_toutes_les_lignes
from restitution import filtrer_trier_lignes

TABLES = {"boamp": TABLE_BOAMP, "ted": TABLE_TED}


def main():
    load_dotenv()

    parser = argparse.ArgumentParser(description="Recalcul de la colonne rapporte.")
    parser.add_argument("--table", choices=TABLES, default="boamp")
    table = TABLES[parser.parse_args().table]

    conn = obtenir_connexion()
    try:
        toutes = recuperer_toutes_les_lignes(conn, table)
        ids_retenus = [l["idweb"] for l in filtrer_trier_lignes(toutes)]

        with conn.cursor() as cur:
            cur.execute(
                f"UPDATE {table} SET rapporte = (idweb = ANY(%s));",
                (ids_retenus,),
            )
        conn.commit()
        print(f"{table} : {len(ids_retenus)} annonce(s) marquée(s) 'rapporte' sur {len(toutes)}.")
    finally:
        conn.close()


if __name__ == "__main__":
    main()
