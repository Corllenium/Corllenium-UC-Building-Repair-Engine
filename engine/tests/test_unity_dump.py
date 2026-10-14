# engine/tests/test_unity_dump.py
import json
from pathlib import Path

import numpy as np
import pytest

from engine.unity.dump import DumpError, read_unity_dump

OBJ = """o m
v 0 0 0
v 1 0 0
v 0 1 0
vt 0 0
vt 1 0
vt 0 1
vn 0 0 1
usemtl wall
f 1/1/1 2/2/1 3/3/1
"""


def _sidecar(**over):
    d = {"schema": 1, "complete": True, "unity_version": "6000.4.7f1", "asset_path": "Assets/x.obj",
         "importer": {"globalScale": 0.0254}, "importer_sha256": "ab", "overrides": {},
         "meshes": [{"name": "m", "vertex_count": 3, "index_format": "UInt16",
                     "submeshes": [{"material": "wall", "texture": None, "triangle_count": 1}]}]}
    d.update(over)
    return d


def _write(tmp_path, sidecar):
    (tmp_path / "f.obj").write_text("mtllib f.mtl\n" + OBJ)
    (tmp_path / "f.mtl").write_text("newmtl wall\n")
    if sidecar is not None:
        (tmp_path / "f.unity.json").write_text(json.dumps(sidecar))
    return tmp_path / "f.obj"


def test_a_complete_dump_reads_mesh_corner_normals_and_sidecar(tmp_path):
    d = read_unity_dump(_write(tmp_path, _sidecar()))
    assert d.mesh.n_faces == 1 and d.mesh.materials == ["wall"]
    assert d.corner_normals.shape == (1, 3, 3)
    np.testing.assert_allclose(d.corner_normals[0], [[0, 0, 1]] * 3)
    assert d.sidecar["meshes"][0]["index_format"] == "UInt16"


def test_a_dump_without_its_sidecar_is_refused(tmp_path):
    with pytest.raises(DumpError, match="sidecar"):
        read_unity_dump(_write(tmp_path, None))


def test_a_half_written_dump_is_refused(tmp_path):
    with pytest.raises(DumpError, match="complete"):
        read_unity_dump(_write(tmp_path, _sidecar(complete=False)))


def test_an_unknown_schema_is_refused(tmp_path):
    with pytest.raises(DumpError, match="schema"):
        read_unity_dump(_write(tmp_path, _sidecar(schema=2)))


def test_a_face_without_normals_is_refused(tmp_path):
    p = _write(tmp_path, _sidecar())
    p.write_text(p.read_text().replace("f 1/1/1 2/2/1 3/3/1", "f 1/1 2/2 3/3"))
    with pytest.raises(DumpError, match="normal"):
        read_unity_dump(p)
