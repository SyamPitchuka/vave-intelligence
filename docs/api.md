# API

Interactive documentation is served by the running API at `/docs` (Swagger) and `/redoc`. The OpenAPI schema is `/openapi.json`.

All versioned routes are under `/api/v1`. Health is also available at `/health`.

## Authentication

`POST /api/v1/auth/login` returns a bearer token. Send `Authorization: Bearer <token>` on later requests. `GET /api/v1/auth/me` returns the user and permissions. Development accounts are listed by `GET /api/v1/auth/dev-accounts` only when `APP_ENV=development`.

## Ideas and import

- `GET /api/v1/ideas` paginated, filtered historical or submitted ideas
- `GET /api/v1/ideas/search`
- `GET /api/v1/ideas/{idea_id}`
- `POST /api/v1/ideas` and `PATCH /api/v1/ideas/{idea_id}` for drafts and submissions
- `POST /api/v1/ideas/import/preview` multipart workbook
- `POST /api/v1/ideas/import/commit` requires `confirm: true`
- `POST /api/v1/ideas/import/batches/{batch_id}/rollback`

## Duplicate detection and review

- `POST /api/v1/ideas/analyze-duplicates`
- `POST /api/v1/ideas/{idea_id}/analyze`
- `GET /api/v1/duplicate-analyses` and `GET /api/v1/duplicate-analyses/{analysis_id}`
- `POST /api/v1/duplicate-analyses/{analysis_id}/rerun`
- `GET /api/v1/reviews` and `POST /api/v1/reviews`

Review decisions are `confirm_duplicate`, `similar_but_distinct`, `no_duplicate`, and `escalate`. The rationale must be at least 10 characters. The response field `historical_records_changed` is false.

## Analytics, copilot, evaluation, administration

- `GET /api/v1/dashboard/summary`
- `GET /api/v1/analytics/savings` and `GET /api/v1/analytics/rejections`
- `GET/POST /api/v1/documents`, `GET /api/v1/documents/{document_id}/file`
- `POST /api/v1/copilot/chat`, session and feedback routes
- `GET/PUT /api/v1/ai/settings`, `POST /api/v1/ai/providers/test`, `POST /api/v1/ai/reindex`
- `GET /api/v1/evaluation/datasets`, `POST /api/v1/evaluation/runs`
- `GET /api/v1/audit-logs`
- `GET/POST /api/v1/admin/users`
- `GET/PUT /api/v1/admin/data-sources` plus test and sync
- Exports under `/api/v1/exports/` for ideas, analyses, reviews, savings, rejections, evaluation runs, and import errors

Permissions are enforced in `require()`. A hidden button is not the control. Errors use 400 for invalid input, 401 for a missing session, 403 for a missing permission, 404 for a missing record, 409 when a provider is unavailable or blocked, and 429 when the in-process rate limit is exceeded.
