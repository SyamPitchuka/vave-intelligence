"""Chat provider interface. Implementations must not be selected by the frontend."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Protocol


class OfflineModeBlocked(RuntimeError):
    """Raised when an outbound model call is attempted while that path is blocked."""


class ProviderUnavailable(RuntimeError):
    """Raised when the selected local or online model cannot be used."""


@dataclass
class ProviderStatus:
    provider: str
    model: str | None
    available: bool
    detail: str
    external: bool


class ChatProvider(Protocol):
    name: str
    model: str | None
    external: bool

    def complete(self, messages: list[dict[str, str]], *, timeout: int) -> str: ...

    def status(self) -> ProviderStatus: ...


class EmbeddingProvider(Protocol):
    name: str
    model: str
    dimensions: int

    def embed(self, text: str) -> list[float]: ...

    def status(self) -> ProviderStatus: ...
