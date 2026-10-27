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

Options:

    --semantic-threshold T     run the pipeline with semantic_duplicate_threshold = T
    --sweep START STOP STEP    also replay classify_pair with each semantic threshold in the range,
                               reusing the retrieval results; written to the report as "sweep"
    --split-families N         score the sweep separately on the first N component families (tuning)
                               and the rest (held out), and choose thresholds on the tuning families only
    --disable FLAG             run with one classifier rule off (any of CLASSIFIER_FLAGS in classifier.py);
                               repeat to turn off more than one

In the sweep, end-to-end verdicts use the cosine the pipeline itself saw (the vector search score),
and classifier-only verdicts use the directly computed cosine. Which candidates are shown does not
depend on the verdict, so it is the same at every threshold.
"""

from __future__ import annotations

import argparse
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
from app.services.duplicate_detection.classifier import (  # noqa: E402
    CLASSIFIER_FLAGS,
    classifier_flags,
    classify_pair,
    components_match,
)
from app.services.duplicate_detection.service import analyze_submission, pair_inputs, rank_historical  # noqa: E402
from app.services.embeddings.index import idea_embedding_text  # noqa: E402
from app.services.evaluation_service import classification_metrics  # noqa: E402
from app.services.ideas.service import create_submission  # noqa: E402
from app.services.imports.mapping import VOLUME_FIELDS, suggest_mapping  # noqa: E402
from app.services.imports.reader import read_tabular  # noqa: E402
from sqlalchemy import select  # noqa: E402
from sqlalchemy.exc import OperationalError  # noqa: E402

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


def sweep_thresholds(start: float, stop: float, step: float) -> list[float]:
    count = int(round((stop - start) / step))
    return [round(start + index * step, 4) for index in range(count + 1)]


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("workbook", type=Path)
    parser.add_argument("out", type=Path)
    parser.add_argument("--semantic-threshold", type=float, default=None)
    parser.add_argument("--sweep", type=float, nargs=3, metavar=("START", "STOP", "STEP"), default=None)
    parser.add_argument("--split-families", type=int, default=None, metavar="N")
    parser.add_argument("--disable", action="append", default=[], choices=CLASSIFIER_FLAGS)
    args = parser.parse_args()
    workbook, out_path = args.workbook, args.out
    content = workbook.read_bytes()
    queries = sheet(content, "TestQueries")
    pairs = sheet(content, "LabelledPairs")
    mapping = suggest_mapping(list(queries[0].keys()))

    db = get_session_factory()()
    config, chat, embedder, llm_status, warning = _runtime(db)
    if args.semantic_threshold is not None:
        config = {**config, "semantic_duplicate_threshold": args.semantic_threshold}
    for flag in args.disable:
        config = {**config, flag: False}

    def load_records(session):
        # Rollback expires loaded rows, so they must belong to the session in use.
        admin_user = session.scalar(select(User).where(User.email == "admin@vave.local"))
        ideas = {idea.idea_code: idea for idea in session.scalars(select(Idea).where(Idea.origin == "historical")).all()}
        return admin_user, ideas

    admin, historical = load_records(db)
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
    replay_inputs = []  # classify_pair arguments per record, kept out of the JSON report
    query_info = []
    def score_query(db, admin, historical, payload):
        code = payload["idea_code"]
        scored = []
        try:
            submission = create_submission(db, payload, admin.id, submit=True)
            run = analyze_submission(
                db, submission, user_id=admin.id, ai_config=config, chat_provider=chat,
                embedder=embedder, llm_status=llm_status, warning=warning,
            )
            shown = {c.historical_idea_id: c for c in run.candidates}
            retrieval = rank_historical(db, submission, embedder=embedder, limit=int(config["retrieval_top_k"]))
            ranked = {item["idea"].id: item for item in retrieval}
            # The rank the shown candidates had before verdict-based ordering: their retrieval (exact, fuzzy,
            # cosine) order. The shown set is the same either way.
            retrieval_rank = {
                idea_id: position
                for position, idea_id in enumerate((item["idea"].id for item in retrieval if item["idea"].id in shown), start=1)
            }
            query_vector = np.asarray(embedder.embed(idea_embedding_text(submission)), dtype=float)
            info = {"query": code, "outcome": run.outcome_category, "shown": len(run.candidates), "llm_status": run.llm_status}
            for pair in labelled_by_query.get(code, []):
                candidate = historical[str(pair["Candidate_ID"]).strip()]
                item = ranked[candidate.id]
                direct_cosine = cosine(query_vector, vectors[candidate.id]) if candidate.id in vectors else None
                inputs = pair_inputs(submission, candidate, item, config)
                heuristic = classify_pair(
                    **inputs,
                    cosine=direct_cosine,
                    semantic_duplicate_threshold=config.get("semantic_duplicate_threshold"),
                )
                hit = shown.get(candidate.id)
                scored.append(
                    ({
                        "query": code,
                        "candidate": candidate.idea_code,
                        "label": str(pair["Label"]).strip(),
                        "difficulty": str(pair["Difficulty"]).strip(),
                        "shown": hit is not None,
                        "rank": hit.rank if hit else None,
                        "retrieval_rank": retrieval_rank.get(candidate.id),
                        "e2e": hit.category if hit else "not_shown",
                        "classifier": heuristic.category,
                        "fuzzy": item["fuzzy"],
                        "exact": item["exact"],
                        "jaccard": heuristic.token_jaccard,
                        "cosine": direct_cosine,
                        "pipeline_cosine": item["cosine"],
                        "same_component": components_match(
                            submission.component, candidate.component, fuzzy=bool(config.get("component_fuzzy_match")),
                            subset_guard=bool(config.get("component_subset_guard")),
                        ),
                    }, inputs)
                )
        finally:
            db.rollback()
        return info, scored

    for number, row in enumerate(queries, start=1):
        payload = query_payload(row, mapping)
        for attempt in range(1, 4):
            try:
                info, scored = score_query(db, admin, historical, payload)
                break
            except OperationalError as exc:
                # The hosted database can drop the connection mid-run. Each query is rolled back, so it is
                # safe to retry on a fresh session.
                print(f"  {payload['idea_code']}: connection lost (attempt {attempt}): {str(exc).splitlines()[0][:120]}")
                try:
                    db.close()
                except Exception:  # noqa: BLE001 — the connection is already gone
                    pass
                if attempt == 3:
                    raise
                db = get_session_factory()()
                admin, historical = load_records(db)
        query_info.append(info)
        for record, inputs in scored:
            records.append(record)
            replay_inputs.append(inputs)
        if number % 10 == 0:
            print(f"  {number}/{len(queries)} queries")
    db.close()

    def metrics(rows: list[dict], key: str) -> dict:
        return classification_metrics([(r["label"], r[key]) for r in rows])

    def ranking(rows: list[dict], key: str) -> dict:
        """Where the labelled duplicate sits among the shown candidates. Unshown duplicates are counted apart."""
        ranks = [r[key] for r in rows if r["label"] == "duplicate" and r[key] is not None]
        unshown = sum(r["label"] == "duplicate" and r[key] is None for r in rows)
        if not ranks:
            return {"available": False, "unshown": unshown}
        return {
            "available": True,
            "duplicates_shown": len(ranks),
            "unshown": unshown,
            "mean_rank": statistics.fmean(ranks),
            "rank_at_1": sum(rank == 1 for rank in ranks) / len(ranks),
            "at_rank_1": sum(rank == 1 for rank in ranks),
            "worst_rank": max(ranks),
        }

    def summarise(rows: list[dict]) -> dict:
        return {
            mode: {
                "overall": metrics(rows, mode),
                **{d: metrics([r for r in rows if r["difficulty"] == d], mode) for d in DIFFICULTIES},
                "false_positives": dict(
                    Counter(r["label"] for r in rows if r[mode] == "potential_duplicate" and r["label"] != "duplicate")
                ),
                "pairs": len(rows),
                "duplicates": sum(r["label"] == "duplicate" for r in rows),
            }
            for mode in ("e2e", "classifier")
        }

    # A family is the query component. The three queries of a family paraphrase one idea, so splitting by query
    # would leak; the split is by family, in the order families first appear in TestQueries.
    family_order = list(dict.fromkeys(str(row.get("Component", "")).strip() for row in queries))
    family_of_query = {str(row["Idea_ID"]).strip(): str(row.get("Component", "")).strip() for row in queries}
    for record in records:
        record["family"] = family_of_query[record["query"]]
    tune_families = set(family_order[: args.split_families]) if args.split_families else None

    sweep = []
    if args.sweep:
        for threshold in sweep_thresholds(*args.sweep):
            rows = []
            for record, inputs in zip(records, replay_inputs, strict=True):
                e2e = (
                    classify_pair(**inputs, cosine=record["pipeline_cosine"], semantic_duplicate_threshold=threshold).category
                    if record["shown"]
                    else "not_shown"
                )
                classifier = classify_pair(**inputs, cosine=record["cosine"], semantic_duplicate_threshold=threshold).category
                rows.append({**record, "e2e": e2e, "classifier": classifier})
            entry = {"threshold": threshold, **summarise(rows)}
            if tune_families is not None:
                entry["tune"] = summarise([r for r in rows if r["family"] in tune_families])
                entry["holdout"] = summarise([r for r in rows if r["family"] not in tune_families])
            sweep.append(entry)

    split = None
    if tune_families is not None and sweep:
        # Chosen on the tuning families only: highest F1 (ties go to the higher, more conservative threshold),
        # and the lowest threshold with precision 1.0. Held-out numbers are read off afterwards, never compared.
        best = max(sweep, key=lambda e: (e["tune"]["e2e"]["overall"]["f1"] or 0, e["threshold"]))
        precise = [e for e in sweep if e["tune"]["e2e"]["overall"]["precision"] == 1.0]
        split = {
            "rule": "family = query component, in workbook order; first families tune, the rest are held out",
            "tune_families": sorted(tune_families, key=family_order.index),
            "holdout_families": [f for f in family_order if f not in tune_families],
            "max_f1_threshold": best["threshold"],
            "lowest_precision_1_threshold": precise[0]["threshold"] if precise else None,
        }

    report = {
        "config": {
            "semantic_duplicate_threshold": config.get("semantic_duplicate_threshold"),
            **classifier_flags(config),
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
        "ranking": {
            stage: {
                "overall": ranking(records, key),
                **{d: ranking([r for r in records if r["difficulty"] == d], key) for d in DIFFICULTIES},
            }
            for stage, key in (("retrieval_order", "retrieval_rank"), ("stored", "rank"))
        },
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
        "sweep": sweep,
        "split": split,
    }
    out_path.write_text(json.dumps(report, indent=1, default=str), encoding="utf-8")
    print(json.dumps({k: report[k] for k in ("config", "metrics", "confusion", "retrieval", "counts", "ranking")}, indent=1, default=str))
    print(f"wrote {out_path}")


if __name__ == "__main__":
    main()
