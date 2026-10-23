"""E4, the checked coplanar merge (MAIN-INFRA-E4-MERGE-20261023): one `cut` per coplanar region that changed,
over existing vertices only, area preserved, UVs continuous, holes kept, judged by the kernel's site checks.
"""
from __future__ import annotations

import dataclasses

import numpy as np
import pytest

from engine.fixes.pipeline import FixProfile
from engine.pipeline import analyse_topology
from engine.repair.engines import e4_merge
from engine.repair.engines.e4_merge import E4Merge, e4_topology
from engine.repair.kernel import repair_unit
from engine.repair.types import RepairContext, UnitState, apply_edits
from engine.site_judge import SiteJudge
from engine.tests.fixtures.build import _mesh, slab_with_hole
from engine.tests.test_validate_checks import _looks, _with_plate
from engine.topo.edges import EDGE_OPEN

LOOKS = _looks("m0")
UV_PER_IN = 0.05
#: "m0" is a TEXTURED material (texture std above the flat threshold), so the strict UV rule applies to it.
TEXTURED = {"m0": 50.0}


def _uv(p):
    return [p[0] * UV_PER_IN, p[1] * UV_PER_IN]


def t_quad(at=(0.0, 0.0, 0.0)):
    """A 40 x 20 flat quad cut into 4 slivers: the triangle (A, B, C) and a fan from D over two points Q, R lying
    on the interior of the diagonal A-C -- two T-junctions. One affine UV map over the whole quad."""
    A, B, C, D = [0, 0, 0], [40, 0, 0], [40, 20, 0], [0, 20, 0]
    Q, R = [40 / 3, 20 / 3, 0], [80 / 3, 40 / 3, 0]
    P = np.array([A, B, C, D, Q, R], float) + np.asarray(at, float)
    fv = [[0, 1, 2], [0, 4, 3], [4, 5, 3], [5, 2, 3]]
    uvs = [_uv(P[i]) for f in fv for i in f]
    fvt = [[3 * k, 3 * k + 1, 3 * k + 2] for k in range(len(fv))]
    return _mesh("t_quad", P, uvs, fv, fvt, coord_decimals=6)


def two_quads():
    """Two `t_quad`s far apart in x: two coplanar regions, 4 slivers each."""
    return _with_plate(t_quad(), t_quad(at=(200.0, 0.0, 0.0)))


def _run(mesh, *, judge=None, engine=None, **kw):
    judge = judge or SiteJudge(LOOKS, margin=2.0)
    unit = UnitState(mesh=mesh, topo=None, looks={0: LOOKS.key_of("m0")}, viewpoints=None)
    ctx = RepairContext(profile=FixProfile(), decider=None, validator=judge)
    engine = engine or E4Merge(flatness=TEXTURED)
    return repair_unit(unit, ctx, engines=[engine], validate_sites=True, **kw), engine


def _plan(mesh, engine=None):
    engine = engine or E4Merge(flatness=TEXTURED)
    unit = UnitState(mesh=mesh, topo=None, looks={0: LOOKS.key_of("m0")}, viewpoints=None)
    ctx = RepairContext(profile=FixProfile(), decider=None, validator=None)
    return engine.plan(unit, ctx), engine


def _areas(mesh):
    tri = mesh.positions[mesh.face_v]
    return 0.5 * np.linalg.norm(np.cross(tri[:, 1] - tri[:, 0], tri[:, 2] - tri[:, 0]), axis=1)


def _uv_at(mesh, point):
    """The UV of `mesh` at `point` (on z = 0): barycentric in the first face holding it."""
    p = np.asarray(point, float)[:2]
    for f in range(mesh.n_faces):
        a, b, c = mesh.positions[mesh.face_v[f]][:, :2]
        d = (b[0] - a[0]) * (c[1] - a[1]) - (c[0] - a[0]) * (b[1] - a[1])
        wb = ((p[0] - a[0]) * (c[1] - a[1]) - (c[0] - a[0]) * (p[1] - a[1])) / d
        wc = ((b[0] - a[0]) * (p[1] - a[1]) - (p[0] - a[0]) * (b[1] - a[1])) / d
        wa = 1.0 - wb - wc
        if min(wa, wb, wc) >= -1e-9:
            uv = mesh.uvs[mesh.face_vt[f]]
            return wa * uv[0] + wb * uv[1] + wc * uv[2]
    raise AssertionError(f"no face holds {point}")


# ------------------------------------------------------------------------------------------- the plan

def test_four_slivers_with_t_junctions_become_one_cut_of_two_triangles_with_area_kept():
    before = t_quad()
    edits, engine = _plan(before)
    assert len(edits) == 1
    (edit,) = edits
    assert edit.engine == "E4" and edit.kind == "cut" and not edit.legacy
    assert edit.faces == (0, 1, 2, 3) and edit.new_points is None and len(edit.new_faces) == 2
    assert (edit.new_faces < len(before.positions)).all(), "existing vertices only"
    ev = edit.evidence
    assert ev["faces_before"] == 4 and ev["faces_after"] == 2 and ev["region"] == 0 and ev["material"] == 0
    assert ev["area_before"] == pytest.approx(800.0) and ev["area_after"] == pytest.approx(800.0, rel=1e-9)
    assert ev["ring_vertices"] == 4
    assert engine.report["sites"] == 1 and engine.report["refused"] == []


def test_vertices_never_move_and_the_cut_applies_without_new_points():
    before = t_quad()
    edits, _ = _plan(before)
    after, new_to_old = apply_edits(before, edits)
    np.testing.assert_array_equal(after.positions, before.positions)
    assert after.n_faces == 2 and (new_to_old == -1).all()
    assert _areas(after).sum() == pytest.approx(_areas(before).sum(), rel=1e-9)
    # the new triangles face the same way as the old ones
    tri = after.positions[after.face_v]
    assert (np.cross(tri[:, 1] - tri[:, 0], tri[:, 2] - tri[:, 0])[:, 2] > 0).all()


def test_uvs_are_continuous_at_five_sample_points():
    before = t_quad()
    edits, _ = _plan(before)
    after, _ = apply_edits(before, edits)
    assert (after.face_vt >= 0).all(), "the merged triangles carry UVs"
    for point in ([5, 5], [35, 5], [20, 10], [10, 15], [30, 17]):
        np.testing.assert_allclose(_uv_at(after, point), _uv_at(before, point), atol=1e-6)
    assert edits[0].evidence["uv_residual"] <= 1e-6


def test_a_region_whose_triangulation_did_not_change_is_skipped():
    before = t_quad()
    edits, _ = _plan(before)
    merged, _ = apply_edits(before, edits)
    again, engine = _plan(merged)
    assert again == [] and engine.report["skipped"]["unchanged"] == 1, "a second E4 run is a no-op"


def test_a_flat_material_may_be_rebased_by_whole_tiles_recorded_not_refused():
    # with no texture std for "m0" the material is flat (plain colour): the merge re-bases the region's UVs so
    # the minimum lies in [0, 1), a whole-tile shift that is recorded in the evidence and does not refuse the site
    before = t_quad()
    edits, engine = _plan(before, E4Merge(flatness={}))
    assert len(edits) == 1 and engine.report["flat_materials"] == [0]
    assert edits[0].evidence["uv_residual"] == pytest.approx(1.0, abs=1e-6)


def test_a_textured_region_whose_uvs_are_not_one_affine_map_is_refused():
    before = t_quad()
    uvs = before.uvs.copy()
    uvs[9:12] += 0.37                         # the fourth sliver's texture is shifted by a non-integer offset
    shifted = dataclasses.replace(before, uvs=uvs)
    _flat, topo = e4_topology(shifted, TEXTURED, FixProfile())
    if len(set(topo.face_region.tolist())) == 1:     # one region: the merge's single UV map cannot fit both
        edits, engine = _plan(shifted)
        assert edits == [] and engine.report["refused"][0]["reason"] == "uv_seam"
    else:                                            # the UV classes split the region: each side is its own region
        edits, engine = _plan(shifted)
        assert all(e.evidence["uv_residual"] <= 1e-6 for e in edits) and engine.report["refused"] == []


def test_a_region_with_a_real_opening_keeps_the_hole_open():
    before = slab_with_hole(6, 6, 10.0, 2, 4)
    edits, _ = _plan(before)
    assert len(edits) == 1 and len(edits[0].faces) == before.n_faces
    after, _ = apply_edits(before, edits)
    assert _areas(after).sum() == pytest.approx(_areas(before).sum(), rel=1e-9)
    topo = analyse_topology(after)
    open_edges = topo.table.edges[np.asarray(topo.edge_class) == EDGE_OPEN]
    pts = topo.positions_w[open_edges]                      # (n, 2, 3)
    mid = pts.mean(axis=1)
    on_hole = ((mid[:, 0] >= 20 - 1e-9) & (mid[:, 0] <= 40 + 1e-9) & (mid[:, 1] >= 20 - 1e-9)
               & (mid[:, 1] <= 40 + 1e-9))
    assert on_hole.sum() == 4, "the hole's four sides stay open edges"
    centroids = after.positions[after.face_v].mean(axis=1)
    inside = (centroids[:, 0] > 20) & (centroids[:, 0] < 40) & (centroids[:, 1] > 20) & (centroids[:, 1] < 40)
    assert not inside.any(), "no triangle bridges the opening"


def test_a_site_that_changes_area_is_refused(monkeypatch):
    before = t_quad()
    real = e4_merge.merge_regions

    def drop_one(mesh, topo, flat, **kw):
        result = real(mesh, topo, flat, **kw)
        keep = np.arange(result.mesh.n_faces) != 0
        out = dataclasses.replace(result.mesh, face_v=result.mesh.face_v[keep], face_vt=result.mesh.face_vt[keep],
                                  face_vn=result.mesh.face_vn[keep], face_material=result.mesh.face_material[keep],
                                  face_line=result.mesh.face_line[keep])
        return dataclasses.replace(result, mesh=out, source_faces=[s for s, k in zip(result.source_faces, keep) if k],
                                   face_region=result.face_region[keep])

    monkeypatch.setattr(e4_merge, "merge_regions", drop_one)
    edits, engine = _plan(before)
    assert edits == []
    (refused,) = engine.report["refused"]
    assert refused["reason"] == "area_changed" and refused["region"] == 0


def test_a_merge_that_moves_a_vertex_raises(monkeypatch):
    before = t_quad()
    real = e4_merge.merge_regions

    def nudge(mesh, topo, flat, **kw):
        result = real(mesh, topo, flat, **kw)
        positions = result.mesh.positions.copy()
        positions[0, 0] += 1e-3
        return dataclasses.replace(result, mesh=dataclasses.replace(result.mesh, positions=positions))

    monkeypatch.setattr(e4_merge, "merge_regions", nudge)
    with pytest.raises(ValueError, match="positions"):
        _plan(before)


def test_allowed_regions_restricts_the_plan_to_those_regions():
    before = two_quads()
    _flat, topo = e4_topology(before, {}, FixProfile())
    assert set(topo.face_region.tolist()) == {0, 1}
    edits, engine = _plan(before, E4Merge(flatness=TEXTURED, allowed_regions={1}))
    assert len(edits) == 1 and edits[0].evidence["region"] == 1
    assert engine.report["skipped"]["not_allowed"] == 1


# ---------------------------------------------------------------------------------------- the kernel

def test_the_checked_kernel_keeps_a_clean_merge_and_writes_one_check():
    before = t_quad()
    got, _ = _run(before)
    (check,) = got.checks
    assert check["stage"] == "E4" and check["engine"] == "E4" and check["final"] == "PASS"
    assert len(got.kept) == 1 and got.rolled_back == []
    assert got.mesh.n_faces == 2
    np.testing.assert_array_equal(got.mesh.positions, before.positions)
    assert [r["kind"] for r in got.records if "check" not in r] == ["cut"]


class _FailOneSite(SiteJudge):
    """The Validator plus one failing sample on a face the second region's site touches, so that site is charged
    and rolled back while the first region's site is confirmed."""

    def __init__(self, looks, face, **kw):
        super().__init__(looks, **kw)
        self.face = int(face)

    def check(self, after, focus, fills=None):
        from engine.site_judge import FailingSamples, SiteVerdict
        v = super().check(after, focus)
        if self.calls_failed_once:
            return v
        self.calls_failed_once = True
        s = v.samples
        add = lambda a, row: np.concatenate([a, np.asarray(row, dtype=a.dtype)])
        point = self.stage.before.positions[self.stage.before.face_v[self.face]].mean(axis=0)
        samples = FailingSamples(face=add(s.face, [self.face]), index=add(s.index, [0]),
                                 point=np.vstack([s.point, point[None]]),
                                 witness=np.vstack([s.witness, [[0, 0, 1.0]]]), is_dir=add(s.is_dir, [True]),
                                 cluster=add(s.cluster, [len(s.clusters)]), clusters=s.clusters + [{"deleted": 1}])
        return SiteVerdict(failing=v.failing | {(self.face, 0)}, summary=v.summary, seconds=v.seconds,
                           samples=samples)

    calls_failed_once = False


def test_a_site_the_judge_charges_is_rolled_back_and_its_region_copied_through_unchanged():
    before = two_quads()
    got, _ = _run(before, judge=_FailOneSite(LOOKS, face=5, margin=2.0))
    (check,) = got.checks
    assert check["first"] == "FAIL" and check["final"] == "PASS"
    assert [r["site"] for r in check["rolled_back"]] == [1]
    assert len(got.kept) == 1 and len(got.rolled_back) == 1
    assert got.kept[0].evidence["region"] == 0 and got.rolled_back[0].evidence["region"] == 1
    # region 1's four slivers survive untouched, region 0 is two triangles
    assert got.mesh.n_faces == 6
    np.testing.assert_array_equal(got.mesh.face_v[:4], before.face_v[4:8])
    np.testing.assert_array_equal(got.mesh.positions, before.positions)
    lines = [r for r in got.records if "check" not in r]
    assert [line.get("rolled_back", False) for line in lines] == [False, True]
