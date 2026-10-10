"""Evaluation against labelled cases. Metrics are omitted when labels are insufficient."""

from __future__ import annotations

import uuid
from datetime import UTC, datetime
from types import SimpleNamespace

from sqlalchemy import select
from sqlalchemy.orm import Session, selectinload

from app.models import (
    EvaluationCase,
    EvaluationDataset,
    EvaluationPrediction,
    EvaluationRun,
    Idea,
    IdeaVehicleApplicability,
)
from app.services.duplicate_detection.classifier import classify_pair
from app.services.duplicate_detection.service import rank_historical
from app.services.embeddings.index import comparison_text
from app.services.text import normalize_text, query_coverage

_MIN_NOTE = (
    "These figures describe the selected deterministic comparison on this labelled set. "
    "They are not a production accuracy claim."
)


def run_evaluation(
    db: Session,
    dataset_id: uuid.UUID,
    *,
    user_id: uuid.UUID | None,
    embedder,
    fuzzy_strong_threshold: float,
    cosine_retrieve_threshold: float,
    retrieval_k: int,
    provider: str,
    embedding_model: str,
) -> EvaluationRun:
    dataset = db.scalar(
        select(EvaluationDataset).options(selectinload(EvaluationDataset.cases)).where(EvaluationDataset.id == dataset_id)
    )
    if dataset is None:
        raise LookupError("Evaluation dataset was not found.")
    if not dataset.cases:
        raise ValueError("This dataset has no labelled cases, so metrics cannot be calculated.")
    run = EvaluationRun(
        dataset_id=dataset.id,
        provider=provider,
        embedding_model=embedding_model,
        config={
            "fuzzy_strong_threshold": fuzzy_strong_threshold,
            "cosine_retrieve_threshold": cosine_retrieve_threshold,
            "retrieval_k": retrieval_k,
        },
        status="completed",
        created_by=user_id,
        finished_at=datetime.now(UTC),
        notes=_MIN_NOTE,
    )
    db.add(run)
    db.flush()
    if dataset.dataset_type == "copilot":
        metrics, predictions = _copilot(db, dataset.cases, embedder)
    else:
        metrics, predictions = _duplicates(
            db,
            dataset.cases,
            embedder=embedder,
            fuzzy_strong_threshold=fuzzy_strong_threshold,
            retrieval_k=retrieval_k,
        )
    run.metrics = metrics
    for item in predictions:
        db.add(EvaluationPrediction(run_id=run.id, **item))
    db.flush()
    return run


def _duplicates(db: Session, cases: list[EvaluationCase], *, embedder, fuzzy_strong_threshold: float, retrieval_k: int):
    pairs = []
    retrieval_ranks = []
    predictions = []
    historical = {
        idea.idea_code: idea
        for idea in db.scalars(
            select(Idea)
            .where(Idea.origin == "historical")
            .options(
                selectinload(Idea.applicability).selectinload(IdeaVehicleApplicability.vehicle_family),
                selectinload(Idea.belonged_department),
                selectinload(Idea.rejected_department),
            )
        ).all()
    }
    for case in cases:
        candidate = historical.get(case.candidate_idea_code or "")
        if candidate is None:
            predictions.append(
                {"case_id": case.id, "predicted": None, "rank": None, "scores": {"error": "candidate idea is not in the database"}}
            )
            continue
        query = _query_namespace(case.query_text)
        ranked = rank_historical(db, query, embedder=embedder, limit=retrieval_k)
        codes = [item["idea"].idea_code for item in ranked]
        rank = None
        targets = list(case.retrieval_targets or [])
        if targets:
            found = [codes.index(target) + 1 for target in targets if target in codes]
            rank = min(found) if found else None
            retrieval_ranks.append(rank)
        match = next((item for item in ranked if item["idea"].id == candidate.id), None)
        fuzzy = match["fuzzy"] if match else 0.0
        exact = bool(match and match["exact"])
        heuristic = classify_pair(
            query_component=None,
            query_text=case.query_text,
            candidate_component=candidate.component,
            candidate_text=comparison_text(candidate),
            fuzzy_score=fuzzy,
            exact=exact,
            fuzzy_strong_threshold=fuzzy_strong_threshold,
        )
        pairs.append((case.ground_truth, heuristic.category))
        predictions.append(
            {
                "case_id": case.id,
                "predicted": heuristic.category,
                "rank": rank,
                "scores": {"fuzzy": fuzzy, "exact": exact, "cosine": None if not match else match["cosine"]},
            }
        )
    metrics = classification_metrics(pairs)
    metrics["retrieval"] = retrieval_metrics(retrieval_ranks, retrieval_k)
    metrics["warning"] = _MIN_NOTE
    return metrics, predictions


def _copilot(db: Session, cases: list[EvaluationCase], embedder):
    from app.models import DocumentChunk

    chunks = db.scalars(select(DocumentChunk).options(selectinload(DocumentChunk.document))).all()
    hits = 0
    predictions = []
    for case in cases:
        keyword = (case.expected_keyword or "").lower()
        best = None
        best_score = -1.0
        for chunk in chunks:
            score = query_coverage(case.query_text, chunk.content)
            if score > best_score:
                best_score = score
                best = chunk
        hit = bool(best and keyword and keyword in best.content.lower())
        hits += int(hit)
        predictions.append(
            {
                "case_id": case.id,
                "predicted": "cited" if hit else "missed",
                "rank": 1 if hit else None,
                "scores": {"lexical": best_score, "keyword": case.expected_keyword},
            }
        )
    if not cases:
        return {"available": False, "reason": "No labelled copilot cases."}, predictions
    return {
        "available": True,
        "metric": "citation_keyword_in_top_chunk",
        "citation_hit_rate": hits / len(cases),
        "support": len(cases),
        "warning": "This checks whether the expected excerpt was retrieved. It does not grade prose quality, and it is not a production accuracy claim.",
    }, predictions


def classification_metrics(pairs: list[tuple[str, str]]) -> dict:
    labelled = [pair for pair in pairs if pair[0] in {"duplicate", "similar_but_distinct", "unrelated"}]
    positives = [pair for pair in labelled if pair[0] == "duplicate"]
    if not labelled:
        return {"available": False, "reason": "No labelled duplicate cases are available, so precision and recall were not calculated."}
    tp = fp = fn = tn = abstain = 0
    for truth, predicted in labelled:
        truth_positive = truth == "duplicate"
        predicted_positive = predicted == "potential_duplicate"
        if predicted == "insufficient_evidence":
            abstain += 1
        if truth_positive and predicted_positive:
            tp += 1
        elif truth_positive:
            fn += 1
        elif predicted_positive:
            fp += 1
        else:
            tn += 1
    precision = tp / (tp + fp) if tp + fp else None
    recall = tp / (tp + fn) if positives else None
    f1 = None
    if precision is not None and recall is not None and precision + recall:
        f1 = 2 * precision * recall / (precision + recall)
    return {
        "available": True,
        "positive_class": "duplicate",
        "support": len(labelled),
        "positive_support": len(positives),
        "precision": precision,
        "recall": recall if positives else None,
        "f1": f1,
        "false_positive_rate": fp / (fp + tn) if fp + tn else None,
        "false_negative_rate": fn / (fn + tp) if fn + tp else None,
        "abstentions": abstain,
        "tp": tp,
        "fp": fp,
        "fn": fn,
        "tn": tn,
        "recall_note": None if positives else "Recall was not calculated because the labelled set has no duplicate cases.",
        "small_set": len(labelled) < 30,
    }


def retrieval_metrics(ranks: list[int | None], k: int) -> dict:
    if not ranks:
        return {"available": False, "reason": "No cases have a labelled retrieval target, so top-k success was not calculated."}
    hits = [rank for rank in ranks if rank is not None and rank <= k]
    mrr = sum((1 / rank) if rank else 0 for rank in ranks) / len(ranks)
    return {
        "available": True,
        "k": k,
        "support": len(ranks),
        "top_k_success": len(hits) / len(ranks),
        "mean_reciprocal_rank": mrr,
    }


def _query_namespace(text: str):
    return SimpleNamespace(
        id=uuid.uuid4(),
        component=None,
        description=text,
        current_design=None,
        proposed_change=None,
        engineering_rationale=None,
        expected_benefit=None,
        constraints=None,
        idea_type=None,
        applicable_vehicle_details=None,
        belonged_department=None,
        applicability=[],
        normalized_text=normalize_text(text),
        origin="submission",
        is_rejected=False,
        rejection_category=None,
        rejection_reason=None,
        rejected_department=None,
        stage_status=None,
        idea_code="QUERY",
    )
