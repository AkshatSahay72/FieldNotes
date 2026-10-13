"""Authentication and session management services for Fieldnote.

Provides:
- Argon2id password hashing and constant-time verification
- Cryptographically secure session and CSRF token generation
- Server-managed MongoDB session lifecycle (creation, validation, rotation, revocation)
- Timing-safe CSRF validation and Origin header verification
- Thread-safe in-memory rate limiting for authentication endpoints
"""

from collections import defaultdict
from datetime import datetime, timezone, timedelta
import logging
import secrets
import threading
from typing import List, Optional, Tuple
from urllib.parse import urlparse

import argon2
from bson import ObjectId
from fastapi import Request
from pymongo.database import Database

logger = logging.getLogger(__name__)

# OWASP recommended Argon2id parameters
_hasher = argon2.PasswordHasher(
    time_cost=2,
    memory_cost=65536,
    parallelism=1,
    hash_len=32,
    type=argon2.Type.ID,
)


def hash_password(plain_password: str) -> str:
    """Hash a plain text password using Argon2id.

    Never logs or persists the plain text password.
    """
    return _hasher.hash(plain_password)


def verify_password(plain_password: str, hashed_password: str) -> bool:
    """Verify a plain password against an Argon2id hash in constant time.

    Returns False safely upon verification failure without leaking details.
    """
    try:
        return _hasher.verify(hashed_password, plain_password)
    except (argon2.exceptions.VerifyMismatchError,
            argon2.exceptions.VerificationError,
            argon2.exceptions.InvalidHashError):
        return False
    except Exception as err:
        logger.warning("Unexpected error during password verification: %s", type(err).__name__)
        return False


def generate_session_id() -> str:
    """Generate a high-entropy random session identifier (256 bits)."""
    return secrets.token_urlsafe(32)


def generate_csrf_token() -> str:
    """Generate a high-entropy random CSRF token (256 bits)."""
    return secrets.token_urlsafe(32)


def create_session(
    db: Database,
    user_id: ObjectId,
    user_agent: Optional[str] = None,
    ip_address: Optional[str] = None,
    lifetime_seconds: int = 7 * 24 * 3600,
) -> dict:
    """Create a new server-managed session in MongoDB with a unique session ID and CSRF token."""
    now = datetime.now(timezone.utc)
    expires_at = now + timedelta(seconds=lifetime_seconds)
    session_id = generate_session_id()
    csrf_token = generate_csrf_token()

    session_doc = {
        "session_id": session_id,
        "user_id": user_id,
        "csrf_token": csrf_token,
        "created_at": now,
        "last_active_at": now,
        "expires_at": expires_at,
        "is_revoked": False,
        "ip_address": ip_address,
        "user_agent": user_agent,
    }

    db["sessions"].insert_one(session_doc)
    return session_doc


def get_active_session(db: Database, session_id: str) -> Optional[dict]:
    """Retrieve an active, non-expired, non-revoked session by its session ID."""
    if not session_id:
        return None
    now = datetime.now(timezone.utc)
    session = db["sessions"].find_one({
        "session_id": session_id,
        "is_revoked": False,
        "expires_at": {"$gt": now},
    })
    return session


def touch_session(db: Database, session_id: str) -> None:
    """Update last_active_at timestamp on active session."""
    now = datetime.now(timezone.utc)
    try:
        db["sessions"].update_one(
            {"session_id": session_id},
            {"$set": {"last_active_at": now}},
        )
    except Exception as err:
        logger.debug("Failed to touch session %s: %s", session_id[:8], type(err).__name__)


def revoke_session(db: Database, session_id: str) -> bool:
    """Explicitly revoke a session in MongoDB."""
    if not session_id:
        return False
    now = datetime.now(timezone.utc)
    res = db["sessions"].update_one(
        {"session_id": session_id},
        {"$set": {"is_revoked": True, "updated_at": now}},
    )
    return getattr(res, "modified_count", 0) > 0 or getattr(res, "matched_count", 0) > 0


def revoke_all_user_sessions(db: Database, user_id: ObjectId) -> int:
    """Revoke all active sessions for a specific user (e.g. password change)."""
    now = datetime.now(timezone.utc)
    res = db["sessions"].update_many(
        {"user_id": user_id, "is_revoked": False},
        {"$set": {"is_revoked": True, "updated_at": now}},
    )
    return getattr(res, "modified_count", 0)


def validate_csrf_token(session_csrf_token: str, provided_csrf_token: Optional[str]) -> bool:
    """Validate a provided CSRF token against the session token in constant time."""
    if not session_csrf_token or not provided_csrf_token:
        return False
    return secrets.compare_digest(session_csrf_token, provided_csrf_token)


def validate_origin(request: Request, allowed_hosts: Optional[List[str]] = None) -> bool:
    """Validate request Origin and Referer headers against the host server.

    If Origin is present, its host must match the request Host or configured allowed hosts.
    If Referer is present and Origin is missing, its host must match.
    """
    origin = request.headers.get("origin")
    referer = request.headers.get("referer")
    host_header = request.headers.get("host")

    expected_hosts = set()
    if host_header:
        # Strip port if present
        expected_hosts.add(host_header.split(":")[0].lower())
        expected_hosts.add(host_header.lower())
    if allowed_hosts:
        for h in allowed_hosts:
            expected_hosts.add(h.lower())

    if origin:
        try:
            parsed = urlparse(origin)
            origin_host = parsed.hostname
            if not origin_host or (origin_host.lower() not in expected_hosts and parsed.netloc.lower() not in expected_hosts):
                return False
            return True
        except Exception:
            return False

    if referer:
        try:
            parsed = urlparse(referer)
            referer_host = parsed.hostname
            if not referer_host or (referer_host.lower() not in expected_hosts and parsed.netloc.lower() not in expected_hosts):
                return False
            return True
        except Exception:
            return False

    # If neither is sent (e.g. direct programmatic API call / same-site navigation), allow CSRF token to govern
    return True


class AuthRateLimiter:
    """Thread-safe in-memory sliding window rate limiter for authentication endpoints.

    In a multi-process or distributed deployment, this can be swapped with a Redis-backed
    token bucket or sliding log without changing the application interface.
    """

    def __init__(self):
        self._lock = threading.Lock()
        self._history = defaultdict(list)

    def check_rate_limit(
        self,
        key: str,
        max_requests: int = 10,
        window_seconds: int = 60,
    ) -> Tuple[bool, int]:
        """Check if request for key is allowed within the sliding window.

        Returns (is_allowed, retry_after_seconds).
        """
        now = datetime.now(timezone.utc)
        cutoff = now - timedelta(seconds=window_seconds)

        with self._lock:
            timestamps = self._history[key]
            # Prune expired entries
            valid_timestamps = [t for t in timestamps if t > cutoff]
            self._history[key] = valid_timestamps

            if len(valid_timestamps) >= max_requests:
                oldest = valid_timestamps[0]
                retry_after = max(1, int((oldest + timedelta(seconds=window_seconds) - now).total_seconds()))
                return False, retry_after

            self._history[key].append(now)
            return True, 0

    def reset(self, key: Optional[str] = None) -> None:
        """Reset rate limiter state (useful in test suites)."""
        with self._lock:
            if key:
                self._history.pop(key, None)
            else:
                self._history.clear()


auth_rate_limiter = AuthRateLimiter()
