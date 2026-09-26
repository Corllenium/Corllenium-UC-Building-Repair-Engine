### Task 9: the owner's verdicts through the API

**Files:**
- Modify: `api/routers/docs.py` (from Task 1)
- Test: `api/tests/test_docs.py` (append)

**Interfaces:**
- Produces:
  - `GET /api/docs/validation` returns `{"version": 1, "verdicts": {kind_id: {model_id: {verdict, note, at}}}}`, or an empty document when there is no file yet.
  - `PUT /api/docs/validation/{kind_id}/{model_id}`:
    - The body is `{"verdict": "error"|"ok"|"unsure"|null, "note": str <= 2000 chars}`. `null` clears the verdict.
    - It returns `{"kind", "model", "entry"}`.
    - The file is `settings.data_dir / "errors_doc" / "validation.json"`, written atomically.
    - `kind_id` must fully match `[a-z0-9][a-z0-9-]{0,63}`, and `model_id` must fully match `[A-Za-z0-9][A-Za-z0-9_-]{0,31}`; otherwise 404.
  - `validation_file(settings)` and `read_validation(settings)` are importable.

- [ ] **Step 1: Write the failing tests** (append to `api/tests/test_docs.py`; add `import json` at the top)

```python
from api.routers.docs import validation_file


def _fresh():
    validation_file(get_settings()).unlink(missing_ok=True)


def test_validation_starts_empty(client):
    _fresh()
    assert client.get("/api/docs/validation").json() == {"version": 1, "verdicts": {}}


def test_a_verdict_is_saved_and_read_back(client):
    _fresh()
    r = client.put("/api/docs/validation/hidden-faces/CHTM5", json={"verdict": "error", "note": "remove all"})
    assert r.status_code == 200
    assert r.json()["entry"]["verdict"] == "error"
    got = client.get("/api/docs/validation").json()["verdicts"]["hidden-faces"]["CHTM5"]
    assert got["verdict"] == "error" and got["note"] == "remove all" and got["at"].endswith("Z")
    on_disk = json.loads(validation_file(get_settings()).read_text(encoding="utf-8"))
    assert on_disk["verdicts"]["hidden-faces"]["CHTM5"]["note"] == "remove all"


def test_clearing_a_verdict_removes_it(client):
    _fresh()
    client.put("/api/docs/validation/sawtooth/B", json={"verdict": "ok", "note": ""})
    r = client.put("/api/docs/validation/sawtooth/B", json={"verdict": None})
    assert r.json()["entry"] is None
    assert client.get("/api/docs/validation").json() == {"version": 1, "verdicts": {}}


def test_bad_verdicts_and_ids_are_refused(client):
    assert client.put("/api/docs/validation/hidden-faces/A", json={"verdict": "maybe"}).status_code == 422
    assert client.put("/api/docs/validation/hidden-faces/A", json={"verdict": "ok", "note": "x" * 2001}).status_code == 422
    assert client.put("/api/docs/validation/Hidden..Faces/A", json={"verdict": "ok"}).status_code == 404
    assert client.put("/api/docs/validation/hidden-faces/A%20B", json={"verdict": "ok"}).status_code == 404
```

- [ ] **Step 2: Run and see them fail**

Run: `.venv/Scripts/python.exe -m pytest api/tests/test_docs.py -q -p no:cacheprovider`
Expected: the collection fails, because `validation_file` cannot be imported.

- [ ] **Step 3: Implement.** Add to `api/routers/docs.py`: `import json`, `import os`, `import tempfile`, `import threading`, `from datetime import datetime, timezone`, `from typing import Literal`, and `from pydantic import BaseModel, Field`, next to the other imports. Then append:

```python
KIND_ID = re.compile(r"[a-z0-9][a-z0-9-]{0,63}")
MODEL_ID = re.compile(r"[A-Za-z0-9][A-Za-z0-9_-]{0,31}")
_LOCK = threading.Lock()  # one read-modify-write at a time within this process


class VerdictIn(BaseModel):
    verdict: Literal["error", "ok", "unsure"] | None
    note: str = Field(default="", max_length=2000)


def validation_file(settings: Settings):
    return settings.data_dir / "errors_doc" / "validation.json"


def read_validation(settings: Settings) -> dict:
    path = validation_file(settings)
    if not path.is_file():
        return {"version": 1, "verdicts": {}}
    return json.loads(path.read_text(encoding="utf-8"))


def _write_validation(settings: Settings, data: dict) -> None:
    path = validation_file(settings)
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, tmp = tempfile.mkstemp(dir=path.parent, prefix="validation-", suffix=".tmp")
    with os.fdopen(fd, "w", encoding="utf-8") as fh:
        json.dump(data, fh, indent=1)
    os.replace(tmp, path)


@router.get("/validation")
def get_validation(settings: Settings = Depends(get_settings)):
    return read_validation(settings)


@router.put("/validation/{kind_id}/{model_id}")
def put_verdict(kind_id: str, model_id: str, body: VerdictIn, settings: Settings = Depends(get_settings)):
    """The owner's verdict on one kind of error in one model; a null verdict clears it."""
    if not KIND_ID.fullmatch(kind_id) or not MODEL_ID.fullmatch(model_id):
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Unknown error kind or model")
    with _LOCK:
        data = read_validation(settings)
        per_kind = data["verdicts"].setdefault(kind_id, {})
        entry = None
        if body.verdict is None:
            per_kind.pop(model_id, None)
        else:
            entry = {"verdict": body.verdict, "note": body.note,
                     "at": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")}
            per_kind[model_id] = entry
        if not per_kind:
            del data["verdicts"][kind_id]
        _write_validation(settings, data)
    return {"kind": kind_id, "model": model_id, "entry": entry}
```

- [ ] **Step 4: Run and see them pass**

Run: `.venv/Scripts/python.exe -m pytest api/tests/test_docs.py api/tests/test_health.py -q -p no:cacheprovider`
Expected: all pass (8 docs tests and the health tests).

- [ ] **Step 5: Commit**

```bash
git add api/routers/docs.py api/tests/test_docs.py
git commit -m "feat(api): the owner's verdict per error kind and model, kept in data/errors_doc/validation.json" -m "The owner validates each error before the fix phase ('sometimes it seems like an error but it's okay for that model'); the verdicts live beside the page's images, with no database change, so the fix phase can read them." -m "Co-Authored-By: <your model> <noreply@anthropic.com>"
```

