"""E4 after real 7F chain run #2 (2026-10-24): the region normal comes from the input faces' own winding (area-weighted
majority), a region whose input faces disagree in winding is refused `mixed_winding` (36 appended triangles came back
`reversed` on 7F), and a region that still carries a coincident opposite partner E5 could not drop is skipped
`twinned` (472 of the 8,222 charged covered samples on 7F lay on such twins)."""
from __future__ import annotations

import dataclasses

import numpy as np

from engine.repair.engines.e4_merge import E4Merge
from engine.tests.test_e4_merge import TEXTURED, _plan, t_quad


def _reversed(mesh, faces):
    fv, fvt = mesh.face_v.copy(), mesh.face_vt.copy()
    fv[faces] = fv[faces][:, ::-1]
    fvt[faces] = fvt[faces][:, ::-1]
    return dataclasses.replace(mesh, face_v=fv, face_vt=fvt)


def _z(mesh, tri):
    p = mesh.positions[tri]
    return np.cross(p[:, 1] - p[:, 0], p[:, 2] - p[:, 0])[:, 2]


def test_a_quad_whose_source_triangles_wind_clockwise_merges_clockwise():
    before = _reversed(t_quad(), [0, 1, 2, 3])
    assert (_z(before, before.face_v) < 0).all()
    edits, engine = _plan(before)
    assert len(edits) == 1 and engine.report["refused"] == []
    assert (_z(before, edits[0].new_faces) < 0).all(), "the new triangles wind as the input did"
    assert edits[0].evidence["winding"] == {"agreeing_area": 800.0, "disagreeing_area": 0.0, "faces_disagreeing": 0}


def test_a_region_whose_input_faces_disagree_in_winding_is_refused_mixed_winding(monkeypatch):
    # the topology builder never hands the merge a mixed-winding region (opposite normals fall in separate regions,
    # test below), so the guard is driven directly: the real merge of the well-wound quad, handed back for the mixed one
    from engine.fixes.pipeline import FixProfile
    from engine.repair.engines import e4_merge
    from engine.repair.engines.e4_merge import e4_topology
    clean = t_quad()
    before = _reversed(clean, [1, 2, 3])               # the fan winds against the big triangle
    real = e4_merge.merge_regions
    flat, topo = e4_topology(clean, TEXTURED, FixProfile())
    monkeypatch.setattr(e4_merge, "merge_regions", lambda mesh, t, f, **kw: real(clean, topo, f, **kw))
    edits, engine = _plan(before)
    assert edits == []
    (refused,) = engine.report["refused"]
    assert refused["reason"] == "mixed_winding" and refused["faces_before"] == 4
    assert refused["winding"]["faces_disagreeing"] == 3 and refused["winding"]["agreeing_area"] == 400.0
    assert "winding" in refused["detail"]


def test_opposite_winding_faces_fall_in_separate_regions_each_single_winding():
    # measured on 7F chain run #2: 0 of 1,571 appended triangles wind against their source faces, 0 regions mix
    # windings; a reversed sliver is its own region, and every planned region records faces_disagreeing 0
    before = _reversed(t_quad(), [0])
    edits, engine = _plan(before)
    assert engine.report["refused"] == []
    assert all(e.evidence["winding"]["faces_disagreeing"] == 0 for e in edits)
    assert not any(0 in e.faces and len(e.faces) > 1 for e in edits), "the reversed sliver never joins the others"
    for e in edits:
        z = _z(before, e.new_faces)
        assert (z > 0).all() if 0 not in e.faces else (z < 0).all(), "each region keeps its own winding"


def _with_opposite_copy(mesh):
    """`mesh` plus a coincident copy of its whole footprint as two reversed triangles (the twin E5 could not drop)."""
    P = mesh.positions
    quad = np.array([[0, 2, 1], [0, 3, 2]], np.int64)              # A, C, B and A, D, C: facing -z
    uvs = np.vstack([mesh.uvs, (P[quad.reshape(-1)][:, :2] * 0.05)])
    base = len(mesh.uvs)
    fvt = np.arange(base, base + 6).reshape(2, 3)
    n = mesh.n_faces + 2
    return dataclasses.replace(mesh, uvs=uvs, face_v=np.vstack([mesh.face_v, quad]), face_vt=np.vstack([mesh.face_vt, fvt]),
                               face_vn=np.vstack([mesh.face_vn, np.full((2, 3), -1, np.int64)]),
                               face_material=np.concatenate([mesh.face_material, [0, 0]]),
                               face_line=np.arange(1, n + 1, dtype=np.int64))


def test_a_region_with_a_coincident_opposite_partner_is_skipped_twinned():
    before = _with_opposite_copy(t_quad())
    edits, engine = _plan(before)
    assert edits == [], "the slivers still carry their back-to-back twin: the merge would cover its samples"
    assert engine.report["skipped"]["twinned"] >= 1 and engine.report["twinned_faces"] >= 4
    assert engine.report["skip_twinned"] is True and engine.report["refused"] == []


def test_the_twinned_skip_can_be_switched_off():
    before = _with_opposite_copy(t_quad())
    edits, engine = _plan(before, E4Merge(flatness=TEXTURED, skip_twinned=False))
    assert any(e.faces == (0, 1, 2, 3) for e in edits)
    assert engine.report["skipped"]["twinned"] == 0 and engine.report["skip_twinned"] is False


def test_a_plain_quad_is_not_twinned():
    edits, engine = _plan(t_quad())
    assert len(edits) == 1 and engine.report["skipped"]["twinned"] == 0 and engine.report["twinned_faces"] == 0
