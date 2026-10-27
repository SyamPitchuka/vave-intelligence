"""Deterministic engineering comparison.

Embedding similarity is a retrieval signal. It reaches the verdict only through
the optional semantic route (same component, cosine at or above
semantic_duplicate_threshold, no detected difference in action), which is off
unless a threshold is passed. This classifier does not emit a confidence
percentage. Same component, department, or benefit is not enough to call two
ideas duplicates.

Three rules can each be switched off (all off when not passed): fuzzy component
matching after abbreviation expansion, reversal verbs read as a direction flip of
an existing action, and negated action keywords ignored.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field

from rapidfuzz import fuzz

from app.services.text import jaccard, normalize_text

MATERIAL_TERMS = {"aluminum", "aluminium", "plastic", "polypropylene", "pmma", "acrylic", "pet", "titanium"}
TOPOLOGY_TERMS = {"topology", "optimized", "optimisation", "casting"}
DELETE_TERMS = {"delete", "remove", "depopulate"}
DIMENSION_TERMS = {"thickness", "gauge", "diameter", "mm"}
CHANGE_VERBS = {"replace", "substitute", "substitution", "change", "switch", "swap", "use", "using", "adopt"}

# Component matching (component_fuzzy_match): abbreviations are expanded and parenthetical qualifiers dropped
# before a fuzzy comparison, so "Cab Mtg Bkt" and "Battery tray (LV)" match their full names.
COMPONENT_ABBREVIATIONS = {"brkt": "bracket", "bkt": "bracket", "mtg": "mounting", "assy": "assembly"}
COMPONENT_MATCH_THRESHOLD = 90
_PARENTHETICAL = re.compile(r"\([^)]*\)")

# Reversal (reversal_detection): these verbs undo an earlier change, so they flip the direction of an existing
# action instead of adding a new one. "return" and "restore" are common in other senses ("restore bending
# stiffness", "fuel return line"), so a verb counts only when it opens a clause or a back-reference follows it
# in the same clause.
REVERSAL_VERBS = {"revert", "return", "restore", "reinstate", "rollback"}
BACK_REFERENCES = {"back", "original", "originally", "previous", "previously", "earlier", "former"}
REVERSAL_MARKER = "rollback"

# Negation (negation_detection): an action keyword within this many tokens after a cue is ruled out, not proposed.
NEGATION_CUES = (
    ("do", "not"),
    ("don", "t"),
    ("never",),
    ("without",),
    ("instead", "of"),
    ("rather", "than"),
    ("keep",),
    ("retain",),
    ("no", "change", "to"),
)
NEGATION_WINDOW = 5
# Sentence and clause ends. A full stop or comma between digits ("1.5 mm", "1,200") is not one.
_CLAUSE_END = re.compile(r"[.,;:!?](?=\s|$)|\n")


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


CLASSIFIER_FLAGS = ("component_fuzzy_match", "reversal_detection", "negation_detection")


def classifier_flags(ai_config: dict) -> dict[str, bool]:
    """The classify_pair switches, from the effective AI settings."""
    return {flag: bool(ai_config.get(flag)) for flag in CLASSIFIER_FLAGS}


def component_key(value: str | None) -> str:
    text = _PARENTHETICAL.sub(" ", value or "")
    return " ".join(COMPONENT_ABBREVIATIONS.get(token, token) for token in normalize_text(text).split())


def components_match(query: str | None, candidate: str | None, *, fuzzy: bool = False) -> bool:
    if not fuzzy:
        q_component, c_component = normalize_text(query), normalize_text(candidate)
        return bool(q_component and c_component and q_component == c_component)
    q_component, c_component = component_key(query), component_key(candidate)
    return bool(q_component and c_component and fuzz.ratio(q_component, c_component) >= COMPONENT_MATCH_THRESHOLD)


def _negated_positions(words: list[str]) -> set[int]:
    negated: set[int] = set()
    for start in range(len(words)):
        for cue in NEGATION_CUES:
            end = start + len(cue)
            if tuple(words[start:end]) == cue:
                # The cue's own words are not proposals either ("change" in "no change to").
                negated.update(range(start, min(end + NEGATION_WINDOW, len(words))))
    return negated


def read_actions(text: str, *, negation: bool = False, reversal: bool = False) -> tuple[set[str], bool]:
    """The tokens that count as proposed, and whether the text undoes an earlier change."""
    if not negation and not reversal:
        return set(normalize_text(text).split()), False
    tokens: set[str] = set()
    reverses = False
    for clause in _CLAUSE_END.split(text or ""):
        words = normalize_text(clause).split()
        if reversal:
            merged: list[str] = []
            for word in words:
                if word == "back" and merged and merged[-1] == "roll":
                    merged[-1] = "rollback"
                else:
                    merged.append(word)
            words = merged
        negated = _negated_positions(words) if negation else set()
        for index, word in enumerate(words):
            if index in negated:
                continue
            if reversal and word in REVERSAL_VERBS:
                if index == 0 or BACK_REFERENCES.intersection(words[index + 1 :]):
                    reverses = True
                    tokens.add(REVERSAL_MARKER)
                continue
            tokens.add(word)
    return tokens, reverses


def change_types(text: str, *, negation: bool = False, reversal: bool = False) -> set[str]:
    return _change_types(read_actions(text, negation=negation, reversal=reversal)[0])


def _change_types(tokens: set[str]) -> set[str]:
    found: set[str] = set()
    # A reversal verb counts as a change verb: "revert to steel" is still a material change, in reverse.
    if tokens & MATERIAL_TERMS and tokens & (CHANGE_VERBS | {REVERSAL_MARKER}):
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
    component_fuzzy_match: bool = False,
    reversal_detection: bool = False,
    negation_detection: bool = False,
) -> HeuristicResult:
    similarities: list[str] = []
    differences: list[str] = []
    q_norm = normalize_text(query_text)
    c_norm = normalize_text(candidate_text)
    overlap = jaccard(q_norm, c_norm)
    q_component = normalize_text(query_component)
    c_component = normalize_text(candidate_component)
    same_component = components_match(query_component, candidate_component, fuzzy=component_fuzzy_match)
    if same_component and q_component != c_component:
        similarities.append(
            "The component names match once abbreviations and qualifiers are normalised: "
            f"'{query_component}' and '{candidate_component}'."
        )
    elif same_component:
        similarities.append("The component or assembly name matches.")
    elif q_component and c_component:
        differences.append(
            f"Component differs: '{query_component}' compared with '{candidate_component}'."
        )

    q_tokens, q_reverses = read_actions(query_text, negation=negation_detection, reversal=reversal_detection)
    c_tokens, c_reverses = read_actions(candidate_text, negation=negation_detection, reversal=reversal_detection)
    q_types = _change_types(q_tokens)
    c_types = _change_types(c_tokens)
    # One side undoes a change of a kind the other side makes: the same action in the opposite direction.
    direction_flip = bool(q_types & c_types) and q_reverses != c_reverses
    if direction_flip:
        differences.append(
            "The technical action is reversed: one idea undoes a change of the kind the other proposes "
            f"({', '.join(sorted(q_types & c_types))})."
        )
    elif q_types and c_types and q_types == c_types:
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

    different_mechanism = bool(q_types and c_types and q_types.isdisjoint(c_types)) or direction_flip
    same_action = bool(q_types and c_types and q_types == c_types) and not direction_flip
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


# Most to least actionable. Used for the headline outcome and for ordering a run's candidates.
VERDICT_PRIORITY = (
    "potential_duplicate",
    "insufficient_evidence",
    "similar_but_distinct",
    "no_strong_match",
)


def headline_category(categories: list[str]) -> str:
    if not categories:
        return "no_strong_match"
    priority = VERDICT_PRIORITY
    for item in priority:
        if item in categories:
            return item
    return "no_strong_match"
