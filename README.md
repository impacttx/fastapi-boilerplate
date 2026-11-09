# FastAPI Boilerplate - High-Performance & Containerization Reference

A reference Python backend implementing production-grade Authentication, Role-Based Access Control (RBAC), User Profiling, and Items CRUD on PostgreSQL 18. Built as a benchmark and architectural counterpart to [Axum Boilerplate](https://github.com/impacttx/axum-boilerplate) for the blog article *"Rust's Axum vs Python's FastAPI - Performance and Containerization"*.

---

## ⚡ Tech Stack & Tools

- **Runtime & Framework**: Python `>=3.14`, FastAPI `>=0.162.2` (Starlette ASGI engine), Uvicorn
- **Data Validation & Modeling**: Pydantic `>=2.12`, SQLModel, SQLAlchemy 2.0 (asyncio + `asyncpg`)
- **Package & Virtualenv Management**: [uv](https://docs.astral.sh/uv/)
- **Database & Migrations**: PostgreSQL `18-alpine`, Alembic
- **Testing**: Pytest, pytest-asyncio, httpx2
- **Code Quality**: Ruff (linter & formatter), Bandit (AST security analysis), Codespell
- **Git Hooks**: [Prek](https://prek.j178.dev) (Rust-powered Git hook framework)
- **Containerization**: Multi-stage `Dockerfile` with non-root user, `compose.yml`

---

## 🚀 Quick Start

### 1. Prerequisites

Ensure you have `uv` and Docker installed:

```bash
# Install uv (if not already installed)
curl -LsSf https://astral.sh/uv/install.sh | sh
```

### 2. Local Setup

```bash
# 1. Sync virtual environment and dependencies
uv sync --all-groups

# 2. Configure environment
cp .env.example .env.dev

# 3. Start PostgreSQL 18 with Docker Compose
docker compose up db -d

# 4. Run database migrations
uv run alembic upgrade head

# 5. Run seed script (admin user & roles)
uv run python -m app.seed

# 6. Start development server
uv run fastapi dev app/main.py --host 0.0.0.0 --port 8000
```

Swagger UI will be available at: `http://localhost:8000/docs`

---

## 🐳 Docker Deployment

To build and run the entire stack (FastAPI + PostgreSQL 18):

```bash
docker compose up --build
```

Healthcheck endpoint: `http://localhost:8000/health`

---

## 🧪 Testing & Code Quality

```bash
# Run unit tests
uv run pytest -v

# Run linting and code formatting
uv run ruff check --fix
uv run ruff format

# Run security static analysis
uv run bandit -ll -iii -r app

# Run spell checking
uv run codespell

# Run all git hooks via Prek
prek run --all-files
```

---

## 📊 Benchmarking

Run the automated load test suite against this server using `hey` or `wrk`:

```bash
./scripts/benchmark.sh
```

Or run manual benchmarks:

```bash
# Health endpoint (Raw HTTP / ASGI overhead)
hey -n 20000 -c 50 http://localhost:8000/health

# Read query (SQLAlchemy + asyncpg + Pydantic serialization)
hey -n 10000 -c 50 http://localhost:8000/v1/items/?limit=20

# Write mutation (Pydantic validation + Postgres transaction)
hey -n 5000 -c 50 -m POST \
  -H "Content-Type: application/json" \
  -d '{"title":"Load Test","is_completed":false}' \
  http://localhost:8000/v1/items/
```

---

## 📁 Project Structure

```
├── app/
│   ├── auth/          # JWT tokens, password hashing, OAuth helpers
│   ├── core/          # App initialization, middleware, DB engine
│   ├── items/         # Benchmark CRUD models, schemas, and routes
│   ├── migrations/    # Alembic database migrations
│   ├── rbac/          # Role-Based Access Control policies
│   ├── user/          # User profiling and credentials
│   ├── main.py        # ASGI application entrypoint
│   └── seed.py        # Database bootstrap seeder
├── scripts/
│   └── benchmark.sh   # Automated load testing script
├── tests/             # Unit and integration test suite
├── compose.yml        # Docker compose with Postgres 18-alpine
├── Dockerfile         # Multi-stage optimized container image
├── prek.toml          # Prek git hooks configuration
└── pyproject.toml     # uv project configuration and dependencies
```
