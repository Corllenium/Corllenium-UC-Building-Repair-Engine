from dataclasses import replace
from pathlib import Path

import numpy as np
import pytest
from PIL import Image

from engine.io.obj_writer import write_obj
from engine.tests.fixtures.build import cube


def test_list_source_files(client, sample_source_dir):
    r = client.get("/api/source/files")
    assert r.status_code == 200
    files = r.json()
    assert any(f["file"] == "test_cube.obj" and f["tri_count"] == 12 for f in files)


def test_import_model(client, sample_source_dir):
    # Import
    r = client.post("/api/models/import", json={"file": "test_cube.obj"})
    assert r.status_code == 201
    data = r.json()
    assert data["name"] == "test_cube"
    assert data["source_file"] == "test_cube.obj"
    assert len(data["versions"]) == 1
    v = data["versions"][0]
    assert v["kind"] == "snapshot"
    assert v["tri_count"] == 12

    # Idempotent re-import returns the same model
    r2 = client.post("/api/models/import", json={"file": "test_cube.obj"})
    assert r2.status_code == 201
    data2 = r2.json()
    assert data2["id"] == data["id"]
    assert len(data2["versions"]) == 1

    # List models returns the imported model
    r_list = client.get("/api/models")
    assert r_list.status_code == 200
    models = r_list.json()
    assert any(m["id"] == data["id"] for m in models)


def test_import_nonexistent_fails(client, sample_source_dir):
    r = client.post("/api/models/import", json={"file": "nonexistent.obj"})
    assert r.status_code == 404


def test_source_unstable_409_and_manifest_mismatch_422(client, sample_source_dir, monkeypatch):
    from engine.io.snapshot import SourceUnstable, ManifestMismatch
    import api.services.importer

    # 1. SourceUnstable during import -> 409 with Retry-After: 5
    def mock_snapshot_unstable(*args, **kwargs):
        raise SourceUnstable("Source folder is being rebuilt")

    monkeypatch.setattr(api.services.importer, "snapshot_object", mock_snapshot_unstable)
    r = client.post("/api/models/import", json={"file": "test_cube.obj"})
    assert r.status_code == 409
    assert r.headers.get("retry-after") == "5"

    # 2. SourceUnstable during scan -> 409 with Retry-After: 5
    def mock_read_manifest_unstable(*args, **kwargs):
        raise SourceUnstable("Manifest locked during scan")

    monkeypatch.setattr(api.services.importer, "read_manifest_stable", mock_read_manifest_unstable)
    r_scan = client.get("/api/source/files")
    assert r_scan.status_code == 409
    assert r_scan.headers.get("retry-after") == "5"
    monkeypatch.undo()

    # 3. ManifestMismatch during import -> 422
    def mock_snapshot_mismatch(*args, **kwargs):
        raise ManifestMismatch("Face count mismatch: expected 12, got 14")

    monkeypatch.setattr(api.services.importer, "snapshot_object", mock_snapshot_mismatch)
    r_mis = client.post("/api/models/import", json={"file": "test_cube.obj"})
    assert r_mis.status_code == 422



@pytest.fixture
def textured_source_dir(_database):
    from dataclasses import replace
    import numpy as np
    from PIL import Image
    from engine.io.obj_writer import write_obj
    from engine.tests.fixtures.build import cube
    from api.settings import get_settings

    src = get_settings().source_dir
    (src / "tex").mkdir(parents=True, exist_ok=True)
    m = replace(cube(18.0), name="textured_cube", mtllib="textured_cube.mtl", materials=["stone"])
    write_obj(m, src / "textured_cube.obj")
    (src / "textured_cube.mtl").write_text("newmtl stone\nmap_Kd tex/stone.png\n", encoding="utf-8")
    Image.fromarray(np.full((4, 4, 3), 220, np.uint8)).save(src / "tex" / "stone.png")
    (src / "_MANIFEST.txt").write_text(f"# manifest\ntextured_cube.obj  {m.n_faces}  TexturedGroup\n", encoding="utf-8")
    return src


def test_texture_only_reexport_imports_a_new_version(client, textured_source_dir):
    # A texture-only re-export leaves the OBJ bytes alone. Deduplicating versions on them alone
    # returns the old version, whose assets still serve the old texture.
    tex = textured_source_dir / "tex" / "stone.png"
    [old] = client.post("/api/models/import", json={"file": "textured_cube.obj"}).json()["versions"]
    assert old["asset_sha256"] is not None and len(old["asset_sha256"]) == 64
    unchanged = client.post("/api/models/import", json={"file": "textured_cube.obj"}).json()["versions"]
    assert [v["id"] for v in unchanged] == [old["id"]]

    checker = (np.indices((4, 4)).sum(axis=0) % 2 * 255).astype(np.uint8)
    Image.fromarray(np.dstack([checker] * 3)).save(tex)
    r = client.post("/api/models/import", json={"file": "textured_cube.obj"})
    assert r.status_code == 201
    versions = r.json()["versions"]
    assert [v["id"] for v in versions][0] == old["id"] and len(versions) == 2
    new = versions[1]
    assert new["kind"] == "snapshot" and new["sha256"] == old["sha256"]
    assert new["asset_sha256"] != old["asset_sha256"]
    assert client.get(f"/api/versions/{new['id']}/textures/stone.png").content == tex.read_bytes()
    assert client.get(f"/api/versions/{old['id']}/textures/stone.png").content != tex.read_bytes()


def test_import_identical_bytes_two_file_names(client, sample_source_dir):
    from engine.io.obj_writer import write_obj
    from engine.tests.fixtures.build import cube

    # Two distinct files with identical OBJ bytes (D0 identity test case)
    m = cube(20.0)
    write_obj(m, sample_source_dir / "identical_a.obj")
    write_obj(m, sample_source_dir / "identical_b.obj")

    manifest = (sample_source_dir / "_MANIFEST.txt").read_text(encoding="utf-8")
    manifest += f"identical_a.obj  {m.n_faces}  IdenticalGroup\n"
    manifest += f"identical_b.obj  {m.n_faces}  IdenticalGroup\n"
    (sample_source_dir / "_MANIFEST.txt").write_text(manifest, encoding="utf-8")

    r_a = client.post("/api/models/import", json={"file": "identical_a.obj"})
    assert r_a.status_code == 201
    model_a = r_a.json()
    assert model_a["name"] == "identical_a"

    r_b = client.post("/api/models/import", json={"file": "identical_b.obj"})
    assert r_b.status_code == 201
    model_b = r_b.json()
    assert model_b["name"] == "identical_b"
    assert model_b["id"] != model_a["id"]

    # Both models share identical sha256 for their snapshot versions
    assert model_a["versions"][0]["sha256"] == model_b["versions"][0]["sha256"]


def test_import_path_traversal_rejected(client, sample_source_dir):
    # Directory traversal attempts must be rejected with 404 (m11)
    for bad_name in ["../test_cube.obj", "..\\test_cube.obj", "/test_cube.obj", "nonexistent.obj"]:
        r = client.post("/api/models/import", json={"file": bad_name})
        assert r.status_code == 404


def test_m5_backfill_does_not_backfill_when_assets_differ(client, textured_source_dir, db):
    from api.models import ModelVersion
    from sqlalchemy import select

    # First import
    r = client.post("/api/models/import", json={"file": "textured_cube.obj"})
    assert r.status_code == 201
    initial_count = len(r.json()["versions"])
    v_id = r.json()["versions"][-1]["id"]

    ver = db.scalar(select(ModelVersion).where(ModelVersion.id == v_id))
    ver.asset_sha256 = None
    db.commit()

    # Modify texture on disk before re-importing
    tex = textured_source_dir / "tex" / "stone.png"
    Image.fromarray(np.full((4, 4, 3), 100, np.uint8)).save(tex)

    # Re-importing must NOT backfill since assets differ; it must create a new version (m5)
    r2 = client.post("/api/models/import", json={"file": "textured_cube.obj"})
    assert r2.status_code == 201
    versions = r2.json()["versions"]
    assert len(versions) == initial_count + 1


def test_m5_backfill_succeeds_for_unchanged_textured_model(client, textured_source_dir, db):
    from dataclasses import replace
    import numpy as np
    from PIL import Image
    from engine.io.obj_writer import write_obj
    from engine.tests.fixtures.build import cube
    from api.models import ModelVersion
    from sqlalchemy import select

    src = textured_source_dir
    m = replace(cube(14.0), name="backfill_cube", mtllib="backfill_cube.mtl", materials=["granite"])
    write_obj(m, src / "backfill_cube.obj")
    (src / "backfill_cube.mtl").write_text("newmtl granite\nmap_Kd tex/granite.png\n", encoding="utf-8")
    Image.fromarray(np.full((4, 4, 3), 150, np.uint8)).save(src / "tex" / "granite.png")

    manifest_lines = (src / "_MANIFEST.txt").read_text(encoding="utf-8")
    (src / "_MANIFEST.txt").write_text(manifest_lines + f"backfill_cube.obj  {m.n_faces}  BackfillGroup\n", encoding="utf-8")

    # First import
    r = client.post("/api/models/import", json={"file": "backfill_cube.obj"})
    assert r.status_code == 201
    model_data = r.json()
    assert len(model_data["versions"]) == 1
    v_id = model_data["versions"][0]["id"]
    orig_asset_sha = model_data["versions"][0]["asset_sha256"]
    assert orig_asset_sha is not None

    # Simulate pre-migration state where asset_sha256 was NULL
    ver = db.scalar(select(ModelVersion).where(ModelVersion.id == v_id))
    ver.asset_sha256 = None
    ver.flat_materials = None
    db.commit()

    # Re-importing with UNCHANGED textures/MTL must backfill asset_sha256, NOT create a duplicate version!
    r2 = client.post("/api/models/import", json={"file": "backfill_cube.obj"})
    assert r2.status_code == 201
    versions = r2.json()["versions"]
    assert len(versions) == 1
    assert versions[0]["id"] == v_id
    assert versions[0]["asset_sha256"] == orig_asset_sha
    assert versions[0]["flat_materials"] is not None


