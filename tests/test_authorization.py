"""Adversarial multi-user authorization test suite for Fieldnote.

Verifies strict tenant isolation across all endpoints:
- User identity is derived exclusively from server-side authenticated sessions (zero client trust).
- Client-supplied owner_id / user_id values are strictly ignored.
- User A cannot view, update, delete, search, or download User B's notes or attachments.
- Attachment IDs cannot bypass parent note ownership.
- Cross-user data leakage is prevented across full-text search, tag filtering, semantic vector retrieval,
  and analytics aggregation pipelines.
- Unauthenticated requests cannot access private user data.
- Explicitly public synthetic demo records are strictly read-only and separate.
"""

from copy import deepcopy
from datetime import datetime, timezone
import io
from typing import Any, Dict, List, Optional
from bson import ObjectId
import pytest
from fastapi.testclient import TestClient

from app.main import create_app
from app.db import get_database, get_gridfs
from app.config import Settings, get_settings
from app.services.embedding import get_embedding_service
from app.services.auth import auth_rate_limiter


# Valid 1x1 test image bytes
SAMPLE_PNG = (
    b"\x89PNG\r\n\x1a\n\x00\x00\x00\rIHDR\x00\x00\x00\x01\x00\x00\x00\x01\x08\x02\x00\x00\x00\x90wS\xde"
    b"\x00\x00\x00\x0cIDATx\x9cc\xf8\xcf\xc0\x00\x00\x03\x01\x01\x00\xc9\xfe\x92\xef\x00\x00\x00\x00IEND\xaeB`\x82"
)


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

    def put(self, data: bytes, filename: str = None, content_type: str = None, **kwargs):
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


class FakeCursor:
    def __init__(self, docs: List[dict]):
        self._docs = [deepcopy(d) for d in docs]

    def sort(self, key_or_list, direction=1):
        if isinstance(key_or_list, list):
            for key, dir_val in reversed(key_or_list):
                self._docs.sort(key=lambda d: d.get(key, 0) or 0, reverse=(dir_val == -1))
        else:
            self._docs.sort(key=lambda d: d.get(key_or_list, 0) or 0, reverse=(direction == -1))
        return self

    def skip(self, count: int):
        self._docs = self._docs[count:]
        return self

    def limit(self, count: int):
        self._docs = self._docs[:count]
        return self

    def __iter__(self):
        return iter(self._docs)


class FakeCollection:
    def __init__(self, name: str = "", db: Any = None):
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
            elif k == "tags":
                if isinstance(v, dict) and "$in" in v:
                    doc_tags = doc.get("tags", [])
                    if not any(t in doc_tags for t in v["$in"]):
                        return False
            elif k == "$text":
                search_term = v.get("$search", "").lower()
                title = str(doc.get("title", "")).lower()
                content = str(doc.get("content", "")).lower()
                if search_term not in title and search_term not in content:
                    return False
            elif isinstance(v, dict) and "$gt" in v:
                val = doc.get(k)
                if not val or val <= v["$gt"]:
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
        matched = []
        for doc in self.docs.values():
            if self._matches_filter(doc, filter_dict or {}):
                matched.append(doc)
        return FakeCursor(matched)

    def find_one_and_update(self, filter_dict: dict, update_dict: dict, return_document=None) -> Optional[dict]:
        target_doc = None
        for doc in self.docs.values():
            if self._matches_filter(doc, filter_dict):
                target_doc = doc
                break
        if not target_doc:
            return None
        set_fields = update_dict.get("$set", {})
        target_doc.update(deepcopy(set_fields))
        return deepcopy(target_doc)

    def update_one(self, filter_dict: dict, update_dict: dict):
        target_doc = None
        for doc in self.docs.values():
            if self._matches_filter(doc, filter_dict):
                target_doc = doc
                break
        if target_doc:
            target_doc.update(deepcopy(update_dict.get("$set", {})))

            class Res:
                matched_count = 1
                modified_count = 1

            return Res()

        class NoRes:
            matched_count = 0
            modified_count = 0

        return NoRes()

    def update_many(self, filter_dict: dict, update_dict: dict):
        count = 0
        set_fields = update_dict.get("$set", {})
        for doc in self.docs.values():
            if self._matches_filter(doc, filter_dict):
                doc.update(deepcopy(set_fields))
                count += 1

        class ManyRes:
            modified_count = count

        return ManyRes()

    def delete_one(self, filter_dict: dict):
        target_oid = None
        for oid, doc in self.docs.items():
            if self._matches_filter(doc, filter_dict):
                target_oid = oid
                break
        if target_oid:
            del self.docs[target_oid]

            class Res:
                deleted_count = 1

            return Res()

        class NoRes:
            deleted_count = 0

        return NoRes()

    def count_documents(self, filter_dict: Optional[dict] = None) -> int:
        count = 0
        for doc in self.docs.values():
            if self._matches_filter(doc, filter_dict or {}):
                # Check tags non-whitespace match if specified
                if filter_dict and "tags" in filter_dict and "$elemMatch" in filter_dict["tags"]:
                    tags = doc.get("tags", [])
                    if isinstance(tags, list) and any(isinstance(t, str) and t.strip() for t in tags):
                        count += 1
                else:
                    count += 1
        return count

    def aggregate(self, pipeline: List[dict]):
        # Extract owner filter from $match if present
        owner_id = None
        for stage in pipeline:
            if "$match" in stage and "user_id" in stage["$match"]:
                owner_id = stage["$match"]["user_id"]
                break

        # Filter docs by owner first
        current_docs = []
        for doc in self.docs.values():
            if owner_id is not None:
                if doc.get("user_id") == owner_id:
                    current_docs.append(deepcopy(doc))
            else:
                if doc.get("user_id") is None:
                    current_docs.append(deepcopy(doc))

        # 1. Tag distribution
        if any("$unwind" in s for s in pipeline):
            counts = {}
            for d in current_docs:
                tags = d.get("tags")
                if isinstance(tags, list):
                    for t in tags:
                        if isinstance(t, str) and t.strip():
                            counts[t] = counts.get(t, 0) + 1
            sorted_tags = sorted(counts.items(), key=lambda x: (-x[1], x[0]))
            return [{"tag": t, "count": c} for t, c in sorted_tags]

        # 2. Activity pipeline
        if any("$group" in s and "_id" in s["$group"] and isinstance(s["$group"]["_id"], dict) for s in pipeline):
            counts = {}
            for d in current_docs:
                created = d.get("created_at")
                if created and isinstance(created, datetime):
                    ds = created.astimezone(timezone.utc).strftime("%Y-%m-%d")
                    counts[ds] = counts.get(ds, 0) + 1
            sorted_days = sorted(counts.items(), key=lambda x: x[0])
            return [{"date": ds, "count": c} for ds, c in sorted_days]

        # 3. Attachment counts pipeline
        if any("$lookup" in s for s in pipeline):
            att_coll = self.db["attachments"] if self.db else None
            results = []
            for d in current_docs:
                nid = d["_id"]
                acount = 0
                if att_coll:
                    for adoc in att_coll.docs.values():
                        if adoc.get("note_id") == nid:
                            if owner_id is not None:
                                if adoc.get("user_id") == owner_id:
                                    acount += 1
                            else:
                                if adoc.get("user_id") is None:
                                    acount += 1
                results.append({
                    "note_id": str(nid),
                    "title": d.get("title", ""),
                    "attachment_count": acount,
                })
            results.sort(key=lambda x: (-x["attachment_count"], x["title"], x["note_id"]))
            return results

        # 4. Atlas Vector search simulation
        if any("$vectorSearch" in s for s in pipeline):
            # Return all documents with simulated scores for post-filtering validation testing
            results = []
            for d in self.docs.values():
                res = deepcopy(d)
                res["score"] = 0.95
                results.append(res)
            return results

        return []

    def create_index(self, keys, name=None, **kwargs):
        return name or "idx"


class FakeMultiUserDatabase:
    def __init__(self):
        self.collections: Dict[str, FakeCollection] = {}

    def __getitem__(self, name: str) -> FakeCollection:
        if name not in self.collections:
            self.collections[name] = FakeCollection(name=name, db=self)
        return self.collections[name]


class FakeDeterministicEmbeddingService:
    model_name = "sentence-transformers/all-MiniLM-L6-v2"

    def prepare_text(self, title: str, content: str) -> str:
        return f"{title}\n\n{content}"

    def generate_embedding(self, text: str):
        val = 1.0 / (384 ** 0.5)
        return [val] * 384


@pytest.fixture
def multi_user_setup():
    """Isolated multi-user application instance with fake DB, GridFS, and embedding service."""
    db = FakeMultiUserDatabase()
    fs = FakeGridFS()
    embed = FakeDeterministicEmbeddingService()

    app = create_app()
    test_settings = Settings(
        MONGODB_URI="mongodb://localhost:27017",
        DATABASE_NAME="fieldnote_test_db",
        APP_ENV="testing",
        DEMO_MODE=False,
        _env_file=None,
    )
    app.dependency_overrides[get_settings] = lambda: test_settings
    app.dependency_overrides[get_database] = lambda: db
    app.dependency_overrides[get_gridfs] = lambda: fs
    app.dependency_overrides[get_embedding_service] = lambda: embed
    auth_rate_limiter.reset()

    # Pre-seed a synthetic demo record
    demo_id = ObjectId()
    db["notes"].insert_one({
        "_id": demo_id,
        "title": "Synthetic Public Specimen Observation",
        "content": "Public observation of synthetic fungi.",
        "tags": ["demo", "public"],
        "user_id": None,
        "is_demo": True,
        "created_at": datetime(2026, 9, 1, tzinfo=timezone.utc),
        "updated_at": datetime(2026, 9, 1, tzinfo=timezone.utc),
    })

    client_a = TestClient(app, base_url="http://localhost:8000")
    client_b = TestClient(app, base_url="http://localhost:8000")
    client_anon = TestClient(app, base_url="http://localhost:8000")

    # Register User A
    res_a = client_a.post("/api/auth/register", json={
        "email": "user_a@example.com",
        "password": "PasswordUserA123!",
    })
    assert res_a.status_code == 201
    user_a_id = res_a.json()["user"]["id"]
    csrf_a = res_a.json()["csrf_token"]

    # Register User B
    res_b = client_b.post("/api/auth/register", json={
        "email": "user_b@example.com",
        "password": "PasswordUserB456!",
    })
    assert res_b.status_code == 201
    user_b_id = res_b.json()["user"]["id"]
    csrf_b = res_b.json()["csrf_token"]

    client_a.headers["x-csrf-token"] = csrf_a
    client_b.headers["x-csrf-token"] = csrf_b

    yield {
        "db": db,
        "fs": fs,
        "client_a": client_a,
        "client_b": client_b,
        "client_anon": client_anon,
        "user_a_id": user_a_id,
        "user_b_id": user_b_id,
        "csrf_a": csrf_a,
        "csrf_b": csrf_b,
        "demo_id": str(demo_id),
    }

    app.dependency_overrides.clear()
    auth_rate_limiter.reset()


# ==============================================================================
# 1. Identity Derivation & Ownership Tampering
# ==============================================================================

def test_client_supplied_owner_id_tampering_ignored(multi_user_setup):
    """Rule 1: Owner identity is derived strictly from server session; client-supplied owner_id is ignored."""
    client_a = multi_user_setup["client_a"]
    user_a_id = multi_user_setup["user_a_id"]
    user_b_id = multi_user_setup["user_b_id"]
    db = multi_user_setup["db"]

    # User A creates note attempting to impersonate User B
    payload = {
        "title": "Tampered Ownership Attempt",
        "content": "Secret notes of user A",
        "tags": ["personal"],
        "user_id": user_b_id,
        "owner_id": user_b_id,
    }
    res = client_a.post("/api/notes", json=payload)
    assert res.status_code == 201
    created_id = res.json()["id"]

    # Verify document in DB has user_id set to User A, NOT User B
    doc = db["notes"].find_one({"_id": ObjectId(created_id)})
    assert doc is not None
    assert doc["user_id"] == ObjectId(user_a_id)
    assert doc["user_id"] != ObjectId(user_b_id)


# ==============================================================================
# 2. Note CRUD Authorization & Cross-User ID Guessing
# ==============================================================================

def test_note_detail_cross_user_guessing_blocked(multi_user_setup):
    """Rule 2 & 5: User B and unauthenticated client cannot retrieve User A's note by ID."""
    client_a = multi_user_setup["client_a"]
    client_b = multi_user_setup["client_b"]
    client_anon = multi_user_setup["client_anon"]

    # User A creates note
    res = client_a.post("/api/notes", json={"title": "User A Secret", "content": "Sensitive research A"})
    note_a_id = res.json()["id"]

    # User A can retrieve it
    assert client_a.get(f"/api/notes/{note_a_id}").status_code == 200

    # User B guessing note_a_id -> 404 Not Found (not leaked)
    res_b = client_b.get(f"/api/notes/{note_a_id}")
    assert res_b.status_code == 404
    assert res_b.json()["detail"] == f"Note with ID '{note_a_id}' not found"

    # Unauthenticated client guessing note_a_id -> 404 Not Found
    res_anon = client_anon.get(f"/api/notes/{note_a_id}")
    assert res_anon.status_code == 404


def test_note_update_cross_user_mutation_blocked(multi_user_setup):
    """Rule 2: User B cannot update User A's note; data remains untouched."""
    client_a = multi_user_setup["client_a"]
    client_b = multi_user_setup["client_b"]
    client_anon = multi_user_setup["client_anon"]
    db = multi_user_setup["db"]

    res = client_a.post("/api/notes", json={"title": "Original Title", "content": "Original Content"})
    note_a_id = res.json()["id"]

    # User B attempts to tamper with User A's note
    res_b = client_b.put(f"/api/notes/{note_a_id}", json={"title": "Hacked Title", "content": "Hacked Content"})
    assert res_b.status_code == 404

    # Unauthenticated attempts to tamper
    res_anon = client_anon.put(f"/api/notes/{note_a_id}", json={"title": "Anon Hack", "content": "Anon Hack"})
    assert res_anon.status_code == 404

    # Verify original note is unchanged
    doc = db["notes"].find_one({"_id": ObjectId(note_a_id)})
    assert doc["title"] == "Original Title"
    assert doc["content"] == "Original Content"


def test_note_delete_cross_user_deletion_blocked(multi_user_setup):
    """Rule 2: User B cannot delete User A's note; note remains intact."""
    client_a = multi_user_setup["client_a"]
    client_b = multi_user_setup["client_b"]
    client_anon = multi_user_setup["client_anon"]
    db = multi_user_setup["db"]

    res = client_a.post("/api/notes", json={"title": "Undeletable Note", "content": "Important research"})
    note_a_id = res.json()["id"]

    # User B attempts deletion
    res_b = client_b.delete(f"/api/notes/{note_a_id}")
    assert res_b.status_code == 404

    # Unauthenticated attempts deletion
    res_anon = client_anon.delete(f"/api/notes/{note_a_id}")
    assert res_anon.status_code == 404

    # Note still exists
    assert db["notes"].find_one({"_id": ObjectId(note_a_id)}) is not None

    # User A can delete own note
    res_a_del = client_a.delete(f"/api/notes/{note_a_id}")
    assert res_a_del.status_code == 204


def test_note_listing_cross_user_isolation(multi_user_setup):
    """Rule 2 & 5: Note listing only returns notes belonging to the authenticated user."""
    client_a = multi_user_setup["client_a"]
    client_b = multi_user_setup["client_b"]
    client_anon = multi_user_setup["client_anon"]

    # User A creates 2 notes
    client_a.post("/api/notes", json={"title": "Note A1", "content": "Content A1"})
    client_a.post("/api/notes", json={"title": "Note A2", "content": "Content A2"})

    # User B creates 1 note
    client_b.post("/api/notes", json={"title": "Note B1", "content": "Content B1"})

    # User A listing
    notes_a = client_a.get("/api/notes").json()
    assert len(notes_a) == 2
    titles_a = [n["title"] for n in notes_a]
    assert "Note A1" in titles_a
    assert "Note A2" in titles_a
    assert "Note B1" not in titles_a

    # User B listing
    notes_b = client_b.get("/api/notes").json()
    assert len(notes_b) == 1
    assert notes_b[0]["title"] == "Note B1"

    # Unauthenticated listing (does not see User A or User B's private notes)
    notes_anon = client_anon.get("/api/notes").json()
    anon_titles = [n["title"] for n in notes_anon]
    assert "Note A1" not in anon_titles
    assert "Note A2" not in anon_titles
    assert "Note B1" not in anon_titles


# ==============================================================================
# 3. GridFS Attachment Authorization & Bypass Prevention
# ==============================================================================

def test_attachment_upload_other_user_note_blocked(multi_user_setup):
    """Rule 3: User B cannot upload attachments to User A's note."""
    client_a = multi_user_setup["client_a"]
    client_b = multi_user_setup["client_b"]
    client_anon = multi_user_setup["client_anon"]

    res_a = client_a.post("/api/notes", json={"title": "Note A Evidence", "content": "Field evidence"})
    note_a_id = res_a.json()["id"]

    files = {"file": ("malicious.png", SAMPLE_PNG, "image/png")}

    # User B upload attempt -> 404 Not Found
    res_b = client_b.post(f"/api/notes/{note_a_id}/attachments", files=files)
    assert res_b.status_code == 404

    # Anonymous upload attempt -> 404 Not Found
    res_anon = client_anon.post(f"/api/notes/{note_a_id}/attachments", files=files)
    assert res_anon.status_code == 404


def test_attachment_download_and_id_bypass_blocked(multi_user_setup):
    """Rule 3: Knowing attachment ID cannot bypass note ownership; cross-download is rejected."""
    client_a = multi_user_setup["client_a"]
    client_b = multi_user_setup["client_b"]
    client_anon = multi_user_setup["client_anon"]

    # User A creates note and uploads attachment
    res_a = client_a.post("/api/notes", json={"title": "Note A With Photo", "content": "Photo notes"})
    note_a_id = res_a.json()["id"]
    files = {"file": ("evidence_a.png", SAMPLE_PNG, "image/png")}
    att_res = client_a.post(f"/api/notes/{note_a_id}/attachments", files=files)
    assert att_res.status_code == 201
    att_a_id = att_res.json()["id"]

    # User B creates Note B
    res_b = client_b.post("/api/notes", json={"title": "Note B", "content": "User B note"})
    note_b_id = res_b.json()["id"]

    # 1. User B tries to download directly using User A's note_id and att_a_id
    res_b_download = client_b.get(f"/api/notes/{note_a_id}/attachments/{att_a_id}/download")
    assert res_b_download.status_code == 404

    # 2. User B tries ID bypass: pair User B's note_id with User A's att_a_id
    res_b_bypass = client_b.get(f"/api/notes/{note_b_id}/attachments/{att_a_id}/download")
    assert res_b_bypass.status_code == 404

    # 3. Anonymous tries to download User A's attachment
    res_anon_download = client_anon.get(f"/api/notes/{note_a_id}/attachments/{att_a_id}/download")
    assert res_anon_download.status_code == 404

    # 4. User A downloads successfully
    res_a_download = client_a.get(f"/api/notes/{note_a_id}/attachments/{att_a_id}/download")
    assert res_a_download.status_code == 200
    assert res_a_download.content == SAMPLE_PNG


def test_attachment_delete_cross_user_blocked(multi_user_setup):
    """Rule 3: User B cannot delete User A's attachment; binary and metadata remain intact."""
    client_a = multi_user_setup["client_a"]
    client_b = multi_user_setup["client_b"]
    client_anon = multi_user_setup["client_anon"]
    db = multi_user_setup["db"]

    res_a = client_a.post("/api/notes", json={"title": "Note A", "content": "Content"})
    note_a_id = res_a.json()["id"]
    files = {"file": ("evidence_a.png", SAMPLE_PNG, "image/png")}
    att_res = client_a.post(f"/api/notes/{note_a_id}/attachments", files=files)
    att_a_id = att_res.json()["id"]

    # User B attempts to delete
    res_b_del = client_b.delete(f"/api/notes/{note_a_id}/attachments/{att_a_id}")
    assert res_b_del.status_code == 404

    # Anonymous attempts to delete
    res_anon_del = client_anon.delete(f"/api/notes/{note_a_id}/attachments/{att_a_id}")
    assert res_anon_del.status_code == 404

    # Metadata and binary remain
    assert db["attachments"].find_one({"_id": ObjectId(att_a_id)}) is not None


# ==============================================================================
# 4. Search & Retrieval Isolation (Text, Tags, Vector Search)
# ==============================================================================

def test_text_search_and_tag_filtering_isolation(multi_user_setup):
    """Rule 4: Full-text search and tag queries never leak another user's notes."""
    client_a = multi_user_setup["client_a"]
    client_b = multi_user_setup["client_b"]
    client_anon = multi_user_setup["client_anon"]

    # User A creates classified note
    client_a.post("/api/notes", json={
        "title": "Quantum Resonance Log",
        "content": "Secret isotope telemetry findings",
        "tags": ["quantum", "classified"],
    })

    # User B creates unrelated note
    client_b.post("/api/notes", json={
        "title": "Garden Botany Log",
        "content": "Rose bush growth measurements",
        "tags": ["botany", "outdoor"],
    })

    # User B searches text query matching User A's note
    res_b_text = client_b.get("/api/notes?q=quantum")
    assert res_b_text.status_code == 200
    assert len(res_b_text.json()) == 0

    # User B filters by tag matching User A's note
    res_b_tag = client_b.get("/api/notes?tag=classified")
    assert res_b_tag.status_code == 200
    assert len(res_b_tag.json()) == 0

    # User A searches and finds own note
    res_a_text = client_a.get("/api/notes?q=quantum")
    assert res_a_text.status_code == 200
    assert len(res_a_text.json()) == 1
    assert res_a_text.json()[0]["title"] == "Quantum Resonance Log"

    # Anonymous search returns zero private notes
    res_anon_text = client_anon.get("/api/notes?q=quantum")
    assert res_anon_text.status_code == 200
    assert len(res_anon_text.json()) == 0


def test_semantic_vector_search_cross_user_leakage_prevented(multi_user_setup):
    """Rule 4 & 8: Semantic vector search validates returned document ownership in Python."""
    client_a = multi_user_setup["client_a"]
    client_b = multi_user_setup["client_b"]
    client_anon = multi_user_setup["client_anon"]

    # User A creates note
    client_a.post("/api/notes", json={
        "title": "Bioluminescent Spectral Wavelength",
        "content": "Emission peaks at 520 nanometers in cavern fissure",
    })

    # User B queries semantic search
    res_b = client_b.get("/api/search/semantic?q=bioluminescent+wavelength")
    assert res_b.status_code == 200
    # Note A must be excluded by owner validation
    assert len(res_b.json()) == 0

    # Anonymous queries semantic search -> zero private notes leaked
    res_anon = client_anon.get("/api/search/semantic?q=bioluminescent+wavelength")
    assert res_anon.status_code == 200
    anon_titles = [n["title"] for n in res_anon.json()]
    assert "Bioluminescent Spectral Wavelength" not in anon_titles

    # User A queries semantic search -> returns Note A
    res_a = client_a.get("/api/search/semantic?q=bioluminescent+wavelength")
    assert res_a.status_code == 200
    assert len(res_a.json()) == 1
    assert res_a.json()[0]["title"] == "Bioluminescent Spectral Wavelength"


# ==============================================================================
# 5. Analytics Aggregation Isolation
# ==============================================================================

def test_analytics_pipelines_strict_isolation(multi_user_setup):
    """Rule 4: Overview counts, tag distribution, daily activity, and attachment counts are strictly scoped."""
    client_a = multi_user_setup["client_a"]
    client_b = multi_user_setup["client_b"]
    client_anon = multi_user_setup["client_anon"]

    # User A has 2 notes, 1 attachment, 2 tags
    res_a1 = client_a.post("/api/notes", json={"title": "Note A1", "content": "Content", "tags": ["tagA1", "shared"]})
    note_a1_id = res_a1.json()["id"]
    client_a.post("/api/notes", json={"title": "Note A2", "content": "Content", "tags": ["tagA2"]})
    client_a.post(f"/api/notes/{note_a1_id}/attachments", files={"file": ("photo.png", SAMPLE_PNG, "image/png")})

    # User B has 1 note, 0 attachments, 1 tag
    client_b.post("/api/notes", json={"title": "Note B1", "content": "Content", "tags": ["tagB1", "shared"]})

    # 1. Overview counts
    ov_a = client_a.get("/api/analytics/overview").json()
    assert ov_a["total_notes"] == 2
    assert ov_a["total_attachments"] == 1
    assert ov_a["notes_with_tags"] == 2

    ov_b = client_b.get("/api/analytics/overview").json()
    assert ov_b["total_notes"] == 1
    assert ov_b["total_attachments"] == 0
    assert ov_b["notes_with_tags"] == 1

    # 2. Tag distribution
    tags_a = client_a.get("/api/analytics/tags").json()
    tag_names_a = [t["tag"] for t in tags_a]
    assert "tagA1" in tag_names_a
    assert "tagA2" in tag_names_a
    assert "tagB1" not in tag_names_a

    tags_b = client_b.get("/api/analytics/tags").json()
    tag_names_b = [t["tag"] for t in tags_b]
    assert "tagB1" in tag_names_b
    assert "tagA1" not in tag_names_b
    assert "tagA2" not in tag_names_b

    # 3. Attachment counts by note
    att_a = client_a.get("/api/analytics/attachments").json()
    titles_a = [n["title"] for n in att_a]
    assert "Note A1" in titles_a
    assert "Note A2" in titles_a
    assert "Note B1" not in titles_a

    att_b = client_b.get("/api/analytics/attachments").json()
    titles_b = [n["title"] for n in att_b]
    assert "Note B1" in titles_b
    assert "Note A1" not in titles_b
    assert "Note A2" not in titles_b


# ==============================================================================
# 6. Public Synthetic Demo Record Protection & Immutability
# ==============================================================================

def test_synthetic_demo_records_read_only_and_protected(multi_user_setup):
    """Rule 6: Public synthetic demo records can be read, but are strictly read-only."""
    client_a = multi_user_setup["client_a"]
    client_anon = multi_user_setup["client_anon"]
    demo_id = multi_user_setup["demo_id"]

    # 1. Unauthenticated can read public demo note
    res_get = client_anon.get(f"/api/notes/{demo_id}")
    assert res_get.status_code == 200
    assert res_get.json()["title"] == "Synthetic Public Specimen Observation"

    # 2. Authenticated User A attempts mutation -> 403 Forbidden (Demo record read-only)
    res_put = client_a.put(f"/api/notes/{demo_id}", json={"title": "Tampered Demo", "content": "Modified"})
    assert res_put.status_code == 403
    assert res_put.json()["detail"] == "Synthetic demo records are read-only"

    # 3. Authenticated User A attempts deletion -> 403 Forbidden
    res_del = client_a.delete(f"/api/notes/{demo_id}")
    assert res_del.status_code == 403
    assert res_del.json()["detail"] == "Synthetic demo records are read-only"

    # 4. Authenticated User A attempts upload attachment -> 403 Forbidden
    files = {"file": ("demo_att.png", SAMPLE_PNG, "image/png")}
    res_upload = client_a.post(f"/api/notes/{demo_id}/attachments", files=files)
    assert res_upload.status_code == 403
    assert res_upload.json()["detail"] == "Synthetic demo records are read-only"

    # 5. Anonymous attempts mutation -> 403 Forbidden
    res_anon_put = client_anon.put(f"/api/notes/{demo_id}", json={"title": "Anon Tamper", "content": "Modified"})
    assert res_anon_put.status_code == 403
