"""Récupération des annonces BOAMP correspondant aux critères de recherche."""

import requests

URL_BOAMP = "https://boamp-datadila.opendatasoft.com/api/explore/v2.1/catalog/datasets/boamp/records"

# Descripteurs métier BOAMP (nomenclature contrôlée)
MOTS_CLES_DESCRIPTEURS_METIER = [
    "Assistance à maîtrise d'ouvrage",
    "Assistance technique",
    "Audit",
    "Automatisation",
    "Banc d'essais",
    "Captage",
    "Consommable informatique",
    "Décoration (travaux)",
    "Délégation de service public",
    "Dématérialisation",
    "Diagnostic technique",
    "Equipement muséographique",
    "Equipements spécialisés",
    "Etudes",
    "Film",
    "Informatique (assistance)",
    "Informatique (prestations de services)",
    "Maîtrise d'oeuvre",
    "Matériel pédagogique",
    "Mission d'ordonnancement, pilotage, coordination (opc)",
    "Monuments historiques",
    "Numérisation",
    "Prestations de services",
    "Progiciel",
    "Site internet",
]

TAILLE_PAGE = 100
MAX_ANNONCES = 1000  # garde-fou, évite une boucle incontrôlée si le where devient trop large


def construire_where(depuis: str | None = None) -> str:
    """Construit la clause 'where' ODSQL.

    Une annonce est retenue si son "descripteur_libelle" contient l'un des
    descripteurs métier de la nomenclature BOAMP (correspondance exacte).

    depuis : date ISO (AAAA-MM-JJ) minimale de publication.
    """
    libelles = ", ".join(f'"{mc}"' for mc in MOTS_CLES_DESCRIPTEURS_METIER)
    clause = f"descripteur_libelle in ({libelles}) AND datelimitereponse >= now()"
    if depuis:
        clause += f' AND dateparution >= "{depuis}"'
    return clause


def recuperer_annonces(depuis: str | None = None) -> list[dict]:
    """Interroge l'API BOAMP et retourne la liste des annonces trouvées"""
    where = construire_where(depuis)
    params = {
        "select": "*",
        "where": where,
        "limit": TAILLE_PAGE,
        "offset": 0,
    }

    annonces = []
    while True:
        reponse = requests.get(URL_BOAMP, params=params, timeout=30)
        reponse.raise_for_status()
        data = reponse.json()

        resultats = data.get("results", [])
        if not resultats:
            break

        annonces.extend(resultats)

        total = data.get("total_count", 0)
        params["offset"] += TAILLE_PAGE
        if params["offset"] >= total or len(annonces) >= MAX_ANNONCES:
            break

    return annonces
