from unittest.mock import MagicMock
from pymongo.errors import ConnectionFailure, ServerSelectionTimeoutError
from app.config import Settings
from app.db import create_mongo_client, ping_database, close_mongo_client


def test_create_mongo_client_configuration():
    """Verify create_mongo_client sets serverSelectionTimeoutMS without connecting immediately."""
    settings = Settings(
        MONGODB_URI="mongodb://localhost:27017",
        MONGODB_SERVER_SELECTION_TIMEOUT_MS=1500,
        _env_file=None,
    )
    client = create_mongo_client(settings)
    assert client.options.server_selection_timeout == 1.5  # PyMongo stores timeout in seconds internally
    client.close()


def test_ping_database_success():
    """Verify ping_database returns True when admin.command('ping') succeeds."""
    mock_client = MagicMock()
    mock_client.admin.command.return_value = {"ok": 1.0}

    assert ping_database(mock_client) is True
    mock_client.admin.command.assert_called_once_with("ping")


def test_ping_database_connection_failure():
    """Verify ping_database safely returns False when ConnectionFailure is raised."""
    mock_client = MagicMock()
    mock_client.admin.command.side_effect = ConnectionFailure("Cluster unreachable")

    assert ping_database(mock_client) is False


def test_ping_database_server_selection_timeout():
    """Verify ping_database safely returns False when ServerSelectionTimeoutError is raised."""
    mock_client = MagicMock()
    mock_client.admin.command.side_effect = ServerSelectionTimeoutError("Server selection timed out")

    assert ping_database(mock_client) is False


def test_ping_database_none_client():
    """Verify ping_database returns False when client is None without error."""
    assert ping_database(None) is False


def test_close_mongo_client_safely_handles_client_and_none():
    """Verify close_mongo_client handles both valid client and None safely."""
    mock_client = MagicMock()
    close_mongo_client(mock_client)
    mock_client.close.assert_called_once()

    # Must not raise when client is None
    close_mongo_client(None)


def test_init_db_indexes():
    """Verify init_db_indexes creates created_at, tags, text, and attachment indexes."""
    from app.db import init_db_indexes

    mock_notes = MagicMock()
    mock_attachments = MagicMock()
    mock_db = {"notes": mock_notes, "attachments": mock_attachments}

    init_db_indexes(mock_db)
    assert mock_notes.create_index.call_count == 3
    notes_calls = mock_notes.create_index.call_args_list
    assert notes_calls[0] == (([("created_at", -1)],), {"name": "idx_notes_created_at_desc"})
    assert notes_calls[1] == (([("tags", 1)],), {"name": "idx_notes_tags"})
    assert notes_calls[2] == (([("title", "text"), ("content", "text")],), {"name": "idx_notes_text"})

    mock_attachments.create_index.assert_called_once_with(
        [("note_id", 1)],
        name="idx_attachments_note_id",
    )

    # Should handle None gracefully
    init_db_indexes(None)


