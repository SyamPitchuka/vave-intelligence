"""Deterministic engineering comparison.

Embedding similarity is a retrieval signal. It reaches the verdict only through
the optional semantic route (same component, cosine at or above
semantic_duplicate_threshold, no detected difference in action), which is off
unless a threshold is passed. This classifier does not emit a confidence
percentage. Same component, department, or benefit is not enough to call two
ideas duplicates.
"""

from __future__ import annotations

from dataclasses import dataclass, field

from app.services.text import jaccard, normalize_text

MATERIAL_TERMS = {"aluminum", "aluminium", "plastic", "polypropylene", "pmma", "acrylic", "pet", "titanium"}
TOPOLOGY_TERMS = {"topology", "optimized", "optimisation", "casting"}
DELETE_TERMS = {"delete", "remove", "depopulate"}
DIMENSION_TERMS = {"thickness", "gauge", "diameter", "mm"}


@dataclass
class HeuristicResult:
    category: str
    similarities: list[str] = field(default_factory=list)
    differences: list[str] = field(default_factory=list)
    explanation: str = ""
    exact_match: bool = False
    fuzzy_score: float = 0.0
    token_jaccard: float = 0.0
    change_types_query: list[str] = field(default_factory=list)
    change_types_candidate: list[str] = field(default_factory=list)


def change_types(text: str) -> set[str]:
    tokens = set(normalize_text(text).split())
    found: set[str] = set()
    if tokens & MATERIAL_TERMS and tokens & {"replace", "substitute", "substitution", "change", "switch", "swap", "use", "using", "adopt"}:
        found.add("material_substitution")
    if tokens & TOPOLOGY_TERMS:
        found.add("topology")
    if tokens & DELETE_TERMS and "replace" not in tokens and "substitute" not in tokens:
        found.add("deletion")
    if tokens & DIMENSION_TERMS:
        found.add("dimension")
    if tokens & {"commonise", "commonize", "commonisation", "commonization"}:
        found.add("commonisation")
    if tokens & {"bolt", "bolts"} and tokens & {"grade"}:
        found.add("fastener_grade")
    return found


def classify_pair(
    *,
    query_component: str | None,
    query_text: str,
    candidate_component: str | None,
    candidate_text: str,
    fuzzy_score: float,
    exact: bool,
    fuzzy_strong_threshold: float = 86,
    cosine: float | None = None,
    semantic_duplicate_threshold: float | None = None,
) -> HeuristicResult:
    similarities: list[str] = []
    differences: list[str] = []
    q_norm = normalize_text(query_text)
    c_norm = normalize_text(candidate_text)
    overlap = jaccard(q_norm, c_norm)
    q_component = normalize_text(query_component)
    c_component = normalize_text(candidate_component)
    same_component = bool(q_component and c_component and q_component == c_component)
    if same_component:
        similarities.append("The component or assembly name matches.")
    elif q_component and c_component:
        differences.append(
            f"Component differs: '{query_component}' compared with '{candidate_component}'."
        )

    q_types = change_types(query_text)
    c_types = change_types(candidate_text)
    if q_types and c_types and q_types == c_types:
        similarities.append(f"The recorded technical action is the same kind of change ({', '.join(sorted(q_types))}).")
    elif q_types and c_types and q_types.isdisjoint(c_types):
        differences.append(
            "The technical action differs: "
            f"{', '.join(sorted(q_types))} compared with {', '.join(sorted(c_types))}."
        )

    if exact and len(q_norm) >= 20:
        explanation = (
            "The normalised descriptions are identical. That is lexical evidence of the same wording, "
            "not a calibrated probability."
        )
        return HeuristicResult(
            category="potential_duplicate",
            similarities=similarities + ["Normalised description text is an exact match."],
            differences=differences,
            explanation=explanation,
            exact_match=True,
            fuzzy_score=fuzzy_score,
            token_jaccard=overlap,
            change_types_query=sorted(q_types),
            change_types_candidate=sorted(c_types),
        )

    different_mechanism = bool(q_types and c_types and q_types.isdisjoint(c_types))
    same_action = bool(q_types and c_types and q_types == c_types)
    lexical_duplicate = (fuzzy_score >= fuzzy_strong_threshold or overlap >= 0.62) or (
        same_action and same_component and overlap >= 0.42 and fuzzy_score >= 68
    )
    # Off unless a threshold is given. A paraphrase keeps the meaning but not the words, so it fails every
    # lexical rule; this route accepts it on embedding similarity when nothing shows a different action.
    semantic_duplicate = (
        semantic_duplicate_threshold is not None
        and cosine is not None
        and same_component
        and cosine >= semantic_duplicate_threshold
    )
    if lexical_duplicate and not different_mechanism:
        category = "potential_duplicate"
        explanation = (
            "Lexical overlap is high and the technical action does not contradict the historical record. "
            "This is a retrieval result for an engineer to confirm."
        )
        similarities.append("Wording and technical action overlap strongly.")
    elif semantic_duplicate and not different_mechanism:
        category = "potential_duplicate"
        explanation = (
            f"The component matches and the embedding similarity ({cosine:.3f}) is at or above the configured "
            f"threshold ({semantic_duplicate_threshold:.2f}), and no different technical action was detected. "
            "The wording differs, so this rests on meaning rather than shared words. An engineer must confirm it."
        )
        similarities.append("Same component, and the descriptions are close in meaning although worded differently.")
    elif different_mechanism and (same_component or overlap >= 0.2 or fuzzy_score >= 55):
        category = "similar_but_distinct"
        explanation = (
            "The ideas share context, but the proposed technical action is not the same. "
            "Same component or same benefit is not treated as a duplicate."
        )
    elif fuzzy_score < 48 and overlap < 0.18:
        category = "no_strong_match"
        explanation = "No strong lexical match was found against this historical record."
    elif same_component and overlap < 0.45:
        # Low word overlap is not evidence of a different action: a paraphrase of the same change lands here.
        # Similar but distinct needs a detected difference in technical action, handled above.
        category = "insufficient_evidence"
        explanation = (
            "The component matches, but the descriptions neither establish that the engineering change is the same "
            "nor show a different technical action. Manual engineering review is required."
        )
    else:
        category = "insufficient_evidence"
        explanation = (
            "The available text is not sufficient to call this a duplicate or to call it clearly unrelated. "
            "Manual engineering review is required."
        )

    return HeuristicResult(
        category=category,
        similarities=similarities,
        differences=differences,
        explanation=explanation,
        exact_match=False,
        fuzzy_score=fuzzy_score,
        token_jaccard=round(overlap, 4),
        change_types_query=sorted(q_types),
        change_types_candidate=sorted(c_types),
    )


def headline_category(categories: list[str]) -> str:
    if not categories:
        return "no_strong_match"
    priority = (
        "potential_duplicate",
        "insufficient_evidence",
        "similar_but_distinct",
        "no_strong_match",
    )
    for item in priority:
        if item in categories:
            return item
    return "no_strong_match"
