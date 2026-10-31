# Evaluation results: knowledge copilot (Module 2)

Measured on 28 October 2026 against the hosted Neon development database.

| Setting | Value |
| --- | --- |
| Embedding | `sentence-transformers/all-MiniLM-L6-v2`, the provider duplicate detection uses |
| Language model | Ollama was not reachable, so every answer is extractive |
| Retrieval | Top 5 distinct (document, section, page) places (`copilot_distinct_sections` on) |
| Index | The 14 corpus PDFs only: 211 chunks, one MiniLM vector each. No other document and no hashed passage vector |
| Threshold | `copilot_citation_threshold` set to **0.4873** in the dev database's stored settings on 28 October, through the settings service, with an `ai.settings` audit entry. The code default is still `None` |

- **Evaluation set:** `data/vave_module2_retrieval_eval_set.json` (and `.xlsx`), 47 synthetic queries: 34 answerable and 13 that must be refused.
- **Command:** `HF_HUB_OFFLINE=1 backend/.venv/bin/python scripts/evaluate_copilot.py data/vave_module2_retrieval_eval_set.json out.json --threshold 0.4873`
- **The script is read-only.** Its docstring fixes the scoring rules, the split and the threshold rule. All three were written before the first run.

Nothing was tuned on any result.

## Runs

| Run | Index | Labels | Status |
| --- | --- | --- | --- |
| **First run** | 14 PDFs + seeded demo guideline | Original | **The first-run result.** It stands as recorded |
| Re-score A | 14 PDFs only | Original | Isolates the effect of removing the guideline |
| **Re-score B** | 14 PDFs only | Corrected (6 anchors) | **The instrument-fixed result, and the final figures** |

**Final run.** The final run (with the k = 10 sensitivity added) reproduced re-score B exactly: every per-query record, every retrieval figure and every rate at 0.4873. Module 2 is closed on these figures, with no retrieval tuning, threshold change or rerank after them.

**What changed between them:**
- **Re-scores A and B retrieved identically,** passage for passage.
- **Removing the guideline changed one query's top passage:** M2-026, at rank 1 (cosine 0.4523 → 0.4506).
- **The calibration rule picks 0.4873 in every run.**

## Scoring rules

- **Anchor match:** a passage satisfies an anchor (document, section S, page P) when all three hold:
  - the document matches;
  - the page is P;
  - the section is S or a subsection of S.
- **Parent-level anchors count as correct.** An anchor of "section 3, page 6" is satisfied by a 3.1 chunk on page 6, because anchors name the section a reader is sent to. A chunk of section 3 does not satisfy an anchor of 3.1.
- **recall@k:** every anchor of the query is satisfied within the top k.
- **MRR:** 1 / rank of the first passage that satisfies any anchor.
- **Citation accuracy:** the cited passage (the top passage, for an extractive answer) has the right document and the right page.
- **Multi-hop by type:** a hit when every expected document is in the top k, as specified. The every-anchor figure is shown beside it.
- **Abstention:** no answer when the top passage's cosine is below the threshold. The harness replays this rule and checks every query against `compose_answer`; all 47 agreed in every run.

**Split.** Stratified by type, alternating by id:

| | Calibration | Held out |
| --- | --- | --- |
| Answerable | 17 | 17 |
| Must-abstain | 7 | 6 |

**Threshold choice, on the calibration half only.** The candidates are midpoints between the calibration top-1 cosines. Two rules were fixed in advance:

| Rule | Threshold | Calibration result | Comment |
| --- | --- | --- | --- |
| Highest balanced accuracy (mean of answered-when-answerable and refused-when-not) | **0.4873** | 0.668 | The deployed value |
| Lowest threshold with no calibration false answer | **0.7932** | 0 of 17 answerable answered | The same in both halves |

## De-duplication

Two windows of one section count as one result. This changed the top 5 for **3 of 47 queries:** M2-001, M2-020 and M2-023.

## Results

The held-out half is the result.

### Retrieval, answerable queries

Retrieval does not depend on the threshold.

| | First run | Re-score A | **Re-score B** |
| --- | --- | --- | --- |
| **Held out (17)** | | | |
| recall@1 | 0.176 (3) | 0.176 (3) | **0.294 (5)** |
| recall@3 | 0.412 (7) | 0.412 (7) | **0.647 (11)** |
| recall@5 | 0.412 (7) | 0.412 (7) | **0.647 (11)** |
| MRR | 0.358 | 0.368 | **0.544** |
| **Calibration (17)** | | | |
| recall@1 | 0.294 (5) | 0.294 (5) | 0.412 (7) |
| recall@3 | 0.588 (10) | 0.588 (10) | 0.647 (11) |
| recall@5 | 0.706 (12) | 0.706 (12) | 0.765 (13) |
| MRR | 0.536 | 0.536 | 0.634 |
| **All 34** | | | |
| recall@1 | 0.235 (8) | 0.235 (8) | 0.353 (12) |
| recall@3 | 0.500 (17) | 0.500 (17) | 0.647 (22) |
| recall@5 | 0.559 (19) | 0.559 (19) | 0.706 (24) |
| MRR | 0.447 | 0.452 | 0.589 |

- **Neither half was used to choose anything for retrieval.** The gap between the halves is split variance on 17 queries.
- **The all-34 figure is the steadier estimate.**

### At the deployed threshold, 0.4873

**Answerable queries.** These figures are the same in all three runs, except citation accuracy.

| | Calibration | Held out |
| --- | --- | --- |
| Answered | 13 / 17 | **11 / 17** |
| Wrongly refused | 4 / 17 | **6 / 17** |
| Citation accuracy among answered, first run and re-score A | 8 / 13 (0.615) | **4 / 11 (0.364)** |
| Citation accuracy among answered, re-score B | 9 / 13 (0.692) | **4 / 11 (0.364)** |
| Citation accuracy over all answerable, re-score B | 9 / 17 (0.529) | **4 / 17 (0.235)** |

**Must-abstain queries.** These figures are the same in all three runs.

| | Calibration | Held out |
| --- | --- | --- |
| Abstention rate | 4 / 7 (0.571) | **5 / 6 (0.833)** |
| **False-answer rate** | **3 / 7 (0.429)** | **1 / 6 (0.167)** |

### False answers

Each is a question in the corpus's own domain that asks for a detail the corpus does not hold.

| Query | Half | Top-1 cosine | Answered from |
| --- | --- | --- | --- |
| M2-037, gearbox warranty claims FY24 | calibration | 0.567 | WF-FA/2024/021, §2, p.2 (bracket claims) |
| M2-039, FY28 kerb mass target | calibration | **0.783** | WR-RM/2024/002, §1, p.2 (the FY27 target) |
| M2-041, M24 fastener torque | calibration | 0.688 | ES-STD/2023/004, §4.3, p.5 |
| M2-042, FY25 teardown conclusions | held out | 0.686 | TD-BM/FY23/014, §3.3, p.5 (the FY23 report) |

### The threshold trade-off

**No threshold value cleanly separates answerable queries from those that must be refused.**

- **The two populations' top-1 cosines overlap almost completely:**
  - answerable queries: 0.187 to 0.783;
  - must-abstain queries: 0.259 to 0.783.
- **The highest score of all belongs to a query that must be refused:** M2-039, the FY28 target, at 0.7832. The best answerable query scores 0.7829.
- **Every threshold therefore trades refused answers against false answers.** Removing the last false answer means refusing every answerable query. Answering every answerable query means answering every question that should be refused.

The table counts queries, not rates. The calibration half was used to choose; the held-out half was not.

| Threshold | Answerable that lose their answer: calibration / held out / all | False answers: calibration / held out / all |
| --- | --- | --- |
| 0.20 | 0 / 17, 1 / 17, 1 / 34 | 7 / 7, 6 / 6, 13 / 13 |
| 0.25 | 0, 1, 1 | 7, 6, 13 |
| 0.30 | 0, 2, 2 | 6, 5, 11 |
| 0.35 | 0, 2, 2 | 5, 4, 9 |
| 0.40 | 2, 3, 5 | 5, 3, 8 |
| 0.45 | 4, 3, 7 | 4, 1, 5 |
| **0.4873 (deployed)** | **4, 6, 10** | **3, 1, 4** |
| 0.50 | 4, 6, 10 | 3, 1, 4 |
| 0.55 | 7, 8, 15 | 3, 1, 4 |
| 0.60 | 9, 9, 18 | 2, 1, 3 |
| 0.65 | 12, 11, 23 | 2, 1, 3 |
| 0.70 | 14, 14, 28 | 1, 0, 1 |
| 0.75 | 17, 15, 32 | 1, 0, 1 |
| 0.80 | 17, 17, 34 | 0, 0, 0 |

**At 0.4873, across all 47 queries,** 10 of 34 answerable queries lose their answer, and 4 of 13 must-abstain queries are answered: M2-037, M2-039, M2-041 and M2-042.

### Recall by query type

Hits at k = 1 / 3 / 5, all 34, original labels → corrected labels. The re-scores retrieved identically; only the labels differ.

| Type | Original labels | Corrected labels | Held out, corrected |
| --- | --- | --- | --- |
| single_hop (14) | 4 / 9 / 9 | 6 / 11 / 11 | 2 / 6 / 6 of 7 |
| multi_hop, all expected documents (8) | 1 / 4 / 5 | 1 / 4 / 5 | 0 / 1 / 1 of 4 |
| multi_hop, all expected anchors (8) | 0 / 2 / 3 | 0 / 3 / 4 | 0 / 1 / 1 of 4 |
| near_miss (7) | 2 / 4 / 5 | 4 / 6 / 7 | 2 / 3 / 3 of 3 |
| cross_register (5) | 2 / 2 / 2 | 2 / 2 / 2 | 1 / 1 / 1 of 3 |

### Sensitivity: multi-hop at k = 10

**This is not the headline. k = 5 stays the reported figure.**

- **Why check it:** after de-duplication, the top 5 holds five distinct sections. A multi-hop query needs two documents inside that window, so k = 5 may be measuring the window rather than the retriever.
- **Method:** the harness retrieved each multi-hop query again at k = 10 distinct places and applied the same two rules. Corrected labels.

| Rule | Half | k = 5 | k = 10 |
| --- | --- | --- | --- |
| All expected documents | All 8 | 5 / 8 | **7 / 8** |
| All expected documents | Held out | 1 / 4 | 3 / 4 |
| All expected anchors | All 8 | 4 / 8 | **6 / 8** |
| All expected anchors | Held out | 1 / 4 | 2 / 4 |

Rank of the first passage from each expected document, at k = 10:

| Query | Ranks | Within 10 |
| --- | --- | --- |
| M2-015 | 1 | yes |
| M2-016 | 6, 1 | yes |
| M2-017 | 2, 1 | yes |
| M2-018 | 1, 2 | yes |
| M2-019 | 1, 4 | yes |
| M2-020 | 1, not retrieved | no |
| M2-021 | 2, 1 | yes |
| M2-022 | 1, 9 | yes |

- **Two of the three misses at k = 5 are the window.** M2-016 and M2-022 find their second document at ranks 6 and 9.
- **One is the retriever.** M2-020 does not retrieve its second document (TD-BM/2024/015) anywhere in the top 10.
- **At the anchor level,** M2-022's second anchor is still not retrieved at k = 10. M2-015's two anchors sit at ranks 7 and 5.

### Near-miss failures

Corrected labels, guideline removed.

| Query | Expected | Returned at rank 1 instead | Expected anchor rank |
| --- | --- | --- | --- |
| M2-023, door check bracket | VE-WS/2024/017 §3.1 p.3 | **VE-WS/2024/017** §3.2 "Duplicate checks performed during the workshop" p.3 (0.511) | 2 |
| M2-026, coating inside the cab | ES-STD/2023/004 §3.1 p.4 | **VE-WS/2024/017** §3.1 "Ideas logged" p.3 (0.451) | 2 |
| M2-029, warranty cost of bracket failures | WF-FA/2024/021 §4.2 p.4 | **WF-FA/2024/021** §2 "Claims by failure mode" p.2 (0.593) | 4 |

- **M2-024 and M2-027 were near-miss "failures" only because of their labels.** With corrected labels, both are correct at rank 1.
- **In the first run, M2-026 returned the seeded demo guideline,** "Cab mounting bracket example". With the guideline removed, it returns the workshop minutes' idea log instead, and the correct section moves from rank 3 to 2.
- **No near-miss query returned the lexical twin it was built around.**
- **Two of the three remaining failures are the right document, wrong section.**

## Evaluation set label corrections

After the first run, every expected anchor was checked against the chunks in the database. Two anchors (M2-014 and M2-018) matched no chunk at all.

All six suspect anchors were then checked against the **raw PDF page text** (pypdf, not the chunker, the index or retrieval). The check asked two things:
- which pages hold the answer's key phrases;
- whether a heading with the labelled section number exists in the document.

| Query | Was | Now | Raw-text evidence |
| --- | --- | --- | --- |
| M2-002 | §2, p.5 | §2.1, p.6 | "35 per cent mass saving" is on p.6 under 2.1.1, and the durability point is on p.6 under 2.1.2. §2 on p.5 only says the finding is "reported in section 2.1" |
| M2-007 | §3.2, p.4 | §3.2, p.5 | "INR 1,240 per beam" is on p.5. §3.2's heading is on p.4 |
| M2-014 | §5.1, p.5 | §5, p.5 | **No heading numbered 5.1 exists in the PDF.** "Outcome 5.1" (p.5) is a callout under "5 NVH package discussion" |
| M2-018 | §4.2, p.5 | §4.2, p.4 | The only "4.2" heading, "Discussion on item 4.1.1", and the PET felt discussion are on p.4 |
| M2-024 | §6.1, p.7 | §6, p.7 | "Finding 6.1" (p.7) sits under "6 Suspension bracketry". The real §6.1 is "Process route and volume sensitivity" |
| M2-027 | §5.1, p.7 | §5, p.7 | "Finding 5.1" (p.7) sits under "5 Hub, drum and bearing arrangement". The real §5.1 is "Bearing arrangement" |

**Three of the six cite a callout number as a section number** (Finding 6.1, Finding 5.1, Outcome 5.1). These documents number findings and outcomes in a scheme that looks like section numbering but is not.

**M2-014 and M2-018 are label errors, not chunking gaps:**
- **M2-014** names a section the document does not have.
- **M2-018** names the wrong page for a section that exists.

In both cases the chunker filed the answer text under the section and page where it actually appears.

**Where the correction is recorded:**
- **JSON:** each corrected query's `notes`, with the old and new anchor and the reason. The file is a plain list, so it has no file-level note field.
- **xlsx:** the same note in the Queries sheet, plus a "Label corrections" block on the Cover sheet.

The originals are kept as the first-run result above.

## Cross-module finding: a cosine threshold sits inside the distribution it separates

Module 1 and Module 2 show the same thing independently, on different tasks and different corpora.

- **Module 1, duplicate verdicts.** `semantic_duplicate_threshold` 0.82 decides 14 labelled verdicts that sit within 0.01 of it, on both sides ([evaluation-edge-cases-v2.md](evaluation-edge-cases-v2.md#accidental-passes-and-the-threshold)). On deterministic embeddings the calibration rule moved from 0.82 to 0.81 on two pairs, and the held-out families disagreed ([evaluation-hard-set.md](evaluation-hard-set.md#re-baseline-on-deterministic-embeddings-28-october-2026)).
- **Module 2, abstention.** The answerable and must-abstain top-1 cosines overlap almost completely, and the highest score belongs to a query that must be refused. No value of `copilot_citation_threshold` is free of both errors.
- **Same cause in both modules.** A single cosine compares topic, not the detail that decides the case. In Module 1 that detail is direction, programme or negation; in Module 2 it is FY28 against FY27, FY25 against FY23, or M24 against a general torque table. Any threshold on that number sets an error trade-off. It is not a separator.

## Limitations

- **Small samples:** 17 answerable and 6 or 7 must-abstain queries per half. One query moves a rate by 0.06 or more on the answerable side, and by 0.14 to 0.17 on the must-abstain side.
- **One split.** It was not repeated with other partitions.
- **No language model:** every answer was extractive. Generated answers were not evaluated.
- **The evaluation set and the corpus come from the same author and generator.** Six of its 42 anchors were wrong before correction, so others may be too. Only anchors that failed a check were re-verified against the PDFs.
- **The threshold was chosen on the first-run index,** which included the guideline. The rule chooses the same value on the corrected index.
- **A fresh database is still seeded with the demo guideline.** The integration tests rely on it. The dev database no longer contains it.
## Generated answers: the same set with a local language model (31 October 2026)

The figures above were measured with Ollama unreachable, so every answer was extractive. The
generated path was evaluated on 31 October against the same database, the same index and the
same evaluation set.

| Setting | Value |
| --- | --- |
| Language model | `llama3.2` (3B) served by Ollama 0.40.13, CPU only, 127.0.0.1:11434 |
| Embedding | `sentence-transformers/all-MiniLM-L6-v2`, unchanged |
| Threshold | `copilot_citation_threshold` 0.4873, unchanged |
| Provenance line | `embedding=sentence-transformers/all-MiniLM-L6-v2 chat=ollama llm_status=pending` |

- **Command:** `HF_HUB_OFFLINE=1 backend/.venv/bin/python scripts/evaluate_copilot.py data/vave_module2_retrieval_eval_set.json out_generated.json`
- **Outputs committed:** `out_extractive.json` (baseline, `chat=deterministic llm_status=unavailable`) and `out_generated.json`.

### Control: retrieval is unaffected

Retrieval is identical between the two runs, as it must be -  the language model takes no part in
it. Had these moved, the comparison would have been measuring something other than what it claims.

| Measure | Extractive | Generated |
| --- | --- | --- |
| recall@1, @3, @5 (of 34 answerable) | 12, 22, 24 | 12, 22, 24 |
| MRR | 0.5892 | 0.5892 |
| `primary_max_balanced_accuracy` | 0.4873 | 0.4873 |
| `lowest_with_no_calibration_false_answer` | 0.7932 | 0.7932 |

### Outcome: nothing measurable changed in that run

| Measure | Extractive | Generated |
| --- | --- | --- |
| Queries answered | 28 | 28 |
| Queries refused | 19 | 19 |
| Citations correct, calibration / held out | 9 / 4 | 9 / 4 |
| False answers | 4 | 4 |
| Model returned `insufficient` | n/a | **0 of 28** |

The same 28 queries were answered and the same 19 refused -  the same queries, not similar counts.
The four false answers are the same four: M2-037, M2-039, M2-041, M2-042. In 28 opportunities the
model never once reported that the passages did not answer the question, although its instructions
offer that option explicitly.

**Why.** The abstention gate compares the top passage's cosine against the threshold and decides
*before* composition begins (`compose_answer` in `services/copilot/service.py`). The model is only
asked to word an answer that has already been authorised. A language model placed after the gate
cannot repair a gate failure.

### Four queries repeated through the interface

A single batch run establishes what happened once, not what the system does. Four queries were
repeated through the UI afterwards, same configuration. The results do not reproduce the batch run.

| Query | Extractive | Generated, on repetition | Effect |
| --- | --- | --- | --- |
| FY24 H1 duplicate proportion (M2-008) | Quotes the register: "one hundred and forty-eight of them, forty-four per cent" | **"40% of VAVE ideas closed in FY24 H1 were duplicates"**, citing three passages that each state 43.9 or 44 per cent | Worse |
| M24 fastener torque (M2-041) | Quotes the whole table, M8 to M20, so the absence of M24 is visible | **"34 Nm"**, where the batch run gave **"24 Nm"**. Both are M8 values (24 at grade 8.8, 34 at grade 10.9) | Worse |
| FY28 kerb mass target (M2-039) | Quotes the FY27 passage | **Refuses** -  the model judged the retrieved passages insufficient | Better |
| Why steel and aluminium are on separate scales | Returns Finding 2.1 at cosine 0.539, which does not answer the question | **Correct**, citing passage 2 -  the figure caption at 0.536 | Better |

Two improved, two degraded, and M2-039 contradicted its own batch result with identical retrieval
at the same score of 0.783.

- **The scales case is the one gain.** `_extractive` composes from `evidence[0]` alone, so a passage
  that loses by 0.003 is unreachable however clearly it answers. `_generate` receives all k and
  cites by number; here it chose the second.
- **The torque case is the one serious loss.** The table covers M8 to M20. Both fabricated values
  come from the M8 row, one column apart. The figure is constructed, not retrieved, and constructed
  differently on each occasion -  so a reader cannot catch it by asking twice.
- **The duplicate-proportion case is the most instructive.** Three citations, every one stating
  43.9 per cent or forty-four per cent, and an answer of 40 per cent. The citation apparatus worked
  and the arithmetic did not.

**Conclusion.** The effect of generation on this corpus is not a direction but a variance. The
aggregate stability of the batch run conceals movement underneath it rather than showing the model
is inert. A sound evaluation would run the full set many times and report a distribution per
figure. That was not done.

## Probe: facts in tables, figure captions and charts (31 October 2026)

The 47-query set is drawn from prose. Chunking extracts text, so a table survives as a flattened
row of values, a figure caption survives as a sentence, and values plotted inside a chart do not
survive at all. Six queries were written against that distinction *after* the measured evaluation.
They are diagnostic, authored with the corpus open, and change none of the figures above.

| Probe | Where the answer lives | Outcome | Top cosine |
| --- | --- | --- | --- |
| Largest unallocated gap in the kerb mass roadmap | A table, summarised in a Finding | Correct, answered from Finding 2.1 rather than the table | 0.669 |
| October 2024 rate for PA66-GF30 | A table row | Correct; the table was retrieved as flattened text and quoted whole | 0.613 |
| Which stream carries the largest single allocation | A figure caption | Correct, from the caption of a chart the system cannot see | 0.501 |
| Why steel and aluminium are on separate scales | A figure caption | **Wrong**; a Finding that does not answer the question won by 0.003 | 0.539 |
| Hot-rolled coil rate in March 2024 | Plotted in the chart only | Refused, correctly | 0.447 |
| Month of lowest hot-rolled coil rate | Plotted in the chart only | Refused, correctly | 0.460 |

- Tables and captions are retrievable because both survive extraction as text. A caption that only
  named its figure, rather than stating what the figure shows, would not have been answerable.
- Both chart-only probes were refused, but the mechanism is weaker than the result suggests: the
  system refuses because no text matches, not because it knows the value is drawn in a figure it
  does not index. It cannot say "that is plotted in Figure 1".
- The caption failure at 0.003 is the same arithmetic as the thresholds elsewhere in this report,
  now deciding which of two retrieved passages is presented as the answer. The losing passage is
  displayed directly beneath the winning one.
