"""Filtrage et tri des annonces retenues (colonne `rapporte`, affichées sur la page web).

Deux usages : sur les tuples (annonce, score) du run courant (est_retenue,
trier_annonces, restituer), et sur des lignes plates issues directement de
Supabase, pour les scripts de recalcul (filtrer_trier_lignes).

Règle de sélection : le seuil de score exigé décroît avec le nombre de pôles
matchés. Une annonce sans aucun pôle doit donc être très pertinente pour être
retenue, tandis qu'une annonce multi-pôles est retenue plus facilement.

Avis TED non francophones (langue renseignée et différente de "fra") : ils
doivent d'abord dépasser SEUIL_SCORE_TRADUCTION, seuil qui décide aussi de leur
traduction (main.py) ; sans traduction, leurs tags ne sont pas comparables.
Les annonces BOAMP n'ont pas de langue : la règle ne les concerne pas.
"""

SEUIL_SCORE_TRES_HAUT = 0.55
SEUIL_SCORE_HAUT = 0.45
SEUIL_SCORE_MOYEN = 0.35
SEUIL_SCORE_BAS = 0.25
SEUIL_SCORE_TRADUCTION = 0.35


def est_non_francophone(annonce: dict) -> bool:
    langue = annonce.get("langue")
    return bool(langue) and langue != "fra"


def _est_retenue(total_poles: int, score: float, non_francophone: bool = False) -> bool:
    if non_francophone and score <= SEUIL_SCORE_TRADUCTION:
        return False
    if total_poles >= 3:
        return score > SEUIL_SCORE_BAS
    if total_poles == 2:
        return score > SEUIL_SCORE_MOYEN
    if total_poles == 1:
        return score > SEUIL_SCORE_HAUT
    return score > SEUIL_SCORE_TRES_HAUT


def _cle_tri(total_poles: int, score: float) -> tuple[int, float]:
    # Tri principal sur le nombre de pôles, secondaire sur le score.
    return (total_poles, score)


def est_retenue(annonce_score: tuple[dict, float]) -> bool:
    """Pour les tuples (annonce, score) issus du run courant."""
    annonce, score = annonce_score
    return _est_retenue(annonce.get("total_poles", 0), score, est_non_francophone(annonce))


def trier_annonces(resultats: list[tuple[dict, float]]) -> list[tuple[dict, float]]:
    return sorted(
        resultats,
        key=lambda ann_score: _cle_tri(ann_score[0].get("total_poles", 0), ann_score[1]),
        reverse=True,
    )


def restituer(resultats: list[tuple[dict, float]]) -> list[tuple[dict, float]]:
    """Applique le filtre puis le tri sur les résultats du run courant."""
    return trier_annonces([r for r in resultats if est_retenue(r)])

        
def _cle_tri_lignes(total_poles: int, score: float, note) -> tuple:
    """Meilleure note LLM d'abord, puis nb de tags, puis score.
    Les annonces sans note (jamais analysées) sont placées en dernier."""
    note_valeur = note if note is not None else -1
    return (note_valeur, total_poles, score)


def filtrer_trier_lignes(lignes: list[dict]) -> list[dict]:
    """Applique le même filtre sur des lignes plates issues de Supabase
    (dict avec les clés 'total_poles', 'score_similarite', 'analyse_note'),
    puis trie par note LLM décroissante, nb de tags, score de proximité."""
    retenues = [
        ligne
        for ligne in lignes
        if _est_retenue(
            ligne.get("total_poles") or 0,
            ligne.get("score_similarite") or 0,
            est_non_francophone(ligne),
        )
    ]
    return sorted(
        retenues,
        key=lambda ligne: _cle_tri_lignes(
            ligne.get("total_poles") or 0,
            ligne.get("score_similarite") or 0,
            ligne.get("analyse_note"),
        ),
        reverse=True,
    )