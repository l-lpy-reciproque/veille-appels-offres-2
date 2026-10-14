"""Analyse exploratoire ad hoc des données de veille — à exécuter en local
depuis VS Code, à tout moment, sur l'ensemble de l'historique stocké.

N'est pas branché sur la pipeline ni le rapport : script indépendant.

Exécution locale :
    pip install -r requirements-analyse.txt
    python src/analyse_exploratoire.py
"""

import matplotlib.pyplot as plt
import pandas as pd
import seaborn as sns
from dotenv import load_dotenv

from db import obtenir_connexion, recuperer_toutes_les_lignes


def charger_donnees() -> pd.DataFrame:
    load_dotenv()
    conn = obtenir_connexion()
    lignes = recuperer_toutes_les_lignes(conn)
    conn.close()
    return pd.DataFrame(lignes)


def tracer_graphiques(df: pd.DataFrame) -> None:
    sns.set_theme(style="darkgrid")

    df_notes = df.dropna(subset=["analyse_note"])

    fig, axes = plt.subplots(1, 3, figsize=(18, 5))

    sns.boxplot(data=df, x="total_poles", y="score_similarite", ax=axes[0])
    axes[0].set_title(f"Score de similarité vs nb de tags (n={len(df)})")
    axes[0].set_xlabel("Nombre de tags")
    axes[0].set_ylabel("Similarité sémantique")

    sns.boxplot(data=df_notes, x="analyse_note", y="score_similarite", ax=axes[1])
    axes[1].set_title(f"Score de similarité vs note LLM (n={len(df_notes)})")
    axes[1].set_xlabel("Note LLM")
    axes[1].set_ylabel("Similarité sémantique")

    tableau_croise = pd.crosstab(df_notes["total_poles"], df_notes["analyse_note"])
    sns.heatmap(tableau_croise, annot=True, fmt="d", cmap="Blues", ax=axes[2], cbar=False)
    
    axes[2].set_title(f"Nb de tags vs note LLM (n={len(df_notes)})")
    axes[2].set_xlabel("Note LLM")
    axes[2].set_ylabel("Nombre de tags")
    axes[2].invert_yaxis()

    plt.tight_layout()
    plt.show()


if __name__ == "__main__":
    df = charger_donnees()
    print(f"{len(df)} annonces chargées depuis annonces_boamp.")
    print(f"{df['analyse_note'].notna().sum()} annonce(s) avec une note LLM.")
    tracer_graphiques(df)