from copy import deepcopy
from datetime import datetime, timezone, timedelta
from bson import ObjectId
import pytest
from fastapi.testclient import TestClient
from pymongo.errors import PyMongoError

from app.main import app
from app.db import get_database, get_gridfs
from app.config import Settings, get_settings


class FakeCursor:
    """In-memory cursor simulating PyMongo find cursor with sort."""

    def __init__(self, docs):
        self._docs = [deepcopy(d) for d in docs]

    def sort(self, key, direction=-1):
        reverse = direction == -1
        self._docs.sort(key=lambda d: d.get(key), reverse=reverse)
        return self

    def __iter__(self):
        return iter(self._docs)


class FakeCollection:
    """In-memory collection simulating PyMongo collection operations."""

    def __init__(self):
        self.docs = {}

    def insert_one(self, doc):
        oid = doc.get("_id") or ObjectId()
        stored = deepcopy(doc)
        stored["_id"] = oid
        self.docs[oid] = stored

        class InsertResult:
            inserted_id = oid

        return InsertResult()

    def find(self, filter_dict=None):
        return FakeCursor(self.docs.values())

    def find_one(self, filter_dict):
        oid = filter_dict.get("_id")
        doc = self.docs.get(oid)
        return deepcopy(doc) if doc else None

    def find_one_and_update(self, filter_dict, update_dict, return_document=None):
        oid = filter_dict.get("_id")
        doc = self.docs.get(oid)
        if not doc:
            return None
        set_fields = update_dict.get("$set", {})
        doc.update(set_fields)
        return deepcopy(doc)

    def delete_one(self, filter_dict):
        oid = filter_dict.get("_id")
        existed = oid in self.docs
        if existed:
            del self.docs[oid]

        class DeleteResult:
            deleted_count = 1 if existed else 0

        return DeleteResult()

    def create_index(self, keys, name=None):
        return name or "idx"


class FakeGridFS:
    """In-memory test double for GridFS."""

    def delete(self, file_id):
        pass


class FakeDatabase:
    """In-memory test database double simulating PyMongo Database."""

    def __init__(self):
        self._collections = {"notes": FakeCollection(), "attachments": FakeCollection()}

    def __getitem__(self, name):
        if name not in self._collections:
            self._collections[name] = FakeCollection()
        return self._collections[name]


@pytest.fixture
def fake_db():
    """Provides a fresh isolated fake database for each test."""
    return FakeDatabase()


@pytest.fixture
def client(fake_db):
    """Test client with isolated settings and in-memory fake database."""
    test_settings = Settings(
        MONGODB_URI="mongodb://localhost:27017",
        DATABASE_NAME="test_db",
        APP_ENV="testing",
        _env_file=None,
    )
    app.dependency_overrides[get_settings] = lambda: test_settings
    app.dependency_overrides[get_database] = lambda: fake_db
    app.dependency_overrides[get_gridfs] = lambda: FakeGridFS()

    with TestClient(app) as test_client:
        yield test_client

    app.dependency_overrides.clear()


# ==============================================================================
# POST /api/notes (Create Note)
# ==============================================================================

def test_create_note_success(client):
    """Verify creating a note returns 201 Created with valid ObjectId string and timestamps."""
    payload = {
        "title": "Soil Moisture Experiment #1",
        "content": "Observed 34% volumetric water content after irrigation.",
        "tags": ["soil", "irrigation"],
    }
    response = client.post("/api/notes", json=payload)
    assert response.status_code == 201

    data = response.json()
    assert "id" in data
    assert ObjectId.is_valid(data["id"])
    assert data["title"] == payload["title"]
    assert data["content"] == payload["content"]
    assert data["tags"] == payload["tags"]
    assert "created_at" in data
    assert "updated_at" in data


def test_create_note_default_tags(client):
    """Verify creating a note without tags defaults to empty list."""
    payload = {
        "title": "Simple Note",
        "content": "Content without tags provided.",
    }
    response = client.post("/api/notes", json=payload)
    assert response.status_code == 201
    assert response.json()["tags"] == []


def test_create_note_empty_title_validation(client):
    """Verify empty or whitespace-only title raises 422 Unprocessable Entity."""
    response = client.post("/api/notes", json={"title": "   ", "content": "Sample content"})
    assert response.status_code == 422

    response_missing = client.post("/api/notes", json={"content": "No title provided"})
    assert response_missing.status_code == 422


def test_create_note_missing_content(client):
    """Verify missing content raises 422 Unprocessable Entity."""
    response = client.post("/api/notes", json={"title": "Valid Title"})
    assert response.status_code == 422


# ==============================================================================
# GET /api/notes (List Notes)
# ==============================================================================

def test_list_notes_empty(client):
    """Verify listing notes returns empty list when collection is empty."""
    response = client.get("/api/notes")
    assert response.status_code == 200
    assert response.json() == []


def test_list_notes_ordered_newest_first(client, fake_db):
    """Verify listing notes returns documents sorted newest first by created_at."""
    t0 = datetime.now(timezone.utc) - timedelta(hours=2)
    t1 = datetime.now(timezone.utc) - timedelta(hours=1)
    t2 = datetime.now(timezone.utc)

    fake_db["notes"].insert_one({"title": "Oldest", "content": "c1", "tags": [], "created_at": t0, "updated_at": t0})
    fake_db["notes"].insert_one({"title": "Middle", "content": "c2", "tags": [], "created_at": t1, "updated_at": t1})
    fake_db["notes"].insert_one({"title": "Newest", "content": "c3", "tags": [], "created_at": t2, "updated_at": t2})

    response = client.get("/api/notes")
    assert response.status_code == 200
    notes = response.json()
    assert len(notes) == 3
    assert notes[0]["title"] == "Newest"
    assert notes[1]["title"] == "Middle"
    assert notes[2]["title"] == "Oldest"


# ==============================================================================
# GET /api/notes/{note_id} (Retrieve Note)
# ==============================================================================

def test_get_note_by_id_success(client):
    """Verify retrieving an existing note by ID returns 200 OK with correct fields."""
    create_res = client.post(
        "/api/notes",
        json={"title": "Botanical Survey", "content": "Trillium grandiflorum spotted.", "tags": ["flora"]},
    )
    note_id = create_res.json()["id"]

    response = client.get(f"/api/notes/{note_id}")
    assert response.status_code == 200
    data = response.json()
    assert data["id"] == note_id
    assert data["title"] == "Botanical Survey"


def test_get_note_not_found(client):
    """Verify retrieving a non-existent ObjectId returns 404 Not Found."""
    non_existent_id = str(ObjectId())
    response = client.get(f"/api/notes/{non_existent_id}")
    assert response.status_code == 404
    assert "not found" in response.json()["detail"].lower()


def test_get_note_malformed_id(client):
    """Verify retrieving a note with malformed ID string returns 400 Bad Request."""
    response = client.get("/api/notes/invalid-hex-id-123")
    assert response.status_code == 400
    assert "Invalid note ID format" in response.json()["detail"]


# ==============================================================================
# PUT /api/notes/{note_id} (Update Note)
# ==============================================================================

def test_update_note_success(client):
    """Verify updating a note returns 200 OK with updated title, content, and tags."""
    create_res = client.post(
        "/api/notes",
        json={"title": "Draft Title", "content": "Initial findings.", "tags": ["draft"]},
    )
    note_id = create_res.json()["id"]

    update_payload = {
        "title": "Finalized Title",
        "content": "Peer-reviewed findings with verified data points.",
        "tags": ["final", "reviewed"],
    }
    update_res = client.put(f"/api/notes/{note_id}", json=update_payload)
    assert update_res.status_code == 200

    data = update_res.json()
    assert data["id"] == note_id
    assert data["title"] == "Finalized Title"
    assert data["content"] == update_payload["content"]
    assert data["tags"] == ["final", "reviewed"]


def test_update_note_not_found(client):
    """Verify updating a non-existent note returns 404 Not Found."""
    non_existent_id = str(ObjectId())
    response = client.put(
        f"/api/notes/{non_existent_id}",
        json={"title": "Updated", "content": "Updated content"},
    )
    assert response.status_code == 404


def test_update_note_malformed_id(client):
    """Verify updating a note with malformed ID returns 400 Bad Request."""
    response = client.put(
        "/api/notes/not-valid-oid",
        json={"title": "Title", "content": "Content"},
    )
    assert response.status_code == 400


def test_update_note_empty_title_validation(client):
    """Verify updating a note with empty title raises 422 Unprocessable Entity."""
    valid_id = str(ObjectId())
    response = client.put(
        f"/api/notes/{valid_id}",
        json={"title": "", "content": "Valid content"},
    )
    assert response.status_code == 422


# ==============================================================================
# DELETE /api/notes/{note_id} (Delete Note)
# ==============================================================================

def test_delete_note_success(client):
    """Verify deleting a note returns 204 No Content and subsequent retrieval returns 404."""
    create_res = client.post(
        "/api/notes",
        json={"title": "To Delete", "content": "This note will be deleted."},
    )
    note_id = create_res.json()["id"]

    delete_res = client.delete(f"/api/notes/{note_id}")
    assert delete_res.status_code == 204

    # Subsequent retrieval must return 404
    get_res = client.get(f"/api/notes/{note_id}")
    assert get_res.status_code == 404


def test_delete_note_not_found(client):
    """Verify deleting a non-existent note returns 404 Not Found."""
    non_existent_id = str(ObjectId())
    response = client.delete(f"/api/notes/{non_existent_id}")
    assert response.status_code == 404


def test_delete_note_malformed_id(client):
    """Verify deleting a note with malformed ID returns 400 Bad Request."""
    response = client.delete("/api/notes/malformed-id")
    assert response.status_code == 400


# ==============================================================================
# Database Error Handling (503 Service Unavailable)
# ==============================================================================

class ErrorCollection:
    """Mock collection that simulates PyMongo driver errors."""

    def insert_one(self, doc):
        raise PyMongoError("Connection lost during insert")

    def find(self, filter_dict=None):
        raise PyMongoError("Socket error during find")

    def find_one(self, filter_dict):
        raise PyMongoError("Socket error during find_one")

    def find_one_and_update(self, filter_dict, update_dict, return_document=None):
        raise PyMongoError("Network error during update")

    def delete_one(self, filter_dict):
        raise PyMongoError("Network error during delete")


class ErrorDatabase:
    def __getitem__(self, name):
        return ErrorCollection()


def test_database_error_handling_returns_503():
    """Verify database errors return safe 503 without leaking stack traces or credentials."""
    test_settings = Settings(
        MONGODB_URI="mongodb://localhost:27017",
        DATABASE_NAME="test_db",
        APP_ENV="testing",
        _env_file=None,
    )
    app.dependency_overrides[get_settings] = lambda: test_settings
    app.dependency_overrides[get_database] = lambda: ErrorDatabase()
    app.dependency_overrides[get_gridfs] = lambda: FakeGridFS()

    with TestClient(app) as test_client:
        post_res = test_client.post("/api/notes", json={"title": "T", "content": "C"})
        assert post_res.status_code == 503
        assert "Database operation failed" in post_res.json()["detail"]

        list_res = test_client.get("/api/notes")
        assert list_res.status_code == 503

        valid_id = str(ObjectId())
        get_res = test_client.get(f"/api/notes/{valid_id}")
        assert get_res.status_code == 503

        put_res = test_client.put(f"/api/notes/{valid_id}", json={"title": "T", "content": "C"})
        assert put_res.status_code == 503

        del_res = test_client.delete(f"/api/notes/{valid_id}")
        assert del_res.status_code == 503

    app.dependency_overrides.clear()
