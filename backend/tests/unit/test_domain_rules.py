from datetime import date
from decimal import Decimal

from app.core.config import Settings
from app.domain.synthetic import SYNTHETIC_IDEAS
from app.services.duplicate_detection import classifier
from app.services.duplicate_detection.classifier import (
    change_types,
    classify_pair,
    components_match,
    distinguishing_words,
    state_pairs,
)
from app.services.embeddings.deterministic import cosine, embed_text
from app.services.imports.mapping import suggest_mapping
from app.services.llm_providers.base import OfflineModeBlocked
from app.services.llm_providers.factory import build_chat_provider, build_embedding_provider
from app.services.llm_providers.openai import OpenAIChatProvider
from app.services.rejection import StageStatusError, is_rejected, normalize_stage
from app.services.savings import combined_annual_saving
from app.services.text import normalize_text


def test_savings_counts_each_vehicle_family_once():
    total, warnings = combined_annual_saving(
        Decimal("450"),
        [("HCV_RIGID", Decimal("1200")), ("HCV_TIPPER", Decimal("800")), ("HCV_RIGID", Decimal("1200"))],
    )
    assert total == Decimal("900000.00")
    assert warnings


def test_missing_saving_is_not_invented_as_zero():
    total, warnings = combined_annual_saving(None, [("HCV_RIGID", Decimal("10"))])
    assert total is None
    assert warnings


def test_synthetic_idea_001_formula():
    record = SYNTHETIC_IDEAS[0]
    pairs = [(key, Decimal(str(value))) for key, value in record["volumes"].items()]
    total, _warnings = combined_annual_saving(Decimal(str(record["saving_per_vehicle"])), pairs)
    assert total == Decimal("1170000.00")


def test_rejection_rules():
    assert is_rejected("Durability") is True
    assert is_rejected("  ") is False
    assert is_rejected(None) is False
    assert normalize_stage("c") == "C"
    assert normalize_stage(None) is None
    try:
        normalize_stage("Duplicate")
    except StageStatusError as exc:
        assert "not a stage status" in str(exc)
    else:
        raise AssertionError("Duplicate must not be accepted as a stage")


def test_normalisation_preserves_meaning_and_maps_aluminium():
    assert normalize_text("Aluminium cab-mount") == "aluminum cab mount"
    assert normalize_text("  ") == ""


def test_column_aliases_ignore_order_and_punctuation():
    headers = [
        "Total Combined Annual Saving Per Idea (INR)",
        "Idea_ID",
        "HCV Rigid Truck (Annual Volume)",
        "Stage_Status",
        "Applicable Vehicle / Tonnage Details",
    ]
    mapping = suggest_mapping(headers)
    assert mapping["Idea_ID"] == "idea_code"
    assert mapping["Stage_Status"] == "stage_status"
    assert mapping["HCV Rigid Truck (Annual Volume)"] == "volume_hcv_rigid"
    assert mapping["Applicable Vehicle / Tonnage Details"] == "applicable_vehicle_details"


def test_deterministic_embedding_is_stable_and_normalised():
    first = embed_text("aluminium cab mounting bracket")
    second = embed_text("aluminum cab mounting bracket")
    assert len(first) == 384
    assert abs(sum(value * value for value in first) - 1) < 1e-6
    assert first == embed_text("aluminium cab mounting bracket")
    assert cosine(first, second) > 0.9


def test_classifier_does_not_treat_same_component_as_duplicate():
    aluminum = "Replace the steel cab mounting bracket with an aluminium alloy bracket sized for equivalent stiffness."
    topology = "Redesign the cab mounting bracket as a topology-optimised steel casting, retaining the steel grade."
    result = classify_pair(
        query_component="Cab mounting bracket",
        query_text=topology,
        candidate_component="Cab mounting bracket",
        candidate_text=aluminum,
        fuzzy_score=70,
        exact=False,
    )
    assert result.category != "potential_duplicate"


def test_low_word_overlap_alone_does_not_make_a_pair_distinct():
    # A paraphrase of the same change: same component, few shared words, no detected action on the query side.
    paraphrase = "Lighter cab anchorage: move away from the current ferrous part to a light-alloy design, geometry adjusted so rigidity is not lost."
    aluminum = "Replace the steel cab mounting bracket with an aluminium alloy bracket sized for equivalent stiffness to reduce vehicle mass."
    result = classify_pair(
        query_component="Cab mounting bracket",
        query_text=paraphrase,
        candidate_component="Cab mounting bracket",
        candidate_text=aluminum,
        fuzzy_score=58,
        exact=False,
    )
    assert result.token_jaccard < 0.28
    assert result.category == "insufficient_evidence"


def test_detected_different_action_is_similar_but_distinct():
    aluminum = "Replace the steel cab mounting bracket with an aluminium alloy bracket sized for equivalent stiffness."
    topology = "Redesign the cab mounting bracket as a topology-optimised steel casting, retaining the steel grade."
    result = classify_pair(
        query_component="Cab mounting bracket",
        query_text=topology,
        candidate_component="Cab mounting bracket",
        candidate_text=aluminum,
        fuzzy_score=50,
        exact=False,
    )
    assert result.category == "similar_but_distinct"


SEMANTIC_PARAPHRASE = (
    "Lighter cab anchorage: move away from the current ferrous part to a light-alloy design, "
    "geometry adjusted so rigidity is not lost."
)
SEMANTIC_ALUMINUM = (
    "Replace the steel cab mounting bracket with an aluminium alloy bracket sized for equivalent stiffness "
    "to reduce vehicle mass."
)


def _semantic_pair(**overrides):
    arguments = {
        "query_component": "Cab mounting bracket",
        "query_text": SEMANTIC_PARAPHRASE,
        "candidate_component": "Cab mounting bracket",
        "candidate_text": SEMANTIC_ALUMINUM,
        "fuzzy_score": 58,
        "exact": False,
        "cosine": 0.85,
        "semantic_duplicate_threshold": 0.80,
    }
    arguments.update(overrides)
    return classify_pair(**arguments)


def test_semantic_route_accepts_a_same_component_paraphrase():
    assert _semantic_pair().category == "potential_duplicate"
    assert _semantic_pair(cosine=0.80).category == "potential_duplicate"


def test_semantic_route_is_off_without_a_threshold_or_cosine():
    assert _semantic_pair(semantic_duplicate_threshold=None).category == "insufficient_evidence"
    assert _semantic_pair(cosine=None).category == "insufficient_evidence"
    assert _semantic_pair(cosine=0.79).category == "insufficient_evidence"


def test_semantic_route_needs_the_same_component():
    result = _semantic_pair(query_component="Steering column lower bracket")
    assert result.category != "potential_duplicate"


def test_semantic_route_respects_a_detected_different_action():
    topology = "Redesign the cab mounting bracket as a topology-optimised steel casting, retaining the steel grade."
    result = _semantic_pair(query_text=topology, cosine=0.95)
    assert result.category == "similar_but_distinct"


def test_component_match_expands_abbreviations_and_drops_qualifiers():
    assert components_match("Cab Mtg Bkt", "Cab mounting bracket", fuzzy=True)
    assert components_match("Cab mount brkt", "Cab mounting bracket", fuzzy=True)
    assert components_match("Battery tray (LV)", "Battery tray", fuzzy=True)
    assert components_match("Steering column assy", "Steering column assembly", fuzzy=True)
    assert not components_match("Steering column lower bracket", "Cab mounting bracket", fuzzy=True)
    assert not components_match("Cab mounting bracket", None, fuzzy=True)


def test_component_match_is_exact_when_turned_off():
    assert components_match("Cab mounting bracket", "cab  mounting bracket")
    assert not components_match("Cab Mtg Bkt", "Cab mounting bracket")
    assert not components_match("Battery tray (LV)", "Battery tray")


def test_subset_guard_rejects_a_qualified_component_name_at_any_threshold(monkeypatch):
    monkeypatch.setattr(classifier, "COMPONENT_MATCH_THRESHOLD", 80)
    assert components_match("Front spring bracket rear", "Front spring bracket", fuzzy=True)
    assert not components_match("Front spring bracket rear", "Front spring bracket", fuzzy=True, subset_guard=True)
    assert not components_match("Door hinge bracket", "Door hinge bracket lower", fuzzy=True, subset_guard=True)
    # Neither name contains the other, but each has a positional qualifier the other lacks.
    assert components_match("Door hinge bracket upper", "Door hinge bracket lower", fuzzy=True)
    assert not components_match("Door hinge bracket upper", "Door hinge bracket lower", fuzzy=True, subset_guard=True)
    assert not components_match("LH tail lamp lens", "RH tail lamp lens", fuzzy=True, subset_guard=True)


def test_subset_guard_keeps_abbreviations_parentheticals_and_non_distinguishing_words():
    assert components_match("Cab Mtg Bkt", "Cab mounting bracket", fuzzy=True, subset_guard=True)
    assert components_match("Battery tray (LV)", "Battery tray", fuzzy=True, subset_guard=True)
    assert distinguishing_words("Steering column assembly", "Steering column") == set()
    assert distinguishing_words("Steering column lower bracket", "Steering column bracket") == {"lower"}
    assert distinguishing_words("Exhaust heat shield front", "Exhaust heat shield") == {"front"}


SHACKLE = "Change the front spring shackle from forged steel to a fabricated steel assembly to reduce forging cost."
BRACKET = "Change the front spring bracket from forged steel to a fabricated steel assembly to reduce forging cost."


def _lexical_pair(query_component: str, candidate_component: str, **flags):
    return classify_pair(
        query_component=query_component,
        query_text=SHACKLE,
        candidate_component=candidate_component,
        candidate_text=BRACKET,
        fuzzy_score=97.5,
        exact=False,
        component_fuzzy_match=True,
        component_subset_guard=True,
        **flags,
    )


def test_lexical_route_ignores_the_component_unless_required():
    assert _lexical_pair("Front spring shackle", "Front spring bracket").category == "potential_duplicate"


def test_lexical_match_on_a_different_component_is_similar_but_distinct():
    result = _lexical_pair("Front spring shackle", "Front spring bracket", lexical_requires_component=True)
    assert result.category == "similar_but_distinct"
    assert "different components" in result.explanation
    qualified = _lexical_pair("Front spring bracket rear", "Front spring bracket", lexical_requires_component=True)
    assert qualified.category == "similar_but_distinct"


def test_lexical_route_still_accepts_a_matching_or_variant_component():
    assert _lexical_pair("Front spring bracket", "Front spring bracket", lexical_requires_component=True).category == "potential_duplicate"
    assert _lexical_pair("Front spring brkt", "Front spring bracket", lexical_requires_component=True).category == "potential_duplicate"
    # A missing component is not evidence of a different part.
    assert _lexical_pair(None, "Front spring bracket", lexical_requires_component=True).category == "potential_duplicate"


def test_component_variant_reaches_the_semantic_route_only_with_fuzzy_matching():
    assert _semantic_pair(query_component="Cab Mtg Bkt", component_fuzzy_match=True).category == "potential_duplicate"
    assert _semantic_pair(query_component="Cab Mtg Bkt").category == "insufficient_evidence"


REVERT_TO_STEEL = "Revert the cab mounting bracket from aluminium alloy back to the original steel design after field fatigue findings."


def test_state_pairs_read_lengths_with_units_and_materials():
    assert [p.describe() for p in state_pairs("Reduce pan thickness from 1.5 mm to 1.2 mm and add a baffle.")] == [
        "decrease from 1.5 mm to 1.2 mm"
    ]
    # The unit may be given once, and inches convert to millimetres.
    assert state_pairs("Widen the strap from 50 to 60 mm.")[0].direction == "increase"
    assert state_pairs("Thin the pan from 0.059 in to 0.047 in.")[0].describe() == "decrease from 1.499 mm to 1.194 mm"
    assert [p.describe() for p in state_pairs(SEMANTIC_ALUMINUM)] == ["steel to aluminum"]
    assert [p.describe() for p in state_pairs("Substitute an aluminium alloy for the existing steel bracket.")] == [
        "steel to aluminum"
    ]
    assert [p.describe() for p in state_pairs(REVERT_TO_STEEL)] == ["aluminum to steel"]


def test_state_pairs_need_two_states():
    assert state_pairs("Remove material from low-stress regions to save mass.") == []
    assert state_pairs("Reduce propeller shaft tube diameter by 0.2 inch.") == []
    assert state_pairs("Carry the 5 mm crossmember across to the tractor-trailer programme.") == []
    assert state_pairs("Change the bracket from 6 mm to 6 mm.") == []


def test_opposite_directions_are_similar_but_distinct_whatever_the_cosine():
    reduce = "Reduce engine oil pan sheet thickness from 1.5 mm to 1.2 mm and add a baffle to control oil surge."
    increase = "Increase engine oil pan sheet thickness from 1.2 mm to 1.5 mm to improve stone-impact resistance."
    arguments = {"query_component": "Engine oil pan", "candidate_component": "Engine oil pan", "query_text": increase, "candidate_text": reduce}
    on = _semantic_pair(**arguments, cosine=0.99, direction_detection=True)
    assert on.category == "similar_but_distinct"
    assert any("opposite directions" in difference for difference in on.differences)
    # It also overrides a strong lexical score.
    assert _semantic_pair(**arguments, fuzzy_score=95, direction_detection=True).category == "similar_but_distinct"
    assert _semantic_pair(**arguments, cosine=0.99).category == "potential_duplicate"


def test_a_reversal_is_a_flipped_substitution():
    on = _semantic_pair(query_text=REVERT_TO_STEEL, cosine=0.9, direction_detection=True)
    assert on.category == "similar_but_distinct"
    assert any("reversed" in difference for difference in on.differences)
    assert _semantic_pair(query_text=REVERT_TO_STEEL, cosine=0.9).category == "potential_duplicate"


def test_the_same_direction_is_not_a_conflict():
    restore = "Return the cab mounting bracket from aluminium to the original steel design."
    result = _semantic_pair(query_text=REVERT_TO_STEEL, candidate_text=restore, cosine=0.9, direction_detection=True)
    assert result.category == "potential_duplicate"
    # Different materials on each side are not a reversal.
    plastic = "Change the cab mounting bracket from steel to a glass-filled polypropylene moulding."
    assert _semantic_pair(query_text=plastic, cosine=0.9, direction_detection=True).category == "potential_duplicate"


TRAY = "Change the low-voltage battery tray from painted steel to a formed polypropylene tray with metal inserts."
TRAY_AND_MOVE = TRAY + " Relocate the tray 40 mm rearward to clear the new AdBlue line."


def test_a_query_with_extra_changes_is_a_scope_mismatch():
    arguments = {"query_component": "Battery tray", "candidate_component": "Battery tray", "query_text": TRAY_AND_MOVE, "candidate_text": TRAY}
    assert change_types(TRAY_AND_MOVE) == {"dimension", "material_substitution"}
    on = _semantic_pair(**arguments, cosine=0.93, scope_comparison=True)
    assert on.category == "similar_but_distinct"
    assert any("dimension" in difference for difference in on.differences)
    assert _semantic_pair(**arguments, cosine=0.93).category == "potential_duplicate"


def test_scope_is_not_compared_when_the_query_proposes_less_or_the_candidate_has_no_action():
    narrower = {"query_component": "Battery tray", "candidate_component": "Battery tray", "query_text": TRAY, "candidate_text": TRAY_AND_MOVE}
    assert _semantic_pair(**narrower, cosine=0.93, scope_comparison=True).category == "potential_duplicate"
    no_action = {"query_component": "Battery tray", "candidate_component": "Battery tray", "query_text": TRAY_AND_MOVE, "candidate_text": "Lighter battery tray."}
    assert _semantic_pair(**no_action, cosine=0.93, scope_comparison=True).category == "potential_duplicate"


def test_symmetric_fuzzy_score_replaces_the_containment_score_in_the_lexical_rule():
    arguments = {
        "query_component": "Battery tray",
        "candidate_component": "Battery tray",
        # Long enough that word overlap (Jaccard) stays under 0.62, so only the fuzzy score can decide.
        "query_text": TRAY + " Relocate it 40 mm rearward and drop it 15 mm to clear the new AdBlue line and the revised harness routing behind the cab.",
        "candidate_text": TRAY,
        "fuzzy_score": 90,
        "symmetric_fuzzy_score": 70,
        "cosine": None,
    }
    assert _semantic_pair(**arguments).category == "potential_duplicate"
    assert _semantic_pair(**arguments, symmetric_lexical_fuzzy=True).category != "potential_duplicate"
    # Without a symmetric score the containment score is still used.
    assert _semantic_pair(**{**arguments, "symmetric_fuzzy_score": None}, symmetric_lexical_fuzzy=True).category == "potential_duplicate"


KEEP_HANDED = (
    "Keep the left and right mirror brackets as separate handed parts. Do not commonise them. "
    "Reduce cost instead by deleting two webs from each casting."
)
COMMONISE = "Commonise the left and right exterior mirror brackets into one handed bracket with a reversible insert."


def test_negated_action_keywords_are_not_counted():
    assert change_types(KEEP_HANDED) == {"commonisation", "topology"}
    assert change_types(KEEP_HANDED, negation=True) == {"topology"}
    assert change_types("A urethane bumper with no change to the 40 mm fitted length.", negation=True) == set()
    assert change_types("Never use aluminium here.", negation=True) == set()


def test_negation_does_not_cross_a_clause_or_reach_past_the_window():
    assert change_types("Keep the steel grade, and replace the bracket with aluminium.", negation=True) == {"material_substitution"}
    assert change_types("Keep the bracket on the current steel supplier for now and reduce thickness.", negation=True) == {"dimension"}
    # A decimal point is not a sentence end.
    assert change_types("Do not reduce the 1.5 mm wall.", negation=True) == set()


def test_a_query_that_rules_out_the_candidates_change_is_similar_but_distinct():
    arguments = {
        "query_component": "Exterior mirror bracket",
        "query_text": KEEP_HANDED,
        "candidate_component": "Exterior mirror bracket",
        "candidate_text": COMMONISE,
        "cosine": 0.86,
    }
    assert _semantic_pair(**arguments, negation_detection=True).category == "similar_but_distinct"
    assert _semantic_pair(**arguments).category == "potential_duplicate"


def test_candidates_are_ordered_by_verdict_then_cosine():
    from types import SimpleNamespace

    from app.services.duplicate_detection.service import candidate_display_key

    def candidate(code, category, cosine, fuzzy):
        return SimpleNamespace(code=code, category=category, cosine_similarity=cosine, fuzzy_score=fuzzy)

    # Retrieval order is by fuzzy score; the duplicate came last.
    retrieved = [
        candidate("air-tank", "insufficient_evidence", Decimal("0.648"), Decimal("57.04")),
        candidate("look-alike", "similar_but_distinct", Decimal("0.900"), Decimal("56.00")),
        candidate("no-cosine", "potential_duplicate", None, Decimal("90.00")),
        candidate("unrelated", "no_strong_match", Decimal("0.950"), Decimal("55.00")),
        candidate("syn-017", "potential_duplicate", Decimal("0.844"), Decimal("53.38")),
    ]
    ordered = [item.code for item in sorted(retrieved, key=candidate_display_key)]
    assert ordered == ["syn-017", "no-cosine", "air-tank", "look-alike", "unrelated"]


def test_exact_text_is_a_potential_duplicate():
    text = "Replace the steel cab mounting bracket with an aluminium alloy bracket sized for equivalent stiffness to reduce vehicle mass."
    result = classify_pair(
        query_component="Cab mounting bracket",
        query_text=text,
        candidate_component="Cab mounting bracket",
        candidate_text=text,
        fuzzy_score=100,
        exact=True,
    )
    assert result.category == "potential_duplicate"
    assert result.exact_match is True


def test_offline_factory_never_returns_openai_and_blocks_before_network(monkeypatch):
    settings = Settings(
        ai_mode="offline",
        secret_key="test-secret-key-for-unit-and-integration",
        openai_api_key="sk-test",
        app_env="test",
    )

    def explode(*_args, **_kwargs):
        raise AssertionError("network was called")

    monkeypatch.setattr("httpx.Client.post", explode)
    monkeypatch.setattr("httpx.Client.get", explode)
    provider = build_chat_provider(settings, "offline", "llama3.2")
    assert not isinstance(provider, OpenAIChatProvider)
    online = OpenAIChatProvider(api_key="sk-test", model="gpt-4o-mini", base_url="https://api.openai.com/v1", mode="offline")
    try:
        online.complete([{"role": "user", "content": "hello"}], timeout=5)
    except OfflineModeBlocked:
        pass
    else:
        raise AssertionError("offline OpenAI call should be blocked")
    try:
        build_embedding_provider(settings, "offline", "openai", "text-embedding-3-small")
    except Exception as exc:
        assert "blocked" in str(exc).lower()
    else:
        raise AssertionError("offline mode must not construct OpenAI embeddings")


def test_default_embedding_follows_mode_rules():
    from app.services.settings_store import _default_embedding

    minilm = "sentence-transformers/all-MiniLM-L6-v2"
    offline = Settings(ai_mode="offline", embedding_provider="sentence_transformers", embedding_model=minilm)
    assert _default_embedding(offline) == ("sentence_transformers", minilm)
    fallback = Settings(ai_mode="fallback", embedding_provider="sentence_transformers", embedding_model=minilm)
    assert _default_embedding(fallback) == ("deterministic", "deterministic-hash-v1")
    offline_openai = Settings(ai_mode="offline", embedding_provider="openai", embedding_model="text-embedding-3-small")
    assert _default_embedding(offline_openai) == ("deterministic", "deterministic-hash-v1")


def test_date_parse_day_first():
    from app.services.imports.validate import parse_date

    assert parse_date("02/01/2024") == date(2024, 1, 2)
    assert parse_date("2024-01-15") == date(2024, 1, 15)
