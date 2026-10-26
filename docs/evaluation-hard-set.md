# Evaluation results: v2 hard set

Run on 26 October 2026, on Windows 11 with Python 3.14, sentence-transformers 6.2.0, PyTorch 2.14.1 (CPU), and the hosted Neon development database.

Every number here comes from `data/vave_duplicate_eval_set_v2.xlsx`, a synthetic workbook generated for this project. Read [Limitations](#limitations) before relying on any of it.

## Summary

- **Overall, precision 1.0, recall 0.322, F1 0.487.** Of 90 labelled duplicates, 29 were called Potential Duplicate. There were no false positives.
- **Recall depends almost entirely on wording.** Easy duplicates: recall 0.967 (29 of 30). Medium and hard duplicates: recall 0 (0 of 60).
- **Retrieval is not the cause.** All 90 labelled duplicates were among the 15 candidates shown, 65 of them at rank 1. Scoring end to end and scoring the classifier alone give identical precision, recall, and F1.
- **One classifier rule causes 53 of the 61 misses.** A same-component pair with word overlap (Jaccard) below 0.28 is called Similar but Distinct, even when nothing shows a different mechanism. Paraphrased duplicates have Jaccard 0.10 – 0.34.
- **The embedding separates the labels better than the verdict does,** but not cleanly. Within each query, the labelled duplicate has the highest MiniLM cosine of its labelled candidates in 83 of 90 queries. Across queries, 28 similar-but-distinct pairs score above 0.80, where 77 of the 90 duplicates sit.

## Setup

### Database state

- **Removed first:** the 7 earlier test submissions, VAVE-NEW-00001 to -00007, with their 7 analysis runs, 105 candidate rows, 3 vehicle rows, and 14 embedding vectors. None had a review decision. The deletion was recorded in the audit log as `idea.delete_test_submissions`. This also removed analysis `a8555c14`, which [evaluation-results.md](evaluation-results.md#observed-examples) quotes; the figures quoted there are unchanged.
- **Remaining historical ideas:** 20, VAVE-SYN-001 to -020.
- **Imported:** the Ideas sheet, 91 rows, through the normal preview → commit import (batch `d56eccdc-83cf-4bf4-893d-36d99570e269`, marked synthetic, 0 errors). The 52 warnings were all department names outside the initial catalogue (Electrical, Powertrain, Axle, and similar), which are kept as given.
- **Evaluated against:** 111 historical ideas, each with an `all-MiniLM-L6-v2` vector.

The first commit attempt returned HTTP 500 and wrote nothing. `import_commit` crashed on every commit that changed rows; see [Defect found while loading](#defect-found-while-loading).

### Pipeline

| Setting | Value |
| --- | --- |
| AI mode | offline |
| Embedding | `sentence-transformers/all-MiniLM-L6-v2` |
| Language model | Ollama not running, so every verdict comes from `classify_pair` |
| `retrieval_top_k` | 15 |
| `cosine_retrieve_threshold` | 0.40 |
| `fuzzy_strong_threshold` | 86 |

### Method

Command: `HF_HUB_OFFLINE=1 backend/.venv/bin/python scripts/evaluate_hard_set.py data/vave_duplicate_eval_set_v2.xlsx out.json`.

- **Each of the 90 TestQueries** is created as a submission with `create_submission`, using its component, department, text fields, saving, and vehicle volumes. It is then analysed with `analyze_submission` and the application's own runtime, exactly as `POST /ideas/analyze-duplicates` does. The transaction is rolled back afterwards, so no submission, run, or evaluation record is stored.
- **Each of the 597 LabelledPairs** is scored twice:
  - **End to end:** the category the pipeline gave that candidate. A candidate the pipeline did not show counts as not a duplicate.
  - **Classifier only:** `classify_pair` on the pair, whatever retrieval did.
- **Metrics** use `classification_metrics` from `evaluation_service.py`, as `scripts/evaluate.py` does. The positive class is `duplicate`, and only Potential Duplicate counts as a positive prediction. Insufficient Evidence counts as an abstention and as a negative.
- **Cosine** is computed directly between the query's vector and each candidate's stored vector, so it does not depend on the vector search limit. The query is embedded from all its fields, as in the live app.

## Precision, recall, and F1

End to end:

| Difficulty | Pairs | Duplicates | Precision | Recall | F1 | FP rate | TP | FP | FN | TN | Abstentions |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| **overall** | 597 | 90 | **1.000** | **0.322** | **0.487** | 0.000 | 29 | 0 | 61 | 507 | 60 |
| easy | 300 | 30 | 1.000 | 0.967 | 0.983 | 0.000 | 29 | 0 | 1 | 270 | 28 |
| medium | 30 | 30 | — | 0.000 | — | — | 0 | 0 | 30 | 0 | 6 |
| hard | 267 | 30 | — | 0.000 | — | 0.000 | 0 | 0 | 30 | 237 | 26 |

"—" means the metric is undefined: no pair at that difficulty was predicted a duplicate, and the medium set has no negatives at all.

Classifier only, the precision, recall, F1, and counts are identical in every row. Only the abstentions differ (207 overall: 150 easy, 6 medium, 51 hard), because the classifier also judges the unrelated pairs that retrieval never showed.

**Difficulty is tied to the label in this workbook,** so the per-difficulty rows are not like-for-like:

| Label | easy | medium | hard |
| --- | --- | --- | --- |
| duplicate | 30 | 30 | 30 |
| similar but distinct | 0 | 0 | 237 |
| unrelated | 270 | 0 | 0 |

- "Easy" is easy duplicates mixed with unrelated pairs.
- "Medium" is duplicates only.
- "Hard" is hard duplicates mixed with all the similar-but-distinct pairs.

## Predicted category by label

End to end. "Not shown" means the candidate was not among the 15 shown.

| Label | Potential Duplicate | Insufficient Evidence | Similar but Distinct | Not shown | Total |
| --- | --- | --- | --- | --- | --- |
| duplicate (easy) | 29 | 1 | 0 | 0 | 30 |
| duplicate (medium) | 0 | 6 | 24 | 0 | 30 |
| duplicate (hard) | 0 | 1 | 29 | 0 | 30 |
| similar but distinct | 0 | 25 | 141 | 71 | 237 |
| unrelated | 0 | 27 | 0 | 243 | 270 |

- **Duplicates are retrieved.** All 90 were shown. Rank among the 15 shown:
  - easy: 25 at rank 1, worst rank 4
  - medium: 20 at rank 1, worst rank 9
  - hard: 20 at rank 1, worst rank 11
- **The verdict is what fails.** 53 duplicates were called Similar but Distinct, which tells a reviewer the opposite of the truth. Another 8 were sent to manual review.
- **No look-alike was called a duplicate.** Of the 237 similar-but-distinct pairs, 141 were correctly labelled, 25 went to manual review, and 71 were not shown.
- **Reviewer load:** every query showed exactly 15 candidates. The headline outcome was Potential Duplicate for 30 queries and Insufficient Evidence for the other 60.

## Score distributions by label

Fuzzy is RapidFuzz `token_set_ratio` on the comparison text. Jaccard is the word overlap that `classify_pair` uses. Cosine is MiniLM.

### Cosine

| Label | Difficulty | n | min | p25 | median | p75 | max | mean |
| --- | --- | --- | --- | --- | --- | --- | --- | --- |
| duplicate | all | 90 | 0.691 | 0.830 | 0.875 | 0.957 | 0.989 | 0.881 |
| duplicate | easy | 30 | 0.870 | 0.957 | 0.968 | 0.975 | 0.989 | 0.961 |
| duplicate | medium | 30 | 0.702 | 0.824 | 0.859 | 0.906 | 0.951 | 0.857 |
| duplicate | hard | 30 | 0.691 | 0.790 | 0.833 | 0.870 | 0.923 | 0.827 |
| similar but distinct | hard | 237 | 0.375 | 0.631 | 0.715 | 0.760 | 0.910 | 0.684 |
| unrelated | easy | 270 | 0.172 | 0.392 | 0.443 | 0.502 | 0.696 | 0.446 |

### Fuzzy

| Label | Difficulty | n | min | p25 | median | p75 | max | mean |
| --- | --- | --- | --- | --- | --- | --- | --- | --- |
| duplicate | all | 90 | 56.2 | 62.2 | 67.0 | 87.0 | 98.5 | 72.3 |
| duplicate | easy | 30 | 80.0 | 86.5 | 88.7 | 91.3 | 98.5 | 88.5 |
| duplicate | medium | 30 | 57.9 | 61.5 | 65.1 | 68.2 | 77.0 | 65.2 |
| duplicate | hard | 30 | 56.2 | 59.2 | 62.5 | 65.8 | 73.3 | 63.1 |
| similar but distinct | hard | 237 | 43.2 | 53.4 | 55.9 | 58.8 | 80.6 | 56.2 |
| unrelated | easy | 270 | 39.8 | 46.0 | 48.8 | 51.9 | 65.2 | 49.2 |

### Jaccard

| Label | Difficulty | n | min | p25 | median | p75 | max | mean |
| --- | --- | --- | --- | --- | --- | --- | --- | --- |
| duplicate | all | 90 | 0.103 | 0.174 | 0.237 | 0.515 | 0.786 | 0.331 |
| duplicate | easy | 30 | 0.455 | 0.515 | 0.583 | 0.646 | 0.786 | 0.583 |
| duplicate | medium | 30 | 0.116 | 0.168 | 0.224 | 0.267 | 0.344 | 0.221 |
| duplicate | hard | 30 | 0.103 | 0.158 | 0.179 | 0.225 | 0.300 | 0.189 |
| similar but distinct | hard | 237 | 0.021 | 0.085 | 0.122 | 0.162 | 0.394 | 0.130 |
| unrelated | easy | 270 | 0.018 | 0.049 | 0.073 | 0.111 | 0.282 | 0.085 |

What the distributions show:

- **No easy duplicate falls below 0.87 cosine or 80 fuzzy.** That is why the lexical rules catch them.
- **Medium and hard duplicates look lexically like look-alikes.** No medium or hard duplicate reaches fuzzy 86 or Jaccard 0.62, the two rules that call a duplicate without other conditions. Their fuzzy range of 56 – 77 overlaps the similar-but-distinct range of 43 – 81.
- **Cosine keeps more of the gap.** The medium and hard duplicate medians, 0.859 and 0.833, are well above the similar-but-distinct median of 0.715. The ranges still overlap, though: similar-but-distinct pairs reach 0.910, and 28 of them are at 0.80 or above, alongside 77 of the 90 duplicates. No single cosine threshold separates the two labels.
- **Unrelated pairs are well separated on every score.** Their maxima are cosine 0.696 and fuzzy 65.2. Retrieval hid 243 of the 270.
- **Within a query, ranking works.** The labelled duplicate has the highest cosine among that query's labelled candidates in 83 of 90 queries: 30 of 30 easy, 28 of 30 medium, 25 of 30 hard. It has the highest fuzzy score in 82.

## Why medium and hard duplicates are missed

Each of the 61 missed duplicates was traced through the branches of `classify_pair`:

| Difficulty | Verdict | Branch | Pairs |
| --- | --- | --- | --- |
| medium | Similar but Distinct | same component, Jaccard < 0.28 | 24 |
| hard | Similar but Distinct | same component, Jaccard < 0.28 | 29 |
| medium | Insufficient Evidence | same component, Jaccard 0.28 – 0.45 | 6 |
| hard | Insufficient Evidence | same component, Jaccard 0.28 – 0.45 | 1 |
| easy | Insufficient Evidence | fell through every rule | 1 |

**The main cause is this rule** in `classifier.py`:

```python
elif same_component and overlap < 0.45:
    category = "similar_but_distinct" if different_mechanism or overlap < 0.28 else "insufficient_evidence"
```

- **What it does:** for a same-component pair, Jaccard below 0.28 alone is enough to return Similar but Distinct, whether or not the detected kinds of change differ.
- **Why that fails here:** a paraphrase that keeps the meaning and changes the words lands in exactly this branch.
- **Mechanism detection did not help.** On the 61 misses, `change_types()` found no kind of change in either text for 17 pairs, and found one only in the historical text for 31 more. It found one in both texts for only 13. Its keyword lists do not match paraphrases.

Hard examples (all labelled duplicate, all called Similar but Distinct):

| Query → candidate | Fuzzy | Jaccard | Cosine | Query wording | Historical wording |
| --- | --- | --- | --- | --- | --- |
| Q-0003 → H-0001 | 58.1 | 0.188 | 0.835 | "move away from the current ferrous part to a light-alloy design, geometry adjusted so rigidity is not lost" | "Replace the steel cab mounting bracket with an aluminium alloy bracket sized for equivalent stiffness" |
| Q-0006 → H-0005 | 59.5 | 0.167 | 0.827 | "drop the coated metal pressing in favour of a thermoplastic moulding" | "Change the low-voltage battery tray from painted steel to a formed polypropylene tray" |
| Q-0009 → H-0008 | 61.3 | 0.143 | 0.760 | "Thinner sump wall, with an internal plate added so oil movement … does not uncover the pickup" | "Reduce engine oil pan sheet thickness from 1.5 mm to 1.2 mm and add a baffle" |
| Q-0012 → H-0011 | 68.4 | 0.238 | 0.874 | "One mirror mount for both sides instead of two mirror-image parts" | "Commonise the left and right exterior mirror brackets into one handed bracket" |

In each case a reviewer would be told the historical idea is a different change.

**This is the risk noted in [evaluation-results.md](evaluation-results.md#2-a-high-cosine-look-alike-was-correctly-separated-by-keywords): "A paraphrase that avoids those keywords would lose this protection."** On this set the failure goes further than losing protection, because the low-overlap rule returns the opposite verdict.

## Other observations

- **An unlabelled duplicate in the seed data.** Query Q-0037 ("Change the disc brake pad to a cheaper friction material and add an edge chamfer …"):
  - It was flagged Potential Duplicate against **VAVE-SYN-002** (fuzzy 87.2, cosine 0.938). That is the seeded brake-pad chamfer idea, which describes the same change.
  - The workbook does not label it, because the workbook only knows its own VAVE-H ideas, so the hit does not count in the metrics.
  - Its labelled duplicate, VAVE-H-0038 (fuzzy 80.0, cosine 0.970, the highest cosine of any candidate), went to manual review. That pair is the 1 easy miss.
- **The cosine threshold did not matter.** The candidate filter is `exact OR fuzzy ≥ 40 OR cosine ≥ 0.40`. Every duplicate has fuzzy ≥ 56, so all would be shown at any threshold.
- **Comparison with the v1 set.** The 12-case v1 set ([evaluation-results.md](evaluation-results.md)) gave recall 0.8, and its 5 duplicates all had fuzzy ≥ 86. It measured the easy case only. The v2 easy row, recall 0.967, agrees with it.

## Defect found while loading

`POST /api/v1/ideas/import/commit` returned HTTP 500 on every commit that inserted or updated rows. The import transaction rolled back, so nothing was written.

- **Cause:** two lines in `import_commit` (`app/api/v1/router.py`).
  - One read `row.idea_id` from the result of `db.scalars(select(ImportChange.idea_id))`, which already returns plain ids.
  - The other built a list of `DuplicateAnalysisCandidate.idea_id`, an attribute that does not exist, before discarding the list with `and []`. It crashed whenever any analysis candidate existed.
- **Why the tests missed it:** the only import test commits a preview with errors and expects 400.
- **Fix:** read the ids directly, and remove the dead line.
- **Test:** `test_valid_import_commits_and_indexes` commits a one-row CSV and checks that the idea is inserted and embedded. It fails without the fix.

**Still open: import rollback fails for inserted rows.** `import_changes.idea_id` is `NOT NULL` with no `ON DELETE` rule, so deleting an inserted idea is refused with a foreign-key violation. A fix needs a schema decision:
- make the column nullable with `ON DELETE SET NULL`, which keeps the change history, or
- delete those change rows.

Rollback also leaves the idea's embedding vectors behind.

## Limitations

- **Synthetic, from one generator.** The 91 ideas, 90 queries, and 597 labels come from one generated workbook, and the labels encode its author's view of what counts as a duplicate. None of this is a production accuracy claim.
- **Difficulty is tied to the label** (see the table above), so the per-difficulty rows mix different negatives, and precision is undefined for medium and hard.
- **20 VAVE-SYN ideas were also present and are unlabelled.** They can be shown as candidates and take slots among the 15, but they never count in the metrics. One of them was a genuine duplicate of Q-0037.
- **No language model was involved.** With Ollama running, `analyze_submission` asks the model about up to 5 candidates per query. Where the model and the heuristic disagree on a non-exact match, the result becomes Insufficient Evidence. That could turn some of the 53 wrong Similar but Distinct verdicts into manual reviews, but it cannot produce a Potential Duplicate that the heuristic rejects. This was not measured.
- **Nothing was stored as an evaluation run.** The script is read-only, so this run does not appear on the Evaluation page.
