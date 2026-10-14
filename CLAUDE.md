# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Overview

Daily monitoring pipeline for French public tenders (BOAMP): fetch → keyword tagging → semantic scoring → Supabase upsert → threshold filter → LLM rating (Groq) → HTML report → email. Code, identifiers, comments, docstrings and console output are all in French; keep that convention.

## Commands

```bash
pip install -r requirements.txt          # a local venv/ exists at repo root
python src/main.py                        # full pipeline run (entry point)
python src/generer_rapport.py 2026-09-01  # rebuild an HTML report from the DB for dateparution >= date (default: last 7 days)
python src/recalculer_rapporte.py         # recompute the `rapporte` column for the whole table
python test_connexion_db.py               # sanity check of the Supabase connection (not a test suite)
```

There is no test suite, linter or build step. Scripts must be launched as `python src/<file>.py` from the repo root: modules use flat imports (`from db import ...`), which only resolve because `src/` ends up on `sys.path`. Generated reports (`rapport_boamp_<date>.html`) are written to the current directory and are gitignored.

Environment (loaded from `.env` via python-dotenv): `SUPABASE_DB_URL` (required), `GROQ_API_KEY` (optional: LLM analysis is skipped if absent), `SMTP_USER`/`SMTP_PASSWORD`/`MAIL_DESTINATAIRE` (optional: email is skipped if any is missing), `SMTP_HOST`/`SMTP_PORT` (optional).

CI: `.github/workflows/pipeline.yml` runs `python src/main.py` on Python 3.11, currently `workflow_dispatch` only (the cron and the SMTP/Groq secrets are commented out), and caches `~/.cache/huggingface` for the embedding model.

## Architecture

**Incremental cursor.** `main.py` uses `MAX(dateparution)` from the `annonces_boamp` table as `depuis` (falls back to today − 7 days on an empty table). Ingestion fetches `dateparution >= depuis`, so the last day is always re-fetched; that is safe because writes are `INSERT … ON CONFLICT (idweb) DO UPDATE`. The same `depuis` is passed to the report so it reflects exactly the batch processed by that run.

**Two selection paths that must stay consistent.** `restitution.py` holds the score-threshold rule (the required score decreases as `total_poles` increases: ≥3 → >0.2, 2 → >0.3, 1 → >0.4, 0 → >0.5) and exposes it twice:
- on `(annonce, score)` tuples for the current run (`est_retenue`, `restituer`), sorted by (total_poles, score). These decide what gets sent to the LLM and set the `rapporte` flag before the upsert.
- on flat DB rows (`filtrer_trier_lignes`), sorted by (LLM note, total_poles, score), with rows that have no note placed last. These are used by the report and by `recalculer_rapporte.py`.

Both go through `_est_retenue`. When you change thresholds, the clusters in `mots_cles.py`, or the manifesto, existing rows are **not** re-tagged or re-scored (`total_poles` and `score_similarite` are frozen at ingestion). Run `recalculer_rapporte.py` afterwards; it only recomputes `rapporte` from the stored values.

**Tag clusters drive DB columns.** `tagging.CLUSTERS` (column name → keyword list) defines the `match_*` columns, and `db.COLONNES_TAGS` is derived from it. Adding a cluster therefore requires adding the column in Supabase and an entry in `rapport.COULEURS_TAGS` (badge label and color). Keywords in `mots_cles.py` must be lowercase and accent-free, because matching is a plain substring test on text normalized by `utils.normaliser` over `objet`, `nomacheteur` and `descripteur_libelle`.

**Two profile texts** (`profil/`, loaded by `profil.py`):
- `CHEMIN_MANIFESTE` is the short text used for embeddings. It is currently `manifeste_reciproque_2.txt`. The model (`paraphrase-multilingual-mpnet-base-v2`) truncates around 128 tokens, so keep it short and descriptive.
- `manifeste_reciproque_llm.txt` is the long context for the Groq prompt in `analyse.py`. The model is `openai/gpt-oss-120b`, the output is JSON `{"pertinence", "note" 0–5}`, and failures for a single tender are swallowed (that tender simply has no analysis).

Only the `objet` field is embedded for scoring.

**DB columns not owned by the code.** `vue` and `note_humaine` exist in `annonces_boamp` for manual review; no script writes to them. `date_ingestion` is refreshed on every upsert. Analyses are written separately into `analyse_pertinence` and `analyse_note` (`db.enregistrer_analyses`).

**Ingestion.** `ingestion.py` queries the OpenDataSoft BOAMP API with an ODSQL `where` clause: exact match on `MOTS_CLES_DESCRIPTEURS_METIER` (a controlled BOAMP vocabulary) plus `datelimitereponse >= now()`. It is paginated and capped by `MAX_ANNONCES`.

## Leftovers

`requirements-analyse.txt` (pandas/seaborn/matplotlib) belonged to an exploratory analysis script that is no longer in the repo; it is not needed by the pipeline.
