from collections.abc import Sequence
from pathlib import Path

from pydantic import EmailStr, Field, HttpUrl, PostgresDsn, SecretStr, computed_field
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_ignore_empty=True,
        env_file_encoding="utf-8",
        case_sensitive=False,
        extra="ignore",
    )
    PROJECT_NAME: str = "FastAPI Performance & Containerization"
    SERVICE_PATH: str | None = None
    LOG_LEVEL: str = "INFO"
    ENVIRONMENT: str = "development"
    CORS_ORIGINS: Sequence[str] = Field(default=["*"])
    TRUSTED_HOSTS: Sequence[str] = Field(default=["*"])
    ALLOWED_STAFF_EMAIL_DOMAINS: Sequence[str] = Field(default=["example.com", "benchmark.local"])

    ADMIN_DASHBOARD_BASE_URL: HttpUrl = HttpUrl("http://localhost:8080/")
    ADMIN_EMAIL: EmailStr = "admin@example.com"
    ADMIN_MOBILE: str = "+1234567890"
    ADMIN_PASSWORD: SecretStr = SecretStr("Admin123456!")

    # Database
    POSTGRES_USER: SecretStr = SecretStr("postgres")
    POSTGRES_PASSWORD: SecretStr = SecretStr("postgres")
    POSTGRES_DB: str = "benchmark_db"
    POSTGRES_HOST: str = "localhost"
    POSTGRES_PORT: int = 5432
    POSTGRES_USE_SSL: bool = False

    SECRET_KEY: SecretStr = SecretStr("super-secret-key-for-fastapi-benchmarking-32bytes-min")

    # Local testing SMTP
    SMTP_HOST: str | None = None
    SMTP_PORT: int = 1025
    MAIL_FROM: EmailStr = "no-reply@example.com"

    # Mailgun settings (optional)
    MAILGUN_API_KEY: SecretStr | None = None
    MAILGUN_DOMAIN: str | None = None
    MAILGUN_API_BASE_URL: str | None = None

    # PostHog settings (optional)
    POSTHOG_ENABLED: bool = False
    POSTHOG_API_KEY: SecretStr | None = None
    POSTHOG_HOST: HttpUrl = HttpUrl("https://app.posthog.com")

    # Object storage (optional)
    DO_SPACES_KEY: str | None = None
    DO_SPACES_SECRET: str | None = None
    DO_SPACES_REGION: str | None = None
    DO_SPACES_BUCKET: str | None = None
    DO_SPACES_ENDPOINT: HttpUrl | None = None
    DO_SPACES_CDN_ENDPOINT: HttpUrl | None = None

    # Upload configuration
    MAX_UPLOAD_FILE_SIZE: int = Field(default=10, description="Max upload file size in MB")

    # JWT Settings (defaults provided for out-of-the-box local benchmarking)
    JWT_PRIVATE_KEY: SecretStr = SecretStr("")
    JWT_PUBLIC_KEY: SecretStr = SecretStr("")
    JWT_ALGORITHM: str = "HS256"
    JWT_EXPIRY_TIME: int = 60 * 24 * 7  # 7 days
    JWT_REFRESH_EXPIRY_TIME: int = 60 * 24 * 28  # 28 days
    JWT_AUDIENCE: HttpUrl = HttpUrl("http://localhost:8080/")
    JWT_ISSUER: HttpUrl = HttpUrl("http://localhost:8080/")
    JWT_AUTH_URL: HttpUrl = HttpUrl("http://localhost:8080/v1/auth/login")
    JWT_AUTH_TOKEN_URL: HttpUrl = HttpUrl("http://localhost:8080/v1/auth/token")
    OTP_EXPIRY_MINUTES: int = 5

    # Google SSO Settings (optional)
    GOOGLE_CLIENT_ID: str | None = None
    GOOGLE_CLIENT_SECRET: SecretStr | None = None

    STATIC_ASSETS_PATH: str = "/assets"

    @computed_field
    @property
    def DATABASE_URL_SYNC(self) -> str:  # noqa: N802
        return PostgresDsn.build(
            scheme="postgresql+psycopg",
            username=self.POSTGRES_USER.get_secret_value(),
            password=self.POSTGRES_PASSWORD.get_secret_value(),
            host=self.POSTGRES_HOST,
            port=self.POSTGRES_PORT,
            path=self.POSTGRES_DB,
        ).__str__()

    @computed_field
    @property
    def DATABASE_URL_ASYNC(self) -> str:  # noqa: N802
        return PostgresDsn.build(
            scheme="postgresql+asyncpg",
            username=self.POSTGRES_USER.get_secret_value(),
            password=self.POSTGRES_PASSWORD.get_secret_value(),
            host=self.POSTGRES_HOST,
            port=self.POSTGRES_PORT,
            path=self.POSTGRES_DB,
        ).__str__()

    def has_s3_configured(self) -> bool:
        return bool(self.DO_SPACES_KEY and self.DO_SPACES_SECRET and self.DO_SPACES_BUCKET)


settings = Settings()

STATIC_ASSETS_PATH = Path("static-assets")
STATIC_ASSETS_PATH.mkdir(exist_ok=True)

UPLOAD_DIR_ROOT = Path("uploads")
UPLOAD_DIR_ROOT.mkdir(exist_ok=True)
