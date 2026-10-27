# Evaluation results: deterministic and MiniLM embeddings

Run on 26 October 2026, on Windows 11 with Python 3.14, sentence-transformers 6.2.0, PyTorch 2.14.1 (CPU), and a hosted Neon PostgreSQL database seeded with the synthetic data only.

Two embedding models were compared, both 384 dimensions:

- `deterministic-hash-v1`, the hashed lexical vector used in `fallback` mode
- `sentence-transformers/all-MiniLM-L6-v2`, a local neural model used in `offline` mode

Every number here comes from 12 labelled synthetic cases. Read [Limitations](#limitations) before relying on any of it.

## How cosine is used

Cosine similarity never decides whether an idea is a duplicate. (This describes the code on 26 October 2026. An optional semantic route added on 27 October lets cosine decide when an administrator turns it on; see [evaluation-hard-set.md](evaluation-hard-set.md#semantic-potential-duplicate-route).)

- **The duplicate verdict.**
  - In the evaluation, the category comes from `classify_pair` in `duplicate_detection/classifier.py`. Its inputs are the two texts, the components, the fuzzy score, and the exact-match flag. Cosine is not an input.
  - In the live app, the category comes from the same heuristic and, when a language model is available, from that model's comparison.
- **Ranking.** `rank_historical` sorts candidates by exact match, then fuzzy score, then cosine. Cosine only breaks ties.
- **Candidate filter.** The live app shows a historical idea when `exact OR fuzzy >= 40 OR cosine >= cosine_retrieve_threshold` (`duplicate_detection/service.py`). This is the only place the threshold has an effect.
- **The evaluation never applies `cosine_retrieve_threshold`.** `run_evaluation` stores the value in the run's config, but `_duplicates` does not receive it.

As a result, changing the embedding model cannot change the evaluation's precision, recall, or F1. It can only change the retrieval metrics, and even those only through tie-breaks.

## Precision, recall, and F1

Command: `scripts/evaluate.py --deterministic` for the baseline, and `HF_HUB_OFFLINE=1 scripts/evaluate.py` for MiniLM, with MiniLM active and indexed. Positive class: `duplicate`.

| Embedding | Precision | Recall | F1 | False-positive rate | TP | FP | FN | TN | Abstentions | Top-k success (k=15) | MRR | Copilot hit rate |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| deterministic-hash-v1 | 1.0 | 0.8 | 0.889 | 0 | 4 | 0 | 1 | 7 | 2 | 1.0 | 1.0 | 1.0 |
| all-MiniLM-L6-v2 | 1.0 | 0.8 | 0.889 | 0 | 4 | 0 | 1 | 7 | 2 | 1.0 | 1.0 | 1.0 |

The two rows are identical by construction, for the reasons in [How cosine is used](#how-cosine-is-used).

- **Retrieval figures:** 5 cases with labelled retrieval targets.
- **Copilot figures:** 3 cases. The copilot ranks document chunks by lexical coverage, not by embeddings.

## Cosine by label

Cosine between each labelled query and its labelled historical candidate. The query is embedded from its text only, as `scripts/evaluate.py` does.

| Label | Cases | deterministic-hash-v1 | all-MiniLM-L6-v2 |
| --- | --- | --- | --- |
| duplicate | 5 | 0.595 – 0.695 | 0.814 – 0.892 |
| similar but distinct | 4 | 0.337 – 0.448 | 0.693 – 0.772 |
| unrelated | 3 | 0.000 – 0.399 | 0.273 – 0.428 |

Per case:

| Case | Label | Candidate | Deterministic | MiniLM | Fuzzy |
| --- | --- | --- | --- | --- | --- |
| DUP-AXLE | duplicate | VAVE-SYN-005 | 0.659 | 0.892 | 90.3 |
| DUP-BRAKE | duplicate | VAVE-SYN-002 | 0.649 | 0.838 | 87.1 |
| DUP-EXACT | duplicate | VAVE-SYN-001 | 0.695 | 0.834 | 100.0 |
| DUP-PARAPHRASE | duplicate | VAVE-SYN-001 | 0.595 | 0.814 | 86.0 |
| DUP-STEER | duplicate | VAVE-SYN-016 | 0.693 | 0.872 | 91.1 |
| SIM-BOLT | similar but distinct | VAVE-SYN-001 | 0.337 | 0.693 | 57.0 |
| SIM-GAUGE | similar but distinct | VAVE-SYN-001 | 0.448 | 0.772 | 60.0 |
| SIM-TITANIUM | similar but distinct | VAVE-SYN-001 | 0.438 | 0.697 | 63.5 |
| SIM-TOPOLOGY | similar but distinct | VAVE-SYN-001 | 0.357 | 0.741 | 55.2 |
| UNREL-BEZEL | unrelated | VAVE-SYN-009 | 0.000 | 0.274 | 44.0 |
| UNREL-CHIME | unrelated | VAVE-SYN-001 | 0.000 | 0.273 | 39.3 |
| UNREL-PAD | unrelated | VAVE-SYN-002 | 0.399 | 0.428 | 45.3 |

## Separation between duplicates and look-alikes

Both models rank every labelled duplicate above every non-duplicate. The margin is what differs. It is measured from the lowest duplicate to the highest similar-but-distinct pair:

| Embedding | Lowest duplicate | Highest similar but distinct | Gap |
| --- | --- | --- | --- |
| deterministic-hash-v1 | 0.595 | 0.448 | **0.147** |
| all-MiniLM-L6-v2 | 0.814 | 0.772 | **0.042** |

MiniLM raises every score, duplicates and look-alikes alike. A paraphrase scores higher than before, but so does a different change to the same part. On this set MiniLM does not separate duplicates from similar-but-distinct ideas better than the hashed vector. Its margin is about a third of the size. A high MiniLM cosine on its own is not evidence of a duplicate.

## Threshold sweep

The live candidate filter, `exact OR fuzzy >= 40 OR cosine >= t`, was replayed for each of the 12 labelled queries against the 20 historical ideas. The replay is read-only.

- **Duplicates kept:** labelled duplicate candidates admitted, of 5.
- **Non-duplicates admitted:** labelled similar-but-distinct or unrelated candidates admitted, of 7.
- **Cosine-only admissions:** candidates admitted only because of the cosine rule (not exact, fuzzy < 40), summed over the 12 queries.
- **Shown per query:** the average number of candidates admitted, out of 20.

| Embedding | t | Duplicates kept | Non-duplicates admitted | Cosine-only admissions | Shown per query |
| --- | --- | --- | --- | --- | --- |
| deterministic-hash-v1 | 0.22 | 5 | 6 | 2 | 19.8 |
| deterministic-hash-v1 | 0.30 | 5 | 6 | 1 | 19.8 |
| deterministic-hash-v1 | 0.40 – 0.80 | 5 | 6 | 0 | 19.7 |
| all-MiniLM-L6-v2 | 0.22 | 5 | 7 | 4 | 20.0 |
| all-MiniLM-L6-v2 | 0.30 | 5 | 6 | 2 | 19.8 |
| all-MiniLM-L6-v2 | 0.40 – 0.80 | 5 | 6 | 0 | 19.7 |

The values 0.40, 0.50, 0.60, 0.65, 0.70, 0.75, and 0.80 were each tested and gave identical rows, so they are combined above.

Only 4 query–candidate pairs have fuzzy < 40, so only these depend on the threshold:

| Query | Candidate | Deterministic | MiniLM |
| --- | --- | --- | --- |
| SIM-TITANIUM | VAVE-SYN-003 | 0.296 | 0.388 |
| UNREL-BEZEL | VAVE-SYN-019 | 0.354 | 0.313 |
| UNREL-CHIME | VAVE-SYN-018 | 0.000 | 0.273 |
| UNREL-CHIME | VAVE-SYN-001, labelled unrelated | 0.000 | 0.273 |

### Decision

`cosine_retrieve_threshold` was raised from 0.22 to **0.40**:

- **Live:** set on 26 October 2026 with `PUT /api/v1/ai/settings` as `admin@vave.local`, which is recorded in the audit log.
- **New setups:** set in `.env.example`.
- **Code default:** stays at 0.22 in `app/core/config.py`, because the integration tests run on that default and have not been re-run.

Reasons:

- **At 0.22, MiniLM admits all 4 low-fuzzy pairs on cosine alone.** That includes UNREL-CHIME → VAVE-SYN-001, which is labelled unrelated.
- **0.40 is the lowest tested value with no cosine-only admissions for either model,** and every labelled duplicate is kept at it.
- **No tested value above 0.40 changes anything,** so a higher value gains nothing on this data and leaves less room for real paraphrases with low fuzzy scores.

The practical effect is small. `fuzzy >= 40` already admits about 19.7 of the 20 historical ideas per query, and every labelled duplicate has fuzzy ≥ 86. The fuzzy cut-off controls the candidate list far more than the cosine threshold does. It was not tuned, because 12 cases are too few.

## Defects fixed

Both were fixed in commit `9050064`.

1. **`scripts/evaluate.py` always evaluated the deterministic model.**
   - **Defect:** the script built `DeterministicEmbeddingProvider()` directly, whatever the AI settings said. With MiniLM active, it still reported deterministic figures and could not measure the active model at all.
   - **Fix:** it now builds the active provider with `build_embedding_provider`, prints the model name, and keeps the baseline behind `--deterministic`.
2. **First-start settings ignored `EMBEDDING_PROVIDER` outside `online` mode.**
   - **Defect:** `settings_store._defaults` used the configured embedding provider only when `AI_MODE=online`. A fresh database with `AI_MODE=offline` and `EMBEDDING_PROVIDER=sentence_transformers` therefore started on deterministic embeddings, with no message, even though `effective_ai` allows that combination.
   - **Fix:** a new `_default_embedding` applies the same rules as `effective_ai`. Fallback mode is always deterministic, non-online modes never select OpenAI, and anything else uses the configured provider. A unit test covers all three cases.

## Observed examples

These come from duplicate analysis `a8555c14-8649-4e7a-a3c7-d410e33c301f`, run on 26 October 2026:

- **Submission:** VAVE-NEW-00007, component `Cab mounting bracket`, department `Cab`. The description was the DUP-PARAPHRASE text, with no other fields.
- **Settings:** MiniLM embeddings, `cosine_retrieve_threshold` 0.22 (before the change to 0.40), and Ollama unavailable, so every category comes from the heuristic in `classify_pair`.
- **Verification:** the stored category was recomputed from the classifier's inputs for all 15 candidates and matched every time.

The rules below are from `classifier.py`:
- **Potential duplicate** needs one of:
  - fuzzy ≥ 86
  - Jaccard word overlap ≥ 0.62
  - the same component, the same detected kind of change, Jaccard ≥ 0.42, and fuzzy ≥ 68

  It also requires that the two kinds of change do not contradict each other.
- **No strong match** needs fuzzy < 48 and Jaccard < 0.18.

Cosine is not an input to any of these rules.

### 1. The highest cosine lost to a lower one on word overlap

| Candidate | Cosine | Fuzzy | Jaccard | Verdict |
| --- | --- | --- | --- | --- |
| VAVE-SYN-017 | **0.855865** (highest) | 79.80 | 0.3750 | Insufficient Evidence |
| VAVE-SYN-001 | 0.825851 | 85.98 | 0.4242 | Potential Duplicate |

Neither candidate reaches fuzzy 86, so that rule does not separate them.
- **VAVE-SYN-001** qualifies through the same-component, same-action route: both texts are detected as material substitution, its Jaccard of 0.4242 clears 0.42, and its fuzzy of 85.98 clears 68.
- **VAVE-SYN-017** has the same component and the same detected action, and its fuzzy of 79.8 clears 68. It fails only on Jaccard: 0.375 against 0.42. It then falls through to Insufficient Evidence.

VAVE-SYN-017 is itself a reworded copy of VAVE-SYN-001 in the synthetic data. Its rationale reads "Same material substitution as a steel-to-aluminium cab mount bracket". The candidate the embedding rated most similar was the one the verdict rejected, and VAVE-SYN-001 passed by only 0.004 of Jaccard. The verdict follows the words the two texts share, not their meaning.

### 2. A high-cosine look-alike was correctly separated by keywords

VAVE-SYN-019 (cosine 0.775903, fuzzy 53.87, Jaccard 0.1395) was called **Similar but Distinct**, which is correct. It is a topology-optimised steel casting, not a material change.
- **What decided it:** the detected kind of change differs: `material_substitution` for the query against `topology` for the candidate.
- **Where that comes from:** `change_types()`, which matches keywords in the free text. "topology", "optimized", and "casting" mean topology; a material word such as "aluminum" with a verb such as "use" or "replace" means material substitution. It is not a structured field.
- **What did not decide it:** the embedding. At 0.776 the cosine was close to the true duplicates' 0.826 – 0.834.

A paraphrase that avoids those keywords would lose this protection.

### 3. A different component was sent to manual review

VAVE-SYN-008 (`Headliner substrate`, cosine 0.423434, fuzzy 49.45, Jaccard 0.0714) was called **Insufficient Evidence / Manual Review Required**, not No Strong Match.
- **Why:** its fuzzy score of 49.45 is just above the 48 cut-off for No Strong Match. Its detected kinds of change (`dimension`, `material_substitution`) overlap the query's, so it was not treated as a different mechanism either, and it falls through to Insufficient Evidence.
- **Cosine played no part.**
- **Other unrelated parts got the same verdict:** VAVE-SYN-016 (`Steering column lower bracket`, fuzzy 75.14) and VAVE-SYN-005 (`Rear axle banjo housing`, fuzzy 48.61).

In this one run, 4 of the 15 candidates were sent to manual review. Only VAVE-SYN-017 was related to the query. If that rate holds on real history, reviewers would spend much of their time on parts that are clearly unrelated. That risks reviewer fatigue, and with it the chance that a real duplicate is waved through. This is a risk, not a measured effect.

### Fixed defect: submissions crowded historical ideas out of vector search

In the same run, four historical candidates had **no** cosine score: VAVE-SYN-004, -012, -006, and -002.

- **Cause:** `rank_historical` asked `search_similar` for the top `max(retrieval_k, 20)` idea vectors and filtered only by entity type and model, not by origin.
- **State at the time:** the index held 27 MiniLM idea vectors, 20 historical and 7 earlier test submissions. The submissions are near-copies of the query, so they took 7 of the 20 slots.
- **Effect:** the problem grew with every stored submission. A historical idea pushed out of the top 20 could still be shown through the fuzzy rule, but its cosine did not count for ranking or the filter.
- **Fix:** `search_similar` takes an optional `entity_ids` select, applied before the limit. `rank_historical` passes the historical idea ids (excluding the submission itself), so submissions can no longer take slots. `tests/integration/test_vector_search.py` stores 25 identical submissions and checks that all 20 historical ideas still get a cosine. It fails without the fix.

#### Re-run after the fix

Run on 26 October 2026 on the same Neon database, MiniLM active, 20 historical and 7 submission vectors in the index.

- **The evaluation was affected too.** Before the fix, every one of the 12 labelled queries was missing cosine for 7 historical ideas, one per stored submission. After it, none are missing. This was measured read-only by running each query through `rank_historical` with and without the filter.
- **Nothing that the metrics depend on moved.** No labelled candidate was among the missing ideas, the candidate order was identical for all 12 queries, and every retrieval target stayed at rank 1.
- **Metrics:** precision 1.0, recall 0.8, F1 0.889, false-positive rate 0, TP 4 / FP 0 / FN 1 / TN 7, 2 abstentions, top-k success 1.0, MRR 1.0, copilot hit rate 1.0. These are identical to the table above.

This was expected. Precision, recall, and F1 cannot change with cosine (see [How cosine is used](#how-cosine-is-used)), because the evaluation computes fuzzy and exact for every historical idea whether or not the vector search returned it. The retrieval figures could only have changed through a cosine tie-break, and no query had a fuzzy tie at the top. The fix matters for the live candidate filter and for ranking ties, not for these metrics.

## v2 hard set: re-run (28 October 2026)

With the Tier 2 rules, the symmetric fuzzy score off and the component subset guard on (the live defaults): precision **0.890**, recall **0.811**, F1 **0.849**, TP 73, FP 9, FN 17, TN 498, 186 abstentions, mean rank 1.200, rank@1 0.833 (75 / 90).

- **What changed from the baseline below:** scope comparison removed one false positive (Q-0022 against H-0024).
- **What changed nothing:** turning the symmetric score off and adding the guard. Each changed no pair.
- **Database:** 111 historical ideas, with no edge-case ideas left after the edge runs.

Details are in [evaluation-edge-cases-v2.md](evaluation-edge-cases-v2.md#v2-hard-set-run-first).

## v2 hard set: clean baseline (27 October 2026)

This is the reference for comparing later classifier changes on `data/vave_duplicate_eval_set_v2.xlsx`. The method and the earlier runs are in [evaluation-hard-set.md](evaluation-hard-set.md).

- **Database:** 111 historical ideas (VAVE-SYN-001 to -020 and the 91 v2 ideas), each with an `all-MiniLM-L6-v2` vector. The 11 edge-case ideas VAVE-EH-001 to -011 (import batch `e4762c9e`), which had been loaded for [evaluation-edge-cases.md](evaluation-edge-cases.md), were deleted first: 11 ideas, their 55 vehicle rows, 11 vectors and 11 import-change rows. The batch was marked `rolled_back`, and the deletion was recorded in the audit log as `idea.delete_evaluation_ideas`. The edge-case scorer, `scripts/score_edge.py`, now loads those ideas inside a transaction and rolls them back, so they no longer stay in the database.
- **Settings:** offline, MiniLM, Ollama not reachable, `semantic_duplicate_threshold` 0.82, `retrieval_top_k` 15, `cosine_retrieve_threshold` 0.40, `fuzzy_strong_threshold` 86, `component_fuzzy_match` and `negation_detection` on. Any classifier rule added after this baseline must be turned off to reproduce it: with the Tier 2 code, `--disable direction_detection --disable scope_comparison --disable symmetric_lexical_fuzzy` reproduces every pair exactly ([evaluation-edge-cases.md](evaluation-edge-cases.md#v2-regression-check-tier-2)).
- **Command:** `HF_HUB_OFFLINE=1 backend/.venv/bin/python scripts/evaluate_hard_set.py data/vave_duplicate_eval_set_v2.xlsx out.json`

End to end, 597 pairs, 90 duplicates:

| | Precision | Recall | F1 | TP | FP | FN | TN | Abstentions | Mean rank | rank@1 |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| **overall** | **0.880** | **0.811** | **0.844** | 73 | 10 | 17 | 497 | 186 | 1.200 | 0.833 (75 / 90) |
| easy | 1.000 | 1.000 | 1.000 | 30 | 0 | 0 | | | | |
| medium | 1.000 | 0.800 | 0.889 | 24 | 0 | 6 | | | | |
| hard | 0.655 | 0.633 | 0.644 | 19 | 10 | 11 | | | | |

- Classifier only: precision 0.859, recall 0.811, F1 0.834 (12 false positives).
- All 90 duplicates were shown; the worst rank was 3.
- These figures match the ones recorded with 111 historical ideas before the edge-case rules existed ([evaluation-hard-set.md](evaluation-hard-set.md#candidate-ordering-by-verdict)). Component matching and negation detection change no v2 verdict ([evaluation-edge-cases.md](evaluation-edge-cases.md#v2-regression-check)).

## Limitations

- **The sample is small and synthetic.**
  - Only 12 labelled cases (5 duplicate, 4 similar but distinct, 3 unrelated) against 20 synthetic historical ideas, plus 3 copilot cases.
  - One case changes recall by 0.2.
  - The 0.147 and 0.042 gaps each rest on two cosine values.
  - None of this is a production accuracy claim.
- **Every candidate comes from one family.** All 4 similar-but-distinct cases compare against the same historical idea, VAVE-SYN-001, a cab mounting bracket.
- **The 0.40 threshold is a cut-off for this data, not a calibrated value.** It rests on 4 low-fuzzy pairs. Re-run the sweep on labelled real history before trusting it.
- **Evaluation queries are embedded from their text only.** The live app also embeds the component, department, and other fields, which produces different cosines. For example, the integration test's paraphrase request scored 0.836 against VAVE-SYN-001 with MiniLM in the live app, against 0.814 here.
- **No language model was involved.** Ollama was not running, so every verdict came from the deterministic heuristic.
- **The integration tests ran against a hosted Neon database only with the code defaults** (deterministic embeddings, threshold 0.22), not with MiniLM or 0.40.
