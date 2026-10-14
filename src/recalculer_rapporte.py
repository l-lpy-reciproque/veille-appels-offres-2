"""Recalcule la colonne `rapporte` de toute la table annonces_boamp.

`rapporte` vaut vrai pour les annonces qui passent le filtre de restitution
(restitution.filtrer_trier_lignes). À lancer :
  - une fois après avoir ajouté la colonne, pour rattraper l'existant ;
  - chaque fois que vous modifiez les seuils de restitution.py ou les listes
    de mots-clés (les tags `total_poles` sont figés à l'ingestion).

`vue` et `note_humaine` ne sont jamais modifiées par ce script.

Exécution locale :  python src/recalculer_rapporte.py
"""

from dotenv import load_dotenv

from db import obtenir_connexion, recuperer_toutes_les_lignes
from restitution import filtrer_trier_lignes


def main():
    load_dotenv()
    conn = obtenir_connexion()
    try:
        toutes = recuperer_toutes_les_lignes(conn)
        ids_retenus = [l["idweb"] for l in filtrer_trier_lignes(toutes)]

        with conn.cursor() as cur:
            cur.execute(
                "UPDATE annonces_boamp SET rapporte = (idweb = ANY(%s));",
                (ids_retenus,),
            )
        conn.commit()
        print(f"{len(ids_retenus)} annonce(s) marquée(s) 'rapporte' sur {len(toutes)}.")
    finally:
        conn.close()


if __name__ == "__main__":
    main()
