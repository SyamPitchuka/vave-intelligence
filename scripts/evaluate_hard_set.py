"""Score the v2 duplicate evaluation workbook against the live duplicate pipeline. Read-only.

Usage (from the repository root, with the backend virtualenv, after importing the workbook's
Ideas sheet as historical records):

    HF_HUB_OFFLINE=1 backend/.venv/bin/python scripts/evaluate_hard_set.py data/vave_duplicate_eval_set_v2.xlsx out.json

Each TestQueries row is created as a submission and analysed with analyze_submission and the
active runtime, then rolled back, so nothing is stored. Every LabelledPairs row is scored twice:

- end to end: the category the pipeline gave that candidate; a candidate it did not show counts
  as not a duplicate
- classifier only: classify_pair on the pair, whatever retrieval did

Cosine is computed directly between the query and each candidate's stored vector, so it does not
depend on the vector search limit.
"""

from __future__ import annotations

import json
import statistics
import sys
from collections import Counter, defaultdict
from pathlib import Path

BACKEND = Path(__file__).resolve().parents[1] / "backend"
sys.path.insert(0, str(BACKEND))

import numpy as np  # noqa: E402
from app.api.v1.router import _runtime  # noqa: E402
from app.db.session import get_session_factory  # noqa: E402
from app.models import EmbeddingRecord, Idea, User  # noqa: E402
from app.services.duplicate_detection.classifier import classify_pair  # noqa: E402
from app.services.duplicate_detection.service import _pair_text, analyze_submission, rank_historical  # noqa: E402
from app.services.embeddings.index import idea_embedding_text  # noqa: E402
from app.services.evaluation_service import classification_metrics  # noqa: E402
from app.services.ideas.service import create_submission  # noqa: E402
from app.services.imports.mapping import VOLUME_FIELDS, suggest_mapping  # noqa: E402
from app.services.imports.reader import read_tabular  # noqa: E402
from sqlalchemy import select  # noqa: E402

CONTENT_FIELDS = (
    "component",
    "description",
    "current_design",
    "proposed_change",
    "engineering_rationale",
    "expected_benefit",
    "constraints",
    "idea_belonged_department",
    "idea_type",
    "applicable_vehicle_details",
    "saving_per_vehicle",
)
LABELS = ("duplicate", "similar_but_distinct", "unrelated")
DIFFICULTIES = ("easy", "medium", "hard")


def sheet(content: bytes, name: str) -> list[dict]:
    _selected, _sheets, _headers, rows = read_tabular(content, "eval.xlsx", name)
    return rows


def query_payload(row: dict, mapping: dict[str, str]) -> dict:
    mapped = {field: row.get(header) for header, field in mapping.items()}
    payload = {field: mapped.get(field) for field in CONTENT_FIELDS if mapped.get(field) not in (None, "")}
    payload["idea_code"] = str(mapped["idea_code"]).strip()
    payload["is_synthetic"] = True
    payload["vehicles"] = [
        {"family_code": code, "annual_volume": mapped[field]}
        for field, code in VOLUME_FIELDS.items()
        if mapped.get(field) not in (None, "", 0)
    ]
    return payload


def cosine(a: np.ndarray, b: np.ndarray) -> float:
    return float(a @ b / (np.linalg.norm(a) * np.linalg.norm(b)))


def summary(values: list[float]) -> dict:
    if not values:
        return {"n": 0}
    q = statistics.quantiles(values, n=4) if len(values) > 1 else [values[0]] * 3
    return {"n": len(values), "min": min(values), "p25": q[0], "median": q[1], "p75": q[2], "max": max(values), "mean": statistics.fmean(values)}


def main() -> None:
    workbook, out_path = Path(sys.argv[1]), Path(sys.argv[2])
    content = workbook.read_bytes()
    queries = sheet(content, "TestQueries")
    pairs = sheet(content, "LabelledPairs")
    mapping = suggest_mapping(list(queries[0].keys()))

    db = get_session_factory()()
    config, chat, embedder, llm_status, warning = _runtime(db)
    admin = db.scalar(select(User).where(User.email == "admin@vave.local"))
    historical = {idea.idea_code: idea for idea in db.scalars(select(Idea).where(Idea.origin == "historical")).all()}
    vectors = {
        row.entity_id: np.asarray(row.embedding, dtype=float)
        for row in db.scalars(
            select(EmbeddingRecord).where(EmbeddingRecord.entity_type == "idea", EmbeddingRecord.model_name == embedder.model)
        ).all()
    }
    labelled_by_query: dict[str, list[dict]] = defaultdict(list)
    for pair in pairs:
        labelled_by_query[str(pair["Query_ID"]).strip()].append(pair)
    missing = sorted({str(p["Candidate_ID"]).strip() for p in pairs} - set(historical))
    if missing:
        raise SystemExit(f"Labelled candidates are not historical records in the database: {missing[:10]}")
    print(f"embedding={embedder.model} chat={getattr(chat, 'name', None)} llm_status={llm_status} historical={len(historical)}")

    records = []
    query_info = []
    for number, row in enumerate(queries, start=1):
        payload = query_payload(row, mapping)
        code = payload["idea_code"]
        try:
            submission = create_submission(db, payload, admin.id, submit=True)
            run = analyze_submission(
                db, submission, user_id=admin.id, ai_config=config, chat_provider=chat,
                embedder=embedder, llm_status=llm_status, warning=warning,
            )
            shown = {c.historical_idea_id: c for c in run.candidates}
            ranked = {item["idea"].id: item for item in rank_historical(db, submission, embedder=embedder, limit=int(config["retrieval_top_k"]))}
            query_vector = np.asarray(embedder.embed(idea_embedding_text(submission)), dtype=float)
            query_info.append({"query": code, "outcome": run.outcome_category, "shown": len(run.candidates), "llm_status": run.llm_status})
            for pair in labelled_by_query.get(code, []):
                candidate = historical[str(pair["Candidate_ID"]).strip()]
                item = ranked[candidate.id]
                heuristic = classify_pair(
                    query_component=submission.component,
                    query_text=_pair_text(submission),
                    candidate_component=candidate.component,
                    candidate_text=_pair_text(candidate),
                    fuzzy_score=item["fuzzy"],
                    exact=item["exact"],
                    fuzzy_strong_threshold=float(config["fuzzy_strong_threshold"]),
                )
                hit = shown.get(candidate.id)
                records.append(
                    {
                        "query": code,
                        "candidate": candidate.idea_code,
                        "label": str(pair["Label"]).strip(),
                        "difficulty": str(pair["Difficulty"]).strip(),
                        "shown": hit is not None,
                        "rank": hit.rank if hit else None,
                        "e2e": hit.category if hit else "not_shown",
                        "classifier": heuristic.category,
                        "fuzzy": item["fuzzy"],
                        "exact": item["exact"],
                        "jaccard": heuristic.token_jaccard,
                        "cosine": cosine(query_vector, vectors[candidate.id]) if candidate.id in vectors else None,
                    }
                )
        finally:
            db.rollback()
        if number % 10 == 0:
            print(f"  {number}/{len(queries)} queries")
    db.close()

    def metrics(rows: list[dict], key: str) -> dict:
        return classification_metrics([(r["label"], r[key]) for r in rows])

    report = {
        "config": {
            "embedding_model": embedder.model,
            "chat": getattr(chat, "name", None),
            "llm_status": llm_status,
            "retrieval_top_k": config["retrieval_top_k"],
            "cosine_retrieve_threshold": config["cosine_retrieve_threshold"],
            "fuzzy_strong_threshold": config["fuzzy_strong_threshold"],
            "historical": len(historical),
            "queries": len(queries),
            "pairs": len(records),
        },
        "metrics": {
            mode: {
                "overall": metrics(records, mode),
                **{d: metrics([r for r in records if r["difficulty"] == d], mode) for d in DIFFICULTIES},
            }
            for mode in ("e2e", "classifier")
        },
        "confusion": {
            mode: {label: dict(Counter(r[mode] for r in records if r["label"] == label)) for label in LABELS}
            for mode in ("e2e", "classifier")
        },
        "confusion_by_difficulty": {
            d: {label: dict(Counter(r["e2e"] for r in records if r["label"] == label and r["difficulty"] == d)) for label in LABELS}
            for d in DIFFICULTIES
        },
        "counts": {label: dict(Counter(r["difficulty"] for r in records if r["label"] == label)) for label in LABELS},
        "distributions": {
            score: {
                label: {
                    "all": summary([r[score] for r in records if r["label"] == label and r[score] is not None]),
                    **{d: summary([r[score] for r in records if r["label"] == label and r["difficulty"] == d and r[score] is not None]) for d in DIFFICULTIES},
                }
                for label in LABELS
            }
            for score in ("cosine", "fuzzy", "jaccard")
        },
        "retrieval": {
            label: {"shown": sum(r["shown"] for r in records if r["label"] == label), "of": sum(r["label"] == label for r in records)}
            for label in LABELS
        },
        "queries": query_info,
        "pairs": records,
    }
    out_path.write_text(json.dumps(report, indent=1, default=str), encoding="utf-8")
    print(json.dumps({k: report[k] for k in ("config", "metrics", "confusion", "retrieval", "counts")}, indent=1, default=str))
    print(f"wrote {out_path}")


if __name__ == "__main__":
    main()
