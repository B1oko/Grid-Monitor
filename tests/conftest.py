from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from app.core.config import get_settings
from app.drivers.registry import load_drivers, reset_registry


@pytest.fixture(autouse=True)
def _reload_drivers() -> None:
    reset_registry()
    load_drivers()
    yield
    reset_registry()


@pytest.fixture
def data_dir(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    db_url = f"sqlite+aiosqlite:///{(tmp_path / 'test.db').as_posix()}"
    monkeypatch.setenv("DATA_DIR", str(tmp_path))
    monkeypatch.setenv("DATABASE_URL", db_url)
    get_settings.cache_clear()
    yield tmp_path
    get_settings.cache_clear()


@pytest.fixture
def client(data_dir: Path) -> TestClient:
    from app.main import app

    with TestClient(app) as api:
        yield api
