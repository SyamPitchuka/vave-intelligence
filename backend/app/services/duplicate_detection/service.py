"""Duplicate analysis. The language model may recommend; it never changes historical rows."""

from __future__ import annotations

import json
import re
import uuid
from datetime import UTC, datetime
from decimal import Decimal
from typing import Any

from rapidfuzz import fuzz
from sqlalchemy import select
from sqlalchemy.orm import Session, selectinload

from app.domain.constants import ANALYSIS_CATEGORIES
from app.models import (
    DuplicateAnalysisCandidate,
    DuplicateAnalysisRun,
    Idea,
    IdeaVehicleApplicability,
    ReviewDecision,
)
from app.services.duplicate_detection.classifier import classify_pair, headline_category
from app.services.embeddings.index import (
    comparison_text,
    idea_embedding_text,
    search_similar,
    upsert_embedding,
)
from app.services.llm_providers.fallback import FallbackChatProvider
from app.services.text import normalize_text

_SYSTEM = """You compare two engineering VAVE ideas and return JSON only.
Keys:
- category: potential_duplicate | similar_but_distinct | no_strong_match | insufficient_evidence
- similarities: array of short strings grounded in the supplied text
- differences: array of short strings grounded in the supplied text
- explanation: one short paragraph
- sufficient_evidence: boolean

Rules:
- Do not call ideas duplicates only because they share a component, department, or benefit.
- potential_duplicate requires the same technical action and the same mechanism of benefit.
- If the text is not enough, use insufficient_evidence and sufficient_evidence false.
- Use only the supplied fields. Do not invent rejection reasons, departments, savings, dates, or test results.
- Do not instruct anyone to modify official records.
"""


def analyze_submission(
    db: Session,
    submission: Idea,
    *,
    user_id: uuid.UUID | None,
    ai_config: dict[str, Any],
    chat_provider,
    embedder,
    llm_status: str,
    warning: str | None,
) -> DuplicateAnalysisRun:
    if submission.lifecycle_status == "draft":
        submission.lifecycle_status = "submitted"
    model_name = embedder.model
    upsert_embedding(
        db,
        entity_type="idea",
        entity_id=submission.id,
        model_name=model_name,
        text=idea_embedding_text(submission),
        embedder=embedder,
    )
    db.flush()
    ranked = rank_historical(db, submission, embedder=embedder, limit=int(ai_config["retrieval_top_k"]))
    strong = [item for item in ranked if item["exact"] or item["fuzzy"] >= 40 or (item["cosine"] or 0) >= float(ai_config["cosine_retrieve_threshold"])]
    chosen = strong[: int(ai_config["retrieval_top_k"])] or ranked[:5]
    use_llm = not isinstance(chat_provider, FallbackChatProvider) and llm_status == "pending"
    compared = 0
    candidates: list[DuplicateAnalysisCandidate] = []
    for index, item in enumerate(chosen, start=1):
        historical = item["idea"]
        heuristic = classify_pair(
            query_component=submission.component,
            query_text=_pair_text(submission),
            candidate_component=historical.component,
            candidate_text=_pair_text(historical),
            fuzzy_score=item["fuzzy"],
            exact=item["exact"],
            fuzzy_strong_threshold=float(ai_config["fuzzy_strong_threshold"]),
        )
        llm_category = None
        similarities = list(heuristic.similarities)
        differences = list(heuristic.differences)
        explanation = heuristic.explanation
        disagreement = False
        if use_llm and compared < 5 and (item["exact"] or item["fuzzy"] >= 45 or (item["cosine"] or 0) >= float(ai_config["cosine_retrieve_threshold"])):
            compared += 1
            try:
                parsed = _ask_model(chat_provider, submission, historical, int(ai_config["comparison_timeout_seconds"]))
                llm_category = parsed["category"]
                similarities = _as_list(parsed.get("similarities")) or similarities
                differences = _as_list(parsed.get("differences")) or differences
                if parsed.get("explanation"):
                    explanation = str(parsed["explanation"])
                if parsed.get("sufficient_evidence") is False:
                    llm_category = "insufficient_evidence"
                llm_status = "completed"
            except Exception as exc:  # noqa: BLE001 — the engineer must see the provider failure
                llm_status = "failed"
                warning = ((warning + " ") if warning else "") + f"Language model comparison failed: {exc}"
                use_llm = False
        category = _final_category(heuristic.category, llm_category, exact=item["exact"])
        if llm_category and llm_category != heuristic.category:
            disagreement = True
            if not item["exact"]:
                category = "insufficient_evidence"
                explanation = (
                    "The deterministic comparison and the language model disagreed, so the result is "
                    "insufficient evidence rather than an automatic duplicate call. "
                    + explanation
                )
        note = _stored_rejection_note(historical)
        candidates.append(
            DuplicateAnalysisCandidate(
                historical_idea_id=historical.id,
                rank=index,
                cosine_similarity=None if item["cosine"] is None else Decimal(f"{item['cosine']:.6f}"),
                fuzzy_score=Decimal(f"{item['fuzzy']:.2f}"),
                exact_match=item["exact"],
                category=category,
                heuristic_category=heuristic.category,
                llm_category=llm_category,
                disagreement=disagreement,
                explanation=explanation,
                similarities=similarities,
                differences=differences,
                evidence={
                    "exact_normalized_match": item["exact"],
                    "fuzzy_score": item["fuzzy"],
                    "cosine_similarity": item["cosine"],
                    "token_jaccard": heuristic.token_jaccard,
                    "stored_record_note": note,
                    "signals_are_not_probabilities": True,
                    "thresholds_note": "Thresholds are configuration, not a validated production accuracy claim.",
                },
            )
        )
    outcome = headline_category([item.category for item in candidates])
    if not candidates:
        outcome = "no_strong_match"
    run = DuplicateAnalysisRun(
        submission_id=submission.id,
        status="completed",
        outcome_category=outcome,
        provider=getattr(chat_provider, "name", ai_config["mode"]),
        chat_model=getattr(chat_provider, "model", None),
        embedding_model=model_name,
        retrieval_k=int(ai_config["retrieval_top_k"]),
        llm_status=llm_status,
        warning=warning,
        config={
            "mode": ai_config["mode"],
            "fuzzy_strong_threshold": ai_config["fuzzy_strong_threshold"],
            "cosine_retrieve_threshold": ai_config["cosine_retrieve_threshold"],
            "embedding_provider": ai_config["embedding_provider"],
        },
        created_by=user_id,
        completed_at=datetime.now(UTC),
    )
    run.candidates = candidates
    db.add(run)
    db.flush()
    return run


def rank_historical(db: Session, submission: Idea, *, embedder, limit: int) -> list[dict[str, Any]]:
    is_candidate = (Idea.origin == "historical", Idea.id != submission.id)
    historical = db.scalars(
        select(Idea)
        .where(*is_candidate)
        .options(
            selectinload(Idea.applicability).selectinload(IdeaVehicleApplicability.vehicle_family),
            selectinload(Idea.belonged_department),
            selectinload(Idea.rejected_department),
        )
    ).all()
    cosine_by_id: dict[uuid.UUID, float] = {}
    try:
        vector = embedder.embed(idea_embedding_text(submission))
        # Restrict to historical ideas so stored submissions cannot take the top slots.
        for entity_id, score in search_similar(
            db,
            vector=vector,
            model_name=embedder.model,
            entity_type="idea",
            limit=max(limit, 20),
            entity_ids=select(Idea.id).where(*is_candidate),
        ):
            cosine_by_id[entity_id] = score
    except Exception:
        cosine_by_id = {}
    query_norm = normalize_text(submission.description)
    query_blob = comparison_text(submission)
    ranked: list[dict[str, Any]] = []
    seen: set[uuid.UUID] = set()
    for idea in historical:
        if idea.id in seen:
            continue
        seen.add(idea.id)
        candidate_norm = idea.normalized_text or normalize_text(idea.description)
        exact = bool(query_norm and candidate_norm and query_norm == candidate_norm and len(query_norm) >= 20)
        fuzzy = float(fuzz.token_set_ratio(query_blob, comparison_text(idea)))
        ranked.append({"idea": idea, "exact": exact, "fuzzy": fuzzy, "cosine": cosine_by_id.get(idea.id)})
    ranked.sort(key=lambda item: (item["exact"], item["fuzzy"], item["cosine"] or 0), reverse=True)
    return ranked


def latest_decision(db: Session, run_id: uuid.UUID) -> ReviewDecision | None:
    return db.scalar(
        select(ReviewDecision).where(ReviewDecision.run_id == run_id).order_by(ReviewDecision.created_at.desc())
    )


def _pair_text(idea: Idea) -> str:
    parts = [idea.description or "", idea.current_design or "", idea.proposed_change or "", idea.expected_benefit or ""]
    return "\n".join(part for part in parts if part)


def _final_category(heuristic: str, llm_category: str | None, *, exact: bool) -> str:
    if exact:
        return "potential_duplicate"
    if llm_category in ANALYSIS_CATEGORIES:
        return llm_category
    return heuristic


def _ask_model(provider, submission: Idea, historical: Idea, timeout: int) -> dict[str, Any]:
    payload = {
        "new_idea": _public_fields(submission),
        "historical_idea": _public_fields(historical),
    }
    raw = provider.complete(
        [
            {"role": "system", "content": _SYSTEM},
            {"role": "user", "content": json.dumps(payload)},
        ],
        timeout=timeout,
    )
    return _parse_model_json(raw)


def _public_fields(idea: Idea) -> dict[str, Any]:
    return {
        "idea_code": idea.idea_code,
        "component": idea.component,
        "description": idea.description,
        "current_design": idea.current_design,
        "proposed_change": idea.proposed_change,
        "engineering_rationale": idea.engineering_rationale,
        "expected_benefit": idea.expected_benefit,
        "constraints": idea.constraints,
        "idea_type": idea.idea_type,
        "vehicle_details": idea.applicable_vehicle_details,
        "stored_stage_status": idea.stage_status,
        "stored_rejection_category": idea.rejection_category,
        "stored_rejection_reason": idea.rejection_reason,
        "stored_is_rejected": idea.is_rejected,
    }


def _parse_model_json(raw: str) -> dict[str, Any]:
    text = raw.strip()
    if text.startswith("```"):
        text = re.sub(r"^```(?:json)?", "", text).strip()
        text = re.sub(r"```$", "", text).strip()
    start = text.find("{")
    end = text.rfind("}")
    if start < 0 or end < start:
        raise ValueError("The model did not return JSON.")
    data = json.loads(text[start : end + 1])
    if data.get("category") not in ANALYSIS_CATEGORIES:
        raise ValueError("The model returned a category outside the allowed set.")
    return data


def _as_list(value: Any) -> list[str]:
    if not isinstance(value, list):
        return []
    return [str(item) for item in value[:8]]


def _stored_rejection_note(idea: Idea) -> str:
    if not idea.is_rejected:
        return (
            "No rejection category is stored on this historical record. "
            "Under the current dataset rule it is active / not rejected."
        )
    parts = [f"Stored rejection category: {idea.rejection_category}."]
    if idea.rejection_reason:
        parts.append(f"Stored rejection reason: {idea.rejection_reason}.")
    else:
        parts.append("No rejection reason is stored.")
    if idea.rejected_department is not None:
        parts.append(f"Stored rejected department: {idea.rejected_department.name}.")
    else:
        parts.append("No rejected department is stored.")
    parts.append(f"Stored stage status: {idea.stage_status or 'not stored'}.")
    return " ".join(parts)
