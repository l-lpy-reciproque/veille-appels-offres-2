"""Connexion et écriture des résultats dans Supabase (tables annonces_boamp et annonces_ted).

Les fonctions prennent le nom de la table en paramètre (annonces_boamp par
défaut) ; seuls les noms de COLONNES_PAR_TABLE sont acceptés.
"""

import os

import psycopg2
import psycopg2.extras

from tagging import CLUSTERS
from utils import aplatir

TABLE_BOAMP = "annonces_boamp"
TABLE_TED = "annonces_ted"

COLONNES_TAGS = list(CLUSTERS.keys()) + ["total_poles"]

COLONNES_BASE = [
    "idweb", "objet", "nomacheteur", "code_departement", "dateparution",
    "datelimitereponse", "famille_libelle", "descripteur_libelle",
    "procedure_libelle", "url_avis", "score_similarite", "rapporte"
    ]

COLONNES_BASE_TED = [
    "idweb", "objet", "objet_fr", "titre_fr", "description", "langue",
    "nomacheteur", "nomacheteur_fr",
    "pays", "ville", "dateparution", "datelimitereponse", "type_avis",
    "procedure_libelle", "codes_cpv", "libelles_cpv", "url_avis",
    "score_similarite", "rapporte",
]

TOUTES_COLONNES = COLONNES_BASE + COLONNES_TAGS

# Colonnes écrites par la pipeline. Ne jamais y ajouter les colonnes de
# l'équipe (vue, note_humaine, annotation_*) : chaque run les écraserait.
COLONNES_PAR_TABLE = {
    TABLE_BOAMP: TOUTES_COLONNES,
    TABLE_TED: COLONNES_BASE_TED + COLONNES_TAGS,
}

# Champs BOAMP parfois renvoyés sous forme de liste par l'API.
COLONNES_A_APLATIR = {"code_departement", "descripteur_libelle"}


def _verifier_table(table: str) -> str:
    if table not in COLONNES_PAR_TABLE:
        raise ValueError(f"table inconnue : {table}")
    return table


def obtenir_connexion():
    uri = os.environ["SUPABASE_DB_URL"]
    return psycopg2.connect(uri)


def obtenir_derniere_date_parution(conn, valeur_par_defaut: str | None, table: str = TABLE_BOAMP) -> str | None:
    """Retourne la date de publication (dateparution) la plus récente déjà
    enregistrée en base, ou valeur_par_defaut si la table est vide (premier run)."""
    with conn.cursor() as cur:
        cur.execute(f"SELECT MAX(dateparution) FROM {_verifier_table(table)};")
        resultat = cur.fetchone()[0]
    return resultat if resultat else valeur_par_defaut


def recuperer_toutes_les_lignes(conn, table: str = TABLE_BOAMP) -> list[dict]:
    """Récupère l'intégralité de la table, sous forme de dicts plats (pas de
    filtre de date) — utilisé par les scripts de recalcul et l'analyse exploratoire."""
    with conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cur:
        cur.execute(f"SELECT * FROM {_verifier_table(table)};")
        return [dict(ligne) for ligne in cur.fetchall()]


def recuperer_objets_boamp(conn) -> list[tuple[str, str, str]]:
    """(idweb, objet, nomacheteur) de toute la table annonces_boamp, pour le
    dédoublonnage des avis TED français."""
    with conn.cursor() as cur:
        cur.execute(f"SELECT idweb, objet, nomacheteur FROM {TABLE_BOAMP};")
        return cur.fetchall()


def _valeur(annonce: dict, colonne: str, score: float):
    if colonne == "score_similarite":
        return score
    if colonne == "rapporte":
        return bool(annonce.get("rapporte", False))
    if colonne in COLONNES_A_APLATIR:
        return aplatir(annonce.get(colonne))
    return annonce.get(colonne)


def upsert_annonces(conn, resultats: list[tuple[dict, float]], table: str = TABLE_BOAMP) -> None:
    """Insère ou met à jour les annonces scorées et taggées.

    resultats : liste de tuples (annonce, score), l'annonce contenant déjà
    les champs de tags ajoutés par tagging.tagger_annonces().
    """
    colonnes = COLONNES_PAR_TABLE[_verifier_table(table)]
    colonnes_sql = ", ".join(colonnes)
    placeholders = ", ".join(["%s"] * len(colonnes))
    maj_sql = ", ".join(f"{c} = EXCLUDED.{c}" for c in colonnes if c != "idweb")

    with conn.cursor() as cur:
        for annonce, score in resultats:
            cur.execute(
                f"""
                INSERT INTO {table} ({colonnes_sql})
                VALUES ({placeholders})
                ON CONFLICT (idweb) DO UPDATE SET
                    {maj_sql},
                    date_ingestion = now();
                """,
                [_valeur(annonce, c, score) for c in colonnes],
            )
    conn.commit()


def enregistrer_analyses(conn, analyses: dict[str, dict], table: str = TABLE_BOAMP) -> None:
    """Met à jour les colonnes d'analyse LLM pour les annonces concernées."""
    if not analyses:
        return
    with conn.cursor() as cur:
        for idweb, analyse in analyses.items():
            cur.execute(
                f"""
                UPDATE {_verifier_table(table)}
                SET analyse_pertinence = %s,
                    analyse_note = %s
                WHERE idweb = %s;
                """,
                (analyse["analyse_pertinence"], analyse["analyse_note"], idweb),
            )
    conn.commit()

def supprimer_annonces_expirees(
    conn, delai: str = "1 month", table: str = TABLE_BOAMP, delai_sans_date_limite: str = "3 months"
) -> int:
    """Supprime les annonces dont la date limite de réponse est dépassée depuis
    plus de `delai` (intervalle Postgres), ainsi que celles sans date limite
    (certains avis TED) parues depuis plus de `delai_sans_date_limite`. Les
    annonces évaluées par l'équipe (note_humaine renseignée) sont conservées
    pour comparer note humaine, note LLM et score. Retourne le nombre de
    lignes supprimées.

    Les annonces supprimées ne reviennent pas : l'ingestion ne collecte que
    les avis dont la date limite n'est pas dépassée."""
    with conn.cursor() as cur:
        cur.execute(
            f"""
            DELETE FROM {_verifier_table(table)}
            WHERE note_humaine IS NULL
              AND (datelimitereponse::timestamptz < now() - %s::interval
                   OR (datelimitereponse IS NULL
                       AND dateparution::date < now() - %s::interval));
            """,
            (delai, delai_sans_date_limite),
        )
        nb_supprimees = cur.rowcount
    conn.commit()
    return nb_supprimees
