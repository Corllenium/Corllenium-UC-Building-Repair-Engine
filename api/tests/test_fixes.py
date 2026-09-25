import pytest
from api.routers.fixes import VALID_GUARD_VIEWS


def test_guard_view_validation(client, imported_cube, monkeypatch):
    version_id = imported_cube["versions"][0]["id"]
    r_fix = client.post(f"/api/versions/{version_id}/fix", json={"profile": {"n_dirs": 32}})
    run_id = r_fix.json()["id"]

    import api.routers.fixes
    opened_paths = []
    original_file_response = api.routers.fixes.FileResponse

    def mock_file_response(path, *args, **kwargs):
        opened_paths.append(str(path))
        return original_file_response(path, *args, **kwargs)

    monkeypatch.setattr(api.routers.fixes, "FileResponse", mock_file_response)

    # Path traversal and invalid view names must return 404 before opening any file
    for bad_view in ["%5C..%5C..%5Cx", "..%2Fx", "top", "invalid_view"]:
        r = client.get(f"/api/runs/{run_id}/guard/{bad_view}")
        assert r.status_code == 404

    # Assert no file was opened by FileResponse
    assert len(opened_paths) == 0

    # Ensure VALID_GUARD_VIEWS contains exactly the six axis views
    assert set(VALID_GUARD_VIEWS) == {"+x", "-x", "+y", "-y", "+z", "-z"}
