# ─────────────────────────────────────────────────────────────────────────────────────
# Environment variables MUST be set before any app imports because
# app.settings instantiates Settings() eagerly at module import time.
# Dynamically generated secrets ensure cryptographic isolation between test runs.
# ─────────────────────────────────────────────────────────────────────────────────────
from datetime import UTC, datetime
import os
import secrets
import uuid

from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric import rsa

from app.core.models import TermsAndConditions


def _generate_rsa_pem_pair() -> tuple[str, str]:
    """Return (private_key_pem, public_key_pem) as PEM-encoded strings."""
    key = rsa.generate_private_key(public_exponent=65537, key_size=2048)
    private_pem = key.private_bytes(
        encoding=serialization.Encoding.PEM,
        format=serialization.PrivateFormat.TraditionalOpenSSL,
        encryption_algorithm=serialization.NoEncryption(),
    ).decode()
    public_pem = (
        key.public_key()
        .public_bytes(
            encoding=serialization.Encoding.PEM,
            format=serialization.PublicFormat.SubjectPublicKeyInfo,
        )
        .decode()
    )
    return private_pem, public_pem


_JWT_PRIVATE_KEY_PEM, _JWT_PUBLIC_KEY_PEM = _generate_rsa_pem_pair()

# --- Dynamically generated per test-run ---
os.environ.setdefault("SECRET_KEY", secrets.token_urlsafe(64))
os.environ.setdefault("JWT_EXPIRY_TIME", "60")
os.environ.setdefault("JWT_ALGORITHM", "RS256")
os.environ.setdefault("JWT_ISSUER", "http://localhost:8080/")
os.environ.setdefault("JWT_PRIVATE_KEY", _JWT_PRIVATE_KEY_PEM)
os.environ.setdefault("JWT_PUBLIC_KEY", _JWT_PUBLIC_KEY_PEM)

# Rest
os.environ.setdefault("ENVIRONMENT", "development")
os.environ.setdefault("LOG_LEVEL", "DEBUG")
os.environ.setdefault("PROJECT_NAME", "fastboil-test")
os.environ.setdefault("ADMIN_EMAIL", "admin@test.com")
os.environ.setdefault("ADMIN_MOBILE", "+919876543210")
os.environ.setdefault("ADMIN_PASSWORD", "admin")
os.environ["MAILGUN_API_KEY"] = ""
os.environ["MAILGUN_URL"] = ""
os.environ.setdefault("SMTP_HOST", "smtp.gmail.com")
os.environ.setdefault("MAIL_FROM", "no-reply@test.com")
os.environ.setdefault("POSTHOG_API_KEY", "123")
os.environ.setdefault("POSTHOG_HOST", "https://us.i.posthog.com")
os.environ.setdefault("DO_SPACES_KEY", "123")
os.environ.setdefault("DO_SPACES_SECRET", "123")
os.environ.setdefault("DO_SPACES_REGION", "sgp1")
os.environ.setdefault("DO_SPACES_BUCKET", "fastboil-test")
os.environ.setdefault("DO_SPACES_ENDPOINT", "https://sgp1.digitaloceanspaces.com")
os.environ.setdefault("DO_SPACES_CDN_ENDPOINT", "https://fastboil-test.sgp1.cdn.digitaloceanspaces.com")

# Get POSTGRES variables from environment
# If tests run inside docker web container, 'database' is the correct DB hostname
POSTGRES_HOST = os.getenv("POSTGRES_HOST", "database")
POSTGRES_DB = os.getenv("POSTGRES_DB", "fastboil_test")
POSTGRES_USER = os.getenv("POSTGRES_USER", "fastboil")
POSTGRES_PASSWORD = os.getenv("POSTGRES_PASSWORD", "fastboil")  # NOSONAR
POSTGRES_PORT = os.getenv("POSTGRES_PORT", "5432")

from collections.abc import AsyncGenerator

import asyncpg
from fastapi.testclient import TestClient
from httpx2 import ASGITransport, AsyncClient
import orjson
import pytest
import pytest_asyncio
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine
from sqlmodel import SQLModel
from sqlmodel.ext.asyncio.session import AsyncSession

# Import all models to ensure SQLModel has full metadata before table creation
from app.auth.models import *  # NOSONAR
from app.auth.models import User
from app.auth.security import create_access_token

# NOSONAR
from app.core.models import *  # NOSONAR
from app.core.models import Revision
from app.database import get_async_session, orjson_serializer

# Note: importing the Item model module registers the ``items`` table with
# SQLModel metadata so ``SQLModel.metadata.create_all`` creates it in tests.
import app.items.models  # noqa: F401

# NOSONAR
from app.rbac.models import *  # NOSONAR

# NOSONAR
# NOSONAR

# Base database URL (used to connect and run CREATE DATABASE)
TEST_DATABASE_URL = f"postgresql://{POSTGRES_USER}:{POSTGRES_PASSWORD}@{POSTGRES_HOST}:{POSTGRES_PORT}/postgres"
# Get the worker ID from pytest-xdist (if running in parallel); each worker gets its own DB
WORKER_ID = os.environ.get("PYTEST_XDIST_WORKER", "main")
# Generate a unique database name for each worker to avoid data collisions during parallel runs
TEST_DATABASE_NAME = f"test_{POSTGRES_DB}_{WORKER_ID}"
# Final database URL with the unique per-worker database name
FINAL_TEST_DATABASE_URL = (
    f"postgresql+asyncpg://{POSTGRES_USER}:{POSTGRES_PASSWORD}@{POSTGRES_HOST}:{POSTGRES_PORT}/{TEST_DATABASE_NAME}"
)

# NOTE: Do NOT define a custom event_loop fixture — it is removed in pytest-asyncio 1.x.


from unittest import mock


@pytest.fixture(scope="session", autouse=True)
def mock_smtp_globally():
    with mock.patch("smtplib.SMTP") as mock_smtp_class:
        instance = mock_smtp_class.return_value
        instance.__enter__.return_value = instance
        yield mock_smtp_class


@pytest.fixture(scope="session")
def monkeysession():
    with pytest.MonkeyPatch.context() as mp:
        yield mp


@pytest_asyncio.fixture(scope="session", loop_scope="session", autouse=True)
async def setup_test_database(monkeysession: pytest.MonkeyPatch):
    # Connect to the default PostgreSQL database to create the per-worker test database
    conn = await asyncpg.connect(TEST_DATABASE_URL)
    try:
        # Terminate all other connections to the test database if it already exists
        await conn.execute(
            f"""
            SELECT pg_terminate_backend(pg_stat_activity.pid)
            FROM pg_stat_activity
            WHERE pg_stat_activity.datname = '{TEST_DATABASE_NAME}'
            AND pid <> pg_backend_pid();
            """  # noqa: S608
        )
        # Drop the test database if it already exists (leftover from a crashed previous run)
        await conn.execute(f"DROP DATABASE IF EXISTS {TEST_DATABASE_NAME}")
        # Create a fresh test database for this worker
        await conn.execute(f"CREATE DATABASE {TEST_DATABASE_NAME}")
    finally:
        await conn.close()

    # Create the async engine for the test database
    engine = create_async_engine(FINAL_TEST_DATABASE_URL, echo=False)

    # Create all tables in the test database
    async with engine.begin() as econn:
        await econn.run_sync(SQLModel.metadata.create_all)

    from pydantic import SecretStr

    from app.settings import settings

    # Point the app's settings at the per-worker test database for the duration of the session
    monkeysession.setattr(settings, "POSTGRES_DB", SecretStr(TEST_DATABASE_NAME))

    yield  # Run tests here

    # Tear down: drop all tables, dispose engine, then drop the database
    async with engine.begin() as econn:
        await econn.run_sync(SQLModel.metadata.drop_all)

    await engine.dispose()

    # Drop the test database after all tests in this worker are done
    conn = await asyncpg.connect(TEST_DATABASE_URL)
    try:
        # Terminate all other connections to the test database before dropping it
        await conn.execute(
            f"""
            SELECT pg_terminate_backend(pg_stat_activity.pid)
            FROM pg_stat_activity
            WHERE pg_stat_activity.datname = '{TEST_DATABASE_NAME}'
            AND pid <> pg_backend_pid();
            """  # noqa: S608
        )
        await conn.execute(f"DROP DATABASE {TEST_DATABASE_NAME}")
    finally:
        await conn.close()


from sqlalchemy.pool import NullPool

# Global engine for all tests in this worker using NullPool to avoid cross-loop issues
test_engine = create_async_engine(
    FINAL_TEST_DATABASE_URL,
    echo=False,
    json_serializer=orjson_serializer,
    json_deserializer=orjson.loads,
    poolclass=NullPool,
)


@pytest.fixture(name="session")
async def session_fixture() -> AsyncGenerator[AsyncSession]:
    """Provide a transactional AsyncSession for each test."""

    # patch app.database.engine and app.database.async_session_maker
    import app.database

    app.database.engine = test_engine
    async_testing_session_local = async_sessionmaker(
        bind=test_engine,
        class_=AsyncSession,
        expire_on_commit=False,
    )
    app.database.async_session_maker = async_testing_session_local
    async with async_testing_session_local() as session:
        yield session


@pytest.fixture(name="client")
async def client_fixture(session: AsyncSession) -> AsyncGenerator[TestClient]:
    from app.main import app

    async def _override_session():
        yield session

    app.dependency_overrides[get_async_session] = _override_session
    yield TestClient(app)
    app.dependency_overrides.clear()


@pytest.fixture(name="auth_client")
async def test_auth_client(client: TestClient, test_user: User) -> AsyncGenerator[TestClient]:
    """
    A TestClient with a valid JWT Bearer token in its Authorization header.

    It uses the 'test_user' fixture for authentication.
    """
    token = create_access_token(str(test_user.id))
    client.headers["Authorization"] = f"Bearer {token}"
    yield client


@pytest.fixture(name="async_client")
async def async_client_fixture(session: AsyncSession) -> AsyncGenerator[AsyncClient]:
    from app.main import app

    async def _override_session():
        yield session

    app.dependency_overrides[get_async_session] = _override_session
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://testserver/v1") as client:
        yield client
    app.dependency_overrides.clear()


@pytest.fixture(name="async_auth_client")
async def async_auth_client_fixture(session: AsyncSession, test_user: User) -> AsyncGenerator[AsyncClient]:
    from app.main import app

    async def _override_session():
        yield session

    app.dependency_overrides[get_async_session] = _override_session
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://testserver/v1") as client:
        token = create_access_token(str(test_user.id))
        client.headers["Authorization"] = f"Bearer {token}"
        yield client
    app.dependency_overrides.clear()


# ---------------------------------------------------------------------------
# Authentication helpers
# ---------------------------------------------------------------------------


@pytest.fixture
async def test_user(session: AsyncSession) -> User:
    """Seed an active User (no TnC accepted) and return it."""
    user = User(mobile_number=f"+91{uuid.uuid4().int % 10_000_000_000:010d}", is_active=True)
    session.add(user)
    await session.commit()
    await session.refresh(user)
    return user


@pytest.fixture
async def test_user_with_tnc(session: AsyncSession) -> User:
    """Seed an active User who has already accepted the 'chat' TnC."""
    user = User(
        mobile_number=f"+91{uuid.uuid4().int % 10_000_000_000:010d}",
        is_active=True,
        accepted_terms={Revision.V1_0.value: datetime.now(tz=UTC)},
    )
    session.add(user)
    await session.commit()
    await session.refresh(user)
    return user


def _make_auth_headers(user: User) -> dict[str, str]:
    """Return Authorization headers for *user* with a freshly-minted JWT."""
    token = create_access_token(str(user.id))
    return {"Authorization": f"Bearer {token}"}


@pytest.fixture
async def auth_headers(test_user: User) -> dict[str, str]:
    """Bearer headers for *test_user* (no TnC)."""
    return _make_auth_headers(test_user)


@pytest.fixture
async def auth_headers_tnc(test_user_with_tnc: User) -> dict[str, str]:
    """Bearer headers for *test_user_with_tnc* (chat TnC accepted)."""
    return _make_auth_headers(test_user_with_tnc)


@pytest.fixture
async def tnc_record(session: AsyncSession) -> TermsAndConditions:
    """Seed an active TermsAndConditions record for the 'chat' module."""
    import uuid as _uuid

    tnc = TermsAndConditions(
        revision=f"v-test-{_uuid.uuid4().hex[:8]}",  # unique revision to avoid constraint collisions
        content="These are the test terms and conditions.",
        is_active=True,
    )
    session.add(tnc)
    await session.commit()
    await session.refresh(tnc)
    return tnc
