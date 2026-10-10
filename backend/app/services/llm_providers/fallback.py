"""Deterministic providers. They do not open network connections."""

from __future__ import annotations

from app.domain.constants import DETERMINISTIC_EMBEDDING_MODEL, EMBEDDING_DIM
from app.services.embeddings.deterministic import embed_text
from app.services.llm_providers.base import ProviderStatus


class FallbackChatProvider:
    """Used when the operator selects deterministic mode, or when a local model is down.

    `complete` is intentionally absent from the analysis path. Calling it raises so a
    caller cannot accidentally treat boilerplate text as a model judgement.
    """

    name = "deterministic"
    model = None
    external = False

    def complete(self, messages: list[dict[str, str]], *, timeout: int) -> str:
        raise RuntimeError(
            "Deterministic mode does not call a language model. "
            "Use the heuristic comparison result instead."
        )

    def status(self) -> ProviderStatus:
        return ProviderStatus(
            "deterministic",
            None,
            True,
            "Deterministic lexical matching is available. No language model is called.",
            False,
        )


class DeterministicEmbeddingProvider:
    name = "deterministic"
    external = False

    def __init__(self, dimensions: int = EMBEDDING_DIM) -> None:
        self.model = DETERMINISTIC_EMBEDDING_MODEL
        self.dimensions = dimensions

    def embed(self, text: str) -> list[float]:
        return embed_text(text, self.dimensions)

    def status(self) -> ProviderStatus:
        return ProviderStatus(
            "deterministic",
            self.model,
            True,
            "Hashed lexical embeddings are local. They are not a neural semantic model.",
            False,
        )


class SentenceTransformerEmbeddingProvider:
    """Optional local neural embeddings. The package is not installed by default."""

    name = "sentence_transformers"
    external = False

    def __init__(self, model: str, dimensions: int) -> None:
        self.model = model
        self.dimensions = dimensions
        self._loaded = None

    def embed(self, text: str) -> list[float]:
        model = self._model()
        vector = model.encode(text, normalize_embeddings=True).tolist()
        if len(vector) != self.dimensions:
            raise RuntimeError(
                f"Model '{self.model}' produced {len(vector)} dimensions, not {self.dimensions}. "
                "The index was not updated. A dimension change needs a migration and a full re-index."
            )
        return [float(value) for value in vector]

    def status(self) -> ProviderStatus:
        try:
            self._model()
        except Exception as exc:  # noqa: BLE001 — surface the install/load error to the administrator
            return ProviderStatus("sentence_transformers", self.model, False, str(exc), False)
        return ProviderStatus("sentence_transformers", self.model, True, "Local sentence-transformers model loaded.", False)

    def _model(self):
        if self._loaded is not None:
            return self._loaded
        try:
            from sentence_transformers import SentenceTransformer
        except ImportError as exc:
            raise RuntimeError(
                "sentence-transformers is not installed in this environment. "
                "Install it on the server or choose deterministic, OpenAI, or Ollama embeddings."
            ) from exc
        self._loaded = SentenceTransformer(self.model)
        return self._loaded
