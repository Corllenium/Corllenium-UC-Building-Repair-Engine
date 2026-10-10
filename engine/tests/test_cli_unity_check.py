# engine/tests/test_cli_unity_check.py
import json

import numpy as np

from engine import cli
from engine.io.obj_writer import write_obj
from engine.tests.fixtures.build import cube

M = np.array([[-1, 0, 0], [0, 0, 1], [0, 1, 0]], float)


def _write_dump(tmp_path, mesh, faces):
    p = (mesh.positions @ M.T) * 0.0254
    lines = ["mtllib d.mtl", "o m"] + [f"v {x:.6f} {y:.6f} {z:.6f}" for x, y, z in p]
    lines += [f"vt {u} {v}" for u, v in mesh.uvs]
    q = p[faces]
    n = np.cross(q[:, 1] - q[:, 0], q[:, 2] - q[:, 0])
    n /= np.linalg.norm(n, axis=1)[:, None]
    lines += [f"vn {x} {y} {z}" for x, y, z in n]
    lines.append("usemtl m0")
    for k, (f, t) in enumerate(zip(faces, mesh.face_vt[:, ::-1])):
        lines.append("f " + " ".join(f"{a + 1}/{b + 1}/{k + 1}" for a, b in zip(f, t)))
    (tmp_path / "d.obj").write_text("\n".join(lines) + "\n")
    (tmp_path / "d.mtl").write_text("newmtl m0\n")
    side = {"schema": 1, "complete": True, "unity_version": "6000.4.7f1", "asset_path": "x",
            "importer": {"globalScale": 0.0254}, "importer_sha256": "ab", "overrides": {},
            "meshes": [{"name": "m", "vertex_count": len(p), "index_format": "UInt32", "submeshes": []}]}
    (tmp_path / "d.unity.json").write_text(json.dumps(side))
    return tmp_path / "d.obj"


def _build(tmp_path):
    b = cube(100.0)
    write_obj(b, tmp_path / "b.obj")
    return b, tmp_path / "b.obj"


def test_an_unchanged_import_is_unity_safe(tmp_path):
    b, bp = _build(tmp_path)
    dp = _write_dump(tmp_path, b, b.face_v[:, ::-1])
    assert cli.main(["unity-check", "--build", str(bp), "--unity", str(dp), "--out", str(tmp_path / "o")]) == 0
    r = json.loads((tmp_path / "o" / "unity_check.json").read_text())
    assert r["verdict"] == "UNITY-SAFE" and r["causes"] == []


def test_a_dropped_face_is_broken_by_import_with_its_cause(tmp_path):
    b, bp = _build(tmp_path)
    dp = _write_dump(tmp_path, b, b.face_v[1:, ::-1])
    assert cli.main(["unity-check", "--build", str(bp), "--unity", str(dp), "--out", str(tmp_path / "o")]) == 3
    r = json.loads((tmp_path / "o" / "unity_check.json").read_text())
    assert r["verdict"] == "BROKEN BY IMPORT" and "missing" in r["causes"]


def test_an_incomplete_dump_is_refused(tmp_path):
    b, bp = _build(tmp_path)
    dp = _write_dump(tmp_path, b, b.face_v[:, ::-1])
    (tmp_path / "d.unity.json").write_text(json.dumps({"schema": 1, "complete": False}))
    assert cli.main(["unity-check", "--build", str(bp), "--unity", str(dp), "--out", str(tmp_path / "o")]) == 2
