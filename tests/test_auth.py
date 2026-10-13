"""Unit and integration tests for Fieldnote first-party authentication and session management.

Verifies:
- User registration with Argon2id password hashing and session creation
- Duplicate email account rejection (409 Conflict)
- Safe input validation (invalid email, short or whitespace passwords)
- Valid login with session rotation (session fixation protection)
- Invalid login (incorrect password, unknown email) returns non-revealing 401
- Authenticated and unauthenticated access to /api/auth/me and /api/auth/session
- Session expiration and revocation enforcement
- Logout revoking server session and clearing cookies
- CSRF protection: missing or mismatched X-CSRF-Token returns 403 Forbidden
- Origin validation: mismatched cross-origin request returns 403 Forbidden
- Cookie attributes (HttpOnly, SameSite=lax, Path=/, Secure in production)
- Plaintext passwords never stored in database documents or returned in API responses
- Rate limiting on authentication endpoints returning 429 Too Many Requests
"""

from copy import deepcopy
from datetime import datetime, timezone, timedelta
from typing import Optional
from bson import ObjectId
import pytest
from fastapi.testclient import TestClient

from app.main import create_app
from app.db import get_database
from app.config import Settings, get_settings
from app.services.auth import (
    hash_password,
    verify_password,
    auth_rate_limiter,
)


class FakeAuthCollection:
    """In-memory collection simulating PyMongo operations for users and sessions."""

    def __init__(self):
        self.docs = {}

    def count_documents(self, filter_dict=None):
        if not filter_dict:
            return len(self.docs)
        count = 0
        for doc in self.docs.values():
            match = True
            for k, v in filter_dict.items():
                if doc.get(k) != v:
                    match = False
                    break
            if match:
                count += 1
        return count

    def insert_one(self, doc):
        oid = doc.get("_id") or ObjectId()
        stored = deepcopy(doc)
        stored["_id"] = oid
        self.docs[oid] = stored

        class InsertResult:
            inserted_id = oid

        return InsertResult()

    def find_one(self, filter_dict):
        if not filter_dict:
            return None
        for doc in self.docs.values():
            match = True
            for k, v in filter_dict.items():
                if k == "_id":
                    if doc.get("_id") != v:
                        match = False
                        break
                elif isinstance(v, dict) and "$gt" in v:
                    # Compare datetime greater-than
                    val = doc.get(k)
                    if not val or val <= v["$gt"]:
                        match = False
                        break
                elif doc.get(k) != v:
                    match = False
                    break
            if match:
                return deepcopy(doc)
        return None

    def update_one(self, filter_dict, update_dict):
        target_doc = None
        target_oid = None
        for oid, doc in self.docs.items():
            match = True
            for k, v in filter_dict.items():
                if doc.get(k) != v:
                    match = False
                    break
            if match:
                target_doc = doc
                target_oid = oid
                break

        if not target_doc:
            class NoUpdateResult:
                modified_count = 0
                matched_count = 0
            return NoUpdateResult()

        set_fields = update_dict.get("$set", {})
        target_doc.update(deepcopy(set_fields))

        class UpdateResult:
            modified_count = 1
            matched_count = 1

        return UpdateResult()

    def update_many(self, filter_dict, update_dict):
        count = 0
        set_fields = update_dict.get("$set", {})
        for doc in self.docs.values():
            match = True
            for k, v in filter_dict.items():
                if doc.get(k) != v:
                    match = False
                    break
            if match:
                doc.update(deepcopy(set_fields))
                count += 1

        class UpdateManyResult:
            modified_count = count

        return UpdateManyResult()

    def create_index(self, keys, name=None, **kwargs):
        return name or "idx"


class FakeAuthDatabase:
    """In-memory database simulation for authentication tests."""

    def __init__(self):
        self.collections = {}

    def __getitem__(self, name):
        if name not in self.collections:
            self.collections[name] = FakeAuthCollection()
        return self.collections[name]


@pytest.fixture
def fake_auth_db():
    return FakeAuthDatabase()


@pytest.fixture
def auth_client(fake_auth_db):
    app = create_app()
    app.dependency_overrides[get_database] = lambda: fake_auth_db
    auth_rate_limiter.reset()

    with TestClient(app, base_url="http://localhost:8000") as client:
        yield client

    app.dependency_overrides.clear()
    auth_rate_limiter.reset()


# ==============================================================================
# 1. Registration Tests
# ==============================================================================

def test_register_user_success(auth_client, fake_auth_db):
    """Verify registration creates user with Argon2id hash, issues cookies, and returns session."""
    payload = {
        "email": "Jane.Doe@example.com",
        "password": "SecurePassword123!",
    }
    res = auth_client.post("/api/auth/register", json=payload)
    assert res.status_code == 201

    data = res.json()
    assert "user" in data
    assert data["user"]["email"] == "jane.doe@example.com"  # Normalized lowercase
    assert "id" in data["user"]
    assert "password" not in data["user"]
    assert "hashed_password" not in data["user"]
    assert "csrf_token" in data
    assert len(data["csrf_token"]) > 20
    assert "expires_at" in data

    # Verify cookies
    cookies = res.cookies
    assert "fieldnote_session" in cookies
    assert "fieldnote_csrf" in cookies

    # Verify database document
    users = list(fake_auth_db["users"].docs.values())
    assert len(users) == 1
    stored_user = users[0]
    assert stored_user["email"] == "jane.doe@example.com"
    # Plaintext password is NEVER stored
    assert stored_user["hashed_password"] != "SecurePassword123!"
    assert stored_user["hashed_password"].startswith("$argon2id$")
    assert verify_password("SecurePassword123!", stored_user["hashed_password"]) is True

    # Verify session document
    sessions = list(fake_auth_db["sessions"].docs.values())
    assert len(sessions) == 1
    stored_session = sessions[0]
    assert stored_session["session_id"] == cookies["fieldnote_session"]
    assert stored_session["csrf_token"] == data["csrf_token"]
    assert stored_session["is_revoked"] is False


def test_register_duplicate_email_fails(auth_client, fake_auth_db):
    """Verify registering an existing email returns 409 Conflict."""
    payload = {"email": "duplicate@example.com", "password": "Password123!"}
    res1 = auth_client.post("/api/auth/register", json=payload)
    assert res1.status_code == 201

    res2 = auth_client.post("/api/auth/register", json=payload)
    assert res2.status_code == 409
    assert "already exists" in res2.json()["detail"].lower()


def test_register_invalid_inputs(auth_client):
    """Verify validation catches short passwords, blank passwords, and malformed emails."""
    # Password too short (< 8 chars)
    res = auth_client.post(
        "/api/auth/register",
        json={"email": "valid@example.com", "password": "short"},
    )
    assert res.status_code == 422

    # Blank password
    res = auth_client.post(
        "/api/auth/register",
        json={"email": "valid@example.com", "password": "        "},
    )
    assert res.status_code == 422

    # Malformed email
    res = auth_client.post(
        "/api/auth/register",
        json={"email": "not-an-email", "password": "ValidPassword123!"},
    )
    assert res.status_code == 422


# ==============================================================================
# 2. Login Tests
# ==============================================================================

def test_login_success_and_session_rotation(auth_client, fake_auth_db):
    """Verify valid login authenticates, rotates session ID to prevent fixation, and sets cookies."""
    # Pre-register user
    auth_client.post(
        "/api/auth/register",
        json={"email": "researcher@fieldnote.org", "password": "FieldnoteSecret1!"},
    )

    # Initial session ID from registration
    reg_session_id = auth_client.cookies.get("fieldnote_session")
    assert reg_session_id is not None

    # Login with credentials
    login_payload = {
        "email": "researcher@fieldnote.org",
        "password": "FieldnoteSecret1!",
    }
    res = auth_client.post("/api/auth/login", json=login_payload)
    assert res.status_code == 200

    data = res.json()
    assert data["user"]["email"] == "researcher@fieldnote.org"
    new_session_id = res.cookies.get("fieldnote_session")

    # Session ID must be rotated upon authentication
    assert new_session_id != reg_session_id

    # Previous session must be revoked in database
    old_session = fake_auth_db["sessions"].find_one({"session_id": reg_session_id})
    assert old_session["is_revoked"] is True

    # New session must be active in database
    new_session = fake_auth_db["sessions"].find_one({"session_id": new_session_id})
    assert new_session["is_revoked"] is False


def test_login_invalid_password_returns_401(auth_client):
    """Verify incorrect password returns generic 401 Unauthorized without leaking details."""
    auth_client.post(
        "/api/auth/register",
        json={"email": "user@example.com", "password": "CorrectPassword123!"},
    )

    res = auth_client.post(
        "/api/auth/login",
        json={"email": "user@example.com", "password": "WrongPassword999!"},
    )
    assert res.status_code == 401
    assert res.json()["detail"] == "Invalid email or password"


def test_login_nonexistent_user_returns_401(auth_client):
    """Verify unknown email returns generic 401 Unauthorized to prevent account enumeration."""
    res = auth_client.post(
        "/api/auth/login",
        json={"email": "unknown@example.com", "password": "SomePassword123!"},
    )
    assert res.status_code == 401
    assert res.json()["detail"] == "Invalid email or password"


# ==============================================================================
# 3. Session Endpoints & Expiration/Revocation Tests
# ==============================================================================

def test_get_current_session_authenticated(auth_client):
    """Verify /api/auth/me returns current user profile when session cookie is provided."""
    reg_res = auth_client.post(
        "/api/auth/register",
        json={"email": "logged.in@example.com", "password": "ValidPassword123!"},
    )
    assert reg_res.status_code == 201

    me_res = auth_client.get("/api/auth/me")
    assert me_res.status_code == 200
    data = me_res.json()
    assert data["user"]["email"] == "logged.in@example.com"
    assert "csrf_token" in data

    # Test /api/auth/session alias
    session_res = auth_client.get("/api/auth/session")
    assert session_res.status_code == 200
    assert session_res.json()["user"]["email"] == "logged.in@example.com"


def test_get_current_session_unauthenticated(auth_client):
    """Verify /api/auth/me returns 401 when no session cookie is sent."""
    auth_client.cookies.clear()
    res = auth_client.get("/api/auth/me")
    assert res.status_code == 401
    assert "Not authenticated" in res.json()["detail"]


def test_session_expiration_enforced(auth_client, fake_auth_db):
    """Verify expired session in database returns 401."""
    auth_client.post(
        "/api/auth/register",
        json={"email": "expired@example.com", "password": "Password12345!"},
    )
    session_id = auth_client.cookies.get("fieldnote_session")

    # Manually expire session in test DB
    past_time = datetime.now(timezone.utc) - timedelta(hours=1)
    fake_auth_db["sessions"].update_one(
        {"session_id": session_id},
        {"$set": {"expires_at": past_time}},
    )

    res = auth_client.get("/api/auth/me")
    assert res.status_code == 401
    assert "expired" in res.json()["detail"].lower()


def test_session_revocation_enforced(auth_client, fake_auth_db):
    """Verify revoked session in database returns 401."""
    auth_client.post(
        "/api/auth/register",
        json={"email": "revoked@example.com", "password": "Password12345!"},
    )
    session_id = auth_client.cookies.get("fieldnote_session")

    # Manually revoke session in test DB
    fake_auth_db["sessions"].update_one(
        {"session_id": session_id},
        {"$set": {"is_revoked": True}},
    )

    res = auth_client.get("/api/auth/me")
    assert res.status_code == 401
    assert "invalid" in res.json()["detail"].lower() or "expired" in res.json()["detail"].lower()


# ==============================================================================
# 4. Logout Tests
# ==============================================================================

def test_logout_revokes_session_and_clears_cookies(auth_client, fake_auth_db):
    """Verify logout validates CSRF, marks session revoked, and clears cookies."""
    reg_res = auth_client.post(
        "/api/auth/register",
        json={"email": "logout.test@example.com", "password": "Password12345!"},
    )
    csrf_token = reg_res.json()["csrf_token"]
    session_id = auth_client.cookies.get("fieldnote_session")

    # Logout with valid CSRF token header
    logout_res = auth_client.post(
        "/api/auth/logout",
        headers={"X-CSRF-Token": csrf_token},
    )
    assert logout_res.status_code == 200
    assert logout_res.json()["message"] == "Logged out successfully"

    # Database session must be marked revoked
    stored_session = fake_auth_db["sessions"].find_one({"session_id": session_id})
    assert stored_session["is_revoked"] is True

    # Subsequent request to /api/auth/me fails
    me_res = auth_client.get("/api/auth/me")
    assert me_res.status_code == 401


# ==============================================================================
# 5. CSRF Protection Tests
# ==============================================================================

def test_csrf_rejection_when_token_missing(auth_client):
    """Verify state-changing authenticated request without CSRF token returns 403."""
    auth_client.post(
        "/api/auth/register",
        json={"email": "csrf.test@example.com", "password": "Password12345!"},
    )

    # Attempt logout without X-CSRF-Token header
    res = auth_client.post("/api/auth/logout")
    assert res.status_code == 403
    assert "CSRF token validation failed" in res.json()["detail"]


def test_csrf_rejection_when_token_mismatched(auth_client):
    """Verify state-changing authenticated request with incorrect CSRF token returns 403."""
    auth_client.post(
        "/api/auth/register",
        json={"email": "csrf.bad@example.com", "password": "Password12345!"},
    )

    res = auth_client.post(
        "/api/auth/logout",
        headers={"X-CSRF-Token": "completely-invalid-attacker-token"},
    )
    assert res.status_code == 403
    assert "CSRF token validation failed" in res.json()["detail"]


def test_csrf_origin_rejection(auth_client):
    """Verify request with foreign untrusted Origin header returns 403."""
    reg_res = auth_client.post(
        "/api/auth/register",
        json={"email": "origin.test@example.com", "password": "Password12345!"},
    )
    csrf_token = reg_res.json()["csrf_token"]

    # Post from malicious origin
    res = auth_client.post(
        "/api/auth/logout",
        headers={
            "X-CSRF-Token": csrf_token,
            "Origin": "https://malicious-phishing-site.com",
        },
    )
    assert res.status_code == 403
    assert "Cross-origin request rejected" in res.json()["detail"]


# ==============================================================================
# 6. Cookie Security Attributes Tests
# ==============================================================================

def test_cookie_attributes_in_development(auth_client):
    """Verify session cookie has HttpOnly, SameSite=lax, and Path=/."""
    res = auth_client.post(
        "/api/auth/register",
        json={"email": "cookie.dev@example.com", "password": "Password12345!"},
    )
    session_cookie = res.headers.get("set-cookie", "")

    # Must contain HttpOnly
    assert "httponly" in session_cookie.lower()
    # Must contain SameSite=lax
    assert "samesite=lax" in session_cookie.lower()
    # Must contain Path=/
    assert "path=/" in session_cookie.lower()


def test_cookie_attributes_in_production(fake_auth_db):
    """Verify session cookie enforces Secure flag when in production mode."""
    prod_settings = Settings(
        APP_ENV="production",
        MONGODB_URI="mongodb://localhost:27017",
        DATABASE_NAME="fieldnote_prod_db",
        _env_file=None,
    )

    app = create_app()
    app.dependency_overrides[get_database] = lambda: fake_auth_db
    app.dependency_overrides[get_settings] = lambda: prod_settings

    with TestClient(app, base_url="https://fieldnote.example.org") as prod_client:
        res = prod_client.post(
            "/api/auth/register",
            json={"email": "prod.user@example.com", "password": "Password12345!"},
        )
        assert res.status_code == 201
        session_cookie = res.headers.get("set-cookie", "")
        # In production, Secure attribute must be present
        assert "secure" in session_cookie.lower()
        assert "httponly" in session_cookie.lower()


# ==============================================================================
# 7. Rate Limiting Tests
# ==============================================================================

def test_rate_limiting_auth_endpoints(fake_auth_db):
    """Verify exceeding rate limit returns 429 Too Many Requests with Retry-After header."""
    rate_limited_settings = Settings(
        APP_ENV="testing",
        MONGODB_URI="mongodb://localhost:27017",
        RATE_LIMIT_AUTH_REQUESTS=3,
        RATE_LIMIT_AUTH_WINDOW_SECONDS=60,
        _env_file=None,
    )

    app = create_app()
    app.dependency_overrides[get_database] = lambda: fake_auth_db
    app.dependency_overrides[get_settings] = lambda: rate_limited_settings
    auth_rate_limiter.reset()

    with TestClient(app, base_url="http://localhost:8000") as rl_client:
        for i in range(3):
            res = rl_client.post(
                "/api/auth/login",
                json={"email": f"test{i}@example.com", "password": "WrongPassword!"},
            )
            assert res.status_code == 401

        # 4th request exceeds rate limit of 3
        exceeded_res = rl_client.post(
            "/api/auth/login",
            json={"email": "test4@example.com", "password": "WrongPassword!"},
        )
        assert exceeded_res.status_code == 429
        assert "Too many authentication attempts" in exceeded_res.json()["detail"]
        assert "Retry-After" in exceeded_res.headers

    auth_rate_limiter.reset()


def test_malformed_session_cookie_rejected(auth_client):
    """Verify malformed, non-existent, or tampered session cookie returns 401 Unauthorized."""
    auth_client.cookies.set("fieldnote_session", "completely_bogus_token_12345")
    res = auth_client.get("/api/auth/me")
    assert res.status_code == 401
    assert "expired or invalid" in res.json()["detail"].lower()


def test_revoked_session_cookie_rejected(auth_client, fake_auth_db):
    """Verify explicitly revoked session cannot be reused for authentication."""
    res_reg = auth_client.post(
        "/api/auth/register",
        json={"email": "revoked.check@example.com", "password": "Password123!"},
    )
    assert res_reg.status_code == 201
    session_id = auth_client.cookies.get("fieldnote_session")
    assert session_id is not None

    # Verify authenticated before revocation
    assert auth_client.get("/api/auth/me").status_code == 200

    # Mark session revoked in database
    for sess in fake_auth_db["sessions"].docs.values():
        if sess["session_id"] == session_id:
            sess["is_revoked"] = True

    # Next authenticated request must fail with 401
    res_after = auth_client.get("/api/auth/me")
    assert res_after.status_code == 401
