import os
import uuid
import psycopg
from alembic import command
from alembic.config import Config
from api.settings import get_settings

ADMIN_URL = "postgresql://fixer:fixer@127.0.0.1:5490/postgres"


def generate_test_db_name() -> str:
    return f"fixer_test_{os.getpid()}_{uuid.uuid4().hex[:6]}"


def create_test_db(db_name: str | None = None) -> tuple[str, str]:
    if db_name is None:
        db_name = generate_test_db_name()
    with psycopg.connect(ADMIN_URL, autocommit=True) as conn:
        conn.execute(f"CREATE DATABASE {db_name}")

    db_url = f"postgresql+psycopg://fixer:fixer@127.0.0.1:5490/{db_name}"
    return db_name, db_url


def migrate_test_db(db_url: str) -> None:
    old_env = os.environ.get("FIXER_DATABASE_URL")
    os.environ["FIXER_DATABASE_URL"] = db_url
    try:
        get_settings.cache_clear()
        alembic_cfg = Config("alembic.ini")
        command.upgrade(alembic_cfg, "head")
    finally:
        if old_env is not None:
            os.environ["FIXER_DATABASE_URL"] = old_env
            get_settings.cache_clear()
        else:
            os.environ.pop("FIXER_DATABASE_URL", None)
            get_settings.cache_clear()


def drop_test_db(db_name: str) -> None:
    with psycopg.connect(ADMIN_URL, autocommit=True) as conn:
        conn.execute(f"DROP DATABASE IF EXISTS {db_name} WITH (FORCE)")
