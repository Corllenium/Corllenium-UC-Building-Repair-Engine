import numpy as np
import pytest
import shapely

from engine.fixes import merge as merge_module
from engine.fixes.merge import merge_regions
from engine.io.obj_reader import read_obj
from engine.io.obj_writer import write_obj
from engine.pipeline import analyse_topology
from engine.tests.fixtures.build import (arc_topped_strip, cube, frame_with_crossed_seam,
                                         grid_slab, l_shaped_slab, overlapping_pair,
                                         printed_ramp, ramp_fan_region, slab_with_hole,
                                         slab_with_wall, t_junction_lattice_region,
                                         two_slabs_sharing_border,
                                         two_slabs_sharing_curved_border, union_sliver_region)


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

    Simplifying a shared curved border necessarily grows one of the two regions (here by 5.3 sq
    in of 26,460). Rule 9 used to reject any growth beyond `1e-6 * original_area` per region, so
    the right-hand region was fed back and its ring pinned, which pinned the border for its
    neighbour too and shipped the WHOLE border; now it only refuses growth the pass as a whole
    cannot pay for, and the pair keeps the simplification (see
    `test_a_shared_curved_border_is_simplified_on_both_sides`). The invariant below holds either
    way, which is the point: it does not depend on that rule staying as it is."""
    n = 12
    m = two_slabs_sharing_curved_border(n=n)
    topo = analyse_topology(m)
    r = merge_regions(m, topo)

    assert r.report["regions_skipped"] == {} and r.report["converged"] is True
    assert r.mesh.n_faces < m.n_faces          # something really was merged
    assert vertices_inside_an_edge(r.mesh, r.mesh.face_v, sorted(used(r.mesh)),
                                    tol=1.5 * float(topo.quanta.max())) == set()


def test_a_shared_curved_border_is_simplified_on_both_sides():
    """Simplifying a shared border moves area from one region to the other and nowhere else --
    here 5.3 sq in, out of the left slab and into the right -- so the pair's total is unchanged
    and the merge as a whole has not grown. Refusing the right slab on its own for growing (rule
    9 at `1e-6 * original_area`, 4,000x tighter than the boundary movement rule 6 had already
    accepted) fed it back, pinned its whole ring, and so pinned the border for the left slab
    too: 34 triangles shipped where 12 will do."""
    n = 12
    m = two_slabs_sharing_curved_border(n=n)
    topo = analyse_topology(m)
    original_border, _welded = _border_ids(m, topo, n)
    r = merge_regions(m, topo)

    assert r.report["regions_skipped"] == {} and r.report["converged"] is True
    assert r.report["merge_rounds"] == 1            # nothing was fed back
    outers = list({id(v): v["outer"] for v in r.rings.values()}.values())
    assert len(outers) == 2
    kept = [set(int(v) for v in outer) & original_border for outer in outers]
    assert 2 < len(kept[0]) < n, (sorted(kept[0]), n)   # simplified, not flattened to a chord
    assert kept[0] == kept[1], sorted(kept[0] ^ kept[1])
    assert r.mesh.n_faces == sum(len(outer) - 2 for outer in outers) == 12
    assert abs(area(r.mesh) - area(m)) <= 1e-6 * area(m)   # the transfer nets to zero


def test_a_concave_open_border_never_grows_the_mesh():
    """`arc_topped_strip` mirrored: the top edge DIPS, so every chord that replaces a run of arc
    vertices lies outside the original boundary and simplifying can only GROW the region -- by
    6.9 sq in at the ring bound, which rule 6 accepts as boundary movement (far under
    `collinear_tol * perimeter`). It is an OPEN border: no neighbour shrinks to pay for it, so
    the merge as a whole would grow, and `fix_object`'s `area_not_grown` invariant has no guard
    but this one. Whatever a single region is allowed, the shipped mesh may not grow."""
    m = arc_topped_strip(sag=-0.8)
    topo = analyse_topology(m)
    r = merge_regions(m, topo)
    assert r.report["converged"] is True
    assert area(r.mesh) <= area(m) * (1.0 + 1e-6)


def test_an_uncompensated_grower_is_fed_back_and_pins_the_border_for_its_neighbour():
    """The shared-border pair with the right slab's OUTER edge dipping inward as well. The right
    slab now grows twice over: 5.3 sq in across the shared border, which the left slab pays for,
    and 6.9 sq in along its own OPEN edge, which nobody does. The pass as a whole grows, so the
    right slab is fed back and keeps its whole ring -- the shared border with it, so the left
    slab keeps every border vertex too -- and the shipped mesh has not grown. The left slab is
    not fed back: it shrank."""
    n = 12
    m = two_slabs_sharing_curved_border(n=n, outer_sag=0.8)
    topo = analyse_topology(m)
    r = merge_regions(m, topo)

    assert r.report["regions_skipped"] == {} and r.report["converged"] is True
    assert r.report["merge_rounds"] == 2            # one feedback event, then agreement
    outers = list({id(v): v["outer"] for v in r.rings.values()}.values())
    assert sorted(len(outer) for outer in outers) == [2 + n, 2 * n]   # left: border + 2; right: all
    assert area(r.mesh) <= area(m) * (1.0 + 1e-6)


# ------------------------------------------ union rings narrower than any existing vertex pair


def _raw_union_ring_sizes(mesh):
    """Distinct existing vertices each interior ring of the region's grid-snapped union snaps
    to -- the rings exactly as `_union` hands them over, before `_pieces` reads them."""
    topo = analyse_topology(mesh, frozenset())
    members = np.flatnonzero(topo.face_region == 0)
    _normal, origin, basis = merge_module._region_frame(topo.positions_w, topo.face_w, members)
    ids = np.unique(topo.face_w[members])
    xy = (topo.positions_w[ids] - origin) @ basis
    tri = xy[np.searchsorted(ids, topo.face_w[members])]
    union = merge_module._union(shapely.polygons(np.concatenate([tri, tri[:, :1]], axis=1)),
                                merge_module.GRID_SIZE)
    return [len(set(merge_module._nearest_ids(np.asarray(ring.coords)[:-1], xy, ids,
                                               merge_module.SNAP_TOL).tolist()))
            for ring in union.interiors]


def test_union_slivers_narrower_than_snap_tol_close_instead_of_skipping_the_region():
    m = union_sliver_region()
    # precondition: the fixture still reproduces -- its union carries a ring no three existing
    # vertices can bound (if a shapely/GEOS upgrade stops making them, this is what fails)
    assert min(_raw_union_ring_sizes(m)) < 3
    r = merged(m)
    assert r.report["regions_skipped"] == {}
    assert r.report["regions_merged"] == 1 and r.report["faces_copied"] == 0
    loops = r.rings[0]
    assert loops["inners"] == []                       # the slivers closed; they are not holes
    assert r.mesh.n_faces == len(loops["outer"]) - 2   # one hole-free polygon


# A 100 x 100 square region: its 4 corners, a fan centre `p`, the two ends `a`/`b` of an interior
# edge, and a vertex `q` with two lobes `c`/`e` and `d`/`f` beside it. Every "union" below is the
# square minus what a cascaded grid-snapped union can invent: rings one grid cell (1e-4) across.
_SQUARE = np.array([[0.0, 0.0], [100.0, 0.0], [100.0, 100.0], [0.0, 100.0],    # 0-3 corners
                    [50.0, 50.0],                                              # 4 p
                    [30.0, 50.0], [70.0, 50.0],                                # 5 a, 6 b
                    [50.0, 80.0], [60.0, 85.0], [60.0, 95.0],                  # 7 q, 8 c, 9 e
                    [40.0, 85.0], [40.0, 95.0]])                               # 10 d, 11 f
_IDS = np.arange(len(_SQUARE))


def _pieces_of(union):
    return merge_module._pieces(union, _SQUARE, _IDS, merge_module.SNAP_TOL)


def _rings(pieces):
    return [[r.tolist() for r in piece.rings] for piece in pieces]


def test_pieces_closes_a_union_hole_that_snaps_to_one_vertex():
    p = _SQUARE[4]
    one_cell_at_the_fan_centre = [p + (1e-4, 0.0), p + (0.0, 1e-4), p + (-1e-4, 0.0)]
    pieces = _pieces_of(shapely.Polygon(_SQUARE[:4], [one_cell_at_the_fan_centre]))
    assert _rings(pieces) == [[[0, 1, 2, 3]]]
    assert pieces[0].union_area == pytest.approx(10000.0, abs=1e-9)
    assert pieces[0].union_perimeter == pytest.approx(400.0, abs=1e-9)


def test_pieces_closes_a_union_sliver_that_snaps_to_two_vertices():
    a, b = _SQUARE[5], _SQUARE[6]
    one_cell_wide_along_the_edge = [a + (1e-4, 0.0), b + (-1e-4, 1e-4), b + (-1e-4, -1e-4)]
    pieces = _pieces_of(shapely.Polygon(_SQUARE[:4], [one_cell_wide_along_the_edge]))
    assert _rings(pieces) == [[[0, 1, 2, 3]]]
    assert pieces[0].union_area == pytest.approx(10000.0, abs=1e-9)


def test_pieces_splits_a_union_hole_that_revisits_a_vertex_into_its_simple_cycles():
    q, c, e, d, f = _SQUARE[7], _SQUARE[8], _SQUARE[9], _SQUARE[10], _SQUARE[11]
    figure_eight = [q + (1e-4, 0.0), c, e, q + (-1e-4, 0.0), f, d]
    pieces = _pieces_of(shapely.Polygon(_SQUARE[:4], [figure_eight]))
    assert _rings(pieces) == [[[0, 1, 2, 3], [7, 8, 9], [7, 11, 10]]]
    lobes = shapely.Polygon([q, c, e]).area + shapely.Polygon([q, f, d]).area
    # measured on the union's own coordinates, which sit a grid cell off `q`
    assert pieces[0].union_area == pytest.approx(10000.0 - lobes, abs=1e-2)


def test_pieces_drops_the_cycles_of_a_pinched_hole_that_are_too_short_to_be_holes():
    q, c, d = _SQUARE[7], _SQUARE[8], _SQUARE[10]
    bow_tie = [q + (1e-4, 0.0), c, q + (-1e-4, 0.0), d]
    pieces = _pieces_of(shapely.Polygon(_SQUARE[:4], [bow_tie]))
    assert _rings(pieces) == [[[0, 1, 2, 3]]]
    assert pieces[0].union_area == pytest.approx(10000.0, abs=1e-9)


def test_pieces_drops_a_union_island_narrower_than_snap_tol():
    corner = _SQUARE[2]
    one_cell = [corner + (1e-4, 1e-4), corner + (2e-4, 1e-4), corner + (1e-4, 2e-4)]
    union = shapely.MultiPolygon([shapely.Polygon(_SQUARE[:4]), shapely.Polygon(one_cell)])
    assert _rings(_pieces_of(union)) == [[[0, 1, 2, 3]]]


def test_pieces_removes_a_spike_the_outer_ring_makes_to_a_vertex_and_back():
    corner, p = _SQUARE[1], _SQUARE[4]
    spiked = [_SQUARE[0], corner + (-1e-4, 0.0), p + (0.0, 1e-4), corner + (0.0, 1e-4),
              _SQUARE[2], _SQUARE[3]]
    pieces = _pieces_of(shapely.Polygon(spiked))
    assert _rings(pieces) == [[[0, 1, 2, 3]]]
    assert pieces[0].union_area == pytest.approx(10000.0, abs=1e-2)   # the corner sits a cell off


def test_pieces_rejects_an_outer_ring_pinched_into_two_lobes():
    p = _SQUARE[4]
    bow_tie = [_SQUARE[0], _SQUARE[1], p + (1e-4, 0.0), _SQUARE[2], _SQUARE[3], p + (-1e-4, 0.0)]
    assert _pieces_of(shapely.Polygon(bow_tie)) == []


# ------------------------------------------- N1: the snap tolerance is the region's own thickness
# A union corner the grid snapped off its vertex is read as that vertex when it lies within the
# region's THICKNESS -- the spread of its vertices along its own normal -- clamped to
# [SNAP_TOL, SNAP_TOL_MAX]. See `engine.fixes.merge.snap_tolerance` for the measurement.


def _projected(mesh, region=0):
    """`(topo, members, vertex_ids, vertex_xy, thickness)` of one region, projected exactly as the
    merge projects it; the thickness is measured here from first principles."""
    topo = analyse_topology(mesh, frozenset())
    members = np.flatnonzero(topo.face_region == region)
    normal, origin, basis = merge_module._region_frame(topo.positions_w, topo.face_w, members)
    ids = np.unique(topo.face_w[members])
    offsets = (topo.positions_w[ids] - origin) @ normal
    return topo, members, ids, (topo.positions_w[ids] - origin) @ basis, float(np.ptp(offsets))


def _real_union(topo, members, ids, xy):
    tri = xy[np.searchsorted(ids, topo.face_w[members])]
    return merge_module._union(shapely.polygons(np.concatenate([tri, tri[:, :1]], axis=1)),
                               merge_module.GRID_SIZE)


def _corner_moved(union, distance):
    """`union` with its first outer ring coordinate moved `distance` inches along the ring
    towards the next one -- a corner the grid left off its vertex, the way the union leaves one
    at the apex of a narrow fan (0.0016 in on file B's ramp)."""
    ring = np.asarray(union.exterior.coords)[:-1].copy()
    step = ring[1] - ring[0]
    ring[0] = ring[0] + distance * step / np.linalg.norm(step)
    return shapely.Polygon(ring, [r.coords for r in union.interiors])


def test_snap_tolerance_is_the_thickness_clamped_between_floor_and_ceiling():
    assert merge_module.SNAP_TOL == 1e-3 and merge_module.SNAP_TOL_MAX == 1e-2
    assert merge_module.snap_tolerance(0.0) == merge_module.SNAP_TOL
    assert merge_module.snap_tolerance(0.0085) == 0.0085
    assert merge_module.snap_tolerance(0.11) == merge_module.SNAP_TOL_MAX
    assert merge_module.snap_tolerance(0.0, floor=2e-3) == 2e-3


def test_each_region_is_planned_with_its_own_thickness_as_snap_tolerance():
    for mesh, expected in ((grid_slab(10, 10), 0.0), (printed_ramp(), None)):
        topo, members, ids, xy, thickness = _projected(mesh)
        if expected is not None:
            assert thickness == expected      # axis-aligned: exactly flat
        else:
            assert thickness == pytest.approx(0.0046, abs=5e-5)   # rounded Z scatters it
        plans, _copied, _skipped = merge_module._plan_regions(topo, merge_module.GRID_SIZE,
                                                              merge_module.SNAP_TOL)
        assert len(plans) == 1
        assert plans[0].snap_tol == merge_module.snap_tolerance(thickness)


def test_a_union_corner_within_the_regions_thickness_of_its_vertex_merges(monkeypatch):
    """The ramp is 0.0046 in thick; the union's corner lands 0.0016 in off its vertex, as it did
    at the apex of file B's ramp fan. The region used to be copied through whole as
    `new_vertex`; the corner is its vertex, so the region merges to its 2 triangles."""
    m = printed_ramp()
    topo = analyse_topology(m, frozenset())
    real = merge_module._union
    monkeypatch.setattr(merge_module, "_union",
                        lambda polys, grid_size: _corner_moved(real(polys, grid_size), 0.0016))
    r = merge_regions(m, topo)
    assert r.report["regions_skipped"] == {} and r.report["regions_merged"] == 1
    assert r.report["faces_copied"] == 0 and r.mesh.n_faces == 2
    assert abs(area(r.mesh) - area(m)) <= 1e-6 * area(m)


def test_a_union_corner_half_an_inch_from_every_vertex_never_snaps():
    """0.5 in is fifty times the ceiling: no region is thick enough to read it as a vertex."""
    topo, members, ids, xy, thickness = _projected(printed_ramp())
    union = _real_union(topo, members, ids, xy)
    tol = merge_module.snap_tolerance(thickness)
    exact = merge_module._pieces(union, xy, ids, tol)
    near = merge_module._pieces(_corner_moved(union, 0.0016), xy, ids, tol)
    assert _rings(near) == _rings(exact)                       # 0.0016 in: the same vertex
    far = _corner_moved(union, 0.5)
    assert merge_module._pieces(far, xy, ids, tol) is None
    assert merge_module._pieces(far, xy, ids, merge_module.SNAP_TOL_MAX) is None


def test_an_exactly_flat_region_keeps_the_floor():
    """An axis-aligned region projects its vertices onto the union's grid, so its union never
    leaves a corner off one (measured: within 3e-12 in on every such region of both files); the
    same 0.0016 in corner on it is not read as a vertex."""
    topo, members, ids, xy, thickness = _projected(grid_slab(10, 10))
    assert thickness == 0.0
    union = _corner_moved(_real_union(topo, members, ids, xy), 0.0016)
    assert merge_module._pieces(union, xy, ids, merge_module.snap_tolerance(thickness)) is None


# --------------------------- N2: a union corner no vertex can explain sets aside only its makers
# The grid-snapped union leaves SLIVERS along T-junction lines -- a vertex lying exactly on the
# edge of a neighbouring triangle, the two sides snapped a grid cell apart and crossing again at
# a vanishing angle, anywhere along the line: 7.87 in from every vertex on file A. A ring
# narrower than two grid cells is closed whatever its corners snap to. A corner that is still no
# vertex's sets aside the triangles whose boundary passes within the snap tolerance of it, like
# rule 3's overlap exclusions, and the rest of the region is unioned again.


def _merge_union(mesh, region=0):
    """The region's union exactly as the merge builds it (rule 3 applied), with its projection."""
    topo, members, ids, xy, thickness = _projected(mesh, region)
    tri = xy[np.searchsorted(ids, topo.face_w[members])]
    polys = shapely.polygons(np.concatenate([tri, tri[:, :1]], axis=1))
    keep = ~merge_module._overlap_excluded(polys, shapely.area(polys))
    return merge_module._union(polys[keep], merge_module.GRID_SIZE), ids, xy, thickness


def _ring_report(union, ids, xy):
    """`(kind, farthest distance to a vertex, distinct vertices snapped to)` per union ring."""
    out = []
    for poly in merge_module._polygons(union):
        for kind, ring in [("outer", poly.exterior)] + [("hole", r) for r in poly.interiors]:
            c = np.asarray(ring.coords)[:-1]
            d = np.linalg.norm(c[:, None, :] - xy[None, :, :], axis=2)
            out.append((kind, float(d.min(axis=1).max()), len(set(ids[d.argmin(axis=1)].tolist()))))
    return out


def test_pieces_closes_a_hole_thinner_than_two_grid_cells_whose_corner_no_vertex_explains():
    a, b = _SQUARE[5], _SQUARE[6]                  # (30, 50) and (70, 50)
    crossing = (40.0, 50.0 + 1e-4)                 # 10 in from every vertex, a grid cell off the line
    pieces = _pieces_of(shapely.Polygon(_SQUARE[:4], [[a, crossing, b]]))
    assert pieces is not None and _rings(pieces) == [[[0, 1, 2, 3]]]


def test_pieces_closes_a_hole_thinner_than_two_grid_cells_even_when_three_vertices_bound_it():
    a, p, b = _SQUARE[5], _SQUARE[4], _SQUARE[6]   # three collinear vertices on y = 50
    pieces = _pieces_of(shapely.Polygon(_SQUARE[:4], [[a, p + (0.0, 1e-4), b]]))
    assert _rings(pieces) == [[[0, 1, 2, 3]]]      # not a zero-width hole [5, 4, 6]


def test_pieces_keeps_a_hole_one_print_step_wide():
    """0.01 in -- one X/Z print step -- is a hundred grid cells: an opening, not a sliver."""
    xy = np.vstack([_SQUARE, [[30.0, 50.01]]])
    pieces = merge_module._pieces(shapely.Polygon(_SQUARE[:4], [[xy[5], xy[6], xy[12]]]), xy,
                                  np.arange(len(xy)), merge_module.SNAP_TOL)
    assert _rings(pieces) == [[[0, 1, 2, 3], [5, 6, 12]]]


def test_pieces_drops_an_island_thinner_than_two_grid_cells_whatever_its_corners_snap_to():
    top_left, top_right = _SQUARE[3], _SQUARE[2]
    island = [top_left + (0.0, 1e-4), (50.0, 100.0 + 2e-4), top_right + (0.0, 1e-4)]
    union = shapely.MultiPolygon([shapely.Polygon(_SQUARE[:4]), shapely.Polygon(island)])
    pieces = _pieces_of(union)
    assert pieces is not None and _rings(pieces) == [[[0, 1, 2, 3]]]


def test_the_t_junction_lattice_of_file_a_merges_whole():
    """File A's big sloped underside: 274 triangles copied through as `new_vertex`, the lattice
    the owner saw. Its slivers close, its 12 real openings stay, nothing is set aside."""
    m = t_junction_lattice_region()
    union, ids, xy, _thickness = _merge_union(m)
    rings = _ring_report(union, ids, xy)
    # precondition: the union still has the corner 7.87 in from every vertex and its 3 slivers
    # beside the 12 openings (if a shapely/GEOS upgrade stops making them, this is what fails)
    assert max(d for _kind, d, _n in rings) == pytest.approx(7.868, abs=1e-3)
    assert len([ring for ring in rings if ring[0] == "hole"]) == 15
    r = merged(m)
    assert r.report["regions_skipped"] == {} and r.report["regions_merged"] == 1
    assert r.report["new_vertex_triangles_set_aside"] == 0
    assert r.report["faces_copied"] == 4                    # rule 3's four overlapping triangles
    loops = next(iter(r.rings.values()))
    assert len(loops["inners"]) == 12
    assert area(r.mesh) <= area(m) * (1.0 + 1e-6)
    before = vertices_inside_an_edge(m, m.face_v, used(m), tol=1e-6)
    assert vertices_inside_an_edge(r.mesh, r.mesh.face_v, used(r.mesh), tol=1e-6) <= before


def test_the_ramp_of_file_b_merges_as_one_polygon():
    """File B's ramp: its 0.0016 in apex tip snaps (N1), and its two T-junction slivers, which
    snap to 3 and 4 distinct collinear vertices, close instead of making the polygon invalid."""
    m = ramp_fan_region()
    union, ids, xy, thickness = _merge_union(m)
    rings = _ring_report(union, ids, xy)
    assert sorted(n for kind, _d, n in rings if kind == "hole") == [1, 3, 4]   # precondition
    assert max(d for _kind, d, _n in rings) == pytest.approx(0.0016, abs=1e-4)
    assert thickness == pytest.approx(0.0085, abs=1e-4)
    r = merged(m)
    assert r.report["regions_skipped"] == {} and r.report["regions_merged"] == 1
    assert r.report["faces_copied"] == 0 and r.report["new_vertex_triangles_set_aside"] == 0
    loops = r.rings[0]
    assert loops["inners"] == [] and r.mesh.n_faces == len(loops["outer"]) - 2


def test_a_triangle_whose_edge_crosses_a_neighbours_is_set_aside_and_the_rest_merges():
    m = frame_with_crossed_seam()
    union, ids, xy, _thickness = _merge_union(m)
    assert max(d for _kind, d, _n in _ring_report(union, ids, xy)) == pytest.approx(50.0, abs=1e-3)
    r = merged(m)
    assert r.report["regions_skipped"] == {} and r.report["regions_merged"] == 1
    assert r.report["new_vertex_triangles_set_aside"] == 2
    assert sorted(int(s[0]) for s in r.source_faces if len(s) == 1) == [0, 3]   # the seam pair
    assert r.report["faces_copied"] == 2
    assert abs(area(r.mesh) - area(m)) <= 1e-6 * area(m)
    # no T-junction opens: the only vertices inside another triangle's edge are the two the
    # input already had there
    before = vertices_inside_an_edge(m, m.face_v, used(m))
    assert before == {9, 11}
    assert vertices_inside_an_edge(r.mesh, r.mesh.face_v, used(r.mesh)) <= before


def test_setting_triangles_aside_is_deterministic():
    m = frame_with_crossed_seam()
    t = analyse_topology(m, frozenset())
    a, b = merge_regions(m, t), merge_regions(m, t)
    for name in ("face_v", "face_vt", "face_vn", "face_material", "face_line", "uvs", "normals"):
        assert np.array_equal(getattr(a.mesh, name), getattr(b.mesh, name))
    assert a.report == b.report
    assert [x.tolist() for x in a.source_faces] == [x.tolist() for x in b.source_faces]
    assert np.array_equal(a.face_region, b.face_region)


def test_a_region_is_given_up_whole_when_its_corner_outlasts_the_bounded_rounds(monkeypatch):
    """With no round allowed the frame is given up exactly as before: every triangle copied, one
    `new_vertex` skip, nothing counted as set aside -- `regions_skipped` counts whole regions."""
    monkeypatch.setattr(merge_module, "MAX_SET_ASIDE_ROUNDS", 0)
    r = merged(frame_with_crossed_seam())
    assert r.report["regions_skipped"] == {"new_vertex": 1}
    assert r.report["new_vertex_triangles_set_aside"] == 0 and r.report["faces_copied"] == 10


def test_region_outline_sets_aside_the_same_triangles_as_the_merge():
    """Solidify hangs its skirts on `region_outline`, which must stay the merge's own outline."""
    topo = analyse_topology(frame_with_crossed_seam(), frozenset())
    members = np.flatnonzero(topo.face_region == 0)
    outline = merge_module.region_outline(topo, members)
    plans, _copied, _skipped = merge_module._plan_regions(topo, merge_module.GRID_SIZE,
                                                          merge_module.SNAP_TOL)
    assert outline is not None and len(plans) == 1
    assert _rings(outline[0]) == _rings(plans[0].pieces)
    assert sorted(plans[0].set_aside.tolist()) == [0, 3]


def test_an_ordinary_merge_sets_nothing_aside():
    r = merged(grid_slab(10, 10))
    assert r.report["new_vertex_triangles_set_aside"] == 0
