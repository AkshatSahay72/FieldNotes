import logging
from datetime import datetime, timezone
from typing import List, Optional
from bson import ObjectId
from fastapi import APIRouter, Depends, HTTPException, Query, Response, status
from gridfs import GridFS
from pymongo import ReturnDocument
from pymongo.database import Database
from pymongo.errors import PyMongoError

from app.config import check_demo_mode
from app.db import get_database, get_gridfs
from app.schemas import NoteCreate, NoteUpdate, NoteResponse, UserResponse
from app.routes.auth import get_optional_current_user, enforce_write_access
from app.services.embedding import (
    EmbeddingService,
    EmbeddingServiceError,
    get_embedding_service,
)

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/notes", tags=["Notes"])


def validate_object_id(note_id: str) -> ObjectId:
    """Validate that note_id is a valid 24-character hex ObjectId string.
    
    Raises HTTP 400 Bad Request if the format is invalid.
    """
    if not ObjectId.is_valid(note_id):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Invalid note ID format: '{note_id}'",
        )
    return ObjectId(note_id)


def note_doc_to_response(doc: dict) -> NoteResponse:
    """Transform a MongoDB document into a typed NoteResponse."""
    return NoteResponse(
        id=str(doc["_id"]),
        title=doc["title"],
        content=doc["content"],
        tags=doc.get("tags", []),
        type=doc.get("type", "memory"),
        created_at=doc["created_at"],
        updated_at=doc["updated_at"],
    )


def parse_and_validate_tags(
    tag: Optional[List[str]] = None,
    tags: Optional[List[str]] = None,
) -> Optional[List[str]]:
    """Parse, split, normalize, and validate tag filter query parameters.
    
    Accepts repeated query params (e.g., ?tag=soil&tag=water) or comma-delimited strings (e.g., ?tag=soil,water).
    Returns a deduplicated list of non-empty stripped tag strings, or None if no tags requested.
    Raises HTTP 400 Bad Request if any provided tag is empty or whitespace-only.
    """
    raw_inputs = []
    if tag is not None:
        raw_inputs.extend(tag)
    if tags is not None:
        raw_inputs.extend(tags)

    if not raw_inputs:
        return None

    cleaned_tags = []
    for item in raw_inputs:
        parts = item.split(",")
        for part in parts:
            stripped = part.strip()
            if not stripped:
                raise HTTPException(
                    status_code=status.HTTP_400_BAD_REQUEST,
                    detail="Tag filter value cannot be empty",
                )
            if stripped not in cleaned_tags:
                cleaned_tags.append(stripped)

    return cleaned_tags if cleaned_tags else None


def build_notes_query(
    tag_list: Optional[List[str]] = None,
    q: Optional[str] = None,
    entry_type: Optional[str] = None,
) -> dict:
    """Build a composable MongoDB query filter for tags, full-text search, and optional type."""
    query: dict = {}
    if tag_list:
        query["tags"] = {"$in": tag_list}
    if entry_type:
        query["type"] = entry_type
    if q is not None:
        trimmed_q = q.strip()
        if not trimmed_q:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Search query 'q' cannot be empty",
            )
        query["$text"] = {"$search": trimmed_q}
    return query


@router.post(
    "",
    response_model=NoteResponse,
    status_code=status.HTTP_201_CREATED,
    summary="Create a new research note or memory entry",
    dependencies=[Depends(enforce_write_access)],
)
def create_note(
    note_in: NoteCreate,
    db: Database = Depends(get_database),
    embedding_service: EmbeddingService = Depends(get_embedding_service),
    current_user: Optional[UserResponse] = Depends(get_optional_current_user),
) -> NoteResponse:
    """Create a new research note document in MongoDB with vector embedding and derived user ownership."""
    try:
        embedding_text = embedding_service.prepare_text(note_in.title, note_in.content)
        vector = embedding_service.generate_embedding(embedding_text)
    except (EmbeddingServiceError, ValueError) as err:
        logger.error("Failed to generate embedding during note creation: %s", type(err).__name__)
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Embedding generation failed while creating note",
        )

    now = datetime.now(timezone.utc)
    user_id = ObjectId(current_user.id) if current_user else None
    note_doc = {
        "title": note_in.title,
        "content": note_in.content,
        "tags": note_in.tags,
        "type": note_in.type or "memory",
        "embedding": vector,
        "embedding_model": embedding_service.model_name,
        "user_id": user_id,
        "created_at": now,
        "updated_at": now,
    }

    try:
        result = db["notes"].insert_one(note_doc)
        note_doc["_id"] = result.inserted_id
        return note_doc_to_response(note_doc)
    except PyMongoError as err:
        logger.error("Failed to insert note: %s", type(err).__name__)
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Database operation failed while creating note",
        )


@router.get(
    "",
    response_model=List[NoteResponse],
    summary="List, search, and filter research notes",
)
def list_notes(
    tag: Optional[List[str]] = Query(
        None,
        description="Filter by tag (OR semantics). Can be repeated (?tag=soil&tag=water) or comma-separated (?tag=soil,water).",
    ),
    tags: Optional[List[str]] = Query(
        None,
        description="Alias for tag filter parameter.",
    ),
    q: Optional[str] = Query(
        None,
        description="Text search query across note title and content using MongoDB full-text search.",
    ),
    entry_type: Optional[str] = Query(
        None,
        alias="type",
        description="Optional filter by entry type (journal, memory, research, idea, learning).",
    ),
    skip: int = Query(
        0,
        ge=0,
        description="Number of notes to skip (offset, default: 0). Must be >= 0.",
    ),
    limit: int = Query(
        20,
        ge=1,
        le=100,
        description="Maximum number of notes to return (default: 20, max: 100).",
    ),
    db: Database = Depends(get_database),
    current_user: Optional[UserResponse] = Depends(get_optional_current_user),
) -> List[NoteResponse]:
    """Retrieve research notes with optional tag filtering, full-text search, and pagination.
    
    Notes are strictly scoped to the authenticated user (or public demo notes if unauthenticated).
    """
    cleaned_tags = parse_and_validate_tags(tag=tag, tags=tags)
    filter_query = build_notes_query(tag_list=cleaned_tags, q=q, entry_type=entry_type)
    if current_user:
        filter_query["user_id"] = ObjectId(current_user.id)
    else:
        filter_query["user_id"] = None

    try:
        cursor = (
            db["notes"]
            .find(filter_query)
            .sort([("created_at", -1), ("_id", -1)])
            .skip(skip)
            .limit(limit)
        )
        return [note_doc_to_response(doc) for doc in cursor]
    except PyMongoError as err:
        logger.error("Failed to query notes: %s", type(err).__name__)
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Database operation failed while listing notes",
        )


@router.get(
    "/{note_id}",
    response_model=NoteResponse,
    summary="Retrieve a single research note by ID",
)
def get_note(
    note_id: str,
    db: Database = Depends(get_database),
    current_user: Optional[UserResponse] = Depends(get_optional_current_user),
) -> NoteResponse:
    """Retrieve a single research note document by its ObjectId, scoped to authenticated owner."""
    oid = validate_object_id(note_id)
    owner_id = ObjectId(current_user.id) if current_user else None

    try:
        doc = db["notes"].find_one({"_id": oid})
    except PyMongoError as err:
        logger.error("Failed to fetch note %s: %s", note_id, type(err).__name__)
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Database operation failed while fetching note",
        )

    if doc is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Note with ID '{note_id}' not found",
        )

    # Public synthetic demo records can be read; private records require matching owner
    if not doc.get("is_demo", False) and doc.get("user_id") != owner_id:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Note with ID '{note_id}' not found",
        )

    return note_doc_to_response(doc)


@router.put(
    "/{note_id}",
    response_model=NoteResponse,
    summary="Update a research note by ID",
    dependencies=[Depends(enforce_write_access)],
)
def update_note(
    note_id: str,
    note_in: NoteUpdate,
    db: Database = Depends(get_database),
    embedding_service: EmbeddingService = Depends(get_embedding_service),
    current_user: Optional[UserResponse] = Depends(get_optional_current_user),
) -> NoteResponse:
    """Update title, content, and tags of an existing note with vector embedding recomputation and owner scoping."""
    oid = validate_object_id(note_id)
    owner_id = ObjectId(current_user.id) if current_user else None

    try:
        existing = db["notes"].find_one({"_id": oid})
    except PyMongoError as err:
        logger.error("Failed to fetch note %s before update: %s", note_id, type(err).__name__)
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Database operation failed while fetching note",
        )

    if existing is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Note with ID '{note_id}' not found",
        )

    # Protect synthetic demo records from mutation across all clients
    if existing.get("is_demo", False):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Synthetic demo records are read-only",
        )

    # Strict owner authorization
    if existing.get("user_id") != owner_id:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Note with ID '{note_id}' not found",
        )

    now = datetime.now(timezone.utc)
    title_changed = existing.get("title") != note_in.title
    content_changed = existing.get("content") != note_in.content
    needs_new_embedding = title_changed or content_changed

    update_fields = {
        "title": note_in.title,
        "content": note_in.content,
        "tags": note_in.tags,
        "updated_at": now,
    }
    if note_in.type is not None:
        update_fields["type"] = note_in.type

    if needs_new_embedding:
        try:
            embedding_text = embedding_service.prepare_text(note_in.title, note_in.content)
            vector = embedding_service.generate_embedding(embedding_text)
            update_fields["embedding"] = vector
            update_fields["embedding_model"] = embedding_service.model_name
        except (EmbeddingServiceError, ValueError) as err:
            logger.error("Failed to recompute embedding for note %s: %s", note_id, type(err).__name__)
            raise HTTPException(
                status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
                detail="Embedding generation failed while updating note",
            )

    try:
        updated_doc = db["notes"].find_one_and_update(
            {"_id": oid},
            {"$set": update_fields},
            return_document=ReturnDocument.AFTER,
        )
    except PyMongoError as err:
        logger.error("Failed to update note %s: %s", note_id, type(err).__name__)
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Database operation failed while updating note",
        )

    if updated_doc is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Note with ID '{note_id}' not found",
        )

    return note_doc_to_response(updated_doc)


@router.delete(
    "/{note_id}",
    status_code=status.HTTP_204_NO_CONTENT,
    summary="Delete a research note by ID with cascading attachment cleanup",
    dependencies=[Depends(enforce_write_access)],
)
def delete_note(
    note_id: str,
    db: Database = Depends(get_database),
    fs: GridFS = Depends(get_gridfs),
    current_user: Optional[UserResponse] = Depends(get_optional_current_user),
) -> Response:
    """Delete a research note and safely clean up all linked GridFS attachments within owner scope."""
    oid = validate_object_id(note_id)
    owner_id = ObjectId(current_user.id) if current_user else None

    # 1. Verify note exists
    try:
        note = db["notes"].find_one({"_id": oid})
    except PyMongoError as err:
        logger.error("Failed to verify note %s before delete: %s", note_id, type(err).__name__)
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Database operation failed while locating note",
        )

    if note is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Note with ID '{note_id}' not found",
        )

    # Protect synthetic demo records from deletion across all clients
    if note.get("is_demo", False):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Synthetic demo records are read-only",
        )

    # Strict owner authorization
    if note.get("user_id") != owner_id:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Note with ID '{note_id}' not found",
        )

    # 2. Find and clean up child attachments
    try:
        child_attachments = list(db["attachments"].find({"note_id": oid}))
        for att in child_attachments:
            file_id = att.get("file_id")
            if file_id is not None:
                fs.delete(file_id)
            db["attachments"].delete_one({"_id": att["_id"]})
    except Exception as err:
        logger.error("Cascading cleanup failed for note %s attachments: %s", note_id, type(err).__name__)
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Failed to clean up linked attachments; note was not deleted",
        )

    # 3. Delete parent note document
    try:
        result = db["notes"].delete_one({"_id": oid})
    except PyMongoError as err:
        logger.error("Failed to delete note %s: %s", note_id, type(err).__name__)
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Database operation failed while deleting note",
        )

    if result.deleted_count == 0:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Note with ID '{note_id}' not found",
        )

    return Response(status_code=status.HTTP_204_NO_CONTENT)
