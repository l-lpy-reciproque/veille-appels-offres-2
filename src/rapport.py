"""Génération d'un document HTML visuel des annonces sélectionnées, avec des
badges colorés par cluster thématique."""

import html
from datetime import datetime

# colonne -> (libellé affiché, couleur du badge)
COULEURS_TAGS = {
    "match_prestations": ("Prestations", "#42a016"),                      # vert
    "match_numerique_multimedia": ("Numérique / Multimédia", "#1e65b5"),  # bleu
    "match_museo_sceno": ("Muséo / Scéno", "#c7208a"),                    # rose
    "match_secteurs_transverses": ("Secteurs transverses", "#cd6409"),    # orange
    "match_institutions": ("Institutions", "#931cae"),                    # violet
}


def _badges_html(ligne: dict) -> str:
    badges = [
        f'<span style="background:{couleur};color:#fff;padding:3px 11px;'
        f'border-radius:12px;font-size:12px;margin:0 6px 4px 0;display:inline-block;">'
        f'{libelle}</span>'
        for colonne, (libelle, couleur) in COULEURS_TAGS.items()
        if ligne.get(colonne)
    ]
    return "".join(badges) if badges else '<span style="color:#999;">—</span>'


def _texte(valeur) -> str:
    return html.escape(str(valeur)) if valeur else ""


def _formater_date(valeur, avec_heure: bool = False) -> str:
    """Formate une date/datetime ISO BOAMP en JJ/MM/AAAA (+ HH:MM si demandé).
    Retourne le texte brut échappé si le format ne correspond pas à l'attendu."""
    if not valeur:
        return ""
    try:
        dt = datetime.fromisoformat(str(valeur).replace("Z", "+00:00"))
        return dt.strftime("%d/%m/%Y %H:%M" if avec_heure else "%d/%m/%Y")
    except ValueError:
        return _texte(valeur)


def _badge_note(note: int) -> str:
    """Badge coloré pour la note LLM : rouge (0) -> vert (5)."""
    teinte = (max(0, min(5, note)) / 5) * 120
    return (
        f'<span style="background:hsl({teinte:.0f}, 70%, 42%);color:#fff;'
        f'padding:3px 10px;border-radius:12px;font-size:12px;font-weight:600;'
        f'white-space:nowrap;">{note}/5</span>'
    )


def _cellule_analyse(ligne: dict) -> str:
    texte = ligne.get("analyse_pertinence")
    note = ligne.get("analyse_note")
    if texte is None and note is None:
        return '<span style="color:#999;">—</span>'
    badge = _badge_note(int(note)) if note is not None else ""
    phrase = (
        f'<div style="margin-top:6px;line-height:1.35;">{_texte(texte)}</div>'
        if texte else ""
    )
    return f"{badge}{phrase}"


def _cellule_marche(ligne: dict) -> str:
    famille = _texte(ligne.get("famille_libelle"))
    procedure = _texte(ligne.get("procedure_libelle"))
    return (
        f'<div>{famille or "—"}</div>'
        f'<div style="color:#6e6e73;margin-top:4px;">{procedure or "—"}</div>'
    )


def _cellule_dates(ligne: dict) -> str:
    publication = _formater_date(ligne.get("dateparution"))
    limite = _formater_date(ligne.get("datelimitereponse"), avec_heure=True)
    return (
        f'<div>Publié le {publication or "—"}</div>'
        f'<div style="color:#e5441a;margin-top:4px;font-weight:600;">'
        f'Limite : {limite or "—"}</div>'
    )

def _cellule_acheteur(ligne: dict) -> str:
    acheteur = _texte(ligne.get("nomacheteur"))
    departement = _texte(ligne.get("code_departement"))
    return (
        f'<div>{acheteur or "—"}</div>'
        f'<div style="color:#6e6e73;margin-top:4px;">{departement or "—"}</div>'
    )

def _ligne_html(ligne: dict) -> str:
    score = ligne.get("score_similarite") or 0
    return f"""
    <tr>
      <td>{_cellule_acheteur(ligne)}</td>
      <td>
        <div class="objet">{_texte(ligne.get("objet"))}</div>
        <div class="badges">{_badges_html(ligne)}</div>
      </td>
      <td>{_texte(ligne.get("descripteur_libelle"))}</td>
      <td>{_cellule_marche(ligne)}</td>
      <td>{_cellule_dates(ligne)}</td>
      <td class="score">{score:.3f}</td>
      <td>{_cellule_analyse(ligne)}</td>
      <td><a href="{_texte(ligne.get("url_avis")) or "#"}" target="_blank">Voir l'avis</a></td>
    </tr>"""


def generer_rapport(lignes_avant_tri, lignes: list[dict], depuis: str) -> str:
    """Génère le document HTML complet à partir des lignes déjà filtrées/triées."""
    corps = "".join(_ligne_html(ligne) for ligne in lignes)

    return f"""<!DOCTYPE html>
<html lang="fr">
<head>
<meta charset="UTF-8">
<title>Veille appels d'offres BOAMP — depuis le {depuis}</title>
<style>
  body {{
    font-family: -apple-system, "Helvetica Neue", Arial, sans-serif;
    background: #f5f5f7; margin: 0; padding: 32px; color: #1d1d1f;
  }}
  h1 {{ font-size: 22px; margin: 0 0 4px; }}
  .sous-titre {{ color: #6e6e73; margin-bottom: 24px; font-size: 14px; }}
  table {{
    width: 100%; border-collapse: collapse; background: #fff;
    box-shadow: 0 1px 4px rgba(0,0,0,0.08); border-radius: 10px; overflow: hidden;
  }}
  th {{
    text-align: left; background: #efeff1; padding: 12px 14px; font-size: 12px;
    text-transform: uppercase; letter-spacing: 0.04em; color: #555;
  }}
  td {{ padding: 14px; border-top: 1px solid #ececec; font-size: 14px; vertical-align: top; }}
  .objet {{ font-weight: 600; margin-bottom: 6px; line-height: 1.35; }}
  .badges {{ margin-top: 2px; }}
  .score {{ font-variant-numeric: tabular-nums; font-weight: 600; white-space: nowrap; }}
  a {{ color: #1565c0; text-decoration: none; font-weight: 500; }}
  a:hover {{ text-decoration: underline; }}
</style>
</head>
<body>
  <h1>Veille appels d'offres — reciproque</h1>
  <div class="sous-titre">{len(lignes)} annonce(s) sélectionnée(s) sur {len(lignes_avant_tri)} annonce(s) — publiées depuis le {depuis}</div>
  <table>
    <thead>
      <tr>
        <th>Acheteur</th>
        <th>Objet</th>
        <th>Descripteurs</th>
        <th>Marché</th>
        <th>Dates</th>
        <th>Proximité Reciproque</th>
        <th>Analyse LLM</th>
        <th>Avis</th>
      </tr>
    </thead>
    <tbody>{corps}
    </tbody>
  </table>
</body>
</html>"""