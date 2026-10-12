from datetime import datetime
from typing import List, Optional
from pydantic import BaseModel, Field, field_validator


class HealthResponse(BaseModel):
    """Schema for service health check response."""

    status: str = Field(
        ...,
        description="Overall service health status ('healthy' or 'unhealthy')",
        examples=["healthy", "unhealthy"],
    )
    app: str = Field(
        ...,
        description="FastAPI application status",
        examples=["ok"],
    )
    database: str = Field(
        ...,
        description="Database connection status ('connected' or 'disconnected')",
        examples=["connected", "disconnected"],
    )
    environment: str = Field(
        ...,
        description="Current running environment",
        examples=["development", "testing", "production"],
    )


class NoteCreate(BaseModel):
    """Schema for creating a new research note."""

    title: str = Field(
        ...,
        min_length=1,
        description="Title of the research note (required, non-empty)",
        examples=["Observed soil moisture anomalies in plot B"],
    )
    content: str = Field(
        ...,
        description="Body content or findings of the research note",
        examples=["Moisture sensors at 15cm depth indicated higher saturation after rain."],
    )
    tags: List[str] = Field(
        default_factory=list,
        description="Categorical tags for filtering and organization",
        examples=[["soil", "moisture", "fieldwork"]],
    )

    @field_validator("title")
    @classmethod
    def validate_title_not_empty(cls, value: str) -> str:
        trimmed = value.strip()
        if not trimmed:
            raise ValueError("Title must contain non-whitespace characters")
        return trimmed


class NoteUpdate(BaseModel):
    """Schema for updating an existing research note."""

    title: str = Field(
        ...,
        min_length=1,
        description="Updated title of the research note (required, non-empty)",
    )
    content: str = Field(
        ...,
        description="Updated body content of the research note",
    )
    tags: List[str] = Field(
        default_factory=list,
        description="Updated categorical tags",
    )

    @field_validator("title")
    @classmethod
    def validate_title_not_empty(cls, value: str) -> str:
        trimmed = value.strip()
        if not trimmed:
            raise ValueError("Title must contain non-whitespace characters")
        return trimmed


class NoteResponse(BaseModel):
    """Schema for research note response returned by API."""

    id: str = Field(
        ...,
        description="Unique string representation of MongoDB ObjectId",
        examples=["507f1f77bcf86cd799439011"],
    )
    title: str
    content: str
    tags: List[str] = Field(default_factory=list)
    created_at: datetime
    updated_at: datetime


class AttachmentResponse(BaseModel):
    """Schema for research note image attachment response."""

    id: str = Field(
        ...,
        description="Unique string representation of MongoDB ObjectId for attachment metadata",
        examples=["507f1f77bcf86cd799439011"],
    )
    note_id: str = Field(
        ...,
        description="Parent note ObjectId string",
        examples=["507f1f77bcf86cd799439011"],
    )
    filename: str = Field(
        ...,
        description="Sanitized display filename",
        examples=["soil_sample_01.jpg"],
    )
    content_type: str = Field(
        ...,
        description="MIME type of the attachment",
        examples=["image/jpeg", "image/png", "image/webp"],
    )
    file_size: int = Field(
        ...,
        description="File size in bytes",
        examples=[204850],
    )
    caption: Optional[str] = Field(
        default=None,
        description="User-authored short caption or title",
        examples=["Soil stratification cross-section"],
    )
    description: Optional[str] = Field(
        default=None,
        description="User-authored contextual description",
        examples=["Photograph of soil pit taken at 15cm depth."],
    )
    created_at: datetime = Field(
        ...,
        description="UTC creation timestamp",
    )
