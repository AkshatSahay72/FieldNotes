import logging
from typing import Optional
from fastapi import Request, HTTPException, status, Depends
from pymongo import MongoClient, DESCENDING, ASCENDING
from pymongo.database import Database
from pymongo.errors import PyMongoError
import gridfs
from gridfs import GridFS

from app.config import Settings

logger = logging.getLogger(__name__)


def create_mongo_client(settings: Settings) -> MongoClient:
    """Create and return a configured PyMongo MongoClient.
    
    Uses explicit serverSelectionTimeoutMS so unresponsive connections
    fail fast during health checks and startup rather than blocking indefinitely.
    Connection is deferred until the first command is executed.
    """
    return MongoClient(
        settings.mongodb_uri,
        serverSelectionTimeoutMS=settings.mongodb_server_selection_timeout_ms,
        connect=False,
    )


def ping_database(client: Optional[MongoClient]) -> bool:
    """Verify MongoDB connectivity by executing the admin ping command.
    
    Returns True if the ping succeeds, or False if the connection fails or client is None.
    Internal exception details, URIs, and credentials are never leaked.
    """
    if client is None:
        return False
    try:
        client.admin.command("ping")
        return True
    except PyMongoError as err:
        logger.warning("Database ping failed: %s", type(err).__name__)
        return False
    except Exception as err:
        logger.warning("Unexpected error during database ping: %s", type(err).__name__)
        return False


def close_mongo_client(client: Optional[MongoClient]) -> None:
    """Safely close the PyMongo client connection pool."""
    if client is not None:
        try:
            client.close()
        except Exception as err:
            logger.warning("Error closing MongoDB client: %s", type(err).__name__)


def init_db_indexes(db: Optional[Database]) -> None:
    """Create justified indexes on MongoDB collections.
    
    Index justifications:
    - notes.created_at (DESCENDING): The 'GET /api/notes' endpoint retrieves
      notes ordered by newest first (created_at DESC). Creating a B-tree index
      on this field avoids memory-intensive in-memory sort stages and ensures
      efficient index-covered scans as notes volume scales.
    - attachments.note_id (ASCENDING): All attachment operations (listing,
      lookup, and cascading deletion) query by parent note_id. Indexing note_id
      ensures fast lookups without full-collection scans.
    """
    if db is None:
        return
    try:
        db["notes"].create_index(
            [("created_at", DESCENDING)],
            name="idx_notes_created_at_desc",
        )
        db["attachments"].create_index(
            [("note_id", ASCENDING)],
            name="idx_attachments_note_id",
        )
        logger.info("MongoDB indexes on notes and attachments created/verified.")
    except Exception as err:
        logger.warning("Could not initialize database indexes: %s", type(err).__name__)


def get_database(request: Request) -> Database:
    """FastAPI dependency to retrieve the active MongoDB database from application state.
    
    Raises HTTP 503 if the database client is not initialized or unavailable.
    """
    db = getattr(request.app.state, "db", None)
    if db is None:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Database service is currently unavailable",
        )
    return db


def get_gridfs(db: Database = Depends(get_database)) -> GridFS:
    """FastAPI dependency to retrieve the GridFS instance for the active database."""
    return gridfs.GridFS(db)
