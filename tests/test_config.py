import pytest
from pydantic import ValidationError
from app.config import Settings


def test_settings_load_with_valid_mongodb_uri(monkeypatch):
    """Test that settings load successfully when MONGODB_URI is provided."""
    monkeypatch.setenv("MONGODB_URI", "mongodb+srv://user:pass@cluster.mongodb.net/?retryWrites=true")
    monkeypatch.setenv("DATABASE_NAME", "test_fieldnote_db")
    monkeypatch.setenv("APP_ENV", "testing")
    monkeypatch.setenv("MONGODB_SERVER_SELECTION_TIMEOUT_MS", "3000")

    settings = Settings()

    assert settings.mongodb_uri == "mongodb+srv://user:pass@cluster.mongodb.net/?retryWrites=true"
    assert settings.database_name == "test_fieldnote_db"
    assert settings.app_env == "testing"
    assert settings.mongodb_server_selection_timeout_ms == 3000
    assert settings.app_host == "127.0.0.1"
    assert settings.app_port == 8000
    assert settings.upload_dir == "uploads"
    assert settings.embedding_model == "sentence-transformers/all-MiniLM-L6-v2"


def test_settings_custom_embedding_model(monkeypatch):
    """Test that EMBEDDING_MODEL environment variable overrides the default model."""
    monkeypatch.setenv("MONGODB_URI", "mongodb://localhost:27017")
    monkeypatch.setenv("EMBEDDING_MODEL", "custom-org/custom-model")

    settings = Settings()
    assert settings.embedding_model == "custom-org/custom-model"


def test_settings_missing_mongodb_uri_raises_validation_error(monkeypatch):
    """Test that missing MONGODB_URI raises a clear ValidationError."""
    monkeypatch.delenv("MONGODB_URI", raising=False)

    with pytest.raises(ValidationError) as exc_info:
        Settings(_env_file=None)

    errors = exc_info.value.errors()
    field_names = [err["loc"][0] for err in errors]
    assert "MONGODB_URI" in field_names or "mongodb_uri" in field_names


def test_settings_empty_mongodb_uri_raises_validation_error(monkeypatch):
    """Test that empty string MONGODB_URI raises ValidationError due to min_length constraint."""
    monkeypatch.setenv("MONGODB_URI", "")

    with pytest.raises(ValidationError):
        Settings(_env_file=None)
