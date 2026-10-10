"""Deterministic hashed embedding.

This is not a neural semantic model. It is a stable fallback so retrieval and
tests work without downloading weights or calling an external API. Vectors are
L2-normalised and fixed at 384 dimensions, matching the database column.
"""

from __future__ import annotations

import hashlib
import math

from app.domain.constants import EMBEDDING_DIM
from app.services.text import normalize_text


def embed_text(text: str, dimensions: int = EMBEDDING_DIM) -> list[float]:
    vector = [0.0] * dimensions
    normalised = normalize_text(text)
    if not normalised:
        return vector
    tokens = normalised.split()
    for token in tokens:
        _accumulate(vector, token.encode("utf-8"), 1.0)
    compact = "".join(tokens)
    for index in range(max(0, len(compact) - 2)):
        gram = compact[index : index + 3]
        _accumulate(vector, b"g:" + gram.encode("utf-8"), 0.35)
    norm = math.sqrt(sum(value * value for value in vector))
    if norm == 0:
        return vector
    return [value / norm for value in vector]


def _accumulate(vector: list[float], raw: bytes, weight: float) -> None:
    digest = hashlib.sha256(raw).digest()
    index = int.from_bytes(digest[:4], "little") % len(vector)
    sign = 1.0 if digest[4] % 2 == 0 else -1.0
    vector[index] += sign * weight


def cosine(left: list[float], right: list[float]) -> float:
    if not left or not right or len(left) != len(right):
        return 0.0
    return float(sum(a * b for a, b in zip(left, right, strict=True)))
