"""Tests for Application Operational Modes, Database Separation, and Write Security.

Verifies:
1. Safe, validated configuration parsing and explicit mode definitions ('demo', 'authenticated', 'development', 'testing').
2. Database separation rules: fieldnote_demo is kept isolated from private production databases.
3. Private deployments never default to fieldnote_db or silently select a database.
4. Database configuration failures fail closed at startup.
5. In authenticated private mode:
   - Anonymous access cannot perform writes (401 Unauthorized).
   - Anonymous access cannot view private notes (404 Not Found / empty listing).
   - Authenticated users can perform writes with CSRF defenses and per-user authorization.
   - Missing/invalid CSRF tokens on state-changing browser requests are rejected (403 Forbidden).
6. In demo mode:
   - All mutations are rejected (403 Forbidden), even when requests are sent directly to the API
     with authenticated credentials.
"""

from copy import deepcopy
from datetime import datetime, timezone
import io
from typing import Dict, Optional
from bson import ObjectId
import pytest
from fastapi import status
from fastapi.testclient import TestClient

from app.main import app, create_app
from app.db import get_database, get_gridfs
from app.config import Settings, AppMode, get_settings
from app.services.embedding import get_embedding_service
from app.services.auth import auth_rate_limiter

# Sample 1x1 valid PNG bytes
SAMPLE_PNG = (
    b"\x89PNG\r\n\x1a\n\x00\x00\x00\rIHDR\x00\x00\x00\x01\x00\x00\x00\x01\x08\x02\x00\x00\x00\x90wS\xde"
    b"\x00\x00\x00\x0cIDATx\x9cc\xf8\xcf\xc0\x00\x00\x03\x01\x01\x00\xc9\xfe\x92\xef\x00\x00\x00\x00IEND\xaeB`\x82"
)


class FakeCursor:
    def __init__(self, docs):
        self._docs = [deepcopy(d) for d in docs]

    def sort(self, *args, **kwargs):
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
    def __init__(self, name="collection", db=None):
        self.name = name
        self.db = db
        self.docs: Dict[ObjectId, dict] = {}

    def insert_one(self, doc: dict):
        oid = doc.get("_id") or ObjectId()
        stored = deepcopy(doc)
        stored["_id"] = oid
        self.docs[oid] = stored

        class InsertResult:
            inserted_id = oid

        return InsertResult()

    def _matches_filter(self, doc: dict, filter_dict: dict) -> bool:
        if not filter_dict:
            return True
        for k, v in filter_dict.items():
            if k == "_id":
                if doc.get("_id") != v:
                    return False
            elif k == "user_id":
                if doc.get("user_id") != v:
                    return False
            elif k == "note_id":
                if doc.get("note_id") != v:
                    return False
            elif k == "email":
                if doc.get("email") != v:
                    return False
            elif k == "session_id":
                if doc.get("session_id") != v:
                    return False
            elif isinstance(v, dict) and "$gt" in v:
                val = doc.get(k)
                if not val or val <= v["$gt"]:
                    return False
            elif isinstance(v, dict) and "$in" in v:
                doc_list = doc.get(k, [])
                if not any(item in doc_list for item in v["$in"]):
                    return False
            elif doc.get(k) != v:
                return False
        return True

    def find_one(self, filter_dict: dict) -> Optional[dict]:
        for doc in self.docs.values():
            if self._matches_filter(doc, filter_dict):
                return deepcopy(doc)
        return None

    def find(self, filter_dict: Optional[dict] = None) -> FakeCursor:
        matched = [deepcopy(d) for d in self.docs.values() if self._matches_filter(d, filter_dict or {})]
        return FakeCursor(matched)

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
        to_del = [oid for oid, d in self.docs.items() if self._matches_filter(d, filter_dict)]
        for oid in to_del:
            del self.docs[oid]

        class DeleteManyResult:
            deleted_count = len(to_del)

        return DeleteManyResult()

    def count_documents(self, filter_dict):
        return len(list(self.find(filter_dict)))

    def create_index(self, keys, name=None, **kwargs):
        return name or "idx"


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

    def delete(self, file_id: ObjectId):
        self.files.pop(file_id, None)


class FakeDatabase:
    def __init__(self, name="test_db"):
        self.name = name
        self.collections: Dict[str, FakeCollection] = {}

    def __getitem__(self, name: str) -> FakeCollection:
        if name not in self.collections:
            self.collections[name] = FakeCollection(name=name, db=self)
        return self.collections[name]


class FakeEmbeddingService:
    model_name = "sentence-transformers/all-MiniLM-L6-v2"

    def prepare_text(self, title: str, content: str) -> str:
        return f"{title}\n\n{content}"

    def generate_embedding(self, text: str):
        return [0.05] * 384


# ==============================================================================
# 1. Configuration Parsing, Mode Definitions, & Database Separation Tests
# ==============================================================================

def test_authenticated_mode_missing_database_name_fails_closed(monkeypatch):
    """In authenticated private mode, omitting DATABASE_NAME must fail closed."""
    monkeypatch.delenv("DATABASE_NAME", raising=False)
    with pytest.raises(ValueError, match="In authenticated private mode .* DATABASE_NAME must be explicitly configured"):
        Settings(_env_file=None, app_mode="authenticated")


def test_production_environment_missing_database_name_fails_closed(monkeypatch):
    """In production environment, omitting DATABASE_NAME must fail closed."""
    monkeypatch.delenv("DATABASE_NAME", raising=False)
    with pytest.raises(ValueError, match="In authenticated private mode .* DATABASE_NAME must be explicitly configured"):
        Settings(_env_file=None, app_env="production")


def test_demo_mode_missing_database_name_fails_closed(monkeypatch):
    """In demo mode, omitting DATABASE_NAME must fail closed."""
    monkeypatch.delenv("DATABASE_NAME", raising=False)
    with pytest.raises(ValueError, match="When DEMO_MODE is enabled, a dedicated demo database must be explicitly configured"):
        Settings(_env_file=None, app_mode="demo")


def test_invalid_app_mode_string_rejected():
    """An unknown APP_MODE string must raise a ValueError."""
    with pytest.raises(ValueError, match="Invalid APP_MODE 'super_mode'"):
        Settings(_env_file=None, app_mode="super_mode", database_name="fieldnote_custom")


def test_conflicting_authenticated_mode_and_demo_mode_rejected():
    """Conflicting APP_MODE=authenticated and DEMO_MODE=true must be rejected."""
    with pytest.raises(ValueError, match="Conflicting configuration: APP_MODE is 'authenticated' but DEMO_MODE is True"):
        Settings(_env_file=None, app_mode="authenticated", demo_mode=True, database_name="fieldnote_private")


def test_authenticated_mode_targeting_fieldnote_demo_rejected():
    """Authenticated private mode targeting 'fieldnote_demo' must be rejected to prevent cross-data contamination."""
    with pytest.raises(ValueError, match="DATABASE_NAME cannot target the public demo database"):
        Settings(_env_file=None, app_mode="authenticated", database_name="fieldnote_demo")


def test_authenticated_mode_targeting_fieldnote_db_rejected():
    """Authenticated private mode targeting 'fieldnote_db' must be rejected to prevent accidental dev reuse."""
    with pytest.raises(ValueError, match="DATABASE_NAME cannot target the default development database"):
        Settings(_env_file=None, app_mode="authenticated", database_name="fieldnote_db")


def test_demo_mode_targeting_fieldnote_db_rejected():
    """Demo mode targeting 'fieldnote_db' must be rejected."""
    with pytest.raises(ValueError, match="DATABASE_NAME cannot target the default development database"):
        Settings(_env_file=None, app_mode="demo", database_name="fieldnote_db")


def test_dev_mode_targeting_fieldnote_demo_without_demo_flag_rejected():
    """Development mode cannot target 'fieldnote_demo' without demo mode enabled."""
    with pytest.raises(ValueError, match="DATABASE_NAME cannot target 'fieldnote_demo' outside of demo mode"):
        Settings(_env_file=None, app_mode="development", database_name="fieldnote_demo")


def test_dev_mode_accepts_default_fieldnote_db(monkeypatch):
    """In development mode, omitting DATABASE_NAME cleanly defaults to 'fieldnote_db'."""
    monkeypatch.delenv("DATABASE_NAME", raising=False)
    s = Settings(_env_file=None, app_mode="development")
    assert s.database_name == "fieldnote_db"
    assert s.resolved_app_mode == AppMode.DEVELOPMENT
    assert s.is_demo_mode is False


def test_authenticated_mode_aliases():
    """Aliases 'personal' and 'private' map cleanly to AppMode.AUTHENTICATED."""
    s_personal = Settings(_env_file=None, app_mode="personal", database_name="fieldnote_personal")
    assert s_personal.resolved_app_mode == AppMode.AUTHENTICATED
    assert s_personal.requires_authentication_for_writes is True

    s_private = Settings(_env_file=None, app_mode="private", database_name="fieldnote_private")
    assert s_private.resolved_app_mode == AppMode.AUTHENTICATED
    assert s_private.requires_authentication_for_writes is True


# ==============================================================================
# 2. Anonymous Access Restrictions in Authenticated Private Mode
# ==============================================================================

@pytest.fixture
def auth_mode_app():
    """Application configured in authenticated private mode with isolated fake data layer."""
    fake_db = FakeDatabase("fieldnote_private")
    fake_fs = FakeGridFS()
    fake_embed = FakeEmbeddingService()

    app_instance = create_app()
    auth_settings = Settings(
        MONGODB_URI="mongodb://localhost:27017",
        DATABASE_NAME="fieldnote_private",
        APP_MODE="authenticated",
        _env_file=None,
    )
    app_instance.dependency_overrides[get_settings] = lambda: auth_settings
    app_instance.dependency_overrides[get_database] = lambda: fake_db
    app_instance.dependency_overrides[get_gridfs] = lambda: fake_fs
    app_instance.dependency_overrides[get_embedding_service] = lambda: fake_embed
    auth_rate_limiter.reset()

    # Seed a private note belonging to an existing user
    user_oid = ObjectId()
    fake_db["users"].insert_one({
        "_id": user_oid,
        "email": "owner@example.com",
        "hashed_password": "hash",
        "is_active": True,
        "created_at": datetime.now(timezone.utc),
    })
    private_note_oid = ObjectId()
    fake_db["notes"].insert_one({
        "_id": private_note_oid,
        "title": "Private Confidential Memory",
        "content": "Secret experience not for public eyes",
        "tags": ["personal"],
        "user_id": user_oid,
        "is_demo": False,
        "created_at": datetime.now(timezone.utc),
        "updated_at": datetime.now(timezone.utc),
    })

    yield {
        "app": app_instance,
        "db": fake_db,
        "fs": fake_fs,
        "user_oid": user_oid,
        "private_note_oid": private_note_oid,
    }

    app_instance.dependency_overrides.clear()
    auth_rate_limiter.reset()


def test_anonymous_write_operations_rejected_in_authenticated_mode(auth_mode_app):
    """In authenticated private mode, anonymous write requests return 401 Unauthorized."""
    client = TestClient(auth_mode_app["app"], base_url="http://localhost:8000")
    note_id = str(auth_mode_app["private_note_oid"])

    # 1. Create note
    res_create = client.post("/api/notes", json={"title": "Anon Note", "content": "Content"})
    assert res_create.status_code == status.HTTP_401_UNAUTHORIZED
    assert "Authentication required" in res_create.json()["detail"]

    # 2. Update note
    res_update = client.put(f"/api/notes/{note_id}", json={"title": "Updated", "content": "Updated"})
    assert res_update.status_code == status.HTTP_401_UNAUTHORIZED
    assert "Authentication required" in res_update.json()["detail"]

    # 3. Delete note
    res_delete = client.delete(f"/api/notes/{note_id}")
    assert res_delete.status_code == status.HTTP_401_UNAUTHORIZED
    assert "Authentication required" in res_delete.json()["detail"]

    # 4. Upload attachment
    files = {"file": ("test.png", SAMPLE_PNG, "image/png")}
    res_upload = client.post(f"/api/notes/{note_id}/attachments", files=files)
    assert res_upload.status_code == status.HTTP_401_UNAUTHORIZED
    assert "Authentication required" in res_upload.json()["detail"]

    # 5. Delete attachment
    dummy_att_id = str(ObjectId())
    res_del_att = client.delete(f"/api/notes/{note_id}/attachments/{dummy_att_id}")
    assert res_del_att.status_code == status.HTTP_401_UNAUTHORIZED
    assert "Authentication required" in res_del_att.json()["detail"]


def test_anonymous_read_operations_cannot_access_private_records(auth_mode_app):
    """In authenticated private mode, anonymous requests cannot access private notes."""
    client = TestClient(auth_mode_app["app"], base_url="http://localhost:8000")
    note_id = str(auth_mode_app["private_note_oid"])

    # 1. Detail lookup returns 404
    res_get = client.get(f"/api/notes/{note_id}")
    assert res_get.status_code == status.HTTP_404_NOT_FOUND

    # 2. Notes listing returns empty list (no private data returned)
    res_list = client.get("/api/notes")
    assert res_list.status_code == status.HTTP_200_OK
    assert res_list.json() == []


# ==============================================================================
# 3. Authenticated Writes and CSRF Protection in Authenticated Private Mode
# ==============================================================================

def test_authenticated_writes_succeed_with_valid_csrf(auth_mode_app):
    """Authenticated user with valid session and CSRF token can perform writes."""
    client = TestClient(auth_mode_app["app"], base_url="http://localhost:8000")

    # Register and obtain session
    reg_res = client.post("/api/auth/register", json={
        "email": "writer@example.com",
        "password": "PasswordWriter123!",
    })
    assert reg_res.status_code == 201
    csrf_token = reg_res.json()["csrf_token"]

    # Attach CSRF token
    client.headers["x-csrf-token"] = csrf_token

    # 1. Create note
    res_create = client.post("/api/notes", json={"title": "Private Entry", "content": "Journal content"})
    assert res_create.status_code == status.HTTP_201_CREATED
    created_id = res_create.json()["id"]

    # 2. Update note
    res_update = client.put(f"/api/notes/{created_id}", json={"title": "Updated Entry", "content": "Journal content v2"})
    assert res_update.status_code == status.HTTP_200_OK
    assert res_update.json()["title"] == "Updated Entry"

    # 3. Upload attachment
    files = {"file": ("chart.png", SAMPLE_PNG, "image/png")}
    res_upload = client.post(f"/api/notes/{created_id}/attachments", files=files)
    assert res_upload.status_code == status.HTTP_201_CREATED
    att_id = res_upload.json()["id"]

    # 4. Delete attachment
    res_del_att = client.delete(f"/api/notes/{created_id}/attachments/{att_id}")
    assert res_del_att.status_code == status.HTTP_204_NO_CONTENT

    # 5. Delete note
    res_delete = client.delete(f"/api/notes/{created_id}")
    assert res_delete.status_code == status.HTTP_204_NO_CONTENT


def test_authenticated_writes_rejected_when_csrf_token_missing_or_invalid(auth_mode_app):
    """Authenticated cookie request without matching CSRF token is rejected with 403 Forbidden."""
    client = TestClient(auth_mode_app["app"], base_url="http://localhost:8000")

    # Register
    reg_res = client.post("/api/auth/register", json={
        "email": "victim@example.com",
        "password": "PasswordVictim123!",
    })
    assert reg_res.status_code == 201

    # Attempt write WITHOUT x-csrf-token header
    res_no_csrf = client.post("/api/notes", json={"title": "CSRF Attack", "content": "Forged"})
    assert res_no_csrf.status_code == status.HTTP_403_FORBIDDEN
    assert "CSRF token validation failed" in res_no_csrf.json()["detail"]

    # Attempt write with INVALID x-csrf-token header
    client.headers["x-csrf-token"] = "forged-csrf-token-xyz"
    res_bad_csrf = client.post("/api/notes", json={"title": "CSRF Attack", "content": "Forged"})
    assert res_bad_csrf.status_code == status.HTTP_403_FORBIDDEN
    assert "CSRF token validation failed" in res_bad_csrf.json()["detail"]


# ==============================================================================
# 4. Demo Mode Strict Read-Only API Enforcement
# ==============================================================================

def test_demo_mode_blocks_writes_even_when_caller_is_authenticated():
    """In demo mode, writes sent directly to the API are rejected (403 Forbidden) even with auth."""
    fake_db = FakeDatabase("fieldnote_demo")
    fake_fs = FakeGridFS()
    fake_embed = FakeEmbeddingService()

    app_instance = create_app()
    demo_settings = Settings(
        MONGODB_URI="mongodb://localhost:27017",
        DATABASE_NAME="fieldnote_demo",
        APP_MODE="demo",
        _env_file=None,
    )
    app_instance.dependency_overrides[get_settings] = lambda: demo_settings
    app_instance.dependency_overrides[get_database] = lambda: fake_db
    app_instance.dependency_overrides[get_gridfs] = lambda: fake_fs
    app_instance.dependency_overrides[get_embedding_service] = lambda: fake_embed
    auth_rate_limiter.reset()

    client = TestClient(app_instance, base_url="http://localhost:8000")

    # Register an account
    reg_res = client.post("/api/auth/register", json={
        "email": "demouser@example.com",
        "password": "PasswordDemo123!",
    })
    assert reg_res.status_code == 201
    csrf_token = reg_res.json()["csrf_token"]
    client.headers["x-csrf-token"] = csrf_token

    # Direct API write attempt MUST be rejected by demo mode protection
    res_write = client.post("/api/notes", json={"title": "Demo Attempt", "content": "Blocked"})
    assert res_write.status_code == status.HTTP_403_FORBIDDEN
    assert res_write.json() == {"detail": "Operation not permitted in demo mode."}

    app_instance.dependency_overrides.clear()
    auth_rate_limiter.reset()


def test_authenticated_mode_production_env_banner_absent_and_writes_allowed(monkeypatch):
    """Confirm demo banner is absent and demo-mode write restrictions are not applied in authenticated mode."""
    fake_db = FakeDatabase("fieldnote_private")
    fake_fs = FakeGridFS()
    fake_embed = FakeEmbeddingService()

    monkeypatch.setenv("APP_ENV", "production")
    monkeypatch.setenv("APP_MODE", "authenticated")
    monkeypatch.setenv("DEMO_MODE", "false")
    monkeypatch.setenv("DATABASE_NAME", "fieldnote_private")
    monkeypatch.setenv("MONGODB_URI", "mongodb://localhost:27017")

    auth_settings = Settings(_env_file=None)
    assert auth_settings.resolved_app_mode == AppMode.AUTHENTICATED
    assert auth_settings.demo_mode is False
    assert auth_settings.is_demo_mode is False

    app_instance = create_app()
    app_instance.dependency_overrides[get_settings] = lambda: auth_settings
    app_instance.dependency_overrides[get_database] = lambda: fake_db
    app_instance.dependency_overrides[get_gridfs] = lambda: fake_fs
    app_instance.dependency_overrides[get_embedding_service] = lambda: fake_embed
    auth_rate_limiter.reset()

    client = TestClient(app_instance, base_url="https://testserver")

    # 1. UI Check: Demo banner must be completely absent from HTML responses
    res_home = client.get("/")
    assert res_home.status_code == 200
    assert "demo-banner" not in res_home.text
    assert "Public demonstration environment" not in res_home.text

    res_analytics = client.get("/analytics")
    assert res_analytics.status_code == 200
    assert "demo-banner" not in res_analytics.text

    # 2. API Check: Unauthenticated write must return 401 Unauthorized (NOT 403 demo-mode restriction)
    res_unauth = client.post("/api/notes", json={"title": "Private Note", "content": "Content"})
    assert res_unauth.status_code == status.HTTP_401_UNAUTHORIZED
    assert "Authentication required" in res_unauth.json()["detail"]
    assert "demo mode" not in res_unauth.json()["detail"].lower()

    # 3. API Check: Authenticated owner with CSRF can perform writes successfully
    reg_res = client.post("/api/auth/register", json={
        "email": "owner@example.com",
        "password": "PasswordAuth123!",
    })
    assert reg_res.status_code == status.HTTP_201_CREATED
    csrf_token = reg_res.json()["csrf_token"]
    client.headers["x-csrf-token"] = csrf_token

    res_write = client.post("/api/notes", json={"title": "Private Note", "content": "Owner content"})
    assert res_write.status_code == status.HTTP_201_CREATED
    assert res_write.json()["title"] == "Private Note"

    app_instance.dependency_overrides.clear()
    auth_rate_limiter.reset()


def test_boolean_and_quoted_string_parsing_robustness():
    """Verify that string representations of 'false' and quoted strings parse safely."""
    for false_val in ["false", "False", "FALSE", "0", "no", "off"]:
        s = Settings(
            _env_file=None,
            APP_MODE="authenticated",
            DEMO_MODE=false_val,
            DATABASE_NAME="fieldnote_private",
            MONGODB_URI="mongodb://localhost:27017",
        )
        assert s.demo_mode is False
        assert s.is_demo_mode is False
        assert s.resolved_app_mode == AppMode.AUTHENTICATED

    # Quoted string parsing (e.g. from environment variable injection)
    s_quoted = Settings(
        _env_file=None,
        APP_MODE='"authenticated"',
        DEMO_MODE="false",
        DATABASE_NAME="fieldnote_private",
        MONGODB_URI="mongodb://localhost:27017",
    )
    assert s_quoted.resolved_app_mode == AppMode.AUTHENTICATED
    assert s_quoted.is_demo_mode is False
