"""Atlas Vector Search Index Provisioning Script for Fieldnote.

Provisions and verifies the 'idx_notes_vector' Vector Search index on the
MongoDB Atlas 'notes' collection.

Index Specification:
    - Name: idx_notes_vector
    - Type: vectorSearch
    - Field path: embedding
    - Field type: vector
    - Dimensions: 384
    - Similarity: cosine

Usage:
    python scripts/provision_vector_index.py [--check-only] [--timeout 300] [--poll-interval 5]
"""

import argparse
import logging
import sys
import time
from pathlib import Path
from typing import Any, Dict, List, Optional

# Ensure project root is on sys.path for direct script execution
_project_root = str(Path(__file__).resolve().parent.parent)
if _project_root not in sys.path:
    sys.path.insert(0, _project_root)

from pymongo.collection import Collection
from pymongo.database import Database
from pymongo.errors import PyMongoError
from pymongo.operations import SearchIndexModel

from app.config import get_settings
from app.db import create_mongo_client, close_mongo_client

# Logging configuration
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S",
)
logger = logging.getLogger("provision_vector_index")

VECTOR_INDEX_NAME = "idx_notes_vector"
VECTOR_INDEX_TYPE = "vectorSearch"
VECTOR_INDEX_DIMENSIONS = 384
VECTOR_INDEX_SIMILARITY = "cosine"
VECTOR_INDEX_PATH = "embedding"

VECTOR_INDEX_DEFINITION = {
    "fields": [
        {
            "type": "vector",
            "path": VECTOR_INDEX_PATH,
            "numDimensions": VECTOR_INDEX_DIMENSIONS,
            "similarity": VECTOR_INDEX_SIMILARITY,
        }
    ]
}


def find_search_index(
    collection: Collection,
    index_name: str,
) -> Optional[Dict[str, Any]]:
    """Look up a search index by name on the specified collection.
    
    Returns the index metadata document if found, None otherwise.
    """
    try:
        cursor = collection.list_search_indexes(index_name)
        indexes = list(cursor)
        for idx in indexes:
            if idx.get("name") == index_name:
                return idx
        return None
    except PyMongoError as exc:
        # Atlas might raise an error if index does not exist or list fails
        logger.debug("list_search_indexes(%s) returned error: %s", index_name, exc)
        return None


def get_all_search_indexes(collection: Collection) -> List[Dict[str, Any]]:
    """Return all search indexes on the collection."""
    try:
        return list(collection.list_search_indexes())
    except PyMongoError as exc:
        logger.error("Failed to list search indexes: %s", exc)
        raise


def wait_for_index_readiness(
    collection: Collection,
    index_name: str,
    timeout_seconds: float = 300.0,
    poll_interval_seconds: float = 5.0,
) -> Dict[str, Any]:
    """Poll search index metadata until status is READY and queryable is True.
    
    Raises:
        TimeoutError: If the index does not become READY within timeout_seconds.
        RuntimeError: If the index reports a FAILED status.
    """
    start_time = time.time()
    logger.info(
        "Waiting for search index '%s' to become READY (timeout: %.0fs, poll interval: %.1fs)...",
        index_name,
        timeout_seconds,
        poll_interval_seconds,
    )

    last_status = None
    last_queryable = None

    while True:
        elapsed = time.time() - start_time
        if elapsed > timeout_seconds:
            raise TimeoutError(
                f"Timed out after {elapsed:.1f}s waiting for index '{index_name}' "
                f"to reach READY status (last status: {last_status}, queryable: {last_queryable})."
            )

        idx_info = find_search_index(collection, index_name)
        if idx_info:
            status = idx_info.get("status")
            queryable = idx_info.get("queryable", False)

            if status != last_status or queryable != last_queryable:
                logger.info(
                    "Elapsed: %.1fs | Index '%s' | status: %s | queryable: %s",
                    elapsed,
                    index_name,
                    status,
                    queryable,
                )
                last_status = status
                last_queryable = queryable

            if status == "FAILED":
                raise RuntimeError(
                    f"Search index '{index_name}' entered FAILED status: {idx_info}"
                )

            if status == "READY" and queryable is True:
                logger.info(
                    "Search index '%s' is READY and confirmed queryable after %.1fs.",
                    index_name,
                    elapsed,
                )
                return idx_info
        else:
            logger.info("Elapsed: %.1fs | Index '%s' not yet listed by Atlas.", elapsed, index_name)

        time.sleep(poll_interval_seconds)


def provision_vector_index(
    db: Database,
    timeout_seconds: float = 300.0,
    poll_interval_seconds: float = 5.0,
    check_only: bool = False,
) -> Dict[str, Any]:
    """Inspect or provision the Atlas Vector Search index 'idx_notes_vector'.
    
    Returns a dictionary summarizing the outcome and index metadata.
    """
    collection = db["notes"]
    initial_doc_count = collection.count_documents({})
    logger.info("Current note count in 'notes' collection: %d", initial_doc_count)

    existing_indexes = get_all_search_indexes(collection)
    logger.info("Existing search indexes on 'notes': %d found", len(existing_indexes))
    for idx in existing_indexes:
        logger.info(
            " - Found index: name='%s', id='%s', type='%s', status='%s', queryable=%s",
            idx.get("name"),
            idx.get("id"),
            idx.get("type"),
            idx.get("status"),
            idx.get("queryable"),
        )

    target_idx = find_search_index(collection, VECTOR_INDEX_NAME)

    if check_only:
        if target_idx:
            logger.info("Check-only: '%s' is present.", VECTOR_INDEX_NAME)
            return {
                "action": "check_only",
                "exists": True,
                "index": target_idx,
                "notes_count": collection.count_documents({}),
            }
        else:
            logger.info("Check-only: '%s' does not exist.", VECTOR_INDEX_NAME)
            return {
                "action": "check_only",
                "exists": False,
                "index": None,
                "notes_count": collection.count_documents({}),
            }

    if target_idx:
        status = target_idx.get("status")
        queryable = target_idx.get("queryable", False)
        logger.warning(
            "Refusing to create duplicate: index '%s' already exists (status: %s, queryable: %s).",
            VECTOR_INDEX_NAME,
            status,
            queryable,
        )
        if status != "READY" or not queryable:
            logger.info("Existing index is not yet READY/queryable; polling for completion...")
            target_idx = wait_for_index_readiness(
                collection,
                VECTOR_INDEX_NAME,
                timeout_seconds=timeout_seconds,
                poll_interval_seconds=poll_interval_seconds,
            )
        return {
            "action": "already_exists",
            "exists": True,
            "index": target_idx,
            "notes_count": collection.count_documents({}),
        }

    # Create the search index
    logger.info(
        "Creating Vector Search index '%s' (type: %s, dimensions: %d, similarity: %s, path: %s)...",
        VECTOR_INDEX_NAME,
        VECTOR_INDEX_TYPE,
        VECTOR_INDEX_DIMENSIONS,
        VECTOR_INDEX_SIMILARITY,
        VECTOR_INDEX_PATH,
    )
    model = SearchIndexModel(
        definition=VECTOR_INDEX_DEFINITION,
        name=VECTOR_INDEX_NAME,
        type=VECTOR_INDEX_TYPE,
    )

    result_name = collection.create_search_index(model=model)
    logger.info("create_search_index call succeeded. Returned index name: '%s'", result_name)

    # Poll for readiness
    ready_idx = wait_for_index_readiness(
        collection,
        VECTOR_INDEX_NAME,
        timeout_seconds=timeout_seconds,
        poll_interval_seconds=poll_interval_seconds,
    )

    final_doc_count = collection.count_documents({})
    logger.info(
        "Verification: note document count is %d (initial was %d). No documents modified.",
        final_doc_count,
        initial_doc_count,
    )

    return {
        "action": "created",
        "exists": True,
        "index": ready_idx,
        "notes_count": final_doc_count,
    }


def main() -> int:
    """CLI entrypoint for vector search index provisioning."""
    parser = argparse.ArgumentParser(
        description="Provision and verify Atlas Vector Search index 'idx_notes_vector'."
    )
    parser.add_argument(
        "--check-only",
        action="store_true",
        help="Inspect existing search indexes on 'notes' without creating any index.",
    )
    parser.add_argument(
        "--timeout",
        type=float,
        default=300.0,
        help="Maximum wait time in seconds for index to become READY (default: 300).",
    )
    parser.add_argument(
        "--poll-interval",
        type=float,
        default=5.0,
        help="Polling interval in seconds (default: 5).",
    )
    args = parser.parse_args()

    settings = get_settings()
    logger.info("Target database: '%s' | Collection: 'notes'", settings.database_name)

    client = None
    try:
        client = create_mongo_client(settings)
        db = client[settings.database_name]

        # Verify basic connectivity
        db.command("ping")
        logger.info("Atlas connection verified via ping command.")

        outcome = provision_vector_index(
            db=db,
            timeout_seconds=args.timeout,
            poll_interval_seconds=args.poll_interval,
            check_only=args.check_only,
        )

        logger.info("Outcome: %s", outcome.get("action"))
        if outcome.get("index"):
            idx = outcome["index"]
            logger.info(
                "Index Details -> name: %s | id: %s | type: %s | status: %s | queryable: %s",
                idx.get("name"),
                idx.get("id"),
                idx.get("type"),
                idx.get("status"),
                idx.get("queryable"),
            )
            # Log fields definition if present
            definition = idx.get("latestDefinition") or idx.get("definition")
            if definition:
                logger.info("Index Definition: %s", definition)

        logger.info("Notes collection document count: %d", outcome.get("notes_count", 0))
        logger.info("Atlas Vector Search index provisioning process completed successfully.")
        return 0

    except Exception as exc:
        logger.error("Provisioning failed: %s", exc, exc_info=True)
        return 1
    finally:
        if client:
            close_mongo_client(client)


if __name__ == "__main__":
    sys.exit(main())
