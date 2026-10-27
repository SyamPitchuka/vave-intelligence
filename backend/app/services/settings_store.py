"""Non-secret settings live in the database. API keys never do."""

from __future__ import annotations

import uuid
from datetime import UTC, datetime
from typing import Any

from sqlalchemy.orm import Session

from app.core.config import Settings, get_settings
from app.domain.constants import DETERMINISTIC_EMBEDDING_MODEL
from app.models import ApplicationSetting

EDITABLE = {
    "mode",
    "llm_required",
    "chat_model",
    "embedding_provider",
    "embedding_model",
    "retrieval_top_k",
    "comparison_timeout_seconds",
    "fuzzy_strong_threshold",
    "cosine_retrieve_threshold",
    "semantic_duplicate_threshold",
    "component_fuzzy_match",
    "reversal_detection",
    "negation_detection",
    "copilot_lexical_threshold",
    "dataset_label",
    "display_timezone",
}


def _default_embedding(settings: Settings) -> tuple[str, str]:
    """Same rules as effective_ai: fallback is deterministic, and offline never selects OpenAI."""
    provider = settings.embedding_provider
    if settings.ai_mode == "fallback" or (settings.ai_mode != "online" and provider == "openai"):
        provider = "deterministic"
    if provider == "deterministic":
        return provider, DETERMINISTIC_EMBEDDING_MODEL
    return provider, settings.embedding_model


def _defaults(settings: Settings) -> dict[str, Any]:
    embedding_provider, embedding_model = _default_embedding(settings)
    return {
        "mode": settings.ai_mode,
        "llm_required": settings.llm_required,
        "chat_model": _default_chat_model(settings),
        "embedding_provider": embedding_provider,
        "embedding_model": embedding_model,
        "retrieval_top_k": settings.retrieval_top_k,
        "comparison_timeout_seconds": settings.comparison_timeout_seconds,
        "fuzzy_strong_threshold": settings.fuzzy_strong_threshold,
        "cosine_retrieve_threshold": settings.cosine_retrieve_threshold,
        "semantic_duplicate_threshold": settings.semantic_duplicate_threshold,
        "component_fuzzy_match": settings.component_fuzzy_match,
        "reversal_detection": settings.reversal_detection,
        "negation_detection": settings.negation_detection,
        "copilot_lexical_threshold": settings.copilot_lexical_threshold,
        "dataset_label": settings.dataset_label,
        "display_timezone": settings.display_timezone,
        "last_connection_check": None,
        "last_connection_ok": None,
        "last_connection_detail": None,
    }


def _default_chat_model(settings: Settings) -> str | None:
    if settings.ai_mode == "online":
        return settings.openai_chat_model
    if settings.ai_mode == "offline":
        return settings.ollama_chat_model
    return None


def ensure_ai_settings(db: Session) -> ApplicationSetting:
    row = db.get(ApplicationSetting, "ai")
    if row is None:
        row = ApplicationSetting(key="ai", value=_defaults(get_settings()))
        db.add(row)
        db.flush()
    return row


def effective_ai(db: Session) -> dict[str, Any]:
    settings = get_settings()
    stored = dict(ensure_ai_settings(db).value or {})
    merged = _defaults(settings)
    merged.update({key: stored[key] for key in stored})
    mode = str(merged.get("mode") or settings.ai_mode)
    warnings: list[str] = []
    provider_name = str(merged.get("embedding_provider") or "deterministic")
    embedding_model = str(merged.get("embedding_model") or DETERMINISTIC_EMBEDDING_MODEL)
    if mode != "online" and provider_name == "openai":
        warnings.append("OpenAI embeddings are blocked because the active mode is not online.")
        provider_name = "deterministic"
        embedding_model = DETERMINISTIC_EMBEDDING_MODEL
    if mode == "fallback":
        provider_name = "deterministic"
        embedding_model = DETERMINISTIC_EMBEDDING_MODEL
        merged["chat_model"] = None
    elif mode == "offline":
        merged["chat_model"] = merged.get("chat_model") or settings.ollama_chat_model
    elif mode == "online":
        merged["chat_model"] = merged.get("chat_model") or settings.openai_chat_model
    merged["mode"] = mode
    merged["embedding_provider"] = provider_name
    merged["embedding_model"] = embedding_model
    merged["runtime_warnings"] = warnings
    merged["openai_configured"] = bool(settings.openai_api_key)
    merged["external_inference_blocked"] = mode != "online"
    merged["embedding_dimensions"] = settings.embedding_dimensions
    return merged


def save_ai_settings(db: Session, updates: dict[str, Any], user_id: uuid.UUID | None) -> tuple[dict[str, Any], bool]:
    row = ensure_ai_settings(db)
    current = dict(row.value or {})
    previous_model = current.get("embedding_model")
    previous_provider = current.get("embedding_provider")
    for key, value in updates.items():
        if key in EDITABLE:
            current[key] = value
    if current.get("mode") not in {"online", "offline", "fallback"}:
        raise ValueError("Mode must be online, offline, or fallback.")
    top_k = int(current.get("retrieval_top_k") or 15)
    if not 5 <= top_k <= 50:
        raise ValueError("Retrieval count must be between 5 and 50.")
    current["retrieval_top_k"] = top_k
    current["fuzzy_strong_threshold"] = float(current.get("fuzzy_strong_threshold") or 86)
    current["cosine_retrieve_threshold"] = float(current.get("cosine_retrieve_threshold") or 0.22)
    semantic = current.get("semantic_duplicate_threshold")
    if semantic is not None:
        semantic = float(semantic)
        if not 0 < semantic <= 1:
            raise ValueError("The semantic duplicate threshold must be above 0 and at most 1, or empty to turn it off.")
    current["semantic_duplicate_threshold"] = semantic
    for flag in ("component_fuzzy_match", "reversal_detection", "negation_detection"):
        # A row saved before these settings existed has no value; leave it to the default.
        if flag in current:
            current[flag] = bool(current[flag])
    current["comparison_timeout_seconds"] = int(current.get("comparison_timeout_seconds") or 60)
    current["llm_required"] = bool(current.get("llm_required"))
    row.value = current
    row.updated_by = user_id
    row.updated_at = datetime.now(UTC)
    db.flush()
    effective = effective_ai(db)
    reindex = previous_model != effective["embedding_model"] or previous_provider != effective["embedding_provider"]
    return effective, reindex


def record_connection_check(db: Session, *, ok: bool, detail: str) -> None:
    row = ensure_ai_settings(db)
    current = dict(row.value or {})
    current["last_connection_check"] = datetime.now(UTC).isoformat()
    current["last_connection_ok"] = ok
    current["last_connection_detail"] = detail[:500]
    row.value = current
    db.flush()
