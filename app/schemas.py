from pydantic import BaseModel, Field


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
