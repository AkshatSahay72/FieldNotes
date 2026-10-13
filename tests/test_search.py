from datetime import datetime, timezone
from bson import ObjectId
import pytest
from fastapi.testclient import TestClient
from pymongo.errors import OperationFailure, PyMongoError

from app.main import app
from app.db import get_database, get_gridfs
from app.config import Settings, get_settings
from app.services.embedding import get_embedding_service, InferenceError


class FakeEmbeddingService:
    """In-memory deterministic test double for EmbeddingService."""

    EXPECTED_DIMENSION = 384
    model_name = "sentence-transformers/all-MiniLM-L6-v2"

    def __init__(self, fail_inference: bool = False):
        self.fail_inference = fail_inference
        self.encoded_queries = []

    def generate_embedding(self, text: str):
        self.encoded_queries.append(text)
        if self.fail_inference:
            raise InferenceError("Mock inference engine offline")
        val = 1.0 / (384 ** 0.5)
        return [val] * 384


class FakeSearchCollection:
    """In-memory collection mock capturing pipelines and simulating aggregate."""

    def __init__(self, results=None, error_to_raise=None):
        self.results = results if results is not None else []
        self.error_to_raise = error_to_raise
        self.executed_pipeline = None

    def aggregate(self, pipeline):
        self.executed_pipeline = pipeline
        if self.error_to_raise:
            raise self.error_to_raise
        return iter(self.results)

    def find(self, *args, **kwargs):
        class EmptyCursor:
            def sort(self, *a, **k):
                return self
            def skip(self, *a, **k):
                return self
            def limit(self, *a, **k):
                return self
            def __iter__(self):
                return iter([])
        return EmptyCursor()


class FakeSearchDatabase:
    """In-memory database double providing the search collection."""

    def __init__(self, search_collection):
        self.search_collection = search_collection

    def __getitem__(self, name):
        if name == "notes":
            return self.search_collection
        # Dummy collection for other queries
        return FakeSearchCollection()


@pytest.fixture
def fake_embedding():
    return FakeEmbeddingService()


@pytest.fixture
def search_collection():
    return FakeSearchCollection()


@pytest.fixture
def client(search_collection, fake_embedding):
    """Test client with isolated settings, test database, and fake embedding service."""
    test_settings = Settings(
        MONGODB_URI="mongodb://localhost:27017",
        DATABASE_NAME="test_db",
        APP_ENV="testing",
        _env_file=None,
    )
    fake_db = FakeSearchDatabase(search_collection)

    app.dependency_overrides[get_settings] = lambda: test_settings
    app.dependency_overrides[get_database] = lambda: fake_db
    app.dependency_overrides[get_embedding_service] = lambda: fake_embedding

    with TestClient(app) as test_client:
        yield test_client

    app.dependency_overrides.clear()


# ==============================================================================
# Functional & Pipeline Validation Tests
# ==============================================================================

def test_semantic_search_success_and_pipeline_structure(client, search_collection, fake_embedding):
    """Verify successful semantic search executes proper $vectorSearch pipeline and formats results."""
    note_id = ObjectId()
    now = datetime(2026, 10, 13, 10, 0, 0, tzinfo=timezone.utc)
    mock_doc = {
        "_id": note_id,
        "title": "Soil Moisture Experiment",
        "content": "Volumetric water content reached 35% in plot A.",
        "tags": ["soil", "water"],
        "created_at": now,
        "updated_at": now,
        "score": 0.8924,
    }
    search_collection.results = [mock_doc]

    res = client.get("/api/search/semantic?q=moisture+in+plot+A&limit=5")

    assert res.status_code == 200
    data = res.json()
    assert len(data) == 1
    item = data[0]

    # Verify response schema fields
    assert item["id"] == str(note_id)
    assert item["title"] == "Soil Moisture Experiment"
    assert item["content"] == "Volumetric water content reached 35% in plot A."
    assert item["tags"] == ["soil", "water"]
    assert item["score"] == pytest.approx(0.8924, rel=1e-4)
    assert "embedding" not in item
    assert "embedding_model" not in item

    # Verify query text sent to embedding service
    assert fake_embedding.encoded_queries == ["moisture in plot A"]

    # Verify pipeline structure
    pipeline = search_collection.executed_pipeline
    assert len(pipeline) == 2

    # 1. First stage: $vectorSearch
    vstage = pipeline[0]["$vectorSearch"]
    assert vstage["index"] == "idx_notes_vector"
    assert vstage["path"] == "embedding"
    assert len(vstage["queryVector"]) == 384
    assert vstage["limit"] == 5
    # numCandidates = min(max(5*10, 20), 500) = 50
    assert vstage["numCandidates"] == 50

    # 2. Second stage: $project with score meta
    pstage = pipeline[1]["$project"]
    assert pstage["_id"] == 1
    assert pstage["title"] == 1
    assert pstage["content"] == 1
    assert pstage["tags"] == 1
    assert pstage["created_at"] == 1
    assert pstage["updated_at"] == 1
    assert pstage["score"] == {"$meta": "vectorSearchScore"}
    assert "embedding" not in pstage


def test_semantic_search_default_limit(client, search_collection):
    """Verify limit defaults to 10 with numCandidates=100 when limit param is omitted."""
    res = client.get("/api/search/semantic?q=sample+query")
    assert res.status_code == 200

    vstage = search_collection.executed_pipeline[0]["$vectorSearch"]
    assert vstage["limit"] == 10
    assert vstage["numCandidates"] == 100


def test_semantic_search_candidate_boundaries(client, search_collection):
    """Verify numCandidates enforces minimum bound (20) and maximum bound (500)."""
    # Test lower bound (limit=1: 1*10 < 20 -> 20)
    client.get("/api/search/semantic?q=low&limit=1")
    vstage_min = search_collection.executed_pipeline[0]["$vectorSearch"]
    assert vstage_min["limit"] == 1
    assert vstage_min["numCandidates"] == 20

    # Test upper bound (limit=50: 50*10 = 500 -> 500)
    client.get("/api/search/semantic?q=high&limit=50")
    vstage_max = search_collection.executed_pipeline[0]["$vectorSearch"]
    assert vstage_max["limit"] == 50
    assert vstage_max["numCandidates"] == 500


def test_semantic_search_empty_results_returns_empty_list(client, search_collection):
    """Verify zero matches return empty list 200 OK without errors."""
    search_collection.results = []
    res = client.get("/api/search/semantic?q=unmatched+concept")
    assert res.status_code == 200
    assert res.json() == []


# ==============================================================================
# Validation Error Tests
# ==============================================================================

def test_semantic_search_empty_or_whitespace_query_returns_400(client):
    """Verify empty or whitespace-only query string returns HTTP 400 Bad Request."""
    res_empty = client.get("/api/search/semantic?q=")
    assert res_empty.status_code == 400
    assert "cannot be empty or whitespace-only" in res_empty.json()["detail"]

    res_spaces = client.get("/api/search/semantic?q=%20%20%20")
    assert res_spaces.status_code == 400
    assert "cannot be empty or whitespace-only" in res_spaces.json()["detail"]


def test_semantic_search_missing_q_returns_422(client):
    """Verify missing required 'q' parameter returns HTTP 422 Unprocessable Entity."""
    res = client.get("/api/search/semantic")
    assert res.status_code == 422


def test_semantic_search_invalid_limit_returns_422(client):
    """Verify limit values <1, >50, or non-integer return HTTP 422 Unprocessable Entity."""
    assert client.get("/api/search/semantic?q=test&limit=0").status_code == 422
    assert client.get("/api/search/semantic?q=test&limit=51").status_code == 422
    assert client.get("/api/search/semantic?q=test&limit=-5").status_code == 422
    assert client.get("/api/search/semantic?q=test&limit=invalid").status_code == 422


# ==============================================================================
# Failure & Exception Handling Tests
# ==============================================================================

def test_semantic_search_embedding_failure_returns_503(client, fake_embedding):
    """Verify embedding service failure returns sanitized HTTP 503."""
    fake_embedding.fail_inference = True
    res = client.get("/api/search/semantic?q=faulty+inference")
    assert res.status_code == 503
    assert "Embedding generation failed for search query" in res.json()["detail"]


def test_semantic_search_vector_index_unavailable_returns_503(client, search_collection):
    """Verify recognizable missing or unready Atlas vector index returns helpful 503."""
    search_collection.error_to_raise = OperationFailure(
        "PlanExecutor error during aggregation :: caused by :: Remote search index 'idx_notes_vector' not found"
    )
    res = client.get("/api/search/semantic?q=test")
    assert res.status_code == 503
    assert res.json()["detail"] == "Vector search index is not ready or unavailable"


def test_semantic_search_unrelated_database_error_returns_general_503(client, search_collection):
    """Verify unrelated database operation failures do not masquerade as index errors."""
    search_collection.error_to_raise = OperationFailure(
        "Authentication failed: unauthorized access to namespace"
    )
    res = client.get("/api/search/semantic?q=test")
    assert res.status_code == 503
    assert res.json()["detail"] == "Database operation failed during semantic search"


def test_semantic_search_pymongo_error_returns_general_503(client, search_collection):
    """Verify generic PyMongo errors return sanitized 503."""
    search_collection.error_to_raise = PyMongoError("Socket error during query")
    res = client.get("/api/search/semantic?q=test")
    assert res.status_code == 503
    assert res.json()["detail"] == "Database operation failed during semantic search"


# ==============================================================================
# Route Registration & Existing Endpoint Preservation Tests
# ==============================================================================

def test_router_registered_and_existing_endpoints_preserved(client):
    """Verify /api/search/semantic is registered and /health, /api/notes remain accessible."""
    health_res = client.get("/health")
    assert health_res.status_code in (200, 503)

    notes_res = client.get("/api/notes")
    assert notes_res.status_code == 200
    assert isinstance(notes_res.json(), list)

    search_res = client.get("/api/search/semantic?q=registered")
    assert search_res.status_code == 200
