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
    """In-memory cursor simulating PyMongo find cursor with sort, skip, and limit."""

    def __init__(self, docs):
        self._docs = [deepcopy(d) for d in docs]

    def sort(self, key_or_list, direction=-1):
        if isinstance(key_or_list, list):
            # Apply sorts in reverse order to achieve stable multi-key sort
            for key, dir_val in reversed(key_or_list):
                reverse = dir_val == -1
                self._docs.sort(key=lambda d: d.get(key), reverse=reverse)
        else:
            reverse = direction == -1
            self._docs.sort(key=lambda d: d.get(key_or_list), reverse=reverse)
        return self

    def skip(self, count):
        self._docs = self._docs[count:]
        return self

    def limit(self, count):
        self._docs = self._docs[:count]
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
        docs = list(self.docs.values())
        if filter_dict:
            filtered = []
            for doc in docs:
                match = True
                # Handle tags filter: {"tags": {"$in": tag_list}}
                if "tags" in filter_dict:
                    in_tags = filter_dict["tags"].get("$in", [])
                    doc_tags = doc.get("tags", [])
                    if not any(t in doc_tags for t in in_tags):
                        match = False
                # Handle $text search: {"$text": {"$search": search_term}}
                if "$text" in filter_dict:
                    search_term = filter_dict["$text"].get("$search", "").lower()
                    title = doc.get("title", "").lower()
                    content = doc.get("content", "").lower()
                    if search_term not in title and search_term not in content:
                        match = False
                if match:
                    filtered.append(doc)
            return FakeCursor(filtered)
        return FakeCursor(docs)

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
# Milestone 4: Tag Filtering, Text Search & Pagination
# ==============================================================================

def test_list_notes_filter_single_tag(client, fake_db):
    """Verify filtering by a single tag returns only matching notes."""
    fake_db["notes"].insert_one({"title": "Note A", "content": "c1", "tags": ["soil", "moisture"], "created_at": datetime.now(timezone.utc), "updated_at": datetime.now(timezone.utc)})
    fake_db["notes"].insert_one({"title": "Note B", "content": "c2", "tags": ["canopy"], "created_at": datetime.now(timezone.utc), "updated_at": datetime.now(timezone.utc)})

    res = client.get("/api/notes?tag=soil")
    assert res.status_code == 200
    data = res.json()
    assert len(data) == 1
    assert data[0]["title"] == "Note A"


def test_list_notes_filter_multiple_tags_or_semantics(client, fake_db):
    """Verify multiple tags use OR semantics (match notes with any tag)."""
    fake_db["notes"].insert_one({"title": "Note Soil", "content": "c1", "tags": ["soil"], "created_at": datetime.now(timezone.utc), "updated_at": datetime.now(timezone.utc)})
    fake_db["notes"].insert_one({"title": "Note Water", "content": "c2", "tags": ["water"], "created_at": datetime.now(timezone.utc), "updated_at": datetime.now(timezone.utc)})
    fake_db["notes"].insert_one({"title": "Note Flora", "content": "c3", "tags": ["flora"], "created_at": datetime.now(timezone.utc), "updated_at": datetime.now(timezone.utc)})

    res = client.get("/api/notes?tag=soil&tag=water")
    assert res.status_code == 200
    data = res.json()
    titles = [n["title"] for n in data]
    assert len(data) == 2
    assert "Note Soil" in titles
    assert "Note Water" in titles
    assert "Note Flora" not in titles


def test_list_notes_filter_comma_separated_and_alias(client, fake_db):
    """Verify comma-separated tags and ?tags= alias work identically."""
    fake_db["notes"].insert_one({"title": "Note 1", "content": "c1", "tags": ["sensor"], "created_at": datetime.now(timezone.utc), "updated_at": datetime.now(timezone.utc)})
    fake_db["notes"].insert_one({"title": "Note 2", "content": "c2", "tags": ["drone"], "created_at": datetime.now(timezone.utc), "updated_at": datetime.now(timezone.utc)})

    # Comma-separated ?tag=sensor,drone
    res = client.get("/api/notes?tag=sensor,drone")
    assert res.status_code == 200
    assert len(res.json()) == 2

    # Using ?tags= alias
    res_alias = client.get("/api/notes?tags=drone")
    assert res_alias.status_code == 200
    assert len(res_alias.json()) == 1
    assert res_alias.json()[0]["title"] == "Note 2"

    # Both ?tag= and ?tags= supplied together
    res_both = client.get("/api/notes?tag=sensor&tags=drone")
    assert res_both.status_code == 200
    assert len(res_both.json()) == 2


def test_list_notes_empty_or_whitespace_tag_rejected(client):
    """Verify empty or whitespace-only tag query parameters are rejected with 400 Bad Request."""
    for malformed_url in [
        "/api/notes?tag=",
        "/api/notes?tag=   ",
        "/api/notes?tags=",
        "/api/notes?tags=   ",
        "/api/notes?tag=soil,",
        "/api/notes?tags=soil,,water",
        "/api/notes?tag=soil&tags=   ",
        "/api/notes?tag=   &tags=water",
    ]:
        res = client.get(malformed_url)
        assert res.status_code == 400, f"Expected 400 for {malformed_url}, got {res.status_code}"
        assert "Tag filter value cannot be empty" in res.json()["detail"]


def test_list_notes_text_search_matching_title(client, fake_db):
    """Verify text search matches words in title."""
    fake_db["notes"].insert_one({"title": "Geological Survey Plot 3", "content": "Basalt samples gathered.", "tags": [], "created_at": datetime.now(timezone.utc), "updated_at": datetime.now(timezone.utc)})
    fake_db["notes"].insert_one({"title": "Hydrological Monitor", "content": "River stream metrics.", "tags": [], "created_at": datetime.now(timezone.utc), "updated_at": datetime.now(timezone.utc)})

    res = client.get("/api/notes?q=Geological")
    assert res.status_code == 200
    data = res.json()
    assert len(data) == 1
    assert data[0]["title"] == "Geological Survey Plot 3"


def test_list_notes_text_search_matching_content(client, fake_db):
    """Verify text search matches keywords in body content."""
    fake_db["notes"].insert_one({"title": "Plot Analysis", "content": "Volumetric nitrogen concentration high.", "tags": [], "created_at": datetime.now(timezone.utc), "updated_at": datetime.now(timezone.utc)})
    fake_db["notes"].insert_one({"title": "Weather Log", "content": "Cloudy afternoon.", "tags": [], "created_at": datetime.now(timezone.utc), "updated_at": datetime.now(timezone.utc)})

    res = client.get("/api/notes?q=nitrogen")
    assert res.status_code == 200
    data = res.json()
    assert len(data) == 1
    assert data[0]["title"] == "Plot Analysis"


def test_list_notes_text_search_no_matches(client, fake_db):
    """Verify text search returns empty list when query does not match any note."""
    fake_db["notes"].insert_one({"title": "Forestry", "content": "Pine trees.", "tags": [], "created_at": datetime.now(timezone.utc), "updated_at": datetime.now(timezone.utc)})

    res = client.get("/api/notes?q=desert")
    assert res.status_code == 200
    assert res.json() == []


def test_list_notes_empty_or_whitespace_search_rejected(client):
    """Verify empty or whitespace-only search string 'q' is rejected with 400 Bad Request."""
    res_empty = client.get("/api/notes?q=")
    assert res_empty.status_code == 400
    assert "Search query 'q' cannot be empty" in res_empty.json()["detail"]

    res_ws = client.get("/api/notes?q=    ")
    assert res_ws.status_code == 400
    assert "Search query 'q' cannot be empty" in res_ws.json()["detail"]


def test_list_notes_search_combined_with_tag_filter(client, fake_db):
    """Verify composing tag filter and text search in a single query (implicit AND)."""
    # Note matches tag AND keyword
    fake_db["notes"].insert_one({"title": "Irrigation Sensor Log", "content": "Flow rate 12 L/min.", "tags": ["hydrology"], "created_at": datetime.now(timezone.utc), "updated_at": datetime.now(timezone.utc)})
    # Note matches tag only
    fake_db["notes"].insert_one({"title": "Dam Inspection", "content": "Concrete integrity.", "tags": ["hydrology"], "created_at": datetime.now(timezone.utc), "updated_at": datetime.now(timezone.utc)})
    # Note matches keyword only
    fake_db["notes"].insert_one({"title": "Lab Calibration", "content": "Sensor test bench.", "tags": ["lab"], "created_at": datetime.now(timezone.utc), "updated_at": datetime.now(timezone.utc)})

    res = client.get("/api/notes?tag=hydrology&q=Sensor")
    assert res.status_code == 200
    data = res.json()
    assert len(data) == 1
    assert data[0]["title"] == "Irrigation Sensor Log"


def test_list_notes_default_pagination(client, fake_db):
    """Verify default pagination returns up to 20 notes."""
    base_time = datetime.now(timezone.utc)
    for i in range(25):
        fake_db["notes"].insert_one({
            "title": f"Note #{i:02d}",
            "content": f"Content {i}",
            "tags": [],
            "created_at": base_time + timedelta(minutes=i),
            "updated_at": base_time + timedelta(minutes=i),
        })

    res = client.get("/api/notes")
    assert res.status_code == 200
    data = res.json()
    # Default limit is 20
    assert len(data) == 20
    # Newest note (Note #24) first
    assert data[0]["title"] == "Note #24"


def test_list_notes_custom_skip_and_limit(client, fake_db):
    """Verify custom skip and limit slices the sorted notes correctly."""
    base_time = datetime.now(timezone.utc)
    for i in range(10):
        fake_db["notes"].insert_one({
            "title": f"Item {i}",
            "content": "test",
            "tags": [],
            "created_at": base_time + timedelta(minutes=i),
            "updated_at": base_time + timedelta(minutes=i),
        })

    # Total 10 notes: Item 9 (newest) down to Item 0 (oldest)
    # ?skip=2&limit=3 should return items at index 2, 3, 4 -> Item 7, Item 6, Item 5
    res = client.get("/api/notes?skip=2&limit=3")
    assert res.status_code == 200
    data = res.json()
    assert len(data) == 3
    assert data[0]["title"] == "Item 7"
    assert data[1]["title"] == "Item 6"
    assert data[2]["title"] == "Item 5"


def test_list_notes_pagination_validation_errors(client):
    """Verify invalid or out-of-range pagination values return 422 Unprocessable Entity."""
    # Negative skip
    assert client.get("/api/notes?skip=-1").status_code == 422

    # Zero limit
    assert client.get("/api/notes?limit=0").status_code == 422

    # Negative limit
    assert client.get("/api/notes?limit=-5").status_code == 422

    # Limit exceeding maximum (100)
    assert client.get("/api/notes?limit=101").status_code == 422


def test_list_notes_stable_sort_timestamp_tie_breaker(client, fake_db):
    """Verify stable sorting uses _id as a deterministic tie-breaker when created_at timestamps are identical."""
    same_time = datetime.now(timezone.utc)
    # Insert 3 notes with exact same created_at but increasing ObjectIds
    oid1 = ObjectId("507f1f77bcf86cd799439011")
    oid2 = ObjectId("507f1f77bcf86cd799439012")
    oid3 = ObjectId("507f1f77bcf86cd799439013")

    fake_db["notes"].insert_one({"_id": oid1, "title": "Tie 1", "content": "c", "tags": [], "created_at": same_time, "updated_at": same_time})
    fake_db["notes"].insert_one({"_id": oid2, "title": "Tie 2", "content": "c", "tags": [], "created_at": same_time, "updated_at": same_time})
    fake_db["notes"].insert_one({"_id": oid3, "title": "Tie 3", "content": "c", "tags": [], "created_at": same_time, "updated_at": same_time})

    res = client.get("/api/notes")
    assert res.status_code == 200
    data = res.json()
    assert len(data) == 3
    # With [("created_at", -1), ("_id", -1)], higher _id comes first
    assert data[0]["id"] == str(oid3)
    assert data[1]["id"] == str(oid2)
    assert data[2]["id"] == str(oid1)


def test_build_notes_query_unit():
    """Unit test for query construction helper functions."""
    from app.routes.notes import build_notes_query, parse_and_validate_tags

    # Tag parsing & normalization
    assert parse_and_validate_tags(None, None) is None
    assert parse_and_validate_tags(["soil", "water"]) == ["soil", "water"]
    assert parse_and_validate_tags(["soil,water", "sensor"]) == ["soil", "water", "sensor"]
    assert parse_and_validate_tags([" soil ", "water "]) == ["soil", "water"]

    # Query composition
    assert build_notes_query() == {}
    assert build_notes_query(tag_list=["soil"]) == {"tags": {"$in": ["soil"]}}
    assert build_notes_query(tag_list=["soil", "water"]) == {"tags": {"$in": ["soil", "water"]}}
    assert build_notes_query(q="moisture") == {"$text": {"$search": "moisture"}}
    assert build_notes_query(tag_list=["soil"], q="moisture") == {
        "tags": {"$in": ["soil"]},
        "$text": {"$search": "moisture"},
    }



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
