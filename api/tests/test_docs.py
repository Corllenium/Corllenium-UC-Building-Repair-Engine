"""The Errors & fixes page's image and verdict routes (spec 2026-09-26-errors-and-fixes-page-design.md)."""
import json

from api.routers.docs import validation_file
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


def test_a_verdict_sent_without_a_note_keeps_the_saved_note(client):
    _fresh()
    client.put("/api/docs/validation/hidden-faces/A", json={"verdict": "ok", "note": "keep"})
    r = client.put("/api/docs/validation/hidden-faces/A", json={"verdict": "error"})
    assert r.status_code == 200
    assert r.json()["entry"]["verdict"] == "error"
    assert r.json()["entry"]["note"] == "keep"
    got = client.get("/api/docs/validation").json()["verdicts"]["hidden-faces"]["A"]
    assert got["verdict"] == "error" and got["note"] == "keep"


def test_bad_verdicts_and_ids_are_refused(client):
    assert client.put("/api/docs/validation/hidden-faces/A", json={"verdict": "maybe"}).status_code == 422
    assert client.put("/api/docs/validation/hidden-faces/A", json={"verdict": "ok", "note": "x" * 2001}).status_code == 422
    assert client.put("/api/docs/validation/Hidden..Faces/A", json={"verdict": "ok"}).status_code == 404
    assert client.put("/api/docs/validation/hidden-faces/A%20B", json={"verdict": "ok"}).status_code == 404
