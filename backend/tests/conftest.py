"""Point the test process at the disposable database before application imports."""

from __future__ import annotations

import os
import subprocess
import sys
from pathlib import Path

BACKEND_ROOT = Path(__file__).resolve().parents[1]
TEST_URL = os.environ.get(
    "TEST_DATABASE_URL",
    "postgresql+psycopg://vave:vave_dev_password@127.0.0.1:5432/vave_intelligence_test",
)

os.environ["APP_ENV"] = "test"
os.environ["SEED_DEMO_DATA"] = "false"
os.environ["DATABASE_URL"] = TEST_URL
os.environ["SECRET_KEY"] = "test-secret-key-with-sufficient-length"
os.environ["AI_MODE"] = "fallback"
os.environ["EMBEDDING_PROVIDER"] = "deterministic"
os.environ["EMBEDDING_MODEL"] = "deterministic-hash-v1"
os.environ["OPENAI_API_KEY"] = ""
os.environ["LLM_REQUIRED"] = "false"

import pytest  # noqa: E402  — environment must be set before pytest collects application imports


def _ensure_database() -> None:
    import psycopg

    admin = TEST_URL.replace("postgresql+psycopg://", "postgresql://").rsplit("/", 1)[0] + "/postgres"
    name = TEST_URL.rsplit("/", 1)[1].split("?")[0]
    with psycopg.connect(admin, autocommit=True) as connection:
        exists = connection.execute("SELECT 1 FROM pg_database WHERE datname = %s", (name,)).fetchone()
        if exists is None:
            connection.execute(f'CREATE DATABASE "{name}"')


def _migrate() -> None:
    _ensure_database()
    subprocess.run([sys.executable, "-m", "alembic", "upgrade", "head"], cwd=BACKEND_ROOT, check=True)


@pytest.fixture(scope="session")
def seeded_database():
    _migrate()
    from app.core.config import get_settings
    from app.db.seed import seed_demo_content
    from app.db.session import get_session_factory, reset_engine

    get_settings.cache_clear()
    reset_engine()
    db = get_session_factory()()
    try:
        seed_demo_content(db)
        db.commit()
    finally:
        db.close()
    yield


@pytest.fixture
def client(seeded_database):
    from app.api.deps import reset_rate_limits
    from app.main import create_app
    from fastapi.testclient import TestClient

    reset_rate_limits()
    with TestClient(create_app()) as test_client:
        yield test_client


def login(client, email: str, password: str) -> str:
    response = client.post("/api/v1/auth/login", json={"email": email, "password": password})
    assert response.status_code == 200, response.text
    return response.json()["access_token"]


def auth(token: str) -> dict[str, str]:
    return {"Authorization": f"Bearer {token}"}
