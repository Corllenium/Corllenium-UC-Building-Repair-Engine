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

