from pathlib import Path
import pytest
from engine.io.obj_writer import write_obj
from engine.tests.fixtures.build import cube


@pytest.fixture
def sample_source_dir(_database):
    from api.settings import get_settings
    settings = get_settings()
    src = settings.source_dir
    src.mkdir(parents=True, exist_ok=True)

    # Write a test cube
    m = cube(10.0)
    write_obj(m, src / "test_cube.obj")

    # Write a manifest
    manifest_lines = [
        "# manifest",
        f"test_cube.obj  {m.n_faces}  CubeGroup",
    ]
    (src / "_MANIFEST.txt").write_text("\n".join(manifest_lines), encoding="utf-8")
    return src


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
