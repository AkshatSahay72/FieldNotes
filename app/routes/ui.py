from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Optional
from fastapi import APIRouter, Depends, Request, status
from fastapi.responses import HTMLResponse, FileResponse, RedirectResponse
from fastapi.templating import Jinja2Templates
from pymongo.database import Database

from app.config import AppMode, Settings, get_settings
from app.db import get_database
from app.routes.auth import get_optional_current_user
from app.schemas import UserResponse

_app_dir = Path(__file__).resolve().parent.parent
_templates_dir = _app_dir / "templates"
_static_dir = _app_dir / "static"

templates = Jinja2Templates(directory=str(_templates_dir))

router = APIRouter(include_in_schema=False)


@router.get("/login", response_class=HTMLResponse)
def get_login(
    request: Request,
    settings: Settings = Depends(get_settings),
    current_user: Optional[UserResponse] = Depends(get_optional_current_user),
    db: Database = Depends(get_database),
) -> Any:
    """Render the Fieldnote owner authentication view."""
    if current_user is not None:
        return RedirectResponse(url="/", status_code=status.HTTP_302_FOUND)

    try:
        has_owner = db["users"].count_documents({}) >= 1
    except Exception:
        has_owner = False

    return templates.TemplateResponse(
        request=request,
        name="login.html",
        context={
            "active_page": "login",
            "current_year": datetime.now(timezone.utc).year,
            "demo_mode": settings.is_demo_mode,
            "has_owner": has_owner,
            "current_user": None,
        },
    )


@router.get("/", response_class=HTMLResponse)
def get_dashboard(
    request: Request,
    settings: Settings = Depends(get_settings),
    current_user: Optional[UserResponse] = Depends(get_optional_current_user),
) -> Any:
    """Render the Fieldnote research dashboard shell."""
    if settings.resolved_app_mode == AppMode.AUTHENTICATED and current_user is None:
        return RedirectResponse(url="/login", status_code=status.HTTP_302_FOUND)

    return templates.TemplateResponse(
        request=request,
        name="index.html",
        context={
            "active_page": "dashboard",
            "current_year": datetime.now(timezone.utc).year,
            "demo_mode": settings.is_demo_mode,
            "current_user": current_user,
        },
    )


@router.get("/analytics", response_class=HTMLResponse)
def get_analytics(
    request: Request,
    settings: Settings = Depends(get_settings),
    current_user: Optional[UserResponse] = Depends(get_optional_current_user),
) -> Any:
    """Render the Fieldnote aggregation analytics shell."""
    if settings.resolved_app_mode == AppMode.AUTHENTICATED and current_user is None:
        return RedirectResponse(url="/login", status_code=status.HTTP_302_FOUND)

    return templates.TemplateResponse(
        request=request,
        name="analytics.html",
        context={
            "active_page": "analytics",
            "current_year": datetime.now(timezone.utc).year,
            "demo_mode": settings.is_demo_mode,
            "current_user": current_user,
        },
    )


@router.get("/favicon.ico", include_in_schema=False)
def get_favicon() -> FileResponse:
    """Serve the SVG favicon directly for browser favicon.ico requests."""
    return FileResponse(_static_dir / "favicon.svg", media_type="image/svg+xml")
