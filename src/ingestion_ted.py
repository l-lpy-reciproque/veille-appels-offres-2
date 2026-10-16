"""Récupération des appels d'offres européens TED (API de recherche v3).

Ne garde que :
- les appels d'offres (types d'avis TYPES_APPEL_OFFRES), pas les avis
  d'attribution ni les rectificatifs ;
- les avis dont au moins un code CPV figure tel quel dans donnees/codes_cpv.csv.
  Le filtre de TED renvoie aussi les avis portant un code *descendant* d'un
  code de la liste : ils sont écartés ici, côté Python ;
- les avis encore ouverts (date limite non dépassée, ou absente).

Les textes sont gardés dans la langue d'origine : TED ne traduit que
`notice-title` (« Pays – libellé CPV – titre d'origine »), conservé dans
titre_fr. Les libellés français des codes CPV correspondants (libelles_cpv)
servent au tagging par mots-clés. Les avis non francophones assez proches du
manifeste sont traduits ensuite (traduction.py, appelé par main.py).

Chaque avis est converti en dict aux noms de colonnes de la table annonces_ted
(idweb = numéro de publication TED).

Test sans écriture en base :  python src/ingestion_ted.py [AAAA-MM-JJ [AAAA-MM-JJ]]
(par défaut : la veille seulement)
"""

import csv
import html
import sys
import time
from datetime import date, timedelta
from pathlib import Path

import requests

URL_TED = "https://api.ted.europa.eu/v3/notices/search"
CHEMIN_CODES_CPV = Path(__file__).resolve().parent.parent / "donnees" / "codes_cpv.csv"

TYPES_APPEL_OFFRES = ["cn-standard", "cn-social", "cn-desg", "pin-cfc-standard", "pin-cfc-social"]
CHAMPS = [
    "publication-number", "notice-title", "title-proc", "description-proc",
    "buyer-name", "buyer-country", "buyer-city", "publication-date",
    "deadline-receipt-tender-date-lot", "notice-type", "procedure-type",
    "classification-cpv", "links",
]

TAILLE_PAGE = 250  # maximum accepté par l'API
MAX_PAGES = 40     # garde-fou : 40 x 250 = 10 000 avis
PAUSE = 0.5        # secondes entre deux pages


def charger_codes_cpv() -> dict[str, str]:
    """Code CPV à 8 chiffres -> libellé français."""
    with open(CHEMIN_CODES_CPV, newline="", encoding="utf-8") as f:
        return {ligne["code"].strip().zfill(8): ligne["libelle"].strip() for ligne in csv.DictReader(f)}


def construire_requete(depuis: str, jusqua: str, codes: list[str]) -> str:
    """depuis, jusqua : dates ISO (AAAA-MM-JJ) de publication, incluses."""
    return " AND ".join([
        f"publication-date>={depuis.replace('-', '')}",
        f"publication-date<={jusqua.replace('-', '')}",
        f"notice-type IN ({' '.join(TYPES_APPEL_OFFRES)})",
        f"classification-cpv IN ({' '.join(codes)})",
    ])


def _interroger(requete: str, page: int) -> dict:
    corps = {"query": requete, "fields": CHAMPS, "limit": TAILLE_PAGE, "page": page}
    for essai in range(3):
        reponse = requests.post(URL_TED, json=corps, timeout=60)
        if reponse.status_code in (429, 500, 502, 503, 504):  # erreur temporaire : on patiente
            time.sleep(2 * (essai + 1))
            continue
        break
    reponse.raise_for_status()
    return reponse.json()


def _texte(valeur, langues=("fra",)) -> str:
    """Valeur d'un champ multilingue TED ({langue: texte ou liste}) : français
    si disponible, sinon la première langue. Les listes sont jointes par « ; »."""
    if isinstance(valeur, dict):
        valeur = next((valeur[l] for l in langues if valeur.get(l)), None) or next(iter(valeur.values()), None)
    if isinstance(valeur, list):
        valeur = " ; ".join(dict.fromkeys(str(v) for v in valeur if v))
    return _decoder_entites(valeur or "")


def _decoder_entites(texte: str) -> str:
    """Certains textes TED sont échappés deux fois (« &amp;amp; ») : décode
    jusqu'à stabilité."""
    while (decode := html.unescape(texte)) != texte:
        texte = decode
    return texte


def _langue(titres) -> str | None:
    langues = list(titres or {})
    return "fra" if "fra" in langues else next(iter(langues), None)


def convertir(avis: dict, codes_cpv: dict[str, str]) -> dict:
    """Avis TED brut -> dict aux noms de colonnes de annonces_ted."""
    titre_fr = _texte(avis.get("notice-title"))
    titre_origine = _texte(avis.get("title-proc"))
    cpv = list(dict.fromkeys(avis.get("classification-cpv") or []))
    cpv_retenus = [c for c in cpv if c in codes_cpv]
    echeances = [e[:10] for e in avis.get("deadline-receipt-tender-date-lot") or [] if e]
    return {
        "idweb": avis.get("publication-number"),
        # Titre d'origine ; à défaut, la dernière partie de notice-title.
        "objet": titre_origine or titre_fr.split(" – ")[-1],
        "titre_fr": titre_fr,
        "description": _texte(avis.get("description-proc")),
        # "fra" dès que l'avis existe en français (avis bilingues belges, suisses…).
        "langue": _langue(avis.get("title-proc")),
        "nomacheteur": _texte(avis.get("buyer-name")),
        "pays": ", ".join(sorted(set(avis.get("buyer-country") or []))),
        "ville": _texte(avis.get("buyer-city")),
        "dateparution": (avis.get("publication-date") or "")[:10] or None,
        # Dernière échéance des lots : l'avis reste ouvert tant qu'un lot l'est.
        "datelimitereponse": max(echeances, default=None),
        "type_avis": avis.get("notice-type"),
        "procedure_libelle": avis.get("procedure-type"),
        "codes_cpv": ", ".join(cpv),
        "libelles_cpv": ", ".join(codes_cpv[c] for c in cpv_retenus),
        "url_avis": ((avis.get("links") or {}).get("html") or {}).get("FRA"),
    }


def recuperer_annonces(depuis: str, jusqua: str) -> list[dict]:
    """Interroge TED (toutes pages) pour les avis publiés entre depuis et jusqua
    (dates ISO incluses) et retourne les avis retenus, convertis."""
    codes_cpv = charger_codes_cpv()
    requete = construire_requete(depuis, jusqua, sorted(codes_cpv))

    bruts, total = {}, 0
    for page in range(1, MAX_PAGES + 1):
        data = _interroger(requete, page)
        total = data.get("totalNoticeCount") or 0
        if data.get("timedOut"):
            print(f"TED : délai dépassé à la page {page}, résultats peut-être partiels.")
        nouveaux = [a for a in data.get("notices", []) if a.get("publication-number") not in bruts]
        bruts.update((a["publication-number"], a) for a in nouveaux)
        if not nouveaux or len(bruts) >= total:
            break
        time.sleep(PAUSE)
    if len(bruts) < total:
        print(f"TED : collecte incomplète ({len(bruts)} avis sur {total}).")

    aujourdhui = date.today().isoformat()
    annonces = [convertir(a, codes_cpv) for a in bruts.values()]
    annonces = [
        a for a in annonces
        if a["libelles_cpv"]  # CPV exact de la liste
        and (a["datelimitereponse"] is None or a["datelimitereponse"] >= aujourdhui)
    ]
    print(f"TED : {len(bruts)} avis reçus, {len(annonces)} retenus (CPV exact, encore ouverts).")
    return annonces


if __name__ == "__main__":
    from collections import Counter

    hier = (date.today() - timedelta(days=1)).isoformat()
    depuis = sys.argv[1] if len(sys.argv) > 1 else hier
    jusqua = sys.argv[2] if len(sys.argv) > 2 else max(depuis, hier)
    annonces = recuperer_annonces(depuis, jusqua)
    print(Counter(a["pays"] for a in annonces).most_common(10))
    print(Counter(a["langue"] for a in annonces).most_common(10))
    print("sans date limite :", sum(1 for a in annonces if not a["datelimitereponse"]))
    for a in annonces[:5]:
        print({k: (v[:100] if isinstance(v, str) else v) for k, v in a.items()})
