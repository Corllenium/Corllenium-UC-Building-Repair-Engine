# Phase 1B API + Canvas Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or
> superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Import a sidewalk from the live export folder through a web page, store it in PostgreSQL, and see it in
two synced 3D canvases with its gridlines classified, pickable down to the source `f` line.

**Architecture:** `api\` (FastAPI + SQLAlchemy 2 + Alembic, PostgreSQL 16 in Docker) calls the Phase 1A `engine\`
library and never re-implements geometry. `web\` (Vue 3 + TypeScript + three.js) talks only to `/api`. Geometry
travels as the engine's binary `meshbuf`. The throwaway `preview\index.html` is the validated starting point for the viewport.

**Tech Stack:** Python 3.12, FastAPI, SQLAlchemy 2, psycopg 3, Alembic, pydantic-settings, pytest + httpx ·
PostgreSQL 16 (Docker) · Node 24, pnpm, Vite, Vue 3, vue-router, three, vitest.

**Spec:** `docs\superpowers\specs\2026-09-21-uc-model-fixer-design.md`. Evidence: `docs\spike\2026-09-21-phase0-results.md`.
Engine API: `docs\superpowers\plans\2026-09-21-phase1a-engine-foundations.md` plus the final fix wave
(`flat_material_indices`, `FLAT_TEXTURE_STD`, `read_manifest_stable`, `SnapshotResult.source_mtl_path`).

## Global Constraints

- **Canvas renders double-sided by default.** One-sided is a diagnostic toggle, never the default. A one-sided view
  made intact geometry look destroyed during the spike.
- `web\` calls only `/api/*`. `api\` calls `engine\`. `engine\` imports nothing from `api\`.
- The live source folder is touched only through `engine.io.snapshot` (`read_manifest_stable`, `snapshot_object`).
  The API never opens a file under `FIXER_SOURCE_DIR` itself.
- `SourceUnstable` -> HTTP **409** with `Retry-After: 5`. The API never loops on it. `ManifestMismatch` -> **422**.
  Unknown file -> **404**.
- A file name from a client is accepted only if it is a key of the manifest. Textures are served by database
  lookup, never by joining a client string onto a path.
- Originals are immutable: a `snapshot` version row and its directory are never modified after creation.
- Phase 1 shows **no fixed geometry**. The AFTER canvas is labelled `PREVIEW: removable edges hidden, geometry unchanged`.
- PostgreSQL: `postgres:16`, bound to `127.0.0.1:5432`, named volume. Dev credentials `fixer / fixer / fixer`
  live in `.env` (git-ignored), with `.env.example` committed.
- Python commands: `.venv\Scripts\python.exe`. Web commands: `pnpm --dir web ...`. Dev servers start through
  `.claude\launch.json` + the preview tool, not raw shell.
- TDD. Commit trailer: `Co-Authored-By: Claude Fable 5.1 <noreply@anthropic.com>`.
- Every "done" needs an artefact produced that turn: test output, SQL row, screenshot.

## File Structure

| File | Responsibility |
|---|---|
| `engine\io\snapshot.py` (modify) | asset-aware snapshot identity (resolves parked finding F5) |
| `docker-compose.yml`, `.env.example` | PostgreSQL service |
| `api\settings.py` | env-driven settings |
| `api\db.py` | engine, session factory, `get_session` |
| `api\models.py` | ORM tables |
| `alembic.ini`, `api\alembic\env.py`, `api\alembic\versions\0001_initial.py` | schema + seeded `issue_types` |
| `api\schemas.py` | response models |
| `api\services\importer.py` | scan, import, idempotency |
| `api\routers\{source,models,versions,runs}.py` | HTTP surface |
| `api\main.py` | app factory |
| `api\tests\` | pytest against a real `fixer_test` database |
| `web\src\three\meshbuf.ts` | decode the binary buffer |
| `web\src\three\Viewport.ts`, `sync.ts` | renderer, overlays, picking, camera sync |
| `web\src\api\client.ts` | typed fetch wrappers |
| `web\src\views\ModelsView.vue`, `WorkspaceView.vue` | the two pages |

---

### Task 1: Asset-aware snapshot identity (engine)

Resolves parked finding F5: snapshot directory was keyed on the OBJ hash only, so a texture-only re-export
reused stale textures and stale flatness.

**Files:** Modify `engine\io\snapshot.py`, `engine\tests\test_snapshot.py`

**Interfaces — Produces:** `SnapshotResult.asset_sha256: str` (sha256 over `source.mtl` bytes hash + each copied
texture's hash, sorted by file name; empty-string hash when the object has no `mtllib`). Snapshot directory name
becomes `f"{sha256[:12]}-{asset_sha256[:8]}"`.

- [ ] **Step 1: failing tests** (append to `engine\tests\test_snapshot.py`)

```python
def test_texture_only_change_creates_new_snapshot(tmp_path):
    src = make_source(tmp_path / "src")
    a = snapshot_object(src, tmp_path / "snap", expected_tris=1, interval_s=0, sleep=lambda s: None)
    Image.fromarray(np.full((4, 4, 3), 10, np.uint8)).save(tmp_path / "src" / "SRC-TEX" / "stone.png")
    b = snapshot_object(src, tmp_path / "snap", expected_tris=1, interval_s=0, sleep=lambda s: None)
    assert a.sha256 == b.sha256 and a.asset_sha256 != b.asset_sha256 and a.dir != b.dir
    assert a.textures["stone"].read_bytes() != b.textures["stone"].read_bytes()


def test_dir_name_carries_both_hashes(tmp_path):
    src = make_source(tmp_path / "src")
    r = snapshot_object(src, tmp_path / "snap", expected_tris=1, interval_s=0, sleep=lambda s: None)
    assert r.dir.name == f"{r.sha256[:12]}-{r.asset_sha256[:8]}" and len(r.asset_sha256) == 64
```

Also change the one existing assertion `res.dir.name == res.sha256[:12]` to `res.dir.name.startswith(res.sha256[:12])`.
Run: `.venv\Scripts\python.exe -m pytest engine/tests/test_snapshot.py -q`. Expected: 2 FAIL (`AttributeError: asset_sha256`).

- [ ] **Step 2: implement.** Assets must be copied into the incoming dir **before** the final name is known:
  always run `_copy_assets`, then compute `asset_sha256` with this helper, then pick `final`. If `final` exists, discard incoming.

```python
def _asset_digest(folder: Path) -> str:
    h = hashlib.sha256()
    files = [folder / "source.mtl", *sorted((folder / "tex").glob("*"))] if (folder / "tex").exists() else [folder / "source.mtl"]
    for f in files:
        if f.is_file():
            h.update(f.name.encode("utf-8"))
            h.update(bytes.fromhex(sha256_file(f)))
    return h.hexdigest()
```

`_load(final, obj_name, digest)` recomputes `asset_sha256` with the same helper and sets it on the result.

- [ ] **Step 3:** Run the snapshot tests, then the whole suite. Expected: all pass, count = previous + 2.
- [ ] **Step 4:** Commit `feat(engine): asset-aware snapshot identity`.

---

### Task 2: PostgreSQL, settings, session, health

**Files:** Create `docker-compose.yml`, `.env.example`, `api\__init__.py`, `api\settings.py`, `api\db.py`,
`api\main.py`, `api\routers\__init__.py`, `api\tests\__init__.py`, `api\tests\conftest.py`, `api\tests\test_health.py`.
Modify `pyproject.toml`.

**Interfaces — Produces:** `get_settings() -> Settings` (fields `database_url`, `source_dir: Path`, `data_dir: Path`,
`stable_interval_s: float`), `get_engine()`, `get_session()` (FastAPI dependency yielding `Session`),
`create_app() -> FastAPI`, `app`. Test fixtures `client` (TestClient) and `db` (Session) usable by later tasks.

- [ ] **Step 1: `docker-compose.yml`**

```yaml
services:
  db:
    image: postgres:16
    environment:
      POSTGRES_USER: ${FIXER_DB_USER:-fixer}
      POSTGRES_PASSWORD: ${FIXER_DB_PASSWORD:-fixer}
      POSTGRES_DB: ${FIXER_DB_NAME:-fixer}
    ports:
      - "127.0.0.1:5432:5432"
    volumes:
      - fixer_pgdata:/var/lib/postgresql/data
    healthcheck:
      test: ["CMD-SHELL", "pg_isready -U ${FIXER_DB_USER:-fixer} -d ${FIXER_DB_NAME:-fixer}"]
      interval: 5s
      timeout: 3s
      retries: 10
volumes:
  fixer_pgdata:
```

`.env.example`:

```
FIXER_DATABASE_URL=postgresql+psycopg://fixer:fixer@127.0.0.1:5432/fixer
FIXER_SOURCE_DIR=D:\PROJECTS\UC ENVIRONMENT BUILDING\REQUIREMENTS\01-MODEL-EXPORT\CKPT17
FIXER_DATA_DIR=data
```

Run: `docker compose up -d db` then `docker compose ps`. Expected: `db` state `running (healthy)`.
Verify: `docker compose exec db psql -U fixer -d fixer -c "select version();"` prints `PostgreSQL 16`.

- [ ] **Step 2: `pyproject.toml`** — dependencies become
  `["numpy>=2.0", "shapely>=2.1", "pillow>=10", "fastapi>=0.115", "uvicorn[standard]>=0.30", "sqlalchemy>=2.0", "psycopg[binary]>=3.2", "alembic>=1.13", "pydantic-settings>=2.4"]`,
  dev becomes `["pytest>=8", "httpx>=0.27"]`, `testpaths = ["engine/tests", "api/tests"]`.
  Run `.venv\Scripts\python.exe -m pip install -e ".[dev]"`.

- [ ] **Step 3: failing test `api\tests\test_health.py`**

```python
def test_health_reports_database(client):
    r = client.get("/api/health")
    assert r.status_code == 200 and r.json() == {"status": "ok", "db": True}
```

`api\tests\conftest.py`:

```python
import os

import psycopg
import pytest
from fastapi.testclient import TestClient
from sqlalchemy import text

ADMIN = "postgresql://fixer:fixer@127.0.0.1:5432/postgres"
TEST_URL = "postgresql+psycopg://fixer:fixer@127.0.0.1:5432/fixer_test"


@pytest.fixture(scope="session", autouse=True)
def _database(tmp_path_factory):
    with psycopg.connect(ADMIN, autocommit=True) as conn:
        conn.execute("DROP DATABASE IF EXISTS fixer_test WITH (FORCE)")
        conn.execute("CREATE DATABASE fixer_test")
    root = tmp_path_factory.mktemp("fixer")
    os.environ["FIXER_DATABASE_URL"] = TEST_URL
    os.environ["FIXER_SOURCE_DIR"] = str(root / "source")
    os.environ["FIXER_DATA_DIR"] = str(root / "data")
    os.environ["FIXER_STABLE_INTERVAL_S"] = "0"
    from api.settings import get_settings
    get_settings.cache_clear()
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
```

Run: `.venv\Scripts\python.exe -m pytest api/tests/test_health.py -q`. Expected: FAIL, `ModuleNotFoundError: api.settings`.

- [ ] **Step 4: implementation**

`api\settings.py`:

```python
from functools import lru_cache
from pathlib import Path

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_prefix="FIXER_", env_file=".env", extra="ignore")
    database_url: str = "postgresql+psycopg://fixer:fixer@127.0.0.1:5432/fixer"
    source_dir: Path = Path(r"D:\PROJECTS\UC ENVIRONMENT BUILDING\REQUIREMENTS\01-MODEL-EXPORT\CKPT17")
    data_dir: Path = Path("data")
    stable_interval_s: float = 1.0


@lru_cache
def get_settings() -> Settings:
    return Settings()
```

`api\db.py`:

```python
from functools import lru_cache

from sqlalchemy import create_engine
from sqlalchemy.orm import Session

from api.settings import get_settings


@lru_cache
def get_engine():
    return create_engine(get_settings().database_url, pool_pre_ping=True)


def get_session():
    with Session(get_engine()) as session:
        yield session
```

`api\main.py`:

```python
from fastapi import Depends, FastAPI
from sqlalchemy import text
from sqlalchemy.orm import Session

from api.db import get_session


def create_app() -> FastAPI:
    app = FastAPI(title="UC Model Fixer")

    @app.get("/api/health")
    def health(session: Session = Depends(get_session)):
        return {"status": "ok", "db": session.execute(text("select 1")).scalar() == 1}

    return app


app = create_app()
```

- [ ] **Step 5:** Run the test. Expected: `1 passed`.
- [ ] **Step 6:** Commit `feat(api): postgres in docker, settings, session, health`.

---

### Task 3: Tables + migration 0001

**Files:** Create `api\models.py`, `alembic.ini`, `api\alembic\env.py`, `api\alembic\script.py.mako`,
`api\alembic\versions\0001_initial.py`, `api\tests\test_schema.py`. Modify `api\tests\conftest.py`.

**Interfaces — Produces:** ORM classes `Base`, `Model`, `ModelVersion`, `VersionAsset`, `Run`, `IssueType`.

| Table | Columns |
|---|---|
| `models` | `id` pk, `name` str(255) unique, `source_file` str(255), `created_at` timestamptz default now |
| `model_versions` | `id` pk, `model_id` fk, `parent_version_id` fk null, `kind` str(16), `status` str(16) default `ready`, `dir_path` text, `obj_file` str(255), `sha256` str(64), `asset_sha256` str(64), `size_bytes` bigint, `tri_count` int, `vertex_count` int, `material_count` int, `axis_quanta` jsonb, `origin_offset` jsonb, `bbox` jsonb, `stats` jsonb, `flat_materials` jsonb, `produced_by_run_id` fk null, `created_at`. Unique (`model_id`, `kind`, `sha256`, `asset_sha256`) |
| `version_assets` | `id` pk, `version_id` fk, `kind` str(16) (`mtl`, `source_mtl`, `texture`), `name` str(255), `file_name` str(255), `sha256` str(64), `flatness` float null |
| `runs` | `id` pk, `version_id` fk null, `kind` str(16), `status` str(16), `params` jsonb, `engine_commit` str(40) null, `package_versions` jsonb, `started_at`, `finished_at` null, `log` text default '', `error` text null |
| `issue_types` | `key` str(64) pk, `title`, `description` text, `unity_symptom` text, `defect_ref` str(8) null, `meshcheck_kind` str(32) null |

Seed rows for `issue_types` (key · title · defect_ref · meshcheck_kind):
`excess_subdivision` · Gridlines · D1 · unwelded_seam · `coplanar_overlap` · Flickering overlap · D2 · coincident_faces ·
`degenerate` · Zero-area triangles · D5 · sliver · `interior_face` · Hidden inside face · – · – ·
`reversed_face` · Reversed face · – · reversed_faces · `double_sided_pair` · Two-sided pair (info) · – · – ·
`hidden_by_neighbour` · Hidden only by a neighbour object · – · – · `open_edge` · Open edge · – · open_edges ·
`non_manifold` · Edge shared by 3+ faces · – · non_manifold.
Each gets a one-sentence `description` and `unity_symptom` written from the spec's Context section.

- [ ] **Step 1: failing test `api\tests\test_schema.py`**

```python
from sqlalchemy import inspect, text


def test_migration_creates_tables_and_seeds(db):
    names = set(inspect(db.get_bind()).get_table_names())
    assert {"models", "model_versions", "version_assets", "runs", "issue_types", "alembic_version"} <= names
    assert db.execute(text("select count(*) from issue_types")).scalar() == 9
    row = db.execute(text("select defect_ref, meshcheck_kind from issue_types where key='excess_subdivision'")).one()
    assert tuple(row) == ("D1", "unwelded_seam")


def test_version_uniqueness(db):
    from sqlalchemy.exc import IntegrityError
    import pytest
    from api.models import Model, ModelVersion
    m = Model(name="walk", source_file="walk.obj")
    db.add(m); db.flush()
    common = dict(model_id=m.id, kind="snapshot", dir_path="x", obj_file="walk.obj", sha256="a" * 64,
                  asset_sha256="b" * 64, size_bytes=1, tri_count=1, vertex_count=3, material_count=1,
                  axis_quanta=[0.01, 0.1, 0.01], origin_offset=[0, 0, 0], bbox={}, stats={}, flat_materials=[])
    db.add(ModelVersion(**common)); db.flush()
    db.add(ModelVersion(**common))
    with pytest.raises(IntegrityError):
        db.flush()
```

Add to `_database` in `conftest.py`, after `cache_clear()`:

```python
    from alembic import command
    from alembic.config import Config
    command.upgrade(Config("alembic.ini"), "head")
```

And a per-test cleanup so no test depends on another's rows. Ids restart at 1, so the meshbuf cache
(keyed by version id) must be wiped with them:

```python
@pytest.fixture(autouse=True)
def _clean(_database):
    import shutil
    from api.db import get_engine
    from api.settings import get_settings
    with get_engine().begin() as conn:
        conn.execute(text("TRUNCATE version_assets, model_versions, runs, models RESTART IDENTITY CASCADE"))
    shutil.rmtree(get_settings().data_dir / "meshbuf", ignore_errors=True)
    yield
```

`issue_types` and `alembic_version` are never truncated.

Run. Expected: FAIL (`alembic.ini` missing).

- [ ] **Step 2: implement.** `api\models.py` with SQLAlchemy 2 `Mapped[...]` declarations matching the table above
  (`JSONB` from `sqlalchemy.dialects.postgresql`, `DateTime(timezone=True)`, `server_default=func.now()`).
  `alembic.ini`: `script_location = api/alembic`, no `sqlalchemy.url`. `api\alembic\env.py`:

```python
from alembic import context
from sqlalchemy import create_engine

from api.models import Base
from api.settings import get_settings

target_metadata = Base.metadata


def run_migrations_online():
    engine = create_engine(get_settings().database_url)
    with engine.connect() as connection:
        context.configure(connection=connection, target_metadata=target_metadata)
        with context.begin_transaction():
            context.run_migrations()


run_migrations_online()
```

`0001_initial.py` is written by hand with `op.create_table(...)` for the five tables in dependency order
(`models`, `runs`, `model_versions`, `version_assets`, `issue_types`), the unique constraint, and
`op.bulk_insert` for the nine seed rows. `downgrade()` drops them in reverse. `script.py.mako` is Alembic's stock template.

- [ ] **Step 3:** Run `api/tests/test_schema.py`. Expected: `2 passed`. Then apply to the dev database:
  `.venv\Scripts\python.exe -m alembic upgrade head` and
  `docker compose exec db psql -U fixer -d fixer -c "\dt"`. Expected: six tables listed. Paste the output in the report.
- [ ] **Step 4:** Commit `feat(api): schema migration 0001 with seeded issue types`.

---

### Task 4: Importer service

**Files:** Create `api\services\__init__.py`, `api\services\importer.py`, `api\tests\sourcekit.py`, `api\tests\test_importer.py`

**Interfaces — Consumes:** `read_manifest_stable`, `snapshot_object`, `SourceUnstable`, `ManifestMismatch`, `sha256_file`
(`engine.io.snapshot`), `analyse_topology`, `topology_stats`, `flat_material_indices` (`engine.pipeline`).
**Produces:** `UnknownSourceFile(Exception)`,
`scan_source(session, settings, q: str = "") -> dict` (`{"source_state": "ready"|"rebuilding"|"missing", "rows": [{"file","tris","group","imported"}]}`),
`import_object(session, settings, file_name: str) -> ModelVersion`.

`api\tests\sourcekit.py` builds a fake export folder under `FIXER_SOURCE_DIR`:

```python
from pathlib import Path

import numpy as np
from PIL import Image

from engine.io.obj_writer import write_obj
from engine.tests.fixtures.build import grid_slab


def make_export(root: Path, name="CHTM_SIDE_WALK_test.obj") -> Path:
    (root / "split").mkdir(parents=True, exist_ok=True)
    (root / "SRC-TEX").mkdir(exist_ok=True)
    mesh = grid_slab(4, 4)
    mesh.name, mesh.mtllib, mesh.materials = name[:-4], "../lib.mtl", ["stone"]
    write_obj(mesh, root / "split" / name)
    (root / "lib.mtl").write_text("newmtl stone\nmap_Kd SRC-TEX/stone.png\n")
    rng = np.random.default_rng(0)
    Image.fromarray(rng.integers(217, 228, (16, 16, 3)).astype(np.uint8)).save(root / "SRC-TEX" / "stone.png")
    (root / "split" / "_MANIFEST.txt").write_text(
        "file                     tris   sketchup group\n" f"{name}      32   {name[:-4]}\n")
    return root / "split" / name
```

- [ ] **Step 1: failing tests `api\tests\test_importer.py`**

```python
import pytest

from api.models import Run, VersionAsset
from api.services.importer import UnknownSourceFile, import_object, scan_source
from api.settings import get_settings
from api.tests.sourcekit import make_export


def test_import_creates_rows_and_is_idempotent(db):
    s = get_settings()
    make_export(s.source_dir)
    v = import_object(db, s, "CHTM_SIDE_WALK_test.obj")
    assert v.kind == "snapshot" and v.tri_count == 32 and len(v.sha256) == 64 and len(v.asset_sha256) == 64
    assert v.flat_materials == ["stone"] and v.stats["removable_edges"] == 40 and v.stats["regions"] == 1
    kinds = sorted(a.kind for a in db.query(VersionAsset).filter_by(version_id=v.id))
    assert kinds == ["mtl", "source_mtl", "texture"]
    assert db.query(Run).filter_by(version_id=v.id, kind="import", status="ok").count() == 1
    assert import_object(db, s, "CHTM_SIDE_WALK_test.obj").id == v.id


def test_unknown_file_rejected_before_touching_disk(db):
    s = get_settings()
    make_export(s.source_dir)
    with pytest.raises(UnknownSourceFile):
        import_object(db, s, "..\\..\\secret.obj")


def test_scan_marks_imported(db):
    s = get_settings()
    make_export(s.source_dir)
    import_object(db, s, "CHTM_SIDE_WALK_test.obj")
    out = scan_source(db, s, q="side_walk")
    assert out["source_state"] == "ready" and out["rows"] == [
        {"file": "CHTM_SIDE_WALK_test.obj", "tris": 32, "group": "CHTM_SIDE_WALK_test", "imported": True}]


def test_scan_reports_missing_source(db, tmp_path):
    s = get_settings().model_copy(update={"source_dir": tmp_path / "nowhere"})
    assert scan_source(db, s) == {"source_state": "missing", "rows": []}
```

(4x4 slab: 32 tris, edges 8 + 8... interior removable edges = 56 total edges - 16 open = 40.)
Run. Expected: FAIL, `ModuleNotFoundError: api.services.importer`.

- [ ] **Step 2: implement `api\services\importer.py`**

```python
from __future__ import annotations

import subprocess
from datetime import datetime, timezone
from importlib.metadata import version as pkg_version

from sqlalchemy.orm import Session

from api.models import Model, ModelVersion, Run, VersionAsset
from engine.io.snapshot import SourceUnstable, read_manifest_stable, sha256_file, snapshot_object
from engine.pipeline import analyse_topology, flat_material_indices, topology_stats


class UnknownSourceFile(Exception):
    pass


def _manifest(settings):
    return read_manifest_stable(settings.source_dir / "split" / "_MANIFEST.txt", interval_s=settings.stable_interval_s)


def scan_source(session: Session, settings, q: str = "") -> dict:
    if not (settings.source_dir / "split").exists():
        return {"source_state": "missing", "rows": []}
    try:
        rows = _manifest(settings)
    except SourceUnstable:
        return {"source_state": "rebuilding", "rows": []}
    imported = {name for (name,) in session.query(Model.source_file)}
    out = [{"file": r.file, "tris": r.tris, "group": r.group, "imported": r.file in imported}
           for r in rows.values() if q.lower() in r.file.lower()]
    return {"source_state": "ready", "rows": out}


def _engine_commit() -> str | None:
    try:
        return subprocess.run(["git", "rev-parse", "HEAD"], capture_output=True, text=True, timeout=5).stdout.strip() or None
    except OSError:
        return None


def import_object(session: Session, settings, file_name: str) -> ModelVersion:
    rows = _manifest(settings)
    if file_name not in rows:
        raise UnknownSourceFile(file_name)
    started = datetime.now(timezone.utc)
    snap = snapshot_object(settings.source_dir / "split" / file_name, settings.data_dir / "snapshots",
                           expected_tris=rows[file_name].tris, interval_s=settings.stable_interval_s)
    model = session.query(Model).filter_by(name=snap.mesh.name).one_or_none()
    if model is None:
        model = Model(name=snap.mesh.name, source_file=file_name)
        session.add(model)
        session.flush()
    existing = session.query(ModelVersion).filter_by(
        model_id=model.id, kind="snapshot", sha256=snap.sha256, asset_sha256=snap.asset_sha256).one_or_none()
    if existing is not None:
        return existing

    flat = flat_material_indices(snap.mesh, snap.flatness)
    topo = analyse_topology(snap.mesh, flat)
    lo, hi = snap.mesh.bbox()
    run = Run(kind="import", status="ok", params={"file": file_name}, engine_commit=_engine_commit(),
              package_versions={p: pkg_version(p) for p in ("numpy", "shapely", "pillow")},
              started_at=started, finished_at=datetime.now(timezone.utc))
    session.add(run)
    session.flush()
    version = ModelVersion(
        model_id=model.id, kind="snapshot", dir_path=str(snap.dir), obj_file=snap.obj_path.name,
        sha256=snap.sha256, asset_sha256=snap.asset_sha256, size_bytes=snap.size_bytes,
        tri_count=snap.mesh.n_faces, vertex_count=int(len(snap.mesh.positions)),
        material_count=len(snap.mesh.materials), axis_quanta=topo.quanta.tolist(),
        origin_offset=((lo + hi) / 2).tolist(), bbox={"min": lo.tolist(), "max": hi.tolist()},
        stats=topology_stats(topo), flat_materials=[snap.mesh.materials[i] for i in sorted(flat)],
        produced_by_run_id=run.id)
    session.add(version)
    session.flush()
    run.version_id = version.id
    if snap.mtl_path:
        session.add(VersionAsset(version_id=version.id, kind="mtl", name="materials.mtl",
                                 file_name="materials.mtl", sha256=sha256_file(snap.mtl_path)))
    if snap.source_mtl_path:
        session.add(VersionAsset(version_id=version.id, kind="source_mtl", name="source.mtl",
                                 file_name="source.mtl", sha256=sha256_file(snap.source_mtl_path)))
    for material, path in snap.textures.items():
        session.add(VersionAsset(version_id=version.id, kind="texture", name=material,
                                 file_name=f"tex/{path.name}", sha256=sha256_file(path),
                                 flatness=snap.flatness.get(material)))
    session.commit()
    return version
```

- [ ] **Step 3:** Run the importer tests. Expected: `4 passed`. If `removable_edges` differs from 40, hand-count the
  4x4 slab (24 cell borders inside + 16 diagonals = 40) before touching the assertion, and report what you found.
- [ ] **Step 4:** Commit `feat(api): importer service with idempotent snapshot import`.

---

### Task 5: HTTP routers

**Files:** Create `api\schemas.py`, `api\routers\source.py`, `api\routers\models.py`, `api\routers\versions.py`,
`api\routers\runs.py`, `api\tests\test_routes.py`. Modify `api\main.py`.

**Interfaces — Produces** (all under `/api`):

| Method + path | 200 body | Errors |
|---|---|---|
| `GET /source/scan?q=` | `scan_source` dict | – |
| `POST /models/import` `{"file": str}` | 201 `VersionOut`, also when the identical snapshot already exists (import is idempotent, same row comes back) | 404 unknown, 409 + `Retry-After: 5` unstable, 422 manifest mismatch |
| `GET /models` | `[{id, name, source_file, latest_version_id, tri_count}]` | – |
| `GET /models/{id}/versions` | `[VersionOut]` newest first | 404 |
| `GET /versions/{id}` | `VersionOut` | 404 |
| `GET /versions/{id}/meshbuf` | bytes, `application/octet-stream`, cached at `data\meshbuf\{id}.bin` | 404 |
| `GET /versions/{id}/textures/{material}` | image file | 404 |
| `GET /versions/{id}/faces/{face_id}` | `{face_id, line, material, region, vertices[3][3], uvs[3][2]}` | 404 |
| `GET /runs`, `GET /runs/{id}` | `RunOut` | 404 |

`VersionOut` = `id, model_id, kind, status, obj_file, sha256, asset_sha256, size_bytes, tri_count, vertex_count,
material_count, axis_quanta, bbox, stats, flat_materials, created_at`. The meshbuf header's per-material `texture`
is the URL `/api/versions/{id}/textures/{quote(material)}`, or `null` when the material has no texture asset.

- [ ] **Step 1: failing tests `api\tests\test_routes.py`**

```python
import struct

from api.settings import get_settings
from api.tests.sourcekit import make_export


def imported(client):
    make_export(get_settings().source_dir)
    r = client.post("/api/models/import", json={"file": "CHTM_SIDE_WALK_test.obj"})
    assert r.status_code == 201
    return r.json()


def test_import_then_list(client):
    v = imported(client)
    models = client.get("/api/models").json()
    assert models[0]["latest_version_id"] == v["id"] and models[0]["tri_count"] == 32
    assert client.get(f"/api/versions/{v['id']}").json()["sha256"] == v["sha256"]


def test_meshbuf_is_binary_and_cached(client):
    v = imported(client)
    r = client.get(f"/api/versions/{v['id']}/meshbuf")
    assert r.status_code == 200 and r.content[:4] == b"UCMB" and struct.unpack("<I", r.content[4:8])[0] == 1
    assert (get_settings().data_dir / "meshbuf" / f"{v['id']}.bin").exists()
    assert f"/api/versions/{v['id']}/textures/stone".encode() in r.content


def test_texture_served_by_lookup_only(client):
    v = imported(client)
    assert client.get(f"/api/versions/{v['id']}/textures/stone").headers["content-type"] == "image/png"
    assert client.get(f"/api/versions/{v['id']}/textures/..%2F..%2Fmaterials.mtl").status_code == 404


def test_face_maps_back_to_source_line(client):
    v = imported(client)
    f = client.get(f"/api/versions/{v['id']}/faces/0").json()
    assert f["face_id"] == 0 and f["line"] > 0 and f["material"] == "stone" and len(f["vertices"]) == 3
    assert client.get(f"/api/versions/{v['id']}/faces/999").status_code == 404


def test_errors(client, monkeypatch):
    make_export(get_settings().source_dir)
    assert client.post("/api/models/import", json={"file": "nope.obj"}).status_code == 404
    from engine.io.snapshot import SourceUnstable
    import api.routers.models as mod
    monkeypatch.setattr(mod, "import_object", lambda *a, **k: (_ for _ in ()).throw(SourceUnstable("rebuilding")))
    r = client.post("/api/models/import", json={"file": "CHTM_SIDE_WALK_test.obj"})
    assert r.status_code == 409 and r.headers["retry-after"] == "5"
```

Run. Expected: FAIL (404 on every route).

- [ ] **Step 2: implement.** One `APIRouter(prefix="/api")` per file, registered in `create_app()`. Rules:
  - `POST /models/import`: `try: v = import_object(...)` / `except UnknownSourceFile: 404` /
    `except SourceUnstable as e: raise HTTPException(409, str(e), headers={"Retry-After": "5"})` /
    `except ManifestMismatch as e: 422`.
  - `meshbuf`: if cache file exists return it. Else `mesh = read_obj(Path(v.dir_path) / v.obj_file)`,
    `flat = frozenset(i for i, n in enumerate(mesh.materials) if n in v.flat_materials)`,
    `topo = analyse_topology(mesh, flat)`, textures dict built from `VersionAsset` rows of kind `texture`,
    `pack_meshbuf(...)`, write cache, return `Response(content=..., media_type="application/octet-stream")`.
  - `textures`: `VersionAsset` lookup by `(version_id, kind="texture", name=material)`; `FileResponse(Path(v.dir_path) / asset.file_name)`.
    No match -> 404. Never build a path from the URL segment.
  - `faces`: read the OBJ once per request, 404 when `face_id` out of range; `region` from `analyse_topology`.
- [ ] **Step 3:** Run `api/tests -q`. Expected: all pass. Then the whole suite.
- [ ] **Step 4: real import.** Start the API through `.claude\launch.json` (Task 8 adds the config; for this step run
  `.venv\Scripts\python.exe -m uvicorn api.main:app --port 8000` in the background) and:
  `curl -s -X POST localhost:8000/api/models/import -H "content-type: application/json" -d "{\"file\":\"CHTM_SIDE_WALK_2nd_floor.obj\"}"`.
  Expected: 201, `tri_count 4692`, `sha256` starting `ce26e039` (unless re-exported since). Then
  `certutil -hashfile data\snapshots\<dir>\CHTM_SIDE_WALK_2nd_floor.obj SHA256` must print the same hash as the
  database row: `docker compose exec db psql -U fixer -d fixer -c "select sha256, tri_count from model_versions"`.
  Paste all three outputs in the report. A 409 means the other pipeline is rebuilding: wait, retry, report.
- [ ] **Step 5:** Commit `feat(api): source scan, import, versions, meshbuf, textures, faces, runs`.

---

### Task 6: Web scaffold + meshbuf decoder

**Files:** Create `web\package.json` (via pnpm), `web\index.html`, `web\vite.config.ts`, `web\tsconfig.json`,
`web\src\main.ts`, `web\src\App.vue`, `web\src\router.ts`, `web\src\env.d.ts`, `web\src\api\client.ts`,
`web\src\three\meshbuf.ts`, `web\src\three\meshbuf.test.ts`

**Interfaces — Produces:**
`decodeMeshbuf(buf: ArrayBuffer): DecodedMeshbuf` with `header`, `positions: Float32Array`, `uvs`, `normals`,
`triMaterial: Uint16Array`, `triFaceId: Uint32Array`, `triRegion: Int32Array`, `edgePositions: Float32Array`, `edgeClass: Uint8Array`.
`api` object: `scan(q)`, `importFile(file)`, `models()`, `versions(modelId)`, `version(id)`, `meshbuf(id): Promise<ArrayBuffer>`, `face(versionId, faceId)`.

- [ ] **Step 1: scaffold**

```
mkdir web
pnpm --dir web init
pnpm --dir web add vue vue-router three
pnpm --dir web add -D vite @vitejs/plugin-vue typescript vue-tsc vitest @types/three
```

Set `"type": "module"` and scripts `"dev": "vite"`, `"build": "vue-tsc -b && vite build"`, `"test": "vitest run"` in `web\package.json`.

`web\vite.config.ts`:

```ts
import vue from '@vitejs/plugin-vue'
import { defineConfig } from 'vitest/config'

export default defineConfig({
  plugins: [vue()],
  server: { port: 5173, proxy: { '/api': 'http://127.0.0.1:8000' } },
  test: { environment: 'node' },
})
```

- [ ] **Step 2: failing test `web\src\three\meshbuf.test.ts`** — builds a buffer by hand in the engine's layout
  (`UCMB`, u32 version, u32 header length, space-padded JSON, 4-byte padded blocks, offsets relative to data start):

```ts
import { describe, expect, it } from 'vitest'
import { decodeMeshbuf } from './meshbuf'

function build(): ArrayBuffer {
  const pos = new Float32Array([0, 0, 0, 1, 0, 0, 0, 1, 0])
  const cls = new Uint8Array([1])
  const blocks = [
    { name: 'positions', dtype: 'f32', shape: [3, 3], offset: 0, nbytes: 36 },
    { name: 'edge_class', dtype: 'u8', shape: [1], offset: 36, nbytes: 1 },
  ]
  let json = JSON.stringify({ version: 1, name: 't', counts: { faces: 1, edges: 1 }, materials: [], blocks })
  while (json.length % 4) json += ' '
  const head = new TextEncoder().encode(json)
  const out = new Uint8Array(12 + head.length + 40)
  out.set([0x55, 0x43, 0x4d, 0x42])
  const dv = new DataView(out.buffer)
  dv.setUint32(4, 1, true); dv.setUint32(8, head.length, true)
  out.set(head, 12)
  out.set(new Uint8Array(pos.buffer), 12 + head.length)
  out.set(cls, 12 + head.length + 36)
  return out.buffer
}

describe('decodeMeshbuf', () => {
  it('reads header and typed blocks', () => {
    const d = decodeMeshbuf(build())
    expect(d.header.counts.faces).toBe(1)
    expect(Array.from(d.positions)).toEqual([0, 0, 0, 1, 0, 0, 0, 1, 0])
    expect(Array.from(d.edgeClass)).toEqual([1])
  })
  it('rejects a foreign file', () => {
    expect(() => decodeMeshbuf(new Uint8Array(16).buffer)).toThrow(/not a meshbuf/)
  })
})
```

Run: `pnpm --dir web test`. Expected: FAIL, cannot resolve `./meshbuf`.

- [ ] **Step 3: `web\src\three\meshbuf.ts`**

```ts
export interface MeshbufHeader {
  version: number; name: string; units?: string; unit_scale_m?: number
  origin_offset?: number[]; bbox?: { min: number[]; max: number[] }
  materials: { name: string; texture: string | null }[]
  counts: { faces: number; edges: number }
  blocks: { name: string; dtype: 'f32' | 'u16' | 'u32' | 'i32' | 'u8'; shape: number[]; offset: number; nbytes: number }[]
}
export interface DecodedMeshbuf {
  header: MeshbufHeader
  positions: Float32Array; uvs: Float32Array; normals: Float32Array
  triMaterial: Uint16Array; triFaceId: Uint32Array; triRegion: Int32Array
  edgePositions: Float32Array; edgeClass: Uint8Array
}
const CTOR = { f32: Float32Array, u16: Uint16Array, u32: Uint32Array, i32: Int32Array, u8: Uint8Array }

export function decodeMeshbuf(buf: ArrayBuffer): DecodedMeshbuf {
  const magic = new TextDecoder().decode(new Uint8Array(buf, 0, 4))
  if (magic !== 'UCMB') throw new Error('not a meshbuf')
  const dv = new DataView(buf)
  const hlen = dv.getUint32(8, true)
  const header = JSON.parse(new TextDecoder().decode(new Uint8Array(buf, 12, hlen))) as MeshbufHeader
  const start = 12 + hlen
  const get = (name: string, dtype: keyof typeof CTOR) => {
    const b = header.blocks.find(x => x.name === name)
    if (!b) return new CTOR[dtype](0)
    return new CTOR[b.dtype](buf, start + b.offset, b.shape.reduce((a, n) => a * n, 1))
  }
  return {
    header,
    positions: get('positions', 'f32') as Float32Array, uvs: get('uvs', 'f32') as Float32Array,
    normals: get('normals', 'f32') as Float32Array, triMaterial: get('tri_material', 'u16') as Uint16Array,
    triFaceId: get('tri_face_id', 'u32') as Uint32Array, triRegion: get('tri_region', 'i32') as Int32Array,
    edgePositions: get('edge_positions', 'f32') as Float32Array, edgeClass: get('edge_class', 'u8') as Uint8Array,
  }
}
```

`web\src\api\client.ts`: a `json<T>(path, init?)` helper that throws an `ApiError` carrying `status` and
`retryAfter` (from the `Retry-After` header), plus the seven wrappers listed above.
`main.ts`, `App.vue` (`<router-view/>`), `router.ts` (`/` -> ModelsView, `/models/:id` -> WorkspaceView; both views are
created as one-line stubs here and filled in Task 8), `index.html`, `tsconfig.json` (strict, `moduleResolution: "bundler"`).

- [ ] **Step 4:** `pnpm --dir web test` -> `2 passed`. `pnpm --dir web build` -> exits 0.
- [ ] **Step 5:** Add `web/node_modules/` and `web/dist/` are already covered by `.gitignore`. Commit
  `feat(web): vite + vue scaffold, api client, meshbuf decoder`.

---

### Task 7: Viewport, overlays, picking, camera sync

**Files:** Create `web\src\three\Viewport.ts`, `web\src\three\sync.ts`

**Interfaces — Consumes:** `DecodedMeshbuf`.
**Produces:**
`class Viewport { constructor(el: HTMLElement); load(d: DecodedMeshbuf): void; setEdgeClassVisible(cls: number, on: boolean): void; setOneSided(on: boolean): void; pick(clientX: number, clientY: number): number | null; highlight(triIndex: number | null): void; copyCameraFrom(o: Viewport): void; dispose(): void; readonly controls; readonly camera }`,
`EDGE_CLASSES = [{id:0,key:'real',label:'region outline',color:0x222222},{id:1,key:'removable',label:'gridline (removable)',color:0x1f5bff},{id:2,key:'open',label:'open edge',color:0xd8282f},{id:3,key:'nonmanifold',label:'3+ faces',color:0xff9500},{id:4,key:'tjunction',label:'T-junction',color:0xaf52de}]`,
`syncViewports(a: Viewport, b: Viewport, enabled: () => boolean): () => void`.

Port from `preview\index.html` (already verified in a browser): Z-up camera (`camera.up.set(0,0,1)` before creating
`OrbitControls`), hemisphere + directional light, `ResizeObserver`, canvas absolutely positioned inside an
`overflow:hidden` container, `fit()` with distance `size * 1.45`, busy-flag camera sync. Differences from the preview:

- Geometry comes from `positions` / `uvs` / `normals` attributes. One `BufferGeometry`, material **groups** built from
  runs of equal `triMaterial` (`geometry.addGroup(start*3, count*3, materialIndex)`), material array of
  `MeshLambertMaterial({ side: THREE.DoubleSide, polygonOffset: true, polygonOffsetFactor: 1, polygonOffsetUnits: 1 })`.
  Index 65535 maps to one extra grey material appended at the end.
- Textures from `header.materials[i].texture` via `TextureLoader`: `RepeatWrapping` both axes,
  `magFilter = NearestFilter`, `colorSpace = SRGBColorSpace`. `null` -> plain `0xd0d0d4`.
- One `LineSegments` per edge class, built by filtering `edgePositions` with `edgeClass`.
- `setOneSided(true)` sets every mesh material to `THREE.FrontSide`; default and `false` is `DoubleSide`.
- `pick`: `Raycaster.setFromCamera` with NDC from the canvas rect, `intersectObject(mesh)`, return
  `triFaceId[hit.faceIndex]`. Geometry is non-indexed so `faceIndex` is the triangle index.
- `highlight(k)`: a 3-vertex mesh, `MeshBasicMaterial({ color: 0xffd400, depthTest: false, side: DoubleSide })`, `renderOrder = 10`.
- `dispose()`: cancel the animation frame, disconnect the observer, dispose geometries, materials, textures, renderer.

- [ ] **Step 1:** Write `Viewport.ts` and `sync.ts` as specified. No unit test: WebGL has no headless target here.
  Its proof is Task 8's browser verification. State that in the report, do not claim it is tested.
- [ ] **Step 2:** `pnpm --dir web build`. Expected: exits 0 with no type errors.
- [ ] **Step 3:** Commit `feat(web): three.js viewport with edge classes, picking, camera sync`.

---

### Task 8: Pages + end-to-end proof

**Files:** Create `web\src\views\ModelsView.vue`, `web\src\views\WorkspaceView.vue`. Modify `.claude\launch.json`.

**ModelsView:** search box bound to `scan(q)` (default `q = "side"`), table of manifest rows with `tris`, `imported`
badge and an **Import** button. Banner for `source_state`: `rebuilding` -> "Export folder is being rebuilt, try again in
a few seconds", `missing` -> path not found. On 409 show the same rebuilding banner with the `retryAfter` value; never
auto-retry in a loop. Below: imported models, each linking to `/models/:id`.

**WorkspaceView:** loads `versions(modelId)`, takes the newest `snapshot`, fetches and decodes `meshbuf`, feeds the
**same** decoded buffer to two `Viewport`s.
- Left `BEFORE · as exported`: all five edge classes on.
- Right `AFTER · PREVIEW: removable edges hidden, geometry unchanged`: class 1 forced off, its checkbox disabled.
- Toolbar: one checkbox per `EDGE_CLASSES` entry with colour swatch, `one-sided (diagnostic)` off by default,
  `sync cameras` on by default.
- Stat bars from `version.stats`: left `tri_count`, `zero_area_faces`, `removable_edges`, `nonmanifold_edges`;
  right `regions`, `real_edges`, and the text "Fixed geometry arrives in Phase 3".
- Click without drag (pointer moved < 4 px) on either canvas -> `pick` -> `face(versionId, faceId)` -> side panel
  showing face id, source `f` line, material, region, three vertices. Both viewports highlight that triangle.

`.claude\launch.json` gains two configurations next to `preview`:

```json
{ "name": "api", "runtimeExecutable": ".venv/Scripts/python.exe",
  "runtimeArgs": ["-m", "uvicorn", "api.main:app", "--port", "8000"], "port": 8000 },
{ "name": "web", "runtimeExecutable": "pnpm", "runtimeArgs": ["--dir", "web", "dev"], "port": 5173 }
```

- [ ] **Step 1:** Write both views. `pnpm --dir web build` exits 0.
- [ ] **Step 2: run it.** `docker compose up -d db`, `alembic upgrade head`, start `api` and `web` through the preview tool.
- [ ] **Step 3: proof artefacts**, each pasted or attached in the report:
  1. Screenshot of ModelsView listing the two `CHTM_*` sidewalk rows with correct `tris` (4,692 and 7,227).
  2. Import both through the UI. `select m.name, v.tri_count, v.sha256 from model_versions v join models m on m.id = v.model_id;` shows two rows.
  3. Screenshot of WorkspaceView for `CHTM_SIDE_WALK_2nd_floor`: left canvas with blue gridlines, right without.
  4. Browser console: zero errors.
  5. **Pick test**: click a triangle, note `face id` and `f line` from the panel, then
     `sed -n '<line>p' data/snapshots/<dir>/CHTM_SIDE_WALK_2nd_floor.obj` prints an `f` line whose three vertex
     indices, resolved against the `v` lines, equal the three vertices shown in the panel.
  6. Toggle `one-sided (diagnostic)`: screenshot shows holes appearing, toggle off shows them gone.
- [ ] **Step 4:** Commit `feat(web): models and workspace pages`.

---

## Phase 1B done when

- `.venv\Scripts\python.exe -m pytest -q` and `pnpm --dir web test` pass, real counts pasted.
- All six proof artefacts of Task 8 exist.
- `git grep -n "FIXER_SOURCE_DIR\|source_dir" api web` shows the source dir used only in `api\settings.py` and
  `api\services\importer.py`, and there only to build arguments for `engine.io.snapshot` functions.

Deferred to later phases: issues, decisions, guard, fixes, recipes, preferences, hand tagging, job queue
(import is synchronous in Phase 1: sidewalk topology takes 0.27 s).
