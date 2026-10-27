from datetime import date
from decimal import Decimal

from app.core.config import Settings
from app.domain.synthetic import SYNTHETIC_IDEAS
from app.services.duplicate_detection.classifier import (
    change_types,
    classify_pair,
    components_match,
    read_actions,
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


def test_component_variant_reaches_the_semantic_route_only_with_fuzzy_matching():
    assert _semantic_pair(query_component="Cab Mtg Bkt", component_fuzzy_match=True).category == "potential_duplicate"
    assert _semantic_pair(query_component="Cab Mtg Bkt").category == "insufficient_evidence"


REVERT_TO_STEEL = "Revert the cab mounting bracket from aluminium alloy back to the original steel design after field fatigue findings."


def test_reversal_verbs_flip_the_direction_of_an_existing_action():
    tokens, reverses = read_actions(REVERT_TO_STEEL, reversal=True)
    assert reverses
    assert change_types(REVERT_TO_STEEL, reversal=True) == {"material_substitution"}
    assert read_actions("Roll back to the previous steel bracket.", reversal=True)[1]
    assert read_actions("Reinstate the phenolic board.", reversal=True)[1]


def test_reversal_verbs_in_other_senses_are_not_reversals():
    assert not read_actions("Add a rolled edge to restore bending stiffness.", reversal=True)[1]
    assert not read_actions("Reroute the fuel return line behind the crossmember.", reversal=True)[1]
    assert not read_actions(REVERT_TO_STEEL)[1]


def test_a_reversal_of_the_candidates_change_is_similar_but_distinct():
    on = _semantic_pair(query_text=REVERT_TO_STEEL, cosine=0.9, reversal_detection=True)
    assert on.category == "similar_but_distinct"
    assert any("reversed" in difference for difference in on.differences)
    assert _semantic_pair(query_text=REVERT_TO_STEEL, cosine=0.9).category == "potential_duplicate"


def test_two_reversals_of_the_same_change_are_not_a_direction_flip():
    restore = "Return the cab mounting bracket from aluminium to the original steel design."
    result = _semantic_pair(query_text=REVERT_TO_STEEL, candidate_text=restore, cosine=0.9, reversal_detection=True)
    assert result.category == "potential_duplicate"


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
