# VAVE Retrieval Corpus — Source Document Index

All documents listed here are **synthetic / illustrative**, generated for the BITS Pilani WILP M.Tech (AI/ML) dissertation prototype (2024TM05058). Every page carries a watermark and a footer disclaimer. They are **not** genuine the OEM records and must never be described as production history.

Their purpose is to serve as a realistic retrieval corpus for Module 2's RAG knowledge-copilot pipeline.

**Corpus status as at 28 October 2026: 14 documents, 105 pages.**

---

## Part A — Original corpus, rebuilt anonymised (6 documents, 53 pages)

Originally generated 20 September 2026; **rebuilt 28 October 2026 with all organisation, product and competitor names removed.** Section and page anchors are preserved, so every citation in the Mid-Semester Report and in the Module 2 evaluation set still resolves.

| Doc No. | File | Pages | Key citable anchor |
|---|---|---|---|
| CVOEM/VAVE/TD-BM/FY23/014 | `Teardown_Benchmark_Report_FY23.pdf` | 14 | §4.2 Alternator Sub-system, p.12 — HSLA-steel bracket, ~18% weight reduction |
| CVOEM/VAVE/CB-BM/2024/007 | `Competitor_Benchmark_LeafSpring_2024.pdf` | 7 | §2 Suspension Sub-system, p.5 — GFRP composite mono-leaf, 35% mass saving, durability validation ongoing |
| CVOEM/VAVE/CB-BM/2024/011 | `Benchmark_Cabin_Sealing_Glazing_NVH_2024.pdf` | 8 | §2 Cabin Sub-system, p.4 — door-seal/acoustic-glass NVH package; §2.1 NVH Bench, p.5 — 63 dB(A) vs 68 dB(A) |
| CVOEM/VAVE/TD-BM/2024/012 | `Benchmark_Powertrain_Driveline_2024.pdf` | 8 | §3 Powertrain & Driveline, p.6 — 9-speed gearbox ratio spread ~11.5:1 |
| CVOEM/VAVE/CB-BM/2024/013 | `Benchmark_Tipper_Body_Hydraulics_2024.pdf` | 8 | §2 Tipper Body & Hydraulics, p.4 — hardened-steel bolt-on floor liner, +42.0 kg |
| CVOEM/VAVE/TD-BM/2024/014 | `Benchmark_Powertrain_Cooling_Pack_2024.pdf` | 8 | §3 Powertrain Cooling Pack, p.6 — increased-margin radiator + electronic viscous fan |

**Note on subject tipper variant:** no distinct published spec sheet was found for this exact variant; it is treated in the corpus as a tandem-bogie/tipper-kingpin trim of the subject tipper platform, sharing that platform's tipper body, hydraulics, and rear-axle architecture (Doc 013).

---

## Part B — Corpus expansion (8 documents, 52 pages)

Generated 28 October 2026. The expansion deliberately introduces **document-type variety**, not simply more teardowns. The original corpus was homogeneous: six benchmark reports sharing one structure, one register and one vocabulary. A retrieval pipeline evaluated only on that corpus is tested against a single document shape.

| Doc No. | File | Pages | Type | Key citable anchor |
|---|---|---|---|---|
| CVOEM/VAVE/TD-BM/2024/015 | `Teardown_Benchmark_FrontAxle_SubjectVehicle_vs_BenchmarkBC_2024.pdf` | 10 | Teardown benchmark | §3.2 p.4 — micro-alloyed direct-cooled beam, INR 1,240/vehicle; §5.1 p.7 — 180 mm drum width justified on thermal margin; §6.1 p.7 — front spring FRONT and REAR brackets are different load cases |
| CVOEM/VAVE/VE-CL/2024/008 | `VAVE_Idea_Closure_Register_FY24_H1.pdf` | 8 | Closure register | §2 p.2 — 148 of 337 closures (43.9%) are duplicates; §3 p.4 — precedent table, 44 re-submissions from 10 proposals; §6.1 p.7 — a reversal must be linked to the idea it reverses |
| CVOEM/VAVE/MC-IX/2025/003 | `Commodity_Material_Cost_Index_H1FY25.pdf` | 5 | Cost index | §2 p.2 — HR coil −9.3%, aluminium −4.7%, PA66-GF30 +9.9% over 24 months; §3.2 p.4 — controlled cooling INR 4.2/kg vs quench and temper INR 18.4/kg |
| CVOEM/VAVE/WF-FA/2024/021 | `Field_Failure_Warranty_Analysis_Bracketry_FY24.pdf` | 5 | Warranty analysis | §3.1 p.3 — fretting-initiated fatigue at the clamped interface; §3.2 p.3 — bench 1.34× target vs field 0.62× target; §4.2 p.4 — INR 31.4 m warranty cost; §6 p.5 — five conditions for reconsideration |
| CVOEM/VAVE/ES-STD/2023/004 | `Engineering_Standard_Fasteners_Corrosion_Rev04.pdf` | 6 | Engineering standard | §3.1 p.4 — exposure class C1 requires 720 h to red rust; §4.2 p.5 — dissimilar-material clamped joints must be validated on a representative fixture |
| CVOEM/VAVE/SC-TC/2024/009 | `Supplier_Capability_Tooling_Cost_Study_2024.pdf` | 7 | Supplier / cost study | §3 p.3 — fabrication/pressing break-even at 21,400 units/yr; §3.1 p.3 — combined platform volume 29,400 units; §4.1 p.5 — steps 2 and 3 are not separable |
| CVOEM/VAVE/WR-RM/2024/002 | `Kerb_Mass_Reduction_Roadmap_FY24_FY27.pdf` | 5 | Programme roadmap | §2 p.2 — 232 kg target, 171 kg committed, 61 kg gap; §4.1 p.5 — roadmap not closable from the current candidate pool |
| CVOEM/VAVE/VE-WS/2024/017 | `VE_Workshop_Minutes_Cab_Structure_Trim_Sep2024.pdf` | 6 | Meeting minutes | §3.2 p.3 — four in-room duplicate checks with reasoning, including door CHECK vs door HINGE bracket; §5.1 p.5 — roof acoustic pad deletion withdrawn |

### Why the variety matters for Module 2

Each added type stresses the retrieval pipeline differently:

- **Closure register** — dense tabular records with short entries. Tests chunking where a page holds many independent facts rather than one argument.
- **Cost index** — numeric tables with almost no prose. Tests whether a figure can be retrieved by its label.
- **Warranty analysis** — a narrative causal chain across sections. Tests whether retrieval returns the mechanism rather than the symptom.
- **Engineering standard** — normative register ("shall", "should", "may"), clause-numbered. Tests retrieval against a vocabulary that shares almost no wording with an idea submission.
- **Supplier / cost study** — conditional findings that depend on volume. Tests whether a retrieved answer carries its own precondition.
- **Programme roadmap** — forward-looking commitments and gaps rather than recorded facts.
- **Workshop minutes** — informal register, attendance lists, action tables, speech reported indirectly. Structurally unlike every other document in the corpus.

### Deliberate cross-references

The expansion documents cite each other and the original corpus, producing **multi-hop retrieval cases** that a single-document corpus cannot generate. Examples:

| Query would need | Hop 1 | Hop 2 |
|---|---|---|
| Why was the aluminium cab bracket reversed, and can it come back? | WF-FA/2024/021 §3.1 (mechanism) | WF-FA/2024/021 §6 (conditions) + ES-STD/2023/004 §4.2 (fixture requirement) |
| Should the front spring bracket move to pressing? | SC-TC/2024/009 §3 (break-even 21,400) | WR-RM or TD-BM/2024/015 §6 (volume and load case) |
| Is the PET felt headliner idea safe? | VE-WS/2024/017 §4.2 (field history raised) | WR-RM/2024/002 §3.1 (listed as at-risk) |
| What coating can I use on an exposed chassis bracket? | ES-STD/2023/004 §3.1 (720 h, class C1) | MC-IX/2025/003 §3.1 (rate per sq m) |

### Deliberate near-miss pairs

The corpus contains component names and proposals that are lexically close but substantively different. These exist so that retrieval precision can be measured, not just recall:

- door **check** bracket vs door **hinge** bracket (VE-WS §3.2, TD-BM/2024/015)
- front spring **front** bracket vs front spring **rear** bracket (TD-BM/2024/015 §6.1)
- *reduce* oil pan thickness vs *increase* oil pan thickness (VE-CL §3.1)
- material change alone vs material change **plus relocation** (VE-CL §3.1)
- same change, **different programme** — rigid vs tipper (VE-CL §3.1, WF-FA §3.3)

---

## Module 2 evidence status

### REVISED 20 Sep 2026 — real pipeline, not scripted output

Everything below Figure 4 (inclusive) in Section "Module 2 — RAG Knowledge Copilot" was regenerated from an actually-implemented, actually-executed retrieval pipeline. Prior rounds' Figures 4–6 and the Case A/B narrative were scripted/hand-typed to *look like* code-execution screenshots; that was flagged and corrected.

**Real pipeline architecture (documented substitution):** the target architecture named in the synopsis and Section 2 of the report is sentence-transformers + FAISS/ChromaDB. The sandbox used in September had no PyPI or Hugging Face egress, so that stack could not be installed. The running substitute was **TF-IDF vectorization + Truncated SVD (LSA) cosine similarity via scikit-learn**, over the original six-document corpus (53 pages → 41 substantive page-chunks after excluding cover/TOC boilerplate).

**Citation-confidence threshold: 0.50**, calibrated on observed score separation — six well-formed queries scored 0.75–0.92 top-1; deliberately vague queries scored 0.00–0.49.

**Case A (below-threshold abstention):** *"Was the spring redesigned?"* → 0.49, system abstained. Reworded to *"Was the composite mono-leaf spring's durability status evaluated in the suspension competitor-benchmark study?"* → 0.83, correct match.

**Case B (cross-document collision):** *"What door change was benchmarked?"* → 0.66, above threshold but the **wrong** document — a genuine TF-IDF lexical collision on two documents' identically-named "Cabin Sub-system" heading. Reworded → 0.87, correct match.

### UPDATED 28 Oct 2026 — the substitution constraint no longer applies

The `vave-intelligence` repository now runs **sentence-transformers (all-MiniLM-L6-v2) offline** with `HF_HUB_OFFLINE=1`, and has **pgvector** in a hosted Postgres instance. This is the architecture the synopsis commits to. The egress constraint that forced TF-IDF was a property of the September sandbox, not of the project.

**Recommended action before final submission:** re-index this corpus on MiniLM + pgvector, reusing Module 1's embedding path, and re-capture the Module 2 evidence on the committed architecture. The TF-IDF results above should then be reported as an interim stage, with the substitution and its removal both recorded — which is a stronger methodology note than either result alone.

**Note on the threshold:** 0.50 was calibrated against TF-IDF/LSA cosine scores. It does **not** transfer to MiniLM cosine, whose distribution is different. The threshold must be re-calibrated on the new embeddings, not carried over.

### STILL OUTSTANDING — Figure 3

**Figure 3 (Module 1 — Duplicate/Similar-Idea Detection code-execution output, page 10)** of the Mid-Semester Report is a scripted/fabricated notebook screenshot with invented cosine-similarity values (0.93 / 0.88 / 0.79 / 0.41). It was flagged on 20 September 2026 and has **not** been corrected.

Module 1 has since been built, run and evaluated in full. Every value in that figure can now be replaced with real output. **This must be corrected before final submission.**

---

## Generation provenance

| Artefact | Script |
|---|---|
| Page framework, watermark, tables, callouts | `vavedocs/common.py` |
| Figures (12 charts and schematics) | `vavedocs/figures.py` |
| Documents 1–2 | `vavedocs/build_a.py` |
| Documents 3–5 | `vavedocs/build_b.py` |
| Documents 6–8 | `vavedocs/build_c.py` |
| Original corpus rebuilt (1–2) | `vavedocs/build_d.py` |
| Original corpus rebuilt (3–4) | `vavedocs/build_e.py` |
| Original corpus rebuilt (5–6) | `vavedocs/build_f.py` |
| Module 2 evaluation set | `vavedocs/qa_set.py` |

Figure palette validated against the categorical-palette checks (lightness band, chroma floor, CVD separation at ΔE ≥ 8, normal-vision floor, contrast vs surface) — all pass. No dual-axis charts: the Pareto in WF-FA/2024/021 is drawn as two stacked panels sharing one x-axis.
