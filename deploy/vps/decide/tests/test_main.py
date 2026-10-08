"""decide_service.main: how the service starts. MemoryStore only; a fake key; no network, no real Jev call."""
import importlib
import sys

import pytest
from fastapi.testclient import TestClient

from decide_service.store import MemoryStore
from engine.decide import jev

FAKE_KEY = "ts-FAKE-KEY-0123456789-do-not-leak"
OWNER = {"X-Remote-User": "gab"}


@pytest.fixture(autouse=True)
def clean_env(monkeypatch):
    for name in ("DECIDE_DATABASE_URL", "DECIDE_JEV_ENABLED", "DECIDE_OWNER_USERS", "TYPESAFE_API_KEY"):
        monkeypatch.delenv(name, raising=False)
    # the key is read only when the SDK imports; the SDK is not needed for these tests
    monkeypatch.setattr(jev, "sdk_importable", lambda: True)


def _import_main():
    sys.modules.pop("decide_service.main", None)
    return importlib.import_module("decide_service.main")


def test_import_without_database_url_does_not_fail_and_builds_no_app():
    main = _import_main()
    assert not hasattr(main, "app")


def test_import_with_database_url_builds_the_module_level_app(monkeypatch):
    monkeypatch.setenv("DECIDE_DATABASE_URL", "postgresql://x:y@nowhere:5432/z")
    built = []

    import decide_service.pgstore as pgstore

    class Fake(MemoryStore):
        def __init__(self, url):
            super().__init__()
            built.append(url)

        def ensure_schema(self):
            built.append("schema")

    monkeypatch.setattr(pgstore, "PostgresStore", Fake)
    main = _import_main()
    assert hasattr(main, "app")
    assert built == ["postgresql://x:y@nowhere:5432/z", "schema"]


def test_build_app_health_says_jev_is_off_by_default(monkeypatch):
    main = _import_main()                              # imported with no database URL: no module-level app
    monkeypatch.setenv("DECIDE_DATABASE_URL", "memory://")
    app = main.build_app(store_factory=lambda url: MemoryStore())
    body = TestClient(app).get("/api/decide/health", headers=OWNER).json()
    assert body["ok"] is True
    assert body["jev_enabled"] is False


def test_decider_available_follows_the_environment_key(monkeypatch):
    main = _import_main()
    assert main.make_decider().available is False
    monkeypatch.setenv("TYPESAFE_API_KEY", FAKE_KEY)
    assert main.make_decider().available is True
    monkeypatch.delenv("TYPESAFE_API_KEY")
    assert main.make_decider().available is False


def test_decider_repr_never_shows_the_key(monkeypatch):
    main = _import_main()
    monkeypatch.setenv("TYPESAFE_API_KEY", FAKE_KEY)
    decider = main.make_decider()
    assert FAKE_KEY not in repr(decider)
    assert FAKE_KEY not in str(decider)


def test_decider_reads_no_env_file(monkeypatch):
    main = _import_main()
    decider = main.make_decider()
    assert str(decider._env_file).replace("\\", "/").endswith("/nonexistent")
