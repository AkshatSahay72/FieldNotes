import logging
from typing import Optional
from pymongo import MongoClient
from pymongo.errors import PyMongoError
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
