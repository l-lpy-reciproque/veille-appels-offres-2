"""Connexion et écriture des résultats dans Supabase (table annonces_boamp)."""

import os

import psycopg2
import psycopg2.extras

from tagging import CLUSTERS
from utils import aplatir

COLONNES_TAGS = list(CLUSTERS.keys()) + ["total_poles"]

COLONNES_BASE = [
    "idweb", "objet", "nomacheteur", "code_departement", "dateparution",
    "datelimitereponse", "famille_libelle", "descripteur_libelle",
    "procedure_libelle", "url_avis", "score_similarite", "rapporte"
    ]

TOUTES_COLONNES = COLONNES_BASE + COLONNES_TAGS


def obtenir_connexion():
    uri = os.environ["SUPABASE_DB_URL"]
    return psycopg2.connect(uri)


def obtenir_derniere_date_parution(conn, valeur_par_defaut: str) -> str:
    """Retourne la date de publication (dateparution) la plus récente déjà
    enregistrée en base, ou valeur_par_defaut si la table est vide (premier run)."""
    with conn.cursor() as cur:
        cur.execute("SELECT MAX(dateparution) FROM annonces_boamp;")
        resultat = cur.fetchone()[0]
    return resultat if resultat else valeur_par_defaut


def recuperer_toutes_les_lignes(conn) -> list[dict]:
    """Récupère l'intégralité de la table annonces_boamp, sous forme de dicts
    plats (pas de filtre de date) — utilisé par les scripts de recalcul et
    l'analyse exploratoire."""
    with conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cur:
        cur.execute("SELECT * FROM annonces_boamp;")
        return [dict(ligne) for ligne in cur.fetchall()]


def upsert_annonces(conn, resultats: list[tuple[dict, float]]) -> None:
    """Insère ou met à jour les annonces scorées et taggées.

    resultats : liste de tuples (annonce, score), l'annonce contenant déjà
    les champs de tags ajoutés par tagging.tagger_annonces().
    """
    colonnes_sql = ", ".join(TOUTES_COLONNES)
    placeholders = ", ".join(["%s"] * len(TOUTES_COLONNES))
    maj_sql = ", ".join(f"{c} = EXCLUDED.{c}" for c in TOUTES_COLONNES if c != "idweb")

    with conn.cursor() as cur:
        for annonce, score in resultats:
            valeurs = [
                annonce.get("idweb"),
                annonce.get("objet"),
                annonce.get("nomacheteur"),
                aplatir(annonce.get("code_departement")),
                annonce.get("dateparution"),
                annonce.get("datelimitereponse"),
                annonce.get("famille_libelle"),
                aplatir(annonce.get("descripteur_libelle")),
                annonce.get("procedure_libelle"),
                annonce.get("url_avis"),
                score,
                bool(annonce.get("rapporte", False)),
            ] + [annonce.get(colonne) for colonne in COLONNES_TAGS]

            cur.execute(
                f"""
                INSERT INTO annonces_boamp ({colonnes_sql})
                VALUES ({placeholders})
                ON CONFLICT (idweb) DO UPDATE SET
                    {maj_sql},
                    date_ingestion = now();
                """,
                valeurs,
            )
    conn.commit()


def enregistrer_analyses(conn, analyses: dict[str, dict]) -> None:
    """Met à jour les colonnes d'analyse LLM pour les annonces concernées."""
    if not analyses:
        return
    with conn.cursor() as cur:
        for idweb, analyse in analyses.items():
            cur.execute(
                """
                UPDATE annonces_boamp
                SET analyse_pertinence = %s,
                    analyse_note = %s
                WHERE idweb = %s;
                """,
                (analyse["analyse_pertinence"], analyse["analyse_note"], idweb),
            )
    conn.commit()

def supprimer_annonces_expirees(conn, delai: str = "1 month") -> int:
    """Supprime les annonces dont la date limite de réponse est dépassée depuis
    plus de `delai` (intervalle Postgres), sauf celles évaluées par l'équipe
    (note_humaine renseignée), conservées pour comparer note humaine, note LLM
    et score. Retourne le nombre de lignes supprimées.

    Les annonces supprimées ne reviennent pas : l'ingestion ne collecte que
    les avis dont la date limite n'est pas dépassée."""
    with conn.cursor() as cur:
        cur.execute(
            """
            DELETE FROM annonces_boamp
            WHERE datelimitereponse::timestamptz < now() - %s::interval
              AND note_humaine IS NULL;
            """,
            (delai,),
        )
        nb_supprimees = cur.rowcount
    conn.commit()
    return nb_supprimees
