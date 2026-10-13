"""Unit tests for Atlas Vector Search index provisioning script."""

from unittest.mock import MagicMock, patch
import pytest
from pymongo.errors import PyMongoError
from pymongo.operations import SearchIndexModel

from scripts.provision_vector_index import (
    VECTOR_INDEX_NAME,
    VECTOR_INDEX_TYPE,
    VECTOR_INDEX_DIMENSIONS,
    VECTOR_INDEX_SIMILARITY,
    VECTOR_INDEX_PATH,
    find_search_index,
    get_all_search_indexes,
    wait_for_index_readiness,
    provision_vector_index,
)


def test_find_search_index_found():
    """Verify find_search_index returns the matching index dict."""
    mock_coll = MagicMock()
    mock_coll.list_search_indexes.return_value = [
        {"name": "other_index", "status": "READY"},
        {"name": VECTOR_INDEX_NAME, "status": "READY", "queryable": True},
    ]

    result = find_search_index(mock_coll, VECTOR_INDEX_NAME)
    assert result is not None
    assert result["name"] == VECTOR_INDEX_NAME
    assert result["queryable"] is True


def test_find_search_index_not_found():
    """Verify find_search_index returns None when not present or on error."""
    mock_coll = MagicMock()
    mock_coll.list_search_indexes.return_value = [
        {"name": "other_index", "status": "READY"},
    ]

    result = find_search_index(mock_coll, VECTOR_INDEX_NAME)
    assert result is None

    # When PyMongoError is raised
    mock_coll.list_search_indexes.side_effect = PyMongoError("Index not found")
    result_err = find_search_index(mock_coll, VECTOR_INDEX_NAME)
    assert result_err is None


def test_get_all_search_indexes():
    """Verify get_all_search_indexes returns all listed search indexes."""
    mock_coll = MagicMock()
    expected = [{"name": "idx_1"}, {"name": "idx_2"}]
    mock_coll.list_search_indexes.return_value = expected

    result = get_all_search_indexes(mock_coll)
    assert result == expected


def test_wait_for_index_readiness_immediate_ready():
    """Verify wait_for_index_readiness succeeds when index is already READY and queryable."""
    mock_coll = MagicMock()
    mock_coll.list_search_indexes.return_value = [
        {"name": VECTOR_INDEX_NAME, "status": "READY", "queryable": True, "id": "idx123"}
    ]

    result = wait_for_index_readiness(
        mock_coll,
        VECTOR_INDEX_NAME,
        timeout_seconds=5.0,
        poll_interval_seconds=0.01,
    )
    assert result["status"] == "READY"
    assert result["queryable"] is True


def test_wait_for_index_readiness_failed_status():
    """Verify wait_for_index_readiness raises RuntimeError on FAILED status."""
    mock_coll = MagicMock()
    mock_coll.list_search_indexes.return_value = [
        {"name": VECTOR_INDEX_NAME, "status": "FAILED", "queryable": False}
    ]

    with pytest.raises(RuntimeError, match="entered FAILED status"):
        wait_for_index_readiness(
            mock_coll,
            VECTOR_INDEX_NAME,
            timeout_seconds=5.0,
            poll_interval_seconds=0.01,
        )


def test_wait_for_index_readiness_timeout():
    """Verify wait_for_index_readiness raises TimeoutError when timeout expires."""
    mock_coll = MagicMock()
    mock_coll.list_search_indexes.return_value = [
        {"name": VECTOR_INDEX_NAME, "status": "BUILDING", "queryable": False}
    ]

    with pytest.raises(TimeoutError, match="Timed out after"):
        wait_for_index_readiness(
            mock_coll,
            VECTOR_INDEX_NAME,
            timeout_seconds=0.05,
            poll_interval_seconds=0.02,
        )


def test_provision_vector_index_check_only_not_existing():
    """Verify provision_vector_index with check_only=True does not create any index."""
    mock_db = MagicMock()
    mock_coll = mock_db["notes"]
    mock_coll.count_documents.return_value = 0
    mock_coll.list_search_indexes.return_value = []

    result = provision_vector_index(mock_db, check_only=True)
    assert result["action"] == "check_only"
    assert result["exists"] is False
    assert result["index"] is None
    assert mock_coll.create_search_index.call_count == 0


def test_provision_vector_index_check_only_existing():
    """Verify provision_vector_index with check_only=True detects existing index without modification."""
    mock_db = MagicMock()
    mock_coll = mock_db["notes"]
    mock_coll.count_documents.return_value = 0
    mock_coll.list_search_indexes.return_value = [
        {"name": VECTOR_INDEX_NAME, "status": "READY", "queryable": True}
    ]

    result = provision_vector_index(mock_db, check_only=True)
    assert result["action"] == "check_only"
    assert result["exists"] is True
    assert result["index"]["name"] == VECTOR_INDEX_NAME
    assert mock_coll.create_search_index.call_count == 0


def test_provision_vector_index_refuses_duplicate():
    """Verify provision_vector_index refuses to create a duplicate if index already exists."""
    mock_db = MagicMock()
    mock_coll = mock_db["notes"]
    mock_coll.count_documents.return_value = 0
    mock_coll.list_search_indexes.return_value = [
        {"name": VECTOR_INDEX_NAME, "status": "READY", "queryable": True}
    ]

    result = provision_vector_index(mock_db, check_only=False)
    assert result["action"] == "already_exists"
    assert result["exists"] is True
    assert mock_coll.create_search_index.call_count == 0


def test_provision_vector_index_creates_and_polls_successfully():
    """Verify provision_vector_index creates index with exact specifications and polls until ready."""
    mock_db = MagicMock()
    mock_coll = mock_db["notes"]
    mock_coll.count_documents.return_value = 0

    # First call: no search index
    # After creation: returns READY search index
    mock_coll.list_search_indexes.side_effect = [
        [],  # initial list_search_indexes
        [],  # find_search_index check
        [{"name": VECTOR_INDEX_NAME, "status": "READY", "queryable": True}],  # wait_for_index_readiness
    ]
    mock_coll.create_search_index.return_value = VECTOR_INDEX_NAME

    result = provision_vector_index(
        mock_db,
        timeout_seconds=5.0,
        poll_interval_seconds=0.01,
        check_only=False,
    )

    assert result["action"] == "created"
    assert result["exists"] is True
    assert result["index"]["status"] == "READY"
    assert result["index"]["queryable"] is True
    assert mock_coll.create_search_index.call_count == 1

    created_model = mock_coll.create_search_index.call_args[1]["model"]
    assert isinstance(created_model, SearchIndexModel)
    assert created_model.document["name"] == VECTOR_INDEX_NAME
    assert created_model.document["type"] == VECTOR_INDEX_TYPE
    assert created_model.document["definition"]["fields"][0]["path"] == VECTOR_INDEX_PATH
    assert created_model.document["definition"]["fields"][0]["numDimensions"] == VECTOR_INDEX_DIMENSIONS
    assert created_model.document["definition"]["fields"][0]["similarity"] == VECTOR_INDEX_SIMILARITY
