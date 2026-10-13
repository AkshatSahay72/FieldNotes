from datetime import datetime, timezone
from pathlib import Path
from fastapi import APIRouter, Depends, Request
from fastapi.responses import HTMLResponse, FileResponse
from fastapi.templating import Jinja2Templates

from app.config import Settings, get_settings

_app_dir = Path(__file__).resolve().parent.parent
_templates_dir = _app_dir / "templates"
_static_dir = _app_dir / "static"

templates = Jinja2Templates(directory=str(_templates_dir))

router = APIRouter(include_in_schema=False)


@router.get("/", response_class=HTMLResponse)
def get_dashboard(
    request: Request,
    settings: Settings = Depends(get_settings),
) -> HTMLResponse:
    """Render the Fieldnote research dashboard shell."""
    return templates.TemplateResponse(
        request=request,
        name="index.html",
        context={
            "active_page": "dashboard",
            "current_year": datetime.now(timezone.utc).year,
            "demo_mode": settings.demo_mode,
        },
    )


@router.get("/analytics", response_class=HTMLResponse)
def get_analytics(
    request: Request,
    settings: Settings = Depends(get_settings),
) -> HTMLResponse:
    """Render the Fieldnote aggregation analytics shell."""
    return templates.TemplateResponse(
        request=request,
        name="analytics.html",
        context={
            "active_page": "analytics",
            "current_year": datetime.now(timezone.utc).year,
            "demo_mode": settings.demo_mode,
        },
    )


@router.get("/favicon.ico", include_in_schema=False)
def get_favicon() -> FileResponse:
    """Serve the SVG favicon directly for browser favicon.ico requests."""
    return FileResponse(_static_dir / "favicon.svg", media_type="image/svg+xml")
