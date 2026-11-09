# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## FastAPI Boilerplate API

FastAPI backend for FastAPI Boilerplate. Python 3.14, PostgreSQL 18.0, SQLModel 0.0.38 ORM, Alembic migrations.

## Commands

```bash
# Install dependencies
uv sync --all-groups

# Run dev server (Docker)
docker compose up --build

# Lint
uv run ruff check --fix .

# Format
uv run ruff format .

# Type check
uv run pyrefly

# Run all pre-commit hooks
uv run pre-commit run --all-files

# Tests (requires running PostgreSQL — use Docker or .env.test on host)
uv run pytest tests/unit_tests -v

# Tests in parallel
uv run pytest tests/unit_tests -n auto -v

# Tests (single file)
uv run pytest tests/unit_tests/test_bookings.py -v

# Tests inside Docker
docker compose exec backend pytest tests/unit_tests -v

# Generate migration
docker compose exec backend alembic revision --autogenerate -m "<message>"

# Run migrations
docker compose exec backend alembic upgrade head

# Seed database
docker compose exec backend python app/initial_data.py reseed-all
```

## Project Layout

```
app/
  main.py              # FastAPI app creation, middleware, all router registration
  settings.py          # Pydantic BaseSettings (singleton: `settings`), UPLOAD_DIR_ROOT, STATIC_ASSETS_PATH
  database.py          # Async SQLAlchemy engine, SessionDep, get_async_session
  storage.py           # DigitalOcean Spaces (S3-compatible) upload/download helpers
  email_utils.py       # SMTP email sending utility
  seed.py / initial_data.py  # DB population scripts
  auth/                # OTP login, JWT (RS256) tokens, device auth
  bookings/            # Booking management with status workflow
  core/
    errors.py          # Custom exceptions (InvalidToken, AccessTokenRequired, etc.) + handlers
    models.py          # Shared SQLModel base models (Revision, TermsAndConditions)
    routers/           # Shared routers (assets: presigned URL generation)
    schemas.py         # Shared Pydantic schemas
  invoices/            # Invoices and payments
  jobs/                # Operations (teams, jobs, photos, status transitions)
  leads/               # CRM pipeline (leads, quotes, follow-ups)
  migrations/          # Alembic migration scripts
  notifications/       # Email notification service (Jinja2 templates + SMTP), communication logs
  portal/              # Customer-facing APIs (dashboard, self-booking, photos)
  properties/          # Property profiles, contact linking, discount tracking
  rbac/                # Role-based access control + FastAPI dependencies
  services/            # Service catalog (categories, services, areas, rates)
  timeline/            # Central audit trail (polymorphic event log for all domain actions)
  user/                # Profile CRUD, device registration for push tokens
  utils/               # Shared utility helpers
tests/
  conftest.py          # DB setup: creates per-worker test PostgreSQL DB, all fixtures
  unit_tests/          # Main test suite
  integration_tests/   # Integration tests
conftest.py            # Root conftest: loads .env.test before app imports
```

## Key Patterns

**Settings**: `from app.settings import settings` — Pydantic BaseSettings singleton. `SecretStr` fields need `.get_secret_value()`. No env_file loaded at runtime; requires env vars to be set before process start.

**Database session**: `SessionDep = Annotated[AsyncSession, Depends(get_async_session)]` from `app.database`. In `db_service.py`, call `session.flush()` after adds/updates (not `commit()`). Routes call `await session.commit()` then `await session.refresh(obj)` after the db_service call.

**RBAC**: `from app.rbac.dependencies import AdminUser, SalesUser, OpsUser, StaffUser, CurrentUser` — typed annotated dependencies for route signatures. Admins bypass all role checks. `require_roles(*roles)` factory builds one-off role requirements.

**Timeline / audit trail**: Call `timeline.db_service.log_event(session, entity_type=..., entity_id=..., action=..., property_id=..., actor_id=..., actor_type=..., description=...)` from within `db_service` functions after flushing the entity. Every significant state change (create, status update, delete) should emit a timeline event.

**Router split**: Each domain module has two router files — `routes.py` (customer-facing) and `admin_routes.py` (staff/admin). Both are registered in `app/main.py`. Admin routes use `/admin/<resource>` prefix with staff/admin role dependencies.

**Notifications**: `notifications.services.send_notification_email(session, recipient_email=..., template_name=NotificationTemplateName.X, context={...})` — renders Jinja2 HTML template from `app/notifications/templates/`, sends via SMTP, and writes to `communication_logs`.

**File uploads**: `storage.py` wraps aioboto3 for DigitalOcean Spaces in production; local `uploads/` directory in development. `settings.has_s3_configured()` checks if S3 is available.

**Error responses**: All errors use `JSONResponse` with `{"message": ..., "error_code": ..., "resolution": ...}` shape. Raise `HTTPException` in routes; domain errors raise `ValueError` in db_service (caught and re-raised as `HTTPException` in routes).

## Code Style

- **Line length**: 120 characters
- **Formatter**: ruff format (double quotes, space indentation)
- **Linter**: ruff check with extended rules (B, BLE, C4, ERA, I, N, S, SIM, RUF, etc.)
- **Type checker**: pyrefly (`uv run pyrefly`) — native Pydantic support
- **Imports**: isort via ruff — case-sensitive, combine-as-imports, first-party = `app`, `tests`
- **Max complexity**: mccabe 10

## Pre-commit Hooks (run order)

1. Standard checks (trailing whitespace, merge conflicts, JSON/YAML/TOML validation, large files)
2. pyupgrade (`--py314-plus`)
3. bandit (`-iii -ll`)
4. ruff check + ruff format
5. codespell
6. pyrefly

## Testing

- Framework: pytest-asyncio (`asyncio_mode = "auto"`, session-scoped event loop)
- Coverage minimum: **60%** (`fail_under = 60`)
- Tests require a live PostgreSQL instance. The `setup_test_database` session-scoped fixture creates a fresh per-worker database (`test_<worker>`), runs all migrations, then drops it on teardown.
- Parallel runs supported via pytest-xdist (`-n auto`); each worker gets its own isolated database.
- **Root `conftest.py`** loads `.env.test` (project root) before any app imports — required when running outside Docker. Create `.env.test` with `POSTGRES_HOST=localhost` and credentials.

### Available fixtures

| Fixture | Scope | Description |
| --- | --- | --- |
| `session` | function | Transactional `AsyncSession` for the test DB |
| `client` | function | `TestClient` with `session` injected |
| `async_client` | function | `AsyncClient` (httpx2 ASGI) with `session` injected |
| `auth_client` | function | `TestClient` with JWT Bearer header for `test_user` |
| `async_auth_client` | function | `AsyncClient` with JWT Bearer header for `test_user` |
| `test_user` | function | Seeded active `User` (no T&C) |
| `test_user_with_tnc` | function | Seeded active `User` with T&C accepted |
| `auth_headers` | function | `{"Authorization": "Bearer <token>"}` dict for `test_user` |
| `auth_headers_tnc` | function | Same but for `test_user_with_tnc` |

## Environment

Copy `.env.example` to `.env`. Key variables:

- `ENVIRONMENT`: `development` | `staging` | `production`
- `POSTGRES_USER`, `POSTGRES_PASSWORD`, `POSTGRES_DB`, `POSTGRES_HOST`, `POSTGRES_PORT`
- `REDIS_URI`: Redis connection (used for OTP storage and JWT blocklist)
- `JWT_PRIVATE_KEY`, `JWT_PUBLIC_KEY`: RSA key pair for JWT signing (RS256)
- `DO_SPACES_*`: DigitalOcean Spaces credentials for file uploads
- `SMTP_HOST`, `SMTP_PORT`, `MAIL_FROM`: Email delivery config
- `POSTHOG_API_KEY`, `POSTHOG_HOST`: Analytics

## Docker

- `compose.yml`: PostgreSQL 18.0 (port 5432), app (port 8080)
- Dev target auto-reloads on file changes
- `entrypoint.sh` runs `alembic upgrade head` before app start

## CI/CD

- PR checks: pre-commit hooks + unit tests (`code-quality-checks.yml`)
- Deploy: Docker build → DigitalOcean Container Registry → App Platform (`build-and-deploy-do.yml`)

## Gotchas

- **Settings import**: `from app.settings import settings` — not `app.core.config`
- **`metadata` attribute**: SQLAlchemy reserves the name `metadata`. Use `extra_data` with `sa_column=Column("metadata", JSONB)` for JSONB columns that need to map to a column named `metadata` in the DB.
- **`session.flush()` vs `session.commit()`**: `db_service` functions flush (not commit) so timeline events and the parent entity land in the same transaction. Only routes call `commit()`.
- **Alembic outside Docker**: Set `POSTGRES_HOST=localhost` (or use `.env.test`) when running `alembic` from the host machine.
- **ServiceCategory self-referential**: Needs explicit `foreign_keys` and `remote_side` on the relationship.
- **WebSocket heartbeat**: 30s interval, 45s timeout — clients must respond to pings.
