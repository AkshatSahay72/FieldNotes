"""Idempotent vector embedding backfill script for Fieldnote research notes.

Scans the MongoDB 'notes' collection for notes lacking vector embeddings
or having an outdated embedding_model. Generates normalized embeddings
using the shared EmbeddingService and applies concurrency-safe updates.

Usage:
    python scripts/backfill_embeddings.py [--dry-run] [--batch-size N] [--limit N]
"""

import argparse
import logging
import sys
from pathlib import Path
from typing import Any, Dict, Optional

# Ensure project root is on sys.path for direct script execution
_project_root = str(Path(__file__).resolve().parent.parent)
if _project_root not in sys.path:
    sys.path.insert(0, _project_root)

from pymongo.database import Database
from pymongo.errors import PyMongoError

from app.config import get_settings
from app.db import create_mongo_client, close_mongo_client
from app.services.embedding import (
    EmbeddingService,
    EmbeddingServiceError,
    get_embedding_service,
)

logger = logging.getLogger("backfill_embeddings")


def backfill_notes(
    db: Database,
    embedding_service: EmbeddingService,
    dry_run: bool = False,
    batch_size: int = 50,
    limit: Optional[int] = None,
) -> Dict[str, int]:
    """Process notes requiring embeddings and conditionally update them.
    
    Returns a dictionary of counts:
    {"processed": int, "updated": int, "skipped": int, "failed": int}
    """
    target_model = embedding_service.model_name
    query_filter = {
        "$or": [
            {"embedding": {"$exists": False}},
            {"embedding": None},
            {"embedding_model": {"$exists": False}},
            {"embedding_model": {"$ne": target_model}},
        ]
    }

    projection = {
        "_id": 1,
        "title": 1,
        "content": 1,
        "updated_at": 1,
    }

    counts = {
        "processed": 0,
        "updated": 0,
        "skipped": 0,
        "failed": 0,
    }

    try:
        cursor = db["notes"].find(query_filter, projection).batch_size(batch_size)
        if limit is not None and limit > 0:
            cursor = cursor.limit(limit)
    except PyMongoError as err:
        logger.error("Failed to query notes for backfill: %s", type(err).__name__)
        counts["failed"] += 1
        return counts

    for note in cursor:
        counts["processed"] += 1
        note_id = note["_id"]
        title = note.get("title", "")
        content = note.get("content", "")
        updated_at = note.get("updated_at")

        # 1. Format text and compute vector embedding using shared EmbeddingService logic
        try:
            text = embedding_service.prepare_text(title, content)
            vector = embedding_service.generate_embedding(text)
        except (EmbeddingServiceError, ValueError) as err:
            logger.warning(
                "Failed to generate embedding for note ID %s: %s",
                note_id,
                type(err).__name__,
            )
            counts["failed"] += 1
            continue

        # 2. In dry-run mode, register simulated update and proceed
        if dry_run:
            counts["updated"] += 1
            continue

        # 3. Concurrency-safe conditional update: match on _id and updated_at
        update_filter: Dict[str, Any] = {"_id": note_id}
        if updated_at is not None:
            update_filter["updated_at"] = updated_at
        else:
            update_filter["updated_at"] = {"$exists": False}

        try:
            result = db["notes"].update_one(
                update_filter,
                {
                    "$set": {
                        "embedding": vector,
                        "embedding_model": target_model,
                    }
                },
            )
            if result.matched_count == 0:
                # Document was modified or removed concurrently during inference
                counts["skipped"] += 1
                logger.info("Skipped note ID %s (modified concurrently during inference)", note_id)
            else:
                counts["updated"] += 1
        except PyMongoError as err:
            logger.error("Database update failed for note ID %s: %s", note_id, type(err).__name__)
            counts["failed"] += 1

    return counts


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Backfill vector embeddings for Fieldnote research notes."
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Simulate embedding generation without modifying database records.",
    )
    parser.add_argument(
        "--batch-size",
        type=int,
        default=50,
        help="Batch size for MongoDB cursor streaming (default: 50).",
    )
    parser.add_argument(
        "--limit",
        type=int,
        default=None,
        help="Maximum number of notes to process (default: all eligible).",
    )
    args = parser.parse_args()

    # Configure sanitized console logging (never leaks secrets or note content)
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s [%(levelname)s] %(message)s",
    )

    settings = get_settings()
    logger.info("Starting embedding backfill (dry_run=%s, model=%s)", args.dry_run, settings.embedding_model)

    client = None
    try:
        client = create_mongo_client(settings)
        db = client[settings.database_name]
        embedding_service = get_embedding_service(settings)

        counts = backfill_notes(
            db=db,
            embedding_service=embedding_service,
            dry_run=args.dry_run,
            batch_size=args.batch_size,
            limit=args.limit,
        )
    except Exception as err:
        logger.error("Backfill operation encountered a fatal error: %s", type(err).__name__)
        return 1
    finally:
        if client is not None:
            close_mongo_client(client)

    print("\n--- Backfill Summary ---")
    print(f"Dry Run:   {args.dry_run}")
    print(f"Processed: {counts['processed']}")
    print(f"Updated:   {counts['updated']}")
    print(f"Skipped:   {counts['skipped']}")
    print(f"Failed:    {counts['failed']}")
    print("------------------------\n")

    if counts["failed"] > 0:
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
