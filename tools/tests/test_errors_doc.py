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


def _doc(tmp_path, kinds=(), engine_mistakes=(), other=()):
    p = tmp_path / "errors.json"
    p.write_text(json.dumps({"built_from": {"commit": "x", "date": "d"}, "origin": [], "models": [],
                             "kinds": list(kinds), "engine_mistakes": list(engine_mistakes),
                             "other_screenshots": list(other)}), encoding="utf-8")
    return p


def test_check_names_images_that_are_missing(tmp_path):
    img = tmp_path / "img"
    img.mkdir()
    (img / "you-0921-0346-1.png").write_bytes(PNG)
    doc = _doc(tmp_path,
               kinds=[{"id": "k", "examples": [{"image": "you-0921-0346-1.png"}, {"image": "after-a.png"}]}],
               engine_mistakes=[{"id": "m", "examples": [{"image": "you-0922-1005-1.webp"}]}])
    assert missing_images(doc, img) == ["after-a.png", "you-0922-1005-1.webp"]


def test_check_names_owner_images_used_nowhere(tmp_path):
    owner = tmp_path / "owner_images.json"
    owner.write_text(json.dumps([{"file": "you-0921-0346-1.png"}, {"file": "you-0923-0800-1.png"}]), encoding="utf-8")
    doc = _doc(tmp_path, kinds=[{"id": "k", "examples": [{"image": "you-0921-0346-1.png"}]}])
    assert unused_owner_images(doc, owner) == ["you-0923-0800-1.png"]


def test_tool_result_images_are_skipped(tmp_path):
    """A human-origin message containing a tool_result block is not extracted, even if there are other images."""
    human = {"kind": "human"}
    lines = [
        {"type": "user", "timestamp": "2026-09-25T10:00:00.000Z", "origin": human,
         "message": {"role": "user", "content": [_img(PNG, "image/png"),
                                                 {"type": "tool_result", "tool_use_id": "t9",
                                                  "content": [_img(SHOT, "image/png")]}]}}
    ]
    log = tmp_path / "test.jsonl"
    log.write_text("\n".join(json.dumps(x) for x in lines), encoding="utf-8")
    records = extract(log, tmp_path / "out")
    assert len(records) == 0
    files = list((tmp_path / "out" / "img").glob("*"))
    assert len(files) == 0
