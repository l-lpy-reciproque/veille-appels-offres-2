"""Calcul de similarité sémantique entre le profil et les annonces récupérées."""

from sentence_transformers import SentenceTransformer, util

NOM_MODELE = "paraphrase-multilingual-mpnet-base-v2"


def charger_modele() -> SentenceTransformer:
    """Charge le modèle d'embeddings (téléchargé et mis en cache au premier appel)."""
    return SentenceTransformer(NOM_MODELE)


def scorer_annonces(
    modele: SentenceTransformer, manifeste: str, annonces: list[dict]
) -> list[tuple[dict, float]]:
    """Calcule la similarité cosinus entre le manifeste et chaque annonce (champ 'objet'),
    et retourne les annonces triées par score décroissant."""
    if not annonces:
        return []
    embedding_profil = modele.encode(manifeste, convert_to_tensor=True)
    embeddings_annonces = modele.encode(
        [a["objet"] for a in annonces], convert_to_tensor=True
    )
    scores = util.cos_sim(embedding_profil, embeddings_annonces)[0]
    resultats = list(zip(annonces, scores.cpu().tolist()))
    return sorted(resultats, key=lambda x: x[1], reverse=True)
