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
    assert "<title>Fieldnote — Personal Memory Journal</title>" in html
    assert 'name="description"' in html
    assert 'content="Capture, recall, and revisit what you experience, learn, and discover' in html
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


def test_evidence_gallery_and_attachment_modals_markup(client: TestClient):
    """Verify GET / renders Evidence modal, Lightbox modal, and Delete Attachment dialog markup."""
    response = client.get("/")
    assert response.status_code == 200
    html = response.text

    # Evidence Modal and Upload Form
    assert 'id="evidence-modal"' in html
    assert 'id="evidence-modal-backdrop"' in html
    assert 'id="evidence-modal-note-title"' in html
    assert 'id="btn-close-evidence-modal"' in html
    assert 'id="evidence-upload-form"' in html
    assert 'id="evidence-file-input"' in html
    assert 'id="evidence-caption-input"' in html
    assert 'id="evidence-desc-input"' in html
    assert 'id="btn-upload-evidence"' in html
    assert 'accept=".jpg,.jpeg,.png,.webp,image/jpeg,image/png,image/webp"' in html

    # Evidence Gallery Grid and Feedback States
    assert 'id="evidence-grid"' in html
    assert 'id="evidence-empty"' in html
    assert 'id="evidence-loading"' in html
    assert 'id="evidence-error"' in html
    assert 'id="btn-retry-evidence"' in html

    # Lightbox Modal
    assert 'id="lightbox-modal"' in html
    assert 'id="lightbox-modal-backdrop"' in html
    assert 'id="btn-close-lightbox-modal"' in html
    assert 'id="btn-close-lightbox"' in html
    assert 'id="lightbox-img"' in html
    assert 'id="lightbox-caption"' in html
    assert 'id="lightbox-desc"' in html
    assert 'id="lightbox-meta"' in html

    # Delete Attachment Confirmation Modal
    assert 'id="delete-attachment-modal"' in html
    assert 'id="delete-attachment-modal-backdrop"' in html
    assert 'id="delete-attachment-target-name"' in html
    assert 'id="btn-close-delete-attachment-modal"' in html
    assert 'id="btn-cancel-delete-attachment"' in html
    assert 'id="btn-confirm-delete-attachment"' in html


def test_javascript_evidence_gallery_and_upload_contracts(client: TestClient):
    """Verify app.js implements the complete Phase 2C.1 evidence gallery and attachment contract."""
    js_res = client.get("/static/js/app.js")
    assert js_res.status_code == 200
    js_text = js_res.text

    # Note card integration
    assert "📷 Evidence" in js_text
    assert "action-btn-accent" in js_text
    assert "openEvidenceModal(note.id, note.title, evidenceBtn)" in js_text

    # Endpoints
    assert "/attachments" in js_text
    assert "/download" in js_text

    # Multipart Upload without manual Content-Type
    assert "new FormData()" in js_text
    assert 'formData.append("file", file)' in js_text
    assert 'formData.append("caption", captionVal)' in js_text
    assert 'formData.append("description", descVal)' in js_text
    assert "btnUploadEvidence.disabled = true" in js_text

    # Client-side 5 MB file size and MIME checks
    assert "5 * 1024 * 1024" in js_text
    assert "image/jpeg" in js_text
    assert "image/png" in js_text
    assert "image/webp" in js_text

    # Broken image load fallback
    assert "img.onerror = null" in js_text
    assert "evidence-broken" in js_text

    # Delete attachment contract: HTTP 204 handling (no JSON parsing on 204)
    assert 'res.status !== 204' in js_text
    assert "btnConfirmDeleteAttachment.disabled = true" in js_text

    # Keyboard accessibility: Escape and Tab handlers for evidence, lightbox, and delete attachment modals
    assert "lightboxModal.classList.contains(\"is-open\")" in js_text
    assert "deleteAttachmentModal.classList.contains(\"is-open\")" in js_text
    assert "evidenceModal.classList.contains(\"is-open\")" in js_text
    assert "trapModalFocus(lightboxModal, e)" in js_text
    assert "trapModalFocus(deleteAttachmentModal, e)" in js_text
    assert "trapModalFocus(evidenceModal, e)" in js_text


def test_javascript_phase_2c1_corrections(client: TestClient):
    """Verify Phase 2C.1 corrections: scroll-locking selector, stale evidence guarding, dismissal cleanup, and post-delete focus."""
    js_res = client.get("/static/js/app.js")
    assert js_res.status_code == 200
    js_text = js_res.text

    # 1. Correct modal dialog selector for scroll locking in closeDialog
    assert 'document.querySelector(".modal-dialog.is-open")' in js_text
    assert 'document.querySelector(".modal.is-open")' not in js_text

    # 2. Stale evidence response protection with activeEvidenceRequestId and modal-open checks
    assert "activeEvidenceRequestId: 0" in js_text
    assert "var currentEvidenceRequestId = ++state.activeEvidenceRequestId;" in js_text
    assert "function isRequestCurrent()" in js_text
    assert "currentEvidenceRequestId === state.activeEvidenceRequestId" in js_text
    assert 'evidenceModal.classList.contains("is-open")' in js_text
    assert "state.activeEvidenceNote.id === noteId" in js_text
    assert "function closeEvidenceModal()" in js_text
    assert "state.activeEvidenceRequestId++;" in js_text

    # 3. Clearing pending deletion state across all dismissal paths
    assert "function closeDeleteAttachmentModal()" in js_text
    assert "state.attachmentToDelete = null;" in js_text
    assert "btnCloseDeleteAttachmentModal.addEventListener(\"click\", closeDeleteAttachmentModal)" in js_text
    assert "btnCancelDeleteAttachment.addEventListener(\"click\", closeDeleteAttachmentModal)" in js_text
    assert "deleteAttachmentModalBackdrop.addEventListener(\"click\", closeDeleteAttachmentModal)" in js_text

    # 4. Keyboard focus preservation after deletion without targeting unmounted DOM elements
    assert "deleteAttachmentModal._previousFocus = null;" in js_text
    assert "btnUploadEvidence.focus()" in js_text
    assert "btnRetryEvidence.focus()" in js_text


def test_analytics_page_markup_and_controls(client: TestClient):
    """Verify Phase 2C.2 /analytics page markup, sections, accessible containers, and controls."""
    res = client.get("/analytics")
    assert res.status_code == 200
    html = res.text

    # 1. Main container and header actions
    assert 'id="analytics-dashboard"' in html
    assert 'id="btn-refresh-analytics"' in html
    assert 'Refresh Analytics' in html

    # 2. Section A: Research Overview cards
    assert 'id="section-overview"' in html
    assert 'id="overview-loading"' in html
    assert 'id="overview-error"' in html
    assert 'id="overview-error-desc"' in html
    assert 'id="btn-retry-overview"' in html
    assert 'id="overview-grid"' in html
    assert 'id="stat-total-notes"' in html
    assert 'id="stat-total-attachments"' in html
    assert 'id="stat-notes-with-tags"' in html

    # 3. Section B: Tag Distribution
    assert 'id="section-tags"' in html
    assert 'id="tags-loading"' in html
    assert 'id="tags-error"' in html
    assert 'id="tags-error-desc"' in html
    assert 'id="btn-retry-tags"' in html
    assert 'id="tags-empty"' in html
    assert 'id="tags-chart-container"' in html
    assert 'id="tags-chart-bars"' in html

    # 4. Section C: Research Activity
    assert 'id="section-activity"' in html
    assert 'id="activity-loading"' in html
    assert 'id="activity-error"' in html
    assert 'id="activity-error-desc"' in html
    assert 'id="btn-retry-activity"' in html
    assert 'id="activity-empty"' in html
    assert 'id="activity-chart-container"' in html
    assert 'id="activity-timeline-list"' in html

    # 5. Section D: Evidence Distribution with accessible zero-toggle
    assert 'id="section-attachments"' in html
    assert 'id="toggle-include-zero"' in html
    assert 'Include notes with zero attachments' in html
    assert 'id="attachments-loading"' in html
    assert 'id="attachments-error"' in html
    assert 'id="attachments-error-desc"' in html
    assert 'id="btn-retry-attachments"' in html
    assert 'id="attachments-empty"' in html
    assert 'id="attachments-empty-desc"' in html
    assert 'id="attachments-chart-container"' in html
    assert 'id="attachments-count-info"' in html
    assert 'id="attachments-chart-list"' in html

    # 6. Accessibility attributes
    assert 'aria-live="polite"' in html
    assert 'role="alert"' in html
    assert 'role="region"' in html

    # 7. Navigation footer links
    assert 'href="/"' in html
    assert 'href="/api/analytics/overview"' in html


def test_analytics_javascript_contracts_and_resilience(client: TestClient):
    """Verify Phase 2C.2 analytics JS logic, request-race guards, error handling, and safe DOM construction."""
    res = client.get("/static/js/app.js")
    assert res.status_code == 200
    js_text = res.text

    # 1. Initialization and DOM mount
    assert "function initAnalytics()" in js_text
    assert "initAnalytics();" in js_text
    assert 'document.getElementById("analytics-dashboard")' in js_text

    # 2. Independent section request IDs for out-of-order response protection
    assert "reqIds = {" in js_text
    assert "overview: 0" in js_text
    assert "tags: 0" in js_text
    assert "activity: 0" in js_text
    assert "attachments: 0" in js_text

    # 3. Section endpoint URLs and parameter encoding
    assert '"/api/analytics/overview"' in js_text
    assert '"/api/analytics/tags"' in js_text
    assert '"/api/analytics/activity"' in js_text
    assert '"/api/analytics/attachments?include_zero="' in js_text
    assert '(includeZero ? "true" : "false")' in js_text

    # 4. Independent section loaders & error retry hooks
    assert "btnRetryOverview.addEventListener" in js_text
    assert "btnRetryTags.addEventListener" in js_text
    assert "btnRetryActivity.addEventListener" in js_text
    assert "btnRetryAttachments.addEventListener" in js_text
    assert "toggleIncludeZero.addEventListener" in js_text
    assert "btnRefresh.addEventListener" in js_text

    # 5. Fault-isolated parallel loading (Promise.allSettled)
    assert 'typeof Promise.allSettled === "function"' in js_text
    assert "Promise.allSettled([" in js_text

    # 6. Top-25 display limiter and count messaging
    assert "var maxDisplay = 25;" in js_text
    assert "attachments.slice(0, maxDisplay)" in js_text
    assert '"Showing top " + maxDisplay + " of "' in js_text
    assert '"Showing " + totalReturned + " of "' in js_text

    # 7. UTC research activity formatting without date fabrication
    assert 'item.date + " (UTC)"' in js_text
    assert 'renderResearchActivity(activity)' in js_text

    # 8. Safe DOM construction (preventing XSS)
    assert 'titleSpan.textContent = item.title;' in js_text
    assert 'titleSpan.title = item.title;' in js_text
    assert 'titleSpan.setAttribute("aria-label", item.title);' in js_text
    assert 'label.textContent = item.tag;' in js_text
    assert 'fill.setAttribute("role", "progressbar");' in js_text


def test_analytics_css_styles(client: TestClient):
    """Verify Phase 2C.2 analytics visual stylesheet classes and responsive design hooks."""
    res = client.get("/static/css/style.css")
    assert res.status_code == 200
    css = res.text

    # Layout and card containers
    assert ".analytics-container" in css
    assert ".analytics-header" in css
    assert ".analytics-stats-grid" in css
    assert ".stat-card" in css
    assert ".stat-value" in css
    assert ".analytics-charts-grid" in css

    # Chart bars and rows
    assert ".chart-container" in css
    assert ".chart-bars-list" in css
    assert ".chart-bar-row" in css
    assert ".chart-bar-track" in css
    assert ".chart-bar-fill" in css
    assert ".chart-bar-title-truncate" in css
    assert ".tag-pill-label" in css

    assert ".fill-primary" in css
    assert ".fill-accent" in css
    assert ".fill-secondary" in css


def test_demo_mode_banner_rendered_conditionally():
    """Verify demo notice banner is rendered when DEMO_MODE is True and omitted when False."""
    from app.config import Settings, get_settings

    demo_settings = Settings(
        MONGODB_URI="mongodb://localhost:27017",
        DATABASE_NAME="fieldnote_demo",
        DEMO_MODE=True,
        APP_ENV="testing",
        _env_file=None,
    )
    normal_settings = Settings(
        MONGODB_URI="mongodb://localhost:27017",
        DATABASE_NAME="fieldnote_private",
        APP_MODE="authenticated",
        DEMO_MODE=False,
        APP_ENV="testing",
        _env_file=None,
    )

    app_demo = create_app()
    app_demo.dependency_overrides[get_settings] = lambda: demo_settings
    with TestClient(app_demo) as demo_client:
        res = demo_client.get("/")
        assert res.status_code == 200
        assert "demo-banner" in res.text
        assert "Public demonstration environment" in res.text

    app_normal = create_app()
    app_normal.dependency_overrides[get_settings] = lambda: normal_settings
    with TestClient(app_normal) as normal_client:
        res_normal = normal_client.get("/")
        assert res_normal.status_code == 200
        assert "demo-banner" not in res_normal.text


def test_login_route_renders_and_redirects():
    """Verify /login renders authentication view, and unauthenticated visitors are redirected in authenticated mode."""
    from app.config import Settings, get_settings
    from tests.test_auth import FakeAuthDatabase

    mock_db = FakeAuthDatabase()
    auth_settings = Settings(
        MONGODB_URI="mongodb://localhost:27017",
        DATABASE_NAME="fieldnote_auth_test",
        APP_MODE="authenticated",
        DEMO_MODE=False,
        APP_ENV="testing",
        _env_file=None,
    )

    app = create_app()
    from app.db import get_database
    app.dependency_overrides[get_settings] = lambda: auth_settings
    app.dependency_overrides[get_database] = lambda: mock_db

    with TestClient(app) as test_client:
        # Unauthenticated user requesting / should get 302 redirect to /login
        res_root = test_client.get("/", follow_redirects=False)
        assert res_root.status_code == 302
        assert res_root.headers["location"] == "/login"

        # Unauthenticated user requesting /analytics should get 302 redirect to /login
        res_analytics = test_client.get("/analytics", follow_redirects=False)
        assert res_analytics.status_code == 302
        assert res_analytics.headers["location"] == "/login"

        # Direct GET /login renders 200 OK
        res_login = test_client.get("/login")
        assert res_login.status_code == 200
        assert "text/html" in res_login.headers.get("content-type", "")
        html = res_login.text
        assert 'id="auth-email"' in html
        assert 'id="auth-password"' in html
        assert 'id="btn-auth-submit"' in html
        assert "demo-banner" not in html
        assert "Single-owner personal archive" in html or "single-owner" in html.lower()

        # When no owner exists yet, view indicates initial setup
        assert "Initial Owner Setup" in html or "Initial Setup" in html

        # Register owner account via API
        reg_res = test_client.post(
            "/api/auth/register",
            json={"email": "owner@example.com", "password": "SecurePassword123!"},
        )
        assert reg_res.status_code == 201

        # Now when authenticated, visiting /login redirects to /
        res_login_authed = test_client.get("/login", follow_redirects=False)
        assert res_login_authed.status_code == 302
        assert res_login_authed.headers["location"] == "/"

        # Visiting / directly succeeds (200) and displays owner email and Sign Out button
        res_home_authed = test_client.get("/", follow_redirects=False)
        assert res_home_authed.status_code == 200
        assert "owner@example.com" in res_home_authed.text
        assert "btn-logout" in res_home_authed.text
        assert "Sign Out" in res_home_authed.text
        assert "demo-banner" not in res_home_authed.text

        # Logout via API
        from app.services.auth import get_active_session
        csrf_token = reg_res.json()["csrf_token"]
        logout_res = test_client.post(
            "/api/auth/logout",
            headers={"x-csrf-token": csrf_token},
        )
        assert logout_res.status_code == 200

        # After logout, accessing / redirects back to /login
        res_after_logout = test_client.get("/", follow_redirects=False)
        assert res_after_logout.status_code == 302
        assert res_after_logout.headers["location"] == "/login"
