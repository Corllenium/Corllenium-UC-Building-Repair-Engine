### Task 1: the image route

**Files:**
- Create: `api/routers/docs.py`
- Modify: `api/main.py` (import and `include_router`)
- Test: `api/tests/test_docs.py`

**Interfaces:**
- Produces: `GET /api/docs/images/{name}` returns the file `settings.data_dir / "errors_doc" / "img" / name`, with the content type from its extension. A bad name or a missing file returns 404 `{"detail": "Image not found"}`.

- [ ] **Step 1: Write the failing tests** (`api/tests/test_docs.py`)

```python
"""The Errors & fixes page's image route (spec 2026-09-26-errors-and-fixes-page-design.md)."""
from api.settings import get_settings

PNG = b"\x89PNG\r\n\x1a\n" + b"\0" * 16


def _img_dir():
    d = get_settings().data_dir / "errors_doc" / "img"
    d.mkdir(parents=True, exist_ok=True)
    return d


def test_serves_an_image_with_its_type(client):
    (_img_dir() / "you-0921-0346-1.png").write_bytes(PNG)
    r = client.get("/api/docs/images/you-0921-0346-1.png")
    assert r.status_code == 200
    assert r.headers["content-type"] == "image/png"
    assert r.content == PNG


def test_webp_and_jpg_get_their_own_types(client):
    (_img_dir() / "you-0921-0346-2.webp").write_bytes(b"RIFF0000WEBP")
    (_img_dir() / "after-x.jpg").write_bytes(b"\xff\xd8\xff")
    assert client.get("/api/docs/images/you-0921-0346-2.webp").headers["content-type"] == "image/webp"
    assert client.get("/api/docs/images/after-x.jpg").headers["content-type"] == "image/jpeg"


def test_a_missing_image_is_404(client):
    r = client.get("/api/docs/images/nope.png")
    assert r.status_code == 404
    assert r.json() == {"detail": "Image not found"}


def test_names_outside_the_pattern_are_404(client):
    (get_settings().data_dir / "secret.png").write_bytes(PNG)
    (_img_dir() / "notes.txt").write_text("x", encoding="utf-8")
    for name in ["notes.txt", "..%2Fsecret.png", "..%5C..%5Csecret.png", "%2E%2E", "a%20b.png", "x.png%0A"]:
        assert client.get(f"/api/docs/images/{name}").status_code == 404, name
```

- [ ] **Step 2: Run and see them fail**

Run: `.venv/Scripts/python.exe -m pytest api/tests/test_docs.py -q -p no:cacheprovider`
Expected: 3 tests FAIL with 404 where 200 was expected. `test_names_outside_the_pattern_are_404` may already pass, because an unknown route is also a 404.

- [ ] **Step 3: Implement** `api/routers/docs.py`

```python
"""Images for the dashboard's Errors & fixes page, served from data/errors_doc/img.

The owner's screenshots stay out of git (spec 2026-09-26-errors-and-fixes-page-design.md), so
the web image cannot hold them; the API, which mounts data/, serves them by plain file name.
"""
import re

from fastapi import APIRouter, Depends, HTTPException, status
from fastapi.responses import FileResponse

from api.settings import Settings, get_settings

router = APIRouter(prefix="/api/docs", tags=["docs"])

IMAGE_NAME = re.compile(r"[A-Za-z0-9_.-]+\.(png|webp|jpg)")
MEDIA_TYPES = {"png": "image/png", "webp": "image/webp", "jpg": "image/jpeg"}


@router.get("/images/{name}")
def get_doc_image(name: str, settings: Settings = Depends(get_settings)):
    match = IMAGE_NAME.fullmatch(name)
    path = settings.data_dir / "errors_doc" / "img" / name
    if match is None or not path.is_file():
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Image not found")
    return FileResponse(path, media_type=MEDIA_TYPES[match.group(1)])
```

In `api/main.py`:
- add `from api.routers.docs import router as docs_router` after the other router imports;
- add `app.include_router(docs_router)` after `app.include_router(fixes_router)`.

- [ ] **Step 4: Run and see them pass**, then the health test (it builds the whole app)

Run: `.venv/Scripts/python.exe -m pytest api/tests/test_docs.py api/tests/test_health.py -q -p no:cacheprovider`
Expected: all pass.

- [ ] **Step 5: Commit**

```bash
git add api/routers/docs.py api/main.py api/tests/test_docs.py
git commit -m "feat(api): serve the Errors & fixes page's images from data/errors_doc/img" -m "The owner's screenshots stay out of git, so the API (which mounts data/) serves them by plain file name; any other name, or a missing file, is a 404." -m "Co-Authored-By: <your model> <noreply@anthropic.com>"
```

---

