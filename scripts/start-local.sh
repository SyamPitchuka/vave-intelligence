#!/bin/sh
# Start the API and the interface on this computer. 127.0.0.1 then means your machine.
set -eu
ROOT=$(CDPATH= cd -- "$(dirname "$0")/.." && pwd)
cd "$ROOT"
if [ ! -f .env ]; then
  cp .env.example .env
fi
cd "$ROOT/backend"
if [ ! -d .venv ]; then
  python3.12 -m venv .venv
fi
.venv/bin/pip install -r requirements.txt -r requirements-dev.txt
.venv/bin/alembic upgrade head
.venv/bin/uvicorn app.main:app --host 127.0.0.1 --port 8000 &
API_PID=$!
trap 'kill "$API_PID" 2>/dev/null || true' EXIT INT TERM
cd "$ROOT/frontend"
if [ ! -d node_modules ]; then
  npm install
fi
npm run dev -- --host 127.0.0.1 --port 5173
