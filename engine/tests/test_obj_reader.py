import numpy as np
import pytest

from engine.io.obj_reader import ObjFormatError, read_obj

OBJ = """# demo
mtllib ../lib.mtl
o Demo_Object
v 1442.94 22669.4 1622.05
v 1442.94 22630.1 1612.2
v 1442.94 22630.1 1622.05
v 10 0 -0.5
vt 0 0
vt 1 0
vt 1 1
vn 1 0 0
usemtl stone
f 1/1/1 2/2/1 3/3/1
usemtl paint
f 2//1 1//1 4//1
f -4 -3 -2
"""


def test_reads_arrays_and_keeps_face_order(tmp_path):
    p = tmp_path / "a.obj"
    p.write_text(OBJ)
    m = read_obj(p)
    assert m.name == "Demo_Object" and m.mtllib == "../lib.mtl"
    assert m.positions.shape == (4, 3) and m.uvs.shape == (3, 2) and m.normals.shape == (1, 3)
    assert m.face_v.tolist() == [[0, 1, 2], [1, 0, 3], [0, 1, 2]]
    assert m.face_vt.tolist() == [[0, 1, 2], [-1, -1, -1], [-1, -1, -1]]
    assert m.face_vn.tolist() == [[0, 0, 0], [0, 0, 0], [-1, -1, -1]]
    assert m.materials == ["stone", "paint"] and m.face_material.tolist() == [0, 1, 1]
    assert m.face_line.tolist() == [13, 15, 16]
    assert m.coord_decimals == 2 and m.sig_digits == 6


def test_rejects_quads(tmp_path):
    p = tmp_path / "q.obj"
    p.write_text("v 0 0 0\nv 1 0 0\nv 1 1 0\nv 0 1 0\nf 1 2 3 4\n")
    with pytest.raises(ObjFormatError, match="line 5"):
        read_obj(p)


def test_name_falls_back_to_stem(tmp_path):
    p = tmp_path / "thing.obj"
    p.write_text("v 0 0 0\nv 1 0 0\nv 0 1 0\nf 1 2 3\n")
    assert read_obj(p).name == "thing"
