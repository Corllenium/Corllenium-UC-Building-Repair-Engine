import numpy as np

from engine.fixes import merge as merge_module
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


def vertices_inside_an_edge(mesh, faces, candidates, tol=1e-9):
    """Every vertex of `candidates` that lies STRICTLY inside an edge of `faces` without being one
    of that edge's endpoints -- i.e. every T-junction `faces` would open against `candidates`."""
    out = set()
    p = mesh.positions
    for triangle in faces:
        for a, b in ((0, 1), (1, 2), (2, 0)):
            start, end = p[triangle[a]], p[triangle[b]]
            seg = end - start
            length2 = float(seg @ seg)
            for v in candidates:
                if v in (int(triangle[a]), int(triangle[b])):
                    continue
                along = float((p[v] - start) @ seg) / length2
                if 0.0 < along < 1.0 and np.linalg.norm(p[v] - start - along * seg) <= tol:
                    out.add(int(v))
    return out


def test_merge_rounds_is_one_when_no_region_skips_late():
    r = merged(grid_slab(10, 10))
    assert r.report["merge_rounds"] == 1
    assert r.report["converged"] is True


def _left_slab_fails_late(monkeypatch, mesh, topo):
    """Force the LEFT region of `two_slabs_sharing_border()` to fail AFTER the corner pass, as
    rules 6/7/9 do -- a feedback event that takes a second round to settle."""
    bad = int(topo.face_region[0])  # face 0 is cell (0, 0): the LEFT slab, material 0
    real = merge_module._triangulate

    def fails_late(plan, needed, collinear_tol):
        if plan.region == bad:
            return None, "invalid_polygon"
        return real(plan, needed, collinear_tol)

    monkeypatch.setattr(merge_module, "_triangulate", fails_late)


def test_converged_is_false_when_max_rounds_cuts_the_loop_short(monkeypatch):
    """Hitting `MAX_ROUNDS` must not look like agreement: the last round's feedback was never
    fed back, so a neighbour may still be holding a T-junction open."""
    m = two_slabs_sharing_border()
    topo = analyse_topology(m)
    _left_slab_fails_late(monkeypatch, m, topo)

    monkeypatch.setattr(merge_module, "MAX_ROUNDS", 1)
    cut_short = merge_regions(m, topo)
    assert cut_short.report["merge_rounds"] == 1
    assert cut_short.report["converged"] is False

    monkeypatch.setattr(merge_module, "MAX_ROUNDS", 10)
    settled = merge_regions(m, topo)  # the same case needs 2 rounds and does converge
    assert settled.report["merge_rounds"] == 2
    assert settled.report["converged"] is True


def test_late_skipped_region_feeds_its_vertices_back_into_the_corner_pass(monkeypatch):
    m = two_slabs_sharing_border()
    topo = analyse_topology(m)
    bad = int(topo.face_region[0])  # face 0 is cell (0, 0): the LEFT slab, material 0
    real = merge_module._triangulate

    def fails_late(plan, needed, collinear_tol):
        """The left slab always fails AFTER the global corner pass, as rules 6/7/9 do."""
        if plan.region == bad:
            return None, "invalid_polygon"
        return real(plan, needed, collinear_tol)

    monkeypatch.setattr(merge_module, "_triangulate", fails_late)
    r = merge_regions(m, topo)

    assert r.report["regions_skipped"] == {"invalid_polygon": 1}
    assert r.report["merge_rounds"] == 2  # round 1 finds the skip, round 2 confirms nothing new
    border = [j * 11 + 5 for j in range(1, 10)]  # the 9 collinear shared-border vertices
    right = r.mesh.face_v[r.mesh.face_material == 1]
    left = r.mesh.face_v[r.mesh.face_material == 0]
    assert len(left) == 100  # the whole left slab copied through, untouched
    # the left slab kept all its vertices, so the right slab must keep every one it shares:
    # 4 corners + 9 border vertices -> 13 + 0 - 2 = 11 triangles
    assert set(border) <= set(int(v) for v in right.reshape(-1))
    assert len(right) == 11
    assert vertices_inside_an_edge(r.mesh, right, set(int(v) for v in left.reshape(-1))) == set()


def test_keep_all_fallback_feeds_its_ring_vertices_back_into_the_corner_pass(monkeypatch):
    """A `keep_all` success keeps EVERY ring vertex of its region, so it is a feedback event
    exactly like a late skip: its neighbours must keep the border vertices they share with it, or
    those vertices land strictly inside a neighbour's edge -- a T-junction."""
    m = two_slabs_sharing_border()
    topo = analyse_topology(m)
    bad = int(topo.face_region[0])  # face 0 is cell (0, 0): the LEFT slab, material 0
    real = merge_module._polygon

    def invalid_when_simplified(plan, rings):
        """The LEFT region's SIMPLIFIED polygon is always invalid, as rule 6 sees it; its FULL
        ring still builds, so the region lands on the `keep_all` fallback and is accepted."""
        full = sum(len(r) for piece in plan.pieces for r in piece.rings)
        if plan.region == bad and sum(len(r) for r in rings) < full:
            return None
        return real(plan, rings)

    monkeypatch.setattr(merge_module, "_polygon", invalid_when_simplified)
    r = merge_regions(m, topo)

    assert r.report["keep_all_regions"] == 1
    assert r.report["regions_merged"] == 2 and r.report["regions_skipped"] == {}
    assert r.report["merge_rounds"] == 2  # round 1 finds the keep_all, round 2 confirms nothing new

    left = r.mesh.face_v[r.mesh.face_material == 0]
    right = r.mesh.face_v[r.mesh.face_material == 1]
    # the left slab kept all 2*(5+10) = 30 ring vertices -> 30 + 0 - 2 = 28 triangles
    assert len(left) == 28
    border = [j * 11 + 5 for j in range(1, 10)]  # the 9 collinear shared-border vertices
    assert set(border) <= set(int(v) for v in right.reshape(-1))
    assert len(right) == 11  # 4 corners + 9 border vertices -> 13 + 0 - 2 = 11
    assert vertices_inside_an_edge(r.mesh, right, set(int(v) for v in left.reshape(-1))) == set()
    assert vertices_inside_an_edge(r.mesh, left, set(int(v) for v in right.reshape(-1))) == set()


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


# ---------------------------------------------------------------------------------------------
# Task 9: MergeResult.rings -- per hole-free merged region's kept outer ring, for the polygon
# (ngon) export. Keyed by OUTPUT face row index in r.mesh.face_v; every row of the SAME region
# shares the identical ring array object, so a writer can dedup by identity.
# ---------------------------------------------------------------------------------------------

def test_grid_slab_rings_is_one_shared_four_vertex_ring_for_both_output_triangles():
    m = grid_slab(10, 10)
    r = merged(m)
    assert r.mesh.n_faces == 2
    assert set(r.rings.keys()) == {0, 1}
    ring0, ring1 = r.rings[0], r.rings[1]
    assert ring0 is ring1  # same region -> same ring object, for a writer to dedup by identity
    assert len(ring0) == 4
    assert set(int(v) for v in ring0) == used(r.mesh)  # the 4 surviving corners


def test_slab_with_hole_rings_is_empty():
    m = slab_with_hole()
    r = merged(m)
    assert r.mesh.n_faces == 8
    assert r.rings == {}


def test_two_slabs_sharing_border_rings_are_two_distinct_four_vertex_rings():
    m = two_slabs_sharing_border()
    r = merged(m)
    assert r.mesh.n_faces == 4
    assert set(r.rings.keys()) == {0, 1, 2, 3}
    left_ring, right_ring = r.rings[0], r.rings[2]
    assert left_ring is r.rings[1] and right_ring is r.rings[3]
    assert left_ring is not right_ring
    assert len(left_ring) == 4 and len(right_ring) == 4
    assert set(int(v) for v in left_ring) != set(int(v) for v in right_ring)


def test_ring_vertex_ids_index_into_mesh_positions_like_face_v_does():
    """Rings hold ORIGINAL-mesh vertex ids (via welded_to_original), exactly like face_v -- not
    welded ids -- so a writer can use them directly against mesh.positions."""
    m = grid_slab(10, 10)
    r = merged(m)
    ring = r.rings[0]
    assert ring.dtype == np.int64
    assert int(ring.max()) < len(m.positions)


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
