from copy import deepcopy
from datetime import datetime, timezone
from bson import ObjectId
import pytest

from app.services.embedding import EmbeddingService, InferenceError
from scripts.backfill_embeddings import backfill_notes


class FakeBackfillCursor:
    """Simulates PyMongo cursor with batch_size and limit chaining."""

    def __init__(self, docs):
        self._docs = docs
        self._limit = None

    def batch_size(self, size):
        return self

    def limit(self, limit):
        self._limit = limit
        return self

    def __iter__(self):
        docs_to_yield = self._docs[:self._limit] if self._limit else self._docs
        return iter([deepcopy(d) for d in docs_to_yield])


class FakeBackfillCollection:
    """In-memory collection tailored for backfill testing."""

    def __init__(self, docs_list=None):
        self.docs = {}
        if docs_list:
            for d in docs_list:
                oid = d.get("_id") or ObjectId()
                d["_id"] = oid
                self.docs[oid] = deepcopy(d)
        self.simulate_concurrency_conflict = False

    def find(self, filter_dict, projection=None):
        matched = []
        for doc in self.docs.values():
            # Check filter conditions
            or_conditions = filter_dict.get("$or", [])
            matches_or = False
            for cond in or_conditions:
                if "embedding" in cond and cond["embedding"] == {"$exists": False}:
                    if "embedding" not in doc:
                        matches_or = True
                elif "embedding" in cond and cond["embedding"] is None:
                    if doc.get("embedding") is None:
                        matches_or = True
                elif "embedding_model" in cond and cond["embedding_model"] == {"$exists": False}:
                    if "embedding_model" not in doc:
                        matches_or = True
                elif "embedding_model" in cond and "$ne" in cond["embedding_model"]:
                    target = cond["embedding_model"]["$ne"]
                    if doc.get("embedding_model") != target:
                        matches_or = True

            if matches_or:
                matched.append(doc)

        return FakeBackfillCursor(matched)

    def update_one(self, filter_dict, update_dict):
        oid = filter_dict.get("_id")
        doc = self.docs.get(oid)

        class Result:
            matched_count = 0
            modified_count = 0

        res = Result()
        if not doc:
            return res

        if self.simulate_concurrency_conflict:
            # Simulate that the document changed concurrently (e.g. updated_at changed)
            return res

        if "updated_at" in filter_dict:
            expected_updated_at = filter_dict["updated_at"]
            if expected_updated_at == {"$exists": False}:
                if "updated_at" in doc and doc["updated_at"] is not None:
                    return res
            elif doc.get("updated_at") != expected_updated_at:
                return res

        set_fields = update_dict.get("$set", {})
        doc.update(set_fields)
        res.matched_count = 1
        res.modified_count = 1
        return res


class FakeBackfillDatabase:
    def __init__(self, collection):
        self._collection = collection

    def __getitem__(self, name):
        if name == "notes":
            return self._collection
        raise KeyError(name)


class DeterministicFakeEmbeddingService(EmbeddingService):
    """Deterministic embedding service test double."""

    def __init__(self, model_name="sentence-transformers/all-MiniLM-L6-v2", fail_on_id=None):
        super().__init__(model_name=model_name)
        self.fail_on_id = fail_on_id

    def generate_embedding(self, text: str):
        if not text or not text.strip():
            raise ValueError("Empty text")
        if self.fail_on_id and self.fail_on_id in text:
            raise InferenceError("Mock inference failure on specific document")
        val = 1.0 / (384 ** 0.5)
        return [val] * 384


def test_backfill_updates_notes_missing_embeddings():
    """Verify notes without embeddings are processed and updated with vector and model."""
    now = datetime.now(timezone.utc)
    notes_data = [
        {"title": "Note 1", "content": "Content 1", "updated_at": now},
        {"title": "Note 2", "content": "Content 2", "updated_at": now},
    ]
    col = FakeBackfillCollection(notes_data)
    db = FakeBackfillDatabase(col)
    service = DeterministicFakeEmbeddingService()

    counts = backfill_notes(db=db, embedding_service=service)

    assert counts["processed"] == 2
    assert counts["updated"] == 2
    assert counts["skipped"] == 0
    assert counts["failed"] == 0

    for doc in col.docs.values():
        assert "embedding" in doc
        assert len(doc["embedding"]) == 384
        assert doc["embedding_model"] == "sentence-transformers/all-MiniLM-L6-v2"


def test_backfill_idempotency_skips_up_to_date_notes():
    """Verify backfill does not process or modify notes that already have current embeddings."""
    now = datetime.now(timezone.utc)
    notes_data = [
        {
            "title": "Already Embedded Note",
            "content": "Content",
            "embedding": [0.1] * 384,
            "embedding_model": "sentence-transformers/all-MiniLM-L6-v2",
            "updated_at": now,
        }
    ]
    col = FakeBackfillCollection(notes_data)
    db = FakeBackfillDatabase(col)
    service = DeterministicFakeEmbeddingService()

    counts = backfill_notes(db=db, embedding_service=service)

    assert counts["processed"] == 0
    assert counts["updated"] == 0
    assert counts["skipped"] == 0
    assert counts["failed"] == 0


def test_backfill_updates_notes_with_outdated_embedding_model():
    """Verify notes with older embedding_model are detected and updated."""
    now = datetime.now(timezone.utc)
    notes_data = [
        {
            "title": "Old Model Note",
            "content": "Content",
            "embedding": [0.1] * 384,
            "embedding_model": "old-deprecated-model-v1",
            "updated_at": now,
        }
    ]
    col = FakeBackfillCollection(notes_data)
    db = FakeBackfillDatabase(col)
    service = DeterministicFakeEmbeddingService()

    counts = backfill_notes(db=db, embedding_service=service)

    assert counts["processed"] == 1
    assert counts["updated"] == 1
    doc = list(col.docs.values())[0]
    assert doc["embedding_model"] == "sentence-transformers/all-MiniLM-L6-v2"


def test_backfill_dry_run_mode_does_not_modify_database():
    """Verify --dry-run computes embeddings but performs zero database writes."""
    now = datetime.now(timezone.utc)
    notes_data = [{"title": "Dry Run Note", "content": "Content", "updated_at": now}]
    col = FakeBackfillCollection(notes_data)
    db = FakeBackfillDatabase(col)
    service = DeterministicFakeEmbeddingService()

    counts = backfill_notes(db=db, embedding_service=service, dry_run=True)

    assert counts["processed"] == 1
    assert counts["updated"] == 1
    assert counts["skipped"] == 0
    assert counts["failed"] == 0

    doc = list(col.docs.values())[0]
    assert "embedding" not in doc
    assert "embedding_model" not in doc


def test_backfill_concurrency_protection_skips_modified_notes():
    """Verify conditional update skips note if updated_at changed during inference."""
    now = datetime.now(timezone.utc)
    notes_data = [{"title": "Concurrent Note", "content": "Content", "updated_at": now}]
    col = FakeBackfillCollection(notes_data)
    col.simulate_concurrency_conflict = True
    db = FakeBackfillDatabase(col)
    service = DeterministicFakeEmbeddingService()

    counts = backfill_notes(db=db, embedding_service=service)

    assert counts["processed"] == 1
    assert counts["updated"] == 0
    assert counts["skipped"] == 1
    assert counts["failed"] == 0


def test_backfill_handles_missing_updated_at_field():
    """Verify notes without updated_at are updated matching {$exists: False}."""
    notes_data = [{"title": "Legacy Note", "content": "No updated_at key"}]
    col = FakeBackfillCollection(notes_data)
    db = FakeBackfillDatabase(col)
    service = DeterministicFakeEmbeddingService()

    counts = backfill_notes(db=db, embedding_service=service)

    assert counts["processed"] == 1
    assert counts["updated"] == 1
    assert counts["skipped"] == 0
    assert counts["failed"] == 0

    doc = list(col.docs.values())[0]
    assert "embedding" in doc
    assert doc["embedding_model"] == "sentence-transformers/all-MiniLM-L6-v2"


def test_backfill_individual_failure_continues_processing():
    """Verify failure on one note does not abort remaining notes."""
    now = datetime.now(timezone.utc)
    notes_data = [
        {"title": "FAIL_THIS Note", "content": "FAIL_THIS", "updated_at": now},
        {"title": "Good Note", "content": "Valid content", "updated_at": now},
    ]
    col = FakeBackfillCollection(notes_data)
    db = FakeBackfillDatabase(col)
    service = DeterministicFakeEmbeddingService(fail_on_id="FAIL_THIS")

    counts = backfill_notes(db=db, embedding_service=service)

    assert counts["processed"] == 2
    assert counts["updated"] == 1
    assert counts["failed"] == 1


def test_backfill_cli_main_success(monkeypatch, capsys):
    """Verify main() runs with --dry-run and returns exit code 0 when all records succeed."""
    from scripts.backfill_embeddings import main

    monkeypatch.setattr("sys.argv", ["backfill_embeddings.py", "--dry-run"])

    # Mock client and db
    now = datetime.now(timezone.utc)
    col = FakeBackfillCollection([{"title": "Note", "content": "Content", "updated_at": now}])
    db = FakeBackfillDatabase(col)

    class MockClient:
        def __getitem__(self, name):
            return db
        def close(self):
            pass

    monkeypatch.setattr("scripts.backfill_embeddings.create_mongo_client", lambda s: MockClient())
    monkeypatch.setattr("scripts.backfill_embeddings.close_mongo_client", lambda c: None)
    monkeypatch.setattr("scripts.backfill_embeddings.get_embedding_service", lambda s: DeterministicFakeEmbeddingService())

    exit_code = main()
    assert exit_code == 0

    captured = capsys.readouterr()
    assert "Backfill Summary" in captured.out
    assert "Dry Run:   True" in captured.out
    assert "Processed: 1" in captured.out
    assert "Updated:   1 (simulated)" in captured.out
    assert "Failed:    0" in captured.out


def test_backfill_cli_main_returns_nonzero_on_failure(monkeypatch, capsys):
    """Verify main() exits with 1 if any record fails."""
    from scripts.backfill_embeddings import main

    monkeypatch.setattr("sys.argv", ["backfill_embeddings.py"])

    now = datetime.now(timezone.utc)
    col = FakeBackfillCollection([{"title": "Fail Note", "content": "FAIL_ME", "updated_at": now}])
    db = FakeBackfillDatabase(col)

    class MockClient:
        def __getitem__(self, name):
            return db
        def close(self):
            pass

    monkeypatch.setattr("scripts.backfill_embeddings.create_mongo_client", lambda s: MockClient())
    monkeypatch.setattr("scripts.backfill_embeddings.close_mongo_client", lambda c: None)
    monkeypatch.setattr("scripts.backfill_embeddings.get_embedding_service", lambda s: DeterministicFakeEmbeddingService(fail_on_id="FAIL_ME"))

    exit_code = main()
    assert exit_code == 1

    captured = capsys.readouterr()
    assert "Failed:    1" in captured.out
