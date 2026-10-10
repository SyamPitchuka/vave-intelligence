"""OpenAI chat and embeddings. Every call is refused unless mode is online."""

from __future__ import annotations

import httpx

from app.services.llm_providers.base import OfflineModeBlocked, ProviderStatus, ProviderUnavailable


class OpenAIChatProvider:
    name = "openai"
    external = True

    def __init__(self, *, api_key: str, model: str, base_url: str, mode: str) -> None:
        self.model = model
        self._api_key = api_key
        self._base_url = base_url.rstrip("/")
        self._mode = mode

    def _guard(self) -> None:
        if self._mode != "online":
            raise OfflineModeBlocked(
                "Outbound OpenAI calls are blocked because AI mode is not online. "
                "No idea text was sent."
            )
        if not self._api_key:
            raise ProviderUnavailable(
                "Online mode is selected but OPENAI_API_KEY is not configured on the server."
            )

    def complete(self, messages: list[dict[str, str]], *, timeout: int) -> str:
        self._guard()
        payload = {
            "model": self.model,
            "temperature": 0,
            "messages": messages,
            "response_format": {"type": "json_object"},
        }
        headers = {"Authorization": f"Bearer {self._api_key}"}
        url = f"{self._base_url}/chat/completions"
        response = self._post(url, headers, payload, timeout)
        if response.status_code in {429, 503}:
            response = self._post(url, headers, payload, timeout)
        if response.status_code >= 400:
            raise ProviderUnavailable(f"OpenAI chat request failed with status {response.status_code}.")
        body = response.json()
        try:
            return body["choices"][0]["message"]["content"]
        except (KeyError, IndexError, TypeError) as exc:
            raise ProviderUnavailable("OpenAI returned an unexpected chat response.") from exc

    def status(self) -> ProviderStatus:
        try:
            self._guard()
        except (OfflineModeBlocked, ProviderUnavailable) as exc:
            return ProviderStatus("openai", self.model, False, str(exc), True)
        try:
            response = self._post(
                f"{self._base_url}/models",
                {"Authorization": f"Bearer {self._api_key}"},
                None,
                15,
                method="GET",
            )
        except httpx.HTTPError as exc:
            return ProviderStatus("openai", self.model, False, f"OpenAI could not be reached: {exc.__class__.__name__}", True)
        if response.status_code >= 400:
            return ProviderStatus("openai", self.model, False, f"OpenAI status check returned {response.status_code}.", True)
        return ProviderStatus("openai", self.model, True, "OpenAI API accepted the credentials.", True)

    def _post(self, url: str, headers: dict, payload: dict | None, timeout: int, method: str = "POST") -> httpx.Response:
        with httpx.Client(timeout=timeout) as client:
            if method == "GET":
                return client.get(url, headers=headers)
            return client.post(url, headers=headers, json=payload)


class OpenAIEmbeddingProvider:
    name = "openai"
    external = True

    def __init__(self, *, api_key: str, model: str, base_url: str, mode: str, dimensions: int) -> None:
        self.model = model
        self.dimensions = dimensions
        self._api_key = api_key
        self._base_url = base_url.rstrip("/")
        self._mode = mode

    def embed(self, text: str) -> list[float]:
        if self._mode != "online":
            raise OfflineModeBlocked("OpenAI embeddings are blocked because AI mode is not online.")
        if not self._api_key:
            raise ProviderUnavailable("OPENAI_API_KEY is not configured on the server.")
        with httpx.Client(timeout=30) as client:
            response = client.post(
                f"{self._base_url}/embeddings",
                headers={"Authorization": f"Bearer {self._api_key}"},
                json={"model": self.model, "input": text, "dimensions": self.dimensions},
            )
        if response.status_code >= 400:
            raise ProviderUnavailable(f"OpenAI embedding request failed with status {response.status_code}.")
        vector = response.json()["data"][0]["embedding"]
        if len(vector) != self.dimensions:
            raise ProviderUnavailable(
                f"OpenAI returned {len(vector)} dimensions; this database column stores {self.dimensions}. "
                "Re-index only after a migration changes the column."
            )
        return vector

    def status(self) -> ProviderStatus:
        if self._mode != "online":
            return ProviderStatus("openai", self.model, False, "Blocked because mode is not online.", True)
        if not self._api_key:
            return ProviderStatus("openai", self.model, False, "OPENAI_API_KEY is empty.", True)
        return ProviderStatus("openai", self.model, True, "Key is configured. A live embedding call is made only by Test connection.", True)
