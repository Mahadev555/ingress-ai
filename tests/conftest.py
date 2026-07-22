import pytest

from app.core.config import get_settings


@pytest.fixture(autouse=True)
def _isolate_settings_cache():
    """Settings are cached per process; reset around each test so env overrides
    (e.g. monkeypatch.setenv) take effect and never leak between tests."""
    get_settings.cache_clear()
    yield
    get_settings.cache_clear()
