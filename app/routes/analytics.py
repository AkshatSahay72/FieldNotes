import logging
from typing import List, Optional
from bson import ObjectId
from fastapi import APIRouter, Depends, HTTPException, Query, status
from pymongo.database import Database
from pymongo.errors import PyMongoError

from app.db import get_database
from app.schemas import (
    AnalyticsOverview,
    DailyActivity,
    NoteAttachmentSummary,
    TagCount,
    UserResponse,
)
from app.routes.auth import get_optional_current_user

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/analytics", tags=["Analytics"])


def build_tag_distribution_pipeline(owner_id: Optional[ObjectId] = None) -> List[dict]:
    """Construct MongoDB aggregation pipeline for tag frequency distribution.
    
    Stages:
    1. (Optional) $match: Filters notes strictly by authenticated owner.
    2. $unwind: Deconstructs the 'tags' array field so each tag is processed individually.
       Notes with empty or missing tags are automatically excluded.
    3. $match: Filters for valid tag strings containing at least one non-whitespace character
       (excluding nulls, empty strings, and whitespace-only strings).
    4. $group: Groups by tag name and computes the total occurrences.
    5. $sort: Deterministic ordering - frequency count descending, then tag name ascending.
    6. $project: Projects 'tag' and 'count' fields, suppressing '_id'.
    """
    pipeline: List[dict] = []
    if owner_id is not None:
        pipeline.append({"$match": {"user_id": owner_id}})
    pipeline.extend([
        {"$unwind": "$tags"},
        {"$match": {"tags": {"$type": "string", "$regex": r"\S"}}},
        {"$group": {"_id": "$tags", "count": {"$sum": 1}}},
        {"$sort": {"count": -1, "_id": 1}},
        {"$project": {"_id": 0, "tag": "$_id", "count": 1}},
    ])
    return pipeline


def build_note_activity_pipeline(owner_id: Optional[ObjectId] = None) -> List[dict]:
    """Construct MongoDB aggregation pipeline for daily note creation frequency.
    
    Stages:
    1. $match: Ensures 'created_at' is a valid BSON date object and filters by owner.
    2. $group: Truncates and formats 'created_at' to a UTC calendar date string (YYYY-MM-DD)
       and counts notes created on each date.
    3. $sort: Deterministic chronological ordering ascending by date string.
    4. $project: Projects 'date' and 'count' fields, suppressing '_id'.
    """
    match_stage: dict = {"created_at": {"$type": "date"}}
    if owner_id is not None:
        match_stage["user_id"] = owner_id
    return [
        {"$match": match_stage},
        {
            "$group": {
                "_id": {
                    "$dateToString": {
                        "format": "%Y-%m-%d",
                        "date": "$created_at",
                        "timezone": "UTC",
                    }
                },
                "count": {"$sum": 1},
            }
        },
        {"$sort": {"_id": 1}},
        {"$project": {"_id": 0, "date": "$_id", "count": 1}},
    ]


def build_attachment_counts_pipeline(
    include_zero: bool = True,
    owner_id: Optional[ObjectId] = None,
) -> List[dict]:
    """Construct MongoDB aggregation pipeline for attachment counts per research note.
    
    Stages:
    1. (Optional) $match: Filters parent notes by authenticated owner.
    2. $lookup: Performs a left outer join from 'notes' to 'attachments' using
       notes._id == attachments.note_id. Leverages the 'idx_attachments_note_id' index.
    3. $project: Computes 'attachment_count' as the size of the matched attachments array,
       converts the note '_id' to string, and projects the note 'title'. Binary chunks are never loaded.
    4. (Optional) $match: Filters out notes with zero attachments if include_zero is False.
    5. $sort: Deterministic ordering - attachment_count descending, title ascending, note_id ascending.
    """
    pipeline: List[dict] = []
    if owner_id is not None:
        pipeline.append({"$match": {"user_id": owner_id}})
    pipeline.extend([
        {
            "$lookup": {
                "from": "attachments",
                "localField": "_id",
                "foreignField": "note_id",
                "as": "attachments",
            }
        },
        {
            "$project": {
                "_id": 0,
                "note_id": {"$toString": "$_id"},
                "title": "$title",
                "attachment_count": {"$size": "$attachments"},
            }
        },
    ])
    if not include_zero:
        pipeline.append({"$match": {"attachment_count": {"$gt": 0}}})

    pipeline.append({"$sort": {"attachment_count": -1, "title": 1, "note_id": 1}})
    return pipeline


@router.get(
    "/overview",
    response_model=AnalyticsOverview,
    summary="Research Notes and Attachments Overview",
)
def get_research_overview(
    db: Database = Depends(get_database),
    current_user: Optional[UserResponse] = Depends(get_optional_current_user),
) -> AnalyticsOverview:
    """Retrieve high-level summary metrics across notes and evidence attachments scoped by owner.
    
    Returns total research notes count, total attachment metadata records count,
    and the number of notes containing at least one tag.
    """
    owner_id = ObjectId(current_user.id) if current_user else None
    owner_filter: dict = {"user_id": owner_id} if owner_id is not None else {}
    tagged_filter = {
        **owner_filter,
        "tags": {"$elemMatch": {"$type": "string", "$regex": r"\S"}},
    }

    try:
        total_notes = db["notes"].count_documents(owner_filter)
        total_attachments = db["attachments"].count_documents(owner_filter)
        notes_with_tags = db["notes"].count_documents(tagged_filter)
        return AnalyticsOverview(
            total_notes=total_notes,
            total_attachments=total_attachments,
            notes_with_tags=notes_with_tags,
        )
    except PyMongoError as err:
        logger.error("Database error in get_research_overview: %s", type(err).__name__)
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Database service unavailable",
        )


@router.get(
    "/tags",
    response_model=List[TagCount],
    summary="Tag Frequency Distribution",
)
def get_tag_distribution(
    db: Database = Depends(get_database),
    current_user: Optional[UserResponse] = Depends(get_optional_current_user),
) -> List[TagCount]:
    """Retrieve frequency distribution across research tags scoped to owner using MongoDB aggregation.
    
    Deconstructs tag arrays via $unwind and groups counts by tag name.
    Sorted deterministically by frequency descending, then tag name ascending.
    Tag matching is case-sensitive as stored; empty/missing tags are omitted.
    Returns an empty list when no tagged notes exist.
    """
    owner_id = ObjectId(current_user.id) if current_user else None
    pipeline = build_tag_distribution_pipeline(owner_id=owner_id)
    try:
        cursor = db["notes"].aggregate(pipeline)
        return [TagCount(**doc) for doc in cursor]
    except PyMongoError as err:
        logger.error("Database error in get_tag_distribution: %s", type(err).__name__)
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Database service unavailable",
        )


@router.get(
    "/activity",
    response_model=List[DailyActivity],
    summary="Daily Note Creation Activity",
)
def get_note_creation_activity(
    db: Database = Depends(get_database),
    current_user: Optional[UserResponse] = Depends(get_optional_current_user),
) -> List[DailyActivity]:
    """Retrieve note creation activity grouped by calendar day (UTC) scoped to owner.
    
    Groups creation timestamps by YYYY-MM-DD in UTC and returns counts sorted chronologically.
    Returns an empty list when no notes exist. Calendar days with zero activity are not fabricated.
    """
    owner_id = ObjectId(current_user.id) if current_user else None
    pipeline = build_note_activity_pipeline(owner_id=owner_id)
    try:
        cursor = db["notes"].aggregate(pipeline)
        return [DailyActivity(**doc) for doc in cursor]
    except PyMongoError as err:
        logger.error("Database error in get_note_creation_activity: %s", type(err).__name__)
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Database service unavailable",
        )


@router.get(
    "/attachments",
    response_model=List[NoteAttachmentSummary],
    summary="Attachment Counts by Research Note",
)
def get_attachment_counts_by_note(
    include_zero: bool = Query(
        True,
        description="Whether to include notes that currently have zero attachments.",
    ),
    db: Database = Depends(get_database),
    current_user: Optional[UserResponse] = Depends(get_optional_current_user),
) -> List[NoteAttachmentSummary]:
    """Retrieve evidence attachment counts per research note scoped to owner.
    
    Joins notes to attachment metadata and computes array size without loading binary chunks.
    Sorted deterministically by attachment count descending, then note title ascending.
    Returns an empty list when no notes exist.
    """
    owner_id = ObjectId(current_user.id) if current_user else None
    pipeline = build_attachment_counts_pipeline(include_zero=include_zero, owner_id=owner_id)
    try:
        cursor = db["notes"].aggregate(pipeline)
        return [NoteAttachmentSummary(**doc) for doc in cursor]
    except PyMongoError as err:
        logger.error("Database error in get_attachment_counts_by_note: %s", type(err).__name__)
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Database service unavailable",
        )
