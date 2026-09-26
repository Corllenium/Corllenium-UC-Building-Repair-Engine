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
