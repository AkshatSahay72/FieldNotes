from enum import Enum
from functools import lru_cache
from typing import Optional
from fastapi import Depends, HTTPException, status
from pydantic import Field, model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class AppMode(str, Enum):
    """Explicit application operational modes."""

    DEMO = "demo"
    AUTHENTICATED = "authenticated"
    DEVELOPMENT = "development"
    TESTING = "testing"


class Settings(BaseSettings):
    """Application settings loaded from environment variables or .env file."""

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
        populate_by_name=True,
    )

    app_env: str = Field(default="development", alias="APP_ENV")
    app_host: str = Field(default="127.0.0.1", alias="APP_HOST")
    app_port: int = Field(default=8000, alias="APP_PORT")

    # Explicit application mode ('demo', 'authenticated'/'personal'/'private', 'development', 'testing')
    app_mode: Optional[str] = Field(
        default=None,
        alias="APP_MODE",
        description="Explicit application operational mode",
    )

    # Required MongoDB connection settings - never hardcoded
    mongodb_uri: str = Field(
        ...,
        alias="MONGODB_URI",
        min_length=1,
        description="MongoDB connection URI string",
    )
    database_name: str = Field(
        default="fieldnote_db",
        alias="DATABASE_NAME",
        description="Target database name",
    )
    mongodb_server_selection_timeout_ms: int = Field(
        default=2000,
        alias="MONGODB_SERVER_SELECTION_TIMEOUT_MS",
        description="Timeout in milliseconds for server selection and health pings",
    )

    # File storage configuration for evidence attachments (Milestone 3)
    upload_dir: str = Field(default="uploads", alias="UPLOAD_DIR")

    # Vector embedding configuration (Milestone 6)
    embedding_model: str = Field(
        default="sentence-transformers/all-MiniLM-L6-v2",
        alias="EMBEDDING_MODEL",
        description="SentenceTransformers model identifier for vector embeddings",
    )

    # Public demo mode protection (Phase 2D.1)
    demo_mode: bool = Field(
        default=False,
        alias="DEMO_MODE",
        description="Enforces read-only public demo mode, rejecting all mutation operations",
    )

    # First-party authentication and session management
    session_cookie_name: str = Field(
        default="fieldnote_session",
        alias="SESSION_COOKIE_NAME",
        description="HTTP-only session cookie name",
    )
    csrf_cookie_name: str = Field(
        default="fieldnote_csrf",
        alias="CSRF_COOKIE_NAME",
        description="CSRF token cookie name readable by browser client",
    )
    session_lifetime_seconds: int = Field(
        default=7 * 24 * 3600,
        alias="SESSION_LIFETIME_SECONDS",
        description="Server-managed session duration in seconds (default 7 days)",
    )
    session_cookie_secure: Optional[bool] = Field(
        default=None,
        alias="SESSION_COOKIE_SECURE",
        description="Enforce Secure cookie attribute (defaults to True in production)",
    )
    session_cookie_samesite: str = Field(
        default="lax",
        alias="SESSION_COOKIE_SAMESITE",
        description="SameSite cookie policy ('lax', 'strict', or 'none')",
    )
    rate_limit_auth_requests: int = Field(
        default=10,
        alias="RATE_LIMIT_AUTH_REQUESTS",
        description="Maximum authentication attempts allowed per window",
    )
    rate_limit_auth_window_seconds: int = Field(
        default=60,
        alias="RATE_LIMIT_AUTH_WINDOW_SECONDS",
        description="Rate limiting sliding window in seconds",
    )

    @property
    def is_cookie_secure(self) -> bool:
        """Determine whether cookies should have the Secure flag.

        Explicit SESSION_COOKIE_SECURE overrides; defaults to True in production and False otherwise.
        """
        if self.session_cookie_secure is not None:
            return self.session_cookie_secure
        return self.app_env.lower() == "production"

    @property
    def resolved_app_mode(self) -> AppMode:
        """Resolve effective operational mode from explicit APP_MODE, DEMO_MODE, or APP_ENV."""
        if self.app_mode:
            normalized = self.app_mode.strip().lower()
            if normalized in ("demo",):
                return AppMode.DEMO
            if normalized in ("authenticated", "personal", "private"):
                return AppMode.AUTHENTICATED
            if normalized in ("development", "dev"):
                return AppMode.DEVELOPMENT
            if normalized in ("testing", "test"):
                return AppMode.TESTING
            raise ValueError(
                f"Invalid APP_MODE '{self.app_mode}'. Supported modes: "
                "'demo', 'authenticated' (or 'personal'/'private'), 'development', 'testing'."
            )

        if self.demo_mode:
            return AppMode.DEMO
        if self.app_env.lower() == "testing":
            return AppMode.TESTING
        if self.app_env.lower() == "production":
            return AppMode.AUTHENTICATED
        return AppMode.DEVELOPMENT

    @property
    def is_demo_mode(self) -> bool:
        """Determine whether application runs in read-only public demo mode."""
        return self.resolved_app_mode == AppMode.DEMO or self.demo_mode is True

    @property
    def requires_authentication_for_writes(self) -> bool:
        """Determine whether writes strictly require an authenticated user session."""
        return (
            self.resolved_app_mode == AppMode.AUTHENTICATED
            or self.app_env.lower() == "production"
        )

    @model_validator(mode="after")
    def validate_mode_and_database(self) -> "Settings":
        """Validate operational mode and enforce fail-closed database separation rules."""
        # 1. Validate explicit APP_MODE string if supplied
        if self.app_mode:
            normalized = self.app_mode.strip().lower()
            valid_modes = {
                "demo",
                "authenticated",
                "personal",
                "private",
                "development",
                "dev",
                "testing",
                "test",
            }
            if normalized not in valid_modes:
                raise ValueError(
                    f"Invalid APP_MODE '{self.app_mode}'. Supported modes: "
                    "'demo', 'authenticated' (or 'personal'/'private'), 'development', 'testing'."
                )

        effective_mode = self.resolved_app_mode
        demo_mode_set = "demo_mode" in self.model_fields_set or "DEMO_MODE" in self.model_fields_set

        # 2. Check for conflicting explicit configuration
        if effective_mode == AppMode.AUTHENTICATED:
            if self.demo_mode is True:
                raise ValueError("Conflicting configuration: APP_MODE is 'authenticated' but DEMO_MODE is True.")
            self.demo_mode = False
        elif effective_mode == AppMode.DEMO:
            self.demo_mode = True

        # 3. Database separation and fail-closed validation
        has_explicit_db = (
            "database_name" in self.model_fields_set
            or "DATABASE_NAME" in self.model_fields_set
        )

        if effective_mode == AppMode.DEMO:
            if not has_explicit_db:
                raise ValueError(
                    "When DEMO_MODE is enabled, a dedicated demo database must be explicitly configured via DATABASE_NAME."
                )
            if self.database_name == "fieldnote_db":
                raise ValueError(
                    "When DEMO_MODE is enabled, DATABASE_NAME cannot target the default development database ('fieldnote_db'). "
                    "Please specify a dedicated demo database (e.g. 'fieldnote_demo')."
                )
        elif effective_mode == AppMode.AUTHENTICATED:
            if not has_explicit_db:
                raise ValueError(
                    "In authenticated private mode (APP_MODE=authenticated or production deployment), "
                    "DATABASE_NAME must be explicitly configured. It will never default to 'fieldnote_db' or silently select a database."
                )
            if self.database_name == "fieldnote_db":
                raise ValueError(
                    "In authenticated private mode, DATABASE_NAME cannot target the default development database ('fieldnote_db'). "
                    "Please configure a dedicated private database (e.g. 'fieldnote_private')."
                )
            if self.database_name == "fieldnote_demo":
                raise ValueError(
                    "In authenticated private mode, DATABASE_NAME cannot target the public demo database ('fieldnote_demo'). "
                    "Private user data and demo data must remain strictly isolated."
                )
        elif effective_mode == AppMode.DEVELOPMENT:
            if self.database_name == "fieldnote_demo" and not self.demo_mode:
                raise ValueError(
                    "DATABASE_NAME cannot target 'fieldnote_demo' outside of demo mode. "
                    "Demo data must remain isolated."
                )

        return self


@lru_cache
def get_settings() -> Settings:
    """Return cached application settings singleton."""
    return Settings()


def check_demo_mode(settings: Settings = Depends(get_settings)) -> None:
    """Enforce read-only public demo mode protection.

    Rejects write-capable API operations with HTTP 403 Forbidden when running in demo mode.
    """
    if settings.is_demo_mode:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Operation not permitted in demo mode.",
        )
