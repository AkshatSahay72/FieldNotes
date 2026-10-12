import io
import logging
import pathlib
from datetime import datetime, timezone
from typing import List, Optional
from bson import ObjectId
from fastapi import APIRouter, Depends, Form, HTTPException, Response, UploadFile, File, status
from fastapi.responses import StreamingResponse
from gridfs import GridFS
from PIL import Image, UnidentifiedImageError
from pymongo.database import Database
from pymongo.errors import PyMongoError

from app.db import get_database, get_gridfs
from app.schemas import AttachmentResponse

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/notes", tags=["Attachments"])

MAX_FILE_SIZE = 5 * 1024 * 1024  # 5 MB limit
CHUNK_SIZE = 64 * 1024  # 64 KB read buffer
ALLOWED_MIME_TYPES = {"image/jpeg", "image/png", "image/webp"}


def validate_object_id(id_str: str, entity_name: str = "ID") -> ObjectId:
    """Validate that id_str is a valid 24-character hex ObjectId string.
    
    Raises HTTP 400 Bad Request if format is invalid.
    """
    if not ObjectId.is_valid(id_str):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Invalid {entity_name} format: '{id_str}'",
        )
    return ObjectId(id_str)


def detect_image_format(data: bytes) -> Optional[str]:
    """Inspect magic header bytes to verify authentic image signature.
    
    Returns standard MIME type or None if unrecognized.
    """
    if len(data) >= 3 and data.startswith(b"\xff\xd8\xff"):
        return "image/jpeg"
    if len(data) >= 8 and data.startswith(b"\x89PNG\r\n\x1a\n"):
        return "image/png"
    if len(data) >= 12 and data.startswith(b"RIFF") and data[8:12] == b"WEBP":
        return "image/webp"
    return None


def validate_image_content(file_bytes: bytes) -> str:
    """Validate that byte content is an authentic, structurally valid image.
    
    1. Checks binary magic bytes to verify allowed file signatures.
    2. Uses Pillow to verify complete structural integrity without full decompression.
    3. Confirms that structural format matches the detected signature.
    
    Returns detected canonical MIME type or raises HTTP 415.
    """
    detected_mime = detect_image_format(bytes(file_bytes[:16]))
    if not detected_mime or detected_mime not in ALLOWED_MIME_TYPES:
        raise HTTPException(
            status_code=status.HTTP_415_UNSUPPORTED_MEDIA_TYPE,
            detail="Unsupported file type. Only JPEG, PNG, and WebP images are permitted.",
        )

    try:
        with Image.open(io.BytesIO(file_bytes)) as img:
            img.verify()
            format_map = {
                "JPEG": "image/jpeg",
                "PNG": "image/png",
                "WEBP": "image/webp",
            }
            pil_mime = format_map.get(img.format)
            if pil_mime != detected_mime:
                raise HTTPException(
                    status_code=status.HTTP_415_UNSUPPORTED_MEDIA_TYPE,
                    detail="Image header does not match structural image payload",
                )
    except (UnidentifiedImageError, OSError, SyntaxError) as err:
        logger.warning("Structural image validation failed: %s", type(err).__name__)
        raise HTTPException(
            status_code=status.HTTP_415_UNSUPPORTED_MEDIA_TYPE,
            detail="Corrupted or structurally invalid image payload",
        )

    return detected_mime


def attachment_doc_to_response(doc: dict) -> AttachmentResponse:
    """Transform an attachment document into an AttachmentResponse schema."""
    return AttachmentResponse(
        id=str(doc["_id"]),
        note_id=str(doc["note_id"]),
        filename=doc["filename"],
        content_type=doc["content_type"],
        file_size=doc["file_size"],
        caption=doc.get("caption"),
        description=doc.get("description"),
        created_at=doc["created_at"],
    )


def ensure_note_exists(note_oid: ObjectId, db: Database) -> dict:
    """Check that parent note exists; raises 404 Not Found if missing."""
    try:
        note = db["notes"].find_one({"_id": note_oid})
    except PyMongoError as err:
        logger.error("Failed to query note %s: %s", note_oid, type(err).__name__)
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Database operation failed while verifying parent note",
        )

    if note is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Note with ID '{note_oid}' not found",
        )
    return note


@router.post(
    "/{note_id}/attachments",
    response_model=AttachmentResponse,
    status_code=status.HTTP_201_CREATED,
    summary="Upload image attachment for a note",
)
async def upload_attachment(
    note_id: str,
    file: UploadFile = File(..., description="Image file (JPEG, PNG, or WebP, up to 5 MB)"),
    caption: Optional[str] = Form(None, description="Optional caption for evidence"),
    description: Optional[str] = Form(None, description="Optional description of evidence"),
    db: Database = Depends(get_database),
    fs: GridFS = Depends(get_gridfs),
) -> AttachmentResponse:
    """Upload and link an image attachment to an existing research note using GridFS."""
    note_oid = validate_object_id(note_id, "note ID")
    ensure_note_exists(note_oid, db)

    # Enforce bounded reading up to MAX_FILE_SIZE
    file_bytes = bytearray()
    while True:
        chunk = await file.read(CHUNK_SIZE)
        if not chunk:
            break
        file_bytes.extend(chunk)
        if len(file_bytes) > MAX_FILE_SIZE:
            raise HTTPException(
                status_code=status.HTTP_413_CONTENT_TOO_LARGE,
                detail=f"File exceeds maximum allowed size of {MAX_FILE_SIZE // (1024 * 1024)} MB",
            )

    if len(file_bytes) == 0:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Uploaded file is empty",
        )

    # Verify authentic file content through magic header bytes and structural validation
    detected_mime = validate_image_content(bytes(file_bytes))

    # Sanitize display filename (prevent path traversal / directory injection)
    raw_name = pathlib.Path(file.filename or "attachment").name
    sanitized_filename = raw_name.strip() or f"attachment.{detected_mime.split('/')[-1]}"

    now = datetime.now(timezone.utc)
    file_id = None

    try:
        # Store binary chunks in GridFS
        file_id = fs.put(
            bytes(file_bytes),
            filename=sanitized_filename,
            content_type=detected_mime,
        )

        # Store metadata document in attachments collection
        att_doc = {
            "note_id": note_oid,
            "file_id": file_id,
            "filename": sanitized_filename,
            "content_type": detected_mime,
            "file_size": len(file_bytes),
            "caption": caption.strip() if caption and caption.strip() else None,
            "description": description.strip() if description and description.strip() else None,
            "created_at": now,
        }
        result = db["attachments"].insert_one(att_doc)
        att_doc["_id"] = result.inserted_id
        return attachment_doc_to_response(att_doc)
    except PyMongoError as err:
        logger.error("Failed to store attachment: %s", type(err).__name__)
        # Clean up orphaned GridFS binary chunks if metadata insert failed
        if file_id is not None:
            try:
                fs.delete(file_id)
            except Exception as cleanup_err:
                logger.warning("Failed to clean up orphaned GridFS file %s: %s", file_id, type(cleanup_err).__name__)
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Database operation failed while storing attachment",
        )


@router.get(
    "/{note_id}/attachments",
    response_model=List[AttachmentResponse],
    summary="List all attachments for a note",
)
def list_attachments(
    note_id: str,
    db: Database = Depends(get_database),
) -> List[AttachmentResponse]:
    """Retrieve metadata for all attachments linked to the specified note."""
    note_oid = validate_object_id(note_id, "note ID")
    ensure_note_exists(note_oid, db)

    try:
        cursor = db["attachments"].find({"note_id": note_oid}).sort("created_at", 1)
        return [attachment_doc_to_response(doc) for doc in cursor]
    except PyMongoError as err:
        logger.error("Failed to list attachments for note %s: %s", note_id, type(err).__name__)
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Database operation failed while retrieving attachments",
        )


@router.get(
    "/{note_id}/attachments/{attachment_id}",
    response_model=AttachmentResponse,
    summary="Retrieve attachment metadata by ID",
)
def get_attachment(
    note_id: str,
    attachment_id: str,
    db: Database = Depends(get_database),
) -> AttachmentResponse:
    """Retrieve metadata for a specific attachment belonging to a note."""
    note_oid = validate_object_id(note_id, "note ID")
    att_oid = validate_object_id(attachment_id, "attachment ID")
    ensure_note_exists(note_oid, db)

    try:
        doc = db["attachments"].find_one({"_id": att_oid, "note_id": note_oid})
    except PyMongoError as err:
        logger.error("Failed to fetch attachment %s: %s", attachment_id, type(err).__name__)
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Database operation failed while fetching attachment",
        )

    if doc is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Attachment with ID '{attachment_id}' not found for note '{note_id}'",
        )

    return attachment_doc_to_response(doc)


@router.get(
    "/{note_id}/attachments/{attachment_id}/download",
    summary="Download or stream raw image binary",
)
def download_attachment(
    note_id: str,
    attachment_id: str,
    db: Database = Depends(get_database),
    fs: GridFS = Depends(get_gridfs),
) -> StreamingResponse:
    """Stream raw image binary data directly from GridFS with validated Content-Type."""
    note_oid = validate_object_id(note_id, "note ID")
    att_oid = validate_object_id(attachment_id, "attachment ID")
    ensure_note_exists(note_oid, db)

    try:
        doc = db["attachments"].find_one({"_id": att_oid, "note_id": note_oid})
    except PyMongoError as err:
        logger.error("Failed to fetch attachment metadata %s: %s", attachment_id, type(err).__name__)
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Database operation failed while locating attachment",
        )

    if doc is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Attachment with ID '{attachment_id}' not found for note '{note_id}'",
        )

    try:
        grid_out = fs.get(doc["file_id"])
    except Exception as err:
        logger.error("GridFS file not found for attachment %s: %s", attachment_id, type(err).__name__)
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Attachment binary file not found in storage",
        )

    def iterfile():
        try:
            while True:
                chunk = grid_out.read(CHUNK_SIZE)
                if not chunk:
                    break
                yield chunk
        finally:
            if hasattr(grid_out, "close"):
                grid_out.close()

    return StreamingResponse(
        iterfile(),
        media_type=doc["content_type"],
        headers={
            "Content-Disposition": f'inline; filename="{doc["filename"]}"',
            "Content-Length": str(doc["file_size"]),
        },
    )


@router.delete(
    "/{note_id}/attachments/{attachment_id}",
    status_code=status.HTTP_204_NO_CONTENT,
    summary="Delete a single attachment",
)
def delete_attachment(
    note_id: str,
    attachment_id: str,
    db: Database = Depends(get_database),
    fs: GridFS = Depends(get_gridfs),
) -> Response:
    """Delete binary chunks from GridFS and metadata record from attachments collection."""
    note_oid = validate_object_id(note_id, "note ID")
    att_oid = validate_object_id(attachment_id, "attachment ID")
    ensure_note_exists(note_oid, db)

    try:
        doc = db["attachments"].find_one({"_id": att_oid, "note_id": note_oid})
    except PyMongoError as err:
        logger.error("Failed to query attachment %s: %s", attachment_id, type(err).__name__)
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Database operation failed while fetching attachment",
        )

    if doc is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Attachment with ID '{attachment_id}' not found for note '{note_id}'",
        )

    try:
        # Delete binary chunks from GridFS
        fs.delete(doc["file_id"])
        # Delete metadata record
        db["attachments"].delete_one({"_id": att_oid})
    except PyMongoError as err:
        logger.error("Failed to delete attachment %s: %s", attachment_id, type(err).__name__)
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Database operation failed while deleting attachment",
        )

    return Response(status_code=status.HTTP_204_NO_CONTENT)
