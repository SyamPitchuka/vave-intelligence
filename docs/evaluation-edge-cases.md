# Evaluation results: edge-case set

Three runs on 27 October 2026, against the hosted Neon development database with the live stored settings:

- **Run 1, before any fix.** A measurement only, with no code changed.
- **Run 2, Tier 1:** component matching, reversal verbs, and negation ([Tier 1 changes](#tier-1-changes)).
- **Run 3, Tier 2:** direction extraction, scope comparison, and a symmetric fuzzy score ([Tier 2 changes](#tier-2-changes)). Direction extraction replaced Tier 1's reversal verbs.

Each tier was measured on the v2 hard set first, to check for regressions, and only then on these edge cases.

**Since 28 October:** the symmetric fuzzy score is off, and two component rules are on: a subset guard, and the lexical duplicate rule requiring a matching component. With these settings this set gives the same verdict on every pair as run 3. The adversarial follow-up set, the guard and a component-threshold sweep are in [evaluation-edge-cases-v2.md](evaluation-edge-cases-v2.md).

Every number here comes from `data/vave_duplicate_edge_cases.xlsx`, a synthetic workbook of 11 historical ideas, 18 queries and 18 labelled pairs. It was written without sight of the classifier's keyword lists, thresholds or code. Each case type isolates one failure mode and has only two or three pairs, so results are reported **by case type**. No overall figure is given, because it would hide which failure mode is live. Read [Limitations](#limitations) before relying on any of it.

## Summary

| Case type | Label | Pairs | Run 1 | Run 2 (Tier 1) | Run 3 (Tier 2) | What decides it now |
| --- | --- | --- | --- | --- | --- | --- |
| component_name_variant | duplicate | 3 | 0 | 3 | 3 | Component matching |
| opposite_direction | similar_but_distinct | 3 | 0 | 0 | **3** | Direction extraction: opposite length changes |
| negation | similar_but_distinct | 2 | 1 | 2 | 2 | EQ-008: negation detection. EQ-007: never shown (candidate selection) |
| sparse_description | duplicate | 2 | 2 | 2 | 2 | Semantic route on cosine alone |
| superset | similar_but_distinct | 2 | 0 | 0 | **2** | Scope comparison |
| reversal | similar_but_distinct | 2 | 0 | 2 | 2 | Direction extraction: flipped material pair (in run 2: reversal verbs) |
| different_programme | related_not_duplicate | 2 | 0 | 0 | 0 | **Still failing.** Not addressed: the workbook gives every row identical vehicle volumes and will be fixed separately |
| unit_variation | duplicate | 2 | 2 | 2 | 2 | Lexical fuzzy rule |

- **Every case type except different_programme now passes.** No pair that passed in an earlier run failed in a later one.
- **Two cases pass for weaker reasons than their case type suggests.** EQ-007 (negation) was never shown to the reviewer, so it scores as correct only because it was hidden. EQ-008 (negation) passes because a second action ("casting") remains once the negated one is discounted.
- **No threshold was changed.** The cosine threshold, the fuzzy threshold of 86 and the component-match threshold of 90 are as before.
- **On the v2 hard set, Tier 2 removed one false positive and cost nothing.** Precision went from 0.880 to 0.890, F1 from 0.844 to 0.849, and recall (0.811), mean rank (1.200) and rank@1 (0.833) were unchanged. The gain came from scope comparison. Direction extraction and the symmetric fuzzy score changed no v2 pair ([details](#v2-regression-check-tier-2)).
- **The symmetric fuzzy score changed no labelled verdict on either set.** It matters only while the semantic route is on. With the route off, it would cost 10 v2 duplicates ([details](#symmetric-fuzzy-score)). **It was turned off on 28 October**, and that changed no labelled pair on either set.

## Tier 2 changes

Each rule has its own AI setting, defaults to on in `config.py`, and can be turned off with `PUT /api/v1/ai/settings` (or `--disable` in `scripts/evaluate_hard_set.py` and `scripts/score_edge.py`). The dev database's stored row has none of these keys, so the defaults apply there.

| Setting | Rule |
| --- | --- |
| `direction_detection` | `state_pairs` reads before → after pairs from "from X to Y", "replace X with Y" and "substitute Y for X", within one clause and at most 8 tokens per side. Two numbers with a length unit (mm, cm, in/inch; inches converted to millimetres; a unit given only once applies to both) make a **decrease** or an **increase**. Two different materials, from a fixed list of 25 names (steel, aluminium, polypropylene/PP, polycarbonate/PC, PMMA/acrylic, PET, phenolic, rubber, urethane, and others), make a **substitution** X → Y. The pair **conflicts** when the length directions on the two sides are disjoint (only increases against only decreases), or when one side's X → Y is the other side's Y → X and not also X → Y (**flipped substitution**). A conflict counts as a different technical action. The pair is Similar but Distinct, and neither the semantic route nor the lexical rule can call it a duplicate, whatever the cosine or fuzzy score. |
| `scope_comparison` | If the two sides share at least one detected kind of change, and the query has kinds of change the candidate lacks, that is a scope mismatch and also counts as a different technical action. It does not apply when the query proposes *fewer* kinds than the candidate, or when the candidate has no detected action. |
| `symmetric_lexical_fuzzy` (default off since 28 October) | The lexical duplicate rule (fuzzy ≥ 86, or same action and component with Jaccard ≥ 0.42 and fuzzy ≥ 68) uses RapidFuzz `token_sort_ratio` instead of `token_set_ratio`. Retrieval order, the candidate filter, the other classifier branches and the fuzzy score shown in the UI still use `token_set_ratio`. |

**Reversal is now a flipped state pair, so `reversal_detection` was removed,** along with its verb list (revert, return, restore, reinstate, roll back) and the clause-position rule added in Tier 1. That rule existed only to stop "restore bending stiffness" from reading as a reversal. A state pair needs two stated states, so that text yields no pair and the guard is no longer needed. Both reversal cases still pass (run 3, and stage A below). The trade-off: a reversal written without both states ("Revert to the original design") is no longer detected.

**The fuzzy scorer is containment-friendly, as suspected.** `rank_historical` scores with `token_set_ratio`, which compares the shared tokens with each side. A text that contains the other scores near 100 by construction: the superset queries scored 90.2 and 90.6. `token_sort_ratio` compares the two full token lists, so it is symmetric.

New unit tests in `backend/tests/unit/test_domain_rules.py` cover state-pair parsing (units, inches, a unit given once, "substitute … for", reversal, no pair without two states), opposite directions overriding both a cosine of 0.99 and a fuzzy score of 95, a flipped substitution, same-direction and different-material pairs that are not conflicts, scope mismatch and its two exclusions, and the symmetric score replacing the containment score only when enabled. The full backend suite passes: 34 unit and 11 integration tests.

## v2 regression check (Tier 2)

All runs used the clean 111-idea database ([baseline](evaluation-results.md#v2-hard-set-clean-baseline-27-october-2026)) and the same live settings. Each stage turned the Tier 2 rules on one at a time with `--disable`.

| Stage (end to end, 597 pairs) | Precision | Recall | F1 | TP | FP | FN | Mean rank | rank@1 | Pairs changed from baseline |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| Clean baseline (code before Tier 2) | 0.880 | 0.811 | 0.844 | 73 | 10 | 17 | 1.200 | 0.833 | — |
| Z: Tier 2 code, all three off | 0.880 | 0.811 | 0.844 | 73 | 10 | 17 | 1.200 | 0.833 | 0 |
| A: + direction | 0.880 | 0.811 | 0.844 | 73 | 10 | 17 | 1.200 | 0.833 | 0 |
| B: + scope | **0.890** | 0.811 | **0.849** | 73 | **9** | 17 | 1.200 | 0.833 | 3 |
| C: + symmetric fuzzy (live) | 0.890 | 0.811 | 0.849 | 73 | 9 | 17 | 1.200 | 0.833 | 3 (same as B) |

- **No regression.** Recall, mean rank and rank@1 are unchanged at every stage, and no duplicate lost its verdict. Stage Z reproduces the baseline exactly, which confirms that the refactoring (one shared `pair_inputs` helper for the service and both scripts) changed nothing.
- **Direction extraction changed nothing on v2.** 42 of the 181 v2 texts yield a state pair. All of the length pairs are decreases, and no material pair is the reverse of another, so v2 has no opposite-direction pair to catch.
- **Scope comparison removed one false positive.** VAVE-Q-0022 ("Remove two longitudinal ribs from the rear axle banjo casting") was called a Potential Duplicate of VAVE-H-0024 ("from a two-piece welded fabrication to a single casting"). The label is similar_but_distinct. Both texts contain "casting", so both read as `topology`. The query also has `deletion` ("remove"), so it is now a scope mismatch: Similar but Distinct, moved from shown rank 3 to 10. Two other candidates of the same query moved one place as a result (H-0025: 12 → 11; H-0071: 5 → 4). The verdict is right, but the shared `topology` comes from the word "casting", not from a shared action.
- **By difficulty** (precision / recall), stages B and C: easy 1.000 / 1.000, medium 1.000 / 0.800, hard 0.679 / 0.633 (baseline hard 0.655 / 0.633). Classifier only: precision 0.859 → 0.869, 12 → 11 false positives.

### Symmetric fuzzy score

- **Effect on v2 precision: none.** No v2 similar-but-distinct or unrelated pair ever reached `token_set_ratio` 86, so the containment score was not producing v2 false positives.
- **It removes the lexical route from most duplicates.** Of the 23 v2 duplicates at `token_set_ratio` ≥ 86, 21 fall below 86 under `token_sort_ratio` (76.4 – 85.5). They keep their Potential Duplicate verdict only because the semantic route also accepts them.
- **With the semantic route off, it would cost recall.** A classifier-only replay of all 597 pairs with the run's own scores reproduced the live run exactly (73 TP, 11 FP), so it was used for this. With the route off: 29 TP, 0 FP, recall 0.322 using `token_set_ratio`, and 19 TP, 0 FP, recall 0.211 using `token_sort_ratio`. That is 10 duplicates lost for no precision gain. If the semantic route is ever turned off, turn this setting off too.
- **On the edge set it changed no labelled verdict.** On its own, without scope comparison, it does not fix the superset cases, because the semantic route still accepts them (cosine 0.927 and 0.876). It did change two **unlabelled** verdicts:
  - **EQ-001 no longer flags VAVE-SYN-016,** a steering column lower bracket. That is a different component, flagged before Tier 1 only on a containment score of 86.4. Probably a false positive removed.
  - **EQ-003 no longer flags VAVE-SYN-015,** "Low-voltage battery tray". That is the same proposal as the query (painted steel to a formed polypropylene tray with inserts), under a component name that does not reach 90 against "Battery tray (LV)". Probably a true duplicate lost.

## Pairs flagged after component relaxation

After Tier 1, EQ-001 and EQ-002 flagged five unlabelled historical ideas each as Potential Duplicate (measured with the 11 edge-case ideas loaded and Tier 1 rules on). They are listed for review. No change was made on the strength of them.

| Query | Candidate | Candidate component | Cosine | Fuzzy | Candidate text (description) |
| --- | --- | --- | --- | --- | --- |
| EQ-001 | VAVE-SYN-001 | Cab mounting bracket | 0.904 | 84.1 | Replace the steel cab mounting bracket with an aluminium alloy bracket sized for equivalent stiffness to reduce vehicle mass. |
| EQ-001 | VAVE-H-0001 | Cab mounting bracket | 0.902 | 84.1 | (same text as SYN-001) |
| EQ-001 | VAVE-SYN-018 | Cab mounting bracket | 0.899 | 84.1 | (same text as SYN-001) |
| EQ-001 | VAVE-SYN-017 | Cab mounting bracket | 0.897 | 72.6 | Substitute an aluminium alloy for the existing steel bracket that mounts the cab, keeping stiffness unchanged so that mass and cost fall. |
| EQ-001 | VAVE-SYN-016 | Steering column lower bracket | 0.717 | 86.4 | Replace the steel steering column lower bracket with an aluminium alloy bracket of equivalent stiffness. |
| EQ-002 | VAVE-SYN-017 | Cab mounting bracket | 0.904 | 68.1 | (as above) |
| EQ-002 | VAVE-SYN-001 | Cab mounting bracket | 0.892 | 62.2 | (as above) |
| EQ-002 | VAVE-H-0001 | Cab mounting bracket | 0.889 | 62.2 | (as above) |
| EQ-002 | VAVE-SYN-018 | Cab mounting bracket | 0.885 | 62.2 | (as above) |
| EQ-002 | VAVE-H-0003 | Cab mounting bracket | 0.827 | 57.4 | Redesign the cab mounting bracket as a topology-optimised steel casting, removing material only from low-stress regions while keeping the steel grade. |

- EQ-001: "Replace the steel cab mount bracket with an aluminium alloy bracket of equivalent stiffness to cut vehicle mass." EQ-002: "Cab mounting bracket to be changed from steel to aluminium alloy, section resized so stiffness is unchanged."
- **SYN-016 was not caused by the relaxation.** Its component differs. It was flagged before Tier 1 too, through the lexical fuzzy rule (86.4), which does not require a matching component. With the symmetric fuzzy score on, it was no longer flagged. Since that score was turned off on 28 October, it is flagged again.
- **H-0003 (a steel topology casting) is flagged for EQ-002 by the semantic route at 0.827.** EQ-002's wording ("to be changed from …") contains no action keyword: "changed" is not in the verb list. So the action check is skipped and nothing compares the query's steel → aluminium pair with H-0003, which has none.

## Tier 1 changes

| Setting | Rule |
| --- | --- |
| `component_fuzzy_match` | Both component names are normalised, parenthetical qualifiers are dropped, and `brkt`/`bkt` → bracket, `mtg` → mounting, `assy` → assembly are expanded. The names match if RapidFuzz `ratio` is **≥ 90**. When off, normalised names must be identical. |
| `negation_detection` | An action keyword counts as not proposed if it falls within **5 tokens after** a negation cue (`do not`, `don't`, `never`, `without`, `instead of`, `rather than`, `keep`, `retain`, `no change to`) in the same clause. The cue's own words are discounted too. Clauses end at `. , ; : ! ?` followed by a space, and at a line break. |
| `reversal_detection` | *Removed in Tier 2* (see above). It read revert / return / restore / reinstate / roll back as a direction flip of a shared action kind, but only when the verb opened a clause or a back-reference followed it. |

Across all 38 distinct component names in the seed data, the v2 set and this set, the only pairs that reach 90 are the intended variants. The closest pair of different components is "Alternator mounting bracket" and "Radiator mounting bracket" at 84.6. Note that "Low-voltage battery tray" and "Battery tray (LV)" do not match.

**Tier 1 on v2:** no pair changed. None of the 181 v2 texts changes its action set under negation or reversal detection, and all v2 component names are written in full. That shows no harm on v2, not general safety. (Measured on 122 ideas at the time; the clean 111-idea baseline confirms the same figures.)

## Setup

### Database state

- **Runs 1 and 2:** the Ideas sheet was imported for real (batch `e4762c9e`), giving 122 historical ideas.
- **Since run 3:** those 11 ideas were deleted ([evaluation-results.md](evaluation-results.md#v2-hard-set-clean-baseline-27-october-2026)), and the database has 111. `scripts/score_edge.py` loads the Ideas sheet inside a transaction (preview, commit and re-index, as the import endpoints do), scores each query in a savepoint, and rolls everything back. Every edge-case run still sees 122 historical ideas, and the database is left at 111.

### Pipeline (live stored settings)

| Setting | Run 1 | Run 2 | Run 3 |
| --- | --- | --- | --- |
| AI mode, embedding, language model | offline, `all-MiniLM-L6-v2`, Ollama not reachable (every verdict from `classify_pair`) | same | same |
| `semantic_duplicate_threshold` | 0.82 | 0.82 | 0.82 |
| `retrieval_top_k`, `cosine_retrieve_threshold`, `fuzzy_strong_threshold` | 15, 0.40, 86 | same | same |
| `component_fuzzy_match`, `negation_detection` | — | on | on |
| `reversal_detection` | — | on | removed |
| `direction_detection`, `scope_comparison`, `symmetric_lexical_fuzzy` | — | — | on |

### Method

Command: `HF_HUB_OFFLINE=1 backend/.venv/bin/python scripts/score_edge.py data/vave_duplicate_edge_cases.xlsx out.json [--disable SETTING …]`. Runs 1 and 2 used an earlier copy of this script, kept outside the repository, that ran the same steps against the imported ideas.

- **Each of the 18 TestQueries** is created as a submission with `create_submission` and analysed with `analyze_submission`, using the application's own runtime.
- **End to end:** the category the pipeline gave the labelled candidate. A candidate that was not shown counts as not a duplicate.
- **Classifier only:** `classify_pair` on the labelled pair, whatever retrieval did. It agrees with end to end on every pair except EQ-007, in every run.
- **Scoring.** A pair labelled `duplicate` is correct only if it was called Potential Duplicate. A pair labelled `similar_but_distinct` or `related_not_duplicate` is correct whenever it was **not** called Potential Duplicate, as the workbook's Cover sheet specifies. Insufficient Evidence counts as not a duplicate.
- **Cosine** is computed directly between the query's vector and the candidate's stored vector. It equals the pipeline's vector-search score to three decimals.

## Per-pair results

Fuzzy is RapidFuzz `token_set_ratio` on the comparison text (0–100). Jaccard is word overlap of the pair text. Cosine, fuzzy, Jaccard and retrieval position are the same in every run. "Retr. pos." is the candidate's position in retrieval order (exact, then fuzzy, then cosine) among the 122 historical ideas; only the first 15 are shown. "Shown rank" is after the display re-sort by verdict, in run 3.

| Query | Candidate | Case type | Label | Run 1 | Run 2 | Run 3 | Correct (3) | Cosine | Fuzzy | Jaccard | Retr. pos. | Shown rank (3) | Reason (run 3) |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| EQ-001 | EH-001 | component_name_variant | duplicate | Insufficient | **Potential Dup.** | Potential Dup. | yes | 0.920 | 84.7 | 0.552 | 2 | 1 | components match (91.9); cosine ≥ 0.82; same steel → aluminium pair |
| EQ-002 | EH-001 | component_name_variant | duplicate | Insufficient | **Potential Dup.** | Potential Dup. | yes | 0.902 | 65.2 | 0.242 | 3 | 2 | components match; cosine ≥ 0.82 |
| EQ-003 | EH-002 | component_name_variant | duplicate | Insufficient | **Potential Dup.** | Potential Dup. | yes | 0.938 | 84.3 | 0.567 | 2 | 1 | components match; cosine ≥ 0.82 |
| EQ-004 | EH-003 | opposite_direction | similar_but_distinct | Potential Dup. | Potential Dup. | **Similar but Distinct** | yes | 0.827 | 67.6 | 0.351 | 1 | 7 | increase 1.2 → 1.5 mm against decrease 1.5 → 1.2 mm |
| EQ-005 | EH-004 | opposite_direction | similar_but_distinct | Potential Dup. | Potential Dup. | **Similar but Distinct** | yes | 0.847 | 67.3 | 0.316 | 1 | 9 | increase 5 → 6 mm against decrease 6 → 5 mm |
| EQ-006 | EH-005 | opposite_direction | similar_but_distinct | Potential Dup. | Potential Dup. | **Similar but Distinct** | yes | 0.912 | 64.5 | 0.294 | 1 | 13 | increase 50 → 60 mm against decrease 60 → 50 mm |
| EQ-007 | EH-006 | negation | similar_but_distinct | not shown | not shown | not shown | yes | 0.896 | 58.8 | 0.186 | 18 | — | not shown (classifier alone: deletion against material substitution) |
| EQ-008 | EH-007 | negation | similar_but_distinct | Potential Dup. | **Similar but Distinct** | Similar but Distinct | yes | 0.856 | 74.7 | 0.222 | 1 | 11 | "do not commonise" discounted; topology against commonisation |
| EQ-009 | EH-001 | sparse_description | duplicate | Potential Dup. | Potential Dup. | Potential Dup. | yes | 0.883 | 77.2 | 0.185 | 2 | 2 | same component; cosine ≥ 0.82; no action or state pair in query |
| EQ-010 | EH-008 | sparse_description | duplicate | Potential Dup. | Potential Dup. | Potential Dup. | yes | 0.845 | 71.4 | 0.167 | 1 | 1 | same component; cosine ≥ 0.82; no action or state pair in query |
| EQ-011 | EH-002 | superset | similar_but_distinct | Potential Dup. | Potential Dup. | **Similar but Distinct** | yes | 0.927 | 90.2 | 0.442 | 1 | 12 | scope: query adds `dimension` ("relocate 40 mm rearward") |
| EQ-012 | EH-009 | superset | similar_but_distinct | Potential Dup. | Potential Dup. | **Similar but Distinct** | yes | 0.876 | 90.6 | 0.450 | 2 | 7 | scope: query adds `dimension` ("extend 40 mm rearward") |
| EQ-013 | EH-001 | reversal | similar_but_distinct | Potential Dup. | **Similar but Distinct** | Similar but Distinct | yes | 0.857 | 59.8 | 0.195 | 1 | 14 | flipped: aluminium → steel against steel → aluminium |
| EQ-014 | EH-010 | reversal | similar_but_distinct | Potential Dup. | **Similar but Distinct** | Similar but Distinct | yes | 0.889 | 64.0 | 0.275 | 2 | 13 | flipped: PET → phenolic against phenolic → PET |
| EQ-015 | EH-001 | different_programme | related_not_duplicate | Potential Dup. | Potential Dup. | Potential Dup. | no | 0.859 | 65.2 | 0.250 | 1 | 2 | same component; cosine ≥ 0.82 (programme not compared) |
| EQ-016 | EH-004 | different_programme | related_not_duplicate | Potential Dup. | Potential Dup. | Potential Dup. | no | 0.886 | 65.0 | 0.244 | 1 | 1 | same component; cosine ≥ 0.82 (programme not compared) |
| EQ-017 | EH-003 | unit_variation | duplicate | Potential Dup. | Potential Dup. | Potential Dup. | yes | 0.969 | 94.5 | 0.656 | 1 | 1 | lexical and semantic; both sides decrease (0.059 in = 1.499 mm) |
| EQ-018 | EH-011 | unit_variation | duplicate | Potential Dup. | Potential Dup. | Potential Dup. | yes | 0.981 | 94.4 | 0.676 | 2 | 1 | lexical and semantic; no state pair ("by 0.2 inch") |

## By case type

### component_name_variant: 3 of 3 since Tier 1

Component matching makes "Cab mount brkt" (91.9, clearing 90 by 1.9 points), "Cab Mtg Bkt" and "Battery tray (LV)" match. Cosine was already 0.902 – 0.938. EQ-001 and EQ-002 also reach the same steel → aluminium state pair as the candidate, so direction extraction agrees with the verdict. The relaxation also lets these queries reach other cab-bracket ideas (see [Pairs flagged after component relaxation](#pairs-flagged-after-component-relaxation)).

### opposite_direction: 0 → 3 of 3 with direction extraction

**Run 1 and 2 layer: keyword action detection.** Both sides map to `{dimension}`, so the action check saw the same kind of change, and the semantic route accepted the pairs at 0.827 – 0.912. **Run 3:** each side states its change as "from X mm to Y mm", the directions are opposite, and the pair is Similar but Distinct whatever the cosine. Stage A (direction only) already gives 3 of 3.

### negation: 2 of 2 since Tier 1

- **EQ-008** passes because "do not commonise" is discounted and the remaining `topology` ("casting") is disjoint from the candidate's `commonisation`. A query that only ruled out the candidate's change, with no other action, would still be accepted by the semantic route.
- **EQ-007** is unchanged: 18th in retrieval order (fuzzy 58.75, 0.85 below the 15th candidate), although its cosine (0.896) is higher than every candidate shown. It scores as correct only because it was not shown. **Layer: candidate selection.**

### sparse_description: 2 of 2

Neither query has an action keyword or a state pair, so no check applies and the semantic route decides on cosine alone (0.883, 0.845). This is the same mechanism that produced the run 1 false positives. It passes here because these queries are duplicates.

### superset: 0 → 2 of 2 with scope comparison

**Run 1 and 2 layer: the containment-friendly fuzzy score (90.2, 90.6 against 86); action detection was secondary.** **Run 3:** both queries add a second kind of change (`dimension`, from "40 mm rearward") to the candidate's `material_substitution`, so they are scope mismatches. The symmetric fuzzy score on its own does not fix them (stage D: direction and symmetric score on, scope off, still 0 of 2), because the semantic route still accepts them. The scope rule depends on the added change being detectable. Here it is detected because the text contains "mm". A relocation described without a measurement would not be.

### reversal: 2 of 2 since Tier 1, now through direction extraction

Run 2 used reversal verbs. Run 3 reads the reversal as a flipped material pair: "from aluminium alloy back to the original steel" (aluminium → steel) against "replace the steel … with an aluminium alloy bracket" (steel → aluminium), and PET → phenolic against phenolic → PET. With direction extraction off (stage Z), both fail again, because the verb rule no longer exists.

### different_programme: 0 of 2 (still failing, not addressed)

The semantic route fires (0.859, 0.886), and nothing compares vehicle programmes. Per the brief, this was not worked on: every row of the workbook has identical vehicle volumes, so the test data cannot exercise a programme check.

### unit_variation: 2 of 2

Both pass on fuzzy score (94.5, 94.4). EQ-017's inches are converted, so its decrease matches the candidate's. EQ-018 has no state pair ("by 0.2 inch"), so nothing checked its units.

## Route off, for comparison (run 1)

This table was derived from run 1's recorded scores. It was not re-run, and it predates both tiers. With `semantic_duplicate_threshold` = `null`, the eight pairs the semantic route accepted in run 1 would have fallen to Insufficient Evidence:

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

In run 1, no single threshold separated these labels: the two duplicates the semantic route accepted scored 0.845 and 0.883, and the eight false positives scored 0.827 – 0.912. After Tier 2, the only negatives the route still accepts are the two different_programme pairs.

## Limitations

- Each case type has two or three pairs, and each query has one labelled candidate. A case type that passed has only shown that it *can* pass.
- **This set is no longer independent evidence for the rules.** Every Tier 1 and Tier 2 rule was written after reading these failures. No threshold or cue list was tuned on them, but a fresh set is needed to measure the rules fairly. On v2, which none of the rules was written against, Tier 1 and direction extraction never fire, and scope comparison fires once.
- **The rules are keyword- and pattern-based.** Direction needs "from X to Y", "replace X with Y" or "substitute Y for X", with a listed material or a length unit. Scope needs both sides to have a detected kind of change. Wording outside those patterns falls back to cosine.
- The workbook is synthetic, and every historical idea in it uses the same vehicle volumes.
- Ollama was not reachable, so the optional language-model rerank played no part. Every verdict is heuristic.
- Only the labelled pair per query is scored. Retrieval competition comes from the 111 other historical ideas.
