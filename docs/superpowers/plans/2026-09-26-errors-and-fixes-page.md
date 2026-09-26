# Errors & fixes page Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** A dashboard page at `/errors` that documents every error found in the two CHTM sidewalk exports and in the engine, with the owner's own screenshots, what fixed each error, and the measured results.

**Architecture:**
- The content is one committed JSON file, `web/public/docs/errors.json`, which Vite copies into `dist/docs/`.
- The page (`ErrorsView.vue`) fetches it, filters in the browser (model, kind, engine file), and keeps the filter in the URL query.
- The owner's screenshots and the AFTER renders stay out of git, in `data/errors_doc/img/`. The API serves them from `GET /api/docs/images/{name}`.
- A tool extracts the owner's screenshots from the session log. A second tool renders the AFTER images from the owner's current `.skp`.

**Tech Stack:** Vue 3 + vue-router 4 + TypeScript (vitest), FastAPI (pytest), Python 3.12 tools.

**Spec:** `docs/superpowers/specs/2026-09-26-errors-and-fixes-page-design.md`

## Global Constraints

- **No database change:** no migration, no table, no write to the live database `fixer`.
- **Images:**
  - The owner's screenshots and every render live in the git-ignored `data/errors_doc/img/` and are never committed.
  - `errors.json` names images by plain file name. A name must match `^[A-Za-z0-9_.-]+\.(png|webp|jpg)$`.
- **Read-only sources:**
  - The session log (`C:/Users/Future26/.claude/projects/D--PROJECTS-UC-MODEL-FIXER/5472478e-978d-426b-bab2-e7cf21699a70.jsonl`) is read, never written.
  - Nothing is ever written in `D:\PROJECTS\UC ENVIRONMENT BUILDING\...`.
- **Kinds** (id, label):

  | id | label |
  |---|---|
  | `inside-faces` | Hidden inside faces |
  | `sides-bottoms` | Sides and bottoms |
  | `lines-gridlines` | Lines and gridlines |
  | `back-faces` | Back faces |
  | `layers-flicker` | Double layers and flicker |
  | `fragments` | Fragments and slivers |
  | `engine-bug` | Engine bug |

- **Engine files:**
  - `vis/exposure.py`, `fixes/remove.py`, `fixes/solidify.py`, `fixes/merge.py`, `fixes/orient.py`, `fixes/overlap.py`;
  - `detectors/fragments.py`, `detectors/folds.py`;
  - `guard/compare.py`, `guard/piece_rays.py`;
  - `io/skp_writer.py`, `topo/adjacency.py`, `topo/planes.py`.

  In the URL query an engine file is its stem (`solidify` for `fixes/solidify.py`).
- **Sections:** `fixed` = "Fixed & partly fixed", `open` = "Still open", `engine-bug` = "Engine bugs from reviews", in that order. **Status:** `fixed`, `partly`, `open`.
- **Python:**
  - Use `"D:/PROJECTS/UC MODEL FIXER/.venv/Scripts/python.exe"` with `PYTHONPATH` set to the worktree root.
  - API tests: `-m pytest api/tests/<file> -q -p no:cacheprovider`. Each run gets its own `fixer_test_<pid>_*` database.
  - Tool tests: `-m pytest tools/tests/<file> -q -p no:cacheprovider`.
- **Web:**
  - `pnpm --dir web install --frozen-lockfile` once per fresh worktree.
  - Tests: `pnpm --dir web exec vitest run <file>`; types: `pnpm --dir web run type-check`; build: `pnpm --dir web run build`.
- **Commits:** stage files by name, never `git add -A`. End every message with a `Co-Authored-By:` line naming the model that wrote the commit.
- **Deploy:** only by HANDOFF.md section 8, from a commit, with the database backed up and the old images tagged first.

## Rulings on the spec (made while planning)

- Ruling: the content file lives at `web/public/docs/errors.json` (URL `/docs/errors.json`), not `web/public/errors/errors.json`. The spec's path would create `dist/errors/`, and nginx's `try_files $uri $uri/ /index.html` answers `/errors` with a 301 to `/errors/` and then a 403, so the page would break on reload. If this ruling is wrong, it costs one path.
- Ruling: the page's behaviour is tested through pure functions in `errorsDoc.ts` (filter, group, choices, query, validation), and the view itself through `vue-tsc`, the build and the browser check. The spec also asks for a mounted view test, but the project has no `@vue/test-utils` or DOM environment, and adding them duplicates the browser check (global rule 6). If this ruling is wrong, it costs one dev dependency and a test later.

## File map

| File | Task | Responsibility |
|---|---|---|
| `api/routers/docs.py` (new), `api/main.py`, `api/tests/test_docs.py` (new) | 1 | Serve `data/errors_doc/img/<name>` safely |
| `tools/errors_doc/__init__.py`, `extract_owner_images.py`, `check.py` (new); `tools/tests/test_errors_doc.py` (new) | 2 | Owner screenshots out of the log; image check |
| `web/src/utils/errorsDoc.ts`, `errorsDoc.test.ts` (new); `web/public/docs/errors.json` (seed) | 3 | Types, filters, grouping, query, validation; the content test |
| `web/src/views/ErrorsView.vue` (new), `web/src/router.ts`, `web/src/views/ModelsView.vue` | 4 | The page, route, header button, lightbox |
| `web/public/docs/errors.json` (content) | 5 (controller) | Every entry, numbers re-read, images assigned |
| `tools/errors_doc/render_after.py`, `tools/errors_doc/cameras.json` (new) | 6 | AFTER renders from the owner `.skp` |
| records | 7 (controller) | Deploy, check, screenshots, backup |

---

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

### Task 2: the owner's screenshots out of the session log, and the image check

**Files:**
- Create: `tools/errors_doc/__init__.py` (empty), `tools/errors_doc/extract_owner_images.py`, `tools/errors_doc/check.py`
- Test: `tools/tests/test_errors_doc.py`

**Interfaces:**
- Produces:
  - `extract(log_path, out_dir) -> list[dict]`. It writes `out_dir/img/you-<MMDD>-<HHMM>-<n>.<png|webp|jpg>` (UTC time from the log) and `out_dir/owner_images.json`.
  - Each record is `{file, time, words, words_from, line, media_type, sha256}`, in log order. Identical pictures (same bytes) are saved once.
  - `missing_images(errors_json, img_dir) -> list[str]`.
  - `unused_owner_images(errors_json, owner_images_json) -> list[str]`.
  - CLI: `python -m tools.errors_doc.extract_owner_images <log> --out data/errors_doc` and `python -m tools.errors_doc.check`. The check's exit code is 1 when anything is missing or unused.

- [ ] **Step 1: Write the failing tests** (`tools/tests/test_errors_doc.py`)

```python
"""tools/errors_doc on a small made-up session log (spec 2026-09-26-errors-and-fixes-page-design.md)."""
import base64
import hashlib
import json

from tools.errors_doc.check import missing_images, unused_owner_images
from tools.errors_doc.extract_owner_images import extract

PNG = b"\x89PNG\r\n\x1a\nowner-one"
WEBP = b"RIFF\x00\x00\x00\x00WEBPowner-two"
PNG3 = b"\x89PNG\r\n\x1a\nowner-three"
SHOT = b"\x89PNG\r\n\x1a\nclaude-screenshot"


def _img(data: bytes, media: str) -> dict:
    return {"type": "image", "source": {"type": "base64", "media_type": media,
                                        "data": base64.b64encode(data).decode()}}


def _log(tmp_path):
    human = {"kind": "human"}
    lines = [
        {"type": "user", "timestamp": "2026-09-21T03:46:24.877Z", "origin": human,
         "message": {"role": "user", "content": [_img(PNG, "image/png"),
                                                 {"type": "text", "text": "the inside faces"}]}},
        {"type": "user", "timestamp": "2026-09-21T04:38:35.745Z",
         "message": {"role": "user", "content": [{"type": "tool_result", "tool_use_id": "t1",
                                                  "content": [_img(SHOT, "image/png")]}]}},
        {"type": "attachment", "timestamp": "2026-09-22T10:05:00.000Z",
         "attachment": {"type": "queued_command", "origin": human, "timestamp": "2026-09-22T10:05:00.000Z",
                        "prompt": [_img(WEBP, "image/webp"), {"type": "text", "text": "gridlines here"}]}},
        {"type": "user", "timestamp": "2026-09-23T08:00:00.000Z", "origin": human,
         "message": {"role": "user", "content": [_img(PNG3, "image/png")]}},
        {"type": "user", "timestamp": "2026-09-23T08:00:30.000Z", "origin": human,
         "message": {"role": "user", "content": "this is the hole"}},
        {"type": "user", "timestamp": "2026-09-24T09:00:00.000Z", "origin": human,
         "message": {"role": "user", "content": [_img(PNG, "image/png"), {"type": "text", "text": "again"}]}},
        "not json at all",
    ]
    p = tmp_path / "session.jsonl"
    p.write_text("\n".join(x if isinstance(x, str) else json.dumps(x) for x in lines) + "\n", encoding="utf-8")
    return p


def test_saves_each_owner_image_with_their_words(tmp_path):
    out = tmp_path / "errors_doc"
    records = extract(_log(tmp_path), out)
    assert [r["file"] for r in records] == ["you-0921-0346-1.png", "you-0922-1005-1.webp", "you-0923-0800-1.png"]
    assert (out / "img" / "you-0921-0346-1.png").read_bytes() == PNG
    assert (out / "img" / "you-0922-1005-1.webp").read_bytes() == WEBP
    assert [r["words"] for r in records] == ["the inside faces", "gridlines here", "this is the hole"]
    assert [r["words_from"] for r in records] == ["same message", "same message", "next message"]
    assert records[0]["line"] == 1 and records[1]["line"] == 3
    saved = json.loads((out / "owner_images.json").read_text(encoding="utf-8"))
    assert saved == records


def test_skips_claude_s_own_screenshots_and_keeps_a_repeated_picture_once(tmp_path):
    out = tmp_path / "errors_doc"
    records = extract(_log(tmp_path), out)
    files = sorted(p.name for p in (out / "img").iterdir())
    assert len(files) == 3
    assert all((out / "img" / f).read_bytes() != SHOT for f in files)
    assert sum(r["sha256"] == hashlib.sha256(PNG).hexdigest() for r in records) == 1


def test_two_messages_in_one_minute_get_different_numbers(tmp_path):
    human = {"kind": "human"}
    lines = [{"type": "user", "timestamp": f"2026-09-25T12:30:{s:02d}.000Z", "origin": human,
              "message": {"role": "user", "content": [_img(bytes([s]) * 8, "image/png")]}} for s in (1, 2)]
    log = tmp_path / "s.jsonl"
    log.write_text("\n".join(json.dumps(x) for x in lines), encoding="utf-8")
    assert [r["file"] for r in extract(log, tmp_path / "o")] == ["you-0925-1230-1.png", "you-0925-1230-2.png"]


def _doc(tmp_path, errors, other=()):
    p = tmp_path / "errors.json"
    p.write_text(json.dumps({"built_from": {"commit": "x", "date": "d"}, "models": [],
                             "errors": errors, "other_screenshots": list(other)}), encoding="utf-8")
    return p


def test_check_names_images_that_are_missing(tmp_path):
    img = tmp_path / "img"
    img.mkdir()
    (img / "you-0921-0346-1.png").write_bytes(PNG)
    doc = _doc(tmp_path, [{"you_saw": [{"image": "you-0921-0346-1.png"}], "after": [{"image": "after-a.png"}]}],
               [{"image": "you-0922-1005-1.webp"}])
    assert missing_images(doc, img) == ["after-a.png", "you-0922-1005-1.webp"]


def test_check_names_owner_images_used_nowhere(tmp_path):
    owner = tmp_path / "owner_images.json"
    owner.write_text(json.dumps([{"file": "you-0921-0346-1.png"}, {"file": "you-0923-0800-1.png"}]), encoding="utf-8")
    doc = _doc(tmp_path, [{"you_saw": [{"image": "you-0921-0346-1.png"}], "after": []}])
    assert unused_owner_images(doc, owner) == ["you-0923-0800-1.png"]
```

- [ ] **Step 2: Run and see them fail**

Run: `.venv/Scripts/python.exe -m pytest tools/tests/test_errors_doc.py -q -p no:cacheprovider`
Expected: FAIL. The collection error is `ModuleNotFoundError: No module named 'tools.errors_doc'`.

- [ ] **Step 3: Implement.** First `tools/errors_doc/__init__.py`, as an empty file. Then `tools/errors_doc/extract_owner_images.py`:

```python
"""Save every image the owner sent in a Claude Code session log, with their words.

Spec: docs/superpowers/specs/2026-09-26-errors-and-fixes-page-design.md. Two kinds of log line
carry the owner's pictures, both marked as sent by a human:
- type "user" whose message content holds image blocks (a new message);
- type "attachment" of type "queued_command" whose prompt holds image blocks (sent while work ran).
Tool results that carry images are Claude's own screenshots and are skipped. A picture sent twice
(same bytes) is saved once. File names use the log's UTC time: you-<MMDD>-<HHMM>-<n>.<ext>.
"""
import argparse
import base64
import hashlib
import json
import sys
from pathlib import Path

EXT = {"image/png": "png", "image/webp": "webp", "image/jpeg": "jpg"}


def _human(entry: dict):
    """(timestamp, content blocks) of a message the owner sent, else None."""
    kind = entry.get("type")
    if kind == "user":
        if (entry.get("origin") or {}).get("kind") != "human":
            return None
        content = (entry.get("message") or {}).get("content")
        ts = entry.get("timestamp", "")
    elif kind == "attachment":
        att = entry.get("attachment") or {}
        if att.get("type") != "queued_command" or (att.get("origin") or {}).get("kind") != "human":
            return None
        content = att.get("prompt")
        ts = att.get("timestamp") or entry.get("timestamp", "")
    else:
        return None
    if isinstance(content, str):
        content = [{"type": "text", "text": content}]
    if not isinstance(content, list):
        return None
    if any(isinstance(b, dict) and b.get("type") == "tool_result" for b in content):
        return None
    return ts, content


def _messages(log_path: Path) -> list[tuple[int, str, list[tuple[str, bytes]], str]]:
    """(line number, time, images, words) for every message the owner sent, in log order."""
    out = []
    with log_path.open(encoding="utf-8") as fh:
        for line_no, line in enumerate(fh, 1):
            try:
                entry = json.loads(line)
            except json.JSONDecodeError:
                continue
            got = _human(entry) if isinstance(entry, dict) else None
            if got is None:
                continue
            ts, blocks = got
            images, words = [], []
            for b in blocks:
                if not isinstance(b, dict):
                    continue
                if b.get("type") == "text" and (b.get("text") or "").strip():
                    words.append(b["text"].strip())
                src = b.get("source") or {}
                if b.get("type") == "image" and src.get("type") == "base64" and src.get("media_type") in EXT:
                    images.append((src["media_type"], base64.b64decode(src["data"])))
            out.append((line_no, ts, images, " ".join(words)))
    return out


def extract(log_path, out_dir) -> list[dict]:
    log_path, out_dir = Path(log_path), Path(out_dir)
    messages = _messages(log_path)
    img_dir = out_dir / "img"
    img_dir.mkdir(parents=True, exist_ok=True)
    seen: set[str] = set()
    per_minute: dict[str, int] = {}
    records = []
    for k, (line_no, ts, images, words) in enumerate(messages):
        words_from = "same message"
        if images and not words:
            words = next((m[3] for m in messages[k + 1:] if m[3]), "")
            words_from = "next message"
        for media, data in images:
            digest = hashlib.sha256(data).hexdigest()
            if digest in seen:
                continue
            seen.add(digest)
            stamp = f"{ts[5:7]}{ts[8:10]}-{ts[11:13]}{ts[14:16]}"  # 2026-09-21T03:46 -> 0921-0346
            per_minute[stamp] = per_minute.get(stamp, 0) + 1
            name = f"you-{stamp}-{per_minute[stamp]}.{EXT[media]}"
            (img_dir / name).write_bytes(data)
            records.append({"file": name, "time": ts, "words": words, "words_from": words_from,
                            "line": line_no, "media_type": media, "sha256": digest})
    (out_dir / "owner_images.json").write_text(json.dumps(records, indent=1), encoding="utf-8")
    return records


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description="Save the owner's screenshots from a session log.")
    ap.add_argument("log", type=Path)
    ap.add_argument("--out", type=Path, default=Path("data/errors_doc"))
    a = ap.parse_args(argv)
    records = extract(a.log, a.out)
    print(f"{len(records)} images -> {a.out / 'img'}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
```

Then `tools/errors_doc/check.py`:

```python
"""Every image errors.json names exists, and every owner screenshot is used somewhere.

Spec: docs/superpowers/specs/2026-09-26-errors-and-fixes-page-design.md ("every image the owner
sent appears somewhere"). Exit code 1 when anything is missing or unused.
"""
import argparse
import json
import sys
from pathlib import Path


def _named_images(errors_json: Path) -> set[str]:
    doc = json.loads(Path(errors_json).read_text(encoding="utf-8"))
    items = [i for e in doc.get("errors", []) for i in e.get("you_saw", []) + e.get("after", [])]
    items += doc.get("other_screenshots", [])
    return {i["image"] for i in items if i.get("image")}


def missing_images(errors_json, img_dir) -> list[str]:
    return sorted(n for n in _named_images(errors_json) if not (Path(img_dir) / n).is_file())


def unused_owner_images(errors_json, owner_images_json) -> list[str]:
    owner = json.loads(Path(owner_images_json).read_text(encoding="utf-8"))
    used = _named_images(errors_json)
    return sorted(r["file"] for r in owner if r["file"] not in used)


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description="Check the Errors & fixes page's images.")
    ap.add_argument("--errors-json", type=Path, default=Path("web/public/docs/errors.json"))
    ap.add_argument("--doc-dir", type=Path, default=Path("data/errors_doc"))
    a = ap.parse_args(argv)
    missing = missing_images(a.errors_json, a.doc_dir / "img")
    unused = unused_owner_images(a.errors_json, a.doc_dir / "owner_images.json")
    for n in missing:
        print(f"missing: {n}")
    for n in unused:
        print(f"unused owner screenshot: {n}")
    print(f"{len(missing)} missing, {len(unused)} unused")
    return 1 if missing or unused else 0


if __name__ == "__main__":
    sys.exit(main())
```

- [ ] **Step 4: Run and see them pass**

Run: `.venv/Scripts/python.exe -m pytest tools/tests -q -p no:cacheprovider`
Expected: all pass (the 5 new tests and the existing auto_continue tests).

- [ ] **Step 5: Commit**

```bash
git add tools/errors_doc/__init__.py tools/errors_doc/extract_owner_images.py tools/errors_doc/check.py tools/tests/test_errors_doc.py
git commit -m "feat(tools): extract the owner's screenshots from the session log, and check the page's images" -m "The Errors & fixes page shows the owner's own pictures; they are read from the session log (never written), saved once each under data/errors_doc/img, and check.py fails when errors.json names a missing image or leaves an owner screenshot unused." -m "Co-Authored-By: <your model> <noreply@anthropic.com>"
```

---

### Task 3 (SUPERSEDED by Task 8 — owner 11:55; do not implement): the page's logic, and the content test

**Files:**
- Create: `web/src/utils/errorsDoc.ts`, `web/src/utils/errorsDoc.test.ts`, `web/public/docs/errors.json` (a seed the controller fills in Task 5)

**Interfaces:**
- Produces (all exported from `web/src/utils/errorsDoc.ts`):
  - types `Section`, `Status`, `YouSaw`, `AfterImage`, `ErrorEntry`, `ModelCard`, `ErrorsDoc`, `DocFilter`;
  - `KINDS`, `ENGINE_FILES`, `SECTIONS`, `IMAGE_NAME`;
  - `engineStem(file)`, `filterErrors(errors, filter)`, `groupBySection(errors)`;
  - `filterChoices(doc)`, `filterFromQuery(query, doc)`, `filterToQuery(filter)`;
  - `imageUrl(name)`, `kindLabel(id)`, `validateDoc(doc) -> string[]` (the problems; empty = valid).

- [ ] **Step 1: Write the failing tests** (`web/src/utils/errorsDoc.test.ts`)

```ts
import { describe, it, expect } from 'vitest'
import {
  filterErrors, groupBySection, filterChoices, filterFromQuery, filterToQuery, imageUrl,
  engineStem, kindLabel, validateDoc, type ErrorsDoc, type ErrorEntry,
} from './errorsDoc'
import content from '../../public/docs/errors.json'

function entry(over: Partial<ErrorEntry>): ErrorEntry {
  return {
    id: 'x', section: 'fixed', status: 'fixed', title: 'T', models: ['A'], kind: 'inside-faces',
    engine_files: ['vis/exposure.py'], you_saw: [], after: [],
    error: 'What it is.', how_fixed: 'What the engine does.', ...over,
  }
}

const doc: ErrorsDoc = {
  built_from: { commit: 'ab22ff3', date: '2026-09-25 23:53' },
  models: [
    { id: 'A', name: 'CHTM_SIDE_WALK_2nd_floor', skp: 'a.skp', numbers: {}, source: 's' },
    { id: 'B', name: 'CHTM_2nd_to_3rd_building_sidewalk_outside', skp: 'b.skp', numbers: {}, source: 's' },
  ],
  errors: [
    entry({ id: 'hidden', models: ['A', 'B'] }),
    entry({ id: 'sides', kind: 'sides-bottoms', engine_files: ['fixes/solidify.py'] }),
    entry({ id: 'knife', section: 'open', status: 'open', models: ['A'], kind: 'sides-bottoms',
            engine_files: ['fixes/solidify.py'] }),
    entry({ id: 'guard-blind', section: 'engine-bug', status: 'fixed', models: ['B'], kind: 'engine-bug',
            engine_files: ['guard/compare.py'] }),
  ],
  other_screenshots: [],
}

describe('errorsDoc', () => {
  it('filters by model, kind and engine file, all combined', () => {
    const none = { model: null, kind: null, engine: null }
    expect(filterErrors(doc.errors, none).map(e => e.id)).toEqual(['hidden', 'sides', 'knife', 'guard-blind'])
    expect(filterErrors(doc.errors, { ...none, model: 'B' }).map(e => e.id)).toEqual(['hidden', 'guard-blind'])
    expect(filterErrors(doc.errors, { ...none, kind: 'sides-bottoms' }).map(e => e.id)).toEqual(['sides', 'knife'])
    expect(filterErrors(doc.errors, { model: 'A', kind: 'sides-bottoms', engine: 'fixes/solidify.py' })
      .map(e => e.id)).toEqual(['sides', 'knife'])
    expect(filterErrors(doc.errors, { model: 'B', kind: 'sides-bottoms', engine: null })).toEqual([])
  })

  it('groups into the three sections in order and hides empty ones', () => {
    expect(groupBySection(doc.errors).map(s => [s.id, s.title, s.entries.length])).toEqual([
      ['fixed', 'Fixed & partly fixed', 2], ['open', 'Still open', 1], ['engine-bug', 'Engine bugs from reviews', 1]])
    expect(groupBySection(doc.errors.filter(e => e.section !== 'open')).map(s => s.id)).toEqual(['fixed', 'engine-bug'])
  })

  it('offers only the kinds and engine files some entry uses', () => {
    const c = filterChoices(doc)
    expect(c.models.map(m => m.id)).toEqual(['A', 'B'])
    expect(c.kinds.map(k => k.id)).toEqual(['inside-faces', 'sides-bottoms', 'engine-bug'])
    expect(c.engineFiles).toEqual(['vis/exposure.py', 'fixes/solidify.py', 'guard/compare.py'])
  })

  it('reads the filter from the URL query and ignores unknown values', () => {
    expect(filterFromQuery({ model: 'A', kind: 'sides-bottoms', engine: 'solidify' }, doc))
      .toEqual({ model: 'A', kind: 'sides-bottoms', engine: 'fixes/solidify.py' })
    expect(filterFromQuery({ model: 'Z', kind: 'nope', engine: 'merge' }, doc))
      .toEqual({ model: null, kind: null, engine: null })
    expect(filterFromQuery({ model: ['B', 'A'] }, doc).model).toBe('B')
  })

  it('writes the filter back as a short query', () => {
    expect(filterToQuery({ model: 'A', kind: null, engine: 'fixes/solidify.py' })).toEqual({ model: 'A', engine: 'solidify' })
    expect(engineStem('guard/piece_rays.py')).toBe('piece_rays')
  })

  it('builds image URLs through the API and labels kinds in plain words', () => {
    expect(imageUrl('you-0921-0346-1.png')).toBe('/api/docs/images/you-0921-0346-1.png')
    expect(kindLabel('layers-flicker')).toBe('Double layers and flicker')
  })

  it('names every problem in a bad document', () => {
    const bad: ErrorsDoc = { ...doc, errors: [
      entry({ id: 'a', error: '', kind: 'nonsense', engine_files: ['fixes/nope.py'],
              you_saw: [{ date: '2026-09-21', words: 'w', image: '../x.png' }], models: ['C'] }),
      entry({ id: 'a', section: 'later' as never, status: 'maybe' as never, how_fixed: ' ' }),
    ] }
    const problems = validateDoc(bad)
    expect(problems).toEqual([
      'a: "error" is empty',
      'a: unknown kind "nonsense"',
      'a: unknown engine file "fixes/nope.py"',
      'a: unknown model "C"',
      'a: bad image name "../x.png"',
      'a: duplicate id',
      'a: unknown section "later"',
      'a: unknown status "maybe"',
      'a: "how_fixed" is empty',
    ])
    expect(validateDoc(doc)).toEqual([])
  })

  it('the committed errors.json is valid', () => {
    expect(validateDoc(content as unknown as ErrorsDoc)).toEqual([])
  })
})
```

- [ ] **Step 2: Run and see them fail**

Run: `pnpm --dir web exec vitest run src/utils/errorsDoc.test.ts`
Expected: FAIL. The module `./errorsDoc` and `../../public/docs/errors.json` do not resolve.

- [ ] **Step 3: Implement** `web/src/utils/errorsDoc.ts`

```ts
// The Errors & fixes page's content model and logic (spec 2026-09-26-errors-and-fixes-page-design.md).
// The page itself only renders what these functions return.

export type Section = 'fixed' | 'open' | 'engine-bug'
export type Status = 'fixed' | 'partly' | 'open'

export interface YouSaw { date: string; words: string; image?: string }
export interface AfterImage { image: string; caption?: string }
export interface ErrorEntry {
  id: string
  section: Section
  status: Status
  title: string
  models: string[]
  kind: string
  engine_files: string[]
  you_saw: YouSaw[]
  after: AfterImage[]
  error: string
  how_fixed: string
  engine_detail?: string
  commits?: string[]
  result?: Record<string, string>
  left?: string | null
  source?: string
}
export interface ModelCard {
  id: string
  name: string
  skp: string
  numbers: Record<string, number | number[]>
  source: string
}
export interface ErrorsDoc {
  built_from: { commit: string; date: string }
  models: ModelCard[]
  errors: ErrorEntry[]
  other_screenshots: YouSaw[]
}
export interface DocFilter { model: string | null; kind: string | null; engine: string | null }

export const KINDS: { id: string; label: string }[] = [
  { id: 'inside-faces', label: 'Hidden inside faces' },
  { id: 'sides-bottoms', label: 'Sides and bottoms' },
  { id: 'lines-gridlines', label: 'Lines and gridlines' },
  { id: 'back-faces', label: 'Back faces' },
  { id: 'layers-flicker', label: 'Double layers and flicker' },
  { id: 'fragments', label: 'Fragments and slivers' },
  { id: 'engine-bug', label: 'Engine bug' },
]

export const ENGINE_FILES: string[] = [
  'vis/exposure.py', 'fixes/remove.py', 'fixes/solidify.py', 'fixes/merge.py', 'fixes/orient.py',
  'fixes/overlap.py', 'detectors/fragments.py', 'detectors/folds.py', 'guard/compare.py',
  'guard/piece_rays.py', 'io/skp_writer.py', 'topo/adjacency.py', 'topo/planes.py',
]

export const SECTIONS: { id: Section; title: string }[] = [
  { id: 'fixed', title: 'Fixed & partly fixed' },
  { id: 'open', title: 'Still open' },
  { id: 'engine-bug', title: 'Engine bugs from reviews' },
]

const STATUSES: Status[] = ['fixed', 'partly', 'open']
export const IMAGE_NAME = /^[A-Za-z0-9_.-]+\.(png|webp|jpg)$/

export const engineStem = (file: string): string => file.split('/').pop()!.replace(/\.py$/, '')
export const kindLabel = (id: string): string => KINDS.find(k => k.id === id)?.label ?? id
export const imageUrl = (name: string): string => `/api/docs/images/${encodeURIComponent(name)}`

export function filterErrors(errors: ErrorEntry[], f: DocFilter): ErrorEntry[] {
  return errors.filter(e =>
    (!f.model || e.models.includes(f.model)) &&
    (!f.kind || e.kind === f.kind) &&
    (!f.engine || e.engine_files.includes(f.engine)))
}

export function groupBySection(errors: ErrorEntry[]): { id: Section; title: string; entries: ErrorEntry[] }[] {
  return SECTIONS
    .map(s => ({ ...s, entries: errors.filter(e => e.section === s.id) }))
    .filter(s => s.entries.length > 0)
}

export function filterChoices(doc: ErrorsDoc) {
  const kinds = new Set(doc.errors.map(e => e.kind))
  const files = new Set(doc.errors.flatMap(e => e.engine_files))
  return {
    models: doc.models.map(m => ({ id: m.id, label: `${m.id} · ${m.name}` })),
    kinds: KINDS.filter(k => kinds.has(k.id)),
    engineFiles: ENGINE_FILES.filter(f => files.has(f)),
  }
}

/** The filter from the URL query; a value that is not one of the page's choices is ignored. */
export function filterFromQuery(query: Record<string, unknown>, doc: ErrorsDoc): DocFilter {
  const one = (v: unknown) => (Array.isArray(v) ? v[0] : v)
  const c = filterChoices(doc)
  const model = one(query.model), kind = one(query.kind), engine = one(query.engine)
  return {
    model: c.models.some(m => m.id === model) ? (model as string) : null,
    kind: c.kinds.some(k => k.id === kind) ? (kind as string) : null,
    engine: c.engineFiles.find(f => engineStem(f) === engine) ?? null,
  }
}

export function filterToQuery(f: DocFilter): Record<string, string> {
  const q: Record<string, string> = {}
  if (f.model) q.model = f.model
  if (f.kind) q.kind = f.kind
  if (f.engine) q.engine = engineStem(f.engine)
  return q
}

/** Every rule the spec puts on errors.json, as readable problems; empty means valid. */
export function validateDoc(doc: ErrorsDoc): string[] {
  const problems: string[] = []
  const models = new Set(doc.models.map(m => m.id))
  const seen = new Set<string>()
  const checkImage = (id: string, name: string | undefined) => {
    if (name !== undefined && !IMAGE_NAME.test(name)) problems.push(`${id}: bad image name "${name}"`)
  }
  for (const e of doc.errors) {
    if (seen.has(e.id)) problems.push(`${e.id}: duplicate id`)
    seen.add(e.id)
    if (!SECTIONS.some(s => s.id === e.section)) problems.push(`${e.id}: unknown section "${e.section}"`)
    if (!STATUSES.includes(e.status)) problems.push(`${e.id}: unknown status "${e.status}"`)
    if (!e.error?.trim()) problems.push(`${e.id}: "error" is empty`)
    if (!e.how_fixed?.trim()) problems.push(`${e.id}: "how_fixed" is empty`)
    if (!KINDS.some(k => k.id === e.kind)) problems.push(`${e.id}: unknown kind "${e.kind}"`)
    for (const f of e.engine_files) if (!ENGINE_FILES.includes(f)) problems.push(`${e.id}: unknown engine file "${f}"`)
    for (const m of e.models) if (!models.has(m)) problems.push(`${e.id}: unknown model "${m}"`)
    for (const s of e.you_saw) checkImage(e.id, s.image)
    for (const a of e.after) checkImage(e.id, a.image)
  }
  for (const s of doc.other_screenshots) checkImage('other_screenshots', s.image)
  return problems
}
```

Check the expected order in the "names every problem" test against this code before running it:
- The first entry `a` is new, and passes section and status. Its problems come out as: `error` empty, kind, engine file, model, image.
- The second entry `a` gives: duplicate, section, status, `how_fixed` empty.
- This order is exactly the test's list, because the checks run duplicate, section, status, error, how_fixed, kind, engine files, models, images. For the first entry only `error` fires among the first five, so its list starts with `"error" is empty`.

Then create the seed `web/public/docs/errors.json`. It is valid and has one entry; the controller fills the rest in Task 5:

```json
{
  "built_from": { "commit": "ab22ff3", "date": "2026-09-25 23:53" },
  "models": [
    { "id": "A", "name": "CHTM_SIDE_WALK_2nd_floor",
      "skp": "D:/PROJECTS/UC MODEL FIXER/OBJ FIXED RESULT/CHTM_SIDE_WALK_2nd_floor.fixed.skp",
      "numbers": {}, "source": "data/output_verified/CHTM_SIDE_WALK_2nd_floor/report.json at ab22ff3" },
    { "id": "B", "name": "CHTM_2nd_to_3rd_building_sidewalk_outside",
      "skp": "D:/PROJECTS/UC MODEL FIXER/OBJ FIXED RESULT/CHTM_2nd_to_3rd_building_sidewalk_outside.fixed.skp",
      "numbers": {}, "source": "data/output_verified/CHTM_2nd_to_3rd_building_sidewalk_outside/report.json at ab22ff3" }
  ],
  "errors": [
    { "id": "hidden-inside-faces", "section": "fixed", "status": "fixed",
      "title": "Hidden faces inside the slabs",
      "models": ["A", "B"], "kind": "inside-faces",
      "engine_files": ["vis/exposure.py", "fixes/remove.py"],
      "you_saw": [], "after": [],
      "error": "SketchUp exports every face it has, including the partition faces inside a slab. Nobody can see them from outside, but in X-ray they fill the slab, and in Unity they cost triangles and cause flicker.",
      "how_fixed": "The engine shoots rays in every direction from four points on each face. A face that no ray from outside can reach is removed. Before it goes, the guard renders the model from 26 directions with and without it; if any pixel changes, the face is put back.",
      "engine_detail": "engine/vis/exposure.py compute_side_exposure, classify_exposure; engine/fixes/remove.py; guard: engine/guard/compare.py",
      "commits": [], "result": {}, "left": null, "source": "report.json" }
  ],
  "other_screenshots": []
}
```

- [ ] **Step 4: Run and see them pass**, then the type check

Run: `pnpm --dir web exec vitest run src/utils/errorsDoc.test.ts` and then `pnpm --dir web run type-check`
Expected: 8 tests pass; the type check exits 0. If `vue-tsc` rejects the JSON import, add `"resolveJsonModule": true` to the `compilerOptions` of the tsconfig that includes `src` (look in `web/tsconfig.app.json` or `web/tsconfig.json`), and list that file in the commit.

- [ ] **Step 5: Commit**

```bash
git add web/src/utils/errorsDoc.ts web/src/utils/errorsDoc.test.ts web/public/docs/errors.json
git commit -m "feat(web): the Errors & fixes page's content model, filters and content test" -m "errors.json is committed and filtered in the browser (spec approach A); validateDoc enforces the spec's rules on it, and the test runs it on the committed file." -m "Co-Authored-By: <your model> <noreply@anthropic.com>"
```

---

### Task 4 (SUPERSEDED by Task 10 — owner 11:55; do not implement): the page

**Files:**
- Create: `web/src/views/ErrorsView.vue`
- Modify: `web/src/router.ts` (route `/errors`), `web/src/views/ModelsView.vue` (header button)

**Interfaces:**
- Consumes: everything Task 3 exports; `GET /docs/errors.json` (static); `GET /api/docs/images/{name}` (Task 1).

- [ ] **Step 1: Add the route** in `web/src/router.ts`. Import `ErrorsView from './views/ErrorsView.vue'` after the other view imports, and add `{ path: '/errors', name: 'errors', component: ErrorsView },` after the workspace route.

- [ ] **Step 2: Add the header button** in `web/src/views/ModelsView.vue`. Put it inside `<div class="header-actions">`, before the Refresh button:

```vue
        <router-link to="/errors" class="btn btn-secondary">Errors &amp; fixes</router-link>
```

- [ ] **Step 3: Create** `web/src/views/ErrorsView.vue`:

```vue
<template>
  <div class="errors-page">
    <header class="page-header">
      <div>
        <router-link to="/" class="back">← Models</router-link>
        <h1>Errors &amp; fixes</h1>
        <p class="purpose">Every error found in the CHTM sidewalk exports and in the engine, what fixed it, and what is still open.</p>
        <p v-if="doc" class="built">Built from commit <code>{{ doc.built_from.commit }}</code>, {{ doc.built_from.date }}</p>
      </div>
    </header>

    <p v-if="loadError" class="error-box">Could not load the documentation: {{ loadError }}</p>
    <p v-else-if="!doc" class="muted">Loading…</p>

    <template v-if="doc">
      <section class="built-cards">
        <h2>What we built</h2>
        <div class="cards">
          <article v-for="m in doc.models" :key="m.id" class="model-card">
            <h3>{{ m.id }} · {{ m.name }}</h3>
            <dl>
              <template v-for="(value, key) in m.numbers" :key="key">
                <dt>{{ numberLabel(String(key)) }}</dt>
                <dd>{{ Array.isArray(value) ? `${fmt(value[0])} → ${fmt(value[1])}` : fmt(value) }}</dd>
              </template>
            </dl>
            <div class="skp">
              <code>{{ m.skp }}</code>
              <button class="btn btn-secondary btn-small" @click="copy(m.skp)">{{ copied === m.skp ? 'Copied' : 'Copy' }}</button>
            </div>
            <p class="source">Source: {{ m.source }}</p>
          </article>
        </div>
      </section>

      <section class="filters">
        <label>Model
          <select v-model="filter.model">
            <option :value="null">All</option>
            <option v-for="m in choices.models" :key="m.id" :value="m.id">{{ m.label }}</option>
          </select>
        </label>
        <label>Kind
          <select v-model="filter.kind">
            <option :value="null">All</option>
            <option v-for="k in choices.kinds" :key="k.id" :value="k.id">{{ k.label }}</option>
          </select>
        </label>
        <label>Engine file
          <select v-model="filter.engine">
            <option :value="null">All</option>
            <option v-for="f in choices.engineFiles" :key="f" :value="f">{{ f }}</option>
          </select>
        </label>
        <span class="count">{{ shown.length }} of {{ doc.errors.length }} errors</span>
        <button class="btn btn-secondary btn-small" @click="clear">Clear</button>
      </section>

      <section v-for="s in sections" :key="s.id" class="section">
        <h2>{{ s.title }} <span class="muted">({{ s.entries.length }})</span></h2>
        <article v-for="e in s.entries" :id="e.id" :key="e.id" class="entry">
          <header class="entry-head">
            <h3>{{ e.title }}</h3>
            <span class="status" :class="e.status">{{ STATUS_LABEL[e.status] }}</span>
            <span v-for="m in e.models" :key="m" class="tag">Model {{ m }}</span>
            <span class="tag">{{ kindLabel(e.kind) }}</span>
            <span v-for="f in e.engine_files" :key="f" class="tag mono">{{ f }}</span>
          </header>

          <div v-if="e.you_saw.length || e.after.length" class="pair">
            <div class="col">
              <h4>What you saw</h4>
              <figure v-for="(s2, n) in e.you_saw" :key="n">
                <img v-if="s2.image" :src="imageUrl(s2.image)" :alt="s2.words" loading="lazy" @click="openBox(entryImages(e), s2.image)" />
                <figcaption><span class="date">{{ s2.date }}</span> “{{ s2.words }}”</figcaption>
              </figure>
            </div>
            <div class="col">
              <h4>After</h4>
              <figure v-for="(a, n) in e.after" :key="n">
                <img :src="imageUrl(a.image)" :alt="a.caption ?? 'After'" loading="lazy" @click="openBox(entryImages(e), a.image)" />
                <figcaption v-if="a.caption">{{ a.caption }}</figcaption>
              </figure>
              <p v-if="!e.after.length" class="muted">No render yet.</p>
            </div>
          </div>

          <h4>The error</h4>
          <p>{{ e.error }}</p>
          <h4>How we fixed it</h4>
          <p>{{ e.how_fixed }}</p>
          <p v-if="e.engine_detail || e.commits?.length" class="small">
            <span v-if="e.engine_detail">{{ e.engine_detail }}</span>
            <span v-if="e.commits?.length"> · commits {{ e.commits.join(', ') }}</span>
          </p>
          <template v-if="e.result && Object.keys(e.result).length">
            <h4>Result</h4>
            <ul class="result">
              <li v-for="(r, m) in e.result" :key="m"><strong>{{ m }}:</strong> {{ r }}</li>
            </ul>
          </template>
          <template v-if="e.left">
            <h4>What's left</h4>
            <p>{{ e.left }}</p>
          </template>
          <p v-if="e.source" class="small">Numbers from: {{ e.source }}</p>
        </article>
      </section>

      <p v-if="!sections.length" class="muted">No error matches these filters.</p>

      <section v-if="doc.other_screenshots.length" class="section">
        <h2>Other screenshots you sent</h2>
        <div class="strip">
          <figure v-for="(o, n) in doc.other_screenshots" :key="n">
            <img v-if="o.image" :src="imageUrl(o.image)" :alt="o.words" loading="lazy" @click="openBox(otherImages, o.image)" />
            <figcaption><span class="date">{{ o.date }}</span> “{{ o.words }}”</figcaption>
          </figure>
        </div>
      </section>
    </template>

    <div v-if="box" class="lightbox" @click.self="box = null">
      <button class="lb-close" @click="box = null">Close ✕</button>
      <button v-if="box.list.length > 1" class="lb-prev" @click="step(-1)">‹</button>
      <img :src="imageUrl(box.list[box.at])" alt="" />
      <button v-if="box.list.length > 1" class="lb-next" @click="step(1)">›</button>
      <p class="lb-name">{{ box.list[box.at] }} ({{ box.at + 1 }} / {{ box.list.length }})</p>
    </div>
  </div>
</template>

<script setup lang="ts">
import { computed, onBeforeUnmount, onMounted, reactive, ref, watch } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import {
  filterChoices, filterErrors, filterFromQuery, filterToQuery, groupBySection, imageUrl, kindLabel,
  type DocFilter, type ErrorEntry, type ErrorsDoc,
} from '../utils/errorsDoc'

const STATUS_LABEL = { fixed: 'Fixed', partly: 'Partly fixed', open: 'Open' } as const
const NUMBER_LABEL: Record<string, string> = {
  triangles: 'Triangles', back_faces_px: 'Back faces seen from outside (px)', wall_strips: 'Wall strips added',
  wall_length_in: 'Wall length added (in)', bottoms_added: 'Bottoms added', pieces_replaced: 'Broken side pieces replaced',
  hidden_removed: 'Hidden faces removed', faces_flipped: 'Faces flipped',
}

const route = useRoute()
const router = useRouter()
const doc = ref<ErrorsDoc | null>(null)
const loadError = ref('')
const filter = reactive<DocFilter>({ model: null, kind: null, engine: null })
const copied = ref('')
const box = ref<{ list: string[]; at: number } | null>(null)

const choices = computed(() => (doc.value ? filterChoices(doc.value) : { models: [], kinds: [], engineFiles: [] }))
const shown = computed(() => (doc.value ? filterErrors(doc.value.errors, filter) : []))
const sections = computed(() => groupBySection(shown.value))
const otherImages = computed(() => (doc.value?.other_screenshots ?? []).flatMap(o => (o.image ? [o.image] : [])))

const fmt = (v: number) => v.toLocaleString()
const numberLabel = (key: string) => NUMBER_LABEL[key] ?? key

function entryImages(e: ErrorEntry): string[] {
  return [...e.you_saw.flatMap(s => (s.image ? [s.image] : [])), ...e.after.map(a => a.image)]
}

function openBox(list: string[], image: string) {
  box.value = { list, at: Math.max(0, list.indexOf(image)) }
}

function step(d: number) {
  if (!box.value) return
  const n = box.value.list.length
  box.value.at = (box.value.at + d + n) % n
}

function onKey(ev: KeyboardEvent) {
  if (!box.value) return
  if (ev.key === 'Escape') box.value = null
  else if (ev.key === 'ArrowLeft') step(-1)
  else if (ev.key === 'ArrowRight') step(1)
}

async function copy(text: string) {
  try {
    await navigator.clipboard.writeText(text)
    copied.value = text
  } catch {
    copied.value = ''
  }
}

function clear() {
  Object.assign(filter, { model: null, kind: null, engine: null })
}

watch(filter, () => {
  router.replace({ query: filterToQuery(filter) })
})

onMounted(async () => {
  window.addEventListener('keydown', onKey)
  try {
    const r = await fetch('/docs/errors.json', { cache: 'no-cache' })
    if (!r.ok) throw new Error(`HTTP ${r.status}`)
    doc.value = (await r.json()) as ErrorsDoc
    Object.assign(filter, filterFromQuery(route.query, doc.value))
  } catch (err) {
    loadError.value = err instanceof Error ? err.message : String(err)
  }
})

onBeforeUnmount(() => window.removeEventListener('keydown', onKey))
</script>

<style scoped>
.errors-page { max-width: 1200px; margin: 0 auto; padding: 24px 16px 64px; font-family: system-ui, -apple-system, 'Segoe UI', Roboto, sans-serif; color: #1c1d21; }
.page-header { border-bottom: 1px solid #dcdde2; padding-bottom: 16px; margin-bottom: 24px; }
.page-header h1 { margin: 6px 0 4px; font-size: 24px; }
.back { color: #1f5bff; text-decoration: none; font-size: 14px; }
.purpose { margin: 0; color: #4a4d57; }
.built { margin: 6px 0 0; font-size: 13px; color: #6b6f7b; }
.muted { color: #6b6f7b; }
.error-box { background: #fdecec; border: 1px solid #f5b5b5; padding: 10px 12px; border-radius: 6px; }
.cards { display: grid; grid-template-columns: repeat(auto-fit, minmax(320px, 1fr)); gap: 16px; }
.model-card { background: #fff; border: 1px solid #dcdde2; border-radius: 8px; padding: 14px 16px; }
.model-card h3 { margin: 0 0 8px; font-size: 15px; word-break: break-all; }
.model-card dl { display: grid; grid-template-columns: auto auto; gap: 4px 12px; margin: 0; font-size: 13px; }
.model-card dt { color: #4a4d57; }
.model-card dd { margin: 0; font-variant-numeric: tabular-nums; }
.skp { display: flex; gap: 8px; align-items: center; margin-top: 10px; font-size: 12px; }
.skp code { word-break: break-all; }
.source, .small { font-size: 12px; color: #6b6f7b; }
.filters { position: sticky; top: 0; z-index: 2; display: flex; flex-wrap: wrap; gap: 12px; align-items: center; background: #f6f7f9; border: 1px solid #dcdde2; border-radius: 8px; padding: 10px 12px; margin: 24px 0; font-size: 14px; }
.filters select { margin-left: 6px; }
.count { margin-left: auto; font-weight: 600; }
.section h2 { font-size: 18px; margin: 28px 0 12px; }
.entry { background: #fff; border: 1px solid #dcdde2; border-radius: 8px; padding: 14px 16px; margin-bottom: 16px; }
.entry-head { display: flex; flex-wrap: wrap; gap: 6px; align-items: center; margin-bottom: 10px; }
.entry-head h3 { margin: 0 8px 0 0; font-size: 16px; }
.status { font-size: 12px; font-weight: 700; padding: 2px 8px; border-radius: 4px; }
.status.fixed { background: #e6f6ec; color: #16723a; }
.status.partly { background: #fff4e0; color: #9a5b00; }
.status.open { background: #fdecec; color: #b42323; }
.tag { font-size: 12px; background: #eef0f4; color: #3b3f4a; padding: 2px 6px; border-radius: 4px; }
.mono { font-family: ui-monospace, Consolas, monospace; }
.pair { display: grid; grid-template-columns: 1fr 1fr; gap: 16px; margin: 8px 0 12px; }
.col h4, .entry h4 { margin: 10px 0 4px; font-size: 13px; text-transform: uppercase; letter-spacing: 0.04em; color: #4a4d57; }
figure { margin: 0 0 10px; }
figure img { width: 100%; max-height: 320px; object-fit: contain; background: #f0f1f4; border: 1px solid #dcdde2; border-radius: 6px; cursor: zoom-in; }
figcaption { font-size: 13px; color: #3b3f4a; margin-top: 4px; }
.date { font-weight: 600; margin-right: 6px; }
.result { margin: 0; padding-left: 18px; }
.strip { display: grid; grid-template-columns: repeat(auto-fill, minmax(220px, 1fr)); gap: 12px; }
.btn-small { padding: 3px 10px; font-size: 12px; }
.lightbox { position: fixed; inset: 0; z-index: 50; background: rgba(10, 12, 16, 0.88); display: flex; align-items: center; justify-content: center; }
.lightbox img { max-width: 88vw; max-height: 84vh; object-fit: contain; background: #fff; }
.lb-close { position: absolute; top: 16px; right: 20px; }
.lb-prev, .lb-next { position: absolute; top: 50%; font-size: 40px; background: none; border: none; color: #fff; cursor: pointer; padding: 0 16px; }
.lb-prev { left: 8px; }
.lb-next { right: 8px; }
.lb-name { position: absolute; bottom: 12px; color: #d8dae0; font-size: 13px; }
@media (max-width: 760px) { .pair { grid-template-columns: 1fr; } }
</style>
```

- [ ] **Step 4: Check types, tests and the build**

Run: `pnpm --dir web run type-check`, then `pnpm --dir web exec vitest run`, then `pnpm --dir web run build`
Expected:
- the type check exits 0;
- all web tests pass;
- the build succeeds, and `web/dist/docs/errors.json` exists.

- [ ] **Step 5: Commit**

```bash
git add web/src/views/ErrorsView.vue web/src/router.ts web/src/views/ModelsView.vue
git commit -m "feat(web): the Errors & fixes page at /errors, linked from the Models header" -m "Filters by model, kind and engine file combine and live in the URL; each card shows the owner's screenshot beside the AFTER render, the error and how it was fixed in plain words, and the measured result; images open in a lightbox." -m "Co-Authored-By: <your model> <noreply@anthropic.com>"
```

---

### Task 5 (SUPERSEDED by Task 11 — owner 11:55): the content

This task is judgement work: viewing the images, writing plain words and re-reading numbers. So the controller does it, not a subagent.

- [ ] **Step 1:** Run the extraction on the real log:
  `python -m tools.errors_doc.extract_owner_images "C:/Users/Future26/.claude/projects/D--PROJECTS-UC-MODEL-FIXER/5472478e-978d-426b-bab2-e7cf21699a70.jsonl" --out "D:/PROJECTS/UC MODEL FIXER/data/errors_doc"`.
  Record the count, and zip `data/errors_doc/img` into `data/backups/errors_doc-2026-09-26.zip`.
- [ ] **Step 2:** View every image, and assign each one to the entry it shows, or to `other_screenshots`.
- [ ] **Step 3:** Fill `web/public/docs/errors.json`:
  - **Models:** the numbers re-read from `data/output_verified/*/report.json`.
  - **Entries:** every entry the spec's "Initial entries" lists. Each has `error` and `how_fixed` in plain words, its result numbers with their source, and `left` for the open entries.
- [ ] **Step 4:** Run the content test (`vitest run src/utils/errorsDoc.test.ts`) and `python -m tools.errors_doc.check`. Missing AFTER renders are allowed until Task 6; unused owner screenshots are not.
- [ ] **Step 5:** Commit `web/public/docs/errors.json`.

### Task 6 (DEFERRED — the page is a plan; renders per kind can come later): AFTER renders

**Files:**
- Create: `tools/errors_doc/render_after.py`, `tools/errors_doc/cameras.json`

The script extends `docs/superpowers/records/scripts/render_skp.py`, which draws a `.skp` with only SketchUp's edges from fixed views, with a free camera. It also copies the close-up approach of `render_skp_closeup.py` from branch `feat/coincident-pairs`, where it lives now.
- For each camera in `cameras.json` (`{"after-<id>.png": {"skp": "A"|"B", "eye": [x,y,z], "target": [x,y,z], "up": [0,0,1], "fov": 40}}`, model inches), it reads the owner `.skp` with `engine/io/skp_writer.py::read_skp`.
- It draws double-sided with back faces purple, and only the edges SketchUp draws.
- It writes a 1200 x 800 PNG to `data/errors_doc/img/`.

The controller writes this task's brief once Task 5 has shown which spots need renders, with the exact camera list and the existing renderer's code read first.

### Task 7 (controller): deploy and check

- [ ] Merge `feat/errors-page` into `feat-dashboard`.
- [ ] Rebuild the web and API images by HANDOFF section 8, from that commit. Back up first and tag the old images.
- [ ] **Check in the browser:**
  - `http://localhost:5190/errors` loads, including on reload;
  - each filter changes the counts;
  - every image request is 200;
  - the lightbox opens and steps;
  - `check.py` passes.
- [ ] Send the owner screenshots of the page. Update the records (HANDOFF sections 2 and 3, the session record, the ledger) and commit them.

---

## Tasks 8-11: the planning catalogue (owner, 2026-09-26 11:55-12:15; spec "Amendment" sections)

The page lays out every **kind** of error for the owner to validate before any fix phase. Each kind
opens a floating window with eight parts:
1. What it is.
2. How we find it: the exact, measurable test.
3. Why the model has it: Minecraft → Little Tiles → SketchUp → OBJ.
4. How much of each model it is.
5. Why you don't want it in Unity.
6. The solution, plus what is never done.
7. Done so far.
8. Why some can remain.

The owner gives a verdict per kind and model. Nothing in any model is changed.

### Task 8: the catalogue's logic, and the content test

**Files:**
- Create: `web/src/utils/errorsDoc.ts`, `web/src/utils/errorsDoc.test.ts`, `web/public/docs/errors.json` (seed)

**Interfaces:**
- Produces (exported from `web/src/utils/errorsDoc.ts`):

```ts
export type Status = 'fixed' | 'partly' | 'open' | 'planned'
export type Verdict = 'error' | 'ok' | 'unsure'
export interface Example { image?: string; date?: string; words?: string; caption?: string; model?: string }
export interface Kind {
  id: string; title: string; summary: string; color: string            // color: '#rrggbb'
  models: Record<string, { status: Status; count: string }>             // keyed by model id
  what: string; find: string[]; why: string; why_note?: string
  unity: string[]; solution: string[]; never?: string[]; done: string[]; remain: string
  engine_files: string[]; examples: Example[]; sources: string[]
}
export interface EngineMistake {
  id: string; title: string; what_happened: string; how_caught: string; fix: string
  models: string[]; engine_files: string[]; commits?: string[]; examples: Example[]
}
export interface ModelCard { id: string; name: string; role: string; skp?: string; numbers: Record<string, number | number[]>; source: string }
export interface Catalogue {
  built_from: { commit: string; date: string }
  origin: string[]                       // intro paragraphs
  models: ModelCard[]; kinds: Kind[]; engine_mistakes: EngineMistake[]; other_screenshots: Example[]
}
export interface DocFilter { model: string | null; engine: string | null }
export interface VerdictEntry { verdict: Verdict; note: string; at: string }
export interface Validation { version: 1; verdicts: Record<string, Record<string, VerdictEntry>> }   // kind id -> model id -> entry

export const ENGINE_FILES: string[]      // the 13 files of the Global Constraints, in that order
export const STATUS_LABEL: Record<Status, string>   // Fixed / Partly fixed / Open / Planned, not fixed yet
export const VERDICTS: { id: Verdict; label: string }[]   // error 'Error, must fix'; ok 'OK for this model'; unsure 'Not sure'
export const IMAGE_NAME: RegExp          // /^[A-Za-z0-9_.-]+\.(png|webp|jpg)$/
export const WINDOW_HEADER = 48          // px of the floating window's title bar that must stay on screen
export function engineStem(file: string): string
export function statusLabel(s: Status): string
export function imageUrl(name: string): string      // '/api/docs/images/' + encodeURIComponent(name)
export function filterKinds(kinds: Kind[], f: DocFilter): Kind[]          // model: kind.models has the key; engine: in engine_files
export function filterMistakes(ms: EngineMistake[], f: DocFilter): EngineMistake[]   // model: in m.models; engine: in engine_files
export function filterChoices(cat: Catalogue): { models: { id: string; label: string }[]; engineFiles: string[] }
export function filterFromQuery(q: Record<string, unknown>, cat: Catalogue): DocFilter
export function openFromQuery(q: Record<string, unknown>, cat: Catalogue): string | null   // a kind or mistake id, else null
export function filterToQuery(f: DocFilter, open: string | null): Record<string, string>   // model, engine (stem), open
export function clampWindow(x: number, y: number, w: number, vw: number, vh: number): { x: number; y: number }
export function verdictOf(v: Validation | null, kindId: string, modelId: string): VerdictEntry | null
export function validationSummary(cat: Catalogue, v: Validation | null): { pairs: number; validated: number; error: number; ok: number; unsure: number }
export function validateCatalogue(cat: Catalogue): string[]
```

- [ ] **Step 1: Write the failing tests** (`web/src/utils/errorsDoc.test.ts`)

```ts
import { describe, it, expect } from 'vitest'
import {
  filterKinds, filterMistakes, filterChoices, filterFromQuery, openFromQuery, filterToQuery, clampWindow,
  statusLabel, imageUrl, engineStem, verdictOf, validationSummary, validateCatalogue,
  type Catalogue, type Kind, type EngineMistake, type Validation,
} from './errorsDoc'
import content from '../../public/docs/errors.json'

function kind(over: Partial<Kind>): Kind {
  return {
    id: 'k', title: 'T', summary: 'S', color: '#1f5bff', models: { A: { status: 'fixed', count: '1' } },
    what: 'W', find: ['F'], why: 'Y', unity: ['U'], solution: ['S1'], done: ['D'], remain: 'R',
    engine_files: ['vis/exposure.py'], examples: [], sources: ['report.json'], ...over,
  }
}

function mistake(over: Partial<EngineMistake>): EngineMistake {
  return {
    id: 'm', title: 'M', what_happened: 'H', how_caught: 'C', fix: 'F', models: ['A'],
    engine_files: ['guard/compare.py'], examples: [], ...over,
  }
}

const cat: Catalogue = {
  built_from: { commit: 'abc1234', date: '2026-09-26 12:00' },
  origin: ['Minecraft, Little Tiles, SketchUp, OBJ.'],
  models: [
    { id: 'CHTM5', name: 'chtm_5ft_floor', role: 'example, not fixed', numbers: {}, source: 's' },
    { id: 'A', name: 'CHTM_SIDE_WALK_2nd_floor', role: 'fixed file', numbers: {}, source: 's' },
    { id: 'B', name: 'CHTM_2nd_to_3rd_building_sidewalk_outside', role: 'fixed file', numbers: {}, source: 's' },
  ],
  kinds: [
    kind({ id: 'hidden-faces', engine_files: ['vis/exposure.py', 'fixes/remove.py'], models: {
      CHTM5: { status: 'planned', count: '12,870' }, A: { status: 'fixed', count: '2,065' }, B: { status: 'fixed', count: '2,771' } } }),
    kind({ id: 'gridlines', models: { A: { status: 'fixed', count: 'x' } }, engine_files: ['fixes/merge.py', 'topo/planes.py'] }),
    kind({ id: 'sawtooth', models: { B: { status: 'partly', count: 'y' } }, engine_files: ['fixes/solidify.py'] }),
  ],
  engine_mistakes: [
    mistake({ id: 'guard-blind', models: ['B'], engine_files: ['guard/compare.py'] }),
    mistake({ id: 'underside-top', models: ['A'], engine_files: ['fixes/solidify.py'] }),
  ],
  other_screenshots: [],
}

describe('errorsDoc', () => {
  it('filters kinds by the model they occur in and by engine file, combined', () => {
    const none = { model: null, engine: null }
    expect(filterKinds(cat.kinds, none).map(k => k.id)).toEqual(['hidden-faces', 'gridlines', 'sawtooth'])
    expect(filterKinds(cat.kinds, { ...none, model: 'CHTM5' }).map(k => k.id)).toEqual(['hidden-faces'])
    expect(filterKinds(cat.kinds, { ...none, model: 'A' }).map(k => k.id)).toEqual(['hidden-faces', 'gridlines'])
    expect(filterKinds(cat.kinds, { ...none, engine: 'fixes/solidify.py' }).map(k => k.id)).toEqual(['sawtooth'])
    expect(filterKinds(cat.kinds, { model: 'A', engine: 'fixes/solidify.py' })).toEqual([])
  })

  it('filters engine mistakes the same way', () => {
    expect(filterMistakes(cat.engine_mistakes, { model: 'A', engine: null }).map(m => m.id)).toEqual(['underside-top'])
    expect(filterMistakes(cat.engine_mistakes, { model: null, engine: 'guard/compare.py' }).map(m => m.id)).toEqual(['guard-blind'])
  })

  it('offers the models, and only the engine files something uses, in the fixed order', () => {
    const c = filterChoices(cat)
    expect(c.models).toEqual([
      { id: 'CHTM5', label: 'CHTM5 · chtm_5ft_floor' },
      { id: 'A', label: 'A · CHTM_SIDE_WALK_2nd_floor' },
      { id: 'B', label: 'B · CHTM_2nd_to_3rd_building_sidewalk_outside' },
    ])
    expect(c.engineFiles).toEqual(['vis/exposure.py', 'fixes/remove.py', 'fixes/solidify.py', 'fixes/merge.py',
      'guard/compare.py', 'topo/planes.py'])
  })

  it('reads the filter and the open window from the URL, ignoring unknown values', () => {
    expect(filterFromQuery({ model: 'B', engine: 'solidify' }, cat)).toEqual({ model: 'B', engine: 'fixes/solidify.py' })
    expect(filterFromQuery({ model: 'Z', engine: 'nope' }, cat)).toEqual({ model: null, engine: null })
    expect(filterFromQuery({ model: ['A', 'B'] }, cat).model).toBe('A')
    expect(openFromQuery({ open: 'gridlines' }, cat)).toBe('gridlines')
    expect(openFromQuery({ open: 'guard-blind' }, cat)).toBe('guard-blind')
    expect(openFromQuery({ open: 'nothing' }, cat)).toBeNull()
  })

  it('writes the filter and the open window back as a short query', () => {
    expect(filterToQuery({ model: 'A', engine: 'fixes/solidify.py' }, 'hidden-faces'))
      .toEqual({ model: 'A', engine: 'solidify', open: 'hidden-faces' })
    expect(filterToQuery({ model: null, engine: null }, null)).toEqual({})
    expect(engineStem('guard/piece_rays.py')).toBe('piece_rays')
  })

  it('keeps a dragged window s title bar on screen', () => {
    expect(clampWindow(100, 50, 560, 1600, 900)).toEqual({ x: 100, y: 50 })
    expect(clampWindow(-40, -10, 560, 1600, 900)).toEqual({ x: 0, y: 0 })
    expect(clampWindow(1500, 880, 560, 1600, 900)).toEqual({ x: 1040, y: 852 })
    expect(clampWindow(50, 50, 900, 700, 500)).toEqual({ x: 0, y: 50 })
  })

  it('labels statuses in plain words and builds image URLs through the API', () => {
    expect(statusLabel('planned')).toBe('Planned, not fixed yet')
    expect(statusLabel('partly')).toBe('Partly fixed')
    expect(imageUrl('you-0921-0346-1.png')).toBe('/api/docs/images/you-0921-0346-1.png')
  })

  it('reads the owner s verdicts and counts the validated kind-and-model pairs', () => {
    const v: Validation = { version: 1, verdicts: {
      'hidden-faces': { CHTM5: { verdict: 'error', note: '', at: 't' }, A: { verdict: 'ok', note: 'fine here', at: 't' } },
      gridlines: { B: { verdict: 'error', note: '', at: 't' } },     // B is not one of gridlines' models: not counted
      unknown: { A: { verdict: 'unsure', note: '', at: 't' } },
    } }
    expect(validationSummary(cat, v)).toEqual({ pairs: 5, validated: 2, error: 1, ok: 1, unsure: 0 })
    expect(validationSummary(cat, null)).toEqual({ pairs: 5, validated: 0, error: 0, ok: 0, unsure: 0 })
    expect(verdictOf(v, 'hidden-faces', 'A')?.note).toBe('fine here')
    expect(verdictOf(v, 'hidden-faces', 'B')).toBeNull()
    expect(verdictOf(null, 'hidden-faces', 'A')).toBeNull()
  })

  it('names every problem in a bad catalogue, in a fixed order', () => {
    const bad: Catalogue = {
      ...cat,
      kinds: [
        kind({ id: 'a', what: ' ', color: 'blue', models: { Z: { status: 'fixed', count: '1' } },
               engine_files: ['fixes/nope.py'], examples: [{ image: '../x.png' }] }),
        kind({ id: 'a', solution: [], models: { A: { status: 'maybe' as never, count: '1' } } }),
      ],
      engine_mistakes: [mistake({ id: 'm', fix: '', models: ['Q'] })],
    }
    expect(validateCatalogue(bad)).toEqual([
      'a: "what" is empty',
      'a: bad colour "blue"',
      'a: unknown model "Z"',
      'a: unknown engine file "fixes/nope.py"',
      'a: bad image name "../x.png"',
      'a: duplicate id',
      'a: "solution" has no steps',
      'a: unknown status "maybe"',
      'm: "fix" is empty',
      'm: unknown model "Q"',
    ])
    expect(validateCatalogue(cat)).toEqual([])
  })

  it('the committed errors.json is valid', () => {
    expect(validateCatalogue(content as unknown as Catalogue)).toEqual([])
  })
})
```

- [ ] **Step 2: Run and see them fail**

Run: `pnpm --dir web exec vitest run src/utils/errorsDoc.test.ts`
Expected: FAIL. `./errorsDoc` and `../../public/docs/errors.json` do not resolve.

- [ ] **Step 3: Implement** `web/src/utils/errorsDoc.ts` to the interface above. These rules are exact:
  - `ENGINE_FILES`, in this order: `vis/exposure.py`, `fixes/remove.py`, `fixes/solidify.py`, `fixes/merge.py`, `fixes/orient.py`, `fixes/overlap.py`, `detectors/fragments.py`, `detectors/folds.py`, `guard/compare.py`, `guard/piece_rays.py`, `io/skp_writer.py`, `topo/adjacency.py`, `topo/planes.py`.
  - `filterChoices`:
    - `models` are all of `cat.models` in order, labelled `` `${id} · ${name}` ``;
    - `engineFiles` are the `ENGINE_FILES` that any kind or engine mistake names, kept in `ENGINE_FILES` order.
  - `filterFromQuery`:
    - takes the first element of an array value;
    - `model` must be a model id and `engine` must be the stem of one of `filterChoices(cat).engineFiles`, which returns the full path;
    - anything else becomes `null`.
  - `openFromQuery` returns `q.open` when it equals a kind id or an engine-mistake id; otherwise `null`.
  - `filterToQuery` includes only the keys that are set, with `engine` as its stem.
  - `clampWindow`: `x = min(max(x, 0), max(0, vw - w))` and `y = min(max(y, 0), max(0, vh - WINDOW_HEADER))`.
  - `validationSummary`:
    - `pairs` counts every `(kind, model id)` in `kind.models`;
    - `validated`, `error`, `ok` and `unsure` count only those pairs that have a verdict;
    - verdicts for other ids are ignored.
  - `validateCatalogue`: one shared set of ids across kinds and engine mistakes.
    - **For each kind**, in array order, check in this order:
      1. duplicate id → `id: duplicate id`;
      2. each of `summary`, `what`, `why`, `remain` that is empty after trim → `id: "<field>" is empty`;
      3. each of `find`, `unity`, `solution`, `done` that has no non-empty item → `id: "<field>" has no steps`;
      4. `color` not matching `/^#[0-9a-fA-F]{6}$/` → `id: bad colour "<color>"`;
      5. for each `models` key in order: not a model id → `id: unknown model "<key>"`, then a status not in `STATUS_LABEL` → `id: unknown status "<status>"`;
      6. each engine file not in `ENGINE_FILES` → `id: unknown engine file "<file>"`;
      7. each example image not matching `IMAGE_NAME` → `id: bad image name "<name>"`.
    - **For each engine mistake**, check in this order:
      1. duplicate id;
      2. each of `what_happened`, `how_caught`, `fix` that is empty → `id: "<field>" is empty`;
      3. each model not a model id → `id: unknown model "<m>"`;
      4. engine files;
      5. example images.
    - **Last**, check each `other_screenshots` image, as `other_screenshots: bad image name "<name>"`.

  Then create the seed `web/public/docs/errors.json`. It must validate. Its content is the owner-approved "Hidden inside faces" kind (12:05), with the "How we find it" part the owner asked for at 12:15:

```json
{
  "built_from": { "commit": "ab22ff3", "date": "2026-09-25 23:53" },
  "origin": [
    "These models were built in Minecraft with the Little Tiles mod, exported, brought into SketchUp, and exported again as one OBJ per SketchUp group. Every step keeps all the geometry the step before made, so the OBJ carries what Little Tiles builds with: many small closed boxes on the block grid.",
    "This page lays out every kind of error found so far: what it is, how it is found, why the model has it, how much of each model it is, why it is unwanted in Unity, the solution, what was done, and why some can remain. It is a plan: nothing in any model is changed by it. Give your verdict per model in each error's window."
  ],
  "models": [
    { "id": "CHTM5", "name": "chtm_5ft_floor", "role": "Example building, not fixed: errors measured only", "numbers": { "triangles": 20599 },
      "source": "snapshot c0c877002500 (dashboard model 2, version 6)" },
    { "id": "A", "name": "CHTM_SIDE_WALK_2nd_floor", "role": "Sidewalk, fixed by the engine",
      "skp": "D:/PROJECTS/UC MODEL FIXER/OBJ FIXED RESULT/CHTM_SIDE_WALK_2nd_floor.fixed.skp",
      "numbers": { "triangles": [4692, 881], "back_faces_px": [569108, 18348] },
      "source": "data/output_verified/CHTM_SIDE_WALK_2nd_floor/report.json at ab22ff3" },
    { "id": "B", "name": "CHTM_2nd_to_3rd_building_sidewalk_outside", "role": "Sidewalk, fixed by the engine",
      "skp": "D:/PROJECTS/UC MODEL FIXER/OBJ FIXED RESULT/CHTM_2nd_to_3rd_building_sidewalk_outside.fixed.skp",
      "numbers": { "triangles": [7227, 513], "back_faces_px": [464939, 2869] },
      "source": "data/output_verified/CHTM_2nd_to_3rd_building_sidewalk_outside/report.json at ab22ff3" }
  ],
  "kinds": [
    {
      "id": "hidden-faces",
      "title": "Hidden inside faces",
      "summary": "Faces inside the solid parts of the model that no camera outside can ever see.",
      "color": "#1f5bff",
      "models": {
        "CHTM5": { "status": "planned", "count": "12,870 of 20,599 triangles (62 %)" },
        "A": { "status": "fixed", "count": "2,108 of 4,692 triangles; 2,065 removed, 43 kept by the guard" },
        "B": { "status": "fixed", "count": "2,787 of 7,227 triangles; 2,771 removed, 16 kept by the guard" }
      },
      "what": "Faces inside the solid parts of the model: between two slabs, inside a wall, under a floor. They are real triangles in the OBJ, but no camera standing anywhere outside can ever see them.",
      "find": [
        "Take 4 points on each face: its centre, and three points near its corners (0.6 / 0.2 / 0.2 of the way to each corner).",
        "From every point, cast 128 rays spread evenly over all directions, on both sides of the face. The rays hit every other face of the object from either side, the way Unity and SketchUp draw them.",
        "A ray escapes when it leaves the object without hitting a face. A face is hidden when none of its rays escapes.",
        "When some rays escape but fewer than 5 % (the slit threshold, 0.05), the face is seen only through a thin gap: a 'slit' face. It is kept unless 'Accept slit faces' is on.",
        "The test sees this object alone. A face hidden only by a neighbouring building still counts as visible, because Unity may stream that neighbour out.",
        "Zero-area triangles are left out: they are their own kind of error."
      ],
      "why": "Little Tiles builds everything from small boxes (tiles) on Minecraft's block grid. Each tile is exported as a closed box with all six sides, including the sides pressed against a neighbouring tile, so a wall built from 16 small tiles carries every wall between every pair of tiles. SketchUp keeps every face it imports, and the OBJ export per group keeps them again. That is also why they come in pairs: two touching tiles give two faces on one plane, facing opposite ways. CHTM 5th floor has 13,947 such pairs.",
      "why_note": "Our reading of the measurements; we have not seen the exporter's code.",
      "unity": [
        "Unity still sends every one of those triangles to the GPU: 62 % of CHTM 5th floor is never seen.",
        "They take lightmap space and collider cost for nothing.",
        "Where a hidden face lies exactly on an outer surface, Unity cannot decide which one is in front, so it flickers.",
        "In X-ray and in SketchUp they fill the slabs with lines (the 09-21 screenshots)."
      ],
      "solution": [
        "Find them with the ray test above, never by guessing.",
        "Remove only those faces, never the sides of a slab or wall (owner's rule: only the inside).",
        "Guard every removal: render the object from 26 directions with and without the removed faces; if even one pixel of the outside changes, that face is put back.",
        "Check what is left in the dashboard: X-ray, and the blue 'Hidden inside faces' filter of the 3D viewer."
      ],
      "never": [
        "Blender's 'select interior faces' and delete: it deleted 88 % of this model once.",
        "Welding vertices farther apart than 0.1 mm.",
        "'Make Manifold' or 'Fill Holes': both closed real openings in this model before."
      ],
      "done": [
        "Sidewalk A: 2,065 removed, 43 put back by the guard.",
        "Sidewalk B: 2,771 removed, 16 put back by the guard.",
        "Both files pass every check.",
        "CHTM 5th floor: not touched. Planning only."
      ],
      "remain": "Faces seen through a real small gap are kept on purpose, so no hole opens. Faces the guard put back stay: removing them changed the picture, so they were visible after all.",
      "engine_files": ["vis/exposure.py", "fixes/remove.py", "guard/compare.py"],
      "examples": [],
      "sources": [
        "CHTM 5th floor: engine.cli errors on snapshot c0c877002500, 2026-09-26 (hidden 12,870)",
        "A and B: report.json at ab22ff3 (n_hidden_candidates, n_removed_hidden, n_restored_by_guard)",
        "Method: engine/vis/exposure.py (4 sample points, 128 directions, slit threshold 0.05); guard: engine/guard/compare.py (26 views)"
      ]
    }
  ],
  "engine_mistakes": [],
  "other_screenshots": []
}
```

- [ ] **Step 4: Run and see them pass**, then the type check

Run: `pnpm --dir web exec vitest run src/utils/errorsDoc.test.ts`, then `pnpm --dir web run type-check`.
Expected: 10 tests pass, and the type check exits 0. If `vue-tsc` rejects the JSON import, add `"resolveJsonModule": true` to `compilerOptions` in the tsconfig that includes `src` (check `web/tsconfig.app.json` or `web/tsconfig.json`), and list that file in the commit.

- [ ] **Step 5: Commit**

```bash
git add web/src/utils/errorsDoc.ts web/src/utils/errorsDoc.test.ts web/public/docs/errors.json
git commit -m "feat(web): the error catalogue's model, filters, verdict counts and content test" -m "The Errors page lays out every kind of error for the owner to validate before any fix phase; validateCatalogue enforces the spec's rules on the committed errors.json, which starts with the owner-approved 'Hidden inside faces' kind." -m "Co-Authored-By: <your model> <noreply@anthropic.com>"
```

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

### Task 10: the page and its floating window

**Files:**
- Create: `web/src/views/ErrorsView.vue`, `web/src/components/ErrorWindow.vue`
- Modify: `web/src/router.ts` (route `/errors`), `web/src/views/ModelsView.vue` (header button)

**Interfaces:**
- Consumes: Task 8's exports; `GET /docs/errors.json`; `GET /api/docs/images/{name}` (Task 1); `GET /api/docs/validation` and `PUT /api/docs/validation/{kind}/{model}` (Task 9).

- [ ] **Step 1: Route and button.**
  - `web/src/router.ts`: import `ErrorsView from './views/ErrorsView.vue'`, and add `{ path: '/errors', name: 'errors', component: ErrorsView }` after the workspace route.
  - `web/src/views/ModelsView.vue`: inside `<div class="header-actions">`, before Refresh, add `<router-link to="/errors" class="btn btn-secondary">Errors &amp; fixes</router-link>`.

- [ ] **Step 2: `ErrorsView.vue`** (script setup, TypeScript, scoped styles in the light style of `ModelsView.vue`: max-width 1200px, `#1c1d21` text, `#dcdde2` borders, white cards, 8px radius). Top to bottom:
  1. **Header.** A "← Models" link to `/`, the title **"Errors: what they are, and the plan"**, and the line "Built from commit `<built_from.commit>`, <built_from.date>".
     - Beside the title, the validation summary from `validationSummary(cat, validation)`: "Validated 2 of 5 · 1 must fix · 1 OK · 0 not sure".
  2. **Origin:** each paragraph of `cat.origin`.
  3. **The models:** one card per `cat.models`, holding its name, `role`, its `numbers` (a `[a, b]` pair shown as `a → b`, with thousands separators) and `source`.
     - When `skp` is set, show the path with a Copy button that uses `navigator.clipboard.writeText` in try/catch.
     - Number labels: triangles "Triangles"; back_faces_px "Back faces seen from outside (px)". Any other key is shown as-is.
  4. **Filter bar** (sticky at the top): Model select (All + `filterChoices().models`), Engine file select (All + `engineFiles`), "N of M kinds" and a Clear button.
  5. **Catalogue grid** of `filterKinds(cat.kinds, filter)` (CSS grid, `minmax(300px, 1fr)`). Each card is a button-like `article` (`role="button"`, `tabindex="0"`, Enter opens it) and shows:
     - a 6px left border in `kind.color`, the title, and the summary;
     - one row per model in `kind.models`: the model id, a status badge (`statusLabel`), the count, and the owner's verdict when there is one (`verdictOf`), as a small badge;
     - clicking the card opens the window.
  6. **"Engine mistakes caught by reviews":** cards of `filterMistakes(...)` (title and models). Clicking opens the window.
  7. **"Other screenshots you sent":** a strip of `other_screenshots`. Clicking opens the lightbox.
  8. **Loading and errors.** Fetch `/docs/errors.json` with `{ cache: 'no-cache' }` and `/api/docs/validation` on mount.
     - A failed catalogue fetch shows "Could not load the documentation: <message>".
     - A failed validation fetch only shows a small note, "Verdicts could not be loaded", and the page still works.
  9. **URL.** On load, set the filter from `filterFromQuery(route.query, cat)` and the open window from `openFromQuery`. Then `watch` the filter and the open id, and call `router.replace({ query: filterToQuery(filter, openId) })`.
  10. **Lightbox** (full-screen dark overlay). The image comes from `imageUrl(name)`. It has a Close button, ‹ › buttons when there is more than one image, Esc to close and ArrowLeft/ArrowRight to step. The keydown listener is added on mount and removed on unmount.

- [ ] **Step 3: `ErrorWindow.vue`,** the floating window.
  - **Props:** `kind: Kind | null`, `mistake: EngineMistake | null`, `models: ModelCard[]`, `validation: Validation | null`.
  - **Emits:** `close`, `image` (payload `{ list: string[]; name: string }`) and `verdict` (payload `{ kindId: string; modelId: string; verdict: Verdict | null; note: string }`).
  - **Frame:** `position: fixed`, z-index 40, width 560px, height 72vh. `resize: both; overflow: hidden`. Min 360 × 240. White, with a shadow.
  - **Title bar:** 48px, drag handle, cursor move. It shows the colour swatch, the title, and a ✕ button.
  - **Body:** scrolls (`overflow: auto`).
  - **Starting position:** `clampWindow(window.innerWidth - 560 - 24, 72, 560, innerWidth, innerHeight)`.
  - **Dragging:**
    - `pointerdown` on the title bar calls `setPointerCapture` and records the offset.
    - `pointermove` moves the window to `clampWindow(ev.clientX - offX, ev.clientY - offY, el.offsetWidth, innerWidth, innerHeight)`.
    - `pointerup` releases.
  - **Esc** emits `close` (keydown listener on `window`, removed on unmount).
  - **Body for a kind:** headings in this order, each followed by its content.
    1. **What it is:** `what`.
    2. **How we find it:** `find`, as an ordered list.
    3. **Why the model has it:** `why`, then `why_note` in small italic.
    4. **How much of each model it is:** a table with rows model name, status badge, count.
    5. **Why you don't want it in Unity:** `unity`, as a list.
    6. **The solution:** `solution`, as an ordered list. Then **Never do this**, `never` as a list, when present.
    7. **Done so far:** `done`, as a list.
    8. **Why some can remain:** `remain`.
    9. **Your screenshots:** a grid of `examples`, each with its image (click emits `image`), date, words and caption.
    10. **Your verdict:** one row per model in `kind.models`.
        - The row holds three toggle buttons from `VERDICTS`. The active one is highlighted, and clicking it again emits `null`.
        - It also holds a note `textarea`, prefilled from `verdictOf`. It emits on blur when changed, keeping the current verdict; with no verdict yet, it emits `'unsure'`.
        - A small "saved <at>" follows.
    11. **Engine files:** monospace tags. Then **Numbers from:** `sources`, in small print.
  - **Body for a mistake:** What happened, How it was caught, The fix, Engine files, Commits, then the examples.

- [ ] **Step 4: Saving a verdict** (in `ErrorsView.vue`).
  - On `verdict`, `PUT /api/docs/validation/<kind>/<model>` with JSON `{ verdict, note }`.
  - On success, update the local `validation` object: set or delete the entry from the response.
  - On failure, show a short red note in the window's verdict row ("Not saved: <message>") and keep the previous state.

- [ ] **Step 5: Check types, tests and the build**

Run: `pnpm --dir web run type-check`, then `pnpm --dir web exec vitest run`, then `pnpm --dir web run build`.
Expected:
- the type check exits 0;
- all web tests pass;
- the build succeeds, and `web/dist/docs/errors.json` exists.

  Note for the template: TypeScript does not narrow `x.image` inside an `@click` closure, so pass `image: string | undefined` and handle `undefined`.

- [ ] **Step 6: Commit**

```bash
git add web/src/views/ErrorsView.vue web/src/components/ErrorWindow.vue web/src/router.ts web/src/views/ModelsView.vue
git commit -m "feat(web): the Errors page at /errors -- a catalogue of error kinds, each opening a floating window with its plan and the owner's verdict" -m "Every kind shows what it is, how it is found, why the model has it (Minecraft Little Tiles export), how much of each model it is, why it is unwanted in Unity, the solution, what was done and why some remain; the owner marks each kind per model as an error to fix, OK for that model, or not sure." -m "Co-Authored-By: <your model> <noreply@anthropic.com>"
```

### Task 11 (controller): the content

- [ ] Run the extraction on the session log (Task 2's CLI), and zip `data/errors_doc/img` into `data/backups/errors_doc-2026-09-26.zip`.
- [ ] View every screenshot, and assign each one as an example of the kind or engine mistake it shows, or to `other_screenshots`.
- [ ] Write the other nine kinds at the approved depth, including "How we find it", and the engine mistakes. Re-read every number from its report, and give each one its source.
- [ ] Run `vitest run src/utils/errorsDoc.test.ts` and `python -m tools.errors_doc.check` (no missing images, no unused owner screenshots). Commit `web/public/docs/errors.json`.

## Order

Tasks run in this order: **1 and 2 (done), 8, 9, 10, then 7 (deploy)**.
- Task 11's content work runs while Tasks 8-10 are built.
- Tasks 3, 4 and 5 are superseded; Task 6 is deferred.
