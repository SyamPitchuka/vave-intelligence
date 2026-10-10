# VAVE Intelligence

AI-assisted idea management, duplicate detection, and an engineering knowledge copilot for a Value Analysis / Value Engineering workflow.

Engineering Value Intelligence | Semantic Search | Knowledge Discovery | Savings Analytics

The historical record stays under human control. An analysis can recommend `Potential Duplicate`, `Similar but Distinct`, `No Strong Match Found`, or `Insufficient Evidence / Manual Review Required`. It does not reject an idea and it does not rewrite historical rejection fields.

Synthetic rows are labelled synthetic. Stage letters in the sample guideline are a demonstration convention, not an OEM standard.

## What is included

- React, TypeScript, and Vite interface with the executive dashboard, Idea Explorer, submission, duplicate evidence, reviews, import, savings, rejections, copilot, evaluation, AI settings, audit, and administration.
- FastAPI service under `/api/v1`, OpenAPI at `/docs`.
- PostgreSQL with pgvector, Alembic migrations, and Excel import with preview, validation, merge strategies, and rollback.
- Provider modes: OpenAI (online, server-side key only), Ollama (offline), and a deterministic matcher that needs no model download.
- Savings calculated in the backend: saving per vehicle times the sum of unique vehicle-family annual volumes, in INR, projected rather than realised.
- Labelled evaluation that omits a metric when the labels are insufficient.
- Role checks on the API for system administrator, VAVE engineer, department reviewer, department head, and read-only management.

Further notes are in [docs/architecture.md](docs/architecture.md), [docs/api.md](docs/api.md), [docs/data-dictionary.md](docs/data-dictionary.md), [docs/security.md](docs/security.md), and [docs/limitations.md](docs/limitations.md).

## Requirements

- Python 3.12
- Node.js 22
- PostgreSQL 16 with the `vector` and `pg_trgm` extensions

Docker Compose is provided for a later machine that has a Docker daemon. It was not started in the environment used to verify this revision.

## Local setup

```bash
cp .env.example .env
```

Create the database role and databases if they do not exist. The password below matches the development placeholder in `.env.example`. Replace it before any shared deployment.

```bash
sudo -u postgres psql -c "CREATE USER vave WITH SUPERUSER PASSWORD 'vave_dev_password';" || true
sudo -u postgres psql -c "CREATE DATABASE vave_intelligence OWNER vave;" || true
sudo -u postgres psql -c "CREATE DATABASE vave_intelligence_test OWNER vave;" || true
sudo -u postgres psql -d vave_intelligence -c "CREATE EXTENSION IF NOT EXISTS vector; CREATE EXTENSION IF NOT EXISTS pg_trgm;"
sudo -u postgres psql -d vave_intelligence_test -c "CREATE EXTENSION IF NOT EXISTS vector; CREATE EXTENSION IF NOT EXISTS pg_trgm;"
```

On a Debian host where policy blocks the package service start:

```bash
sudo pg_ctlcluster 16 main start
pg_isready -h 127.0.0.1 -p 5432
```

### API

```bash
cd backend
python3.12 -m venv .venv
.venv/bin/pip install -r requirements.txt -r requirements-dev.txt
.venv/bin/alembic upgrade head
.venv/bin/uvicorn app.main:app --host 127.0.0.1 --port 8000
```

Startup with `SEED_DEMO_DATA=true` loads reference data, five development users, the synthetic workbook, embeddings, the guideline, and the labelled cases.

```bash
curl -s http://127.0.0.1:8000/health
```

A healthy response has `"status": "ok"`, `"database": "ok"`, and `"pgvector": "ok"`.

### Interface

```bash
cd frontend
npm install
npm run dev
```

Open `http://127.0.0.1:5173`. The Vite server proxies `/api` and `/health` to port 8000.

### Development accounts

These exist only when `APP_ENV=development` and demo seeding is on. Change them before any shared use.

| Email | Password | Role |
| --- | --- | --- |
| admin@vave.local | ChangeMeAdmin!23 | System administrator |
| engineer@vave.local | VaveDemo!234 | VAVE engineer |
| reviewer@vave.local | VaveDemo!234 | Department reviewer |
| head@vave.local | VaveDemo!234 | Department head |
| viewer@vave.local | VaveDemo!234 | Read-only management |

## Checks that were run

Commands were run from this repository on 10 October 2026.

```bash
cd backend && .venv/bin/ruff check app tests
cd backend && .venv/bin/pytest -q --tb=line
cd frontend && npx tsc --noEmit
cd frontend && npx vitest run
cd frontend && npm run build
cd /workspace && backend/.venv/bin/python scripts/evaluate.py
```

Results:

- Ruff: all checks passed.
- Backend pytest: 20 passed (11 unit tests and 9 integration tests against `vave_intelligence_test`) in about 5 seconds. One Starlette deprecation warning was printed for the TestClient import.
- Frontend typecheck: passed.
- Frontend vitest: 8 passed.
- Frontend production build: passed (`vite build`). The bundle is larger than 500 kB before gzip because charts and the table library are in the main chunk.
- Integration coverage includes health, the read-only role receiving 403 on idea creation, dashboard totals, the VAVE-SYN-001 saving of 1,170,000 INR, the VAVE-SYN-018 workbook mismatch, exception-sheet rejection, duplicate analysis, a human review that leaves the historical row unchanged, a copilot citation containing “saving per vehicle”, evaluation metrics, and an offline-mode run that does not call `api.openai.com`.
- `scripts/evaluate.py` on the development database, deterministic provider, synthetic labels only: duplicate set support 12, precision 1.0, recall 0.8, F1 about 0.889, false-positive rate 0, top-k success 1.0 on 5 retrieval targets. Copilot keyword-in-top-chunk hit rate 1.0 on 3 cases. These figures are not a production accuracy claim.

Not run:

- Docker Compose. `docker` was not installed, so the images were not built and the health checks inside Compose were not observed.
- Playwright. Browser end-to-end automation was not installed. The API integration test is the executed workflow check.
- A live OpenAI call and a live Ollama model. Both are guarded and covered by unit or integration tests that must not require those services. External tests are marked `external` and are not part of the default suite.

## AI modes

Set `AI_MODE` in `.env`, or change it in AI settings as a system administrator. A restart is not required for the stored setting.

- `fallback` uses exact match, fuzzy match, and hashed embeddings. No network inference.
- `offline` uses Ollama at `OLLAMA_BASE_URL`. The host must be on `OLLAMA_ALLOW_HOSTS`. The application does not run `ollama pull`. If the model is missing, the settings test explains that. With `LLM_REQUIRED=false`, analysis continues deterministically and shows a warning. It does not fall back to OpenAI.
- `online` calls OpenAI with `OPENAI_API_KEY` from the server environment. The key is never returned to the browser. Do not enable this for confidential ideas unless that provider is approved.

Embedding vectors are 384 dimensions. Re-index after changing the embedding model. `nomic-embed-text` is 768 dimensions and is rejected by this schema.

## Tests and evaluation

```bash
cd backend && .venv/bin/pytest -q
cd frontend && npm test
backend/.venv/bin/python scripts/evaluate.py
```

Pytest uses `vave_intelligence_test`, not the development database. The suite applies migrations and seeds synthetic data into that database.

## Docker Compose

On a machine with Docker:

```bash
cp .env.example .env
docker compose up --build
```

The interface is published on port 8080 and the API on port 8000. PostgreSQL data is in the `pgdata` volume. The backend entrypoint runs `alembic upgrade head` before uvicorn. An optional local model server is not started unless requested:

```bash
docker compose --profile offline up --build
```

You still install the Ollama model yourself.

## Troubleshooting

- Health reports `database: error`: PostgreSQL is not accepting connections, or `DATABASE_URL` is wrong.
- Health reports `pgvector: missing`: run `CREATE EXTENSION vector` or use the `pgvector/pgvector:pg16` image.
- Import commit returns 400: the preview still has error rows. Download the error report, or explicitly allow valid rows only.
- Offline analysis says the local model is unavailable: start Ollama and install the configured model, or switch to deterministic fallback.
- Online test says the API key is missing: set `OPENAI_API_KEY` on the server. An empty key is the safe default.
- Production startup refuses the development secret or the demo password. That check is intentional.

## Project layout

```text
frontend/     React application
backend/      FastAPI application, migrations, tests
data/synthetic/  Generated synthetic workbook
docs/         Architecture, API, data dictionary, security, limitations
scripts/      Labelled evaluation command
docker-compose.yml
```
