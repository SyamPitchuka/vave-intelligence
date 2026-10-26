# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## What this is

VAVE Intelligence: a React/TypeScript SPA (`frontend/`) plus a FastAPI service (`backend/`) on PostgreSQL 16 with pgvector and pg_trgm. It handles Value Analysis / Value Engineering idea management, duplicate detection, savings analytics, and a document-grounded knowledge copilot. `README.md` has full setup (DB roles, extensions, dev accounts); `docs/` has architecture, API, data dictionary, security and limitations notes.

## Commands

The README uses POSIX venv paths (`.venv/bin/...`). On this Windows machine the venv executables are under `.venv/Scripts/`.

Backend (run from `backend/`):

```bash
python3.12 -m venv .venv && .venv/bin/pip install -r requirements.txt -r requirements-dev.txt
.venv/bin/alembic upgrade head
.venv/bin/uvicorn app.main:app --host 127.0.0.1 --port 8000
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
- `backend/.venv/bin/python scripts/evaluate.py` runs labelled duplicate/copilot evaluation against the dev DB.
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

AI provider modes (`AI_MODE`, also changeable at runtime by an admin through `settings_store`):

- `fallback`: exact + RapidFuzz + deterministic hashed embeddings (`deterministic-hash-v1`); no network.
- `offline`: Ollama on an allow-listed host only (`OLLAMA_ALLOW_HOSTS`); never downloads models; must never fall back to OpenAI.
- `online`: OpenAI with a server-side key; the key is never returned to the browser, and the browser never calls a provider.
- `llm_providers/factory.py` builds providers. Offline and fallback refuse to construct an OpenAI client, and a test checks that offline mode doesn't call `api.openai.com`.

Duplicate pipeline (`services/duplicate_detection`): normalise → exact match → fuzzy → pgvector search → dedupe by idea id → heuristic classify (optional LLM rerank) → attach historical rejection fields from the DB **after** the model returns → store the run. The results are only recommendations (`Potential Duplicate`, `Similar but Distinct`, `No Strong Match Found`, `Insufficient Evidence / Manual Review Required`). Human review decisions are stored separately and never overwrite historical idea or rejection fields.

Embeddings: vectors are fixed at **384 dimensions** in the schema. Idea and document-chunk vectors share one table, told apart by `entity_type` and filtered by embedding model name. Changing the model requires an admin re-index. A different dimension requires a new migration (so `nomic-embed-text`, at 768, is rejected).

Savings (`services/savings.py`) is the authoritative calculation: saving per vehicle × the sum of annual volumes across *unique* vehicle families, in INR (projected, not realised). A missing saving stays `None` and is never treated as 0. The spreadsheet figure is never trusted. The frontend must not calculate official savings or rejection status.

Frontend: routes are in `src/App.tsx`, with one folder per feature in `src/features/`. Server state uses TanStack Query through `src/lib/api.ts`. Auth/session is in `src/lib/auth.tsx` and `session.ts`, UI role gating in `src/lib/permissions.ts`, and zod form schemas in `src/lib/schemas.ts`. `@` is aliased to `src/`. Styling uses Tailwind with Radix-based primitives in `src/components/ui`.

## Data conventions

- Synthetic data (`data/synthetic/`, `data/local/vave_synthetic_ideas.xlsx`) must stay labelled as synthetic. The stage letters in the sample guideline are a demo convention, not an OEM standard.
- `data/local/` is the only folder that "Load from local folder" can read. Allowed types: `.xlsx`, `.csv`, `.pdf`, `.docx`, `.txt`, `.md`.
- The copilot quotes retrieved excerpts or abstains. Evaluation leaves out a metric when the labels can't support it, rather than reporting a misleading number.
