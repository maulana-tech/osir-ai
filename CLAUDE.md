# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## What this is

Osir AI: a Django 5 social-media management app (multi-platform publishing, scheduling, inbox, analytics, client portal) with a REST + MCP "Agent API", plus `agent/`, a Strands Agents SDK autopilot (AWS "Agents for Humans" hackathon entry) that drives Studio through that MCP server and runs on Amazon Bedrock AgentCore. Server-rendered templates + HTMX + Alpine.js; Tailwind 4 is the only frontend build step. Background jobs run on django-background-tasks (PostgreSQL-backed, no Redis/Celery).

## Commands

Python 3.12 (CI + pyproject). Node 20+ for Tailwind only. `make help` lists everything.

```bash
make setup                      # cp .env.example .env, pip install, npm install (theme/static_src), migrate
# For a DB-server-free dev setup, set DATABASE_URL=sqlite:///db.sqlite3 in .env

# Dev needs three processes:
make server                     # python manage.py runserver
make worker                     # python manage.py process_tasks  (nothing publishes without this)
make tailwind                   # cd theme/static_src && npm run start  (writes static/css/dist/styles.css)

make migrate / make migrations

make docker-up                  # postgres, migrate, app, worker, tailwind, console (web/)
docker compose --profile agent up -d   # + agent-worker (needs STUDIO_API_KEY and AWS creds in .env)
make docker-prod                # adds Caddy: APP_DOMAIN → app, CONSOLE_DOMAIN → console

make lint                       # ruff check . && ruff format --check .
make format                     # ruff check --fix . && ruff format .
make typecheck                  # mypy apps/ config/ providers/ tests/ --ignore-missing-imports
pre-commit install && pre-commit install --hook-type pre-push   # same checks as CI, plus gitleaks
```

### Tests

```bash
pytest                                                   # whole suite
pytest apps/composer/tests/test_clone.py                 # one file
pytest apps/publisher/tests.py::TestX::test_y            # one test
pytest -k "first_comment"                                # by keyword
pytest --cov=apps --cov-report=term-missing              # coverage (what CI runs)
```

- Tests **always use PostgreSQL** (`config/settings/test.py` hardcodes the engine; DB name `osir_ai_test`, overridable via `DB_HOST`/`DB_USER`/`DB_PASSWORD`/`DB_PORT`). Start one with `docker compose up postgres -d`. SQLite in `.env` does not apply to tests.
- `SECRET_KEY` / `ENCRYPTION_KEY_SALT` get test defaults automatically; no `.env` needed for pytest.
- Tests live in `apps/<app>/tests/` or `apps/<app>/tests.py`, plus `tests/providers/` for platform provider modules. Shared fixtures (`user`, `organization`, `org_owner`) are in root `conftest.py`.
- Ruff: line length 120, `*/migrations/*` excluded. Per-file lint exceptions are documented in `pyproject.toml`; don't "fix" them.

## Settings

`config/settings/{base,development,production,test}.py`, driven by django-environ reading `.env`. `manage.py` defaults to `development`, `wsgi.py`/`asgi.py` to `production`, pytest to `test` (pyproject). Override only via `DJANGO_SETTINGS_MODULE`.

## Architecture

### Tenancy and RBAC
- Hierarchy: `Organization` → `Workspace` → everything else. v1 assumes one org per user.
- `apps/members/middleware.py:RBACMiddleware` populates `request.org`, `request.org_membership`, `request.workspace`, `request.workspace_membership` on every request. Workspace-scoped pages are mounted under `/workspace/<uuid:workspace_id>/...` (see `config/urls.py`) and the middleware resolves the workspace from that URL kwarg.
- Enforce access with decorators from `apps/members/decorators.py`: `require_org_role`, `require_workspace_role`, `require_permission(key)`, `require_org_permission(key)`.
- `apps/common/managers.py` provides abstract `OrgScopedModel` / `WorkspaceScopedModel` with `objects.for_org(id)` / `objects.for_workspace(id)`. Scoping is **explicit**, not automatic: always filter through these in views.

### Social providers (`providers/`)
- One module per platform implementing the `SocialProvider` ABC in `providers/base.py` (OAuth, publish, comments, metrics, inbox, webhooks). Shared dataclasses/enums in `providers/types.py`, exceptions in `providers/exceptions.py`. HTTP goes through `SocialProvider._request` (httpx).
- `providers/__init__.py` holds `PROVIDER_REGISTRY` and `get_provider(platform, credentials)`. Platform keys match `PlatformCredential.Platform` (note `instagram` vs `instagram_login`, `linkedin_personal` vs `linkedin_company`).
- App credentials: `apps/credentials/models.py:resolve_platform_credentials` reads the encrypted `PlatformCredential` row and falls back to `settings.PLATFORM_CREDENTIALS_FROM_ENV` (`PLATFORM_<X>_*` env vars).
- Composio fallback (`apps/credentials/composio.py`): when an org has no credentials for a platform and `COMPOSIO_AUTH_CONFIGS` has an entry, the connect grid runs Composio's hosted OAuth (`_start_composio_connect` / `composio_callback` in `apps/social_accounts/views.py`). Such accounts have `auth_source="composio"`, empty tokens, and `_resolve_publish_credentials` adds `composio_api_key` + `composio_connected_account_id` to the provider credentials, which makes `SocialProvider._request` send the call through `providers/composio_transport.py` instead of directly. Keep every provider HTTP call on `_request` (or on a pre-signed URL that needs no auth) so the proxy switch stays complete.
- Caption limits must use `providers.caption_wire_length` (LinkedIn escaping makes typed length ≠ wire length).
- Adding a platform: new `providers/<name>.py`, register in `PROVIDER_REGISTRY`, add to the `Platform` enum, env vars in `.env.example`, README "Platform Credentials" section, tests in `tests/providers/`.

### Content pipeline
- `apps/composer` owns `Post` and its per-platform children `PlatformPost`. **Status lives on `PlatformPost`**; `Post.status` is an aggregate derived in `apps/composer/status.py`. Don't write status on `Post`.
- `apps/publisher/engine.py:PublishEngine` is the publish loop (poll due `PlatformPost`s → `publishing` → dispatch in a thread pool → retry with backoff → delayed first comment). It is driven by the `run_publish_cycle` background task in `apps/publisher/tasks.py`.
- `apps/calendar` (scheduling/queues), `apps/approvals`, `apps/media_library` (Pillow/FFmpeg processing), `apps/inbox` (sync + inbound webhooks at `/webhooks/`), `apps/analytics` sit around this core.

### Background jobs
- `@background` tasks live in `apps/<app>/tasks.py`. Recurring ones are registered idempotently from `post_migrate` via `apps.common.background.register_recurring_task` (keyed by `verbose_name`). Follow that pattern rather than hand-rolling registration.
- Jobs are rows in the `background_task` table; the worker (`process_tasks`) is the only thing that runs them.

### Agent API and MCP
- `apps/api` is a django-ninja API at `/api/v1/` (routers in `apps/api/routers/`, OpenAPI at `/api/v1/docs`). `apps/api/auth.py:ApiKeyAuth` resolves `Authorization: Bearer bb_studio_...` to an `ApiKey` (`apps/api_keys`) and duck-types `request.workspace_membership` so the same `require_permission` decorators work in Ninja routes. Key permissions are intersected with the issuer's live workspace permissions on every request.
- `apps/mcp` is a JSON-RPC 2.0 Streamable-HTTP MCP server mounted at `/api/v1/mcp`, sharing the API's auth, rate limits (`apps/api/limits.py`) and audit log. Registry in `apps/mcp/tools.py`; post/media/analytics tools in `apps/mcp/handlers.py`; inbox, ideas, schedule, approval and `notify_team` tools in `apps/mcp/handlers_autopilot.py` (both imported from `apps/mcp/apps.py`). New tools: define a handler `(args, context) -> dict`, re-check the workspace permission with `_require_perm`, scope reads by the key's `social_accounts` allowlist, and register with `register_tool`. The OAuth path substitutes a shim for `api_key`, so only use `.workspace_id`, `.social_accounts.all()`, `.issued_by`.
- `apps/autopilot` records agent runs (`AgentRun`) and serves the console: REST at `/api/v1/agent/*` (`apps/autopilot/api.py`: runs, command, decisions, policy, approvals) and runner MCP tools `record_run` / `claim_pending_run` / `finish_run` (`apps/autopilot/mcp_tools.py`). A console command is a `pending` run; `tasks.invoke_agentcore` hands it to AgentCore when `AGENT_RUNTIME_ARN` is set, otherwise `agent/run_local.py worker` claims it.
- Inbox replies go through `apps/inbox/services.py:send_reply` (shared by the HTMX view and the MCP tool). Agent-facing notification event types are `EventType.AGENT_DECISION_NEEDED` and `AGENT_DIGEST`.
- `apps/oauth_server` is an OAuth 2.1 authorization server (django-oauth-toolkit + dynamic client registration) so native MCP connectors like Claude Desktop can log in without an API key. Discovery docs are wired in `config/urls.py`.

### Cross-cutting helpers (`apps/common`)
- `encryption.py`: `EncryptedTextField` / `EncryptedJSONField` (AES-GCM, key derived from `SECRET_KEY` + `ENCRYPTION_KEY_SALT`). Use these for any token/secret column.
- `htmx.py`: `trigger_response` / `toast_response` for HTMX-driven views.
- `validators.py`: SSRF-safe URL checks, tag normalization, safe XML parsing.
- `context_processors.py:sidebar_context` builds the nav; heavy per-request logic belongs there only if it's needed on every page.

### Autopilot agent (`agent/`)
- Separate Python package with its own venv and `requirements.txt` (strands-agents, mcp, bedrock-agentcore). It has no Studio imports: it discovers tools from `/api/v1/mcp/` at runtime with a `bb_studio_` key.
- `Workspace.agent_autonomy` (`off` / `draft_only` / `autopilot`, edited on the approvals settings page) is the human's dial; the agent reads it through the `get_workspace_policy` MCP tool and `osir_agent/studio.py:select_tools` drops `SCHEDULE_TOOLS` unless autopilot, direct scheduling, and `publish_directly` all hold.
- `osir_agent/loops.py:run_task(task, instruction=)` runs one of `inbox` / `calendar` / `digest` / `command`; prompts and the escalation guardrails are in `osir_agent/prompts.py`; `osir_agent/studio.py:select_tools` hides `WRITE_TOOLS` in dry-run. `main.py` is the AgentCore entrypoint, `run_local.py` the CLI, `schedule/create_schedules.sh` the EventBridge Scheduler setup.
- Tests: `cd agent && pytest` (no network). Root `ruff check .` also covers `agent/`.

### Osir Console (`web/`)
- Next.js 15 App Router + TypeScript + Tailwind 4. Server components read from Studio through `lib/studio.ts` (server-only, one API key from `STUDIO_URL` / `STUDIO_API_KEY`); mutations are server actions in `app/actions.ts`. No client-side data fetching; `AutoRefresh` re-renders every 15s.
- Commands: `cd web && npm run dev`, `npm run build`, `npm run typecheck`. Needs a running Studio.

## Docs
- `README.md`: setup, per-platform OAuth app configuration, API/MCP reference, troubleshooting.
- `agent/README.md`: the autopilot's design, run and deploy instructions, and the architecture diagram.
