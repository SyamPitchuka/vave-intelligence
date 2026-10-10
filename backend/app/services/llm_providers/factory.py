"""Select providers from the effective mode. Offline never returns an OpenAI client."""

from __future__ import annotations

from app.core.config import Settings
from app.services.llm_providers.base import ProviderUnavailable
from app.services.llm_providers.fallback import (
    DeterministicEmbeddingProvider,
    FallbackChatProvider,
    SentenceTransformerEmbeddingProvider,
)
from app.services.llm_providers.ollama import OllamaChatProvider, OllamaEmbeddingProvider
from app.services.llm_providers.openai import OpenAIChatProvider, OpenAIEmbeddingProvider


def build_chat_provider(settings: Settings, mode: str, chat_model: str | None):
    if mode == "online":
        return OpenAIChatProvider(
            api_key=settings.openai_api_key,
            model=chat_model or settings.openai_chat_model,
            base_url=settings.openai_base_url,
            mode=mode,
        )
    if mode == "offline":
        return OllamaChatProvider(
            base_url=settings.ollama_base_url,
            model=chat_model or settings.ollama_chat_model,
            allow_hosts=settings.ollama_host_allowlist(),
            mode=mode,
        )
    if mode == "fallback":
        return FallbackChatProvider()
    raise ProviderUnavailable(f"Unknown AI mode '{mode}'.")


def build_embedding_provider(settings: Settings, mode: str, provider_name: str, model_name: str):
    """Offline and fallback modes cannot select OpenAI embeddings."""
    if provider_name == "openai":
        if mode != "online":
            raise ProviderUnavailable(
                "OpenAI embeddings are blocked because the active mode is not online. "
                "No text was sent. Switch the embedding provider or select online mode."
            )
        return OpenAIEmbeddingProvider(
            api_key=settings.openai_api_key,
            model=model_name or settings.openai_embedding_model,
            base_url=settings.openai_base_url,
            mode=mode,
            dimensions=settings.embedding_dimensions,
        )
    if provider_name == "ollama":
        if mode == "fallback":
            raise ProviderUnavailable("Deterministic fallback mode uses local hashed embeddings, not Ollama.")
        return OllamaEmbeddingProvider(
            base_url=settings.ollama_base_url,
            model=model_name or settings.ollama_embedding_model,
            allow_hosts=settings.ollama_host_allowlist(),
            mode=mode,
            dimensions=settings.embedding_dimensions,
        )
    if provider_name == "sentence_transformers":
        return SentenceTransformerEmbeddingProvider(model_name, settings.embedding_dimensions)
    return DeterministicEmbeddingProvider(settings.embedding_dimensions)
