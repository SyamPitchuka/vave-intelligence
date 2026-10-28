# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## What this is

VAVE Intelligence: a React/TypeScript SPA (`frontend/`) plus a FastAPI service (`backend/`) on PostgreSQL 16 with pgvector and pg_trgm. It handles Value Analysis / Value Engineering idea management, duplicate detection, savings analytics, and a document-grounded knowledge copilot. `README.md` has full setup (DB roles, extensions, dev accounts); `docs/` has architecture, API, data dictionary, security and limitations notes.

## Commands

The commands below use POSIX venv paths (`.venv/bin/...`). On the Windows dev laptop, application control blocks the `.venv\Scripts\*.exe` launchers ("Access is denied"). Always run tools as modules there: `.\.venv\Scripts\python.exe -m alembic|uvicorn|pytest|ruff ...`. The dev database is hosted on Neon. It needs outbound TCP 5432, which the office network blocks, and the hotspot can drop connections mid-request.

Backend (run from `backend/`):

```bash
python3.12 -m venv .venv && .venv/bin/pip install -r requirements.txt -r requirements-dev.txt
.venv/bin/python -c "from sentence_transformers import SentenceTransformer; SentenceTransformer('sentence-transformers/all-MiniLM-L6-v2')"  # once
.venv/bin/alembic upgrade head
HF_HUB_OFFLINE=1 .venv/bin/uvicorn app.main:app --host 127.0.0.1 --port 8000
.venv/bin/ruff check app tests
.venv/bin/pytest -q                                   # default suite (unit + integration)
.venv/bin/pytest tests/unit/test_domain_rules.py::test_name -q   # single test
.venv/bin/pytest tests/unit -q                        # unit tests only
```

Frontend (run from `frontend/`):

```bash
npm install
npm run dev            # Vite on :5173, proxies /api and /health to :8000
npm run typecheck      # tsc --noEmit
npm test               # vitest run
npx vitest run src/test/app.test.tsx -t "name"   # single test
npm run build          # tsc + vite build
```

Other:

- `sh scripts/start-local.sh` sets up `.env`, the venv, migrations, and starts both servers.
- `backend/.venv/bin/python scripts/evaluate.py` runs the labelled duplicate/copilot evaluation against the dev DB with the **active** embedding model (`--deterministic` for the hashed baseline). It stores evaluation runs. Precision, recall, and F1 come from `classify_pair`, called without a cosine or a query component, so they don't change with the embedding model; only the retrieval metrics can. For the v2 hard set (end to end, threshold sweeps, family split), use `scripts/evaluate_hard_set.py`; see its docstring.
- Seeding (every API start and `evaluate.py`) rewrites `data/synthetic/vave_synthetic_ideas.xlsx` with new timestamps. Don't commit that file unless the synthetic data actually changed.
- `docker compose up --build` (UI on 8080, API on 8000; `--profile offline` adds Ollama). Not verified in the original environment.

## Testing notes

- `backend/tests/conftest.py` sets env vars **before** app imports: `APP_ENV=test`, `AI_MODE=fallback`, deterministic embeddings, empty OpenAI key, and `DATABASE_URL` pointing at `vave_intelligence_test` (override with `TEST_DATABASE_URL`). It creates that DB if missing, runs `alembic upgrade head` and seeds the synthetic data once per session. Tests never touch the dev database.
- Use the `client` fixture plus `login()`/`auth()` helpers from conftest for API tests.
- Pytest markers `integration` and `external` are declared in `pyproject.toml` but no test applies them yet, so filtering with `-m` has no effect. Select tests by path instead. Anything that needs a live OpenAI key or Ollama model must be marked `external` and kept out of the default suite.
- Integration tests assert specific seeded values (e.g. VAVE-SYN-001 saving of 1,170,000 INR, VAVE-SYN-018 workbook mismatch), so changes to `backend/app/domain/synthetic.py`, the seed, or the savings rule can break them.

## Architecture

Backend layering:

- `app/main.py`: app factory (`create_app`). Lifespan seeds demo content when `SEED_DEMO_DATA=true`. Exception handlers map domain errors to HTTP: `LookupError`→404, `ValueError`→400, `ProviderUnavailable`/`OfflineModeBlocked`→409. Services raise these rather than `HTTPException`.
- `app/api/v1/router.py`: every route lives in this one file. Handlers are meant to stay thin and call services. Role checks go through `require(...)` in `app/api/deps.py` (roles: system administrator, VAVE engineer, department reviewer, department head, read-only management). Rate limiting is also in `deps.py`.
- `app/services/`: the domain logic. Key packages: `ideas`, `imports` (read → map → validate → staging preview → commit/rollback with merge strategies), `duplicate_detection`, `embeddings`, `copilot`, `llm_providers`, `analytics_service`, `evaluation_service`, `audit`, `sources/corporate` (optional read-only external DB), `local_folder` (file loading restricted to `data/local`).
- `app/models/entities.py`: all SQLAlchemy models. Schema changes need an Alembic migration in `backend/alembic/versions/`. `repositories/`, `schemas/` and `scripts/` are empty placeholders.
- `app/core/config.py`: settings from `.env` via a cached `get_settings()` (tests call `get_settings.cache_clear()` and `reset_engine()`). Production startup refuses the dev secret or demo password on purpose.

AI settings (`services/settings_store.py`): `.env` (`AI_MODE`, `EMBEDDING_PROVIDER`, `EMBEDDING_MODEL`) only provides defaults when the `ai` row in `application_settings` is first created. After that, **the stored row wins over `.env`**. Change settings with `PUT /api/v1/ai/settings` as admin, which is audited, then `POST /api/v1/ai/reindex`. `effective_ai` and `_default_embedding` enforce the same rules: fallback always uses deterministic embeddings, and non-online modes never use OpenAI.

AI provider modes:

- `fallback`: exact + RapidFuzz + deterministic hashed embeddings (`deterministic-hash-v1`); no network. Ignores the configured embedding provider.
- `offline` (current default): local `sentence-transformers/all-MiniLM-L6-v2` embeddings and Ollama on an allow-listed host only (`OLLAMA_ALLOW_HOSTS`) for chat; never downloads Ollama models; must never fall back to OpenAI. With Ollama down and `LLM_REQUIRED=false`, analysis uses the heuristic comparison and returns an "Ollama is not reachable" warning.
- `online`: OpenAI with a server-side key; the key is never returned to the browser, and the browser never calls a provider.
- `llm_providers/factory.py` builds providers. Offline and fallback refuse to construct an OpenAI client, and a test checks that offline mode doesn't call `api.openai.com`.

Duplicate pipeline (`services/duplicate_detection`): normalise → exact match → fuzzy → pgvector search → dedupe by idea id → select the first `retrieval_top_k` in (exact, fuzzy, cosine) order → heuristic classify (optional LLM rerank of the first 5) → re-sort the shown candidates by verdict (`VERDICT_PRIORITY`), then cosine, and renumber `rank` (`candidate_display_key`) → attach historical rejection fields from the DB **after** the model returns → store the run. Selection and LLM budget still follow fuzzy order; only the displayed order is by verdict. The results are only recommendations (`Potential Duplicate`, `Similar but Distinct`, `No Strong Match Found`, `Insufficient Evidence / Manual Review Required`). Human review decisions are stored separately and never overwrite historical idea or rejection fields.

Embeddings: vectors are fixed at **384 dimensions** in the schema. Idea vectors are in `embedding_records`; copilot passage vectors are in their own table, `document_chunk_embeddings`, made by the same provider. Both are filtered by embedding model name. Old models' vectors are kept. Changing the model requires an admin re-index. A different dimension requires a new migration (so `nomic-embed-text`, at 768, is rejected). The seed always writes deterministic vectors (`seed.py`), so a fresh database needs one re-index before MiniLM search works. `rank_historical` swallows embedding errors and returns no cosine scores, so a broken embedder fails silently. Check that the `cosine_similarity` values aren't null.

Cosine is used in four places:
- as the final tie-breaker in retrieval order, which decides which candidates are shown (after exact match and fuzzy score)
- as the main key within a verdict group in the displayed candidate order
- in the candidate filter `exact OR fuzzy >= 40 OR cosine >= cosine_retrieve_threshold` (`duplicate_detection/service.py`)
- in the optional semantic route to Potential Duplicate in `classify_pair`: same component AND cosine >= `semantic_duplicate_threshold` AND no detected different action

The semantic route is off unless `semantic_duplicate_threshold` is set. It defaults to `None` in `config.py` (and so in the tests), but the dev database's stored settings have it at **0.82** since 27 October 2026. It is set with `PUT /api/v1/ai/settings`, where an explicit `null` turns it off. While it is on, `scripts/evaluate_hard_set.py` headline metrics include the route; set it to `null` to reproduce route-off baselines. Its held-out evaluation is in `docs/evaluation-hard-set.md`. 0.82 was chosen on 15 component families before the determinism fix (held-out F1 0.828). Re-run on deterministic embeddings, the same rule selects 0.81 (held-out F1 0.831), while 0.82 scores 0.867 held out. The live value was left at 0.82 pending a decision. Seven more classifier rules each have their own setting in `config.py`, all on by default except `symmetric_lexical_fuzzy`, and can be turned off with `PUT /api/v1/ai/settings` (or `--disable` in `evaluate_hard_set.py` and `score_edge.py`): `component_fuzzy_match` (abbreviations expanded, parenthetical qualifiers dropped, RapidFuzz `ratio` >= 90; not `token_set_ratio`), `COMPONENT_DESCRIPTIVE_QUALIFIERS` ("low voltage", "LV") are dropped from component names, a dated assumption that must be reversed once high-voltage batteries are in the corpus; `component_subset_guard` (with fuzzy matching, a name that contains the other plus words other than "assembly"/"part" etc., or a positional qualifier such as front/rear/LH/RH on one side only, is a different component), `lexical_requires_component` (a lexical text match on a different component is Similar but Distinct, not Potential Duplicate; same matcher as the semantic route; not applied when either component is missing), `negation_detection` (action keywords within 5 tokens after a cue such as "do not" or "keep" are not counted), `direction_detection` ("from X to Y" / "replace X with Y" state pairs; opposite length changes or a flipped material substitution make the pair Similar but Distinct whatever the cosine; this also covers reversals), `scope_comparison` (a query adding kinds of change the candidate lacks is not a duplicate) and `symmetric_lexical_fuzzy` (off: the lexical duplicate rule would use `token_sort_ratio` instead of the containment-friendly `token_set_ratio`; it changed no labelled verdict and costs v2 recall with the semantic route off). Failures still open, by layer, are listed under Further work in `docs/evaluation-edge-cases-v2.md`; 14 labelled verdicts rest on cosine within 0.01 of 0.82. `idea_embedding_text` sorts the vehicle list so embeddings are deterministic. Before 28 October they depended on row order and drifted by up to 0.011 between runs, and every recorded evaluation figure was re-baselined after the fix. In `docs/evaluation-hard-set.md` the sweep and split were re-run and added as a re-baseline section; its earlier sections remain a record of the pre-fix runs. `classify_pair` arguments for a retrieved candidate come from `pair_inputs` in `duplicate_detection/service.py`, shared with both evaluation scripts. `docs/evaluation-edge-cases.md` (set v1) and `docs/evaluation-edge-cases-v2.md` (the adversarial set v2, generated by `scripts/edge_cases_v2.py`) have the edge-case results and the v2 regression checks; `scripts/score_edge.py` runs either set without leaving its ideas in the database (`--sweep-component LO HI` replays the component threshold). The evaluation records `cosine_retrieve_threshold` but never applies it. The threshold is 0.40 in `.env.example` and in the dev database's stored settings, and 0.22 in `config.py`, which the tests use. `docs/evaluation-results.md` has the measurements behind it. Update that file if you re-run the evaluation.

Savings (`services/savings.py`) is the authoritative calculation: saving per vehicle × the sum of annual volumes across *unique* vehicle families, in INR (projected, not realised). A missing saving stays `None` and is never treated as 0. The spreadsheet figure is never trusted. The frontend must not calculate official savings or rejection status.

Frontend: routes are in `src/App.tsx`, with one folder per feature in `src/features/`. Server state uses TanStack Query through `src/lib/api.ts`. Auth/session is in `src/lib/auth.tsx` and `session.ts`, UI role gating in `src/lib/permissions.ts`, and zod form schemas in `src/lib/schemas.ts`. `@` is aliased to `src/`. Styling uses Tailwind with Radix-based primitives in `src/components/ui`.

## Data conventions

- Synthetic data (`data/synthetic/`, `data/local/vave_synthetic_ideas.xlsx`) must stay labelled as synthetic. The stage letters in the sample guideline are a demo convention, not an OEM standard.
- `data/local/` is the only folder that "Load from local folder" can read. Allowed types: `.xlsx`, `.csv`, `.pdf`, `.docx`, `.txt`, `.md`.
- The copilot (Module 2, `docs/architecture.md`) answers from retrieved passages with a citation per claim, quotes the top passage as an explicitly labelled extractive answer when no language model is reachable, or abstains. `copilot_citation_threshold` defaults to `None` in `config.py`; the dev database's stored settings have it at **0.4873** since 28 October 2026, chosen on the calibration half of the Module 2 set (do not reuse 0.50, which was fitted to TF-IDF/LSA). No value separates answerable from must-refuse queries; the trade-off table is in `docs/evaluation-copilot.md`. The dev index holds only the 14 corpus documents (the seeded demo guideline was removed from it; a fresh database still seeds it). The Module 2 corpus is the PDFs in `data/`; load them with `HF_HUB_OFFLINE=1 backend/.venv/bin/python scripts/ingest_corpus.py --expect 14` (refuses to index with hashed vectors). Evaluate it with `scripts/evaluate_copilot.py data/vave_module2_retrieval_eval_set.json out.json` (read-only; scoring rules, split and threshold rule in its docstring); results, including the six evaluation-set anchors corrected on 28 October, are in `docs/evaluation-copilot.md`. Evaluation leaves out a metric when the labels can't support it, rather than reporting a misleading number.
