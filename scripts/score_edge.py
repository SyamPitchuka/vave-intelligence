"""Score the edge-case duplicate workbook against the live duplicate pipeline, by case type. Read-only.

Usage (from the repository root, with the backend virtualenv):

    HF_HUB_OFFLINE=1 backend/.venv/bin/python scripts/score_edge.py data/vave_duplicate_edge_cases.xlsx out.json

The workbook's Ideas sheet is imported as historical records inside one transaction (preview, commit and
re-index, as the import endpoints do), each TestQueries row is analysed in a savepoint, and everything is
rolled back at the end, so the database is left as it was. Do not import the Ideas sheet beforehand: the
historical records would then appear twice.

Each LabelledPairs row is scored end to end (the category the pipeline gave that candidate; a candidate it did
not show counts as not a duplicate) and classifier only (classify_pair on the pair, whatever retrieval did).
A `duplicate` pair is correct only when called Potential Duplicate. A `similar_but_distinct` or
`related_not_duplicate` pair is correct whenever it is not called Potential Duplicate, as the workbook's Cover
sheet specifies. Results are reported per Case_Type; with two or three pairs per type there is no overall figure.

Options:

    --disable FLAG    run with one classifier rule off (see CLASSIFIER_FLAGS); repeat to turn off more than one
"""

from __future__ import annotations

import argparse
import json
import sys
import tempfile
from collections import defaultdict
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

import evaluate_hard_set as hard_set  # noqa: E402  (also puts backend/ on sys.path)
import numpy as np  # noqa: E402
from app.api.v1.router import _reindex_ids, _runtime  # noqa: E402
from app.db.session import get_session_factory  # noqa: E402
from app.models import EmbeddingRecord, Idea, ImportChange, User  # noqa: E402
from app.services.duplicate_detection.classifier import (  # noqa: E402
    CLASSIFIER_FLAGS,
    change_types,
    classifier_flags,
    classify_pair,
    components_match,
)
from app.services.duplicate_detection.service import analyze_submission, pair_inputs, rank_historical  # noqa: E402
from app.services.embeddings.index import idea_embedding_text  # noqa: E402
from app.services.ideas.service import create_submission  # noqa: E402
from app.services.imports.mapping import suggest_mapping  # noqa: E402
from app.services.imports.service import build_preview, commit_batch  # noqa: E402
from sqlalchemy import select  # noqa: E402
from sqlalchemy.exc import OperationalError  # noqa: E402

NEGATIVE_LABELS = {"similar_but_distinct", "related_not_duplicate"}


def correct(label: str, category: str) -> bool:
    if label == "duplicate":
        return category == "potential_duplicate"
    if label in NEGATIVE_LABELS:
        return category != "potential_duplicate"
    raise ValueError(f"Unknown label {label!r}")


def load_historical(db, content: bytes, filename: str, admin: User) -> list[str]:
    with tempfile.TemporaryDirectory() as storage:
        batch = build_preview(
            db, content=content, filename=filename, sheet_name="Ideas", mapping_override=None,
            merge_strategy="reject_conflicts", is_synthetic=True, allow_partial=False, user_id=admin.id,
            storage_dir=Path(storage),
        )
        if batch.error_count:
            raise SystemExit(f"The Ideas sheet has {batch.error_count} error rows; nothing was scored.")
        batch = commit_batch(db, batch.id, confirm=True, user_id=admin.id)
    ids = list(db.scalars(select(ImportChange.idea_id).where(ImportChange.batch_id == batch.id)).all())
    _reindex_ids(db, ids)
    db.flush()
    return [idea.idea_code for idea in db.scalars(select(Idea).where(Idea.id.in_(ids))).all()]


def score(db, args, content: bytes, disabled: list[str]) -> dict:
    queries = hard_set.sheet(content, "TestQueries")
    pairs = hard_set.sheet(content, "LabelledPairs")
    mapping = suggest_mapping(list(queries[0].keys()))
    config, chat, embedder, llm_status, warning = _runtime(db)
    for flag in disabled:
        config = {**config, flag: False}
    flags = classifier_flags(config)
    admin = db.scalar(select(User).where(User.email == "admin@vave.local"))
    loaded = load_historical(db, content, args.workbook.name, admin)
    historical = {idea.idea_code: idea for idea in db.scalars(select(Idea).where(Idea.origin == "historical")).all()}
    vectors = {
        row.entity_id: np.asarray(row.embedding, dtype=float)
        for row in db.scalars(
            select(EmbeddingRecord).where(EmbeddingRecord.entity_type == "idea", EmbeddingRecord.model_name == embedder.model)
        ).all()
    }
    code_of = {idea.id: code for code, idea in historical.items()}
    labelled: dict[str, list[dict]] = defaultdict(list)
    for pair in pairs:
        labelled[str(pair["Query_ID"]).strip()].append(pair)
    print(f"embedding={embedder.model} llm_status={llm_status} historical={len(historical)} (loaded {len(loaded)}) flags={flags}")

    records = []
    for row in queries:
        payload = hard_set.query_payload(row, mapping)
        savepoint = db.begin_nested()
        try:
            submission = create_submission(db, payload, admin.id, submit=True)
            run = analyze_submission(
                db, submission, user_id=admin.id, ai_config=config, chat_provider=chat,
                embedder=embedder, llm_status=llm_status, warning=warning,
            )
            shown = {c.historical_idea_id: c for c in run.candidates}
            retrieval = rank_historical(db, submission, embedder=embedder, limit=int(config["retrieval_top_k"]))
            ranked = {item["idea"].id: item for item in retrieval}
            position = {item["idea"].id: number for number, item in enumerate(retrieval, start=1)}
            query_vector = np.asarray(embedder.embed(idea_embedding_text(submission)), dtype=float)
            other_duplicates = [
                code_of.get(c.historical_idea_id) for c in sorted(run.candidates, key=lambda c: c.rank)
                if c.category == "potential_duplicate"
            ]
            for pair in labelled.get(payload["idea_code"], []):
                candidate = historical[str(pair["Candidate_ID"]).strip()]
                item = ranked[candidate.id]
                inputs = pair_inputs(submission, candidate, item, config)
                direct_cosine = hard_set.cosine(query_vector, vectors[candidate.id])
                heuristic = classify_pair(
                    **inputs, cosine=direct_cosine, semantic_duplicate_threshold=config.get("semantic_duplicate_threshold")
                )
                hit = shown.get(candidate.id)
                label = str(pair["Label"]).strip()
                e2e = hit.category if hit else "not_shown"
                negation = flags.get("negation_detection", False)
                records.append({
                    "query": payload["idea_code"],
                    "candidate": candidate.idea_code,
                    "label": label,
                    "case_type": str(pair["Case_Type"]).strip(),
                    "e2e": e2e,
                    "classifier": heuristic.category,
                    "correct": correct(label, e2e),
                    "shown": hit is not None,
                    "rank": hit.rank if hit else None,
                    "retrieval_position": position[candidate.id],
                    "fuzzy_at_cutoff": retrieval[int(config["retrieval_top_k"]) - 1]["fuzzy"],
                    "cosine": direct_cosine,
                    "pipeline_cosine": item["cosine"],
                    "fuzzy": item["fuzzy"],
                    "jaccard": heuristic.token_jaccard,
                    "same_component": components_match(
                        submission.component, candidate.component, fuzzy=flags.get("component_fuzzy_match", False)
                    ),
                    "query_actions": sorted(change_types(inputs["query_text"], negation=negation)),
                    "candidate_actions": sorted(change_types(inputs["candidate_text"], negation=negation)),
                    "explanation": heuristic.explanation,
                    "differences": heuristic.differences,
                    "outcome": run.outcome_category,
                    "other_potential_duplicates": [code for code in other_duplicates if code != candidate.idea_code],
                })
        finally:
            savepoint.rollback()
    by_type: dict[str, dict] = {}
    for record in records:
        entry = by_type.setdefault(record["case_type"], {"label": record["label"], "pairs": 0, "correct": 0})
        entry["pairs"] += 1
        entry["correct"] += record["correct"]
    return {
        "config": {
            "semantic_duplicate_threshold": config.get("semantic_duplicate_threshold"),
            **flags,
            "embedding_model": embedder.model,
            "llm_status": llm_status,
            "retrieval_top_k": config["retrieval_top_k"],
            "cosine_retrieve_threshold": config["cosine_retrieve_threshold"],
            "fuzzy_strong_threshold": config["fuzzy_strong_threshold"],
            "historical": len(historical),
        },
        "by_case_type": by_type,
        "pairs": records,
    }


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("workbook", type=Path)
    parser.add_argument("out", type=Path)
    parser.add_argument("--disable", action="append", default=[], choices=CLASSIFIER_FLAGS)
    args = parser.parse_args()
    content = args.workbook.read_bytes()
    for attempt in range(1, 4):
        db = get_session_factory()()
        try:
            report = score(db, args, content, args.disable)
            break
        except OperationalError as exc:
            # The hosted database can drop the connection mid-run. Nothing is committed, so start again.
            print(f"connection lost (attempt {attempt}): {str(exc).splitlines()[0][:120]}")
            if attempt == 3:
                raise
        finally:
            try:
                db.rollback()
                db.close()
            except Exception:  # noqa: BLE001 — the connection may already be gone
                pass
    args.out.write_text(json.dumps(report, indent=1, default=str), encoding="utf-8")
    for case_type, entry in report["by_case_type"].items():
        print(f"{case_type:24} {entry['label']:22} {entry['correct']}/{entry['pairs']}")
    for r in report["pairs"]:
        print(
            f"{r['query']} {r['candidate']} {r['case_type']:22} {r['label']:22} -> {r['e2e']:22} "
            f"{'ok ' if r['correct'] else 'FAIL'} cos={r['cosine']:.3f} fuzzy={r['fuzzy']:.1f} "
            f"same={r['same_component']} pos={r['retrieval_position']} rank={r['rank']}"
        )
    print(f"wrote {args.out}")


if __name__ == "__main__":
    main()
