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
