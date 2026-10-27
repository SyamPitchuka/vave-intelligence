"""Validated application settings. Secrets come from the environment, never from the client."""

from __future__ import annotations

from functools import lru_cache
from pathlib import Path

from pydantic import Field, field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

REPO_ROOT = Path(__file__).resolve().parents[3]
BACKEND_ROOT = Path(__file__).resolve().parents[2]


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=(str(REPO_ROOT / ".env"), str(BACKEND_ROOT / ".env"), ".env"),
        env_file_encoding="utf-8",
        extra="ignore",
    )

    app_env: str = "development"
    app_name: str = "VAVE Intelligence"
    app_version: str = "1.0.0"
    secret_key: str = "change-me-in-production-use-a-long-random-string"
    access_token_expire_minutes: int = 480
    cors_origins: str = "http://localhost:5173,http://127.0.0.1:5173"
    backend_host: str = "0.0.0.0"
    backend_port: int = 8000

    database_url: str = "postgresql+psycopg://vave:vave_dev_password@127.0.0.1:5432/vave_intelligence"
    test_database_url: str = (
        "postgresql+psycopg://vave:vave_dev_password@127.0.0.1:5432/vave_intelligence_test"
    )

    seed_demo_data: bool = True
    demo_user_password: str = "VaveDemo!234"
    admin_email: str = "admin@vave.local"
    admin_password: str = "ChangeMeAdmin!23"
    display_timezone: str = "Asia/Kolkata"
    dataset_label: str = "Synthetic"

    ai_mode: str = "fallback"
    llm_required: bool = False

    openai_api_key: str = ""
    openai_base_url: str = "https://api.openai.com/v1"
    openai_chat_model: str = "gpt-4o-mini"
    openai_embedding_model: str = "text-embedding-3-small"
    openai_embedding_dimensions: int = 384

    ollama_base_url: str = "http://127.0.0.1:11434"
    ollama_chat_model: str = "llama3.2"
    ollama_embedding_model: str = "nomic-embed-text"
    ollama_allow_hosts: str = "localhost,127.0.0.1,::1,ollama,host.docker.internal"

    embedding_provider: str = "deterministic"
    embedding_model: str = "deterministic-hash-v1"
    embedding_dimensions: int = 384

    retrieval_top_k: int = 15
    comparison_timeout_seconds: int = 60
    fuzzy_strong_threshold: float = 86
    cosine_retrieve_threshold: float = 0.22
    # None keeps the semantic Potential Duplicate route off (see classify_pair).
    semantic_duplicate_threshold: float | None = None
    # Classifier rules from the edge-case evaluation (see classify_pair); each can be turned off on its own.
    component_fuzzy_match: bool = True
    component_subset_guard: bool = True
    negation_detection: bool = True
    direction_detection: bool = True
    scope_comparison: bool = True
    # Off: it changed no labelled v2 or edge-case verdict, and it costs v2 recall unless the semantic route is on
    # (docs/evaluation-edge-cases.md).
    symmetric_lexical_fuzzy: bool = False
    copilot_lexical_threshold: float = 0.45

    upload_max_mb: int = 20
    chunk_size: int = 800
    chunk_overlap: int = 120

    log_level: str = "INFO"
    log_prompt_bodies: bool = False
    run_jobs_inline: bool = False

    corporate_database_url: str = ""
    corporate_ideas_view: str = "vave_historical_ideas"

    vave_data_dir: str = ""
    storage_dir: str = ""

    testing: bool = Field(default=False)

    @field_validator("ai_mode")
    @classmethod
    def _mode(cls, value: str) -> str:
        allowed = {"online", "offline", "fallback"}
        mode = value.strip().lower()
        if mode not in allowed:
            raise ValueError(f"AI_MODE must be one of {sorted(allowed)}")
        return mode

    @field_validator("embedding_dimensions")
    @classmethod
    def _dim(cls, value: int) -> int:
        if value != 384:
            raise ValueError(
                "This build stores vectors in a vector(384) column. "
                "A different dimension needs a new migration and a full re-index."
            )
        return value

    def cors_origin_list(self) -> list[str]:
        return [item.strip() for item in self.cors_origins.split(",") if item.strip()]

    def ollama_host_allowlist(self) -> set[str]:
        return {item.strip().lower() for item in self.ollama_allow_hosts.split(",") if item.strip()}

    def resolved_data_dir(self) -> Path:
        if self.vave_data_dir:
            return Path(self.vave_data_dir)
        candidate = REPO_ROOT / "data"
        if candidate.exists():
            return candidate
        return BACKEND_ROOT / "data"

    def resolved_storage_dir(self) -> Path:
        path = Path(self.storage_dir) if self.storage_dir else REPO_ROOT / "storage"
        path.mkdir(parents=True, exist_ok=True)
        return path

    def assert_production_safe(self) -> None:
        if self.app_env != "production":
            return
        if len(self.secret_key) < 32 or "change-me" in self.secret_key:
            raise RuntimeError("SECRET_KEY must be a long random value when APP_ENV=production")
        if "vave_dev_password" in self.database_url or self.admin_password == "ChangeMeAdmin!23":
            raise RuntimeError("Replace development credentials before production use")
        if self.seed_demo_data:
            raise RuntimeError("SEED_DEMO_DATA must be false in production")


@lru_cache
def get_settings() -> Settings:
    settings = Settings()
    settings.assert_production_safe()
    return settings
