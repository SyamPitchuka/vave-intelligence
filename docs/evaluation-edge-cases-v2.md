# Evaluation results: edge-case set v2

Measured on 28 October 2026 against the hosted Neon development database, with the live stored settings. The workbook is `data/vave_duplicate_edge_cases_v2.xlsx`, and `scripts/edge_cases_v2.py` generates it. It has 14 historical ideas (VAVE-FH-001 to -014), 22 queries (VAVE-FQ-001 to -022) and 22 labelled pairs. `scripts/measure_v2.py` prints its lexical properties.

**This set is a different instrument from [set v1](evaluation-edge-cases.md).** Set v1 was written without sight of the classifier, and every case in it was something the system got wrong. Set v2 was written knowing which rules exist. It probes their weak directions and gives each probe type a positive and a negative case, so a rule that fires too readily loses marks. That makes it a stronger test of over-firing and a weaker test of generalisation. It does not replace a held-out set written blind.

## Summary

- **10 of 22 pairs fail, and every failure is a negative that was flagged as a Potential Duplicate.** All 6 positives pass; 6 of 16 negatives pass.
- **The new component subset guard changes no verdict on either edge set or on the v2 hard set.** The failures it was meant to fix happen in a layer that never looks at the component name ([details](#component-matching-which-scorer-and-the-prediction)).
- **The component threshold doesn't decide any v2 edge verdict anywhere from 80 to 95.** Across the whole sweep on both edge sets, one verdict flips: v1's EQ-001 fails at 92 and above ([sweep](#component-threshold-sweep-80-to-95)).
- **The symmetric fuzzy score is off.** Turning it off changed no labelled pair on the v2 hard set or on either edge set.
- **The v2 hard set hasn't regressed:** precision 0.890, recall 0.811, F1 0.849, rank@1 0.833.
- **No threshold was changed.**

## Changes in this run

| Setting | Change |
| --- | --- |
| `symmetric_lexical_fuzzy` | Default changed from on to off in `config.py`. The dev database's stored row has no key for it, so the default applies there. **The finding still stands:** `token_set_ratio` is containment-friendly. A query that contains the candidate's text plus more scores 90 or above (v1 superset queries 90.2 and 90.6; v2 qualifier queries 100.0). Scope comparison fixes the v1 superset cases, not the symmetric score. |
| `component_subset_guard` (new, default on) | Part of fuzzy component matching (`components_match` with `subset_guard=True`). Both names are normalised first: abbreviations expanded, parenthetical qualifiers dropped. The names are then a **different component** in two cases: one name's words are a strict subset of the other's and the extra words include anything other than `assembly`, `part`, `component`, `unit` or `complete`; or either name has a positional or ordinal qualifier that the other lacks. The qualifiers are front, rear, upper, lower, left, right, LH, RH, inner, outer, first and second. The guard runs before the fuzzy threshold, so a score of 100 can't get past it. The second case also covers names where neither contains the other: "LH tail lamp lens" and "RH tail lamp lens" score 94.1 on `fuzz.ratio`, enough to match at 90 without the guard (upper against lower door hinge bracket scores 87.5). |

`scripts/score_edge.py` now also:

- reads `Probe_Type` and `Polarity` (v2) as well as `Case_Type` (v1)
- reports three outcomes: correct, wrong, and not retrieved
- lists every unlabelled Potential Duplicate with its text, component, cosine and fuzzy score
- replays the component threshold with `--sweep-component LO HI`
- analyses a query that the submit form would refuse as a draft, and marks it

## Component matching: which scorer, and the prediction

**Component matching doesn't use `token_set_ratio`.** `components_match` compares the normalised names with `fuzz.ratio` at 90 or above. `token_sort_ratio` is used only by the lexical duplicate rule, and only when `symmetric_lexical_fuzzy` is on. So the premise that the qualifier names score exactly 100 and clear every threshold doesn't hold for component matching:

| Query | Query component | Candidate component | `fuzz.ratio` (used) | `token_sort_ratio` | `token_set_ratio` |
| --- | --- | --- | --- | --- | --- |
| FQ-001 | Cab mounting damper | Cab mounting bracket | 76.9 | 61.5 | 77.4 |
| FQ-002 | Front spring shackle | Front spring bracket | 85.0 | 60.0 | 85.0 |
| FQ-003 | Door check bracket | Door hinge bracket | 83.3 | 66.7 | 83.3 |
| FQ-004 | Front spring bracket rear | Front spring bracket | 88.9 | 88.9 | 100.0 |
| FQ-005 | Door hinge bracket lower | Door hinge bracket | 85.7 | 85.7 | 100.0 |
| FQ-006 | Exhaust heat shield front | Exhaust heat shield | 86.4 | 86.4 | 100.0 |
| v1 EQ-001 (positive) | Cab mount brkt → cab mount bracket | Cab mounting bracket | 91.9 | 91.9 | 91.9 |

**The prediction, stated before the run:**

- **The components wouldn't match.** At 90, all six negatives fall below the `fuzz.ratio` threshold.
- **The three qualifier negatives would fail anyway**, along with at least two of the three variant negatives. The lexical duplicate rule (fuzzy ≥ 86 or Jaccard ≥ 0.62) never checks the component, and these descriptions differ by a word or two.

**Measured, the prediction held.** All six pairs got `same_component = False`. The three qualifier negatives and FQ-002 and FQ-003 were still called Potential Duplicate by the lexical rule, on fuzzy 100.0, 100.0, 100.0, 97.5 and 97.4. The query contains the candidate's whole description plus one qualifier word, and `token_set_ratio` scores that 100. FQ-001 passed only because its fuzzy score (83.2) and Jaccard (0.533) both fell short of the lexical rule.

**So the subset guard is correct but has nothing to act on in this set.** It would matter if the component threshold were lowered (at 88 or below, FQ-004's name matches without it), or for a pair worded differently enough to miss the lexical rule. **What would fix these five failures** is making the lexical rule respect a component mismatch. That wasn't in scope, so it has not been done.

## Results by probe type

End to end, with the live settings. The "guard off" and "guard on" columns come from the same code, run one after the other with `--disable component_subset_guard` and without it. They're identical.

| Probe type | Polarity | Label | Pairs | Guard off: correct / wrong / not retrieved | Guard on: correct / wrong / not retrieved |
| --- | --- | --- | --- | --- | --- |
| component_variant_negative | negative | similar_but_distinct | 3 | 1 / **2** / 0 | 1 / **2** / 0 |
| component_qualifier_negative | negative | similar_but_distinct | 3 | 0 / **3** / 0 | 0 / **3** / 0 |
| reversal_no_states | negative | similar_but_distinct | 2 | 2 / 0 / 0 | 2 / 0 / 0 |
| scope_substantive | negative | similar_but_distinct | 1 | 0 / **1** / 0 | 0 / **1** / 0 |
| different_programme | negative | related_not_duplicate | 2 | 1 / **1** / 0 | 1 / **1** / 0 |
| negation_only | negative | similar_but_distinct | 2 | 0 / **2** / 0 | 0 / **2** / 0 |
| sparse_negative | negative | similar_but_distinct | 3 | 2 / **1** / 0 | 2 / **1** / 0 |
| **negatives** | | | **16** | **6 / 10 / 0** | **6 / 10 / 0** |
| direction_agreement | positive | duplicate | 3 | 3 / 0 / 0 | 3 / 0 / 0 |
| scope_cosmetic | positive | duplicate | 2 | 2 / 0 / 0 | 2 / 0 / 0 |
| same_programme_negative | positive | duplicate | 1 | 1 / 0 / 0 | 1 / 0 / 0 |
| **positives** | | | **6** | **6 / 0 / 0** | **6 / 0 / 0** |

The per-type totals cover 22 pairs: 16 negatives and 6 positives. (The workbook's `same_programme_negative` is labelled `duplicate` with polarity `positive`.) Every labelled candidate was retrieved and shown. The classifier-only verdicts match the end-to-end ones on every pair.

## Per-pair results and failing layer

Cosine is the direct query-candidate cosine (MiniLM). Fuzzy is `token_set_ratio` on the comparison text, the score retrieval and the lexical rule use. "Same comp." is `components_match` with the live settings.

| Query | Candidate | Probe type | Verdict | Outcome | Cosine | Fuzzy | Same comp. | Layer that decided it |
| --- | --- | --- | --- | --- | --- | --- | --- | --- |
| FQ-001 | FH-001 | component_variant_negative | Insufficient Evidence | correct | 0.813 | 83.2 | no | Component mismatch keeps the semantic route closed, and fuzzy 83.2 is under the lexical 86 |
| FQ-002 | FH-002 | component_variant_negative | Potential Duplicate | **wrong** | 0.835 | 97.5 | no | **Lexical rule**: ignores the component mismatch |
| FQ-003 | FH-003 | component_variant_negative | Potential Duplicate | **wrong** | 0.881 | 97.4 | no | **Lexical rule**: ignores the component mismatch |
| FQ-004 | FH-002 | component_qualifier_negative | Potential Duplicate | **wrong** | 0.971 | 100.0 | no | **Lexical rule**: `token_set_ratio` 100 for a containing text |
| FQ-005 | FH-003 | component_qualifier_negative | Potential Duplicate | **wrong** | 0.982 | 100.0 | no | **Lexical rule**, as FQ-004 |
| FQ-006 | FH-004 | component_qualifier_negative | Potential Duplicate | **wrong** | 0.971 | 100.0 | no | **Lexical rule**, as FQ-004 |
| FQ-007 | FH-005 | direction_agreement | Potential Duplicate | correct | 0.977 | 85.2 | yes | Lexical rule (same action, Jaccard 0.571). Both sides parse as decreases, so no conflict |
| FQ-008 | FH-006 | direction_agreement | Potential Duplicate | correct | 0.985 | 94.5 | yes | Lexical rule. "down by 1 mm" gives no state pair, so there's nothing to conflict with |
| FQ-009 | FH-007 | direction_agreement | Potential Duplicate | correct | 0.989 | 88.1 | yes | Lexical rule. "away from X and over to Y" gives no state pair and no detected action |
| FQ-010 | FH-001 | reversal_no_states | Insufficient Evidence | correct | 0.816 | 54.5 | yes | Cosine 0.816 is under 0.82. **Not** direction detection, which finds no state pair |
| FQ-011 | FH-008 | reversal_no_states | Insufficient Evidence | correct | 0.629 | 53.6 | yes | Cosine under 0.82, as FQ-010 |
| FQ-012 | FH-009 | scope_cosmetic | Potential Duplicate | correct | 0.966 | 100.0 | yes | Lexical rule. The part-marking clause isn't a detected kind of change, so scope doesn't fire |
| FQ-013 | FH-004 | scope_cosmetic | Potential Duplicate | correct | 0.941 | 98.9 | yes | Lexical rule, as FQ-012 |
| FQ-014 | FH-010 | scope_substantive | Potential Duplicate | **wrong** | 0.897 | 78.6 | yes | **Action detection → semantic route.** The candidate's steel → glass-filled nylon change isn't detected ("nylon" isn't in the change-type material list), so it has no detected action and scope comparison can't apply. The query's "25 mm" is detected as `dimension` |
| FQ-015 | FH-011 | different_programme | Potential Duplicate | **wrong** | 0.834 | 65.2 | yes | **Semantic route; no programme comparison exists.** The volumes differ (tipper only against rigid only), but nothing reads them |
| FQ-016 | FH-012 | different_programme | Insufficient Evidence | correct | 0.817 | 67.1 | yes | Cosine 0.817, **0.003 under 0.82**. Passes by margin, not by any programme check |
| FQ-017 | FH-013 | same_programme_negative | Potential Duplicate | correct | 0.924 | 79.6 | yes | Lexical rule (same action, Jaccard 0.515) |
| FQ-018 | FH-014 | negation_only | Potential Duplicate | **wrong** | 0.942 | 62.8 | yes | **Negation → semantic route.** "should not be taken forward" isn't a cue, so the material change still counts on both sides |
| FQ-019 | FH-009 | negation_only | Potential Duplicate | **wrong** | 0.933 | 74.5 | yes | **Semantic route.** Negation works: "Do not proceed" and "Retain" leave the query with no detected action. But a query with no action is "no different action", so the route accepts it |
| FQ-020 | FH-001 | sparse_negative | Insufficient Evidence | correct (refused at submit) | 0.749 | 61.1 | no | Component mismatch. The submit form also refuses "Al bracket." as under 20 characters |
| FQ-021 | FH-005 | sparse_negative | Insufficient Evidence | correct | 0.810 | 50.0 | yes | Cosine 0.810, **0.01 under 0.82**. No conflict was detected, so this passes by margin |
| FQ-022 | FH-007 | sparse_negative | Potential Duplicate | **wrong** (refused at submit) | 0.832 | 58.5 | yes | **Direction → semantic route.** "PC instead of PMMA" isn't a state-pair pattern, and "instead of" is a negation cue. The submit form refuses this 19-character text, so in the product it never reaches analysis |

**Three passes rest on cosine falling just under 0.82, not on the rule their probe tests:** FQ-010, FQ-016 and FQ-021. A different embedding model, or a threshold change, could turn them into failures.

## Component threshold sweep, 80 to 95

`score_edge.py --sweep-component 80 95` replays `classify_pair` on every labelled pair at each integer threshold. It reuses the retrieval results, which don't depend on the verdict. Both edge sets were swept with the guard off and on.

| Set | Probe or case type | Correct at 80 … 91 | Correct at 92 … 95 | Flips at |
| --- | --- | --- | --- | --- |
| v1 | component_name_variant (3 positives) | 3 | 2 | **92**: EQ-001 "Cab mount brkt" at 91.9 stops matching and falls back to Insufficient Evidence |
| v1 | every other case type | unchanged | unchanged | none |
| v2 | every probe type, guard off or on | unchanged | unchanged | none |

The verdicts don't move, but the component *match* does. Without the guard, as the threshold falls:

- FQ-004 ("…rear") matches at 88 or below.
- FQ-006 ("…front") matches at 86 or below.
- FQ-005 ("…lower") and FQ-002 ("shackle") match at 85 or below.
- FQ-003 ("check") matches at 83 or below.

With the guard, the three qualifier names never match at any threshold. FQ-002 and FQ-003 still do below 85.0 and 83.3, because their names differ by a substituted word, not an added one. None of this changes a verdict, because those pairs are already flagged by the lexical rule.

**The margin is thin on both sides.** The one positive that needs fuzzy matching (EQ-001, 91.9) is 1.9 points above 90. The closest negative name (FQ-004, 88.9) is 1.1 points below it. Within 80 to 95, these sets only constrain the threshold to between 89 and 91. That rests on one positive pair, and on a negative the guard already handles.

## v2 hard set (run first)

`scripts/evaluate_hard_set.py data/vave_duplicate_eval_set_v2.xlsx`, 111 historical ideas, 597 pairs:

| Run | Precision | Recall | F1 | TP | FP | FN | Mean rank | rank@1 | Pairs changed |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| Tier 2 as committed (symmetric on) | 0.890 | 0.811 | 0.849 | 73 | 9 | 17 | 1.200 | 0.833 | — |
| Symmetric off, guard off | 0.890 | 0.811 | 0.849 | 73 | 9 | 17 | 1.200 | 0.833 | 0 |
| Symmetric off, guard on (live) | 0.890 | 0.811 | 0.849 | 73 | 9 | 17 | 1.200 | 0.833 | 0 |
| Final, after the edge runs | 0.890 | 0.811 | 0.849 | 73 | 9 | 17 | 1.200 | 0.833 | 0 |

Set v1, re-scored with the live settings, has the same verdict on every pair as in [run 3](evaluation-edge-cases.md). The guard changed nothing on it either.

## Unlabelled pairs EQ-001 and EQ-002 flag (set v1, live settings)

With the symmetric score off, the list is the same 10 pairs as before Tier 2.

- **EQ-001** "Cab mount brkt": "Replace the steel cab mount bracket with an aluminium alloy bracket of equivalent stiffness to cut vehicle mass."
- **EQ-002** "Cab Mtg Bkt": "Cab mounting bracket to be changed from steel to aluminium alloy, section resized so stiffness is unchanged."

| Query | Candidate | Component | Cosine | Fuzzy | Candidate text |
| --- | --- | --- | --- | --- | --- |
| EQ-001 | SYN-001 | Cab mounting bracket | 0.904 | 84.1 | Replace the steel cab mounting bracket with an aluminium alloy bracket sized for equivalent stiffness to reduce vehicle mass. |
| EQ-001 | H-0001 | Cab mounting bracket | 0.902 | 84.1 | Same text as SYN-001. |
| EQ-001 | SYN-018 | Cab mounting bracket | 0.899 | 84.1 | Same text as SYN-001. |
| EQ-001 | SYN-017 | Cab mounting bracket | 0.897 | 72.6 | Substitute an aluminium alloy for the existing steel bracket that mounts the cab, keeping stiffness unchanged so that mass and cost fall. |
| EQ-001 | SYN-016 | Steering column lower bracket | 0.717 | 86.4 | Replace the steel steering column lower bracket with an aluminium alloy bracket of equivalent stiffness. |
| EQ-002 | SYN-017 | Cab mounting bracket | 0.904 | 68.1 | As above. |
| EQ-002 | SYN-001 | Cab mounting bracket | 0.892 | 62.2 | As above. |
| EQ-002 | H-0001 | Cab mounting bracket | 0.889 | 62.2 | As above. |
| EQ-002 | SYN-018 | Cab mounting bracket | 0.885 | 62.2 | As above. |
| EQ-002 | H-0003 | Cab mounting bracket | 0.827 | 57.4 | Redesign the cab mounting bracket as a topology-optimised steel casting, removing material only from low-stress regions while keeping the steel grade. |

SYN-016 is flagged by the lexical rule on a different component, the same failure as FQ-002 to FQ-006. H-0003 is flagged by the semantic route: "changed" isn't a change verb, so EQ-002 has no detected action to set against the topology change.

Set v2's unlabelled flags show the same pattern. FQ-006, the front heat shield, is also flagged against H-0056, the unqualified heat shield. FQ-018 and FQ-019, the rejection-only queries, are also flagged against the historical aluminium steering bracket and polypropylene battery tray. The full list is in the run JSON (`unlabelled_flags`).

## Limitations

- **Two or three pairs per probe type.** Each result is about a mechanism, not a rate.
- **The set was written knowing the rules.** It tests over-firing, not generalisation.
- **Two sparse queries are below the 20-character submission minimum.** They were analysed as drafts so the classifier is measured, but in the product a user can't submit them.
- **The live LLM rerank was unavailable** (Ollama not reachable), so every verdict is the heuristic one.
- **The edge-set ideas are loaded and rolled back in one transaction.** The database had 111 historical ideas before and after every run, and no VAVE-FH or VAVE-EH codes.
