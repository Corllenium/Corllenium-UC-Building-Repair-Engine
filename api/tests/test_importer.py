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
    m = replace(cube(10.0), name="textured_cube", mtllib="textured_cube.mtl", materials=["stone"])
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
