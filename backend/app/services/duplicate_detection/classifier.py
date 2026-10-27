"""Deterministic engineering comparison.

Embedding similarity is a retrieval signal. It reaches the verdict only through
the optional semantic route (same component, cosine at or above
semantic_duplicate_threshold, no detected difference in action), which is off
unless a threshold is passed. This classifier does not emit a confidence
percentage. Same component, department, or benefit is not enough to call two
ideas duplicates.

Further rules can each be switched off (all off when not passed): fuzzy component
matching after abbreviation expansion (with a guard for qualified names such as
"front"/"rear"), negated action keywords ignored, opposite before -> after state pairs
(direction, which also covers reversals), a query that adds kinds of change (scope), and
a symmetric fuzzy score for the lexical rule.
"""

from __future__ import annotations

import re
import unicodedata
from dataclasses import dataclass, field

from rapidfuzz import fuzz

from app.services.text import SYNONYMS, jaccard, normalize_text

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
# Subset guard (component_subset_guard): "Front spring bracket rear" and "Front spring bracket" name different parts
# although one name contains the other. A fuzzy score cannot see that (ratio gives them 88.9, token_set_ratio 100),
# so a name whose extra words are anything but these is a different component, and a positional or ordinal
# qualifier on either side that the other lacks always is. This is checked before the threshold, not instead of it.
NON_DISTINGUISHING_COMPONENT_WORDS = {"assembly", "part", "component", "unit", "complete"}
POSITIONAL_QUALIFIERS = {
    "front", "rear", "upper", "lower", "left", "right", "lh", "rh", "inner", "outer", "first", "second",
}

# Direction (direction_detection): "from X to Y", "replace X with Y" and "substitute Y for X" give a state pair.
# Two numbers with a length unit make a decrease or an increase; two different materials make a substitution
# X -> Y. A reversal ("revert from aluminium back to steel") is a substitution pair that runs the other way, so
# it needs no verb list of its own.
LENGTH_UNITS = {"mm": 1.0, "cm": 10.0, "in": 25.4, "inch": 25.4, "inches": 25.4}
MATERIALS = {
    "steel": "steel",
    "aluminum": "aluminum",
    "polypropylene": "polypropylene",
    "pp": "polypropylene",
    "polycarbonate": "polycarbonate",
    "pc": "polycarbonate",
    "pmma": "pmma",
    "acrylic": "pmma",
    "pet": "pet",
    "phenolic": "phenolic",
    "rubber": "rubber",
    "urethane": "urethane",
    "polyurethane": "urethane",
    "titanium": "titanium",
    "magnesium": "magnesium",
    "nylon": "nylon",
    "polyamide": "nylon",
    "abs": "abs",
    "iron": "iron",
    "copper": "copper",
    "brass": "brass",
    "zinc": "zinc",
    "vinyl": "vinyl",
    "fleece": "fleece",
    "composite": "composite",
}
STATE_SPAN = 8
_STATE_TOKEN = re.compile(r"\d+(?:\.\d+)?|[a-z]+")

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


@dataclass(frozen=True)
class StatePair:
    kind: str  # "length" (values in mm) or "material"
    before: str | float
    after: str | float

    @property
    def direction(self) -> str:
        if self.kind == "length":
            return "decrease" if self.after < self.before else "increase"
        return "substitute"

    def describe(self) -> str:
        if self.kind == "length":
            return f"{self.direction} from {self.before:g} mm to {self.after:g} mm"
        return f"{self.before} to {self.after}"


CLASSIFIER_FLAGS = (
    "component_fuzzy_match",
    "component_subset_guard",
    "negation_detection",
    "direction_detection",
    "scope_comparison",
    "symmetric_lexical_fuzzy",
)


def classifier_flags(ai_config: dict) -> dict[str, bool]:
    """The classify_pair switches, from the effective AI settings."""
    return {flag: bool(ai_config.get(flag)) for flag in CLASSIFIER_FLAGS}


def component_key(value: str | None) -> str:
    text = _PARENTHETICAL.sub(" ", value or "")
    return " ".join(COMPONENT_ABBREVIATIONS.get(token, token) for token in normalize_text(text).split())


def distinguishing_words(query: str | None, candidate: str | None) -> set[str]:
    """Words that make two component names different parts: a positional qualifier only one name has, or the
    extra words of a name that contains the other (apart from words such as "assembly")."""
    q_words, c_words = set(component_key(query).split()), set(component_key(candidate).split())
    found = (q_words ^ c_words) & POSITIONAL_QUALIFIERS
    if q_words != c_words and (q_words <= c_words or c_words <= q_words):
        found |= (q_words ^ c_words) - NON_DISTINGUISHING_COMPONENT_WORDS
    return found


def components_match(
    query: str | None, candidate: str | None, *, fuzzy: bool = False, subset_guard: bool = False
) -> bool:
    if not fuzzy:
        q_component, c_component = normalize_text(query), normalize_text(candidate)
        return bool(q_component and c_component and q_component == c_component)
    q_component, c_component = component_key(query), component_key(candidate)
    if subset_guard and distinguishing_words(query, candidate):
        return False
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


def read_actions(text: str, *, negation: bool = False) -> set[str]:
    """The tokens that count as proposed."""
    if not negation:
        return set(normalize_text(text).split())
    tokens: set[str] = set()
    for clause in _CLAUSE_END.split(text or ""):
        words = normalize_text(clause).split()
        negated = _negated_positions(words)
        tokens.update(word for index, word in enumerate(words) if index not in negated)
    return tokens


def change_types(text: str, *, negation: bool = False) -> set[str]:
    return _change_types(read_actions(text, negation=negation))


def _state_tokens(clause: str) -> list[str]:
    # Not normalize_text: it splits "1.5" into "1" and "5".
    text = unicodedata.normalize("NFKC", clause).lower().replace("-", " ")
    return [SYNONYMS.get(token, token) for token in _STATE_TOKEN.findall(text)]


def _length(span: list[str]) -> tuple[float, str | None] | None:
    for index, token in enumerate(span):
        if token[0].isdigit():
            unit = span[index + 1] if index + 1 < len(span) and span[index + 1] in LENGTH_UNITS else None
            return float(token), unit
    return None


def _material(span: list[str]) -> str | None:
    return next((MATERIALS[token] for token in span if token in MATERIALS), None)


def _state_pair(before: list[str], after: list[str]) -> StatePair | None:
    old, new = _length(before), _length(after)
    if old and new:
        old_unit, new_unit = old[1] or new[1], new[1] or old[1]
        if old_unit and new_unit:
            old_mm, new_mm = old[0] * LENGTH_UNITS[old_unit], new[0] * LENGTH_UNITS[new_unit]
            return StatePair("length", round(old_mm, 3), round(new_mm, 3)) if old_mm != new_mm else None
    old_material, new_material = _material(before), _material(after)
    if old_material and new_material and old_material != new_material:
        return StatePair("material", old_material, new_material)
    return None


def state_pairs(text: str) -> list[StatePair]:
    """Before -> after state pairs stated in the text."""
    found: list[StatePair] = []
    for clause in _CLAUSE_END.split(text or ""):
        words = _state_tokens(clause)
        for index, word in enumerate(words):
            if word == "from":
                link, swapped = "to", False
            elif word in {"replace", "replaced", "replacing"}:
                link, swapped = "with", False
            elif word in {"substitute", "substituted", "substituting"}:
                link, swapped = "for", True  # "substitute Y for X": X is the old state
            else:
                continue
            window = words[index + 1 : index + 1 + STATE_SPAN]
            if link not in window:
                continue
            split = index + 1 + window.index(link)
            first, second = words[index + 1 : split], words[split + 1 : split + 1 + STATE_SPAN]
            pair = _state_pair(second, first) if swapped else _state_pair(first, second)
            if pair and pair not in found:
                found.append(pair)
    return found


def direction_conflict(query: list[StatePair], candidate: list[StatePair]) -> str | None:
    """Why the two ideas change the same thing in opposite directions, or None if they do not."""
    q_lengths = {pair.direction for pair in query if pair.kind == "length"}
    c_lengths = {pair.direction for pair in candidate if pair.kind == "length"}
    if q_lengths and c_lengths and q_lengths.isdisjoint(c_lengths):
        return (
            "The proposed changes run in opposite directions: "
            f"{'; '.join(p.describe() for p in query if p.kind == 'length')} compared with "
            f"{'; '.join(p.describe() for p in candidate if p.kind == 'length')}."
        )
    q_materials = {(p.before, p.after) for p in query if p.kind == "material"}
    c_materials = {(p.before, p.after) for p in candidate if p.kind == "material"}
    flipped = sorted((old, new) for old, new in q_materials if (new, old) in c_materials and (old, new) not in c_materials)
    if flipped:
        old, new = flipped[0]
        return f"The material change is reversed: {old} to {new} compared with {new} to {old}."
    return None


def _change_types(tokens: set[str]) -> set[str]:
    found: set[str] = set()
    if tokens & MATERIAL_TERMS and tokens & CHANGE_VERBS:
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
    component_subset_guard: bool = False,
    negation_detection: bool = False,
    direction_detection: bool = False,
    scope_comparison: bool = False,
    symmetric_lexical_fuzzy: bool = False,
    symmetric_fuzzy_score: float | None = None,
) -> HeuristicResult:
    similarities: list[str] = []
    differences: list[str] = []
    q_norm = normalize_text(query_text)
    c_norm = normalize_text(candidate_text)
    overlap = jaccard(q_norm, c_norm)
    q_component = normalize_text(query_component)
    c_component = normalize_text(candidate_component)
    same_component = components_match(
        query_component, candidate_component, fuzzy=component_fuzzy_match, subset_guard=component_subset_guard
    )
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

    q_types = change_types(query_text, negation=negation_detection)
    c_types = change_types(candidate_text, negation=negation_detection)
    # The same quantity or material changed in opposite directions. Cosine cannot see this: the wording is
    # nearly the same either way.
    conflict = direction_conflict(state_pairs(query_text), state_pairs(candidate_text)) if direction_detection else None
    if conflict:
        differences.append(conflict)
    # The query proposes kinds of change the historical idea does not: a larger scope, not the same idea.
    extra_scope = q_types - c_types if scope_comparison and c_types and not q_types.isdisjoint(c_types) else set()
    if extra_scope:
        differences.append(
            "The query proposes more than the historical idea: it also includes "
            f"{', '.join(sorted(extra_scope))}, which the historical idea does not."
        )
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

    different_mechanism = bool(q_types and c_types and q_types.isdisjoint(c_types)) or bool(conflict) or bool(extra_scope)
    same_action = bool(q_types and c_types and q_types == c_types) and not conflict
    # token_set_ratio scores a text that contains the other near 100, so a superset passes the fuzzy rule by
    # construction. A symmetric score (token_sort_ratio) is used for the duplicate call when enabled.
    lexical_fuzzy = symmetric_fuzzy_score if symmetric_lexical_fuzzy and symmetric_fuzzy_score is not None else fuzzy_score
    lexical_duplicate = (lexical_fuzzy >= fuzzy_strong_threshold or overlap >= 0.62) or (
        same_action and same_component and overlap >= 0.42 and lexical_fuzzy >= 68
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
