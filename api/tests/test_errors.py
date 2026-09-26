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
