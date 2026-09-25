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


def test_fix_run_report_carries_details_and_source_faces(client, _database):
    import json
    from api.settings import get_settings
    from engine.io.obj_writer import write_obj
    from engine.tests.fixtures.build import box_with_partition

    settings = get_settings()
    src = settings.source_dir
    src.mkdir(parents=True, exist_ok=True)

    m = box_with_partition(10.0)
    write_obj(m, src / "box_part.obj")
    (src / "_MANIFEST.txt").write_text(f"# manifest\nbox_part.obj  {m.n_faces}  BoxPartGroup\n", encoding="utf-8")

    r_imp = client.post("/api/models/import", json={"file": "box_part.obj"})
    assert r_imp.status_code == 201
    model_data = r_imp.json()
    version_id = model_data["versions"][0]["id"]

    r_fix = client.post(
        f"/api/versions/{version_id}/fix",
        json={"profile": {"n_dirs": 32, "accept_slit": False}},
    )
    assert r_fix.status_code == 200
    run_data = r_fix.json()
    rep = run_data["report_json"]

    # 1. merge_report
    assert "merge_report" in rep
    mr = rep["merge_report"]
    for k in [
        "converged", "rolled_back", "rolled_back_reason", "tris_before",
        "tris_after", "regions_merged", "skipped_by_reason", "merge_rounds"
    ]:
        assert k in mr, f"Missing key {k} in merge_report"

    # 2. guard_after_removal and guard_final with totals and passed
    for guard_key in ["guard_after_removal", "guard_final"]:
        assert guard_key in rep
        g = rep[guard_key]
        assert "passed" in g
        assert "totals" in g
        assert "edge_flicker" in g["totals"]

    # 3. invariants and passed
    assert "invariants" in rep
    assert "passed" in rep

    # 4. n_* counts
    for count_key in [
        "n_removed_hidden", "n_restored_by_guard", "n_flipped",
        "n_zero_area_dropped", "n_hidden_candidates"
    ]:
        assert count_key in rep, f"Missing {count_key} in report"

    # 5. one_sided_holes before/after and profile
    assert "one_sided_holes_before" in rep
    assert "one_sided_holes_after" in rep
    assert "profile" in rep

    # 6. source_faces asset
    fixed_version_id = run_data["fixed_version_id"]
    r_ver = client.get(f"/api/versions/{fixed_version_id}")
    assert r_ver.status_code == 200
    v_assets = r_ver.json()["assets"]
    sf_asset = next((a for a in v_assets if a["kind"] == "source_faces"), None)
    assert sf_asset is not None, "source_faces asset not found on fixed version"
    assert sf_asset["name"] == "source_faces.json"

    # Check file exists and is valid list of lists
    sf_file = settings.data_dir / sf_asset["path"]
    assert sf_file.exists()
    sf_data = json.loads(sf_file.read_text(encoding="utf-8"))
    assert isinstance(sf_data, list)
    assert len(sf_data) == rep["tris_after"]
    for row in sf_data:
        assert isinstance(row, list)
        for orig_id in row:
            assert isinstance(orig_id, int)

