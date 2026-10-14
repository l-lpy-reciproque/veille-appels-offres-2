"""Envoi par email du rapport HTML quotidien de veille BOAMP.

Variables d'environnement attendues (à définir en secrets GitHub) :
    SMTP_USER         — adresse d'expédition (ex. une adresse Gmail dédiée)
    SMTP_PASSWORD     — mot de passe d'application SMTP (pas le mot de passe du compte)
    MAIL_DESTINATAIRE — adresse(s) de destination, séparée(s) par des virgules
    SMTP_HOST         — optionnel, défaut : smtp.gmail.com
    SMTP_PORT         — optionnel, défaut : 587
"""

import os
import smtplib
from datetime import date
from email.message import EmailMessage
from pathlib import Path


def configurer_email_disponible() -> bool:
    """Vrai si toutes les variables d'environnement nécessaires sont présentes.

    Permet de ne pas planter un run local où aucun SMTP n'est configuré.
    """
    return all(
        os.environ.get(var)
        for var in ("SMTP_USER", "SMTP_PASSWORD", "MAIL_DESTINATAIRE")
    )


def envoyer_rapport(chemin_html: str | Path) -> None:
    """Envoie le rapport HTML en pièce jointe (fichier .html ouvrable en local).

    L'objet du mail est « veille appels d'offre boamp [AAAA-MM-JJ] ».
    Le corps du mail reste volontairement minimal : c'est la pièce jointe
    HTML qui contient le rapport à proprement parler.
    """
    chemin = Path(chemin_html)
    expediteur = os.environ["SMTP_USER"]
    mot_de_passe = os.environ["SMTP_PASSWORD"]
    destinataires = [
        adresse.strip()
        for adresse in os.environ["MAIL_DESTINATAIRE"].split(",")
        if adresse.strip()
    ]
    hote = os.environ.get("SMTP_HOST", "smtp.gmail.com")
    port = int(os.environ.get("SMTP_PORT", "587"))

    sujet = f"veille appels d'offre boamp {date.today().isoformat()}"

    msg = EmailMessage()
    msg["Subject"] = sujet
    msg["From"] = expediteur
    msg["To"] = ", ".join(destinataires)
    msg.set_content(
        "Rapport de veille BOAMP en pièce jointe "
        "(fichier .html ouvrable dans n'importe quel navigateur)."
    )

    msg.add_attachment(
        chemin.read_bytes(),
        maintype="text",
        subtype="html",
        filename=chemin.name,
    )

    with smtplib.SMTP(hote, port, timeout=30) as smtp:
        smtp.starttls()
        smtp.login(expediteur, mot_de_passe)
        smtp.send_message(msg)