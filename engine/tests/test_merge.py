import numpy as np

from engine.fixes.merge import merge_regions
from engine.io.obj_reader import read_obj
from engine.io.obj_writer import write_obj
from engine.pipeline import analyse_topology
from engine.tests.fixtures.build import (cube, grid_slab, l_shaped_slab, overlapping_pair, slab_with_hole,
                                         slab_with_wall, two_slabs_sharing_border)


def area(mesh):
    p = mesh.positions[mesh.face_v]
    return float(0.5 * np.linalg.norm(np.cross(p[:, 1] - p[:, 0], p[:, 2] - p[:, 0]), axis=1).sum())


def used(mesh):
    return set(int(v) for v in mesh.face_v.reshape(-1))


def merged(mesh, flat_materials=frozenset()):
    return merge_regions(mesh, analyse_topology(mesh, flat_materials), flat_materials)


def test_grid_slab_merges_to_two_triangles():
    m = grid_slab(10, 10)
    r = merged(m)
    assert m.n_faces == 200 and r.mesh.n_faces == 2
    assert r.report["tris_before"] == 200 and r.report["tris_after"] == 2
    assert r.report["regions_merged"] == 1 and r.report["regions_skipped"] == {}
    assert len(m.positions) == 121 and len(used(r.mesh)) == 4
    assert r.report["vertices_dropped"] == 117
    assert abs(area(r.mesh) - area(m)) <= 1e-9 * area(m)
    assert r.report["max_area_rel_error"] <= 1e-9


def test_grid_slab_triangles_are_wound_to_the_region_normal():
    r = merged(grid_slab(10, 10))
    p = r.mesh.positions[r.mesh.face_v]
    n = np.cross(p[:, 1] - p[:, 0], p[:, 2] - p[:, 0])
    assert (n[:, 2] > 0).all()


def test_l_shaped_slab_merges_to_four_triangles():
    m = l_shaped_slab()
    r = merged(m)
    assert m.n_faces == 150 and r.mesh.n_faces == 4
    assert len(used(r.mesh)) == 6
    assert abs(area(r.mesh) - area(m)) <= 1e-9 * area(m)


def test_slab_with_hole_merges_to_eight_triangles():
    m = slab_with_hole()
    r = merged(m)
    assert m.n_faces == 192 and r.mesh.n_faces == 8
    assert len(used(r.mesh)) == 8
    assert abs(area(r.mesh) - area(m)) <= 1e-9 * area(m)


def test_two_slabs_sharing_border_drop_all_nine_shared_vertices():
    m = two_slabs_sharing_border()
    r = merged(m)
    assert m.n_faces == 200 and r.mesh.n_faces == 4
    assert r.report["regions_merged"] == 2 and r.report["regions_skipped"] == {}
    border = [j * 11 + 5 for j in range(1, 10)]
    assert len(border) == 9 and not (set(border) & used(r.mesh))
    assert {11 * 0 + 5, 11 * 10 + 5} <= used(r.mesh)  # the two border ENDS are corners, kept
    assert abs(area(r.mesh) - area(m)) <= 1e-9 * area(m)


def test_wall_foot_on_the_slab_border_survives_and_the_interior_foot_does_not():
    m = slab_with_wall()
    r = merged(m)
    border, foot = 5 * 11, 5 * 11 + 3
    slab = r.mesh.face_v[np.abs(r.mesh.positions[r.mesh.face_v][:, :, 2]).max(axis=1) == 0.0]
    # Hand count, 3 triangles. The slab is one 100x100 square region with no holes, so it
    # triangulates into `n + 2h - 2 = n - 2` triangles over its n surviving RING vertices. The
    # corner pass keeps the 4 square corners, plus (0, 50) -- the wall foot that lies ON the
    # slab's border, which the copied-through wall face still uses. n = 5 -> 3 triangles: the
    # 2 the bare slab would give, plus 1 for that surviving border vertex.
    # The other foot, (30, 50), is INTERIOR to the slab. It is not on any ring, and it needs no
    # shared vertex: the slab surface is continuous beneath it and a perpendicular wall standing
    # on it cannot open a crack. Pinning it would also make the region unexportable as one polygon.
    assert len(slab) == 3
    assert set(int(v) for v in slab.reshape(-1)) == {0, 10, 110, 120, border}
    assert foot in used(r.mesh)  # still used -- by the wall face, not by the slab
    assert "interior_vertices_pinned" not in r.report
    assert abs(area(r.mesh) - area(m)) <= 1e-9 * area(m)


def test_overlapping_triangle_and_the_cells_it_overlaps_are_copied_through():
    m = overlapping_pair()
    r = merged(m)
    copied = {int(s[0]) for s in r.source_faces if len(s) == 1}
    assert copied == {44, 46, 47, 200}
    assert r.report["regions_skipped"] == {}
    assert r.report["regions_merged"] == 1
    assert r.mesh.n_faces == 13


def test_cube_keeps_its_twelve_triangles_and_drops_nothing():
    m = cube()
    r = merged(m)
    assert m.n_faces == 12 and r.mesh.n_faces == 12
    assert r.report["regions_merged"] == 6 and r.report["vertices_dropped"] == 0
    assert used(r.mesh) == set(range(8))
    assert abs(area(r.mesh) - area(m)) <= 1e-9 * area(m)


def test_merge_is_deterministic():
    m = grid_slab(10, 10)
    t = analyse_topology(m)
    a, b = merge_regions(m, t), merge_regions(m, t)
    for field in ("face_v", "face_vt", "face_vn", "face_material", "face_line", "uvs", "normals"):
        assert np.array_equal(getattr(a.mesh, field), getattr(b.mesh, field))
    assert a.report == b.report
    assert [x.tolist() for x in a.source_faces] == [x.tolist() for x in b.source_faces]


def test_positions_are_never_altered():
    m = grid_slab(10, 10)
    before = m.positions.copy()
    r = merged(m)
    assert np.array_equal(r.mesh.positions, before) and np.array_equal(m.positions, before)
    assert len(r.mesh.positions) == len(before)


def test_source_faces_map_every_new_face_back_to_its_region():
    m = grid_slab(10, 10)
    r = merged(m)
    assert len(r.source_faces) == r.mesh.n_faces
    for s in r.source_faces:
        assert s.dtype == np.int64 and len(s) == 200 and s.tolist() == list(range(200))


def offset_slab(du=7.5, dv=-3.25):
    m = grid_slab(10, 10)
    m.uvs = m.uvs + np.array([du, dv])
    return m


def test_new_uv_and_normal_rows_are_appended_not_overwritten():
    m = offset_slab()
    r = merged(m)
    assert np.array_equal(r.mesh.uvs[:len(m.uvs)], m.uvs)
    assert len(r.mesh.uvs) == len(m.uvs) + 4 and len(r.mesh.normals) == 1
    vt = r.mesh.face_vt[r.mesh.face_vt >= 0]
    assert (vt >= len(m.uvs)).all()
    assert np.allclose(r.mesh.normals[0], [0.0, 0.0, 1.0])
    assert (r.mesh.face_vn == 0).all()


def test_patterned_material_keeps_the_fit_offset_flat_material_is_rebased():
    m = offset_slab()
    patterned = merged(m)
    uv = patterned.mesh.uvs[np.unique(patterned.mesh.face_vt)]
    xy = patterned.mesh.positions[np.unique(patterned.mesh.face_v)][:, :2]
    assert np.allclose(np.sort(uv, axis=0), np.sort(xy * 0.05 + [7.5, -3.25], axis=0), atol=1e-9)

    flat = merged(m, frozenset({0}))
    uv = flat.mesh.uvs[np.unique(flat.mesh.face_vt)]
    assert np.allclose(uv.min(axis=0), [0.5, 0.75], atol=1e-9)
    assert flat.mesh.n_faces == 2


def test_merged_mesh_round_trips_through_write_and_read(tmp_path):
    m = slab_with_wall()
    r = merged(m)
    path = tmp_path / "merged.obj"
    write_obj(r.mesh, path)
    back = read_obj(path)
    assert back.n_faces == r.mesh.n_faces == 4  # 3 slab triangles + the copied-through wall face
    assert np.array_equal(back.face_v, r.mesh.face_v)
    assert np.allclose(area(back), area(m))
    # one new vn for the merged region; the copied-through wall face keeps its original -1
    assert len(back.normals) == 1 and np.array_equal(back.face_vn, r.mesh.face_vn)
    assert sorted(set(back.face_vn.reshape(-1).tolist())) == [-1, 0]
    assert np.array_equal(back.face_vt, r.mesh.face_vt)
