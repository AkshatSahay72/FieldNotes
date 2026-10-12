from functools import lru_cache
from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """Application settings loaded from environment variables or .env file."""

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
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


@lru_cache
def get_settings() -> Settings:
    """Return cached application settings singleton."""
    return Settings()
