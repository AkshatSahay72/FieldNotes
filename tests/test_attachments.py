import io
from copy import deepcopy
from datetime import datetime, timezone
from bson import ObjectId
import pytest
from fastapi.testclient import TestClient
from pymongo.errors import PyMongoError

from app.main import app
from app.db import get_database, get_gridfs
from app.config import Settings, get_settings


# Sample valid 1x1 image byte payloads verified by Pillow
SAMPLE_PNG = (
    b"\x89PNG\r\n\x1a\n\x00\x00\x00\rIHDR\x00\x00\x00\x01\x00\x00\x00\x01\x08\x02\x00\x00\x00\x90wS\xde"
    b"\x00\x00\x00\x0cIDATx\x9cc\xf8\xcf\xc0\x00\x00\x03\x01\x01\x00\xc9\xfe\x92\xef\x00\x00\x00\x00IEND\xaeB`\x82"
)
SAMPLE_JPEG = (
    b"\xff\xd8\xff\xe0\x00\x10JFIF\x00\x01\x01\x00\x00\x01\x00\x01\x00\x00\xff\xdb\x00C\x00\x08\x06\x06\x07\x06\x05\x08\x07\x07\x07"
    b"\t\t\x08\n\x0c\x14\r\x0c\x0b\x0b\x0c\x19\x12\x13\x0f\x14\x1d\x1a\x1f\x1e\x1d\x1a\x1c\x1c $.' \",#\x1c\x1c(7),01444\x1f'9=82<.342"
    b"\xff\xdb\x00C\x01\t\t\t\x0c\x0b\x0c\x18\r\r\x182!\x1c!22222222222222222222222222222222222222222222222222"
    b"\xff\xc0\x00\x11\x08\x00\x01\x00\x01\x03\x01\"\x00\x02\x11\x01\x03\x11\x01\xff\xc4\x00\x1f\x00\x00\x01\x05\x01\x01\x01\x01\x01\x01"
    b"\x00\x00\x00\x00\x00\x00\x00\x00\x01\x02\x03\x04\x05\x06\x07\x08\t\n\x0b\xff\xc4\x00\xb5\x10\x00\x02\x01\x03\x03\x02\x04\x03\x05\x05\x04\x04"
    b"\x00\x00\x01}\x01\x02\x03\x00\x04\x11\x05\x12!1A\x06\x13Qa\x07\"q\x142\x81\x91\xa1\x08#B\xb1\xc1\x15R\xd1\xf0$3br\x82\t\n\x16\x17\x18\x19\x1a"
    b"%&'()*456789:CDEFGHIJSTUVWXYZcdefghijstuvwxyz\x83\x84\x85\x86\x87\x88\x89\x8a\x92\x93\x94\x95\x96\x97\x98\x99\x9a\xa2\xa3\xa4\xa5\xa6\xa7\xa8\xa9\xaa"
    b"\xb2\xb3\xb4\xb5\xb6\xb7\xb8\xb9\xba\xc2\xc3\xc4\xc5\xc6\xc7\xc8\xc9\xca\xd2\xd3\xd4\xd5\xd6\xd7\xd8\xd9\xda\xe1\xe2\xe3\xe4\xe5\xe6\xe7\xe8\xe9\xea"
    b"\xf1\xf2\xf3\xf4\xf5\xf6\xf7\xf8\xf9\xfa\xff\xc4\x00\x1f\x01\x00\x03\x01\x01\x01\x01\x01\x01\x01\x01\x01\x00\x00\x00\x00\x00\x00\x01\x02\x03\x04\x05"
    b"\x06\x07\x08\t\n\x0b\xff\xc4\x00\xb5\x11\x00\x02\x01\x02\x04\x04\x03\x04\x07\x05\x04\x04\x00\x01\x02w\x00\x01\x02\x03\x11\x04\x05!1\x06\x12AQ\x07"
    b"aq\x13\"2\x81\x08\x14B\x91\xa1\xb1\xc1\t#3R\xf0\x15br\xd1\n\x16$4\xe1%\xf1\x17\x18\x19\x1a&'()*56789:CDEFGHIJSTUVWXYZcdefghijstuvwxyz\x82\x83\x84"
    b"\x85\x86\x87\x88\x89\x8a\x92\x93\x94\x95\x96\x97\x98\x99\x9a\xa2\xa3\xa4\xa5\xa6\xa7\xa8\xa9\xaa\xb2\xb3\xb4\xb5\xb6\xb7\xb8\xb9\xba\xc2\xc3\xc4\xc5"
    b"\xc6\xc7\xc8\xc9\xca\xd2\xd3\xd4\xd5\xd6\xd7\xd8\xd9\xda\xe2\xe3\xe4\xe5\xe6\xe7\xe8\xe9\xea\xf2\xf3\xf4\xf5\xf6\xf7\xf8\xf9\xfa\xff\xda\x00\x0c\x03"
    b"\x01\x00\x02\x11\x03\x11\x00?\x00\xe2\xe8\xa2\x8a\xf9\x93\xf7\x13\xff\xd9"
)
SAMPLE_WEBP = (
    b"RIFF<\x00\x00\x00WEBPVP8 0\x00\x00\x00\xd0\x01\x00\x9d\x01*\x01\x00\x01\x00\x01@&%\xa0\x02t\xba\x01\xf8\x00\x03\xb0\x00"
    b"\xfe\xf2\xeb\x7f\xfc\xd8\x15\xcds\xef\xf7\xff\xd2\xe0\xfd.\x0f\xd2\xe0\xff\xd2\x90\x00\x00"
)


class FakeGridOut:
    """Simulates PyMongo GridOut file object."""

    def __init__(self, data: bytes, filename: str, content_type: str):
        self._buffer = io.BytesIO(data)
        self.filename = filename
        self.content_type = content_type

    def read(self, size=-1):
        return self._buffer.read(size)

    def close(self):
        self._buffer.close()


class FakeGridFS:
    """In-memory test double for PyMongo GridFS."""

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


class FakeCursor:
    def __init__(self, docs):
        self._docs = [deepcopy(d) for d in docs]

    def sort(self, key, direction=1):
        reverse = direction == -1
        self._docs.sort(key=lambda d: d.get(key), reverse=reverse)
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

        class Res:
            inserted_id = oid

        return Res()

    def find(self, filter_dict=None):
        filter_dict = filter_dict or {}
        matches = []
        for d in self.docs.values():
            match = True
            for k, v in filter_dict.items():
                if d.get(k) != v:
                    match = False
                    break
            if match:
                matches.append(d)
        return FakeCursor(matches)

    def find_one(self, filter_dict):
        for d in self.docs.values():
            match = True
            for k, v in filter_dict.items():
                if d.get(k) != v:
                    match = False
                    break
            if match:
                return deepcopy(d)
        return None

    def delete_one(self, filter_dict):
        target_oid = None
        for oid, d in self.docs.items():
            match = True
            for k, v in filter_dict.items():
                if d.get(k) != v:
                    match = False
                    break
            if match:
                target_oid = oid
                break

        if target_oid:
            del self.docs[target_oid]
            deleted = 1
        else:
            deleted = 0

        class Res:
            deleted_count = deleted

        return Res()

    def delete_many(self, filter_dict):
        to_delete = []
        for oid, d in self.docs.items():
            match = True
            for k, v in filter_dict.items():
                if d.get(k) != v:
                    match = False
                    break
            if match:
                to_delete.append(oid)

        for oid in to_delete:
            del self.docs[oid]

        class Res:
            deleted_count = len(to_delete)

        return Res()

    def create_index(self, keys, name=None):
        return name or "idx"


class FakeDatabase:
    def __init__(self):
        self._collections = {
            "notes": FakeCollection(),
            "attachments": FakeCollection(),
        }

    def __getitem__(self, name):
        if name not in self._collections:
            self._collections[name] = FakeCollection()
        return self._collections[name]


@pytest.fixture
def fake_db():
    return FakeDatabase()


@pytest.fixture
def fake_fs():
    return FakeGridFS()


@pytest.fixture
def client(fake_db, fake_fs):
    test_settings = Settings(
        MONGODB_URI="mongodb://localhost:27017",
        DATABASE_NAME="test_db",
        APP_ENV="testing",
        _env_file=None,
    )
    app.dependency_overrides[get_settings] = lambda: test_settings
    app.dependency_overrides[get_database] = lambda: fake_db
    app.dependency_overrides[get_gridfs] = lambda: fake_fs

    with TestClient(app) as test_client:
        yield test_client

    app.dependency_overrides.clear()


@pytest.fixture
def sample_note(fake_db):
    """Seed one note and return its string ID."""
    now = datetime.now(timezone.utc)
    res = fake_db["notes"].insert_one({
        "title": "Geology Field Observation",
        "content": "Observed quartz veining in basalt outcrop.",
        "tags": ["geology", "fieldwork"],
        "created_at": now,
        "updated_at": now,
    })
    return str(res.inserted_id)


# ==============================================================================
# POST /api/notes/{note_id}/attachments (Upload)
# ==============================================================================

def test_upload_attachment_jpeg_success(client, sample_note):
    """Verify uploading a valid JPEG returns 201 with metadata."""
    files = {"file": ("rock_sample.jpg", SAMPLE_JPEG, "image/jpeg")}
    data = {"caption": "Quartz vein close-up", "description": "10x hand lens magnification."}

    response = client.post(f"/api/notes/{sample_note}/attachments", files=files, data=data)
    assert response.status_code == 201

    body = response.json()
    assert ObjectId.is_valid(body["id"])
    assert body["note_id"] == sample_note
    assert body["filename"] == "rock_sample.jpg"
    assert body["content_type"] == "image/jpeg"
    assert body["file_size"] == len(SAMPLE_JPEG)
    assert body["caption"] == "Quartz vein close-up"
    assert body["description"] == "10x hand lens magnification."
    assert "created_at" in body


def test_upload_attachment_png_and_webp_success(client, sample_note):
    """Verify uploading PNG and WebP images succeed."""
    res_png = client.post(
        f"/api/notes/{sample_note}/attachments",
        files={"file": ("diagram.png", SAMPLE_PNG, "image/png")},
    )
    assert res_png.status_code == 201
    assert res_png.json()["content_type"] == "image/png"

    res_webp = client.post(
        f"/api/notes/{sample_note}/attachments",
        files={"file": ("photo.webp", SAMPLE_WEBP, "image/webp")},
    )
    assert res_webp.status_code == 201
    assert res_webp.json()["content_type"] == "image/webp"


def test_upload_attachment_invalid_mime_rejected(client, sample_note):
    """Verify non-image file is rejected with 415 Unsupported Media Type."""
    files = {"file": ("script.py", b"print('malicious executable')", "text/plain")}
    response = client.post(f"/api/notes/{sample_note}/attachments", files=files)
    assert response.status_code == 415
    assert "Unsupported file type" in response.json()["detail"]


def test_upload_attachment_fake_content_type_rejected(client, sample_note):
    """Verify client spoofing image/jpeg with text bytes is rejected via magic byte check."""
    files = {"file": ("fake.jpg", b"NOT_A_REAL_JPEG_IMAGE_HEADER", "image/jpeg")}
    response = client.post(f"/api/notes/{sample_note}/attachments", files=files)
    assert response.status_code == 415


def test_upload_attachment_empty_file_rejected(client, sample_note):
    """Verify empty file upload returns 400 Bad Request."""
    files = {"file": ("empty.jpg", b"", "image/jpeg")}
    response = client.post(f"/api/notes/{sample_note}/attachments", files=files)
    assert response.status_code == 400


def test_upload_attachment_oversized_rejected(client, sample_note):
    """Verify file exceeding 5 MB is rejected with 413 Payload Too Large."""
    oversized_data = SAMPLE_JPEG + (b"X" * (5 * 1024 * 1024 + 1))
    files = {"file": ("huge.jpg", oversized_data, "image/jpeg")}
    response = client.post(f"/api/notes/{sample_note}/attachments", files=files)
    assert response.status_code == 413
    assert "exceeds maximum allowed size" in response.json()["detail"]


def test_upload_attachment_missing_parent_note(client):
    """Verify uploading to a non-existent note returns 404 Not Found."""
    non_existent = str(ObjectId())
    files = {"file": ("test.jpg", SAMPLE_JPEG, "image/jpeg")}
    response = client.post(f"/api/notes/{non_existent}/attachments", files=files)
    assert response.status_code == 404


def test_upload_attachment_malformed_note_id(client):
    """Verify uploading with malformed note ID returns 400 Bad Request."""
    files = {"file": ("test.jpg", SAMPLE_JPEG, "image/jpeg")}
    response = client.post("/api/notes/invalid-note-id/attachments", files=files)
    assert response.status_code == 400


def test_upload_attachment_sanitizes_path_traversal(client, sample_note):
    """Verify path traversal in filename (../../secret.jpg) is stripped to safe basename."""
    files = {"file": ("../../etc/passwd_photo.jpg", SAMPLE_JPEG, "image/jpeg")}
    response = client.post(f"/api/notes/{sample_note}/attachments", files=files)
    assert response.status_code == 201
    assert response.json()["filename"] == "passwd_photo.jpg"


# ==============================================================================
# GET /api/notes/{note_id}/attachments (Listing)
# ==============================================================================

def test_list_attachments_for_note(client, sample_note, fake_db):
    """Verify listing attachments returns all items linked to parent note."""
    client.post(
        f"/api/notes/{sample_note}/attachments",
        files={"file": ("photo1.jpg", SAMPLE_JPEG, "image/jpeg")},
        data={"caption": "First photo"},
    )
    client.post(
        f"/api/notes/{sample_note}/attachments",
        files={"file": ("photo2.png", SAMPLE_PNG, "image/png")},
        data={"caption": "Second photo"},
    )

    response = client.get(f"/api/notes/{sample_note}/attachments")
    assert response.status_code == 200
    items = response.json()
    assert len(items) == 2
    assert items[0]["filename"] == "photo1.jpg"
    assert items[1]["filename"] == "photo2.png"


def test_list_attachments_missing_note(client):
    """Verify listing attachments for non-existent note returns 404."""
    non_existent = str(ObjectId())
    response = client.get(f"/api/notes/{non_existent}/attachments")
    assert response.status_code == 404


# ==============================================================================
# GET /api/notes/{note_id}/attachments/{attachment_id} (Metadata)
# ==============================================================================

def test_get_attachment_metadata_success(client, sample_note):
    """Verify retrieving single attachment metadata by ID."""
    upload_res = client.post(
        f"/api/notes/{sample_note}/attachments",
        files={"file": ("specimen.jpg", SAMPLE_JPEG, "image/jpeg")},
        data={"caption": "Specimen A"},
    )
    att_id = upload_res.json()["id"]

    get_res = client.get(f"/api/notes/{sample_note}/attachments/{att_id}")
    assert get_res.status_code == 200
    assert get_res.json()["id"] == att_id
    assert get_res.json()["caption"] == "Specimen A"


def test_get_attachment_metadata_not_found(client, sample_note):
    """Verify retrieving non-existent attachment returns 404."""
    non_existent_att = str(ObjectId())
    response = client.get(f"/api/notes/{sample_note}/attachments/{non_existent_att}")
    assert response.status_code == 404


def test_get_attachment_metadata_malformed_id(client, sample_note):
    """Verify malformed attachment ID returns 400 Bad Request."""
    response = client.get(f"/api/notes/{sample_note}/attachments/not-valid-hex")
    assert response.status_code == 400


# ==============================================================================
# GET /api/notes/{note_id}/attachments/{attachment_id}/download (Stream Download)
# ==============================================================================

def test_download_attachment_stream_success(client, sample_note):
    """Verify download endpoint streams raw binary with correct Content-Type."""
    upload_res = client.post(
        f"/api/notes/{sample_note}/attachments",
        files={"file": ("sample.jpg", SAMPLE_JPEG, "image/jpeg")},
    )
    att_id = upload_res.json()["id"]

    download_res = client.get(f"/api/notes/{sample_note}/attachments/{att_id}/download")
    assert download_res.status_code == 200
    assert download_res.content == SAMPLE_JPEG
    assert download_res.headers["content-type"] == "image/jpeg"
    assert 'filename="sample.jpg"' in download_res.headers["content-disposition"]


def test_download_attachment_not_found(client, sample_note):
    """Verify downloading non-existent attachment returns 404."""
    non_existent_att = str(ObjectId())
    response = client.get(f"/api/notes/{sample_note}/attachments/{non_existent_att}/download")
    assert response.status_code == 404


# ==============================================================================
# DELETE /api/notes/{note_id}/attachments/{attachment_id} (Delete Single)
# ==============================================================================

def test_delete_single_attachment_success(client, sample_note, fake_fs, fake_db):
    """Verify deleting attachment purges metadata and binary chunks from GridFS."""
    upload_res = client.post(
        f"/api/notes/{sample_note}/attachments",
        files={"file": ("to_del.jpg", SAMPLE_JPEG, "image/jpeg")},
    )
    att_id = upload_res.json()["id"]

    del_res = client.delete(f"/api/notes/{sample_note}/attachments/{att_id}")
    assert del_res.status_code == 204

    # Metadata gone
    get_res = client.get(f"/api/notes/{sample_note}/attachments/{att_id}")
    assert get_res.status_code == 404

    # GridFS chunks gone
    assert len(fake_fs.files) == 0


def test_delete_attachment_not_found(client, sample_note):
    """Verify deleting non-existent attachment returns 404."""
    non_existent = str(ObjectId())
    response = client.delete(f"/api/notes/{sample_note}/attachments/{non_existent}")
    assert response.status_code == 404


# ==============================================================================
# Cascading Deletion: DELETE /api/notes/{note_id}
# ==============================================================================

def test_cascade_delete_note_purges_all_attachments(client, sample_note, fake_fs, fake_db):
    """Verify deleting a note purges all associated attachments from GridFS and collection."""
    # Upload 2 attachments
    client.post(
        f"/api/notes/{sample_note}/attachments",
        files={"file": ("pic1.jpg", SAMPLE_JPEG, "image/jpeg")},
    )
    client.post(
        f"/api/notes/{sample_note}/attachments",
        files={"file": ("pic2.png", SAMPLE_PNG, "image/png")},
    )

    assert len(fake_fs.files) == 2
    assert len(fake_db["attachments"].docs) == 2

    # Delete parent note
    del_note_res = client.delete(f"/api/notes/{sample_note}")
    assert del_note_res.status_code == 204

    # Confirm parent note is gone
    assert client.get(f"/api/notes/{sample_note}").status_code == 404

    # Confirm all attachments are purged
    assert len(fake_fs.files) == 0
    assert len(fake_db["attachments"].docs) == 0


def test_cascade_delete_failure_protects_note_from_deletion(client, sample_note, fake_db):
    """Verify that if attachment cleanup fails, the parent note is NOT deleted and 503 is returned."""
    client.post(
        f"/api/notes/{sample_note}/attachments",
        files={"file": ("pic.jpg", SAMPLE_JPEG, "image/jpeg")},
    )

    # Simulate failure in GridFS delete
    class FaultyGridFS:
        def delete(self, file_id):
            raise PyMongoError("GridFS disk corruption or timeout")

    app.dependency_overrides[get_gridfs] = lambda: FaultyGridFS()

    del_res = client.delete(f"/api/notes/{sample_note}")
    assert del_res.status_code == 503
    assert "Failed to clean up linked attachments; note was not deleted" in del_res.json()["detail"]

    # Parent note MUST still exist in database
    get_res = client.get(f"/api/notes/{sample_note}")
    assert get_res.status_code == 200
    assert get_res.json()["id"] == sample_note


def test_upload_attachment_corrupted_structural_content_rejected(client, sample_note):
    """Verify that a file with valid JPEG magic header but corrupted payload is rejected with 415."""
    corrupted_jpg = b"\xff\xd8\xff\xe0\x00\x10JFIF\x00corrupted_non_image_payload_here"
    response = client.post(
        f"/api/notes/{sample_note}/attachments",
        files={"file": ("fake.jpg", corrupted_jpg, "image/jpeg")},
    )
    assert response.status_code == 415
    assert "Corrupted or structurally invalid image payload" in response.json()["detail"]


def test_upload_attachment_metadata_failure_cleans_up_gridfs_file(client, sample_note, fake_fs, fake_db):
    """Verify that if metadata insert fails, the created GridFS binary is cleaned up."""
    # Configure attachments collection to fail on insert_one
    original_insert = fake_db["attachments"].insert_one

    def failing_insert(doc):
        raise PyMongoError("Database disk failure during metadata insert")

    fake_db["attachments"].insert_one = failing_insert

    response = client.post(
        f"/api/notes/{sample_note}/attachments",
        files={"file": ("pic.jpg", SAMPLE_JPEG, "image/jpeg")},
    )
    assert response.status_code == 503
    # Verify that fake_fs has 0 orphaned files
    assert len(fake_fs.files) == 0

    fake_db["attachments"].insert_one = original_insert


def test_cascading_deletion_retry_after_partial_failure(client, sample_note, fake_fs, fake_db):
    """Verify partial failure during cascade delete preserves parent note and can be retried safely."""
    # Upload 2 attachments
    res1 = client.post(
        f"/api/notes/{sample_note}/attachments",
        files={"file": ("pic1.jpg", SAMPLE_JPEG, "image/jpeg")},
    )
    res2 = client.post(
        f"/api/notes/{sample_note}/attachments",
        files={"file": ("pic2.png", SAMPLE_PNG, "image/png")},
    )
    att1_id = res1.json()["id"]
    att2_id = res2.json()["id"]

    assert len(fake_fs.files) == 2
    assert len(fake_db["attachments"].docs) == 2

    # Make the second deletion fail in GridFS
    original_delete = fake_fs.delete
    delete_call_count = 0

    def partial_fail_delete(file_id):
        nonlocal delete_call_count
        delete_call_count += 1
        if delete_call_count == 2:
            raise PyMongoError("Transient network failure on second file delete")
        original_delete(file_id)

    fake_fs.delete = partial_fail_delete

    # Attempt deletion -> should fail with 503
    del_res = client.delete(f"/api/notes/{sample_note}")
    assert del_res.status_code == 503

    # Parent note MUST still exist
    assert client.get(f"/api/notes/{sample_note}").status_code == 200

    # Attachment 1 was cleaned up, attachment 2 remains; does NOT falsely claim all attachments intact
    remaining_atts = client.get(f"/api/notes/{sample_note}/attachments").json()
    assert len(remaining_atts) == 1
    assert remaining_atts[0]["id"] == att2_id

    # Restore healthy delete and retry
    fake_fs.delete = original_delete
    retry_res = client.delete(f"/api/notes/{sample_note}")
    assert retry_res.status_code == 204

    # Now parent note and all attachments are completely gone
    assert client.get(f"/api/notes/{sample_note}").status_code == 404
    assert len(fake_fs.files) == 0
    assert len(fake_db["attachments"].docs) == 0

