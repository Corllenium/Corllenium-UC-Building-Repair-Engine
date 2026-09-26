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


def test_a_stale_or_unversioned_errors_file_reads_as_not_computed_yet(client, imported_cube):
    """Review M2: a file written before `find_errors` last changed what it means (version 1, or
    no version at all) is not served; the panel then offers Find errors again. A current one is."""
    import json
    from api.routers.errors import errors_file
    from api.settings import get_settings
    vid = imported_cube["versions"][0]["id"]
    path = errors_file(get_settings(), vid)
    path.parent.mkdir(parents=True, exist_ok=True)
    stale = {"version": 1, "n_faces": 12, "counts": {"loose": 0}}
    for body in (stale, {k: v for k, v in stale.items() if k != "version"}):
        path.write_text(json.dumps(body), encoding="utf-8")
        r = client.get(f"/api/versions/{vid}/errors")
        assert r.status_code == 404
        assert r.json()["detail"] == "not computed yet"

    from engine.detectors.errors import ERRORS_VERSION
    current = {**stale, "version": ERRORS_VERSION}
    path.write_text(json.dumps(current), encoding="utf-8")
    r = client.get(f"/api/versions/{vid}/errors")
    assert r.status_code == 200
    assert r.json() == current


def test_an_unknown_version_is_refused(client):
    r = client.post("/api/versions/999999/errors")
    assert r.status_code == 404
    assert r.json()["detail"] == "Version not found"


def test_a_fix_run_writes_its_after_errors_file(client, imported_cube):
    vid = imported_cube["versions"][0]["id"]
    run = client.post(f"/api/versions/{vid}/fix", json={"profile": {"n_dirs": 32}}).json()
    assert run["status"] == "completed"
    r = client.get(f"/api/versions/{run['fixed_version_id']}/errors")
    assert r.status_code == 200
    # numbered as the AFTER meshbuf is, so the viewer's face-count guard accepts it (review M6)
    after = client.get(f"/api/versions/{run['fixed_version_id']}").json()
    assert r.json()["n_faces"] == after["tri_count"]


def test_a_fix_run_completes_when_its_after_errors_file_fails(client, imported_cube, monkeypatch):
    """Review M6, Task 6's isolation: the AFTER file is written after the run is committed, and a
    failure there never changes the run's outcome -- the AFTER version simply has no file."""
    import api.routers.versions as versions_mod

    def fails(*_args, **_kwargs):
        raise RuntimeError("find_errors failed")

    monkeypatch.setattr(versions_mod, "find_errors", fails)
    vid = imported_cube["versions"][0]["id"]
    run = client.post(f"/api/versions/{vid}/fix", json={"profile": {"n_dirs": 32}}).json()
    assert run["status"] == "completed"
    r = client.get(f"/api/versions/{run['fixed_version_id']}/errors")
    assert r.status_code == 404
    assert r.json()["detail"] == "not computed yet"
