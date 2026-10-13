"""Unit and route tests for Milestone 7 Phase 2A UI Foundation.

Verifies:
- GET / renders the research dashboard shell with valid HTML, title, and meta description.
- GET /analytics renders the analytics shell with valid HTML, title, and meta description.
- Static assets (favicon.svg, style.css, app.js) are served with correct content-types.
- /favicon.ico route serves the SVG favicon cleanly.
- Unknown browser routes return custom HTML 404 pages.
- Unknown API routes (/api/*) strictly preserve JSON 404 responses.
- Existing API endpoint error responses preserve JSON formatting.
- Accessible navigation attributes and dynamic copyright year are present in templates.
"""

from datetime import datetime, timezone
import pytest
from fastapi.testclient import TestClient

from app.main import create_app


@pytest.fixture
def client():
    app = create_app()
    with TestClient(app) as test_client:
        yield test_client


def test_dashboard_renders_html_with_metadata(client: TestClient):
    """Verify GET / returns 200 OK, HTML content-type, correct title and meta description."""
    response = client.get("/")
    assert response.status_code == 200
    assert "text/html" in response.headers.get("content-type", "")

    html = response.text
    assert "<title>Fieldnote — Research Dashboard</title>" in html
    assert 'name="description"' in html
    assert 'content="Explore and manage scientific field observations' in html
    assert 'name="viewport"' in html
    assert 'content="width=device-width, initial-scale=1.0"' in html


def test_analytics_renders_html_with_metadata(client: TestClient):
    """Verify GET /analytics returns 200 OK, HTML content-type, correct title and meta description."""
    response = client.get("/analytics")
    assert response.status_code == 200
    assert "text/html" in response.headers.get("content-type", "")

    html = response.text
    assert "<title>Fieldnote — Analytics &amp; Pipeline Insights</title>" in html
    assert 'name="description"' in html
    assert 'content="Real-time MongoDB aggregation pipeline insights' in html


def test_static_favicon_and_ico_routes(client: TestClient):
    """Verify /static/favicon.svg and /favicon.ico are served successfully."""
    svg_res = client.get("/static/favicon.svg")
    assert svg_res.status_code == 200
    assert "image/svg+xml" in svg_res.headers.get("content-type", "")
    assert "<svg" in svg_res.text

    ico_res = client.get("/favicon.ico")
    assert ico_res.status_code == 200
    assert "image/svg+xml" in ico_res.headers.get("content-type", "")
    assert "<svg" in ico_res.text


def test_static_css_and_js_served(client: TestClient):
    """Verify style.css and app.js are mounted and served via /static/."""
    css_res = client.get("/static/css/style.css")
    assert css_res.status_code == 200
    assert "text/css" in css_res.headers.get("content-type", "")
    assert "--color-primary" in css_res.text

    js_res = client.get("/static/js/app.js")
    assert js_res.status_code == 200
    assert "javascript" in js_res.headers.get("content-type", "")
    assert "initMobileNavigation" in js_res.text


def test_unknown_browser_route_returns_html_404(client: TestClient):
    """Verify unknown browser URL returns custom HTML 404 page."""
    response = client.get("/unmapped-research-page", headers={"Accept": "text/html"})
    assert response.status_code == 404
    assert "text/html" in response.headers.get("content-type", "")

    html = response.text
    assert "<title>Fieldnote — Page Not Found</title>" in html
    assert "404" in html
    assert "Page Not Found" in html
    assert 'href="/"' in html  # Return to Dashboard link


def test_unknown_api_route_preserves_json_404(client: TestClient):
    """Verify unknown /api/* URL returns JSON 404 without HTML."""
    response = client.get("/api/unmapped-endpoint")
    assert response.status_code == 404
    assert "application/json" in response.headers.get("content-type", "")
    data = response.json()
    assert "detail" in data
    assert data["detail"] == "Not Found"


def test_api_json_accept_header_preserves_json_404(client: TestClient):
    """Verify non-API URL with Accept: application/json returns JSON 404."""
    response = client.get("/unmapped-endpoint", headers={"Accept": "application/json"})
    assert response.status_code == 404
    assert "application/json" in response.headers.get("content-type", "")
    assert response.json()["detail"] == "Not Found"


def test_navigation_elements_and_dynamic_year(client: TestClient):
    """Verify logo link, mobile menu accessibility attributes, and dynamic year."""
    response = client.get("/")
    assert response.status_code == 200
    html = response.text

    # Clickable Logo linking to root
    assert '<a href="/" class="brand-logo"' in html

    # Accessible mobile navigation toggle
    assert 'id="mobile-menu-toggle"' in html
    assert 'aria-label="Toggle navigation menu"' in html
    assert 'aria-expanded="false"' in html
    assert 'aria-controls="mobile-nav-drawer"' in html

    # Mobile drawer and backdrop
    assert 'id="mobile-nav-drawer"' in html
    assert 'id="mobile-nav-backdrop"' in html

    # Valid navigation destinations
    assert 'href="/analytics"' in html
    assert 'href="/docs"' in html

    # Dynamic year matches current UTC year
    current_year = str(datetime.now(timezone.utc).year)
    assert f'<span id="current-year">{current_year}</span>' in html

    # Omit invented contact links (no placeholder mailto or tel)
    assert "mailto:" not in html
    assert "tel:" not in html
