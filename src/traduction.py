"""Traduction automatique en français des avis TED non francophones.

Modèle local facebook/m2m100_418M (licence MIT, ~2 Go, téléchargé et mis en
cache au premier appel) : un seul modèle pour toutes les langues de l'UE.
NLLB, plus précis, est exclu car sa licence interdit l'usage commercial.

Seuls l'objet et le nom de l'acheteur sont traduits (textes courts), pour le
tagging par mots-clés, l'affichage et le LLM. La traduction est imparfaite
(noms propres parfois traduits à tort) : l'original reste en base.
"""

from functools import cache

NOM_MODELE = "facebook/m2m100_418M"
TAILLE_LOT = 16
LONGUEUR_MAX = 256  # tokens, en entrée comme en sortie

# Code de langue TED (ISO 639-3) -> code m2m100. Langue absente (maltais,
# basque…) : l'avis n'est pas traduit.
LANGUES = {
    "bul": "bg", "cat": "ca", "ces": "cs", "dan": "da", "deu": "de", "ell": "el",
    "eng": "en", "est": "et", "fin": "fi", "gle": "ga", "glg": "gl", "hrv": "hr",
    "hun": "hu", "isl": "is", "ita": "it", "lav": "lv", "lit": "lt", "ltz": "lb",
    "mkd": "mk", "nld": "nl", "nor": "no", "pol": "pl", "por": "pt", "ron": "ro",
    "slk": "sk", "slv": "sl", "spa": "es", "sqi": "sq", "srp": "sr", "swe": "sv",
    "tur": "tr", "ukr": "uk",
}


@cache
def _charger():
    from transformers import M2M100ForConditionalGeneration, M2M100Tokenizer

    print(f"Chargement du modèle de traduction {NOM_MODELE}…")
    tokenizer = M2M100Tokenizer.from_pretrained(NOM_MODELE)
    modele = M2M100ForConditionalGeneration.from_pretrained(NOM_MODELE).eval()
    return tokenizer, modele


def _traduire(textes: list[str], langue: str) -> list[str]:
    import torch

    tokenizer, modele = _charger()
    tokenizer.src_lang = langue
    traductions = []
    for debut in range(0, len(textes), TAILLE_LOT):
        entree = tokenizer(
            textes[debut:debut + TAILLE_LOT], return_tensors="pt",
            padding=True, truncation=True, max_length=LONGUEUR_MAX,
        )
        with torch.no_grad():
            sortie = modele.generate(
                **entree, forced_bos_token_id=tokenizer.get_lang_id("fr"),
                max_new_tokens=LONGUEUR_MAX, num_beams=1,
            )
        traductions += tokenizer.batch_decode(sortie, skip_special_tokens=True)
    return traductions


def traduire_annonces(annonces: list[dict]) -> None:
    """Ajoute objet_fr et nomacheteur_fr à chaque annonce, en place, en
    regroupant les annonces par langue (un lot = une langue source)."""
    par_langue: dict[str, list[dict]] = {}
    for annonce in annonces:
        code = LANGUES.get(annonce.get("langue"))
        if code:
            par_langue.setdefault(code, []).append(annonce)

    nb = sum(len(lot) for lot in par_langue.values())
    print(f"Traduction de {nb} avis sur {len(annonces)} ({len(par_langue)} langue(s))…")
    for code, lot in par_langue.items():
        textes = [t for a in lot for t in (a.get("objet") or "", a.get("nomacheteur") or "")]
        traductions = _traduire(textes, code)
        for i, annonce in enumerate(lot):
            annonce["objet_fr"] = traductions[2 * i] or None
            annonce["nomacheteur_fr"] = traductions[2 * i + 1] or None
