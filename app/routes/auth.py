"""Authentication and session management routes for Fieldnote.

Endpoints:
- POST /api/auth/register : Register a new user account, hash password with Argon2id, create session
- POST /api/auth/login    : Authenticate credentials, rotate session identifier, set HTTP-only cookies
- POST /api/auth/logout   : Validate CSRF, revoke server session, delete cookies
- GET  /api/auth/me       : Retrieve current authenticated user and session info
- GET  /api/auth/session  : Alias for /api/auth/me
"""

from datetime import datetime, timezone
import logging
from typing import Optional, Tuple
from bson import ObjectId
from fastapi import APIRouter, Depends, HTTPException, Request, Response, status
from pymongo.database import Database

from app.config import Settings, get_settings
from app.db import get_database
from app.schemas import (
    UserRegisterRequest,
    UserLoginRequest,
    UserResponse,
    SessionResponse,
)
from app.services.auth import (
    hash_password,
    verify_password,
    create_session,
    get_active_session,
    touch_session,
    revoke_session,
    validate_csrf_token,
    validate_origin,
    auth_rate_limiter,
)

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/auth", tags=["Authentication"])


def get_client_ip(request: Request) -> str:
    """Extract client IP address for rate limiting."""
    forwarded = request.headers.get("x-forwarded-for")
    if forwarded:
        return forwarded.split(",")[0].strip()
    return request.client.host if request.client else "127.0.0.1"


def enforce_auth_rate_limit(
    request: Request,
    settings: Settings = Depends(get_settings),
) -> None:
    """Enforce rate limits on sensitive authentication endpoints."""
    ip = get_client_ip(request)
    allowed, retry_after = auth_rate_limiter.check_rate_limit(
        key=ip,
        max_requests=settings.rate_limit_auth_requests,
        window_seconds=settings.rate_limit_auth_window_seconds,
    )
    if not allowed:
        raise HTTPException(
            status_code=status.HTTP_429_TOO_MANY_REQUESTS,
            detail="Too many authentication attempts. Please try again later.",
            headers={"Retry-After": str(retry_after)},
        )


def get_current_session_data(
    request: Request,
    db: Database = Depends(get_database),
    settings: Settings = Depends(get_settings),
) -> Tuple[dict, dict]:
    """Dependency that extracts and validates the active session and corresponding user from cookies.

    Raises HTTP 401 if session cookie is missing, expired, revoked, or user inactive.
    """
    session_id = request.cookies.get(settings.session_cookie_name)
    if not session_id:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Not authenticated",
        )

    session = get_active_session(db, session_id)
    if not session:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Session expired or invalid",
        )

    user_id = session.get("user_id")
    if not user_id:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid session user",
        )

    user = db["users"].find_one({"_id": user_id, "is_active": True})
    if not user:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="User not found or account deactivated",
        )

    # Touch session activity
    touch_session(db, session_id)
    return user, session


def get_current_user(
    session_data: Tuple[dict, dict] = Depends(get_current_session_data),
) -> UserResponse:
    """Dependency returning the authenticated UserResponse model."""
    user, _ = session_data
    return UserResponse(
        id=str(user["_id"]),
        email=user["email"],
        created_at=user["created_at"],
        is_active=user.get("is_active", True),
    )


def get_optional_current_user(
    request: Request,
    db: Database = Depends(get_database),
    settings: Settings = Depends(get_settings),
) -> Optional[UserResponse]:
    """Dependency returning the current user if authenticated, or None if unauthenticated."""
    session_id = request.cookies.get(settings.session_cookie_name)
    if not session_id:
        return None
    session = get_active_session(db, session_id)
    if not session:
        return None
    user_id = session.get("user_id")
    if not user_id:
        return None
    user = db["users"].find_one({"_id": user_id, "is_active": True})
    if not user:
        return None
    return UserResponse(
        id=str(user["_id"]),
        email=user["email"],
        created_at=user["created_at"],
        is_active=user.get("is_active", True),
    )


def verify_csrf(
    request: Request,
    db: Database = Depends(get_database),
    settings: Settings = Depends(get_settings),
) -> None:
    """Verify CSRF token and Origin header for state-changing browser requests.

    Only applies to state-changing HTTP methods when a session cookie is present.
    """
    if request.method in ("GET", "HEAD", "OPTIONS"):
        return

    session_id = request.cookies.get(settings.session_cookie_name)
    if not session_id:
        # Request is not authenticated via cookie (e.g. initial login/registration)
        return

    # Validate Origin/Referer
    if not validate_origin(request):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Cross-origin request rejected",
        )

    # Fetch active session to retrieve expected CSRF token
    session = get_active_session(db, session_id)
    if not session:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Session expired or invalid",
        )

    # Read CSRF token from header (or form data)
    provided_csrf = request.headers.get("x-csrf-token")
    if not provided_csrf:
        # Fallback check query/cookie if custom header omitted
        provided_csrf = request.headers.get("x-xsrf-token")

    if not validate_csrf_token(session.get("csrf_token", ""), provided_csrf):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="CSRF token validation failed",
        )


def enforce_write_access(
    request: Request,
    settings: Settings = Depends(get_settings),
    current_user: Optional[UserResponse] = Depends(get_optional_current_user),
    db: Database = Depends(get_database),
) -> Optional[UserResponse]:
    """Validate permissions for state-changing write operations across application modes.

    1. Enforces read-only public demo protection: all writes rejected with 403 Forbidden.
    2. Enforces authenticated personal mode: unauthenticated writes rejected with 401 Unauthorized.
    3. Enforces CSRF defense on cookie-authenticated requests: rejected with 403 Forbidden on failure.
    """
    if settings.is_demo_mode:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Operation not permitted in demo mode.",
        )

    if settings.requires_authentication_for_writes and current_user is None:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Authentication required to perform write operations.",
        )

    # Validate CSRF token for browser sessions on state-changing requests
    verify_csrf(request=request, db=db, settings=settings)

    return current_user


@router.post(
    "/register",
    response_model=SessionResponse,
    status_code=status.HTTP_201_CREATED,
    summary="Register a new user account",
    dependencies=[Depends(enforce_auth_rate_limit)],
)
def register_user(
    reg_in: UserRegisterRequest,
    response: Response,
    request: Request,
    db: Database = Depends(get_database),
    settings: Settings = Depends(get_settings),
) -> SessionResponse:
    """Register a new user account with Argon2id password hashing and establish a session."""
    # Check for duplicate email
    existing = db["users"].find_one({"email": reg_in.email})
    if existing:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="An account with this email already exists",
        )

    now = datetime.now(timezone.utc)
    hashed = hash_password(reg_in.password)

    user_doc = {
        "_id": ObjectId(),
        "email": reg_in.email,
        "hashed_password": hashed,
        "is_active": True,
        "created_at": now,
        "updated_at": now,
    }

    try:
        db["users"].insert_one(user_doc)
    except Exception as err:
        # Catch duplicate key race conditions
        if "duplicate" in str(err).lower() or "11000" in str(err):
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail="An account with this email already exists",
            )
        logger.error("Failed to insert user document: %s", type(err).__name__)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to create user account",
        )

    # Create initial authenticated session
    session = create_session(
        db=db,
        user_id=user_doc["_id"],
        user_agent=request.headers.get("user-agent"),
        ip_address=get_client_ip(request),
        lifetime_seconds=settings.session_lifetime_seconds,
    )

    # Set HTTP-only session cookie and client-readable CSRF cookie
    response.set_cookie(
        key=settings.session_cookie_name,
        value=session["session_id"],
        httponly=True,
        secure=settings.is_cookie_secure,
        samesite=settings.session_cookie_samesite,
        max_age=settings.session_lifetime_seconds,
        path="/",
    )
    response.set_cookie(
        key=settings.csrf_cookie_name,
        value=session["csrf_token"],
        httponly=False,
        secure=settings.is_cookie_secure,
        samesite=settings.session_cookie_samesite,
        max_age=settings.session_lifetime_seconds,
        path="/",
    )

    user_resp = UserResponse(
        id=str(user_doc["_id"]),
        email=user_doc["email"],
        created_at=user_doc["created_at"],
        is_active=True,
    )

    return SessionResponse(
        user=user_resp,
        csrf_token=session["csrf_token"],
        expires_at=session["expires_at"],
    )


@router.post(
    "/login",
    response_model=SessionResponse,
    status_code=status.HTTP_200_OK,
    summary="Authenticate user and establish session",
    dependencies=[Depends(enforce_auth_rate_limit)],
)
def login_user(
    login_in: UserLoginRequest,
    response: Response,
    request: Request,
    db: Database = Depends(get_database),
    settings: Settings = Depends(get_settings),
) -> SessionResponse:
    """Authenticate user credentials, rotate session identifier (anti-fixation), and issue cookies."""
    user = db["users"].find_one({"email": login_in.email})

    # Safe generic error message to prevent account enumeration
    if not user or not user.get("is_active", True):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid email or password",
        )

    if not verify_password(login_in.password, user.get("hashed_password", "")):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid email or password",
        )

    # Protect against session fixation: rotate/revoke any pre-existing session
    prev_session_id = request.cookies.get(settings.session_cookie_name)
    if prev_session_id:
        revoke_session(db, prev_session_id)

    # Issue a brand-new session identifier
    session = create_session(
        db=db,
        user_id=user["_id"],
        user_agent=request.headers.get("user-agent"),
        ip_address=get_client_ip(request),
        lifetime_seconds=settings.session_lifetime_seconds,
    )

    # Set HTTP-only session cookie and client-readable CSRF cookie
    response.set_cookie(
        key=settings.session_cookie_name,
        value=session["session_id"],
        httponly=True,
        secure=settings.is_cookie_secure,
        samesite=settings.session_cookie_samesite,
        max_age=settings.session_lifetime_seconds,
        path="/",
    )
    response.set_cookie(
        key=settings.csrf_cookie_name,
        value=session["csrf_token"],
        httponly=False,
        secure=settings.is_cookie_secure,
        samesite=settings.session_cookie_samesite,
        max_age=settings.session_lifetime_seconds,
        path="/",
    )

    user_resp = UserResponse(
        id=str(user["_id"]),
        email=user["email"],
        created_at=user["created_at"],
        is_active=user.get("is_active", True),
    )

    return SessionResponse(
        user=user_resp,
        csrf_token=session["csrf_token"],
        expires_at=session["expires_at"],
    )


@router.post(
    "/logout",
    status_code=status.HTTP_200_OK,
    summary="Log out and revoke current session",
    dependencies=[Depends(verify_csrf)],
)
def logout_user(
    response: Response,
    request: Request,
    db: Database = Depends(get_database),
    settings: Settings = Depends(get_settings),
) -> dict:
    """Revoke active session in MongoDB and delete authentication cookies."""
    session_id = request.cookies.get(settings.session_cookie_name)
    if session_id:
        revoke_session(db, session_id)

    # Clear authentication and CSRF cookies
    response.delete_cookie(
        key=settings.session_cookie_name,
        path="/",
    )
    response.delete_cookie(
        key=settings.csrf_cookie_name,
        path="/",
    )

    return {"message": "Logged out successfully"}


@router.get(
    "/me",
    response_model=SessionResponse,
    status_code=status.HTTP_200_OK,
    summary="Get current authenticated session information",
)
@router.get(
    "/session",
    response_model=SessionResponse,
    status_code=status.HTTP_200_OK,
    summary="Get current authenticated session information (alias)",
    include_in_schema=False,
)
def get_session_info(
    session_data: Tuple[dict, dict] = Depends(get_current_session_data),
) -> SessionResponse:
    """Return active session details, current user profile, and CSRF token."""
    user, session = session_data
    user_resp = UserResponse(
        id=str(user["_id"]),
        email=user["email"],
        created_at=user["created_at"],
        is_active=user.get("is_active", True),
    )
    return SessionResponse(
        user=user_resp,
        csrf_token=session["csrf_token"],
        expires_at=session["expires_at"],
    )
