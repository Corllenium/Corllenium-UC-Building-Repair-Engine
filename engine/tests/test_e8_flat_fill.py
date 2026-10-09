"""Job P2-E8b: the narrow flat fill (`engine.repair.engines.e8_fill.E8FlatFill`), the owner's one exception to "no hole
filling" (AGENTS.md section 4, 2026-10-03).

A hole whose whole border lies in one plane matching the neighbouring surface may be filled using existing points only.
The rulings E8b-R1..R5 of the brief: a candidate is one simple closed loop of open edges with no inner loop (R1); its
points lie within 2 print steps of their least-squares plane and every face along it is coplanar with it (normal within
1 degree up to sign, in the plane within that tolerance) (R2); its largest inscribed circle is at most 39.37 in across
(R3); its neighbours have one look and one affine UV map fits them within 1e-3 (R4); the fill is ear-clipped on the
loop's own points: n - 2 triangles, no new point, an E8 "add" (R5). Every refused loop is listed with its reason.
"""
from __future__ import annotations

import numpy as np
import pytest

from engine.fixes.pipeline import FixProfile
from engine.pipeline import analyse_topology
from engine.repair.engines.e8_fill import FILL_MAX_DIAMETER, E8FlatFill, ear_clip
from engine.repair.types import RepairContext, UnitState, apply_edits
from engine.tests.fixtures.holes import holed_slab, square_hole_slab
from engine.topo.edges import EDGE_OPEN


def _plan(mesh, looks=None):
    engine = E8FlatFill()
    unit = UnitState(mesh=mesh, topo=None, looks=looks or {}, viewpoints=None)
    edits = engine.plan(unit, RepairContext(profile=FixProfile(), decider=None, validator=None))
    return engine, edits


def _open_edges(mesh) -> int:
    return int((np.asarray(analyse_topology(mesh).edge_class) == EDGE_OPEN).sum())


def _tri_normals(mesh, faces):
    tri = mesh.positions[np.asarray(faces)]
    n = np.cross(tri[:, 1] - tri[:, 0], tri[:, 2] - tri[:, 0])
    return n, 0.5 * np.linalg.norm(n, axis=1)


# ------------------------------------------------------------------------------------------- item 1: one fill


def test_the_engine_is_a_non_legacy_stage_named_e8b_whose_edits_are_e8():
    engine = E8FlatFill()
    assert engine.name == "E8b" and engine.legacy is False
    assert FILL_MAX_DIAMETER == pytest.approx(39.37)


def test_a_square_hole_in_a_flat_slab_is_filled_from_its_own_points_and_the_slab_closes():
    mesh = square_hole_slab()
    assert _open_edges(mesh) == 8, "the hole's border: 4 corners and 4 midpoints, 8 open edges"
    engine, edits = _plan(mesh)

    (fill,) = edits
    assert (fill.engine, fill.kind, fill.faces, fill.legacy) == ("E8", "add", (), False)
    assert fill.new_points is None, "existing points only (E8b-R5)"
    loop = fill.evidence["loop"]
    assert len(loop) == 8 and len(fill.new_faces) == len(loop) - 2, "n - 2 triangles"
    assert set(fill.new_faces.ravel().tolist()) <= set(loop) and max(loop) < len(mesh.positions)
    assert fill.evidence["flat_fill"] is True and fill.evidence["material"] == 0
    assert fill.evidence["inscribed_diameter"] == pytest.approx(20.0, abs=0.05)

    normals, areas = _tri_normals(mesh, fill.new_faces)
    assert (areas > 1e-6).all(), "no degenerate triangle"
    assert areas.sum() == pytest.approx(400.0, rel=1e-6) and fill.evidence["area"] == pytest.approx(400.0, rel=1e-6)
    assert (normals[:, 2] > 0).all(), "wound to face up, as its neighbours do"
    # the neighbours' UV continued: (x, y) * 0.05
    expected_uv = mesh.positions[fill.new_faces][..., :2] * 0.05
    assert np.allclose(fill.new_face_uv, expected_uv, atol=1e-9)
    assert np.allclose(fill.new_face_normal, [0.0, 0.0, 1.0])

    after, _ = apply_edits(mesh, edits)
    assert _open_edges(after) == 0, "the slab's open edges go to 0"
    assert engine.not_filled == []


def test_a_concave_hole_is_ear_clipped_into_n_minus_2_triangles_of_its_own_area():
    mesh = holed_slab("l_hole", holes={(4, 4), (5, 4), (4, 5)})
    _, edits = _plan(mesh)
    (fill,) = edits
    assert len(fill.evidence["loop"]) == 8 and len(fill.new_faces) == 6
    normals, areas = _tri_normals(mesh, fill.new_faces)
    assert (areas > 1e-6).all() and (normals[:, 2] > 0).all()
    assert areas.sum() == pytest.approx(300.0, rel=1e-6)
    assert _open_edges(apply_edits(mesh, edits)[0]) == 0


def test_ear_clip_gives_n_minus_2_triangles_and_skips_collinear_ears():
    square_with_midpoints = np.array([[0, 0], [1, 0], [2, 0], [2, 1], [2, 2], [1, 2], [0, 2], [0, 1]], float)
    tris = ear_clip(square_with_midpoints)
    assert len(tris) == 6
    p = square_with_midpoints[np.asarray(tris)]
    cross = (p[:, 1, 0] - p[:, 0, 0]) * (p[:, 2, 1] - p[:, 0, 1]) - (p[:, 1, 1] - p[:, 0, 1]) * (p[:, 2, 0] - p[:, 0, 0])
    assert (cross > 0).all() and 0.5 * cross.sum() == pytest.approx(4.0)


# ------------------------------------------------------------------------------------------- item 2: refusals


def _refused(mesh):
    engine, edits = _plan(mesh)
    assert edits == [], "a refused loop is left unfilled"
    (row,) = engine.not_filled
    return row


def test_a_non_planar_border_is_refused():
    # 16 loop points (a 4 x 4 cell hole of 5 in cells); one corner raised 3 print steps (0.03 in): it lies 0.023 in
    # off the least-squares plane, beyond plane_tol = 2 print steps (0.02 in)
    mesh = holed_slab("bent", nx=12, ny=12, cell=5.0, holes={(i, j) for i in range(4, 8) for j in range(4, 8)},
                      lift={(4, 4): 0.03})
    row = _refused(mesh)
    assert (row["rule"], row["reason"]) == ("E8b-R2", "not_planar")
    assert row["vertices"] == 16 and row["planarity"] > 0.02


def test_a_hole_with_a_wall_at_its_border_is_refused():
    # the hole is the top's border cell: its edge x = 100 is the side's top edge, a neighbour at 90 degrees
    row = _refused(holed_slab("walled", holes={(9, 4)}))
    assert (row["rule"], row["reason"]) == ("E8b-R2", "neighbour_not_coplanar")
    assert row["max_angle"] == pytest.approx(90.0, abs=1e-6)


def test_two_looks_around_the_hole_are_refused():
    mesh = holed_slab("two_looks", holes={(i, j) for i in (4, 5) for j in (4, 5)}, materials=("m0", "m1"),
                      material_of=lambda i, j: 1 if i >= 6 else 0)
    row = _refused(mesh)
    assert (row["rule"], row["reason"]) == ("E8b-R4", "two_looks")
    assert sorted(row["looks"]) == ["material:m0", "material:m1"]


def test_a_uv_seam_around_the_hole_is_refused():
    mesh = holed_slab("uv_seam", holes={(i, j) for i in (4, 5) for j in (4, 5)},
                      uv_shift=lambda i, j: (0.37, 0.0) if i >= 6 else (0.0, 0.0))
    row = _refused(mesh)
    assert (row["rule"], row["reason"]) == ("E8b-R4", "uv_seam")
    assert row["uv_residual"] > 1e-3


def test_a_hole_1_5_m_wide_is_refused():
    row = _refused(holed_slab("wide", holes={(i, j) for i in range(2, 8) for j in range(2, 8)}))
    assert (row["rule"], row["reason"]) == ("E8b-R3", "too_wide")
    assert row["inscribed_diameter"] == pytest.approx(60.0, abs=0.05) and row["inscribed_diameter"] > FILL_MAX_DIAMETER


def test_a_hole_with_an_inner_hole_is_refused():
    # a 30 in hole with the middle cell left standing in it: the island's border is a loop inside the hole's loop
    holes = {(i, j) for i in range(3, 6) for j in range(3, 6)} - {(4, 4)}
    engine, edits = _plan(holed_slab("island", holes=holes))
    assert edits == []
    (row,) = engine.not_filled
    assert (row["rule"], row["reason"]) == ("E8b-R1", "inner_loop") and row["vertices"] == 12
    assert engine.report["outer_boundaries"] == 1, "the island's own border is an outer boundary, not a hole"


def test_a_hole_a_post_passes_through_is_refused():
    """Stricter than R1's letter, never looser: a closed post standing in the hole has no open edge inside it, but a
    fill would cut through it."""
    import dataclasses
    slab = square_hole_slab()
    # a closed 4 x 4 in post from the slab's bottom (z = -8) to z = 20, in the middle of the 20 in hole
    x0, x1, y0, y1, z0, z1 = 48.0, 52.0, 48.0, 52.0, -8.0, 20.0
    box = np.array([[x, y, z] for z in (z0, z1) for y in (y0, y1) for x in (x0, x1)], float)
    quads = [(0, 2, 3, 1), (4, 5, 7, 6), (0, 1, 5, 4), (2, 6, 7, 3), (0, 4, 6, 2), (1, 3, 7, 5)]
    n = len(slab.positions)
    tris = np.array([[q[0], q[1], q[2]] for q in quads] + [[q[0], q[2], q[3]] for q in quads]) + n
    mesh = dataclasses.replace(
        slab, positions=np.vstack([slab.positions, box]), face_v=np.vstack([slab.face_v, tris]),
        face_vt=np.vstack([slab.face_vt, np.full((len(tris), 3), -1)]),
        face_vn=np.vstack([slab.face_vn, np.full((len(tris), 3), -1)]),
        face_material=np.concatenate([slab.face_material, np.zeros(len(tris), np.int64)]),
        face_line=np.arange(1, slab.n_faces + len(tris) + 1))
    row = _refused(mesh)
    assert (row["rule"], row["reason"]) == ("E8b-R1", "faces_inside")


def test_each_refused_row_carries_what_e8c_needs():
    row = _refused(holed_slab("wide", holes={(i, j) for i in range(2, 8) for j in range(2, 8)}))
    assert {"loop", "rule", "reason", "detail", "vertices", "centroid", "points"} <= set(row)
    assert len(row["points"]) == row["vertices"] == 24


# ------------------------------------------------------------------------------------------- fix round 1, item 5


def test_polylabel_s_tolerance_counts_against_the_hole_at_the_cap():
    """A square hole exactly one block (39.37 in) across: polylabel may be 0.005 in off, so the hole is refused;
    one 39.3 in across is still filled."""
    at_cap = holed_slab("at_cap", [0.0, 20.0, 59.37, 80.0], [0.0, 20.0, 59.37, 80.0], holes={(1, 1)})
    row = _refused(at_cap)
    assert (row["rule"], row["reason"]) == ("E8b-R3", "too_wide")
    under = holed_slab("under", [0.0, 20.0, 59.3, 80.0], [0.0, 20.0, 59.3, 80.0], holes={(1, 1)})
    _, edits = _plan(under)
    assert len(edits) == 1


def test_a_degenerate_neighbour_is_refused_with_its_own_reason_and_no_nan(monkeypatch):
    """A neighbour face with no area has no normal: refused as `neighbour_degenerate`, never compared as NaN. (The
    topology leaves zero-area faces out, so the test flattens a neighbour in the positions the engine measures while
    the topology stays the unflattened mesh's.)"""
    import dataclasses
    import json

    from engine.repair.engines import e8_fill
    mesh = square_hole_slab()
    _, (fill,) = _plan(mesh)
    loop = set(fill.evidence["loop"])
    f = fill.evidence["neighbours"][0]
    corners = mesh.face_v[f].tolist()
    third = next(v for v in corners if v not in loop)
    on_edge = [v for v in corners if v in loop]
    positions = mesh.positions.copy()
    positions[third] = positions[on_edge].mean(axis=0)          # the face's third corner on its loop edge: no area
    flat = dataclasses.replace(mesh, positions=positions)
    topo = analyse_topology(mesh)
    monkeypatch.setattr(e8_fill, "analyse_topology_memo", lambda m: topo)
    engine, edits = _plan(flat)
    assert edits == []
    (row,) = engine.not_filled
    assert (row["rule"], row["reason"]) == ("E8b-R2", "neighbour_degenerate")
    json.dumps(row, allow_nan=False)
