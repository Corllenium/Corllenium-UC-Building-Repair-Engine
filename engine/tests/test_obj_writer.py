import numpy as np

from engine.io.obj_reader import read_obj
from engine.io.obj_writer import write_obj
from engine.tests.fixtures.build import cube


def test_round_trip_preserves_everything(tmp_path):
    a = cube(10.0)
    a.materials, a.face_material = ["stone", "paint"], np.array([0] * 6 + [1] * 6)
    p = tmp_path / "c.obj"
    write_obj(a, p)
    b = read_obj(p)
    assert np.array_equal(a.positions, b.positions) and np.allclose(a.uvs, b.uvs, atol=1e-6)
    assert np.array_equal(a.face_v, b.face_v) and np.array_equal(a.face_vt, b.face_vt)
    assert b.materials == ["stone", "paint"] and np.array_equal(a.face_material, b.face_material)


def test_write_is_deterministic(tmp_path):
    write_obj(cube(), tmp_path / "1.obj")
    write_obj(cube(), tmp_path / "2.obj")
    assert (tmp_path / "1.obj").read_bytes() == (tmp_path / "2.obj").read_bytes()
