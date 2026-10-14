# Pipeline de veille — appels d'offres BOAMP

Pipeline automatisée de collecte, de tri, d'analyse et de restitution des avis
de marché publiés sur le BOAMP. Les annonces sont filtrées par descripteurs
métier, taguées par pôles d'activité, classées par similarité sémantique avec
le profil de reciproque, puis évaluées par un LLM. Le résultat est un rapport
HTML envoyé par email.

```
API BOAMP ─► tags par mots-clés ─► score sémantique ─► Supabase (upsert)
          ─► filtre (seuil selon nb de pôles) ─► analyse LLM (Groq)
          ─► rapport HTML ─► email
```

## Démarrage rapide

```bash
python -m venv venv && source venv/bin/activate
pip install -r requirements.txt
# créer un fichier .env à la racine (voir ci-dessous)
python test_connexion_db.py   # vérifie l'accès à Supabase
python src/main.py            # lance la pipeline complète
```

Les scripts se lancent **depuis la racine du dépôt**, sous la forme
`python src/<fichier>.py` : les imports entre modules sont « à plat »
(`from db import ...`) et ne fonctionnent que parce que `src/` est alors dans
le `sys.path`.

### Variables d'environnement (`.env`)

| Variable | Obligatoire | Rôle |
|---|---|---|
| `SUPABASE_DB_URL` | oui | Chaîne de connexion Postgres Supabase (Session pooler). |
| `GROQ_API_KEY` | non | Clé Groq. Absente : l'analyse LLM est ignorée pour tout le run. |
| `SMTP_USER` | non | Adresse d'expédition. |
| `SMTP_PASSWORD` | non | Mot de passe d'application SMTP (pas le mot de passe du compte). |
| `MAIL_DESTINATAIRE` | non | Destinataire(s), séparés par des virgules. |
| `SMTP_HOST` / `SMTP_PORT` | non | Par défaut `smtp.gmail.com` / `587`. |

Si l'une des trois variables `SMTP_USER`, `SMTP_PASSWORD`, `MAIL_DESTINATAIRE`
manque, le rapport est généré mais pas envoyé.

## Commandes

| Commande | Usage |
|---|---|
| `python src/main.py` | Run complet : collecte, tags, score, écriture en base, analyse LLM, rapport, mail. |
| `python src/generer_rapport.py 2026-09-01` | Régénère un rapport HTML depuis la base pour les annonces publiées à partir de cette date (sans argument : 7 derniers jours). Aucune collecte, aucun appel LLM. |
| `python src/recalculer_rapporte.py` | Recalcule la colonne `rapporte` de toute la table. À lancer après toute modification des seuils ou des mots-clés. |
| `python test_connexion_db.py` | Vérifie la connexion Supabase et affiche le nombre de lignes. |

Les rapports sont écrits dans le répertoire courant sous le nom
`rapport_boamp_<date>.html` (ignorés par git).

## Fonctionnement

### 1. Collecte incrémentale
`main.py` lit le `MAX(dateparution)` de la table `annonces_boamp` et s'en sert
comme curseur `depuis` (table vide : aujourd'hui − 7 jours). `ingestion.py`
interroge l'API OpenDataSoft du BOAMP avec :
- une correspondance exacte sur une liste de descripteurs métier
  (`MOTS_CLES_DESCRIPTEURS_METIER`, vocabulaire contrôlé du BOAMP) ;
- `datelimitereponse >= now()` (avis encore ouverts) ;
- `dateparution >= depuis`.

La pagination est plafonnée par `MAX_ANNONCES` (1000). Le dernier jour est
toujours re-collecté, ce qui est sans risque : l'écriture se fait en
`INSERT … ON CONFLICT (idweb) DO UPDATE`.

### 2. Tags thématiques
`tagging.py` confronte chaque annonce aux clusters de mots-clés de
`mots_cles.py` (prestations, numérique/multimédia, muséo/scéno, secteurs
transverses, institutions). Le texte cherché est la réunion de `objet`,
`nomacheteur` et `descripteur_libelle`, normalisée (minuscules, sans accents).
Chaque cluster produit une colonne booléenne `match_*`, et `total_poles` en
fait la somme.

### 3. Score sémantique
`scoring.py` calcule la similarité cosinus entre l'embedding du manifeste court
et celui de l'**objet** de l'annonce, avec le modèle
`paraphrase-multilingual-mpnet-base-v2` (sentence-transformers).

### 4. Sélection
`restitution.py` applique un seuil de score qui baisse quand le nombre de
pôles matchés augmente :

| `total_poles` | Score exigé |
|---|---|
| ≥ 3 | > 0.2 |
| 2 | > 0.3 |
| 1 | > 0.4 |
| 0 | > 0.5 |

Les annonces retenues sont marquées `rapporte = true` en base et envoyées au LLM.

### 5. Analyse LLM
`analyse.py` soumet chaque annonce retenue à Groq (modèle `openai/gpt-oss-120b`)
avec le manifeste détaillé en contexte. Le modèle renvoie une phrase de
pertinence et une note sur 5, stockées dans `analyse_pertinence` et
`analyse_note`. Si l'appel échoue pour une annonce (timeout, quota, réponse
invalide), elle reste sans analyse et la pipeline continue.

### 6. Rapport et envoi
Le rapport est construit à partir de la base, avec le même `depuis` que la
collecte : il reflète donc exactement le lot traité par le run. Pour chaque
annonce, il affiche l'acheteur, l'objet avec ses badges de pôles, les
descripteurs, la famille et la procédure du marché, les dates de publication et
de limite de réponse, le score de proximité, la note et la phrase du LLM, et le
lien vers l'avis. Tri : note LLM décroissante, puis nombre de pôles, puis
score. Les annonces sans note sont placées en dernier.

`envoi_mail.py` envoie le fichier en pièce jointe, avec pour objet
« veille appels d'offre boamp AAAA-MM-JJ ».

## Personnaliser la veille

### Textes de profil (`profil/`)
Modifiables sans toucher au code. Le choix des fichiers se fait dans
`src/profil.py` :
- **manifeste court** (`CHEMIN_MANIFESTE`, actuellement
  `manifeste_reciproque_2.txt`) : sert aux embeddings. Le modèle tronque
  autour de 128 tokens, donc seul le début du texte compte. Un texte bref et
  descriptif, sans critères d'exclusion, fonctionne mieux.
- **manifeste LLM** (`manifeste_reciproque_llm.txt`) : contexte long fourni au
  LLM, qui peut contenir des critères d'appréciation.

`manifeste_reciproque_0.txt` et `manifeste_reciproque_1.txt` sont des variantes
qui ne sont pas utilisées actuellement.

### Mots-clés et clusters
- Les mots-clés de `mots_cles.py` doivent être **en minuscules et sans
  accents** : la correspondance est un simple test de sous-chaîne sur le texte
  normalisé.
- Ajouter un cluster demande trois modifications : l'entrée dans
  `tagging.CLUSTERS`, la colonne `match_<nom>` (booléenne) dans la table
  Supabase, et le libellé et la couleur du badge dans `rapport.COULEURS_TAGS`.

### Après une modification
Les annonces déjà en base ne sont **ni re-taguées ni re-scorées** :
`total_poles` et `score_similarite` restent ceux calculés à l'ingestion.
Après avoir changé les seuils, les mots-clés ou le manifeste, lancez
`python src/recalculer_rapporte.py`, qui recalcule `rapporte` à partir des
valeurs stockées.

## Base de données

Table `annonces_boamp`, clé primaire `idweb` :
- champs BOAMP : `objet`, `nomacheteur`, `code_departement`, `dateparution`,
  `datelimitereponse`, `famille_libelle`, `descripteur_libelle`,
  `procedure_libelle`, `url_avis` ;
- calculés : `match_*`, `total_poles`, `score_similarite`, `rapporte`,
  `analyse_pertinence`, `analyse_note`, `date_ingestion` (mise à jour à
  chaque upsert) ;
- revue manuelle : `vue` et `note_humaine`, qu'aucun script ne modifie.

## Structure du dépôt

```
src/
  main.py                 point d'entrée de la pipeline
  ingestion.py            appel paginé à l'API BOAMP
  mots_cles.py            listes de mots-clés par cluster
  tagging.py              colonnes match_* et total_poles
  scoring.py              embeddings et similarité cosinus
  profil.py               chargement des manifestes
  db.py                   connexion Supabase, upsert, lectures, analyses
  restitution.py          seuils de sélection et tri
  analyse.py              analyse de pertinence par Groq
  rapport.py              génération du HTML (badges, notes, dates)
  generer_rapport.py      rapport à partir de la base pour une date donnée
  envoi_mail.py           envoi SMTP du rapport
  recalculer_rapporte.py  recalcul de la colonne rapporte
  utils.py                normalisation de texte, aplatissement
profil/                   textes de profil (manifestes)
test_connexion_db.py      vérification de la connexion Supabase
.github/workflows/        exécution sur GitHub Actions
```

`requirements-analyse.txt` (pandas, seaborn, matplotlib) n'est pas nécessaire
à la pipeline. Il servait à un script d'analyse exploratoire qui n'est plus
dans le dépôt.

## Exécution automatique (GitHub Actions)

`.github/workflows/pipeline.yml` lance `python src/main.py` sous Python 3.11 et
met en cache le modèle Hugging Face (`~/.cache/huggingface`). Il est
actuellement **déclenché à la main uniquement** (`workflow_dispatch`). Pour un
run quotidien :
1. décommenter le bloc `schedule` (cron `0 6 * * *`, soit 8 h à Paris en été) ;
2. ajouter les secrets `GROQ_API_KEY`, `SMTP_USER`, `SMTP_PASSWORD` et
   `MAIL_DESTINATAIRE` dans le dépôt, puis décommenter les lignes `env`
   correspondantes. Seul `SUPABASE_DB_URL` est transmis pour l'instant.
