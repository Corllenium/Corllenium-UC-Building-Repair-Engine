### Task 5: the API keeps one errors file per version

**Files:**
- Create: `api/routers/errors.py`
- Modify: `api/main.py` (include the router)
- Test: `api/tests/test_errors.py`

**Interfaces:**
- Consumes: `find_errors`; the `ModelVersion` and `VersionAsset` models; `get_db`; `Settings.data_dir`.
- Produces:
  - `POST /api/versions/{id}/errors` returns 200 with the errors dict (Task 2's keys).
  - `GET /api/versions/{id}/errors` returns 200 with the dict, or 404 with `{"detail": "not computed yet"}`.
  - Unknown version: 404 `{"detail": "Version not found"}`.
  - `errors_file(settings, version_id) -> Path` is importable by Task 6.

- [ ] **Step 1: Write the failing tests** (`api/tests/test_errors.py`)

```python
def test_errors_are_not_computed_before_the_button(client, imported_cube):
    vid = imported_cube["versions"][0]["id"]
    r = client.get(f"/api/versions/{vid}/errors")
    assert r.status_code == 404
    assert r.json()["detail"] == "not computed yet"


def test_find_errors_saves_the_file_and_serves_it(client, imported_cube):
    from api.routers.errors import errors_file
    from api.settings import get_settings
    vid = imported_cube["versions"][0]["id"]
    r = client.post(f"/api/versions/{vid}/errors")
    assert r.status_code == 200
    body = r.json()
    assert body["n_faces"] == 12
    assert set(body["counts"]) == {"flicker_diff", "flicker_same", "reversed", "hidden", "loose",
                                   "open_edges", "cracks"}
    assert errors_file(get_settings(), vid).exists()
    again = client.get(f"/api/versions/{vid}/errors")
    assert again.status_code == 200
    assert again.json() == body


def test_an_unknown_version_is_refused(client):
    r = client.post("/api/versions/999999/errors")
    assert r.status_code == 404
    assert r.json()["detail"] == "Version not found"
```

- [ ] **Step 2: Run them and see them fail**

Run: `.venv/Scripts/python.exe -m pytest api/tests/test_errors.py -q -p no:cacheprovider`
Expected: FAIL (404 for the POST: no such route).

- [ ] **Step 3: Implement** `api/routers/errors.py`:

```python
"""The 3D error filter's files: one per version, `data/errors/version-<id>.json`."""
import json
from pathlib import Path

from fastapi import APIRouter, Depends, HTTPException, status
from fastapi.responses import JSONResponse
from sqlalchemy import select
from sqlalchemy.orm import Session

from api.db import get_db
from api.models import ModelVersion, VersionAsset
from api.settings import Settings, get_settings
from engine.detectors.errors import find_errors
from engine.fixes.pipeline import FixProfile
from engine.io.obj_reader import read_obj

router = APIRouter(prefix="/api/versions", tags=["errors"])


def errors_file(settings: Settings, version_id: int) -> Path:
    return settings.data_dir / "errors" / f"version-{version_id}.json"


def write_errors(settings: Settings, version_id: int, result: dict) -> None:
    path = errors_file(settings, version_id)
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(".json.tmp")
    tmp.write_text(json.dumps(result), encoding="utf-8")
    tmp.replace(path)


@router.post("/{id}/errors")
def compute_errors(id: int, db: Session = Depends(get_db), settings: Settings = Depends(get_settings)):
    version = db.scalar(select(ModelVersion).where(ModelVersion.id == id))
    if version is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Version not found")
    obj_asset = db.scalar(select(VersionAsset).where(VersionAsset.version_id == id, VersionAsset.kind == "obj"))
    if obj_asset is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="OBJ asset not found")
    obj_path = settings.data_dir / obj_asset.path
    if not obj_path.exists():
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="OBJ file missing on disk")
    result = find_errors(read_obj(obj_path), FixProfile())
    write_errors(settings, id, result)
    return JSONResponse(result)


@router.get("/{id}/errors")
def get_errors(id: int, settings: Settings = Depends(get_settings)):
    path = errors_file(settings, id)
    if not path.exists():
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="not computed yet")
    return JSONResponse(json.loads(path.read_text(encoding="utf-8")))
```

In `api/main.py`, add the import next to the other routers and include it:

```python
from api.routers.errors import router as errors_router
```

```python
    app.include_router(errors_router)
```

- [ ] **Step 4: Run them and see them pass**

Run: `.venv/Scripts/python.exe -m pytest api/tests/test_errors.py -q -p no:cacheprovider`
Expected: 3 passed.

- [ ] **Step 5: Commit**

```bash
git add api/routers/errors.py api/main.py api/tests/test_errors.py
git commit -m "feat(api): Find errors per version, kept as data/errors/version-<id>.json" -m "POST computes a version's errors file with find_errors; GET serves it or says not computed yet. No table, no migration." -m "Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>"
```

---

