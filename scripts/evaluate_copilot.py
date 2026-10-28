"""Evaluate the knowledge copilot against data/vave_module2_retrieval_eval_set.json. Read-only.

Usage (from the repository root, with the backend virtualenv, after scripts/ingest_corpus.py):

    HF_HUB_OFFLINE=1 backend/.venv/bin/python scripts/evaluate_copilot.py data/vave_module2_retrieval_eval_set.json out.json

Every rule below was fixed before the first run.

Scoring
- Anchor match (``anchor_matches``): a retrieved passage satisfies an expected anchor (document, section S, page P)
  when its document number ends with the expected one, its page is P, and its section is S or lies under S
  (3.1 and 3.1.2 satisfy an anchor of 3). Anchors name the section a reader is sent to, not the leaf, so a
  parent-level anchor is satisfied by its subsections on that page. The reverse does not hold: a chunk of
  section 3 does not satisfy an anchor of 3.1.
- Multi-hop anchors are written "3.1 and 6" / "3 and 5" and pair in order with expected_docs.
- recall@k (answerable): the query is a hit at k when every one of its anchors is satisfied by some passage in the
  top k. For single anchors that is the usual definition.
- Multi-hop by type, as specified: a hit at k when every expected DOCUMENT appears in the top k. The stricter
  every-anchor figure is reported next to it.
- MRR (answerable): 1 / rank of the first passage that satisfies any anchor of the query; 0 if none in the top k.
- Citation accuracy: the answer's cited passage (the top passage for an extractive answer) has the right document
  AND the right page for one of the query's anchors. Section is not required. Reported over the answerable
  queries that were answered, and over all answerable queries (an abstention counts as not correct).
- Abstention follows the system rule exactly: no answer when nothing is retrieved or when the top passage's cosine
  is below copilot_citation_threshold. Each query is also run through compose_answer at the chosen threshold, and
  the script stops if the two disagree.

Retrieval is top 5 distinct (document, section, page) places, as the copilot does with copilot_distinct_sections on.
The same queries are also retrieved without de-duplication, to count how many top-5 lists change.

Split (deterministic, by id, stratified by type): within each type, queries sorted by id alternate between
calibration and held-out, starting with calibration. A type with an odd count gives its extra query to
calibration and held-out in turn, in the order the odd types first appear (near_miss: calibration,
cross_register: held-out, vague: calibration). Result: answerable 17 / 17, must-abstain 7 / 6.

Threshold selection, on the calibration half only. Candidates are 0, the midpoints between consecutive distinct
calibration top-1 cosines, and a value above the largest. Two thresholds are chosen; held-out figures are read
off at both and never used to choose:
- primary: the highest balanced accuracy, mean of (answerable queries answered) and (must-abstain queries
  refused), ties to the higher threshold;
- the lowest candidate with no false answer on the calibration half.

Sensitivity (not the headline): multi_hop queries are also retrieved at k = 10 distinct places, and scored by the
same all-documents and all-anchors rules, to see whether k = 5 measures the window rather than the retriever.

With --threshold T the queries are also scored at T (the deployed setting), and every query is checked against
compose_answer at T. A trade-off table reports, on a fixed grid of thresholds, how many answerable queries lose
their answer and how many must-abstain queries get a false answer, per half.
"""

from __future__ import annotations

import argparse
import json
import statistics
import sys
from collections import defaultdict
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "backend"))

from app.api.v1.router import _runtime  # noqa: E402
from app.db.session import get_session_factory  # noqa: E402
from app.models import User  # noqa: E402
from app.services.copilot.service import compose_answer, retrieve  # noqa: E402
from sqlalchemy import select  # noqa: E402

K = 5
# Sensitivity only: five distinct sections may be too narrow a window for a query that needs two documents.
MULTI_HOP_SENSITIVITY_K = 10
ANSWERABLE_TYPES = ("single_hop", "multi_hop", "near_miss", "cross_register")


def not_retrieved(value, fmt: str = "{:.3f}") -> str:
    """A missing value means nothing was retrieved; it is never printed as 0."""
    return "not retrieved" if value is None else fmt.format(value)


def anchors(item: dict) -> list[dict]:
    if not item["answerable"]:
        return []
    sections = [part.strip() for part in str(item["expected_section"]).split(" and ")]
    pages = [int(part) for part in str(item["expected_page"]).split(" and ")]
    docs = item["expected_docs"]
    if not (len(docs) == len(sections) == len(pages)):
        raise SystemExit(f"{item['id']}: {len(docs)} documents, {len(sections)} sections, {len(pages)} pages")
    return [{"doc": doc, "section": section, "page": page} for doc, section, page in zip(docs, sections, pages, strict=True)]


def doc_matches(hit: dict, doc: str) -> bool:
    return bool(hit.get("document_number")) and hit["document_number"].endswith(doc)


def section_within(retrieved: str | None, expected: str) -> bool:
    """The retrieved section is the expected one or one of its subsections: 3.1 is within 3, 3 is not within 3.1."""
    return retrieved is not None and (retrieved == expected or retrieved.startswith(expected + "."))


def anchor_matches(hit: dict, anchor: dict) -> bool:
    return doc_matches(hit, anchor["doc"]) and hit.get("page_number") == anchor["page"] and section_within(hit.get("section_number"), anchor["section"])


def _check_rules() -> None:
    hit = {"document_number": "CVOEM/VAVE/TD-BM/2024/014", "page_number": 6, "section_number": "3.1"}
    assert anchor_matches(hit, {"doc": "TD-BM/2024/014", "section": "3", "page": 6})  # parent anchor, leaf retrieved
    assert anchor_matches(hit, {"doc": "TD-BM/2024/014", "section": "3.1", "page": 6})
    assert not anchor_matches({**hit, "section_number": "3"}, {"doc": "TD-BM/2024/014", "section": "3.1", "page": 6})
    assert not anchor_matches({**hit, "section_number": "31"}, {"doc": "TD-BM/2024/014", "section": "3", "page": 6})
    assert not anchor_matches({**hit, "page_number": 7}, {"doc": "TD-BM/2024/014", "section": "3", "page": 6})
    assert not anchor_matches(hit, {"doc": "TD-BM/2024/015", "section": "3", "page": 6})


def split(items: list[dict]) -> dict[str, str]:
    by_type: dict[str, list[dict]] = defaultdict(list)
    for item in sorted(items, key=lambda entry: entry["id"]):
        by_type[item["type"]].append(item)
    assignment, odd_turn = {}, 0
    for kind in dict.fromkeys(item["type"] for item in sorted(items, key=lambda entry: entry["id"])):
        group = by_type[kind]
        start = 0
        if len(group) % 2:
            start, odd_turn = odd_turn % 2, odd_turn + 1
        for index, item in enumerate(group):
            assignment[item["id"]] = "calibration" if (index + start) % 2 == 0 else "held_out"
    return assignment


def candidates(scores: list[float]) -> list[float]:
    values = sorted(set(scores))
    mids = [round((a + b) / 2, 4) for a, b in zip(values, values[1:], strict=False)]
    return [0.0, *mids, round(values[-1] + 0.01, 4)]


def abstains(record: dict, threshold: float | None) -> bool:
    top = record["top_score"]
    return top is None or (threshold is not None and top < threshold)


def rates(records: list[dict], threshold: float | None) -> dict:
    answerable = [r for r in records if r["answerable"]]
    refuse = [r for r in records if not r["answerable"]]
    answered = [r for r in answerable if not abstains(r, threshold)]
    false_answers = [r for r in refuse if not abstains(r, threshold)]
    return {
        "answerable_n": len(answerable),
        "answerable_answered": len(answered),
        "answerable_abstained": len(answerable) - len(answered),
        "citation_correct": sum(r["citation_correct"] for r in answered),
        "must_abstain_n": len(refuse),
        "must_abstain_refused": len(refuse) - len(false_answers),
        "false_answers": len(false_answers),
        "false_answer_ids": [r["id"] for r in false_answers],
    }


def balanced(stats: dict) -> float:
    return 0.5 * stats["answerable_answered"] / stats["answerable_n"] + 0.5 * stats["must_abstain_refused"] / stats["must_abstain_n"]


def retrieval_summary(records: list[dict]) -> dict:
    answerable = [r for r in records if r["answerable"]]
    n = len(answerable)
    return {
        "n": n,
        **{f"recall@{k}": sum(r["anchor_hit_rank"] is not None and r["anchor_hit_rank"] <= k for r in answerable) for k in (1, 3, 5)},
        "mrr": statistics.fmean(1 / r["first_relevant_rank"] if r["first_relevant_rank"] else 0.0 for r in answerable) if n else None,
    }


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("evalset", type=Path)
    parser.add_argument("out", type=Path)
    parser.add_argument("--threshold", type=float, default=None, help="also score at this threshold (the deployed value)")
    args = parser.parse_args()
    _check_rules()
    items = json.loads(args.evalset.read_text(encoding="utf-8"))
    assignment = split(items)

    db = get_session_factory()()
    config, chat, embedder, llm_status, warning = _runtime(db)
    user = db.scalar(select(User).where(User.email == "engineer@vave.local"))
    print(f"embedding={embedder.model} chat={getattr(chat, 'name', None)} llm_status={llm_status}")
    if warning:
        print(f"runtime warning: {warning}")

    records = []
    for item in items:
        hits = retrieve(db, user=user, question=item["query"], embedder=embedder, top_k=K, distinct_sections=True)
        windows = retrieve(db, user=user, question=item["query"], embedder=embedder, top_k=K, distinct_sections=False)
        expected = anchors(item)
        # Rank at which every anchor is satisfied (the deepest of the per-anchor first ranks).
        per_anchor = [next((h["rank"] for h in hits if anchor_matches(h, a)), None) for a in expected]
        anchor_hit_rank = max(per_anchor) if expected and None not in per_anchor else None
        per_doc = [next((h["rank"] for h in hits if doc_matches(h, doc)), None) for doc in dict.fromkeys(item["expected_docs"])]
        doc_hit_rank = max(per_doc) if per_doc and None not in per_doc else None
        first_relevant = next((h["rank"] for h in hits if any(anchor_matches(h, a) for a in expected)), None)
        top = hits[0] if hits else None
        citation_correct = bool(top) and any(doc_matches(top, a["doc"]) and top.get("page_number") == a["page"] for a in expected)
        records.append(
            {
                "id": item["id"],
                "type": item["type"],
                "answerable": item["answerable"],
                "half": assignment[item["id"]],
                "query": item["query"],
                "expected": expected,
                "top_score": top["cosine_similarity"] if top else None,
                "anchor_hit_rank": anchor_hit_rank,
                "doc_hit_rank": doc_hit_rank,
                "first_relevant_rank": first_relevant,
                "citation_correct": citation_correct,
                "top5_changed_by_dedup": [h["chunk_id"] for h in hits] != [h["chunk_id"] for h in windows],
                "hits": [
                    {k: h[k] for k in ("rank", "cosine_similarity", "document_number", "section_number", "section_heading", "page_number")}
                    for h in hits
                ],
            }
        )

    calibration = [r for r in records if r["half"] == "calibration"]
    held_out = [r for r in records if r["half"] == "held_out"]
    sweep = []
    for threshold in candidates([r["top_score"] for r in calibration if r["top_score"] is not None]):
        stats = rates(calibration, threshold)
        sweep.append({"threshold": threshold, "balanced_accuracy": balanced(stats), **stats})
    primary = max(sweep, key=lambda e: (e["balanced_accuracy"], e["threshold"]))["threshold"]
    safe = next(e["threshold"] for e in sweep if e["false_answers"] == 0)

    # The replay must agree with the copilot itself: run every query through compose_answer at the scored threshold.
    scored = args.threshold if args.threshold is not None else primary
    for record, item in zip(records, items, strict=True):
        hits = retrieve(db, user=user, question=item["query"], embedder=embedder, top_k=K, distinct_sections=True)
        answer = compose_answer(item["query"], hits, threshold=scored, chat_provider=chat, llm_status=llm_status, embedder=embedder, timeout=30)
        record["mode_at_scored_threshold"] = answer.mode
        if (answer.mode == "abstained") != abstains(record, scored):
            raise SystemExit(f"{record['id']}: compose_answer and the replay disagree")
        record["answer_at_scored_threshold"] = answer.text
    db.rollback()
    db.close()

    report = {
        "config": {"embedding": embedder.model, "chat": getattr(chat, "name", None), "llm_status": llm_status, "k": K, "distinct_sections": True},
        "top5_changed_by_dedup": sum(r["top5_changed_by_dedup"] for r in records),
        "thresholds": {"primary_max_balanced_accuracy": primary, "lowest_with_no_calibration_false_answer": safe},
        "calibration_sweep": sweep,
        "records": records,
    }
    grid = sorted({round(0.20 + 0.05 * step, 2) for step in range(13)} | ({scored} if scored is not None else set()))
    report["tradeoff"] = [
        {"threshold": threshold, **{half: rates(rows, threshold) for half, rows in (("calibration", calibration), ("held_out", held_out), ("all", records))}}
        for threshold in grid
    ]
    report["top1_cosine"] = {
        group: sorted(r["top_score"] for r in records if r["answerable"] == flag and r["top_score"] is not None)
        for group, flag in (("answerable", True), ("must_abstain", False))
    }
    report["thresholds"]["scored"] = scored
    for name, threshold in (("primary", primary), ("no_false_answer", safe), ("scored", scored)):
        report[name] = {half: rates(rows, threshold) for half, rows in (("calibration", calibration), ("held_out", held_out))}
    report["multi_hop_sensitivity"] = []
    db = get_session_factory()()
    user = db.scalar(select(User).where(User.email == "engineer@vave.local"))
    for record, item in zip(records, items, strict=True):
        if item["type"] != "multi_hop":
            continue
        wide = retrieve(db, user=user, question=item["query"], embedder=embedder, top_k=MULTI_HOP_SENSITIVITY_K, distinct_sections=True)
        expected = anchors(item)
        per_anchor = [next((h["rank"] for h in wide if anchor_matches(h, a)), None) for a in expected]
        per_doc = [next((h["rank"] for h in wide if doc_matches(h, doc)), None) for doc in dict.fromkeys(item["expected_docs"])]
        report["multi_hop_sensitivity"].append(
            {
                "id": item["id"],
                "half": record["half"],
                "k": MULTI_HOP_SENSITIVITY_K,
                "anchor_ranks": per_anchor,
                "doc_ranks": per_doc,
                "all_anchors_rank": max(per_anchor) if None not in per_anchor else None,
                "all_docs_rank": max(per_doc) if None not in per_doc else None,
            }
        )
    db.rollback()
    db.close()
    report["retrieval"] = {
        "calibration": retrieval_summary(calibration),
        "held_out": retrieval_summary(held_out),
        "all_answerable": retrieval_summary(records),
    }
    args.out.write_text(json.dumps(report, indent=1, default=str), encoding="utf-8")
    print(f"wrote {args.out}")


if __name__ == "__main__":
    main()
