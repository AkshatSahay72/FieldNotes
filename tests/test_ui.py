"""Unit and route tests for Milestone 7 Phase 2A & 2B UI Foundation & Dashboard.

Verifies:
- GET / renders the research dashboard with valid HTML, metadata, search controls, and modals.
- GET /analytics renders the analytics shell with valid HTML, title, and metadata.
- Static assets (favicon.svg, style.css, app.js) are served with correct content-types.
- /favicon.ico route serves the SVG favicon cleanly.
- Unknown browser routes return custom HTML 404 pages.
- Unknown API routes (/api/*) strictly preserve JSON 404 responses.
- Existing API endpoint error responses preserve JSON formatting.
- Accessible navigation attributes and dynamic copyright year are present in templates.
- Complete Phase 2B Dashboard interactive elements (search mode toggle, tag filters,
  notes grid, empty/error/loading states, note modal, delete confirmation dialog, toasts).
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
    assert 'content="Explore, search, and manage scientific research notes' in html
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
    assert "initDashboard" in js_res.text


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


def test_dashboard_search_and_filter_controls(client: TestClient):
    """Verify Phase 2B search mode switcher (Text vs Semantic) and tag filter controls."""
    response = client.get("/")
    assert response.status_code == 200
    html = response.text

    # Search Mode Toggle: MongoDB Text Search vs Atlas Semantic Search
    assert 'id="mode-text-btn"' in html
    assert 'data-mode="text"' in html
    assert 'id="mode-semantic-btn"' in html
    assert 'data-mode="semantic"' in html

    # Search Form & Inputs
    assert 'id="search-form"' in html
    assert 'id="search-input"' in html
    assert 'id="btn-search-submit"' in html
    assert 'id="btn-search-clear"' in html

    # Tag filter controls
    assert 'id="tag-filter-section"' in html
    assert 'id="tag-filter-input"' in html
    assert 'id="btn-apply-tags"' in html
    assert 'id="btn-clear-tags"' in html

    # Active filters container
    assert 'id="active-filters-bar"' in html
    assert 'id="active-filter-chips"' in html
    assert 'id="btn-clear-all-filters"' in html


def test_dashboard_notes_states_and_pagination(client: TestClient):
    """Verify Phase 2B loading, error, empty state containers, notes grid, and pagination."""
    response = client.get("/")
    assert response.status_code == 200
    html = response.text

    # States
    assert 'id="notes-loading"' in html
    assert 'id="notes-error"' in html
    assert 'id="btn-retry-notes"' in html
    assert 'id="notes-empty"' in html
    assert 'id="btn-empty-create"' in html

    # Notes Card Grid
    assert 'id="notes-grid"' in html

    # Pagination controls
    assert 'id="pagination-controls"' in html
    assert 'id="btn-prev-page"' in html
    assert 'id="btn-next-page"' in html
    assert 'id="page-indicator"' in html
    assert 'id="limit-select"' in html


def test_dashboard_accessible_modals(client: TestClient):
    """Verify Phase 2B Note Create/Edit and Delete Confirmation modal dialogs."""
    response = client.get("/")
    assert response.status_code == 200
    html = response.text

    # Create / Edit Note Modal
    assert 'id="btn-open-create-modal"' in html
    assert 'id="note-modal"' in html
    assert 'role="dialog"' in html
    assert 'aria-modal="true"' in html
    assert 'id="note-form"' in html
    assert 'id="note-title-input"' in html
    assert 'id="note-content-input"' in html
    assert 'id="note-tags-input"' in html
    assert 'id="btn-save-note"' in html
    assert 'id="btn-cancel-note"' in html

    # Delete Confirmation Dialog
    assert 'id="delete-modal"' in html
    assert 'role="alertdialog"' in html
    assert 'id="delete-note-target-title"' in html
    assert 'id="btn-confirm-delete"' in html
    assert 'id="btn-cancel-delete"' in html

    # Toast Container
    assert 'id="toast-container"' in html
    assert 'aria-live="polite"' in html


def test_javascript_app_bundle_contracts(client: TestClient):
    """Verify app.js contains API endpoints, semantic search differentiation, and safe rendering."""
    js_res = client.get("/static/js/app.js")
    assert js_res.status_code == 200
    js_text = js_res.text

    # Uses existing API endpoints
    assert "/api/notes" in js_text
    assert "/api/search/semantic" in js_text

    # Explicit differentiation between semantic search and text search (no silent fallback)
    assert 'state.searchMode === "semantic"' in js_text
    assert 'state.searchMode === "text"' in js_text

    # Safe text rendering to prevent XSS
    assert "textContent" in js_text

    # Keyboard accessibility listeners
    assert '"Escape"' in js_text
    assert '"Esc"' in js_text
    assert '"Tab"' in js_text


def test_javascript_race_condition_prevention(client: TestClient):
    """Verify app.js implements monotonically increasing activeRequestId to prevent stale async responses."""
    js_res = client.get("/static/js/app.js")
    assert js_res.status_code == 200
    js_text = js_res.text

    # Monotonically increasing activeRequestId in state and loadNotes
    assert "activeRequestId: 0" in js_text
    assert "var currentRequestId = ++state.activeRequestId;" in js_text

    # Both semantic and text branches must guard against stale responses
    assert "if (currentRequestId !== state.activeRequestId) return" in js_text


def test_javascript_modal_focus_trap(client: TestClient):
    """Verify app.js implements reusable Tab and Shift+Tab focus trapping for open modals."""
    js_res = client.get("/static/js/app.js")
    assert js_res.status_code == 200
    js_text = js_res.text

    # Focus trap helpers and focusable selectors
    assert "trapModalFocus" in js_text
    assert "FOCUSABLE_SELECTORS" in js_text
    assert "getModalFocusableElements" in js_text

    # Cycling from last to first (Tab) and first to last (Shift+Tab)
    assert "event.shiftKey" in js_text
    assert "firstEl.focus()" in js_text
    assert "lastEl.focus()" in js_text


def test_javascript_tag_normalization(client: TestClient):
    """Verify app.js normalizes tag filter inputs by trimming, dropping empty/duplicate tokens."""
    js_res = client.get("/static/js/app.js")
    assert js_res.status_code == 200
    js_text = js_res.text

    assert "function normalizeTags(rawString)" in js_text
    assert "normalizeTags(tagFilterInput.value)" in js_text


def test_javascript_pagination_recovery_and_search_clearing(client: TestClient):
    """Verify app.js handles pagination past the end and synchronizes native search input clear."""
    js_res = client.get("/static/js/app.js")
    assert js_res.status_code == 200
    js_text = js_res.text

    # Pagination recovery when state.skip > 0
    assert "state.skip > 0" in js_text
    assert "navigated past the last available note" in js_text
    assert "btnPrevPage.disabled = false" in js_text
    assert "btnNextPage.disabled = true" in js_text

    # Synchronizes native search event
    assert 'searchInput.addEventListener("search"' in js_text
