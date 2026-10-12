import logging
from contextlib import asynccontextmanager
from typing import AsyncGenerator, Optional
from fastapi import FastAPI, Depends, Request, Response, status
from pymongo import MongoClient

from app.config import Settings, get_settings
from app.db import create_mongo_client, close_mongo_client, ping_database, init_db_indexes
from app.schemas import HealthResponse
from app.routes.notes import router as notes_router
from app.routes.attachments import router as attachments_router
from app.routes.analytics import router as analytics_router

logger = logging.getLogger(__name__)


def get_db_client(request: Request) -> Optional[MongoClient]:
    """Dependency to retrieve the PyMongo client from application state."""
    return getattr(request.app.state, "db_client", None)


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncGenerator[None, None]:
    """Manage application lifespan: initialize, index, and cleanly close PyMongo client."""
    client: Optional[MongoClient] = None
    try:
        settings = get_settings()
        client = create_mongo_client(settings)
        app.state.db_client = client
        app.state.db = client[settings.database_name]
        logger.info("MongoDB client initialized for database: %s", settings.database_name)
        # Initialize justified indexes in non-testing environments
        if settings.app_env != "testing":
            init_db_indexes(app.state.db)
    except Exception as err:
        logger.error("Failed to initialize MongoDB client: %s", type(err).__name__)
        app.state.db_client = None
        app.state.db = None

    yield

    if client is not None:
        logger.info("Closing MongoDB client connection pool")
        close_mongo_client(client)


def create_app() -> FastAPI:
    """Application factory for Fieldnote API."""
    application = FastAPI(
        title="Fieldnote API",
        description="Research Notes & Evidence Management System API",
        version="0.5.0",
        lifespan=lifespan,
    )

    # Register modular routers
    application.include_router(notes_router)
    application.include_router(attachments_router)
    application.include_router(analytics_router)

    @application.get(
        "/health",
        response_model=HealthResponse,
        summary="Service Health Check",
        tags=["Health"],
    )
    @application.get(
        "/api/health",
        response_model=HealthResponse,
        summary="Service Health Check (API prefix)",
        tags=["Health"],
        include_in_schema=False,
    )
    def health_check(
        response: Response,
        settings: Settings = Depends(get_settings),
        client: Optional[MongoClient] = Depends(get_db_client),
    ) -> HealthResponse:
        """Return application and database connection health status.
        
        Distinguishes application availability from database connectivity.
        Returns 200 OK if both app and database are healthy.
        Returns 503 Service Unavailable if database is unreachable, without leaking internal details.
        """
        is_db_connected = ping_database(client)

        if not is_db_connected:
            response.status_code = status.HTTP_503_SERVICE_UNAVAILABLE
            return HealthResponse(
                status="unhealthy",
                app="ok",
                database="disconnected",
                environment=settings.app_env,
            )

        return HealthResponse(
            status="healthy",
            app="ok",
            database="connected",
            environment=settings.app_env,
        )

    return application


app = create_app()
