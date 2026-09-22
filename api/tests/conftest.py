import os
import psycopg
import pytest
from fastapi.testclient import TestClient

ADMIN = "postgresql://fixer:fixer@127.0.0.1:5490/postgres"
TEST_URL = "postgresql+psycopg://fixer:fixer@127.0.0.1:5490/fixer_test"


@pytest.fixture(scope="session", autouse=True)
def _database(tmp_path_factory):
    try:
        with psycopg.connect(ADMIN, autocommit=True) as conn:
            conn.execute("DROP DATABASE IF EXISTS fixer_test WITH (FORCE)")
            conn.execute("CREATE DATABASE fixer_test")
    except Exception as e:
        print(f"Warning: could not create fixer_test: {e}")
    root = tmp_path_factory.mktemp("fixer")
    os.environ["FIXER_DATABASE_URL"] = TEST_URL
    os.environ["FIXER_SOURCE_DIR"] = str(root / "source")
    os.environ["FIXER_DATA_DIR"] = str(root / "data")
    os.environ["FIXER_STABLE_INTERVAL_S"] = "0"
    from api.settings import get_settings
    get_settings.cache_clear()
    from api.db import get_engine
    get_engine.cache_clear()
    yield root


@pytest.fixture()
def client(_database):
    from api.main import create_app
    return TestClient(create_app())


@pytest.fixture()
def db(_database):
    from api.db import get_engine
    from sqlalchemy.orm import Session
    with Session(get_engine()) as s:
        yield s
        s.rollback()
