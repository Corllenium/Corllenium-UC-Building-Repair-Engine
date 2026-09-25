from pathlib import Path
import pytest
from engine.transport.meshbuf import unpack_meshbuf


def test_get_meshbuf(client, imported_cube):
    version_id = imported_cube["versions"][0]["id"]
    r = client.get(f"/api/versions/{version_id}/meshbuf")
    assert r.status_code == 200
    assert r.headers["content-type"] == "application/octet-stream"
    assert r.headers["x-tris-count"] == "12"

    buf = r.content
    assert buf[:4] == b"UCMB"
    header, blocks = unpack_meshbuf(buf)
    assert header["name"] == "cube"
    assert header["counts"]["faces"] == 12
    assert "positions" in blocks


def test_run_fix_endpoint(client, imported_cube):
    version_id = imported_cube["versions"][0]["id"]
    r = client.post(
        f"/api/versions/{version_id}/fix",
        json={"profile": {"n_dirs": 32, "slit_threshold": 0.05, "accept_slit": False}},
    )
    assert r.status_code == 201
    run_data = r.json()
    assert run_data["status"] == "completed"
    assert run_data["fixed_version_id"] is not None
    assert run_data["report_json"]["tris_before"] == 12

    # Check run can be fetched
    run_id = run_data["id"]
    r_run = client.get(f"/api/runs/{run_id}")
    assert r_run.status_code == 200
    assert r_run.json()["id"] == run_id

    # Check fixed version meshbuf can be fetched
    fixed_ver_id = run_data["fixed_version_id"]
    r_fixed_mb = client.get(f"/api/versions/{fixed_ver_id}/meshbuf")
    assert r_fixed_mb.status_code == 200
    assert r_fixed_mb.content[:4] == b"UCMB"


def test_fixed_version_keeps_materials_and_textures(client, _database):
    from dataclasses import replace
    import numpy as np
    from PIL import Image
    from engine.io.obj_writer import write_obj
    from engine.tests.fixtures.build import cube
    from api.settings import get_settings

    src = get_settings().source_dir
    (src / "tex").mkdir(parents=True, exist_ok=True)
    m = replace(cube(14.0), name="stone_cube", mtllib="stone_cube.mtl", materials=["stone"])
    write_obj(m, src / "stone_cube.obj")
    (src / "stone_cube.mtl").write_text("newmtl stone\nmap_Kd tex/stone.png\n", encoding="utf-8")
    Image.fromarray(np.full((4, 4, 3), 220, np.uint8)).save(src / "tex" / "stone.png")
    (src / "_MANIFEST.txt").write_text(f"# manifest\nstone_cube.obj  {m.n_faces}  StoneGroup\n", encoding="utf-8")

    r_imp = client.post("/api/models/import", json={"file": "stone_cube.obj"})
    assert r_imp.status_code == 201
    snap_ver = r_imp.json()["versions"][0]
    snap_ver_id = snap_ver["id"]
    assert "stone" in (snap_ver.get("flat_materials") or [])

    # Get snapshot meshbuf
    r_snap_mb = client.get(f"/api/versions/{snap_ver_id}/meshbuf")
    assert r_snap_mb.status_code == 200
    snap_header, _ = unpack_meshbuf(r_snap_mb.content)
    assert any(m["name"] == "stone" and m.get("texture") == "tex/stone.png" for m in snap_header["materials"])

    # Run fix
    r_fix = client.post(
        f"/api/versions/{snap_ver_id}/fix",
        json={"profile": {"n_dirs": 32, "accept_slit": False}},
    )
    assert r_fix.status_code == 201
    fixed_ver_id = r_fix.json()["fixed_version_id"]

    # Fixed version meshbuf must have identical materials and texture entries
    r_fixed_mb = client.get(f"/api/versions/{fixed_ver_id}/meshbuf")
    assert r_fixed_mb.status_code == 200
    fixed_header, _ = unpack_meshbuf(r_fixed_mb.content)
    assert fixed_header["materials"] == snap_header["materials"]
    assert any(m["name"] == "stone" and m.get("texture") == "tex/stone.png" for m in fixed_header["materials"])


def test_m5_backfill_null_asset_sha256(client, _database, db):
    from engine.io.obj_writer import write_obj
    from engine.tests.fixtures.build import cube
    from api.settings import get_settings
    from api.models import ModelVersion
    from sqlalchemy import select

    src = get_settings().source_dir
    src.mkdir(parents=True, exist_ok=True)
    m = cube(16.0)
    write_obj(m, src / "m5_cube.obj")
    (src / "_MANIFEST.txt").write_text(f"# manifest\nm5_cube.obj  {m.n_faces}  M5Group\n", encoding="utf-8")

    # Import cube
    r_imp = client.post("/api/models/import", json={"file": "m5_cube.obj"})
    assert r_imp.status_code == 201
    v_id = r_imp.json()["versions"][0]["id"]

    # Simulate pre-e57462d version where asset_sha256 was NULL
    ver = db.scalar(select(ModelVersion).where(ModelVersion.id == v_id))
    real_asset_sha = ver.asset_sha256
    assert real_asset_sha is not None
    ver.asset_sha256 = None
    db.commit()

    # Re-importing must not create a duplicate version, and must backfill asset_sha256
    r_reimp = client.post("/api/models/import", json={"file": "m5_cube.obj"})
    assert r_reimp.status_code == 201
    versions = r_reimp.json()["versions"]
    assert len(versions) == 1
    assert versions[0]["id"] == v_id
    assert versions[0]["asset_sha256"] == real_asset_sha


def test_face_picking_endpoint_for_snapshot_and_fixed(client, imported_cube):
    version_id = imported_cube["versions"][0]["id"]

    # 1. Test snapshot version face endpoint
    r = client.get(f"/api/versions/{version_id}/faces/0")
    assert r.status_code == 200
    data = r.json()
    assert data["face_id"] == 0
    assert isinstance(data["line"], int)
    assert data["line"] > 0
    assert data["material"] == "m0"
    assert len(data["vertices"]) == 3
    assert len(data["vertices"][0]) == 3
    assert "source_faces" not in data or data["source_faces"] is None

    # Invalid face id
    assert client.get(f"/api/versions/{version_id}/faces/999").status_code == 404
    assert client.get(f"/api/versions/{version_id}/faces/-1").status_code == 404

    # 2. Run fix and test fixed version face endpoint
    r_fix = client.post(
        f"/api/versions/{version_id}/fix",
        json={"profile": {"n_dirs": 32, "slit_threshold": 0.05, "accept_slit": False}},
    )
    assert r_fix.status_code == 201
    fixed_ver_id = r_fix.json()["fixed_version_id"]
    assert fixed_ver_id is not None

    r_fixed = client.get(f"/api/versions/{fixed_ver_id}/faces/0")
    assert r_fixed.status_code == 200
    data_fixed = r_fixed.json()
    assert data_fixed["face_id"] == 0
    assert isinstance(data_fixed["line"], int)
    assert data_fixed["line"] > 0
    assert len(data_fixed["vertices"]) == 3
    assert "source_faces" in data_fixed
    assert isinstance(data_fixed["source_faces"], list)
    assert len(data_fixed["source_faces"]) >= 1
    for sf in data_fixed["source_faces"]:
        assert "face_id" in sf
        assert "line" in sf
        assert isinstance(sf["face_id"], int)
        assert isinstance(sf["line"], int)
        assert sf["line"] > 0


def test_get_version_run(client, imported_cube):
    version_id = imported_cube["versions"][0]["id"]
    # 404 when no fix run has occurred
    r_empty = client.get(f"/api/versions/{version_id}/run")
    assert r_empty.status_code == 404

    # Run fix
    r_fix = client.post(
        f"/api/versions/{version_id}/fix",
        json={"profile": {"n_dirs": 32, "slit_threshold": 0.05, "accept_slit": False}},
    )
    assert r_fix.status_code == 201
    run_data = r_fix.json()
    fixed_ver_id = run_data["fixed_version_id"]
    assert fixed_ver_id is not None

    # Fetch run for fixed version
    r_run = client.get(f"/api/versions/{fixed_ver_id}/run")
    assert r_run.status_code == 200
    assert r_run.json()["id"] == run_data["id"]
    assert "report_json" in r_run.json()

    # Non-existent version
    assert client.get("/api/versions/99999/run").status_code == 404


