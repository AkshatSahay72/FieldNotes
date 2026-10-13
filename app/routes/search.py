import logging
from typing import List, Optional
from fastapi import APIRouter, Depends, HTTPException, Query, status
from pymongo.database import Database
from pymongo.errors import OperationFailure, PyMongoError

from bson import ObjectId
from app.db import get_database
from app.schemas import SemanticSearchResult, UserResponse
from app.routes.auth import get_optional_current_user
from app.services.embedding import (
    EmbeddingService,
    EmbeddingServiceError,
    get_embedding_service,
)

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/search", tags=["Search"])

VECTOR_INDEX_NAME = "idx_notes_vector"
VECTOR_PATH = "embedding"
MIN_CANDIDATES = 20
MAX_CANDIDATES = 500
CANDIDATE_MULTIPLIER = 10


def calculate_num_candidates(limit: int) -> int:
    """Calculate bounded candidate pool size for approximate nearest neighbor search.
    
    In Atlas Vector Search, numCandidates specifies how many nearest neighbor candidates
    to evaluate across the HNSW graph before returning the top 'limit' results.
    - Uses a 10x multiplier over the requested limit.
    - Enforces a minimum lower bound of 20 (guaranteeing numCandidates >= limit).
    - Caps at a maximum of 500 to bound server memory and latency.
    """
    return min(max(limit * CANDIDATE_MULTIPLIER, MIN_CANDIDATES), MAX_CANDIDATES)


def is_vector_index_unavailable_error(err: OperationFailure) -> bool:
    """Identify whether a MongoDB OperationFailure is specifically caused by a missing or unready vector index."""
    err_str = str(err).lower()
    if VECTOR_INDEX_NAME in err_str and any(
        phrase in err_str for phrase in ["not found", "does not exist", "not ready", "building", "initial sync"]
    ):
        return True
    if any(
        phrase in err_str for phrase in [
            "vectorsearch index",
            "search index not found",
            "remote search index",
        ]
    ):
        return True
    return False


@router.get(
    "/semantic",
    response_model=List[SemanticSearchResult],
    summary="Semantic note retrieval via Atlas Vector Search",
)
def semantic_search_notes(
    q: str = Query(
        ...,
        description="Natural language query string for semantic search. Cannot be empty or whitespace-only.",
    ),
    limit: int = Query(
        10,
        ge=1,
        le=50,
        description="Maximum number of semantic results to return (default: 10, min: 1, max: 50).",
    ),
    db: Database = Depends(get_database),
    embedding_service: EmbeddingService = Depends(get_embedding_service),
    current_user: Optional[UserResponse] = Depends(get_optional_current_user),
) -> List[SemanticSearchResult]:
    """Search research notes by semantic similarity using MongoDB Atlas Vector Search.
    
    Converts the query string into a 384-dimensional dense vector using the shared
    EmbeddingService (sentence-transformers/all-MiniLM-L6-v2) and executes an aggregation
    pipeline using $vectorSearch on the 'notes' collection.
    
    Candidate results are strictly validated and filtered by authenticated owner
    to prevent cross-tenant vector search leakage.
    """
    trimmed_q = q.strip()
    if not trimmed_q:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Search query 'q' cannot be empty or whitespace-only",
        )

    # 1. Generate query embedding vector using shared embedding service
    try:
        query_vector = embedding_service.generate_embedding(trimmed_q)
    except (EmbeddingServiceError, ValueError) as err:
        logger.error("Failed to generate embedding for semantic search query: %s", type(err).__name__)
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Embedding generation failed for search query",
        )

    # 2. Build Atlas Vector Search aggregation pipeline
    num_candidates = calculate_num_candidates(limit)
    pipeline = [
        {
            "$vectorSearch": {
                "index": VECTOR_INDEX_NAME,
                "path": VECTOR_PATH,
                "queryVector": query_vector,
                "numCandidates": num_candidates,
                "limit": limit,
            }
        },
        {
            "$project": {
                "_id": 1,
                "title": 1,
                "content": 1,
                "tags": 1,
                "user_id": 1,
                "created_at": 1,
                "updated_at": 1,
                "score": {"$meta": "vectorSearchScore"},
            }
        },
    ]

    expected_owner_id = ObjectId(current_user.id) if current_user else None

    # 3. Execute aggregation pipeline on notes collection with strict ownership validation
    try:
        cursor = db["notes"].aggregate(pipeline)
        results: List[SemanticSearchResult] = []
        for doc in cursor:
            doc_user_id = doc.get("user_id")
            # Strict owner validation prevents cross-tenant vector leakage
            if expected_owner_id is not None:
                if doc_user_id != expected_owner_id:
                    continue
            else:
                if doc_user_id is not None:
                    continue

            results.append(
                SemanticSearchResult(
                    id=str(doc["_id"]),
                    title=doc["title"],
                    content=doc["content"],
                    tags=doc.get("tags", []),
                    created_at=doc["created_at"],
                    updated_at=doc["updated_at"],
                    score=float(doc.get("score", 0.0)),
                )
            )
            if len(results) >= limit:
                break
        return results
    except OperationFailure as err:
        if is_vector_index_unavailable_error(err):
            logger.warning(
                "Vector search index '%s' unavailable or not ready: %s",
                VECTOR_INDEX_NAME,
                type(err).__name__,
            )
            raise HTTPException(
                status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
                detail="Vector search index is not ready or unavailable",
            )
        logger.error("Database operation failure during semantic search: %s", type(err).__name__)
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Database operation failed during semantic search",
        )
    except PyMongoError as err:
        logger.error("Database error during semantic search: %s", type(err).__name__)
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Database operation failed during semantic search",
        )
