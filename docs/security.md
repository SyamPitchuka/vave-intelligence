# Security and privacy

This prototype is not a certified production system. The controls below are implemented. The checklist at the end is still open before any corporate deployment.

## Implemented

- Passwords are hashed with bcrypt. Sessions are HS256 bearer tokens with a configured lifetime.
- Role checks run in the API. The five roles are system administrator, VAVE engineer, department reviewer, department head, and read-only management.
- OpenAI keys are read from the server environment. They are not written to the database, returned by the API, or placed in browser storage.
- Offline and fallback modes raise `OfflineModeBlocked` before an OpenAI HTTP client is used. There is no silent switch to online mode.
- CORS origins come from configuration. Responses set `X-Content-Type-Options`, `X-Frame-Options`, and `Referrer-Policy`.
- Queries use SQLAlchemy bound parameters. The corporate adapter uses a fixed column list and a view name that must match a conservative pattern. The language model does not generate SQL.
- Uploads are limited by size and by extension and magic-byte checks for PDF, DOCX, and text.
- Logs redact fields named password, api key, authorization, secret, prompt, description, and token. Full prompts are off unless `LOG_PROMPT_BODIES` is set.
- Imports and review decisions commit in a database transaction. Rollback of an import is blocked once an idea has been used in an analysis.
- Login and analysis endpoints have a per-process rate limit.

## Before production

- Replace `SECRET_KEY`, the demo passwords, and the development database password. `APP_ENV=production` refuses the development defaults and refuses demo seeding.
- Use a least-privilege database role. The local `vave` role used for development is a superuser.
- Put PostgreSQL and the API on a private network, terminate TLS, and restrict CORS to the real origin.
- Decide, in writing, whether any idea text may be sent to an online model. Leave `AI_MODE=offline` or `fallback` until that decision exists.
- Move the rate limit and background jobs off process memory if more than one API instance runs.
- Back up the PostgreSQL volume and test restore. `alembic downgrade` is the schema rollback path. Take a database backup before downgrading.
- Review dependency and image vulnerabilities in the target registry. This environment did not run a container scan because the Docker daemon was not available.
- Confirm document visibility with the organisation's access rules. The copilot will not return a chunk whose document the caller cannot read.
