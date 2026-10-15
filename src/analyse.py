"""Analyse de pertinence des annonces retenues via l'API Groq.

Pour chaque annonce, demande au LLM une phrase d'analyse et une note de
pertinence sur 5. Le contexte « qui est reciproque » est fourni au modèle
via le manifeste, ce qui évite de dupliquer la description du profil.

Fallback : en cas d'échec pour une annonce (timeout, réponse invalide,
quota), l'annonce est ignorée — la pipeline continue et l'annonce reste
sans analyse (elle apparaît quand même sur la page web).
"""

import json
import os
from groq import Groq
from profil import charger_manifeste_llm

NOM_MODELE = "openai/gpt-oss-120b"
TEMPERATURE = 0.2
LONGUEUR_MAX_OBJET = 1500  # garde-fou sur la taille du prompt

SYSTEM_PROMPT = """Tu es un assistant qui aide l'agence Reciproque à trier les
appels d'offres publics. Tu analyses chaque annonce et rends un avis bref et
factuel sur sa pertinence pour Reciproque, en te fondant uniquement sur le
profil d'activité ci-dessous.

Tu réponds TOUJOURS par un objet JSON valide, sans texte autour, au format :
{{"pertinence": "<une phrase d'analyse>", "note": <entier de 0 à 5>}}

La note suit cette échelle :
- 5 : cœur de métier, très forte adéquation
- 4 : pertinent, adéquation claire
- 3 : à considérer, adéquation partielle
- 2 : peu pertinent, éloignement marqué
- 1 : hors sujet, mais possible ouverture
- 0 : aucun rapport avec l'activité de Reciproque

La phrase d'analyse doit être concise (une seule phrase), en français, et
justifier la note en s'appuyant sur un élément concret de l'annonce.

PROFIL D'ACTIVITÉ DE RECIPROQUE :
{manifeste}
L'agence Reciproque travaille principalement en région parisienne ou dans des territoires facilement accessibles en transport. Si ce critère n'est pas respecté, la note peut légèrement baisser, sans aller en dessous de 0.
"""


def _prompt_annonce(annonce: dict) -> str:
    objet = (annonce.get("objet") or "")[:LONGUEUR_MAX_OBJET]
    return (
        f"Objet : {objet}\n"
        f"Acheteur : {annonce.get('nomacheteur') or ''}\n"
        f"Famille : {annonce.get('famille_libelle') or ''}\n"
        f"Descripteurs : {annonce.get('descripteur_libelle') or ''}\n"
        f"Département : {annonce.get('code_departement') or ''}\n"
    )


def _analyser_une(client: Groq, annonce: dict, system: str) -> dict | None:
    """Retourne {'analyse_pertinence': str, 'analyse_note': int} ou None en cas d'échec."""
    try:
        reponse = client.chat.completions.create(
            model=NOM_MODELE,
            temperature=TEMPERATURE,
            response_format={"type": "json_object"},
            messages=[
                {"role": "system", "content": system},
                {"role": "user", "content": _prompt_annonce(annonce)},
            ],
        )
        donnees = json.loads(reponse.choices[0].message.content)
        note = int(donnees["note"])
        if not 0 <= note <= 5:
            raise ValueError(f"note hors bornes : {note}")
        return {
            "analyse_pertinence": str(donnees["pertinence"]).strip(),
            "analyse_note": note,
        }
    except Exception as e:
        print(f"  analyse échouée pour {annonce.get('idweb')} : {e}")
        return None


def analyser_annonces(annonces: list[dict]) -> dict[str, dict]:
    """Analyse une liste d'annonces.

    Retourne {idweb: {'analyse_pertinence': str, 'analyse_note': int}}.
    Les annonces dont l'analyse échoue sont simplement absentes du résultat.
    """
    if not annonces:
        return {}
    if not os.environ.get("GROQ_API_KEY"):
        print("GROQ_API_KEY absent : analyse LLM ignorée.")
        return {}

    system = SYSTEM_PROMPT.format(manifeste=charger_manifeste_llm())
    client = Groq(api_key=os.environ["GROQ_API_KEY"])

    resultats: dict[str, dict] = {}
    for i, annonce in enumerate(annonces, start=1):
        idweb = annonce.get("idweb")
        if not idweb:
            continue
        print(f"  analyse {i}/{len(annonces)} : {idweb}")
        analyse = _analyser_une(client, annonce, system)
        if analyse:
            resultats[idweb] = analyse
    return resultats