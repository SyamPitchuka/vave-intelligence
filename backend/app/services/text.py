"""Text normalisation for matching. The original description is always stored unchanged."""

from __future__ import annotations

import re
import unicodedata

SYNONYMS = {
    "aluminium": "aluminum",
    "optimised": "optimized",
    "optimise": "optimize",
    "optimisation": "optimization",
    "colour": "color",
    "centre": "center",
    "grey": "gray",
    "fibre": "fiber",
    "mould": "mold",
    "tyre": "tire",
    "tyres": "tires",
}

_TOKEN = re.compile(r"[a-z0-9]+")


def normalize_text(value: str | None) -> str:
    if not value:
        return ""
    text = unicodedata.normalize("NFKC", value).lower().replace("-", " ")
    tokens = [SYNONYMS.get(token, token) for token in _TOKEN.findall(text)]
    return " ".join(tokens)


def tokenize(value: str | None) -> list[str]:
    return normalize_text(value).split()


def comparison_blob(
    *,
    component: str | None,
    description: str | None,
    proposed_change: str | None = None,
    expected_benefit: str | None = None,
    current_design: str | None = None,
) -> str:
    parts = [component, description, current_design, proposed_change, expected_benefit]
    return normalize_text(" ".join(part for part in parts if part))


def jaccard(left: str, right: str) -> float:
    a = set(left.split())
    b = set(right.split())
    if not a or not b:
        return 0.0
    return len(a & b) / len(a | b)


def query_coverage(query: str, document: str) -> float:
    q = set(tokenize(query))
    d = set(tokenize(document))
    if not q:
        return 0.0
    return len(q & d) / len(q)
