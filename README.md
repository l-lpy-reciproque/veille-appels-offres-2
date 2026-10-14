# Veille appels d'offres BOAMP — reciproque

Chaque matin, une pipeline collecte les avis de marché publiés sur le BOAMP,
les tague par pôles d'activité, les classe par similarité sémantique avec le
profil de reciproque et fait évaluer les plus pertinents par un LLM. Les
annonces retenues sont consultées sur une **page web** où l'équipe peut les
marquer comme vues et leur donner sa propre note.

```
API BOAMP ─► tags par mots-clés ─► score sémantique ─► Supabase (upsert)
          ─► filtre (seuil selon nb de pôles) ─► analyse LLM (Groq)
          ─► suppression des annonces expirées depuis plus d'un mois

Page web (GitHub Pages) ◄─► Supabase : lecture des annonces retenues,
                                        écriture de « vue » et de l'évaluation
```

**Page :** https://l-lpy-reciproque.github.io/veille-appels-offres-2/
(accès sur identifiant, comptes créés dans Supabase).

## La page web

Fichier unique [`web/index.html`](web/index.html), sans étape de build. Elle lit
directement la table `annonces_boamp` : rien n'est régénéré chaque jour, les
nouvelles annonces apparaissent dès que la pipeline a tourné.

- **Annonces affichées** : celles marquées `rapporte` par la pipeline, plus
  celles déjà évaluées par l'équipe (même si elles ne passent plus le filtre).
- **Tri** : date de publication la plus récente d'abord ; à date égale, note
  LLM, puis nombre de pôles, puis score.
- **En tête** : nombre d'annonces publiées aujourd'hui (toutes celles
  collectées, et parmi elles les retenues). Vaut 0 avant le run du matin et
  les jours sans publication.
- **Colonnes** : acheteur, objet et badges de pôles, descripteurs, marché,
  dates, proximité sémantique, analyse LLM, **Évaluation** (note de 0 à 5 ;
  recliquer la note l'efface ; affiche qui a modifié en dernier et quand),
  lien vers l'avis, **Vue** (case à cocher ; grise la ligne).
- **Filtres** : masquer les vues, masquer les annonces dont la date limite est
  passée (actif par défaut), date de publication minimale, recherche texte.

Publication : [`.github/workflows/pages.yml`](.github/workflows/pages.yml)
déploie `web/` à chaque push sur `main` qui modifie ce dossier. GitHub Pages
met la page en cache jusqu'à 10 minutes : après un déploiement, recharger avec
Cmd + Shift + R.

Pour tester en local :

```bash
python3 -m http.server 8000 --directory web   # puis http://localhost:8000
```

## Pipeline

### Démarrage rapide

```bash
python -m venv venv && source venv/bin/activate
pip install -r requirements.txt
python test_connexion_db.py   # vérifie l'accès à Supabase
python src/main.py            # lance la pipeline complète
```

Les scripts se lancent **depuis la racine du dépôt**, sous la forme
`python src/<fichier>.py` : les imports entre modules sont « à plat »
(`from db import ...`) et ne fonctionnent que parce que `src/` est alors dans
le `sys.path`.

### Variables d'environnement (`.env` en local, secrets GitHub en CI)

| Variable | Obligatoire | Rôle |
|---|---|---|
| `SUPABASE_DB_URL` | oui | Chaîne de connexion Postgres Supabase (Session pooler). |
| `GROQ_API_KEY` | non | Clé Groq. Absente : aucune analyse LLM pendant le run. |

### Exécution quotidienne

[`.github/workflows/pipeline.yml`](.github/workflows/pipeline.yml) lance
`python src/main.py` tous les jours à 6 h UTC (8 h à Paris en été, 7 h en
hiver), et peut être déclenché à la main depuis l'onglet Actions. Il met en
cache le modèle Hugging Face. GitHub désactive les tâches planifiées d'un dépôt
public après 60 jours sans commit (un email prévient ; un clic dans Actions
les réactive).

### Étapes

1. **Collecte incrémentale** (`ingestion.py`). Le curseur `depuis` est le
   `MAX(dateparution)` en base (table vide : aujourd'hui − 7 jours). L'API
   OpenDataSoft du BOAMP est interrogée avec une correspondance exacte sur des
   descripteurs métier (`MOTS_CLES_DESCRIPTEURS_METIER`), `datelimitereponse
   >= now()` et `dateparution >= depuis`, plafonnée à `MAX_ANNONCES` (1000).
   Le dernier jour est toujours re-collecté, sans risque : l'écriture se fait
   en `INSERT … ON CONFLICT (idweb) DO UPDATE`, qui ne touche jamais aux
   colonnes de l'équipe (`vue`, `note_humaine`).
2. **Tags** (`tagging.py`, `mots_cles.py`). Cinq clusters de mots-clés
   (prestations, numérique/multimédia, muséo/scéno, secteurs transverses,
   institutions) cherchés dans `objet`, `nomacheteur` et `descripteur_libelle`
   normalisés (minuscules, sans accents). Une colonne `match_*` par cluster,
   et `total_poles` pour leur somme.
3. **Score sémantique** (`scoring.py`). Similarité cosinus entre le manifeste
   court et l'**objet** de l'annonce, avec `paraphrase-multilingual-mpnet-base-v2`.
4. **Sélection** (`restitution.py`). Le score exigé baisse quand le nombre de
   pôles augmente ; les annonces retenues sont marquées `rapporte = true`.

   | `total_poles` | Score exigé |
   |---|---|
   | ≥ 3 | > 0.2 |
   | 2 | > 0.3 |
   | 1 | > 0.4 |
   | 0 | > 0.5 |

5. **Analyse LLM** (`analyse.py`). Chaque annonce retenue est soumise à Groq
   (`openai/gpt-oss-120b`) avec le manifeste détaillé ; il renvoie une phrase
   de pertinence et une note sur 5 (`analyse_pertinence`, `analyse_note`). Un
   échec pour une annonce la laisse simplement sans analyse.
6. **Nettoyage** (`db.supprimer_annonces_expirees`). Suppression des annonces
   dont la date limite est dépassée depuis plus d'un mois, **sauf celles
   évaluées par l'équipe**, conservées pour comparer note humaine, note LLM et
   score. Une annonce supprimée ne revient pas, puisque la collecte ignore les
   avis expirés.

## Scripts ponctuels

| Commande | Usage |
|---|---|
| `python src/recalculer_scores.py similarite` | Recalcule `score_similarite` pour toute la table avec le manifeste court actuel. |
| `python src/recalculer_rapporte.py` | Recalcule `rapporte` (annonces retenues) à partir des scores et tags stockés. |
| `python src/recalculer_scores.py llm` | Analyse par le LLM les annonces retenues sans note (reprise possible après un quota Groq épuisé). Avec `--reinitialiser` : efface toutes les analyses puis ré-analyse toutes les retenues (vérifie d'abord que l'API répond ; enregistre par lots de 25). |
| `python src/analyse_exploratoire.py` | Graphiques sur tout l'historique : score selon le nombre de tags, score selon la note LLM, heatmap tags × note. Dépendances à part : `pip install -r requirements-analyse.txt`. |
| `python test_connexion_db.py` | Vérifie la connexion Supabase et affiche le nombre de lignes. |

## Personnaliser la veille

### Textes de profil (`profil/`)
Modifiables sans toucher au code ; les chemins sont dans `src/profil.py`.
- `manifeste_reciproque_2.txt` : **manifeste court**, pour les embeddings. Le
  modèle tronque autour de 128 tokens : texte bref et descriptif, sans
  critères d'exclusion.
- `manifeste_reciproque_llm.txt` : **manifeste détaillé**, contexte du LLM ;
  peut contenir des critères d'appréciation.

### Mots-clés et clusters
- Les mots-clés de `mots_cles.py` doivent être **en minuscules et sans
  accents** (simple test de sous-chaîne sur le texte normalisé).
- Ajouter un cluster demande : l'entrée dans `tagging.CLUSTERS`, la colonne
  `match_<nom>` (integer) dans Supabase, et le libellé et la couleur du badge
  dans `COULEURS_TAGS` de `web/index.html`.

### Après une modification
La pipeline ne recalcule rien pour les annonces déjà en base.

| Modification | À lancer |
|---|---|
| Seuils (`restitution.py`) | `recalculer_rapporte.py`, puis `recalculer_scores.py llm` |
| Manifeste court | `recalculer_scores.py similarite`, `recalculer_rapporte.py`, puis `recalculer_scores.py llm` |
| Manifeste LLM ou prompt | `recalculer_scores.py llm --reinitialiser` |
| Mots-clés ou clusters | Aucun script ne re-tague l'existant : seules les nouvelles annonces en profitent. |

`recalculer_scores.py llm` (sans `--reinitialiser`) sert à noter les annonces
qui deviennent retenues après un recalcul, sans toucher aux notes existantes.

## Base de données (Supabase)

Table `annonces_boamp`, clé `idweb` :
- **champs BOAMP** : `objet`, `nomacheteur`, `code_departement`,
  `dateparution`, `datelimitereponse` (texte ISO), `famille_libelle`,
  `descripteur_libelle`, `procedure_libelle`, `url_avis` ;
- **calculés par la pipeline** : `match_*`, `total_poles`, `score_similarite`,
  `rapporte`, `analyse_pertinence`, `analyse_note`, `date_ingestion` (mise à
  jour à chaque upsert) ;
- **saisis sur la page** : `vue` (booléen), `note_humaine` (0 à 5) ;
- **traçabilité** : `annotation_par` (email) et `annotation_le`, remplis par
  le trigger `tracer_annotation` uniquement quand `vue` ou `note_humaine`
  change.

Accès depuis la page :
- RLS activée ; politiques `lecture` (SELECT) et `maj` (UPDATE) réservées au
  rôle `authenticated` ; le rôle `anon` n'a aucun droit ;
- `authenticated` ne peut modifier que les colonnes `vue` et `note_humaine`
  (droits par colonne) ;
- inscriptions publiques désactivées : les comptes (email + mot de passe) se
  créent dans Authentication → Users ;
- la clé publishable inscrite dans `web/index.html` est publique par
  conception. N'y mettre **jamais** une clé secrète ou `service_role`.

La pipeline se connecte directement en Postgres (`SUPABASE_DB_URL`) et n'est
pas soumise à ces règles.

Tout ce qui précède (table, droits, trigger) est dans
[`sql/schema_supabase.sql`](sql/schema_supabase.sql), à exécuter dans le SQL
editor de Supabase pour recréer le projet. Le script peut être relancé sans
risque sur une base déjà à jour. Toute modification du schéma doit y être
reportée.

## Structure du dépôt

```
src/
  main.py                  point d'entrée de la pipeline
  ingestion.py             appel paginé à l'API BOAMP
  mots_cles.py             listes de mots-clés par cluster
  tagging.py               colonnes match_* et total_poles
  scoring.py               embeddings et similarité cosinus
  profil.py                chargement des manifestes
  db.py                    connexion, upsert, lectures, analyses, nettoyage
  restitution.py           seuils de sélection et tri
  analyse.py               analyse de pertinence par Groq
  utils.py                 normalisation de texte, aplatissement
  recalculer_scores.py     recalcul des scores de similarité et des analyses LLM
  recalculer_rapporte.py   recalcul de la colonne rapporte
  analyse_exploratoire.py  graphiques sur l'historique (hors pipeline)
web/index.html             page de suivi des annonces
profil/                    manifestes (court et LLM)
sql/schema_supabase.sql    schéma, droits et trigger Supabase
test_connexion_db.py       vérification de la connexion Supabase
.github/workflows/         pipeline quotidienne et publication de la page
```
