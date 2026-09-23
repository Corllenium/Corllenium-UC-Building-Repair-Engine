import numpy as np
import pytest

from engine.fixes import merge as merge_module
from engine.fixes.merge import merge_regions
from engine.io.obj_reader import read_obj
from engine.io.obj_writer import write_obj
from engine.pipeline import analyse_topology
from engine.tests.fixtures.build import (arc_topped_strip, cube, grid_slab, l_shaped_slab,
                                         overlapping_pair, slab_with_hole, slab_with_wall,
                                         two_slabs_sharing_border,
                                         two_slabs_sharing_curved_border)


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
# Task 9 / M2: MergeResult.rings -- every merged single-piece region's kept loops, for the
# polygon (ngon) and SketchUp exports. Keyed by OUTPUT face row index in r.mesh.face_v; every row
# of the SAME region shares the identical {"outer": ..., "inners": [...]} dict object, so a
# writer can dedup by identity. A region WITH holes has an entry too (M2) -- the ngon writer just
# keeps triangles for it.
# ---------------------------------------------------------------------------------------------

def test_grid_slab_rings_is_one_shared_four_vertex_ring_for_both_output_triangles():
    m = grid_slab(10, 10)
    r = merged(m)
    assert r.mesh.n_faces == 2
    assert set(r.rings.keys()) == {0, 1}
    ring0, ring1 = r.rings[0], r.rings[1]
    assert ring0 is ring1  # same region -> same ring object, for a writer to dedup by identity
    assert len(ring0["outer"]) == 4
    assert ring0["inners"] == []
    assert set(int(v) for v in ring0["outer"]) == used(r.mesh)  # the 4 surviving corners


def test_slab_with_hole_rings_has_an_outer_loop_and_one_inner_loop_of_four():
    """M2: a holed region is no longer left out. It gets its loops like any other single-piece
    region -- the OBJ export just keeps triangles for it (see test_obj_writer)."""
    m = slab_with_hole()
    r = merged(m)
    assert r.mesh.n_faces == 8
    assert set(r.rings.keys()) == set(range(8))
    ring = r.rings[0]
    assert all(r.rings[i] is ring for i in range(8))
    assert len(ring["outer"]) == 4
    assert len(ring["inners"]) == 1 and len(ring["inners"][0]) == 4
    assert set(int(v) for v in ring["outer"]).isdisjoint(set(int(v) for v in ring["inners"][0]))


def test_inner_loops_are_wound_opposite_to_the_outer_loop():
    """Outer CCW as seen from the region's outward side, holes CW -- the convention every
    polygon consumer (SketchUp included) expects, so a hole reads as a hole."""
    m = slab_with_hole()
    ring = merged(m).rings[0]
    xy = lambda ids: m.positions[np.asarray(ids)][:, :2]
    signed = lambda p: float(np.sum(p[:, 0] * np.roll(p[:, 1], -1) - np.roll(p[:, 0], -1) * p[:, 1]))
    assert signed(xy(ring["outer"])) > 0.0
    assert signed(xy(ring["inners"][0])) < 0.0


def test_two_slabs_sharing_border_rings_are_two_distinct_four_vertex_rings():
    m = two_slabs_sharing_border()
    r = merged(m)
    assert r.mesh.n_faces == 4
    assert set(r.rings.keys()) == {0, 1, 2, 3}
    left_ring, right_ring = r.rings[0], r.rings[2]
    assert left_ring is r.rings[1] and right_ring is r.rings[3]
    assert left_ring is not right_ring
    assert len(left_ring["outer"]) == 4 and len(right_ring["outer"]) == 4
    assert left_ring["inners"] == [] and right_ring["inners"] == []
    assert set(int(v) for v in left_ring["outer"]) != set(int(v) for v in right_ring["outer"])


def test_ring_vertex_ids_index_into_mesh_positions_like_face_v_does():
    """Rings hold ORIGINAL-mesh vertex ids (via welded_to_original), exactly like face_v -- not
    welded ids -- so a writer can use them directly against mesh.positions."""
    m = grid_slab(10, 10)
    r = merged(m)
    ring = r.rings[0]["outer"]
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


# ---------------------------------------------------------------------------------------------
# M3: ring simplification with a GLOBAL deviation bound. The corner pass used to test each ring
# vertex against the chord of its own two neighbours, so a run of nearly-collinear vertices could
# be dropped one after another and the surviving chord end up far outside the bound the guard's
# ring test assumes. Ramer-Douglas-Peucker drops a vertex only when the WHOLE original polyline
# between its surviving neighbours stays inside the bound.
# ---------------------------------------------------------------------------------------------

def _neighbour_deviation(xy: np.ndarray) -> np.ndarray:
    """Distance of each interior point of an open polyline from the chord of its own neighbours."""
    return np.array([_point_to_segment(xy[k], xy[k - 1], xy[k + 1]) for k in range(1, len(xy) - 1)])


def _point_to_segment(p, a, b) -> float:
    ab = np.asarray(b, float) - np.asarray(a, float)
    denom = float(ab @ ab)
    if denom == 0.0:
        return float(np.linalg.norm(np.asarray(p, float) - a))
    t = float(np.clip((np.asarray(p, float) - a) @ ab / denom, 0.0, 1.0))
    return float(np.linalg.norm(np.asarray(p, float) - (a + t * ab)))


def _deviation_from_ring(points: np.ndarray, ring_xy: np.ndarray) -> float:
    """The worst distance from any of `points` to the CLOSED polyline `ring_xy`."""
    return max(min(_point_to_segment(p, ring_xy[k - 1], ring_xy[k]) for k in range(len(ring_xy)))
               for p in points)


def test_arc_ring_stays_within_the_bound_instead_of_drifting_off_it():
    m = arc_topped_strip()
    topo = analyse_topology(m)
    tol = 1.5 * float(topo.quanta.max())
    assert tol == pytest.approx(0.15)

    top = m.positions[12:][:, [0, 2]]          # the 12 arc vertices, in the region's own plane
    # Every arc vertex is well inside the bound of its OWN neighbours' chord ...
    assert _neighbour_deviation(top).max() == pytest.approx(0.0267, abs=5e-4)
    assert _neighbour_deviation(top).max() < tol
    # ... and yet the arc as a whole is 0.8 off the chord between its two ends, 5x the bound.
    ends = np.array([_point_to_segment(p, top[0], top[-1]) for p in top])
    assert ends.max() == pytest.approx(0.8, abs=1e-3) and ends.max() > tol

    # At THAT bound the per-vertex rule calls every arc vertex collinear (each is 0.027 < 0.15
    # from its own neighbours' chord) and proposes the four sharp corners -- a boundary 0.8 in
    # off the original, which loses 118 sq in of area, more than `_triangulate` allows, so the
    # region falls back to keeping ALL 24 ring vertices and simplifies nothing at all.
    r = merge_regions(m, topo, collinear_tol=tol)
    ring = r.rings[0]["outer"]
    assert 4 < len(ring) < 24      # simplified, but NOT collapsed onto the four sharp corners
    ring_xy = m.positions[ring][:, [0, 2]]
    original = m.positions[np.unique(m.face_v)][:, [0, 2]]
    assert _deviation_from_ring(original, ring_xy) <= tol


def test_ring_bound_defaults_to_one_and_a_half_axis_quanta():
    """The bound is the mesh's own print precision, not a fixed 1e-3 in: asking for
    `1.5 * max(q)` explicitly must give exactly what the default gives."""
    m = arc_topped_strip()
    topo = analyse_topology(m)
    explicit = merge_regions(m, topo, collinear_tol=1.5 * float(topo.quanta.max()))
    default = merge_regions(m, topo)
    assert np.array_equal(default.rings[0]["outer"], explicit.rings[0]["outer"])
    assert default.mesh.n_faces == explicit.mesh.n_faces


# ---------------------------------------------------------------------------------------------
# MQ2: two regions sharing a CURVED border. Ramer-Douglas-Peucker is not local -- what it keeps
# along a stretch depends on that stretch's endpoints -- so two regions only stay in step if they
# simplify a shared stretch between the SAME anchors. `_divergent_vertices` is what guarantees
# that; this is its regression test on a border where RDP actually has a choice to make.
#
# The check runs at the simplification bound, not at 1e-9: a vertex dropped from a CURVED border
# is not on the chord that replaces it, so a T-junction here is a crack up to `collinear_tol`
# wide, which an exact on-the-segment test would miss entirely.
# ---------------------------------------------------------------------------------------------

def _border_ids(mesh, topo, n):
    """The shared border's vertices as `(original ids, welded ids)`. The fixture emits them as
    original rows `n .. 2n-1`; `weld_exact` reorders, so the welded ids are looked up, not
    assumed."""
    from engine.topo.weld import weld_exact
    _, remap = weld_exact(mesh.positions, mesh.coord_decimals)
    return set(range(n, 2 * n)), set(int(w) for w in remap[n:2 * n])


def test_two_regions_keep_the_same_vertices_of_a_shared_curved_border():
    """The global corner pass decides ring membership for every region at once. Both rings must
    come out of it holding the SAME subset of the shared border -- a proper subset, or the fixture
    would prove nothing."""
    n = 12
    m = two_slabs_sharing_curved_border(n=n)
    topo = analyse_topology(m)
    collinear_tol = 1.5 * float(topo.quanta.max())
    _original, welded = _border_ids(m, topo, n)

    plans, copied, _skipped = merge_module._plan_regions(topo, merge_module.GRID_SIZE,
                                                        merge_module.SNAP_TOL)
    assert len(plans) == 2
    needed = merge_module._needed_vertices(topo, copied, plans, collinear_tol, set())

    kept = []
    for plan in plans:
        ring = plan.pieces[0].rings[0]
        kept.append({int(v) for v in ring[needed[ring]]} & welded)
    assert 2 < len(kept[0]) < n, (sorted(kept[0]), n)   # simplified, and not flattened to a chord
    assert kept[0] == kept[1], sorted(kept[0] ^ kept[1])


def test_a_shared_curved_border_opens_no_t_junction_in_the_shipped_mesh():
    """End to end: whatever the feedback loop does with these two regions, no vertex of the
    shipped mesh may end up inside another triangle's edge.

    On this fixture the shipped mesh keeps the WHOLE border, because simplifying a shared curved
    border necessarily grows one of the two regions (here by 5.3 sq in of 26,460) and rule 9
    rejects any growth beyond `1e-6 * original_area` -- so the right-hand region is fed back and
    its ring is pinned, which pins the border for its neighbour too. The invariant below holds
    either way, which is the point: it does not depend on that rule staying as it is."""
    n = 12
    m = two_slabs_sharing_curved_border(n=n)
    topo = analyse_topology(m)
    r = merge_regions(m, topo)

    assert r.report["regions_skipped"] == {} and r.report["converged"] is True
    assert r.mesh.n_faces < m.n_faces          # something really was merged
    assert vertices_inside_an_edge(r.mesh, r.mesh.face_v, sorted(used(r.mesh)),
                                    tol=1.5 * float(topo.quanta.max())) == set()
