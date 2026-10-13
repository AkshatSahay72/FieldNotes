"""Pytest root configuration ensuring complete isolation from live MongoDB Atlas.

Enforces offline, safe test defaults before application startup or test collection:
- APP_ENV is forced to 'testing' (suppressing lifespan index initialization on remote clusters).
- MONGODB_URI defaults to local offline loopback (preventing network calls to remote clusters).
- DATABASE_NAME defaults to 'fieldnote_test_db'.
- DEMO_MODE defaults to 'false'.
"""

import os
import pytest

# Ensure testing configuration takes absolute precedence over .env file
os.environ["APP_ENV"] = "testing"
os.environ.setdefault("MONGODB_URI", "mongodb://localhost:27017")
os.environ.setdefault("DATABASE_NAME", "fieldnote_test_db")
os.environ.setdefault("DEMO_MODE", "false")

from app.config import get_settings

# Clear settings cache so initial test imports use the isolated test configuration
get_settings.cache_clear()

# Eagerly initialize sentence_transformers to prevent late Windows C-extension access violations
try:
    import sentence_transformers  # noqa: F401
except ImportError:
    pass


@pytest.fixture(autouse=True)
def ensure_isolated_test_settings():
    """Guarantees that test settings remain isolated and settings cache is cleared after tests."""
    yield
    get_settings.cache_clear()
