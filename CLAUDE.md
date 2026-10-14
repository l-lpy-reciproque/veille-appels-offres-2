# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Overview

Daily monitoring of French public tenders (BOAMP) for the agency reciproque. Two parts:
- a Python pipeline: fetch → keyword tagging → semantic scoring → Supabase upsert → threshold filter (`rapporte`) → LLM rating (Groq) → deletion of long-expired tenders;
- a static web page (`web/index.html`, GitHub Pages) that reads selected tenders straight from Supabase and lets logged-in users tick them as seen (`vue`) and rate them (`note_humaine`).

There is no report file and no email anymore. Code, identifiers, comments, docstrings, console output and UI text are all in French; keep that convention.

## Commands

```bash
pip install -r requirements.txt          # a local venv/ exists at repo root
python src/main.py                        # full pipeline run (entry point)
python src/recalculer_scores.py similarite        # recompute score_similarite for every row with the current manifesto
python src/recalculer_rapporte.py         # recompute the `rapporte` column for the whole table
python src/recalculer_scores.py llm [--reinitialiser]  # LLM-rate retained rows lacking a note (or wipe all notes and redo)
python src/analyse_exploratoire.py        # ad hoc plots over the whole history (needs requirements-analyse.txt)
python test_connexion_db.py               # sanity check of the Supabase connection (not a test suite)
python3 -m http.server 8000 --directory web       # serve the page locally
```

There is no test suite, linter or build step. Scripts must be launched as `python src/<file>.py` from the repo root: modules use flat imports (`from db import ...`), which only resolve because `src/` ends up on `sys.path`. For the page, `node --check` on the extracted `<script>` is the only cheap syntax check.

Environment (loaded from `.env` via python-dotenv, GitHub secrets in CI): `SUPABASE_DB_URL` (required, direct Postgres connection), `GROQ_API_KEY` (optional: LLM analysis is skipped if absent).

CI:
- `.github/workflows/pipeline.yml` runs `python src/main.py` daily at 06:00 UTC (plus `workflow_dispatch`) on Python 3.11 and caches `~/.cache/huggingface`.
- `.github/workflows/pages.yml` deploys `web/` to GitHub Pages on pushes to `main` that touch it. Pages caches for up to 10 minutes, so a just-pushed change may need a hard refresh.

## Architecture

**Incremental cursor.** `main.py` uses `MAX(dateparution)` from `annonces_boamp` as `depuis` (falls back to today − 7 days on an empty table). Ingestion fetches `dateparution >= depuis`, so the last day is always re-fetched; that is safe because writes are `INSERT … ON CONFLICT (idweb) DO UPDATE` over `db.TOUTES_COLONNES`, which excludes the team's columns. Never add `vue`, `note_humaine` or `annotation_*` to the upsert, or every run would wipe the team's work.

**Selection rule.** `restitution._est_retenue` holds the score threshold (the required score decreases as `total_poles` increases: ≥3 → >0.2, 2 → >0.3, 1 → >0.4, 0 → >0.5). It is applied:
- on `(annonce, score)` tuples for the current run (`est_retenue`, `restituer`). This sets `rapporte` before the upsert and decides what goes to the LLM;
- on flat DB rows (`filtrer_trier_lignes`, sorted by LLM note, total_poles, score, with unrated rows last). This is used by `recalculer_rapporte.py`, and by `recalculer_scores.py llm`, which rates the most promising rows first in case the Groq quota runs out.

The page does **not** reimplement the threshold: it shows `rapporte = true OR note_humaine IS NOT NULL`. Its sort is deliberately different: `dateparution` descending first (newest day on top), then the same LLM note / total_poles / score order.

**Stored values are frozen.** The pipeline never re-tags or re-scores existing rows. After a manifesto change, run `recalculer_scores.py similarite`. After threshold or score changes, run `recalculer_rapporte.py` (it only recomputes `rapporte` from stored values), then `recalculer_scores.py llm` to rate newly retained rows. Nothing re-tags existing rows after a keyword/cluster change. `recalculer_scores.py` does not touch `rapporte`.

**Tag clusters drive DB columns and the page.** `tagging.CLUSTERS` (column name → keyword list) defines the `match_*` columns (integer), and `db.COLONNES_TAGS` is derived from it. Adding a cluster requires:
- adding the column in Supabase;
- adding an entry to `COULEURS_TAGS` in `web/index.html` (badge label and color). The page selects these columns by name, so a missing entry means no badge, and a stale entry makes the query fail.

Keywords in `mots_cles.py` must be lowercase and accent-free, because matching is a plain substring test on text normalized by `utils.normaliser` over `objet`, `nomacheteur` and `descripteur_libelle`.

**Two profile texts** (`profil/`, loaded by `profil.py`):
- `CHEMIN_MANIFESTE` (`manifeste_reciproque_2.txt`) is the short text used for embeddings. The model (`paraphrase-multilingual-mpnet-base-v2`) truncates around 128 tokens, so keep it short and descriptive. Only the `objet` field of a tender is embedded.
- `manifeste_reciproque_llm.txt` is the long context for the Groq prompt in `analyse.py`. The model is `openai/gpt-oss-120b`, the output is JSON `{"pertinence", "note" 0–5}`, and failures for a single tender are swallowed (that tender simply has no analysis).

**Cleanup.** `db.supprimer_annonces_expirees` runs at the end of every pipeline run and deletes rows whose `datelimitereponse` (ISO text, cast to `timestamptz`) is more than one month past, **except rows with a `note_humaine`**. Those are kept to compare human rating, LLM rating and score. Deleted rows never come back, because ingestion only fetches tenders that are still open.

**Ingestion.** `ingestion.py` queries the OpenDataSoft BOAMP API with an ODSQL `where` clause: exact match on `MOTS_CLES_DESCRIPTEURS_METIER` (a controlled BOAMP vocabulary) plus `datelimitereponse >= now()`. It is paginated and capped by `MAX_ANNONCES`.

## Web page and Supabase security

`web/index.html` is a single file with no build step. It loads `@supabase/supabase-js` (pinned) from jsdelivr and uses email/password auth. It contains the project URL and the **publishable** key, which is public by design. Never put a secret or `service_role` key there.

Access is enforced in Supabase, not in the page. The full schema, policies, grants and trigger are in `sql/schema_supabase.sql`. It is re-runnable, but it is applied by hand in the Supabase SQL editor: keep it in sync with any schema change. It sets up:
- RLS is on, with policies `lecture` (SELECT) and `maj` (UPDATE) for `authenticated` only. `anon` has no grants.
- `authenticated` has column-level UPDATE on `vue` and `note_humaine` only.
- Constraint: `note_humaine` is NULL or between 0 and 5.
- Trigger `tracer_annotation` (BEFORE UPDATE) fills `annotation_par` (JWT email) and `annotation_le` only when `vue` or `note_humaine` changes, so pipeline upserts don't touch them.
- Public sign-ups are disabled; accounts are created in the Supabase dashboard.

Any new column the page must write needs its own column grant. The pipeline connects as the database owner through `SUPABASE_DB_URL`, so these rules don't apply to it.

Page conventions: build DOM with `textContent` (tender text comes from BOAMP and is untrusted) and only link `http(s)` URLs. "Today" means `dateparution` equal to the local date, not `date_ingestion`, which is refreshed on every re-fetch.
