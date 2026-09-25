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

    from api.settings import get_settings
    settings = get_settings()
    # Create target file outside run directory that path traversal might attempt to reach
    traversal_target = settings.data_dir / "fixed" / "x.png"
    traversal_target.parent.mkdir(parents=True, exist_ok=True)
    traversal_target.write_bytes(b"dummy_png")

    # Path traversal and invalid view names must return 404 before opening any file
    for bad_view in ["%5C..%5C..%5Cx", "..%2Fx", "top", "invalid_view"]:
        r = client.get(f"/api/runs/{run_id}/guard/{bad_view}")
        assert r.status_code == 404

    # Assert no file was opened by FileResponse for bad views
    assert len(opened_paths) == 0

    # Valid view returns 200 and serves the file
    r_ok = client.get(f"/api/runs/{run_id}/guard/+z")
    assert r_ok.status_code == 200
    assert len(opened_paths) == 1
    assert opened_paths[0].endswith("guard_+z.png")

    # Ensure VALID_GUARD_VIEWS contains exactly the six axis views
    assert set(VALID_GUARD_VIEWS) == {"+x", "-x", "+y", "-y", "+z", "-z"}


def test_guard_images_written_by_run(client, imported_cube):
    from api.settings import get_settings
    settings = get_settings()
    version_id = imported_cube["versions"][0]["id"]
    r_fix = client.post(f"/api/versions/{version_id}/fix", json={"profile": {"n_dirs": 32}})
    assert r_fix.status_code == 201
    run_data = r_fix.json()
    run_id = run_data["id"]

    run_dir = settings.data_dir / "fixed" / str(run_id)
    # The run writes the six PNGs under its run directory
    for view in ["+x", "-x", "+y", "-y", "+z", "-z"]:
        png_path = run_dir / f"guard_{view}.png"
        assert png_path.exists(), f"guard_{view}.png should exist in {run_dir}"

    # And the endpoint serves one
    r_img = client.get(f"/api/runs/{run_id}/guard/+z")
    assert r_img.status_code == 200
    assert r_img.headers["content-type"] == "image/png"
    assert len(r_img.content) > 0



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
    assert r_fix.status_code == 201
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


def test_source_faces_maps_to_original_face_ids_and_obj_lines(client, _database):
    import json
    from api.settings import get_settings
    from engine.io.obj_writer import write_obj
    from engine.io.obj_reader import read_obj
    from engine.tests.fixtures.build import slab_with_sawtooth_side

    settings = get_settings()
    src = settings.source_dir
    src.mkdir(parents=True, exist_ok=True)

    m = slab_with_sawtooth_side()
    obj_path = src / "sawtooth.obj"
    write_obj(m, obj_path)
    (src / "_MANIFEST.txt").write_text(f"# manifest\nsawtooth.obj  {m.n_faces}  SawtoothGroup\n", encoding="utf-8")

    r_imp = client.post("/api/models/import", json={"file": "sawtooth.obj"})
    assert r_imp.status_code == 201
    model_data = r_imp.json()
    version_id = model_data["versions"][0]["id"]
    n_snap_faces = m.n_faces

    r_fix = client.post(
        f"/api/versions/{version_id}/fix",
        json={"profile": {"n_dirs": 16, "accept_slit": False}},
    )
    assert r_fix.status_code == 201
    fixed_id = r_fix.json()["fixed_version_id"]

    # Verify source_faces.json
    r_sf = client.get(f"/api/versions/{fixed_id}/assets/source_faces.json")
    assert r_sf.status_code == 200
    sf_data = r_sf.json()

    # Every face id in source_faces.json must be an ORIGINAL face ID (< n_snap_faces) or -1 (invented)
    snap_mesh = read_obj(obj_path)
    for row in sf_data:
        for orig_id in row:
            assert orig_id == -1 or 0 <= orig_id < n_snap_faces

    # Pick face 0 in fixed version
    r_face = client.get(f"/api/versions/{fixed_id}/faces/0")
    assert r_face.status_code == 200
    f_data = r_face.json()
    assert "source_faces" in f_data
    assert len(f_data["source_faces"]) > 0
    for sf in f_data["source_faces"]:
        orig_id = sf["face_id"]
        line = sf["line"]
        if orig_id != -1:
            assert 0 <= orig_id < n_snap_faces
            # Line matches the original OBJ file face_line
            assert line == int(snap_mesh.face_line[orig_id])



def test_fix_atomic_rollback_on_exception(client, imported_cube, monkeypatch, db):
    import api.routers.versions
    from api.models import FixRun, ModelVersion, VersionAsset
    from api.settings import get_settings
    from sqlalchemy import select

    settings = get_settings()
    version_id = imported_cube["versions"][0]["id"]

    def mock_build_report_fail(*args, **kwargs):
        raise RuntimeError("Report generation crash after flush")

    # Monkeypatch _build_report to fail AFTER fixed version and assets have been flushed
    monkeypatch.setattr(api.routers.versions, "_build_report", mock_build_report_fail)

    fixed_count_before = len(
        db.scalars(
            select(ModelVersion).where(
                ModelVersion.model_id == imported_cube["id"],
                ModelVersion.kind == "fixed",
            )
        ).all()
    )
    asset_count_before = len(db.scalars(select(VersionAsset)).all())

    r = client.post(f"/api/versions/{version_id}/fix", json={"profile": {"n_dirs": 32}})
    assert r.status_code == 201
    run_data = r.json()
    assert run_data["status"] == "failed"
    assert "RuntimeError: Report generation crash after flush" in (run_data["error"] or "")
    assert run_data.get("fixed_version_id") is None

    # In DB: NO new kind="fixed" version was created for this model (rolled back atomically)
    fixed_count_after = len(
        db.scalars(
            select(ModelVersion).where(
                ModelVersion.model_id == imported_cube["id"],
                ModelVersion.kind == "fixed",
            )
        ).all()
    )
    assert fixed_count_after == fixed_count_before

    # In DB: NO orphaned VersionAsset rows created
    asset_count_after = len(db.scalars(select(VersionAsset)).all())
    assert asset_count_after == asset_count_before

    # On disk: out_dir was cleaned up, no orphan directory left behind (m2)
    run_dir = settings.data_dir / "fixed" / str(run_data["id"])
    assert not run_dir.exists()

    # In DB: run is recorded as failed with formatted error
    run_db = db.scalar(select(FixRun).where(FixRun.id == run_data["id"]))
    assert run_db is not None
    assert run_db.status == "failed"
    assert run_db.error == "RuntimeError: Report generation crash after flush"


def test_two_sequential_runs_create_two_directories(client, imported_cube):
    from api.settings import get_settings

    settings = get_settings()
    version_id = imported_cube["versions"][0]["id"]

    r1 = client.post(f"/api/versions/{version_id}/fix", json={"profile": {"n_dirs": 32}})
    assert r1.status_code == 201
    run1_id = r1.json()["id"]

    r2 = client.post(f"/api/versions/{version_id}/fix", json={"profile": {"n_dirs": 32}})
    assert r2.status_code == 201
    run2_id = r2.json()["id"]

    assert run1_id != run2_id

    dir1 = settings.data_dir / "fixed" / str(run1_id)
    dir2 = settings.data_dir / "fixed" / str(run2_id)
    assert dir1.is_dir()
    assert dir2.is_dir()


def test_concurrent_fix_returns_409(client, imported_cube):
    import api.routers.versions

    version_id = imported_cube["versions"][0]["id"]
    model_id = imported_cube["id"]

    # Manually acquire the in-process lock to simulate an active fix running for this model
    with api.routers.versions._fixes_lock:
        api.routers.versions._active_model_fixes.add(model_id)

    try:
        # A second request for the same model must be rejected with 409
        r = client.post(f"/api/versions/{version_id}/fix", json={"profile": {"n_dirs": 32}})
        assert r.status_code == 409
        assert "fix already running" in r.json()["detail"]
    finally:
        with api.routers.versions._fixes_lock:
            api.routers.versions._active_model_fixes.discard(model_id)

    # After the lock is released, the request succeeds with 201
    r_ok = client.post(f"/api/versions/{version_id}/fix", json={"profile": {"n_dirs": 32}})
    assert r_ok.status_code == 201


def test_stored_flat_materials_enforced_to_zero_std(client, imported_cube, monkeypatch, db):
    import api.routers.versions
    from api.models import ModelVersion
    from sqlalchemy import select

    version_id = imported_cube["versions"][0]["id"]
    ver = db.scalar(select(ModelVersion).where(ModelVersion.id == version_id))
    ver.flat_materials = ["m0"]
    db.commit()

    captured_flatness = {}

    orig_fix = api.routers.versions.fix_object

    def spy_fix_object(mesh, flatness, profile):
        captured_flatness.update(flatness)
        return orig_fix(mesh, flatness, profile)

    monkeypatch.setattr(api.routers.versions, "fix_object", spy_fix_object)

    r = client.post(f"/api/versions/{version_id}/fix", json={"profile": {"n_dirs": 32, "flat_texture_std": 0.5}})
    assert r.status_code == 201
    assert captured_flatness.get("m0") == 0.0


def test_fix_run_writes_skp_and_copies_to_skp_dir(client, imported_cube):
    from api.settings import get_settings
    settings = get_settings()
    version_id = imported_cube["versions"][0]["id"]
    r_fix = client.post(f"/api/versions/{version_id}/fix", json={"profile": {"n_dirs": 32}})
    assert r_fix.status_code == 201
    run_data = r_fix.json()
    assert "skp" in run_data["report_json"]
    skp_info = run_data["report_json"]["skp"]

    # When SketchUp DLL is available on the host
    if not skp_info.get("written"):
        pytest.skip(f"SketchUp writer skipped: {skp_info.get('reason')}")
    run_dir = settings.data_dir / "fixed" / str(run_data["id"])
    name = imported_cube["name"]
    assert (run_dir / f"{name}.fixed.skp").exists()
    if settings.skp_dir:
        assert (settings.skp_dir / f"{name}.fixed.skp").exists()
    assert skp_info.get("copied_to") is not None


def test_fix_run_succeeds_when_skp_dll_absent(client, imported_cube, monkeypatch):
    from engine.io.skp_writer import SketchUpUnavailable
    import engine.cli

    def mock_write_skp(*args, **kwargs):
        raise SketchUpUnavailable("SketchUp C API DLL not found")

    monkeypatch.setattr(engine.cli, "write_skp", mock_write_skp)

    version_id = imported_cube["versions"][0]["id"]
    r_fix = client.post(f"/api/versions/{version_id}/fix", json={"profile": {"n_dirs": 32}})
    assert r_fix.status_code == 201
    run_data = r_fix.json()
    assert run_data["status"] == "completed"
    assert "skp" in run_data["report_json"]
    skp_info = run_data["report_json"]["skp"]
    assert skp_info["written"] is False
    assert "SketchUp C API DLL not found" in skp_info["reason"]


def test_fix_run_failure_after_skp_does_not_replace_owner_skp(client, imported_cube, monkeypatch):
    import api.routers.versions as versions_mod
    from api.settings import get_settings
    settings = get_settings()
    settings.skp_dir.mkdir(parents=True, exist_ok=True)
    name = imported_cube["name"]
    owner_file = settings.skp_dir / f"{name}.fixed.skp"
    owner_file.write_text("original owner skp content", encoding="utf-8")

    def fake_write_skp(result, name, out_dir, flat_mats, profile, enabled=True, copy_dir=None):
        skp_path = out_dir / f"{name}.fixed.skp"
        skp_path.write_text("new fixed skp content", encoding="utf-8")
        if copy_dir is not None:
            dest = copy_dir / f"{name}.fixed.skp"
            copy_dir.mkdir(parents=True, exist_ok=True)
            dest.write_text("new fixed skp content", encoding="utf-8")
            return {"written": True, "copied_to": str(dest)}
        return {"written": True, "copied_to": None}

    monkeypatch.setattr(versions_mod, "_write_skp", fake_write_skp)

    def fail_build_report(*args, **kwargs):
        raise RuntimeError("Crash after skp step")

    monkeypatch.setattr(versions_mod, "_build_report", fail_build_report)

    version_id = imported_cube["versions"][0]["id"]
    r_fix = client.post(f"/api/versions/{version_id}/fix", json={"profile": {"n_dirs": 32}})
    assert r_fix.status_code == 201
    run_data = r_fix.json()
    assert run_data["status"] == "failed"
    assert "Crash after skp step" in run_data["error"]

    # The owner's file must remain untouched!
    assert owner_file.exists()
    assert owner_file.read_text(encoding="utf-8") == "original owner skp content"


def test_skp_writing_is_serialized_by_lock(client, imported_cube, monkeypatch):
    import api.routers.versions as versions_mod
    lock_acquired = []

    def spy_write_skp(*args, **kwargs):
        assert versions_mod._skp_lock.locked()
        lock_acquired.append(True)
        return {"written": False, "reason": "test lock spy"}

    monkeypatch.setattr(versions_mod, "_write_skp", spy_write_skp)

    version_id = imported_cube["versions"][0]["id"]
    r_fix = client.post(f"/api/versions/{version_id}/fix", json={"profile": {"n_dirs": 32}})
    assert r_fix.status_code == 201
    assert len(lock_acquired) == 1






