from pathlib import Path
import pytest
from engine.io.obj_writer import write_obj
from engine.tests.fixtures.build import cube
from engine.transport.meshbuf import unpack_meshbuf


@pytest.fixture
def imported_cube(client, _database):
    from api.settings import get_settings
    settings = get_settings()
    src = settings.source_dir
    src.mkdir(parents=True, exist_ok=True)

    m = cube(10.0)
    write_obj(m, src / "cube.obj")
    (src / "_MANIFEST.txt").write_text(f"# manifest\ncube.obj  {m.n_faces}  CubeGroup\n", encoding="utf-8")

    r = client.post("/api/models/import", json={"file": "cube.obj"})
    assert r.status_code == 201
    return r.json()


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
    assert r.status_code == 200
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
