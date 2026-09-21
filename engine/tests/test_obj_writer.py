import numpy as np
import pytest

from engine.fixes.merge import merge_regions
from engine.io.obj_reader import ObjFormatError, read_obj
from engine.io.obj_writer import write_obj, write_obj_polygons
from engine.pipeline import analyse_topology
from engine.tests.fixtures.build import cube, grid_slab, slab_with_hole


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


# ---------------------------------------------------------------------------------------------
# Task 9: write_obj_polygons -- one f line per hole-free merged region (MergeResult.rings),
# ordinary triangles otherwise. The polygon file is a viewer/documentation artifact, never
# re-read by read_obj (triangles only, by design).
# ---------------------------------------------------------------------------------------------

def _face_lines(path):
    """A tiny polygon-aware counter: just the token counts of every 'f' line, without going
    through read_obj (which refuses non-triangle faces by design)."""
    out = []
    for line in path.read_text(encoding="utf-8").splitlines():
        if line.startswith("f "):
            out.append(len(line.split()) - 1)  # vertex count of that face
    return out


def test_grid_slab_ngon_file_has_exactly_one_four_vertex_face(tmp_path):
    m = grid_slab(10, 10)
    r = merge_regions(m, analyse_topology(m))
    assert r.mesh.n_faces == 2  # the triangulated file still has 2 triangles

    path = tmp_path / "grid_slab.ngon.obj"
    write_obj_polygons(r.mesh, r.rings, path)

    faces = _face_lines(path)
    assert faces == [4]  # exactly one face, 4 vertices -- both triangles collapsed into it

    with pytest.raises(ObjFormatError):
        read_obj(path)  # triangles only, by design -- must fail loudly, not silently mis-parse


def test_slab_with_hole_ngon_file_stays_eight_triangles(tmp_path):
    m = slab_with_hole()
    r = merge_regions(m, analyse_topology(m))
    assert r.mesh.n_faces == 8
    assert r.rings == {}  # the region has a hole: no polygon entry

    path = tmp_path / "slab_with_hole.ngon.obj"
    write_obj_polygons(r.mesh, r.rings, path)

    faces = _face_lines(path)
    assert faces == [3] * 8  # ordinary triangles, one line per output face

    back = read_obj(path)  # every face IS a triangle here, so read_obj succeeds
    assert back.n_faces == 8


def test_ngon_polygon_face_uses_the_ring_vertex_ids_in_order(tmp_path):
    m = grid_slab(10, 10)
    r = merge_regions(m, analyse_topology(m))
    path = tmp_path / "grid_slab.ngon.obj"
    write_obj_polygons(r.mesh, r.rings, path)

    lines = [ln for ln in path.read_text(encoding="utf-8").splitlines() if ln.startswith("f ")]
    assert len(lines) == 1
    obj_indices = [int(tok) for tok in lines[0].split()[1:]]
    assert sorted(v - 1 for v in obj_indices) == sorted(int(v) for v in r.rings[0])


def test_write_obj_polygons_is_deterministic(tmp_path):
    m = grid_slab(10, 10)
    r = merge_regions(m, analyse_topology(m))
    write_obj_polygons(r.mesh, r.rings, tmp_path / "1.obj")
    write_obj_polygons(r.mesh, r.rings, tmp_path / "2.obj")
    assert (tmp_path / "1.obj").read_bytes() == (tmp_path / "2.obj").read_bytes()
