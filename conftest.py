"""
Root conftest.py - loads .env.test and overrides POSTGRES_HOST to localhost
so the test suite can connect to the Dockerised Postgres from the host machine.

This file is intentionally placed at the project root so that pytest processes
it *before* any imports from ``app.*`` take place, ensuring pydantic-settings
picks up all required variables.
"""

import os
from pathlib import Path

from dotenv import load_dotenv

# ---------------------------------------------------------------------------
# Load test environment variables BEFORE any app module is imported.
# ``override=True`` ensures these values win over any already-set shell vars.
# ---------------------------------------------------------------------------
_env_file = Path(__file__).parent / ".env.test"
load_dotenv(_env_file, override=True)

# The DB service is reachable as "database" in Docker Compose. When running
# tests directly on the host we need to speak to the container on localhost instead.
# When running inside the container (e.g. backend service), we should speak to "database".
default_host = "database" if Path("/.dockerenv").exists() else "localhost"
os.environ["POSTGRES_HOST"] = os.getenv("TEST_POSTGRES_HOST", default_host)
