# Pipeline de veille — appels d'offres BOAMP

Pipeline automatisée de collecte, de tri, d'analyse et de restitution des avis
de marché publiés sur le BOAMP, filtrés par descripteurs métier, classés par
similarité sémantique avec le profil d'activité de reciproque, puis évalués
par un LLM.

Chaque matin, la pipeline :
1. récupère les nouvelles annonces publiées sur le BOAMP (depuis la dernière
   `dateparution` connue en base) ;
2. les enrichit de tags thématiques (par pôles d'activité) ;
3. calcule un score de similarité sémantique avec le manifeste de reciproque ;
4. les enregistre dans Supabase (table `annonces_boamp`) ;
5. fait évaluer par un LLM (via Groq) les annonces retenues après filtrage ;
6. génère un rapport HTML du lot traité et l'envoie par email.

## Structure

- `profil/manifeste_reciproque_0.txt` — texte décrivant le profil d'activité,
  utilisé pour le calcul de similarité et le prompt de groq. Modifiable sans toucher au code.
- `profil/manifeste_reciproque_2.txt` — texte court (moins de 128 tokens) décrivant le profil d'activité, utilisé pour le calcul de similarité. Modifiable sans toucher au code.
- `profil/manifeste_reciproque_llm.txt` — texte décrivant le profil d'activité,
  utilisé pour le prompt de groq. Modifiable sans toucher au code.
- `src/ingestion.py` — appel à l'API BOAMP, filtré sur les descripteurs métier
  (`MOTS_CLES_DESCRIPTEURS_METIER`, correspondance exacte sur
  `descripteur_libelle`) et sur les avis dont la date limite de réponse n'est
  pas dépassée.
- `src/mots_cles.py` — listes de mots-clés par cluster thématique (prestations,
  numérique/multimédia, muséo/scéno, secteurs transverses, institutions).
- `src/tagging.py` — calcul des tags binaires par cluster (`match_*`) +
  `total_poles`.
- `src/scoring.py` — calcul des embeddings et de la similarité cosinus avec le
  manifeste.
- `src/profil.py` — chargement du fichier de profil.
- `src/db.py` — connexion Supabase, écriture (upsert) des annonces, lecture
  des lignes (par date ou intégrale), enregistrement des analyses LLM.
- `src/restitution.py` — filtrage (seuil de score dégressif selon le nombre de
  tags) et tri des annonces retenues.
- `src/analyse.py` — analyse de pertinence par LLM (Groq) : phrase d'analyse +
  note sur 5, pour les annonces retenues après restitution.
- `src/rapport.py` — génération du document HTML (badges par cluster, note
  LLM, dates).
- `src/generer_rapport.py` — génération d'un rapport HTML pour une plage de
  dates choisie, indépendamment d'un run de collecte.
- `src/envoi_mail.py` — envoi du rapport en pièce jointe par SMTP.
- `src/analyse_exploratoire.py` — script d'analyse ad hoc (hors pipeline), à
  exécuter en local pour visualiser les relations entre score, tags et notes
  LLM sur l'ensemble de l'historique stocké.
- `src/recalculer_score.py` — script d'analyse ad hoc (hors pipeline), à exécuter en local pour recalculer l'entiereté des scores calculés et générés précédemment, afin d'analyser les résultats avec les systèmes du moment.
- `src/main.py` — orchestration du pipeline (point d'entrée).
- `src/utils.py` — fonctions utilitaires (normalisation, aplatissement).
- `.github/workflows/pipeline.yml` — exécution automatique planifiée.

## Fonctionnement détaillé

### Ingestion
`ingestion.py` interroge l'API OpenDataSoft du BOAMP en filtrant sur une liste
de descripteurs métier contrôlés (`MOTS_CLES_DESCRIPTEURS_METIER`, nomenclature
BOAMP, correspondance exacte via l'opérateur `in`), et ne conserve que les avis
dont la date limite de réponse n'est pas dépassée. Lors d'un run incrémental,
seules les annonces publiées depuis la dernière `dateparution` connue en base
sont récupérées (logique portée par `db.obtenir_derniere_date_parution`).

### Tags thématiques
Chaque annonce est confrontée à cinq clusters de mots-clés (prestations,
numérique/multimédia, muséo/scéno, secteurs transverses, institutions), sur la
réunion normalisée (minuscule, sans accents) des champs `objet`, `nomacheteur`
et `descripteur_libelle`. Le résultat est stocké sous forme de cinq colonnes
binaires (`match_*`) plus un `total_poles` correspondant à la somme des
correspondances.

### Scoring
Le score de similarité cosinus est calculé entre les embeddings du manifeste et
ceux de l'objet de chaque annonce, via le modèle
`paraphrase-multilingual-mpnet-base-v2` de Hugging Face.

### Sélection pour la restitution
Le seuil de score exigé décroît avec le nombre de pôles matchés (`total_poles`) :

| `total_poles` | Seuil de score |
|---|---|
| ≥ 3 | > 0.2 |
| 2 | > 0.3 |
| 1 | > 0.4 |
| 0 | > 0.5 |

### Analyse LLM
Les annonces retenues pour la restitution sont ensuite soumises à un LLM (Groq,
modèle `openai/gpt-oss-120b`) qui renvoie une phrase d'analyse et une note de
pertinence sur 5, sur la base du manifeste de reciproque. En cas d'échec pour
une annonce (timeout, quota, réponse invalide), celle-ci est simplement
ignorée — la pipeline continue et le rapport est généré sans analyse pour
elle. Si `GROQ_API_KEY` n'est pas configurée, l'analyse est ignorée pour tout
le run.

### Rapport HTML
Le rapport est généré à partir du même `depuis` que celui utilisé pour
l'ingestion du run, afin de refléter exactement le lot d'annonces traité. 
Il affiche, par annonce : acheteur, objet et ses badges de tags par cluster, 
descripteurs, marché (famille + procédure), dates (publication + limite de 
réponse), score de proximité, analyse LLM (badge de note + phrase), lien 
vers l'avis. Les annonces sont triées par note LLM décroissante, puis par 
nombre de tags, puis par score de proximité — celles jamais analysées sont 
placées en dernier.

### Analyse exploratoire (hors pipeline)
`analyse_exploratoire.py` est un script indépendant, à lancer ponctuellement en
local, qui trace trois graphiques sur l'ensemble de l'historique stocké : 
- score de similarité vs nombre de tags,
- score vs note LLM,
- une heatmap de comptage tags vs note LLM. 
Dépendances séparées dans `requirements-analyse.txt` pour ne pas alourdir 
l'installation du pipeline automatisé.

## Exécution locale

```bash
pip install -r requirements.txt
python src/main.py
```

Pour l'analyse exploratoire :

```bash
pip install -r requirements-analyse.txt
python src/analyse_exploratoire.py
```

Pour générer un rapport sur une plage de dates choisie, indépendamment d'un run :

```bash
python src/generer_rapport.py 2026-09-01
```

## Variables d'environnement / secrets requis

- `SUPABASE_DB_URL` — chaîne de connexion Supabase (Session pooler).
- `GROQ_API_KEY` — clé API Groq, pour l'analyse LLM (optionnelle : ignorée
  proprement si absente).
- Variables SMTP pour l'envoi du rapport par mail (voir `envoi_mail.py`).