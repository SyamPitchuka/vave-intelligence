# Evaluation results: edge-case set

Run on 27 October 2026 against the hosted Neon development database, with the live stored settings.

Every number here comes from `data/vave_duplicate_edge_cases.xlsx`, a synthetic workbook of 11 historical ideas, 18 queries and 18 labelled pairs. It was written without sight of the classifier's keyword lists, thresholds or code. Each case type isolates one failure mode and has only two or three pairs, so results are reported **by case type**. No overall figure is given, because it would hide which failure mode is live. Read [Limitations](#limitations) before relying on any of it.

## Summary

| Case type | Label | Pairs | Correct | Main failing layer |
| --- | --- | --- | --- | --- |
| component_name_variant | duplicate | 3 | **0** | Component exact match |
| opposite_direction | similar_but_distinct | 3 | **0** | Keyword action detection (no direction); the cosine threshold lets them through |
| negation | similar_but_distinct | 2 | 1 | Keyword action detection (negation ignored). The one "correct" pair was never shown to the reviewer (candidate selection) |
| sparse_description | duplicate | 2 | 2 | — |
| superset | similar_but_distinct | 2 | **0** | Fuzzy strong threshold (`token_set_ratio` rewards a superset); action detection treats a superset as the same action |
| reversal | similar_but_distinct | 2 | **0** | Keyword action detection (no action found in the query, so the guard is skipped) |
| different_programme | related_not_duplicate | 2 | **0** | Cosine threshold: the semantic route fires, and no layer compares vehicle programmes |
| unit_variation | duplicate | 2 | 2 | — |

- **Six of the eight failure modes are live.** Only sparse descriptions and unit variation passed.
- **The semantic route (cosine ≥ 0.82, same component, no detected different action) produced 8 of the 10 false positives.** Its guard is the keyword action detector, and that detector cannot see direction (reduce/increase, widen), negation ("do not commonise"), or reversal ("revert", "return"). The other two false positives (superset) came from the lexical fuzzy route.
- **No cosine threshold separates these labels.** The two duplicates that the semantic route accepted scored 0.845 and 0.883. The eight false positives it accepted scored 0.827 – 0.912. Excluding all eight needs a threshold above 0.912, which also loses both duplicates.
- **Component variants fail on exact string match alone.** All three have cosine 0.902 – 0.938, which is above every semantic-route false positive except one (0.912). EQ-001 and EQ-003 also miss the fuzzy strong threshold (86) by 1.3 and 1.7 points.

## Setup

### Database state

- **Before:** 111 historical ideas (VAVE-SYN-001 to -020 and the 91 v2 hard-set ideas), as recorded in [evaluation-hard-set.md](evaluation-hard-set.md#database-state).
- **Imported:** the workbook's Ideas sheet, 11 rows (VAVE-EH-001 to -011), through the same preview → commit → re-index steps as `POST /ideas/import/preview` and `/ideas/import/commit` (batch `e4762c9e-ff9e-4f15-9f2a-031596d67f76`, marked synthetic, 0 errors, 5 warnings). An `import.commit.requested` audit entry was written.
- **Evaluated against:** 122 historical ideas, each with an `all-MiniLM-L6-v2` vector.

These 11 ideas **stay in the development database**. Import rollback still fails for inserted rows ([evaluation-hard-set.md](evaluation-hard-set.md#defect-found-while-loading)), so they would have to be deleted by hand. Until then, a re-run of the v2 hard set searches 122 historical ideas, not 111, and its numbers may differ from the ones recorded.

### Pipeline (live stored settings)

| Setting | Value |
| --- | --- |
| AI mode | offline |
| Embedding | `sentence-transformers/all-MiniLM-L6-v2` |
| Language model | Ollama not reachable, so every verdict comes from `classify_pair` |
| `semantic_duplicate_threshold` | 0.82 |
| `retrieval_top_k` | 15 |
| `cosine_retrieve_threshold` | 0.40 |
| `fuzzy_strong_threshold` | 86 |

### Method

No application code was changed. A throwaway driver, kept outside the repository, ran the same per-query steps as `score_query` in `scripts/evaluate_hard_set.py` and reused that script's `query_payload` and `cosine` helpers. That script could not be used unchanged because it does not know the `related_not_duplicate` label or the `Case_Type` column.

- **Each of the 18 TestQueries** is created as a submission with `create_submission` and analysed with `analyze_submission`, using the application's own runtime. The transaction is then rolled back, so no submission or run is stored.
- **End to end:** the category the pipeline gave the labelled candidate. A candidate that was not shown counts as not a duplicate.
- **Classifier only:** `classify_pair` on the labelled pair, whatever retrieval did. It agrees with end to end on every pair except EQ-007 (see [negation](#negation)).
- **Scoring.** A pair labelled `duplicate` is correct only if it was called Potential Duplicate. A pair labelled `similar_but_distinct` or `related_not_duplicate` is correct whenever it was **not** called Potential Duplicate, as the workbook's Cover sheet specifies. Insufficient Evidence counts as not a duplicate.
- **Cosine** is computed directly between the query's vector and the candidate's stored vector. On all 18 pairs it equals the pipeline's vector-search score to three decimals.
- **Route** is the classifier branch that produced Potential Duplicate. *Lexical* means fuzzy ≥ 86, or Jaccard ≥ 0.62, or (same action, same component, Jaccard ≥ 0.42 and fuzzy ≥ 68). *Semantic* means same component and cosine ≥ 0.82.
- The run was repeated once and gave identical verdicts and scores.

## Per-pair results

Fuzzy is RapidFuzz `token_set_ratio` on the comparison text (0–100). Jaccard is word overlap of the pair text. "Retr. pos." is the candidate's position in retrieval order (exact, then fuzzy, then cosine) among all 122 historical ideas; only the first 15 are shown. "Shown rank" is its position after the display re-sort by verdict. "Actions" are the `change_types` keyword sets for the query and the candidate.

| Query | Candidate | Case type | Label | Verdict | Correct | Cosine | Fuzzy | Jaccard | Same comp. | Actions (query / candidate) | Retr. pos. | Shown rank | Route |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| EQ-001 | EH-001 | component_name_variant | duplicate | Insufficient Evidence | no | 0.920 | 84.7 | 0.552 | no | material / material | 2 | 2 | — |
| EQ-002 | EH-001 | component_name_variant | duplicate | Insufficient Evidence | no | 0.902 | 65.2 | 0.242 | no | — / material | 3 | 2 | — |
| EQ-003 | EH-002 | component_name_variant | duplicate | Insufficient Evidence | no | 0.938 | 84.3 | 0.567 | no | material / material | 2 | 2 | — |
| EQ-004 | EH-003 | opposite_direction | similar_but_distinct | Potential Duplicate | no | 0.827 | 67.6 | 0.351 | yes | dimension / dimension | 1 | 1 | semantic |
| EQ-005 | EH-004 | opposite_direction | similar_but_distinct | Potential Duplicate | no | 0.847 | 67.3 | 0.316 | yes | dimension / dimension | 1 | 1 | semantic |
| EQ-006 | EH-005 | opposite_direction | similar_but_distinct | Potential Duplicate | no | 0.912 | 64.5 | 0.294 | yes | dimension / dimension | 1 | 2 | semantic |
| EQ-007 | EH-006 | negation | similar_but_distinct | not shown | yes | 0.896 | 58.8 | 0.186 | yes | deletion / material | 18 | — | — |
| EQ-008 | EH-007 | negation | similar_but_distinct | Potential Duplicate | no | 0.856 | 74.7 | 0.222 | yes | commonisation, topology / commonisation | 1 | 3 | semantic |
| EQ-009 | EH-001 | sparse_description | duplicate | Potential Duplicate | yes | 0.883 | 77.2 | 0.185 | yes | — / material | 2 | 2 | semantic |
| EQ-010 | EH-008 | sparse_description | duplicate | Potential Duplicate | yes | 0.845 | 71.4 | 0.167 | yes | — / material | 1 | 1 | semantic |
| EQ-011 | EH-002 | superset | similar_but_distinct | Potential Duplicate | no | 0.927 | 90.2 | 0.442 | yes | dimension, material / material | 1 | 1 | lexical (also semantic) |
| EQ-012 | EH-009 | superset | similar_but_distinct | Potential Duplicate | no | 0.876 | 90.6 | 0.450 | yes | dimension, material / material | 2 | 2 | lexical (also semantic) |
| EQ-013 | EH-001 | reversal | similar_but_distinct | Potential Duplicate | no | 0.857 | 59.8 | 0.195 | yes | — / material | 1 | 5 | semantic |
| EQ-014 | EH-010 | reversal | similar_but_distinct | Potential Duplicate | no | 0.889 | 64.0 | 0.275 | yes | — / dimension, material | 2 | 1 | semantic |
| EQ-015 | EH-001 | different_programme | related_not_duplicate | Potential Duplicate | no | 0.859 | 65.2 | 0.250 | yes | — / material | 1 | 2 | semantic |
| EQ-016 | EH-004 | different_programme | related_not_duplicate | Potential Duplicate | no | 0.886 | 65.0 | 0.244 | yes | dimension / dimension | 1 | 1 | semantic |
| EQ-017 | EH-003 | unit_variation | duplicate | Potential Duplicate | yes | 0.969 | 94.5 | 0.656 | yes | dimension / dimension | 1 | 1 | lexical (also semantic) |
| EQ-018 | EH-011 | unit_variation | duplicate | Potential Duplicate | yes | 0.981 | 94.4 | 0.676 | yes | dimension / dimension | 2 | 1 | lexical (also semantic) |

"material" is `material_substitution`. "—" in the actions column means no action keyword was found.

## Failures by case type

### component_name_variant (0 of 3)

**Layer: component exact match.** `classify_pair` compares normalised component strings for equality. "Cab mount brkt", "Cab Mtg Bkt" and "Battery tray (LV)" do not equal "Cab mounting bracket" or "Battery tray", so `same_component` is false. That blocks the semantic route and the third lexical clause, both of which need it. The verdict falls to Insufficient Evidence.

- Cosine is 0.902 – 0.938, which is 0.08 – 0.12 above the 0.82 threshold. The semantic route would have accepted all three if the component had matched.
- EQ-001 (fuzzy 84.7) and EQ-003 (84.3) miss the component-independent fuzzy route by 1.3 and 1.7 points. Their Jaccard (0.552, 0.567) is below 0.62.
- Retrieval was not the problem: all three were shown, at rank 2.

### opposite_direction (0 of 3)

**Layer: keyword action detection, with the cosine threshold letting the pairs through.** All three pairs went through the semantic route. Its only guard is that the query and candidate action sets must not be disjoint. Both sides map to `{dimension}` (from "thickness", "mm"), and the detector has no idea of direction: "reduce … from 1.5 mm to 1.2 mm" and "increase … from 1.2 mm to 1.5 mm" give the same set.

- The margins over 0.82 are +0.007 (EQ-004), +0.027 (EQ-005) and +0.092 (EQ-006). Raising the threshold to 0.83 would only rescue EQ-004. EQ-006, a width change in the opposite direction, scored 0.912, higher than both sparse duplicates the route correctly accepted.

### negation (1 of 2)

- **EQ-008 (failed). Layer: keyword action detection.** "Do not commonise them" still contains "commonise", so the query's action set is `{commonisation, topology}` ("topology" comes from "casting"). The candidate's set is `{commonisation}`. The sets overlap, so no different action is detected, and the semantic route fires at 0.856 (+0.036).
- **EQ-007 (scored correct, but only because it was not shown). Layer: candidate selection.** The candidate was 18th in retrieval order. Its fuzzy score (58.75) was 0.85 below the 15th candidate's (59.6), so it fell outside `retrieval_top_k`, although its cosine (0.896) is higher than every candidate that was shown (highest 0.858). Had it been shown, the classifier would have said Similar but Distinct, because "remove material" gives `{deletion}` and the candidate gives `{material_substitution}`. That is the right verdict, but for a keyword reason ("remove"), not because the negation was understood. The reviewer of this query never saw the historical idea it rules out. Instead, an unlabelled historical idea (VAVE-H-0031) was shown as a Potential Duplicate at rank 1.

### sparse_description (2 of 2)

Both passed through the semantic route (0.883 and 0.845). Neither query yielded an action keyword ("Al bracket", "PMMA instead of PC" have no change verb from the list). An empty set skips the action guard, so the route decided on cosine alone. The correct result therefore rests on the same mechanism that produced the reversal false positives.

### superset (0 of 2)

**Layer: the fuzzy strong threshold (lexical route), not one of the four layers listed in the brief. Keyword action detection is a secondary cause.** `token_set_ratio` scores the shared tokens against each side. When the query contains the candidate's whole text plus an extra clause, the score is high: 90.2 and 90.6, against a threshold of 86. Action detection does find the extra change (`dimension` from "40 mm"), but the guard only rejects *disjoint* sets. `{dimension, material}` and `{material}` overlap, so no difference is recorded. The semantic route would also have accepted both (0.927, 0.876).

### reversal (0 of 2)

**Layer: keyword action detection, with the cosine threshold letting the pairs through.** "Revert the cab mounting bracket from aluminium alloy back to the original steel" and "Return the headliner substrate from PET felt to the original phenolic resin board" yield no action at all. The material words are present, but "revert" and "return" are not in the change-verb list. An empty query set skips the guard entirely, and the semantic route fires at 0.857 (+0.037) and 0.889 (+0.069). Even with the verb recognised, the guard would compare `{material_substitution}` with `{material_substitution}` and still find no difference, because the detector records the kind of change, not its direction.

### different_programme (0 of 2)

**Layer: cosine threshold, with no layer that compares programmes.** These are same-component, same-change pairs, so the semantic route fires as designed (0.859, 0.886). Nothing in the pipeline compares the programme. It appears only in the free text ("to the tipper programme"). The structured vehicle volumes cannot separate it either, because every row of this workbook carries the same volumes for all five families. The system has no "related, not a duplicate" verdict. Showing these pairs is useful, as the workbook notes, but calling them Potential Duplicate is wrong.

### unit_variation (2 of 2)

Both passed through the lexical route (fuzzy 94.5 and 94.4), because the rest of the wording is nearly identical. They did not need any understanding of units, so this does not show that the system handles units. A unit-varied paraphrase would depend on the semantic route.

## Route off, for comparison

This is not a second run. It is derived from the recorded scores using `classify_pair`'s branch order. With `semantic_duplicate_threshold` = `null`, the eight pairs the semantic route accepted would fall to Insufficient Evidence (same component, Jaccard < 0.45, no different action detected):

| Case type | Correct, route on (live) | Correct, route off |
| --- | --- | --- |
| component_name_variant | 0 / 3 | 0 / 3 |
| opposite_direction | 0 / 3 | 3 / 3 |
| negation | 1 / 2 | 2 / 2 |
| sparse_description | 2 / 2 | 0 / 2 |
| superset | 0 / 2 | 0 / 2 |
| reversal | 0 / 2 | 2 / 2 |
| different_programme | 0 / 2 | 2 / 2 |
| unit_variation | 2 / 2 | 2 / 2 |

The route trades the sparse-description duplicates against the opposite-direction, negation, reversal and different-programme negatives. On this set, no threshold value avoids that trade (see [Summary](#summary)). "Correct" for the negatives with the route off means Insufficient Evidence, not Similar but Distinct, so the reviewer is still left to tell them apart.

## Other observations

- **Unlabelled candidates were also called Potential Duplicate.** For example, the reversal query EQ-013 had five other historical ideas called Potential Duplicate (VAVE-SYN-017, SYN-001, H-0001, SYN-019, SYN-018). The labelled candidate was shown at rank 5. Those pairs are not labelled, so they are not scored here.
- **The headline outcome was Potential Duplicate for 17 of 18 queries.** EQ-002 was the exception (Insufficient Evidence).

## Limitations

- Each case type has two or three pairs, and each query has one labelled candidate. A case type that passed has only shown that it *can* pass. A failure, though, identifies a mechanism, and each one above is traced to a specific rule.
- The workbook is synthetic, and every historical idea in it uses the same vehicle volumes.
- Ollama was not reachable, so the optional language-model rerank played no part. Every verdict is heuristic.
- Only the labelled pair per query is scored. Retrieval competition comes from the 111 other historical ideas already in the development database.
- The driver that produced these numbers is not in the repository, because this was a measurement-only run. It ran the same steps as `scripts/evaluate_hard_set.py`, with case-type grouping and the third label added.
