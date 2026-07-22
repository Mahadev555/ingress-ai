from contextlib import contextmanager

import httpx
import pytest
from fastapi.testclient import TestClient

from app.core.config import get_settings
from app.main import app

ADMIN_TOKEN = "test-admin-token"


@pytest.fixture(autouse=True)
def _isolate_settings(monkeypatch):
    """Reset the cached settings around each test and default the database to a
    fresh in-memory SQLite so tests never touch a real database or leak state."""
    monkeypatch.setenv("DATABASE_URL", "sqlite+aiosqlite:///:memory:")
    get_settings.cache_clear()
    yield
    get_settings.cache_clear()


@pytest.fixture
def make_gateway(monkeypatch):
    """Return a factory yielding an authenticated TestClient.

    Each gateway uses a fresh in-memory database, has the admin API enabled,
    and (optionally) a mocked upstream via an httpx handler.
    """
    monkeypatch.setenv("ADMIN_API_KEY", ADMIN_TOKEN)

    @contextmanager
    def factory(handler=None, allowed_models=None):
        with TestClient(app) as client:
            if handler is not None:
                app.state.http_client = httpx.AsyncClient(
                    transport=httpx.MockTransport(handler)
                )
            created = client.post(
                "/admin/keys",
                headers={"X-Admin-Token": ADMIN_TOKEN},
                json={"name": "test", "allowed_models": allowed_models or []},
            )
            assert created.status_code == 200, created.text
            client.headers["Authorization"] = f"Bearer {created.json()['key']}"
            yield client

    return factory
