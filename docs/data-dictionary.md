# Data dictionary

Timestamps are stored in UTC. The interface formats them in the configured display timezone, `Asia/Kolkata` by default. Money columns are INR. `total_combined_annual_saving` is projected, calculated by the service, and is not a realised saving.

## Identity and access

| Table | Purpose |
| --- | --- |
| users | Account, password hash, timezone, optional department |
| roles | system_administrator, vave_engineer, department_reviewer, department_head, readonly_management |
| user_roles | Assignment of roles |
| departments | Source labels, including the supplied spelling `steeting` |
| department_aliases | Optional later aliases. Source values are not rewritten |
| audit_logs | Action, actor, entity, and small details. Description bodies are not stored here |

## Ideas

| Table | Purpose |
| --- | --- |
| ideas | One row per Idea ID. Stage status A–F is independent of rejection. `is_rejected` is true only when rejection category is non-blank |
| vehicle_families | HCV Rigid Truck, HCV Tipper, Tractor-Trailer, RMC, COWL |
| idea_vehicle_applicability | Annual volume for one idea and one family. Unique on that pair |
| rejection_categories | Catalogue, including Duplicate |
| rejection_reasons | Catalogue. Duplicate is a reason, not a stage |

`reported_total_saving` keeps the workbook figure. `savings_mismatch` is true when that figure differs from the calculated total by more than 0.50 INR. `is_synthetic` marks demonstration rows. `origin` is `historical` or `submission`.

## Import

| Table | Purpose |
| --- | --- |
| import_batches | File, sheet, mapping, merge strategy, counts, status |
| import_staging_rows | Preview payload and planned action |
| import_row_errors | Row, column, severity, message |
| import_changes | Before and after snapshots used by rollback |

## Retrieval and review

| Table | Purpose |
| --- | --- |
| embedding_records | `vector(384)` keyed by entity type, entity id, and model name |
| duplicate_analysis_runs | Outcome, provider, models, thresholds, warning |
| duplicate_analysis_candidates | Rank, scores, explanation, similarities, differences |
| review_decisions | Human decision and the AI recommendation captured at decision time |

Analysis categories are `potential_duplicate`, `similar_but_distinct`, `no_strong_match`, and `insufficient_evidence`. They are not stage statuses.

## Documents and evaluation

| Table | Purpose |
| --- | --- |
| documents | Uploaded file metadata and visibility |
| document_chunks | Chunk text, page, section |
| chat_sessions, chat_messages, chat_feedback | Copilot history for the owning user |
| evaluation_datasets, evaluation_cases | Ground truth, separate from predictions |
| evaluation_runs, evaluation_predictions | Metrics and per-case output |
| application_settings | Non-secret AI settings |
| jobs | Re-index status |
| data_source_configs | Corporate view name and the environment variable that holds the DSN. The secret is not stored |
