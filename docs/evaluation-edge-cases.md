# Evaluation results: edge-case set

Two runs on 27 October 2026, against the hosted Neon development database with the live stored settings:

- **Run 1, before any fix.** A measurement only, with no code changed.
- **Run 2, with the three Tier 1 classifier rules turned on** (see [Tier 1 changes](#tier-1-changes)). Before this run, the v2 hard set was re-run to check for regressions ([v2 regression check](#v2-regression-check)).

Every number here comes from `data/vave_duplicate_edge_cases.xlsx`, a synthetic workbook of 11 historical ideas, 18 queries and 18 labelled pairs. It was written without sight of the classifier's keyword lists, thresholds or code. Each case type isolates one failure mode and has only two or three pairs, so results are reported **by case type**. No overall figure is given, because it would hide which failure mode is live. Read [Limitations](#limitations) before relying on any of it.

## Summary

| Case type | Label | Pairs | Run 1 correct | Run 2 correct | Layer still responsible |
| --- | --- | --- | --- | --- | --- |
| component_name_variant | duplicate | 3 | 0 | **3** | — (fixed by component matching) |
| opposite_direction | similar_but_distinct | 3 | 0 | 0 | Keyword action detection (no direction); the cosine threshold lets them through |
| negation | similar_but_distinct | 2 | 1 | 2 | EQ-008 fixed by negation detection. EQ-007 is still "correct" only because candidate selection never showed it |
| sparse_description | duplicate | 2 | 2 | 2 | — |
| superset | similar_but_distinct | 2 | 0 | 0 | Fuzzy strong threshold; action detection treats a superset as the same action |
| reversal | similar_but_distinct | 2 | 0 | **2** | — (fixed by reversal detection) |
| different_programme | related_not_duplicate | 2 | 0 | 0 | Cosine threshold: the semantic route fires, and no layer compares vehicle programmes |
| unit_variation | duplicate | 2 | 2 | 2 | — |

- **Tier 1 fixed six pairs**, each through the rule aimed at it: three component variants, both reversals, and the negation pair EQ-008. No pair that passed in run 1 failed in run 2.
- **Three failure modes are still live: opposite_direction (0 of 3), superset (0 of 2) and different_programme (0 of 2).** None of the Tier 1 rules addresses them. No threshold was changed to make them pass.
- **The negation fix only works when the query names some other action.** EQ-008 now passes because, once "do not commonise" is discounted, the query's remaining action ("casting" gives `topology`) is disjoint from the candidate's `commonisation`. A query that only ruled out the candidate's change, and named nothing else, would have no detected action, so the semantic route would still accept it.
- **EQ-007 has not changed.** It was never shown (18th in retrieval order), so it is scored correct without the reviewer ever seeing the idea it rules out.
- **The v2 hard set is unchanged on every pair**, with precision 0.890, recall 0.811, F1 0.849 and rank@1 0.756 before and after. This shows no regression, but it is weak evidence of safety: none of the three rules changes a single action set or component match in the v2 texts ([details](#v2-regression-check)).

## Tier 1 changes

All three rules live in `classify_pair` (`backend/app/services/duplicate_detection/classifier.py`). Each has its own setting in the AI settings, defaults to on in `config.py`, and can be turned off with `PUT /api/v1/ai/settings`. The dev database's stored row has none of the three keys, so the defaults (on) apply there. `scripts/evaluate_hard_set.py --disable <setting>` turns one off for an evaluation run.

| Setting | Rule |
| --- | --- |
| `component_fuzzy_match` | Both component names are normalised (lowercase, punctuation removed), parenthetical qualifiers are dropped, and `brkt`/`bkt` → bracket, `mtg` → mounting, `assy` → assembly are expanded. The names match if RapidFuzz `ratio` is **≥ 90**. When off, normalised names must be identical, as before. |
| `reversal_detection` | `revert`, `return`, `restore`, `reinstate` and `roll back` count as a change verb and mark the text as undoing an earlier change. If both ideas share an action kind and only one of them is a reversal, the pair has a **direction flip**. That counts as a different technical action, so the pair is Similar but Distinct and neither the lexical nor the semantic route can call it a duplicate. |
| `negation_detection` | An action keyword counts as not proposed if it falls within **5 tokens after** a negation cue (`do not`, `don't`, `never`, `without`, `instead of`, `rather than`, `keep`, `retain`, `no change to`) in the same clause. The cue's own words are discounted too, so the "change" in "no change to" is not read as a change verb. Clauses end at `. , ; : ! ?` followed by a space, and at a line break, so "1.5 mm" is not split. |

Two choices go beyond the brief, and both make the rules stricter, not looser:

- **Reversal verbs need context.** A reversal verb counts only when it opens a clause, or when a back-reference (`back`, `original`, `originally`, `previous`, `previously`, `earlier`, `former`) follows it in the same clause. Without this, the edge-case candidate EH-005 ("add a rolled edge to **restore** bending stiffness") would read as a reversal. EQ-006 (opposite_direction) would then have passed for the wrong reason, and every "restore stiffness" or "fuel return line" text would risk the same.
- **Negation stops at the clause end.** Otherwise "Keep the steel grade, and replace the bracket with aluminium" would discount "replace".

The threshold of 90 is the one given in the brief. It was not tuned. Across all 38 distinct component names in the seed data, the v2 set and this set, the only pairs that reach 90 are the intended variants. The closest pair of different components is "Alternator mounting bracket" and "Radiator mounting bracket" at 84.6.

Unit tests in `backend/tests/unit/test_domain_rules.py` cover each rule on its own and with its setting off. The full backend suite passes: 30 unit and 11 integration tests.

## v2 regression check

The v2 hard set was run on the old code and on the new code, against the same database. That database now has 122 historical ideas, because these 11 edge-case ideas were added in run 1. The numbers recorded in [evaluation-hard-set.md](evaluation-hard-set.md) were measured with 111, so they are not the baseline here.

| Run (end to end, 597 pairs) | Precision | Recall | F1 | TP | FP | FN | Mean rank | rank@1 |
| --- | --- | --- | --- | --- | --- | --- | --- | --- |
| Old code, 122 historical | 0.890 | 0.811 | 0.849 | 73 | 9 | 17 | 1.322 | 0.756 (68 / 90) |
| Tier 1 on, 122 historical | 0.890 | 0.811 | 0.849 | 73 | 9 | 17 | 1.322 | 0.756 (68 / 90) |

- **No pair changed.** Across all 597 pairs, the end-to-end verdict, the classifier-only verdict, the shown rank and the component match are identical in both runs. By difficulty (precision/recall): easy 1.000/1.000, medium 1.000/0.800, hard 0.679/0.633, in both runs.
- **Why nothing changed.** Of the 181 v2 texts (Ideas and TestQueries), none changes its detected action set under negation or reversal detection, and none is read as a reversal. The v2 component names are all written canonically. The v2 texts do contain the cues ("instead of" 15 times, "rather than" 11, "keep"/"keeps"/"keeping" 14, "restores" 4), but never in a way that removes a detected action. So this check shows the rules do no harm on v2. It cannot show they are safe on wording that v2 does not contain.
- **The 11 edge-case ideas cost v2 some rank.** With 111 historical ideas, [evaluation-hard-set.md](evaluation-hard-set.md#candidate-ordering-by-verdict) recorded precision 0.880, recall 0.811, F1 0.844, mean rank 1.200 and rank@1 0.833. The code is the same, so the drop to rank@1 0.756 comes from the added ideas, several of which are close variants of v2 components (cab mounting bracket, battery tray, engine oil pan and others).

## Setup

### Database state

- **Before run 1:** 111 historical ideas (VAVE-SYN-001 to -020 and the 91 v2 hard-set ideas), as recorded in [evaluation-hard-set.md](evaluation-hard-set.md#database-state).
- **Imported:** the workbook's Ideas sheet, 11 rows (VAVE-EH-001 to -011), through the same preview → commit → re-index steps as `POST /ideas/import/preview` and `/ideas/import/commit` (batch `e4762c9e-ff9e-4f15-9f2a-031596d67f76`, marked synthetic, 0 errors, 5 warnings). An `import.commit.requested` audit entry was written.
- **Evaluated against:** 122 historical ideas, each with an `all-MiniLM-L6-v2` vector, in both runs.

These 11 ideas **stay in the development database**. Import rollback still fails for inserted rows ([evaluation-hard-set.md](evaluation-hard-set.md#defect-found-while-loading)), so they would have to be deleted by hand.

### Pipeline (live stored settings)

| Setting | Run 1 | Run 2 |
| --- | --- | --- |
| AI mode | offline | offline |
| Embedding | `sentence-transformers/all-MiniLM-L6-v2` | same |
| Language model | Ollama not reachable, so every verdict comes from `classify_pair` | same |
| `semantic_duplicate_threshold` | 0.82 | 0.82 |
| `retrieval_top_k` | 15 | 15 |
| `cosine_retrieve_threshold` | 0.40 | 0.40 |
| `fuzzy_strong_threshold` | 86 | 86 |
| `component_fuzzy_match`, `reversal_detection`, `negation_detection` | did not exist | on |

### Method

A driver kept outside the repository runs the same per-query steps as `score_query` in `scripts/evaluate_hard_set.py` and reuses that script's `query_payload` and `cosine` helpers. That script does not know the `related_not_duplicate` label or the `Case_Type` column. In run 2 the driver passes the same classifier settings the pipeline uses.

- **Each of the 18 TestQueries** is created as a submission with `create_submission` and analysed with `analyze_submission`, using the application's own runtime. The transaction is then rolled back, so no submission or run is stored.
- **End to end:** the category the pipeline gave the labelled candidate. A candidate that was not shown counts as not a duplicate.
- **Classifier only:** `classify_pair` on the labelled pair, whatever retrieval did. In both runs it agrees with end to end on every pair except EQ-007.
- **Scoring.** A pair labelled `duplicate` is correct only if it was called Potential Duplicate. A pair labelled `similar_but_distinct` or `related_not_duplicate` is correct whenever it was **not** called Potential Duplicate, as the workbook's Cover sheet specifies. Insufficient Evidence counts as not a duplicate.
- **Cosine** is computed directly between the query's vector and the candidate's stored vector. On all 18 pairs it equals the pipeline's vector-search score to three decimals.
- **Route** is the classifier branch that produced Potential Duplicate. *Lexical* means fuzzy ≥ 86, or Jaccard ≥ 0.62, or (same action, same component, Jaccard ≥ 0.42 and fuzzy ≥ 68). *Semantic* means same component and cosine ≥ 0.82.
- Run 1 was repeated once and gave identical verdicts and scores.

## Per-pair results

Fuzzy is RapidFuzz `token_set_ratio` on the comparison text (0–100). Jaccard is word overlap of the pair text. Cosine, fuzzy, Jaccard and retrieval position are the same in both runs. "Retr. pos." is the candidate's position in retrieval order (exact, then fuzzy, then cosine) among all 122 historical ideas; only the first 15 are shown. Columns marked (2) are from run 2. "Actions" are the detected action sets for the query and the candidate.

| Query | Candidate | Case type | Label | Run 1 verdict | Run 2 verdict | Correct (2) | Cosine | Fuzzy | Jaccard | Same comp. (2) | Actions (2), query / candidate | Retr. pos. | Shown rank (2) | Route or reason (2) |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| EQ-001 | EH-001 | component_name_variant | duplicate | Insufficient Evidence | **Potential Duplicate** | yes | 0.920 | 84.7 | 0.552 | yes (was no) | material / material | 2 | 1 | lexical (same action and component, Jaccard ≥ 0.42, fuzzy ≥ 68); also semantic |
| EQ-002 | EH-001 | component_name_variant | duplicate | Insufficient Evidence | **Potential Duplicate** | yes | 0.902 | 65.2 | 0.242 | yes (was no) | — / material | 3 | 2 | semantic |
| EQ-003 | EH-002 | component_name_variant | duplicate | Insufficient Evidence | **Potential Duplicate** | yes | 0.938 | 84.3 | 0.567 | yes (was no) | material / material | 2 | 2 | lexical (same action and component, Jaccard ≥ 0.42, fuzzy ≥ 68); also semantic |
| EQ-004 | EH-003 | opposite_direction | similar_but_distinct | Potential Duplicate | Potential Duplicate | no | 0.827 | 67.6 | 0.351 | yes | dimension / dimension | 1 | 1 | semantic |
| EQ-005 | EH-004 | opposite_direction | similar_but_distinct | Potential Duplicate | Potential Duplicate | no | 0.847 | 67.3 | 0.316 | yes | dimension / dimension | 1 | 1 | semantic |
| EQ-006 | EH-005 | opposite_direction | similar_but_distinct | Potential Duplicate | Potential Duplicate | no | 0.912 | 64.5 | 0.294 | yes | dimension / dimension | 1 | 2 | semantic |
| EQ-007 | EH-006 | negation | similar_but_distinct | not shown | not shown | yes | 0.896 | 58.8 | 0.186 | yes | deletion / material | 18 | — | not shown |
| EQ-008 | EH-007 | negation | similar_but_distinct | Potential Duplicate | **Similar but Distinct** | yes | 0.856 | 74.7 | 0.222 | yes | topology / commonisation (query was commonisation, topology) | 1 | 11 | different action |
| EQ-009 | EH-001 | sparse_description | duplicate | Potential Duplicate | Potential Duplicate | yes | 0.883 | 77.2 | 0.185 | yes | — / material | 2 | 2 | semantic |
| EQ-010 | EH-008 | sparse_description | duplicate | Potential Duplicate | Potential Duplicate | yes | 0.845 | 71.4 | 0.167 | yes | — / material | 1 | 1 | semantic |
| EQ-011 | EH-002 | superset | similar_but_distinct | Potential Duplicate | Potential Duplicate | no | 0.927 | 90.2 | 0.442 | yes | dimension, material / material | 1 | 1 | lexical (fuzzy ≥ 86); also semantic |
| EQ-012 | EH-009 | superset | similar_but_distinct | Potential Duplicate | Potential Duplicate | no | 0.876 | 90.6 | 0.450 | yes | dimension, material / material | 2 | 2 | lexical (fuzzy ≥ 86); also semantic |
| EQ-013 | EH-001 | reversal | similar_but_distinct | Potential Duplicate | **Similar but Distinct** | yes | 0.857 | 59.8 | 0.195 | yes | material (reversal) / material (query was —) | 1 | 10 | direction flip |
| EQ-014 | EH-010 | reversal | similar_but_distinct | Potential Duplicate | **Similar but Distinct** | yes | 0.889 | 64.0 | 0.275 | yes | material (reversal) / dimension, material (query was —) | 2 | 12 | direction flip |
| EQ-015 | EH-001 | different_programme | related_not_duplicate | Potential Duplicate | Potential Duplicate | no | 0.859 | 65.2 | 0.250 | yes | — / material | 1 | 2 | semantic |
| EQ-016 | EH-004 | different_programme | related_not_duplicate | Potential Duplicate | Potential Duplicate | no | 0.886 | 65.0 | 0.244 | yes | dimension / dimension | 1 | 1 | semantic |
| EQ-017 | EH-003 | unit_variation | duplicate | Potential Duplicate | Potential Duplicate | yes | 0.969 | 94.5 | 0.656 | yes | dimension / dimension | 1 | 1 | lexical (fuzzy ≥ 86); also semantic |
| EQ-018 | EH-011 | unit_variation | duplicate | Potential Duplicate | Potential Duplicate | yes | 0.981 | 94.4 | 0.676 | yes | dimension / dimension | 2 | 1 | lexical (fuzzy ≥ 86); also semantic |

"material" is `material_substitution`. "—" means no action keyword was found. In run 1, EQ-001 to EQ-003 had same component "no". Every other column not marked (2) is the same in both runs.

## By case type

### component_name_variant: 0 → 3 of 3 (fixed)

**Run 1 layer: component exact match.** "Cab mount brkt", "Cab Mtg Bkt" and "Battery tray (LV)" did not equal "Cab mounting bracket" or "Battery tray". That blocked the semantic route and the third lexical clause, both of which need a matching component. Cosine was already 0.902 – 0.938.

**Run 2:** the components match ("Cab mount brkt" → "cab mount bracket", ratio 91.9 against "cab mounting bracket"; the other two match exactly once expanded or stripped). EQ-001 and EQ-003 now pass on the lexical rule that needs a matching component, and EQ-002 passes on the semantic route. The EQ-001 match clears 90 by 1.9 points.

The same rule also lets these queries reach other historical ideas for the same component. EQ-001 and EQ-002 now have five unlabelled Potential Duplicates each (aluminium cab mounting bracket ideas such as VAVE-SYN-001, SYN-017 and H-0001), up from 1 and 0. Those pairs are not labelled, so they are not scored here.

### opposite_direction: 0 of 3 (still failing)

**Layer: keyword action detection, with the cosine threshold letting the pairs through.** Both sides of each pair map to `{dimension}` (from "thickness" or "mm"). The detector records the kind of change, not its direction, so "reduce … from 1.5 mm to 1.2 mm" and "increase … from 1.2 mm to 1.5 mm" are the same action, and the semantic route accepts them. Margins over 0.82: +0.007 (EQ-004), +0.027 (EQ-005), +0.092 (EQ-006). Reversal detection does not apply: these queries propose a change in the other direction; they do not undo an earlier one.

### negation: 1 → 2 of 2

- **EQ-008 (fixed by negation detection).** "Do not commonise them" is discounted, so the query's action set drops from `{commonisation, topology}` to `{topology}`, which is disjoint from the candidate's `{commonisation}`. The verdict is Similar but Distinct and the candidate drops from shown rank 3 to 11. The rule depends on that remaining `topology` ("casting"). Without another detected action, the query would have had none at all, and the semantic route (cosine 0.856) would still have called it a duplicate.
- **EQ-007 (unchanged; candidate selection).** Still 18th in retrieval order: its fuzzy score (58.75) is 0.85 below the 15th candidate's (59.6), although its cosine (0.896) is higher than every candidate shown. It is scored correct only because it was not shown. The classifier alone says Similar but Distinct, from "remove material" (`deletion`) against `material_substitution`, which was already true before negation detection.

### sparse_description: 2 of 2

Both still pass through the semantic route (0.883, 0.845). Neither query yields an action keyword, so the action guard is skipped and the verdict rests on cosine alone.

### superset: 0 of 2 (still failing)

**Layer: the fuzzy strong threshold (lexical route); keyword action detection is secondary.** `token_set_ratio` scores 90.2 and 90.6, because the query contains the candidate's whole text. Action detection does find the extra change (`dimension`), but the guard only rejects disjoint sets, and `{dimension, material}` overlaps `{material}`. The semantic route would also accept both (0.927, 0.876).

### reversal: 0 → 2 of 2 (fixed)

**Run 1 layer: keyword action detection.** "Revert" and "return" were not change verbs, so the queries had no detected action and the guard was skipped.

**Run 2:** "Revert … back to the original steel" and "Return the headliner substrate …" open their clauses, so both queries are read as `material_substitution`, reversed. The candidates make the forward change, so the pair is a direction flip: Similar but Distinct, with the difference "The technical action is reversed". The headline outcome of both queries changed from Potential Duplicate to Insufficient Evidence. EQ-013 had also called five unlabelled aluminium cab-bracket ideas Potential Duplicate in run 1; in run 2 it calls none.

### different_programme: 0 of 2 (still failing)

**Layer: cosine threshold, with no layer that compares programmes.** These are same-component, same-change pairs, so the semantic route fires as designed (0.859, 0.886). The programme appears only in free text ("to the tipper programme"), and every row of this workbook carries the same vehicle volumes, so the structured applicability cannot separate them either. None of the Tier 1 rules applies.

### unit_variation: 2 of 2

Both still pass on fuzzy score (94.5, 94.4), because the rest of the wording is nearly identical. This shows nothing about handling units.

## Route off, for comparison (run 1)

This table was derived from run 1's recorded scores using `classify_pair`'s branch order. It was not re-run, and it predates Tier 1. With `semantic_duplicate_threshold` = `null`, the eight pairs the semantic route accepted in run 1 would have fallen to Insufficient Evidence:

| Case type | Correct, route on (run 1) | Correct, route off (run 1 code) |
| --- | --- | --- |
| component_name_variant | 0 / 3 | 0 / 3 |
| opposite_direction | 0 / 3 | 3 / 3 |
| negation | 1 / 2 | 2 / 2 |
| sparse_description | 2 / 2 | 0 / 2 |
| superset | 0 / 2 | 0 / 2 |
| reversal | 0 / 2 | 2 / 2 |
| different_programme | 0 / 2 | 2 / 2 |
| unit_variation | 2 / 2 | 2 / 2 |

In run 1, no single threshold separated these labels: the two duplicates the semantic route accepted scored 0.845 and 0.883, and the eight false positives it accepted scored 0.827 – 0.912. In run 2, the route's remaining false positives are the three opposite_direction and two different_programme pairs (0.827 – 0.912). The two sparse duplicates (0.845, 0.883) still sit inside that range.

## Limitations

- Each case type has two or three pairs, and each query has one labelled candidate. A case type that passed has only shown that it *can* pass. A failure, though, identifies a mechanism, and each one above is traced to a specific rule.
- The fixed cases were fixed by rules written after reading these failures. The rules were not tuned on these pairs (the thresholds and cue lists are the ones in the brief), but this set is no longer independent evidence for them. A fresh set is needed to measure them.
- The workbook is synthetic, and every historical idea in it uses the same vehicle volumes.
- Ollama was not reachable, so the optional language-model rerank played no part. Every verdict is heuristic.
- Only the labelled pair per query is scored. Retrieval competition comes from the 111 other historical ideas already in the development database.
- The edge-case driver is not in the repository. It runs the same steps as `scripts/evaluate_hard_set.py`, with case-type grouping and the third label added.
