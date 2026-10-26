# VAVE Intelligence

AI-assisted idea management, duplicate detection, and an engineering knowledge copilot for a Value Analysis / Value Engineering workflow.

Engineering Value Intelligence | Semantic Search | Knowledge Discovery | Savings Analytics

## Problem statement

A VAVE programme collects cost-reduction ideas from engineers across departments, often over many years and in spreadsheets. As the history grows, three problems show up:

- **Repeated ideas.** A new submission can repeat an idea that was already implemented, is in progress, or was rejected, sometimes with different wording. Checking by hand against hundreds of historical rows is slow, so duplicates reach reviewers and rejected ideas come back without anyone seeing why they were rejected the first time.
- **Unreliable savings figures.** Annual savings are typed into workbooks. When an idea applies to several vehicle families, totals can be double-counted or simply disagree with saving per vehicle × volume. Nobody can tell which figure to trust.
- **Knowledge that is hard to find.** Guidelines and the reasoning behind past decisions sit in documents and rejection fields that are hard to search when an engineer is writing a new idea.

VAVE Intelligence addresses these by:

- Importing the idea history with validation and rollback.
- Checking each new idea against that history with exact, fuzzy, and vector search, and showing the evidence.
- Calculating savings in one place in the backend.
- Answering questions from approved documents with quoted excerpts, or abstaining.

The historical record stays under human control. An analysis can recommend `Potential Duplicate`, `Similar but Distinct`, `No Strong Match Found`, or `Insufficient Evidence / Manual Review Required`. It does not reject an idea and it does not rewrite historical rejection fields.

Synthetic rows are labelled synthetic. Stage letters in the sample guideline are a demonstration convention, not an OEM standard.

## What is included

- React, TypeScript, and Vite interface with the executive dashboard, Idea Explorer, submission, duplicate evidence, reviews, import, savings, rejections, copilot, evaluation, AI settings, audit, and administration.
- FastAPI service under `/api/v1`, OpenAPI at `/docs`.
- PostgreSQL with pgvector, Alembic migrations, and Excel import with preview, validation, merge strategies, and rollback.
- Provider modes: OpenAI (online, server-side key only), Ollama (offline), and a deterministic matcher that needs no model download.
- Local neural embeddings with sentence-transformers `all-MiniLM-L6-v2` (384 dimensions), the default in `.env.example`. The deterministic hashed embedding remains available.
- Savings calculated in the backend: saving per vehicle times the sum of unique vehicle-family annual volumes, in INR, projected rather than realised.
- Labelled evaluation that omits a metric when the labels are insufficient.
- Role checks on the API for system administrator, VAVE engineer, department reviewer, department head, and read-only management.

Further notes are in [docs/architecture.md](docs/architecture.md), [docs/api.md](docs/api.md), [docs/data-dictionary.md](docs/data-dictionary.md), [docs/security.md](docs/security.md), [docs/limitations.md](docs/limitations.md), and [docs/evaluation-results.md](docs/evaluation-results.md).

## Screenshots

No screenshots have been captured yet. Save them as PNG files in `docs/screenshots/` using the names below, then replace each "Not yet captured" with an image link such as `![Dashboard](docs/screenshots/dashboard.png)`. Take them from the synthetic dataset only, not from company records.

| View | File | What it should show | Image |
| --- | --- | --- | --- |
| Sign-in | `sign-in.png` | Sign-in page with the development-accounts notice | Not yet captured |
| Executive dashboard | `dashboard.png` | Idea totals, stage and department breakdown, projected savings | Not yet captured |
| Idea Explorer | `idea-explorer.png` | Searchable idea table with filters | Not yet captured |
| Duplicate evidence | `duplicate-evidence.png` | Ranked candidates with match evidence and historical rejection fields | Not yet captured |
| Import preview | `import-preview.png` | Workbook preview with row errors and merge strategy | Not yet captured |
| Savings | `savings.png` | Calculated totals and workbook mismatches | Not yet captured |
| Knowledge copilot | `copilot.png` | An answer with quoted, cited excerpts | Not yet captured |

## Requirements

- Python 3.12 (Python 3.14 also works; see [Windows setup notes](#windows-setup-notes))
- Node.js 22
- PostgreSQL 16 with the `vector` and `pg_trgm` extensions, either local or hosted

Docker Compose is provided for a later machine that has a Docker daemon. It was not started in the environment used to verify this revision.

## Local setup (Linux and macOS)

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
```

`requirements.txt` includes `sentence-transformers`, which pulls in PyTorch. The CPU build is a large download. Fetch the embedding model once, then start the API with `HF_HUB_OFFLINE=1` so it loads only the cached copy and never contacts Hugging Face:

```bash
.venv/bin/python -c "from sentence_transformers import SentenceTransformer; SentenceTransformer('sentence-transformers/all-MiniLM-L6-v2')"
HF_HUB_OFFLINE=1 .venv/bin/uvicorn app.main:app --host 127.0.0.1 --port 8000
```

Startup with `SEED_DEMO_DATA=true` loads reference data, five development users, the synthetic workbook, embeddings, the guideline, and the labelled cases. Seeding can be repeated without duplicating rows. It also rewrites `data/synthetic/vave_synthetic_ideas.xlsx`; if only that file changed, discard it with `git checkout -- data/synthetic/vave_synthetic_ideas.xlsx`.

The seed writes deterministic vectors only. After the first start, re-index once as `admin@vave.local`, either with **AI settings → Re-index embeddings** or through the API:

```bash
TOKEN=$(curl -s -X POST http://127.0.0.1:8000/api/v1/auth/login -H 'Content-Type: application/json' \
  -d '{"email":"admin@vave.local","password":"ChangeMeAdmin!23"}' | python3 -c "import sys, json; print(json.load(sys.stdin)['access_token'])")
curl -s -X POST http://127.0.0.1:8000/api/v1/ai/reindex -H "Authorization: Bearer $TOKEN"
```

A completed re-index reports `"model": "sentence-transformers/all-MiniLM-L6-v2"` with the idea and chunk counts. Until it runs, vector search has no MiniLM vectors, and the cosine scores are missing from duplicate analysis.

`.env` only sets the AI settings on the database's first start. After that, the settings stored in the database win, so change them in **AI settings** (or `PUT /api/v1/ai/settings`), then re-index.

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

Open `http://127.0.0.1:5173`. The Vite server proxies `/api` and `/health` to port 8000, so the browser never makes a cross-origin call.

`sh scripts/start-local.sh` performs the API and interface steps in one command on Linux and macOS.

## Windows setup notes

These notes come from a Windows 11 laptop without administrator rights, where Docker and a local PostgreSQL install were not possible. Everything below runs as a normal user.

### 1. Node.js without an installer

Download the Node.js 22 **Windows Binary (.zip)** for x64 from <https://nodejs.org/en/download> and check its SHA-256 against the `SHASUMS256.txt` published next to it. Extract it under `%LOCALAPPDATA%\Programs`, then add that folder to your user `Path`:

```powershell
$nodeDir = "$env:LOCALAPPDATA\Programs\node-v22.x.y-win-x64"   # the folder you extracted
$userPath = [Environment]::GetEnvironmentVariable('Path', 'User')
[Environment]::SetEnvironmentVariable('Path', "$userPath;$nodeDir", 'User')
```

Open a new PowerShell window afterwards so `node` and `npm` are found.

### 2. Python

Use Python 3.12 if you can install it for your user only. The backend dependencies also install, and the unit tests pass, on Python 3.14. Check which versions you have with `py -0p`.

```powershell
cd backend
py -3.12 -m venv .venv          # or: py -3.14 -m venv .venv
.\.venv\Scripts\python.exe -m pip install -r requirements.txt -r requirements-dev.txt
```

### 3. A hosted PostgreSQL database

pgvector does not come with the standard Windows PostgreSQL installer. Without admin rights, a hosted database is the simplest option. [Neon](https://neon.tech) has a free tier that supports `vector` and `pg_trgm`. Supabase also works.

1. Create a Neon project with Postgres 16 or 17 in the region nearest you.
2. Copy the connection string from **Connect**.
3. In `.env`, set `DATABASE_URL`, changing the start from `postgresql://` to `postgresql+psycopg://`:

   ```
   DATABASE_URL=postgresql+psycopg://<user>:<password>@<host>.neon.tech/neondb?sslmode=require&channel_binding=require
   ```

You do not need to run `CREATE EXTENSION`. The first migration creates both extensions.

A hosted database lives on the provider's servers, not your laptop. Keep it to the synthetic data unless your organisation has approved that provider for real VAVE records.

### 4. Migrate and run

On some managed laptops, application-control policy blocks the `.exe` launchers that pip puts in `.venv\Scripts` (`alembic.exe`, `uvicorn.exe`) with "Access is denied". Run them as Python modules instead. That form works everywhere.

```powershell
# backend\ - once, and after pulling new migrations
.\.venv\Scripts\python.exe -m alembic upgrade head

# backend\ - once: download all-MiniLM-L6-v2 into %USERPROFILE%\.cache\huggingface
.\.venv\Scripts\python.exe -c "from sentence_transformers import SentenceTransformer; SentenceTransformer('sentence-transformers/all-MiniLM-L6-v2')"

# backend\ - window 1. HF_HUB_OFFLINE keeps it from contacting Hugging Face.
$env:HF_HUB_OFFLINE = '1'
.\.venv\Scripts\python.exe -m uvicorn app.main:app --host 127.0.0.1 --port 8000

# frontend\ - window 2
npm install
npm run dev
```

After the first start, re-index once as `admin@vave.local` with **AI settings → Re-index embeddings** (see [API](#api)). The API takes longer to start than with deterministic embeddings, because it loads PyTorch.

`scripts/start-local.sh` is a POSIX shell script and does not run in PowerShell.

### Windows troubleshooting

- **Migrations or the API hang when connecting to the database.** Corporate networks often block outgoing TCP port 5432. Test it with `Test-NetConnection <host>.neon.tech -Port 5432`. If `TcpTestSucceeded` is false, use another network, such as a phone hotspot without the VPN, or ask IT to allow port 5432 to the provider. Neon does not accept PostgreSQL connections on port 443.
- **`password authentication failed` after resetting the database password.** Update `DATABASE_URL` in `.env` and restart the API. `/docs` still loads while the database is unreachable, but sign-in returns HTTP 500 and the interface shows "The request could not be completed".
- **`Port 5173 is already in use` or `address already in use` on 8000.** A previous server is still running. Find it with `Get-NetTCPConnection -LocalPort 5173 -State Listen` and stop that process ID with `Stop-Process`.
- **`Invoke-RestMethod` reports "The underlying connection was closed" against the Vite server.** This is a Windows PowerShell 5.1 connection-reuse quirk, not an app error. Add `-DisableKeepAlive`.

## Development accounts

These exist only when `APP_ENV=development` and demo seeding is on. The passwords come from `ADMIN_PASSWORD` and `DEMO_USER_PASSWORD` in `.env`. Change them before any shared use.

| Email | Password | Role |
| --- | --- | --- |
| admin@vave.local | ChangeMeAdmin!23 | System administrator |
| engineer@vave.local | VaveDemo!234 | VAVE engineer |
| reviewer@vave.local | VaveDemo!234 | Department reviewer |
| head@vave.local | VaveDemo!234 | Department head |
| viewer@vave.local | VaveDemo!234 | Read-only management |

## AI modes

Set `AI_MODE` in `.env`, or change it in AI settings as a system administrator. A restart is not required for the stored setting.

- `fallback` uses exact match, fuzzy match, and hashed embeddings. No network inference. This mode always uses `deterministic-hash-v1`, whatever embedding provider is configured.
- `offline` is the default in `.env.example`. It uses local `all-MiniLM-L6-v2` embeddings and Ollama at `OLLAMA_BASE_URL` for the language-model comparison. The host must be on `OLLAMA_ALLOW_HOSTS`. The application does not run `ollama pull`. If the model is missing, the settings test explains that. With `LLM_REQUIRED=false`, analysis continues deterministically and shows a warning. It does not fall back to OpenAI.
- `online` calls OpenAI with `OPENAI_API_KEY` from the server environment. The key is never returned to the browser. Do not enable this for confidential ideas unless that provider is approved.

Embedding vectors are 384 dimensions. Re-index after changing the embedding model. `nomic-embed-text` is 768 dimensions and is rejected by this schema.

Cosine similarity affects two things in the live app:
- the order of candidates, where it breaks ties after exact match and fuzzy score
- the candidate filter: a historical idea is shown if it is an exact match, or has fuzzy ≥ 40, or has cosine ≥ `cosine_retrieve_threshold`

The duplicate category comes from the heuristic comparison and, when available, the language model. Cosine never decides it.

## Tests and evaluation

```bash
cd backend && .venv/bin/pytest -q
cd frontend && npm test
HF_HUB_OFFLINE=1 backend/.venv/bin/python scripts/evaluate.py   # active embedding model
backend/.venv/bin/python scripts/evaluate.py --deterministic     # deterministic-hash-v1 baseline
```

On Windows, use `.\.venv\Scripts\python.exe -m pytest -q`.

`scripts/evaluate.py` evaluates the embedding model active in AI settings, so that model must already be indexed. It stores a run in the database, as the Evaluation page does. Its precision, recall, and F1 come from the heuristic comparison, which does not use cosine, so they are the same for every embedding model. Only the retrieval figures can differ.

Pytest uses `vave_intelligence_test`, not the development database. The suite applies migrations and seeds synthetic data into that database. To create it, the test setup connects to a database named `postgres` on the same server. On a hosted provider, create `vave_intelligence_test` in the provider's console first, and point `TEST_DATABASE_URL` at it. On Neon the owner role can create databases, so the test setup creates `vave_intelligence_test` itself; set `TEST_DATABASE_URL` in the shell (conftest reads the environment, not `.env`). The unit tests need no database: `pytest tests/unit -q`.

## Checks that were run

### Linux, 10 October 2026

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
- Integration coverage includes:
  - health, and the read-only role receiving 403 on idea creation
  - dashboard totals, the VAVE-SYN-001 saving of 1,170,000 INR, and the VAVE-SYN-018 workbook mismatch
  - exception-sheet rejection and duplicate analysis
  - a human review that leaves the historical row unchanged
  - a copilot citation containing "saving per vehicle"
  - evaluation metrics, and an offline-mode run that does not call `api.openai.com`
- `scripts/evaluate.py` on the development database, deterministic provider, synthetic labels only:
  - duplicate set support 12, precision 1.0, recall 0.8, F1 about 0.889, false-positive rate 0
  - top-k success 1.0 on 5 retrieval targets
  - copilot keyword-in-top-chunk hit rate 1.0 on 3 cases

  These figures are not a production accuracy claim.

### Windows 11 with Neon, 26 October 2026

Python 3.14, portable Node.js 22.23.4, hosted Neon database, sentence-transformers 6.2.0 with PyTorch 2.14.1 (CPU).

- Backend unit tests (`pytest tests/unit`): 12 passed.
- Frontend typecheck: passed. Frontend vitest: 8 passed.
- `alembic upgrade head` against Neon: reached `e1d14600b48e (head)`.
- API `/health`: `status ok`, `database ok`, `pgvector ok`.
- Seeded dashboard: 20 ideas, VAVE-SYN-001 saving 1,170,000 INR.
- Sign-in through the Vite proxy worked for all five development accounts.
- After switching to `all-MiniLM-L6-v2`: re-index of 25 ideas and 3 document chunks; Ruff on `app tests` passed; backend unit tests: 13 passed.

`scripts/evaluate.py`, synthetic labels only (12 duplicate cases, 20 historical ideas):

| Embedding | Precision | Recall | F1 | FP rate | Top-k success | MRR | Copilot hit rate |
| --- | --- | --- | --- | --- | --- | --- | --- |
| deterministic-hash-v1 | 1.0 | 0.8 | 0.889 | 0 | 1.0 | 1.0 | 1.0 |
| all-MiniLM-L6-v2 | 1.0 | 0.8 | 0.889 | 0 | 1.0 | 1.0 | 1.0 |

The figures are identical by design (see [Tests and evaluation](#tests-and-evaluation)).

Cosine between each labelled query and its labelled candidate:

| Label (cases) | deterministic-hash-v1 | all-MiniLM-L6-v2 |
| --- | --- | --- |
| duplicate (5) | 0.595 – 0.695 | 0.814 – 0.892 |
| similar but distinct (4) | 0.337 – 0.448 | 0.693 – 0.772 |
| unrelated (3) | 0.000 – 0.399 | 0.273 – 0.428 |

Both models rank every labelled duplicate above every non-duplicate. The gap between the lowest duplicate and the highest similar-but-distinct pair is 0.147 for the deterministic model and 0.042 for MiniLM. MiniLM raises every score; on this set it does not separate the labels better.

The live candidate filter was checked at thresholds from 0.22 to 0.80 on the same 12 queries:
- **Fuzzy ≥ 40 does most of the work.** It admits 19.7 of 20 historical ideas per query on average, and all 5 labelled duplicates have fuzzy ≥ 86.
- **The threshold only matters for the 4 query–candidate pairs with fuzzy < 40.**
- **With MiniLM at 0.22, cosine alone admits all 4 of those pairs,** including the pair labelled unrelated (UNREL-CHIME → VAVE-SYN-001, cosine 0.273).
- **At 0.40 cosine admits none of them, and no duplicate is lost.** Nothing changes between 0.40 and 0.80.

`cosine_retrieve_threshold` is therefore 0.40 in `.env.example`; the code default is still 0.22. The full tables, both fixed defects, and the limits of this 12-case sample are in [docs/evaluation-results.md](docs/evaluation-results.md).

Later on 26 October 2026, on a second Windows 11 laptop (Python 3.14, Node.js 24) against the same Neon project:

- Backend pytest, full suite: 23 passed (13 unit, 10 integration against `vave_intelligence_test` on Neon), including `tests/integration/test_vector_search.py` for the submission-crowding fix.
- Frontend typecheck, vitest (8 passed), and `npm run build`: passed.
- `scripts/evaluate.py` with MiniLM after the fix: unchanged figures (see [docs/evaluation-results.md](docs/evaluation-results.md)).

### Not run anywhere

- Docker Compose. `docker` was not installed, so the images were not built and the health checks inside Compose were not observed.
- Playwright. Browser end-to-end automation was not installed. The API integration test is the executed workflow check.
- A live OpenAI call and a live Ollama model. Both are guarded and covered by unit or integration tests that must not require those services. External tests are marked `external` and are not part of the default suite.

## Docker Compose

On a machine with Docker:

```bash
cp .env.example .env
docker compose up --build
```

The interface is published on port 8080 and the API on port 8000. PostgreSQL data is in the `pgdata` volume. `docker-compose.yml` sets `AI_MODE=fallback` with deterministic embeddings, so the containers don't use MiniLM, although the backend image now includes PyTorch through `requirements.txt`. The backend entrypoint runs `alembic upgrade head` before uvicorn. An optional local model server is not started unless requested:

```bash
docker compose --profile offline up --build
```

You still install the Ollama model yourself.

## Troubleshooting

- Health reports `database: error`: PostgreSQL is not accepting connections, or `DATABASE_URL` is wrong.
- Health reports `pgvector: missing`: run `CREATE EXTENSION vector` or use the `pgvector/pgvector:pg16` image. The same value also appears whenever the database cannot be reached at all.
- Import commit returns 400: the preview still has error rows. Download the error report, or explicitly allow valid rows only.
- Offline analysis says the local model is unavailable: start Ollama and install the configured model, or switch to deterministic fallback.
- Online test says the API key is missing: set `OPENAI_API_KEY` on the server. An empty key is the safe default.
- Production startup refuses the development secret or the demo password. That check is intentional.

Windows-specific problems are under [Windows troubleshooting](#windows-troubleshooting).

## Project layout

```text
frontend/        React application
backend/         FastAPI application, migrations, tests
data/synthetic/  Generated synthetic workbook
data/local/      Files the app may load with "Load from local folder"
docs/            Architecture, API, data dictionary, security, limitations
local/           Notes for opening the project on your own machine
scripts/         Labelled evaluation command and the POSIX start script
docker-compose.yml
```
