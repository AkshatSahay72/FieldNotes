from unittest.mock import MagicMock
import pytest
from fastapi.testclient import TestClient
from pymongo.errors import ServerSelectionTimeoutError, ConnectionFailure

from app.main import app, get_db_client
from app.config import Settings, get_settings


@pytest.fixture
def test_settings():
    """Isolated test settings fixture."""
    return Settings(
        MONGODB_URI="mongodb://localhost:27017",
        DATABASE_NAME="test_db",
        APP_ENV="testing",
        _env_file=None,
    )


def test_health_check_healthy(test_settings):
    """Verify /health returns 200 and healthy status when database ping succeeds."""
    mock_client = MagicMock()
    mock_client.admin.command.return_value = {"ok": 1.0}

    app.dependency_overrides[get_settings] = lambda: test_settings
    app.dependency_overrides[get_db_client] = lambda: mock_client

    with TestClient(app) as client:
        response = client.get("/health")
        assert response.status_code == 200
        data = response.json()
        assert data["status"] == "healthy"
        assert data["app"] == "ok"
        assert data["database"] == "connected"
        assert data["environment"] == "testing"

    app.dependency_overrides.clear()


def test_api_health_check_healthy(test_settings):
    """Verify /api/health also returns 200 and healthy status when database ping succeeds."""
    mock_client = MagicMock()
    mock_client.admin.command.return_value = {"ok": 1.0}

    app.dependency_overrides[get_settings] = lambda: test_settings
    app.dependency_overrides[get_db_client] = lambda: mock_client

    with TestClient(app) as client:
        response = client.get("/api/health")
        assert response.status_code == 200
        data = response.json()
        assert data["status"] == "healthy"
        assert data["app"] == "ok"
        assert data["database"] == "connected"

    app.dependency_overrides.clear()


def test_health_check_database_unreachable(test_settings):
    """Verify /health returns 503 and accurate failure status when database is unreachable.
    
    Ensures application availability is distinguished from database connectivity,
    and no internal connection details or stack traces are leaked.
    """
    mock_client = MagicMock()
    mock_client.admin.command.side_effect = ServerSelectionTimeoutError(
        "secret_user:secret_pass@cluster0.mongodb.net: Server selection timeout"
    )

    app.dependency_overrides[get_settings] = lambda: test_settings
    app.dependency_overrides[get_db_client] = lambda: mock_client

    with TestClient(app) as client:
        response = client.get("/health")
        assert response.status_code == 503
        data = response.json()
        assert data["status"] == "unhealthy"
        assert data["app"] == "ok"  # Application is running
        assert data["database"] == "disconnected"  # Database connection failed
        assert data["environment"] == "testing"

        # Verify no credentials or internal error strings leaked
        response_text = response.text
        assert "secret_user" not in response_text
        assert "secret_pass" not in response_text
        assert "mongodb.net" not in response_text
        assert "ServerSelectionTimeoutError" not in response_text

    app.dependency_overrides.clear()


def test_health_check_when_client_is_none(test_settings):
    """Verify /health handles uninitialized database client safely."""
    app.dependency_overrides[get_settings] = lambda: test_settings
    app.dependency_overrides[get_db_client] = lambda: None

    with TestClient(app) as client:
        response = client.get("/health")
        assert response.status_code == 503
        data = response.json()
        assert data["status"] == "unhealthy"
        assert data["app"] == "ok"
        assert data["database"] == "disconnected"

    app.dependency_overrides.clear()


def test_app_lifespan_initializes_and_closes_db_client(monkeypatch):
    """Verify lifespan creates MongoClient and attaches to app.state when MONGODB_URI is configured."""
    monkeypatch.setenv("MONGODB_URI", "mongodb://127.0.0.1:27017")
    monkeypatch.setenv("DATABASE_NAME", "fieldnote_test_db")
    get_settings.cache_clear()

    with TestClient(app):
        assert app.state.db_client is not None
        assert app.state.db.name == "fieldnote_test_db"

    get_settings.cache_clear()

