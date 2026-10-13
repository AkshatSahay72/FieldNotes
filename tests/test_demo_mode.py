"""Tests for Public Demo Mode Safety and Dependency Hardening (Phase 2D.1).

Verifies:
1. Server-side demo-mode write rejection (403 Forbidden) on all note and attachment write endpoints.
2. Unrestricted availability of read, search, analytics, attachment listing, and image downloads.
3. Normal development mode preserves full write capability and does not display demo notice.
4. Demo database selection safety guard preventing accidental writes to development database.
5. Idempotent and safe synthetic demo seeding process without record duplication.
"""

from copy import deepcopy
from datetime import datetime, timezone
import io
from bson import ObjectId
import pytest
from fastapi.testclient import TestClient

from pymongo.errors import PyMongoError

from app.main import app
from app.db import get_database, get_gridfs
from app.config import Settings, get_settings
from app.services.embedding import get_embedding_service
from scripts.seed_demo_data import seed_demo_data, main as seed_main, DEFAULT_DEV_DATABASE_NAME

# Sample valid 1x1 PNG bytes
SAMPLE_PNG = (
    b"\x89PNG\r\n\x1a\n\x00\x00\x00\rIHDR\x00\x00\x00\x01\x00\x00\x00\x01\x08\x02\x00\x00\x00\x90wS\xde"
    b"\x00\x00\x00\x0cIDATx\x9cc\xf8\xcf\xc0\x00\x00\x03\x01\x01\x00\xc9\xfe\x92\xef\x00\x00\x00\x00IEND\xaeB`\x82"
)


class FakeCursor:
    def __init__(self, docs):
        self._docs = [deepcopy(d) for d in docs]

    def sort(self, key_or_list, direction=-1):
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
                if "note_id" in filter_dict and doc.get("note_id") != filter_dict["note_id"]:
                    match = False
                if "filename" in filter_dict and doc.get("filename") != filter_dict["filename"]:
                    match = False
                if match:
                    filtered.append(doc)
            return FakeCursor(filtered)
        return FakeCursor(docs)

    def find_one(self, filter_dict):
        for doc in self.docs.values():
            match = True
            for k, v in filter_dict.items():
                if doc.get(k) != v:
                    match = False
                    break
            if match:
                return deepcopy(doc)
        return None

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

    def delete_many(self, filter_dict):
        to_del = [oid for oid, d in self.docs.items() if d.get("note_id") == filter_dict.get("note_id")]
        for oid in to_del:
            del self.docs[oid]

        class DeleteManyResult:
            deleted_count = len(to_del)

        return DeleteManyResult()

    def count_documents(self, filter_dict):
        return len(list(self.find(filter_dict)))

    def aggregate(self, pipeline):
        return []

    def create_index(self, keys, name=None):
        return name or "idx"


class FakeGridOut:
    def __init__(self, data: bytes, filename: str, content_type: str):
        self._buffer = io.BytesIO(data)
        self.filename = filename
        self.content_type = content_type

    def read(self, size=-1):
        return self._buffer.read(size)

    def close(self):
        self._buffer.close()


class FakeGridFS:
    def __init__(self):
        self.files = {}

    def put(self, data: bytes, filename: str = None, content_type: str = None):
        file_id = ObjectId()
        self.files[file_id] = {
            "data": bytes(data),
            "filename": filename,
            "content_type": content_type,
        }
        return file_id

    def get(self, file_id: ObjectId):
        if file_id not in self.files:
            raise Exception("File not found in GridFS")
        info = self.files[file_id]
        return FakeGridOut(info["data"], info["filename"], info["content_type"])

    def delete(self, file_id: ObjectId):
        self.files.pop(file_id, None)


class FakeDatabase:
    def __init__(self, name: str = "fieldnote_demo"):
        self.name = name
        self._collections = {
            "notes": FakeCollection(),
            "attachments": FakeCollection(),
        }

    def __getitem__(self, name):
        if name not in self._collections:
            self._collections[name] = FakeCollection()
        return self._collections[name]


class FakeEmbeddingService:
    model_name = "sentence-transformers/all-MiniLM-L6-v2"

    def prepare_text(self, title: str, content: str) -> str:
        return f"{title}\n\n{content}"

    def generate_embedding(self, text: str):
        return [0.05] * 384


@pytest.fixture
def fake_db():
    return FakeDatabase()


@pytest.fixture
def fake_fs():
    return FakeGridFS()


@pytest.fixture
def fake_embedding():
    return FakeEmbeddingService()


@pytest.fixture
def demo_settings():
    return Settings(
        demo_mode=True,
        database_name="fieldnote_demo",
    )


@pytest.fixture
def dev_settings():
    return Settings(
        demo_mode=False,
        database_name="fieldnote_db",
    )


@pytest.fixture
def demo_client(fake_db, fake_fs, fake_embedding, demo_settings):
    app.dependency_overrides[get_database] = lambda: fake_db
    app.dependency_overrides[get_gridfs] = lambda: fake_fs
    app.dependency_overrides[get_embedding_service] = lambda: fake_embedding
    app.dependency_overrides[get_settings] = lambda: demo_settings
    yield TestClient(app)
    app.dependency_overrides.clear()


@pytest.fixture
def dev_client(fake_db, fake_fs, fake_embedding, dev_settings):
    app.dependency_overrides[get_database] = lambda: fake_db
    app.dependency_overrides[get_gridfs] = lambda: fake_fs
    app.dependency_overrides[get_embedding_service] = lambda: fake_embedding
    app.dependency_overrides[get_settings] = lambda: dev_settings
    yield TestClient(app)
    app.dependency_overrides.clear()


# ===========================================================================
# 1. Demo Mode Server-Side Protection Tests (Reject all writes)
# ===========================================================================

def test_demo_mode_rejects_create_note(demo_client):
    payload = {
        "title": "Public Write Attempt",
        "content": "This should be blocked server-side.",
        "tags": ["test"],
    }
    response = demo_client.post("/api/notes", json=payload)
    assert response.status_code == 403
    assert response.json() == {"detail": "Operation not permitted in demo mode."}


def test_demo_mode_rejects_update_note(demo_client, fake_db):
    note_id = ObjectId()
    fake_db["notes"].insert_one({
        "_id": note_id,
        "title": "Existing Note",
        "content": "Existing content",
        "tags": [],
        "created_at": datetime.now(timezone.utc),
        "updated_at": datetime.now(timezone.utc),
    })

    payload = {"title": "Updated Title"}
    response = demo_client.put(f"/api/notes/{note_id}", json=payload)
    assert response.status_code == 403
    assert response.json() == {"detail": "Operation not permitted in demo mode."}


def test_demo_mode_rejects_delete_note(demo_client, fake_db):
    note_id = ObjectId()
    fake_db["notes"].insert_one({
        "_id": note_id,
        "title": "Existing Note",
        "content": "Existing content",
        "tags": [],
        "created_at": datetime.now(timezone.utc),
        "updated_at": datetime.now(timezone.utc),
    })

    response = demo_client.delete(f"/api/notes/{note_id}")
    assert response.status_code == 403
    assert response.json() == {"detail": "Operation not permitted in demo mode."}


def test_demo_mode_rejects_upload_attachment(demo_client, fake_db):
    note_id = ObjectId()
    fake_db["notes"].insert_one({
        "_id": note_id,
        "title": "Existing Note",
        "content": "Existing content",
        "tags": [],
        "created_at": datetime.now(timezone.utc),
        "updated_at": datetime.now(timezone.utc),
    })

    files = {"file": ("test.png", SAMPLE_PNG, "image/png")}
    response = demo_client.post(f"/api/notes/{note_id}/attachments", files=files)
    assert response.status_code == 403
    assert response.json() == {"detail": "Operation not permitted in demo mode."}


def test_demo_mode_rejects_delete_attachment(demo_client, fake_db):
    note_id = ObjectId()
    att_id = ObjectId()
    fake_db["notes"].insert_one({
        "_id": note_id,
        "title": "Existing Note",
        "content": "Existing content",
        "tags": [],
        "created_at": datetime.now(timezone.utc),
        "updated_at": datetime.now(timezone.utc),
    })
    fake_db["attachments"].insert_one({
        "_id": att_id,
        "note_id": note_id,
        "filename": "sample.png",
        "content_type": "image/png",
        "file_size": len(SAMPLE_PNG),
        "created_at": datetime.now(timezone.utc),
    })

    response = demo_client.delete(f"/api/notes/{note_id}/attachments/{att_id}")
    assert response.status_code == 403
    assert response.json() == {"detail": "Operation not permitted in demo mode."}


# ===========================================================================
# 2. Demo Mode Read Availability Tests
# ===========================================================================

def test_demo_mode_allows_reads_and_displays_banner(demo_client, fake_db, fake_fs):
    note_id = ObjectId()
    fake_db["notes"].insert_one({
        "_id": note_id,
        "title": "Bioluminescent Specimen",
        "content": "Observation notes",
        "tags": ["specimen"],
        "created_at": datetime.now(timezone.utc),
        "updated_at": datetime.now(timezone.utc),
    })

    file_id = fake_fs.put(SAMPLE_PNG, filename="photo.png", content_type="image/png")
    att_id = ObjectId()
    fake_db["attachments"].insert_one({
        "_id": att_id,
        "note_id": note_id,
        "file_id": file_id,
        "filename": "photo.png",
        "content_type": "image/png",
        "file_size": len(SAMPLE_PNG),
        "created_at": datetime.now(timezone.utc),
    })

    # Home page renders and includes demo banner
    resp_home = demo_client.get("/")
    assert resp_home.status_code == 200
    assert "demo-banner" in resp_home.text
    assert "Demo Mode" in resp_home.text

    # Analytics page renders and includes demo banner
    resp_analytics = demo_client.get("/analytics")
    assert resp_analytics.status_code == 200
    assert "demo-banner" in resp_analytics.text

    # Note listing
    resp_notes = demo_client.get("/api/notes")
    assert resp_notes.status_code == 200
    assert len(resp_notes.json()) == 1

    # Single note retrieval
    resp_single = demo_client.get(f"/api/notes/{note_id}")
    assert resp_single.status_code == 200
    assert resp_single.json()["title"] == "Bioluminescent Specimen"

    # Attachment listing
    resp_att_list = demo_client.get(f"/api/notes/{note_id}/attachments")
    assert resp_att_list.status_code == 200
    assert len(resp_att_list.json()) == 1

    # Attachment download
    resp_download = demo_client.get(f"/api/notes/{note_id}/attachments/{att_id}/download")
    assert resp_download.status_code == 200
    assert resp_download.content == SAMPLE_PNG

    # Analytics endpoints
    assert demo_client.get("/api/analytics/overview").status_code == 200
    assert demo_client.get("/api/analytics/tags").status_code == 200
    assert demo_client.get("/api/analytics/activity").status_code == 200
    assert demo_client.get("/api/analytics/attachments").status_code == 200


# ===========================================================================
# 3. Development Mode Functionality Tests (Normal behavior preserved)
# ===========================================================================

def test_development_mode_preserves_writes_and_omits_banner(dev_client, fake_db):
    # UI does not show demo banner
    resp_home = dev_client.get("/")
    assert resp_home.status_code == 200
    assert "demo-banner" not in resp_home.text

    # Note creation succeeds
    resp_create = dev_client.post(
        "/api/notes",
        json={"title": "Dev Note", "content": "Dev content", "tags": ["dev"]},
    )
    assert resp_create.status_code == 201
    created_id = resp_create.json()["id"]

    # Note update succeeds
    resp_update = dev_client.put(
        f"/api/notes/{created_id}",
        json={"title": "Updated Dev Note", "content": "Updated dev content", "tags": ["dev", "v2"]},
    )
    assert resp_update.status_code == 200
    assert resp_update.json()["title"] == "Updated Dev Note"

    # Attachment upload succeeds
    files = {"file": ("test.png", SAMPLE_PNG, "image/png")}
    resp_upload = dev_client.post(f"/api/notes/{created_id}/attachments", files=files)
    assert resp_upload.status_code == 201
    att_id = resp_upload.json()["id"]

    # Attachment deletion succeeds
    resp_del_att = dev_client.delete(f"/api/notes/{created_id}/attachments/{att_id}")
    assert resp_del_att.status_code == 204

    # Note deletion succeeds
    resp_del = dev_client.delete(f"/api/notes/{created_id}")
    assert resp_del.status_code == 204


# ===========================================================================
# 4. Synthetic Demo Seeding Idempotency Tests
# ===========================================================================

def test_seed_demo_data_idempotency(fake_db, fake_fs, fake_embedding):
    # Run 1: initial population
    counts_run1 = seed_demo_data(
        db=fake_db,
        fs=fake_fs,
        embedding_service=fake_embedding,
        dry_run=False,
    )
    assert counts_run1["notes_created"] == 10
    assert counts_run1["notes_skipped"] == 0
    assert counts_run1["attachments_created"] == 4
    assert counts_run1["attachments_skipped"] == 0

    assert len(fake_db["notes"].docs) == 10
    assert len(fake_db["attachments"].docs) == 4

    # Verify all seeded records are marked as public demo
    for doc in fake_db["notes"].docs.values():
        assert doc.get("is_demo") is True
        assert doc.get("user_id") is None
        assert doc.get("type") in ("journal", "memory", "research", "idea", "learning")

    for att in fake_db["attachments"].docs.values():
        assert att.get("is_demo") is True
        assert att.get("user_id") is None

    # Run 2: second execution must skip everything and create zero duplicates
    counts_run2 = seed_demo_data(
        db=fake_db,
        fs=fake_fs,
        embedding_service=fake_embedding,
        dry_run=False,
    )
    assert counts_run2["notes_created"] == 0
    assert counts_run2["notes_skipped"] == 10
    assert counts_run2["attachments_created"] == 0
    assert counts_run2["attachments_skipped"] == 4

    # Total documents unchanged
    assert len(fake_db["notes"].docs) == 10
    assert len(fake_db["attachments"].docs) == 4


def test_seed_demo_data_dry_run(fake_db, fake_fs):
    counts = seed_demo_data(
        db=fake_db,
        fs=fake_fs,
        dry_run=True,
    )
    assert counts["notes_created"] == 10
    assert counts["attachments_created"] == 4
    # Dry-run must make zero actual writes
    assert len(fake_db["notes"].docs) == 0
    assert len(fake_db["attachments"].docs) == 0


def test_seed_demo_data_safety_abort_on_default_db(monkeypatch):
    # Simulate CLI invocation targeting default 'fieldnote_db' without --allow-default-db
    test_args = ["seed_demo_data.py", "--database-name", DEFAULT_DEV_DATABASE_NAME]
    monkeypatch.setattr("sys.argv", test_args)

    exit_code = seed_main()
    assert exit_code == 1, "Seed script must abort when targeting default dev database without explicit flag"


def test_seed_demo_data_refuses_personal_databases(monkeypatch):
    """Seed script must unconditionally refuse to seed a personal user's database."""
    for personal_db in ["fieldnote_private", "fieldnote_personal", "fieldnote_private_prod"]:
        test_args = ["seed_demo_data.py", "--database-name", personal_db]
        monkeypatch.setattr("sys.argv", test_args)
        exit_code = seed_main()
        assert exit_code == 1, f"Seed script must refuse personal database '{personal_db}'"


def test_seed_demo_data_refuses_omitted_target_database(monkeypatch):
    """Seed script must refuse to run if target database is omitted without fallback."""
    monkeypatch.delenv("DATABASE_NAME", raising=False)
    test_args = ["seed_demo_data.py"]
    monkeypatch.setattr("sys.argv", test_args)
    exit_code = seed_main()
    assert exit_code == 1, "Seed script must refuse execution when target database is omitted"


# ===========================================================================
# 5. Configuration Parsing Tests
# ===========================================================================

def test_seed_demo_data_cleanup_on_attachment_metadata_failure(fake_db, fake_fs):
    """Verify newly uploaded GridFS files are deleted if attachment metadata insert fails."""
    # Put a pre-existing file to ensure pre-existing files are NOT touched
    pre_existing_id = fake_fs.put(b"pre-existing", filename="existing.png", content_type="image/png")

    class FailingAttachmentsCollection(FakeCollection):
        def insert_one(self, doc):
            raise PyMongoError("Simulated database metadata insert failure")

    # Override attachments collection with the failing collection
    fake_db._collections["attachments"] = FailingAttachmentsCollection()

    with pytest.raises(PyMongoError, match="Simulated database metadata insert failure"):
        seed_demo_data(
            db=fake_db,
            fs=fake_fs,
            dry_run=False,
        )

    # The newly uploaded file must have been deleted, while the pre-existing file remains
    assert pre_existing_id in fake_fs.files
    assert len(fake_fs.files) == 1


def test_seed_demo_data_refuses_production_environment(monkeypatch):
    """Verify seed script unconditionally refuses to run when APP_ENV=production."""
    test_args = ["seed_demo_data.py", "--database-name", "fieldnote_demo"]
    monkeypatch.setattr("sys.argv", test_args)
    monkeypatch.setenv("APP_ENV", "production")

    exit_code = seed_main()
    assert exit_code == 1, "Seed script must unconditionally abort when APP_ENV=production"


# ===========================================================================
# 5. Configuration Parsing & Fail-Closed Database Validation Tests
# ===========================================================================

def test_demo_mode_configuration_settings(monkeypatch):
    monkeypatch.delenv("DATABASE_NAME", raising=False)
    s_false = Settings(_env_file=None, demo_mode=False)
    assert s_false.demo_mode is False
    assert s_false.database_name == "fieldnote_db"

    s_true = Settings(_env_file=None, demo_mode=True, database_name="fieldnote_demo")
    assert s_true.demo_mode is True
    assert s_true.database_name == "fieldnote_demo"

    s_alias = Settings(_env_file=None, DEMO_MODE=True, DATABASE_NAME="fieldnote_demo")
    assert s_alias.demo_mode is True
    assert s_alias.database_name == "fieldnote_demo"


def test_demo_mode_database_fail_closed_when_omitted(monkeypatch):
    """In demo mode, an omitted DATABASE_NAME must raise a validation error."""
    # Ensure DATABASE_NAME is absent from environment
    monkeypatch.delenv("DATABASE_NAME", raising=False)

    with pytest.raises(ValueError, match="When DEMO_MODE is enabled, a dedicated demo database must be explicitly configured"):
        Settings(_env_file=None, demo_mode=True)


def test_demo_mode_database_fail_closed_when_targeting_fieldnote_db():
    """In demo mode, setting DATABASE_NAME=fieldnote_db must raise a validation error."""
    with pytest.raises(ValueError, match="cannot target the default development database"):
        Settings(_env_file=None, demo_mode=True, database_name="fieldnote_db")


def test_dev_mode_preserves_default_database(monkeypatch):
    """In development mode (DEMO_MODE=false), default 'fieldnote_db' is accepted cleanly."""
    monkeypatch.delenv("DATABASE_NAME", raising=False)
    s = Settings(_env_file=None, demo_mode=False)
    assert s.database_name == "fieldnote_db"
