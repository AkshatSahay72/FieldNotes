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


def test_demo_mode_without_explicit_database_fails(monkeypatch):
    """Test that enabling DEMO_MODE without explicitly setting DATABASE_NAME fails closed."""
    monkeypatch.setenv("MONGODB_URI", "mongodb://localhost:27017")
    monkeypatch.setenv("DEMO_MODE", "true")
    monkeypatch.delenv("DATABASE_NAME", raising=False)

    with pytest.raises(ValidationError) as exc_info:
        Settings(_env_file=None)
    assert "dedicated demo database must be explicitly configured" in str(exc_info.value)


def test_demo_mode_targeting_default_database_fails(monkeypatch):
    """Test that DEMO_MODE targeting default 'fieldnote_db' fails closed."""
    monkeypatch.setenv("MONGODB_URI", "mongodb://localhost:27017")
    monkeypatch.setenv("DEMO_MODE", "true")
    monkeypatch.setenv("DATABASE_NAME", "fieldnote_db")

    with pytest.raises(ValidationError) as exc_info:
        Settings(_env_file=None)
    assert "cannot target the default development database" in str(exc_info.value)


def test_demo_mode_with_valid_explicit_database_succeeds(monkeypatch):
    """Test that DEMO_MODE with explicit 'fieldnote_demo' succeeds."""
    monkeypatch.setenv("MONGODB_URI", "mongodb://localhost:27017")
    monkeypatch.setenv("DEMO_MODE", "true")
    monkeypatch.setenv("DATABASE_NAME", "fieldnote_demo")

    settings = Settings(_env_file=None)
    assert settings.is_demo_mode is True
    assert settings.database_name == "fieldnote_demo"


def test_authenticated_mode_without_explicit_database_fails(monkeypatch):
    """Test that authenticated private mode without explicit DATABASE_NAME fails closed."""
    monkeypatch.setenv("MONGODB_URI", "mongodb://localhost:27017")
    monkeypatch.setenv("APP_MODE", "authenticated")
    monkeypatch.delenv("DATABASE_NAME", raising=False)

    with pytest.raises(ValidationError) as exc_info:
        Settings(_env_file=None)
    assert "DATABASE_NAME must be explicitly configured" in str(exc_info.value)


def test_authenticated_mode_targeting_default_database_fails(monkeypatch):
    """Test that authenticated private mode targeting 'fieldnote_db' fails closed."""
    monkeypatch.setenv("MONGODB_URI", "mongodb://localhost:27017")
    monkeypatch.setenv("APP_MODE", "authenticated")
    monkeypatch.setenv("DATABASE_NAME", "fieldnote_db")

    with pytest.raises(ValidationError) as exc_info:
        Settings(_env_file=None)
    assert "cannot target the default development database" in str(exc_info.value)


def test_authenticated_mode_targeting_demo_database_fails(monkeypatch):
    """Test that authenticated private mode targeting 'fieldnote_demo' fails closed."""
    monkeypatch.setenv("MONGODB_URI", "mongodb://localhost:27017")
    monkeypatch.setenv("APP_MODE", "authenticated")
    monkeypatch.setenv("DATABASE_NAME", "fieldnote_demo")

    with pytest.raises(ValidationError) as exc_info:
        Settings(_env_file=None)
    assert "cannot target the public demo database" in str(exc_info.value)


def test_authenticated_mode_with_valid_explicit_database_succeeds(monkeypatch):
    """Test that authenticated mode with dedicated database succeeds."""
    monkeypatch.setenv("MONGODB_URI", "mongodb://localhost:27017")
    monkeypatch.setenv("APP_MODE", "authenticated")
    monkeypatch.setenv("DATABASE_NAME", "fieldnote_private")

    settings = Settings(_env_file=None)
    assert settings.is_demo_mode is False
    assert settings.requires_authentication_for_writes is True
    assert settings.database_name == "fieldnote_private"


def test_conflicting_authenticated_and_demo_mode_fails(monkeypatch):
    """Test that setting APP_MODE=authenticated while DEMO_MODE=true raises ValidationError."""
    monkeypatch.setenv("MONGODB_URI", "mongodb://localhost:27017")
    monkeypatch.setenv("APP_MODE", "authenticated")
    monkeypatch.setenv("DEMO_MODE", "true")
    monkeypatch.setenv("DATABASE_NAME", "fieldnote_private")

    with pytest.raises(ValidationError) as exc_info:
        Settings(_env_file=None)
    assert "Conflicting configuration" in str(exc_info.value)


def test_invalid_app_mode_fails(monkeypatch):
    """Test that unsupported APP_MODE string raises ValidationError."""
    monkeypatch.setenv("MONGODB_URI", "mongodb://localhost:27017")
    monkeypatch.setenv("APP_MODE", "invalid_cluster_mode")

    with pytest.raises(ValidationError) as exc_info:
        Settings(_env_file=None)
    assert "Invalid APP_MODE" in str(exc_info.value)


def test_app_mode_aliases_resolve_correctly(monkeypatch):
    """Test that aliases 'personal' and 'private' map to authenticated mode."""
    monkeypatch.setenv("MONGODB_URI", "mongodb://localhost:27017")
    monkeypatch.setenv("DATABASE_NAME", "my_private_notes")

    for alias in ["personal", "private"]:
        monkeypatch.setenv("APP_MODE", alias)
        settings = Settings(_env_file=None)
        assert settings.requires_authentication_for_writes is True

    monkeypatch.setenv("APP_MODE", "dev")
    monkeypatch.setenv("DATABASE_NAME", "fieldnote_db")
    settings_dev = Settings(_env_file=None)
    assert settings_dev.requires_authentication_for_writes is False


def test_is_cookie_secure_production_vs_development(monkeypatch):
    """Test that cookie secure flag defaults to True in production and False in development."""
    monkeypatch.setenv("MONGODB_URI", "mongodb://localhost:27017")
    monkeypatch.setenv("APP_ENV", "production")
    monkeypatch.setenv("DATABASE_NAME", "fieldnote_prod")
    settings_prod = Settings(_env_file=None)
    assert settings_prod.is_cookie_secure is True

    monkeypatch.setenv("APP_ENV", "development")
    monkeypatch.setenv("DATABASE_NAME", "fieldnote_db")
    settings_dev = Settings(_env_file=None)
    assert settings_dev.is_cookie_secure is False

    # Explicit override takes precedence
    monkeypatch.setenv("SESSION_COOKIE_SECURE", "true")
    settings_override = Settings(_env_file=None)
    assert settings_override.is_cookie_secure is True
