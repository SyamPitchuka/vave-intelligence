"""Local Ollama provider. Offline mode refuses any host outside the allow-list."""

from __future__ import annotations

from urllib.parse import urlparse

import httpx

from app.services.llm_providers.base import OfflineModeBlocked, ProviderStatus, ProviderUnavailable


class OllamaChatProvider:
    name = "ollama"
    external = False

    def __init__(self, *, base_url: str, model: str, allow_hosts: set[str], mode: str) -> None:
        self.model = model
        self._base_url = base_url.rstrip("/")
        self._allow_hosts = {host.lower() for host in allow_hosts}
        self._mode = mode

    def _guard_host(self) -> None:
        host = (urlparse(self._base_url).hostname or "").lower()
        if self._mode == "offline" and host not in self._allow_hosts:
            raise OfflineModeBlocked(
                f"Offline mode blocked the Ollama host '{host}'. "
                "Only configured local hosts are allowed, and OpenAI is not used instead."
            )
        if self._mode == "online":
            raise ProviderUnavailable("Online mode does not send chat requests to Ollama.")

    def complete(self, messages: list[dict[str, str]], *, timeout: int) -> str:
        self._guard_host()
        try:
            with httpx.Client(timeout=timeout) as client:
                response = client.post(
                    f"{self._base_url}/api/chat",
                    json={"model": self.model, "messages": messages, "stream": False, "format": "json"},
                )
        except httpx.HTTPError as exc:
            raise ProviderUnavailable(
                f"Ollama is not reachable at {self._base_url}. No external provider was contacted. "
                f"({exc.__class__.__name__})"
            ) from exc
        if response.status_code >= 400:
            raise ProviderUnavailable(
                f"Ollama returned status {response.status_code} for model '{self.model}'. "
                "If the model is missing, install it on the Ollama host. This application will not download it."
            )
        content = response.json().get("message", {}).get("content", "")
        if not content:
            raise ProviderUnavailable("Ollama returned an empty response.")
        return content

    def status(self) -> ProviderStatus:
        try:
            self._guard_host()
        except (OfflineModeBlocked, ProviderUnavailable) as exc:
            return ProviderStatus("ollama", self.model, False, str(exc), False)
        try:
            with httpx.Client(timeout=5) as client:
                response = client.get(f"{self._base_url}/api/tags")
        except httpx.HTTPError:
            return ProviderStatus(
                "ollama",
                self.model,
                False,
                f"Ollama is not reachable at {self._base_url}. Start Ollama locally. "
                "This application will not fall back to an online model.",
                False,
            )
        if response.status_code >= 400:
            return ProviderStatus("ollama", self.model, False, f"Ollama tags request returned {response.status_code}.", False)
        names = [item.get("name", "") for item in response.json().get("models", [])]
        if not _model_present(names, self.model):
            return ProviderStatus(
                "ollama",
                self.model,
                False,
                f"Model '{self.model}' is not installed in local Ollama. "
                f"Install it on the Ollama host with `ollama pull {self.model}`, then test again. "
                "This application will not download models automatically.",
                False,
            )
        return ProviderStatus("ollama", self.model, True, f"Model '{self.model}' is installed locally.", False)


class OllamaEmbeddingProvider:
    name = "ollama"
    external = False

    def __init__(self, *, base_url: str, model: str, allow_hosts: set[str], mode: str, dimensions: int) -> None:
        self.model = model
        self.dimensions = dimensions
        self._base_url = base_url.rstrip("/")
        self._allow_hosts = {host.lower() for host in allow_hosts}
        self._mode = mode

    def embed(self, text: str) -> list[float]:
        host = (urlparse(self._base_url).hostname or "").lower()
        if self._mode != "online" and host not in self._allow_hosts:
            raise OfflineModeBlocked("Ollama embeddings were blocked because the host is not local.")
        if self._mode == "fallback":
            raise ProviderUnavailable("Deterministic fallback mode does not call Ollama.")
        try:
            with httpx.Client(timeout=30) as client:
                response = client.post(
                    f"{self._base_url}/api/embeddings",
                    json={"model": self.model, "prompt": text},
                )
        except httpx.HTTPError as exc:
            raise ProviderUnavailable(f"Ollama embeddings are not reachable ({exc.__class__.__name__}).") from exc
        if response.status_code >= 400:
            raise ProviderUnavailable(
                f"Ollama embedding model '{self.model}' is unavailable. "
                f"Install it locally with `ollama pull {self.model}`. It will not be downloaded automatically."
            )
        vector = response.json().get("embedding") or []
        if len(vector) != self.dimensions:
            raise ProviderUnavailable(
                f"Ollama model '{self.model}' returned {len(vector)} dimensions, "
                f"but the index stores {self.dimensions}. Vectors were not mixed. "
                "Choose a 384-dimension model or plan a migration and a full re-index."
            )
        return [float(value) for value in vector]

    def status(self) -> ProviderStatus:
        chat = OllamaChatProvider(
            base_url=self._base_url, model=self.model, allow_hosts=self._allow_hosts, mode=self._mode
        )
        current = chat.status()
        return ProviderStatus("ollama", self.model, current.available, current.detail, False)


def _model_present(installed: list[str], wanted: str) -> bool:
    wanted = wanted.strip()
    for name in installed:
        if name == wanted or name.split(":")[0] == wanted or name == f"{wanted}:latest":
            return True
    return False
