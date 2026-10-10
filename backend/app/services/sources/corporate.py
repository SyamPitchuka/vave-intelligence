"""Read-only corporate source. The DSN stays in the environment. SQL is not model-generated."""

from __future__ import annotations

import os
import re

from sqlalchemy import create_engine, text

VIEW_NAME = re.compile(r"^[A-Za-z_][A-Za-z0-9_]*$")
COLUMNS = (
    "idea_code",
    "component",
    "description",
    "idea_generation_date",
    "idea_belonged_department",
    "rejection_date",
    "rejected_department",
    "stage_status",
    "rejection_category",
    "rejection_reason",
    "idea_type",
    "saving_per_vehicle",
    "applicable_vehicle_details",
)


def test_connection(env_var: str, view_name: str) -> str:
    _check(env_var, view_name)
    engine = create_engine(os.environ[env_var], pool_pre_ping=True)
    try:
        with engine.connect() as connection:
            connection.execute(text("SELECT 1"))
            connection.execute(text(f"SELECT {', '.join(COLUMNS)} FROM {view_name} LIMIT 1"))
    finally:
        engine.dispose()
    return "Corporate connection succeeded with the fixed column list. Credentials were not stored."


def fetch_rows(env_var: str, view_name: str, limit: int = 500) -> list[dict]:
    _check(env_var, view_name)
    engine = create_engine(os.environ[env_var], pool_pre_ping=True)
    statement = text(f"SELECT {', '.join(COLUMNS)} FROM {view_name} LIMIT :limit")
    try:
        with engine.connect() as connection:
            result = connection.execute(statement, {"limit": limit})
            return [dict(row._mapping) for row in result]
    finally:
        engine.dispose()


def _check(env_var: str, view_name: str) -> None:
    if not re.fullmatch(r"[A-Z_][A-Z0-9_]*", env_var):
        raise ValueError("The credential environment variable name is not valid.")
    if not VIEW_NAME.match(view_name):
        raise ValueError("The view name must be a plain identifier. Arbitrary SQL is not accepted.")
    if not os.environ.get(env_var):
        raise ValueError(
            f"{env_var} is not set on the server. Excel and the local database remain available, "
            "and the connection string is not stored in the application database."
        )
