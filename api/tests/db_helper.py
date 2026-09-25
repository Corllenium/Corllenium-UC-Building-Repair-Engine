import ctypes
import os
import uuid
import warnings
import psycopg
from alembic import command
from alembic.config import Config
from api.settings import get_settings

ADMIN_URL = "postgresql://fixer:fixer@127.0.0.1:5490/postgres"


def is_pid_alive(pid: int) -> bool:
    if pid <= 0:
        return False
    if os.name == "nt":
        PROCESS_QUERY_LIMITED_INFORMATION = 0x1000
        SYNCHRONIZE = 0x00100000
        handle = ctypes.windll.kernel32.OpenProcess(PROCESS_QUERY_LIMITED_INFORMATION | SYNCHRONIZE, False, pid)
        if not handle:
            return False
        try:
            exit_code = ctypes.c_ulong()
            if ctypes.windll.kernel32.GetExitCodeProcess(handle, ctypes.byref(exit_code)):
                STILL_ACTIVE = 259
                return exit_code.value == STILL_ACTIVE
            return False
        finally:
            ctypes.windll.kernel32.CloseHandle(handle)
    else:
        try:
            os.kill(pid, 0)
            return True
        except Exception:
            return False


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
    try:
        with psycopg.connect(ADMIN_URL, autocommit=True) as conn:
            conn.execute(f"DROP DATABASE IF EXISTS {db_name} WITH (FORCE)")
    except Exception as e:
        warnings.warn(f"Failed to drop test database {db_name}: {e}", UserWarning)


def cleanup_orphaned_test_dbs() -> list[str]:
    dropped: list[str] = []
    try:
        with psycopg.connect(ADMIN_URL, autocommit=True) as conn:
            cur = conn.execute("SELECT datname FROM pg_database WHERE datname LIKE 'fixer_test_%'")
            rows = cur.fetchall()
            for (db_name,) in rows:
                parts = db_name.split("_")
                # Expected format: fixer_test_<pid>_<suffix>
                if len(parts) >= 4 and parts[0] == "fixer" and parts[1] == "test":
                    try:
                        pid = int(parts[2])
                    except ValueError:
                        continue
                    if not is_pid_alive(pid):
                        try:
                            conn.execute(f"DROP DATABASE IF EXISTS {db_name} WITH (FORCE)")
                            dropped.append(db_name)
                        except Exception as e:
                            warnings.warn(f"Failed to drop orphaned test database {db_name}: {e}", UserWarning)
    except Exception as e:
        warnings.warn(f"Failed to scan test databases for cleanup: {e}", UserWarning)
    return dropped

