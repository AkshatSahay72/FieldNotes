from copy import deepcopy
from datetime import datetime, timezone, timedelta
from bson import ObjectId
import pytest
from fastapi.testclient import TestClient
from pymongo.errors import PyMongoError

from app.main import app
from app.db import get_database
from app.config import Settings, get_settings
from app.schemas import (
    AnalyticsOverview,
    DailyActivity,
    NoteAttachmentSummary,
    TagCount,
)
from app.routes.analytics import (
    build_tag_distribution_pipeline,
    build_note_activity_pipeline,
    build_attachment_counts_pipeline,
)


class FakeCollection:
    """In-memory collection simulating PyMongo count_documents and aggregate."""

    def __init__(self, name="", db=None):
        self.name = name
        self.db = db
        self.docs = {}
        self.error_on_next = None

    def insert_one(self, doc):
        oid = doc.get("_id") or ObjectId()
        stored = deepcopy(doc)
        stored["_id"] = oid
        self.docs[oid] = stored
        return oid

    def count_documents(self, filter_dict=None):
        if self.error_on_next:
            err = self.error_on_next
            self.error_on_next = None
            raise err
        if not filter_dict:
            return len(self.docs)
        if "tags" in filter_dict:
            return sum(
                1 for d in self.docs.values()
                if isinstance(d.get("tags"), list)
                and any(isinstance(t, str) and t.strip() for t in d.get("tags"))
            )
        return len(self.docs)

    def aggregate(self, pipeline):
        if self.error_on_next:
            err = self.error_on_next
            self.error_on_next = None
            raise err

        # Determine which pipeline is being evaluated based on first stage
        first_stage = pipeline[0] if pipeline else {}

        # 1. Tag distribution pipeline ($unwind: "$tags")
        if "$unwind" in first_stage and first_stage["$unwind"] == "$tags":
            tag_counts = {}
            for doc in self.docs.values():
                tags = doc.get("tags")
                if isinstance(tags, list):
                    for t in tags:
                        if isinstance(t, str) and t.strip():
                            tag_counts[t] = tag_counts.get(t, 0) + 1
            # Sort: count DESC, tag ASC
            sorted_tags = sorted(tag_counts.items(), key=lambda item: (-item[1], item[0]))
            return [{"tag": t, "count": c} for t, c in sorted_tags]

        # 2. Activity pipeline (starts with $match on created_at or $group)
        if (
            "$match" in first_stage
            and "created_at" in first_stage["$match"]
        ) or "$group" in first_stage:
            daily_counts = {}
            for doc in self.docs.values():
                created = doc.get("created_at")
                if created and isinstance(created, datetime):
                    day_str = created.astimezone(timezone.utc).strftime("%Y-%m-%d")
                    daily_counts[day_str] = daily_counts.get(day_str, 0) + 1
            sorted_days = sorted(daily_counts.items(), key=lambda item: item[0])
            return [{"date": d, "count": c} for d, c in sorted_days]

        # 3. Attachment counts pipeline ($lookup from attachments)
        if "$lookup" in first_stage:
            include_zero = True
            # Check if there is an explicit $match filter for attachment_count > 0
            for stage in pipeline:
                if "$match" in stage and "attachment_count" in stage["$match"]:
                    include_zero = False

            results = []
            att_collection = self.db["attachments"] if self.db else None
            for doc in self.docs.values():
                note_oid = doc["_id"]
                count = 0
                if att_collection:
                    count = sum(
                        1 for a in att_collection.docs.values()
                        if a.get("note_id") == note_oid
                    )
                if count > 0 or include_zero:
                    results.append({
                        "note_id": str(note_oid),
                        "title": doc.get("title", ""),
                        "attachment_count": count,
                    })

            # Sort: count DESC, title ASC, note_id ASC
            results.sort(key=lambda x: (-x["attachment_count"], x["title"], x["note_id"]))
            return results

        return []


class FakeDatabase:
    """In-memory database double simulating PyMongo Database."""

    def __init__(self):
        self.collections = {
            "notes": FakeCollection("notes", self),
            "attachments": FakeCollection("attachments", self),
        }

    def __getitem__(self, name):
        if name not in self.collections:
            self.collections[name] = FakeCollection(name, self)
        return self.collections[name]


@pytest.fixture
def fake_db():
    return FakeDatabase()


@pytest.fixture
def client(fake_db):
    app.dependency_overrides[get_database] = lambda: fake_db
    app.dependency_overrides[get_settings] = lambda: Settings(
        MONGODB_URI="mongodb://fake:27017",
        DATABASE_NAME="fieldnote_test_db",
        APP_ENV="testing",
    )
    with TestClient(app) as test_client:
        yield test_client
    app.dependency_overrides.clear()


# ==============================================================================
# Pipeline Construction Unit Tests
# ==============================================================================

def test_build_tag_distribution_pipeline():
    """Verify tag distribution pipeline uses canonical aggregation stages."""
    pipeline = build_tag_distribution_pipeline()
    assert len(pipeline) == 5
    assert "$unwind" in pipeline[0]
    assert pipeline[0]["$unwind"] == "$tags"
    assert "$match" in pipeline[1]
    assert pipeline[1]["$match"] == {"tags": {"$type": "string", "$regex": r"\S"}}
    assert "$group" in pipeline[2]
    assert pipeline[2]["$group"] == {"_id": "$tags", "count": {"$sum": 1}}
    assert "$sort" in pipeline[3]
    assert pipeline[3]["$sort"] == {"count": -1, "_id": 1}
    assert "$project" in pipeline[4]
    assert pipeline[4]["$project"] == {"_id": 0, "tag": "$_id", "count": 1}


def test_build_note_activity_pipeline():
    """Verify daily note activity pipeline uses $dateToString in UTC."""
    pipeline = build_note_activity_pipeline()
    assert len(pipeline) == 4
    assert "$match" in pipeline[0]
    assert pipeline[0]["$match"] == {"created_at": {"$type": "date"}}
    assert "$group" in pipeline[1]
    date_to_string = pipeline[1]["$group"]["_id"]["$dateToString"]
    assert date_to_string["format"] == "%Y-%m-%d"
    assert date_to_string["date"] == "$created_at"
    assert date_to_string["timezone"] == "UTC"
    assert "$sort" in pipeline[2]
    assert pipeline[2]["$sort"] == {"_id": 1}
    assert "$project" in pipeline[3]
    assert pipeline[3]["$project"] == {"_id": 0, "date": "$_id", "count": 1}


def test_build_attachment_counts_pipeline():
    """Verify attachment counts pipeline uses $lookup and handles include_zero."""
    # include_zero = True
    p_with_zero = build_attachment_counts_pipeline(include_zero=True)
    assert len(p_with_zero) == 3
    assert "$lookup" in p_with_zero[0]
    assert p_with_zero[0]["$lookup"]["from"] == "attachments"
    assert p_with_zero[0]["$lookup"]["localField"] == "_id"
    assert p_with_zero[0]["$lookup"]["foreignField"] == "note_id"
    assert "$project" in p_with_zero[1]
    assert p_with_zero[1]["$project"]["attachment_count"] == {"$size": "$attachments"}
    assert "$sort" in p_with_zero[2]

    # include_zero = False
    p_no_zero = build_attachment_counts_pipeline(include_zero=False)
    assert len(p_no_zero) == 4
    assert "$match" in p_no_zero[2]
    assert p_no_zero[2]["$match"] == {"attachment_count": {"$gt": 0}}


# ==============================================================================
# Endpoint 1: Research Overview Tests
# ==============================================================================

def test_overview_empty_collections(client):
    """Verify overview returns 0s when collections are empty."""
    res = client.get("/api/analytics/overview")
    assert res.status_code == 200
    data = res.json()
    assert data == {
        "total_notes": 0,
        "total_attachments": 0,
        "notes_with_tags": 0,
    }
    # Validate against Pydantic schema
    AnalyticsOverview(**data)


def test_overview_populated_collections(client, fake_db):
    """Verify overview counts notes, attachments, and notes containing tags."""
    # Insert notes
    note1_id = fake_db["notes"].insert_one({
        "title": "Note 1",
        "content": "c1",
        "tags": ["soil", "water"],
        "created_at": datetime.now(timezone.utc),
    })
    note2_id = fake_db["notes"].insert_one({
        "title": "Note 2",
        "content": "c2",
        "tags": [],
        "created_at": datetime.now(timezone.utc),
    })
    note3_id = fake_db["notes"].insert_one({
        "title": "Note 3",
        "content": "c3",
        "tags": ["canopy"],
        "created_at": datetime.now(timezone.utc),
    })

    # Insert attachments
    fake_db["attachments"].insert_one({
        "note_id": note1_id,
        "filename": "soil.jpg",
        "content_type": "image/jpeg",
        "file_size": 1024,
    })
    fake_db["attachments"].insert_one({
        "note_id": note1_id,
        "filename": "soil2.jpg",
        "content_type": "image/jpeg",
        "file_size": 2048,
    })

    res = client.get("/api/analytics/overview")
    assert res.status_code == 200
    data = res.json()
    assert data["total_notes"] == 3
    assert data["total_attachments"] == 2
    assert data["notes_with_tags"] == 2


def test_overview_and_tags_consistent_tag_definition(client, fake_db):
    """Regression test: verify overview notes_with_tags and tag distribution share the same tag definition.
    
    Notes containing only empty strings, whitespace, or null tags must NOT be counted
    as 'notes_with_tags' and must NOT appear in tag distribution.
    """
    fake_db["notes"].insert_one({"title": "Empty array", "content": "c", "tags": []})
    fake_db["notes"].insert_one({"title": "Empty string tag", "content": "c", "tags": [""]})
    fake_db["notes"].insert_one({"title": "Whitespace tag", "content": "c", "tags": ["   "]})
    fake_db["notes"].insert_one({"title": "Null tag", "content": "c", "tags": [None]})
    fake_db["notes"].insert_one({"title": "Valid note 1", "content": "c", "tags": ["soil"]})
    fake_db["notes"].insert_one({"title": "Valid note 2", "content": "c", "tags": ["", "water"]})
    fake_db["notes"].insert_one({"title": "Missing field note", "content": "c"})

    # 1. Overview check
    res_ov = client.get("/api/analytics/overview")
    assert res_ov.status_code == 200
    ov_data = res_ov.json()
    assert ov_data["total_notes"] == 7
    # Only Valid note 1 and Valid note 2 have at least one non-whitespace tag
    assert ov_data["notes_with_tags"] == 2

    # 2. Tag distribution check
    res_tags = client.get("/api/analytics/tags")
    assert res_tags.status_code == 200
    tag_data = res_tags.json()
    # Only "soil" and "water" should appear
    tag_names = [t["tag"] for t in tag_data]
    assert len(tag_names) == 2
    assert "soil" in tag_names
    assert "water" in tag_names
    assert "" not in tag_names
    assert "   " not in tag_names


def test_overview_database_error_returns_503(client, fake_db):
    """Verify overview handles database exceptions gracefully with 503."""
    fake_db["notes"].error_on_next = PyMongoError("Connection timeout")
    res = client.get("/api/analytics/overview")
    assert res.status_code == 503
    assert res.json()["detail"] == "Database service unavailable"


# ==============================================================================
# Endpoint 2: Tag Distribution Tests
# ==============================================================================

def test_tag_distribution_empty(client):
    """Verify tag distribution returns empty list when no notes exist."""
    res = client.get("/api/analytics/tags")
    assert res.status_code == 200
    assert res.json() == []


def test_tag_distribution_counts_and_deterministic_sort(client, fake_db):
    """Verify tags are counted and sorted by count DESC, tag ASC."""
    fake_db["notes"].insert_one({
        "title": "Note A",
        "content": "c",
        "tags": ["soil", "moisture", "fieldwork"],
        "created_at": datetime.now(timezone.utc),
    })
    fake_db["notes"].insert_one({
        "title": "Note B",
        "content": "c",
        "tags": ["soil", "moisture"],
        "created_at": datetime.now(timezone.utc),
    })
    fake_db["notes"].insert_one({
        "title": "Note C",
        "content": "c",
        "tags": ["soil"],
        "created_at": datetime.now(timezone.utc),
    })
    fake_db["notes"].insert_one({
        "title": "Note D",
        "content": "c",
        "tags": ["agriculture"],
        "created_at": datetime.now(timezone.utc),
    })

    res = client.get("/api/analytics/tags")
    assert res.status_code == 200
    data = res.json()
    # soil=3, moisture=2, agriculture=1, fieldwork=1 (agriculture before fieldwork alphabetically)
    assert len(data) == 4
    assert data[0] == {"tag": "soil", "count": 3}
    assert data[1] == {"tag": "moisture", "count": 2}
    assert data[2] == {"tag": "agriculture", "count": 1}
    assert data[3] == {"tag": "fieldwork", "count": 1}

    # Validate each item against TagCount schema
    for item in data:
        TagCount(**item)


def test_tag_distribution_handles_empty_and_blank_tags(client, fake_db):
    """Verify notes with empty tag arrays or missing tags are not counted as false tags."""
    fake_db["notes"].insert_one({
        "title": "Untagged note",
        "content": "c",
        "tags": [],
        "created_at": datetime.now(timezone.utc),
    })
    fake_db["notes"].insert_one({
        "title": "Missing tags note",
        "content": "c",
        "created_at": datetime.now(timezone.utc),
    })
    fake_db["notes"].insert_one({
        "title": "Blank tag note",
        "content": "c",
        "tags": ["", "soil"],
        "created_at": datetime.now(timezone.utc),
    })

    res = client.get("/api/analytics/tags")
    assert res.status_code == 200
    data = res.json()
    assert len(data) == 1
    assert data[0] == {"tag": "soil", "count": 1}


def test_tag_distribution_preserves_case_sensitivity(client, fake_db):
    """Verify tag distribution groups tags case-sensitively without altering stored casing."""
    fake_db["notes"].insert_one({
        "title": "Note 1",
        "content": "c",
        "tags": ["Soil"],
        "created_at": datetime.now(timezone.utc),
    })
    fake_db["notes"].insert_one({
        "title": "Note 2",
        "content": "c",
        "tags": ["soil"],
        "created_at": datetime.now(timezone.utc),
    })

    res = client.get("/api/analytics/tags")
    assert res.status_code == 200
    data = res.json()
    tags = {item["tag"]: item["count"] for item in data}
    assert tags.get("Soil") == 1
    assert tags.get("soil") == 1


def test_tag_distribution_database_error_returns_503(client, fake_db):
    """Verify database exceptions return 503."""
    fake_db["notes"].error_on_next = PyMongoError("Aggregation failed")
    res = client.get("/api/analytics/tags")
    assert res.status_code == 503
    assert res.json()["detail"] == "Database service unavailable"


# ==============================================================================
# Endpoint 3: Daily Activity Tests
# ==============================================================================

def test_daily_activity_empty(client):
    """Verify activity returns empty list when no notes exist."""
    res = client.get("/api/analytics/activity")
    assert res.status_code == 200
    assert res.json() == []


def test_daily_activity_chronological_ordering(client, fake_db):
    """Verify daily note counts are grouped and sorted chronologically ascending."""
    day1 = datetime(2026, 10, 10, 14, 0, 0, tzinfo=timezone.utc)
    day2 = datetime(2026, 10, 11, 9, 30, 0, tzinfo=timezone.utc)
    day2_later = datetime(2026, 10, 11, 18, 45, 0, tzinfo=timezone.utc)
    day3 = datetime(2026, 10, 13, 8, 0, 0, tzinfo=timezone.utc)

    fake_db["notes"].insert_one({"title": "N1", "content": "c", "created_at": day2})
    fake_db["notes"].insert_one({"title": "N2", "content": "c", "created_at": day1})
    fake_db["notes"].insert_one({"title": "N3", "content": "c", "created_at": day3})
    fake_db["notes"].insert_one({"title": "N4", "content": "c", "created_at": day2_later})

    res = client.get("/api/analytics/activity")
    assert res.status_code == 200
    data = res.json()
    assert len(data) == 3
    assert data[0] == {"date": "2026-10-10", "count": 1}
    assert data[1] == {"date": "2026-10-11", "count": 2}
    assert data[2] == {"date": "2026-10-13", "count": 1}

    # Validate each item against DailyActivity schema
    for item in data:
        DailyActivity(**item)


def test_daily_activity_database_error_returns_503(client, fake_db):
    """Verify daily activity database errors return 503."""
    fake_db["notes"].error_on_next = PyMongoError("Date grouping failed")
    res = client.get("/api/analytics/activity")
    assert res.status_code == 503
    assert res.json()["detail"] == "Database service unavailable"


# ==============================================================================
# Endpoint 4: Attachment Counts by Note Tests
# ==============================================================================

def test_attachment_counts_empty(client):
    """Verify attachment counts returns empty list when no notes exist."""
    res = client.get("/api/analytics/attachments")
    assert res.status_code == 200
    assert res.json() == []


def test_attachment_counts_including_and_excluding_zero(client, fake_db):
    """Verify attachment counts per note, testing include_zero True and False."""
    n1_id = fake_db["notes"].insert_one({"title": "Plot Alpha", "content": "c", "created_at": datetime.now(timezone.utc)})
    n2_id = fake_db["notes"].insert_one({"title": "Plot Beta", "content": "c", "created_at": datetime.now(timezone.utc)})
    n3_id = fake_db["notes"].insert_one({"title": "Plot Gamma", "content": "c", "created_at": datetime.now(timezone.utc)})

    # Note 1 has 2 attachments, Note 2 has 1, Note 3 has 0
    fake_db["attachments"].insert_one({"note_id": n1_id, "filename": "a1.jpg"})
    fake_db["attachments"].insert_one({"note_id": n1_id, "filename": "a2.jpg"})
    fake_db["attachments"].insert_one({"note_id": n2_id, "filename": "b1.jpg"})

    # 1. Default (include_zero=True): all 3 notes returned
    res = client.get("/api/analytics/attachments")
    assert res.status_code == 200
    data = res.json()
    assert len(data) == 3
    assert data[0]["note_id"] == str(n1_id)
    assert data[0]["attachment_count"] == 2
    assert data[1]["note_id"] == str(n2_id)
    assert data[1]["attachment_count"] == 1
    assert data[2]["note_id"] == str(n3_id)
    assert data[2]["attachment_count"] == 0

    # Validate against NoteAttachmentSummary schema
    for item in data:
        NoteAttachmentSummary(**item)

    # 2. Exclude zero (include_zero=False): only Note 1 and Note 2 returned
    res_no_zero = client.get("/api/analytics/attachments?include_zero=false")
    assert res_no_zero.status_code == 200
    data_no_zero = res_no_zero.json()
    assert len(data_no_zero) == 2
    assert data_no_zero[0]["note_id"] == str(n1_id)
    assert data_no_zero[1]["note_id"] == str(n2_id)


def test_attachment_counts_database_error_returns_503(client, fake_db):
    """Verify attachment counts database errors return 503."""
    fake_db["notes"].error_on_next = PyMongoError("Lookup failed")
    res = client.get("/api/analytics/attachments")
    assert res.status_code == 503
    assert res.json()["detail"] == "Database service unavailable"
