from functools import lru_cache
from fastapi import Depends, HTTPException, status
from pydantic import Field, model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


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

    @model_validator(mode="after")
    def validate_demo_database(self) -> "Settings":
        """Ensure demo mode explicitly selects a dedicated demo database rather than falling back to dev DB."""
        if self.demo_mode:
            has_explicit_db = (
                "database_name" in self.model_fields_set
                or "DATABASE_NAME" in self.model_fields_set
            )
            if not has_explicit_db:
                raise ValueError(
                    "When DEMO_MODE is enabled, a dedicated demo database must be explicitly configured via DATABASE_NAME."
                )
            if self.database_name == "fieldnote_db":
                raise ValueError(
                    "When DEMO_MODE is enabled, DATABASE_NAME cannot target the default development database ('fieldnote_db'). "
                    "Please specify a dedicated demo database (e.g. 'fieldnote_demo')."
                )
        return self


@lru_cache
def get_settings() -> Settings:
    """Return cached application settings singleton."""
    return Settings()


def check_demo_mode(settings: Settings = Depends(get_settings)) -> None:
    """Enforce read-only public demo mode protection.

    Rejects write-capable API operations with HTTP 403 Forbidden when DEMO_MODE is active.
    """
    if settings.demo_mode:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Operation not permitted in demo mode.",
        )
