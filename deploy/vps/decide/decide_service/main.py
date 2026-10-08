"""How `uc-fixer-decide` starts. uvicorn loads `decide_service.main:app`. The module-level `app` exists only when
DECIDE_DATABASE_URL is set, so tests (and tools) can import this module without a database.

The TypeSafe key comes from the ENVIRONMENT only (TYPESAFE_API_KEY, from decide.env): the decider is told to read no
env file. Jev stays off until DECIDE_JEV_ENABLED is set to true."""
from __future__ import annotations

import os
from pathlib import Path

from decide_service.app import create_app
from decide_service.settings import Settings
from engine.decide.jev import JevDecider

#: A path that never exists, so JevDecider falls back to nothing but the environment.
NO_ENV_FILE = Path("/nonexistent")


def _postgres_store(url: str):
    from decide_service.pgstore import PostgresStore     # looked up at call time; psycopg is needed only here
    store = PostgresStore(url)
    store.ensure_schema()                                 # once, at start
    return store


def _decider(cfg: Settings) -> JevDecider:
    return JevDecider(env_file=NO_ENV_FILE, min_confidence=cfg.min_confidence, batch=cfg.batch)


def make_decider() -> JevDecider:
    """A decider with the settings from the environment; the key is read from the environment only."""
    return _decider(Settings.from_env())


def build_app(store_factory=_postgres_store, env=None):
    cfg = Settings.from_env(env)
    store = store_factory(cfg.database_url)
    return create_app(store, cfg, lambda: _decider(cfg))


if os.environ.get("DECIDE_DATABASE_URL"):
    app = build_app()
