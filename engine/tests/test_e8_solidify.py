"""Job P2-E8a: strict solidify as the repair engine E8 (`engine.repair.engines.e8_solidify.E8Solidify`).

E8 runs `engine.fixes.solidify.solidify` unchanged and hands back what it built as `Edit`s, ONE SITE PER PIECE (a
wall under one outline edge, or one region's bottom), so the kernel's site checks (`validate_sites=True`) judge
every piece on its own. The owner's strict rule (AGENTS.md section 5: a rebuilt side may cover only faces that are
0 % visible) is enforced by those checks, not by the cap guard's threshold (ruling E8-R1): a piece that covers any
sample some viewpoint sees -- an eye-height probe included -- is rolled back, and the other pieces are kept.
"""
from __future__ import annotations

import json
from collections import Counter

import numpy as np
import pytest

from engine.fixes.pipeline import FixProfile, start_fix
from engine.fixes.solidify import solidify
from engine.repair.engines.e8_solidify import E8Solidify
from engine.repair.kernel import repair_unit
from engine.repair.types import RepairContext, UnitState, apply_edits, face_keys
from engine.site_judge import SiteJudge
from engine.tests.fixtures import build as B
from engine.tests.fixtures.build import _mesh, _quads, compartment_with_deep_wall, slab_with_three_skirts
from engine.tests.test_validate_checks import _looks, _moved, _with_plate
from engine.validate.checks import Settings
from engine.validate.sampling import face_samples, recentred, used_bbox
from engine.validate.viewpoints import interior_probes, outside_directions, pedestrian_ring
from engine.validate.visibility import build_caster, visible_samples

_FAST = FixProfile(guard_size=(120, 80), n_dirs=32)

#: The solidify fixtures of `fixtures/build.py` that build at least one piece the cap guard keeps.
SOLIDIFY_FIXTURES = ["slab_with_three_skirts", "compartment_with_deep_wall", "slab_with_sawtooth_side",
                     "open_box_with_cells", "slab_with_half_side", "slab_with_partial_underside",
                     "slab_with_two_depths", "slab_continuing_under_a_landing", "sloped_slab",
                     "slab_with_a_bottom_strip", "slab_beside_a_lower_top", "two_level_slab"]


def _reference(mesh, profile=_FAST):
    """What `solidify` builds on `mesh`, with the topology the pipeline gives it (`start_fix`)."""
    return solidify(mesh, start_fix(mesh, {}, profile).topo_input, profile)


def _plan(mesh, profile=_FAST):
    unit = UnitState(mesh=mesh, topo=None, looks={}, viewpoints=None)
    return E8Solidify().plan(unit, RepairContext(profile=profile, decider=None, validator=None))


def _faces_and_uvs(mesh) -> Counter:
    """The multiset of (face key, UV at each corner, rounded): what must match, whatever the row order."""
    keys = face_keys(mesh, {})
    out = Counter()
    for f, key in enumerate(keys):
        vt = mesh.face_vt[f]
        uv = tuple(np.round(mesh.uvs[vt], 6).ravel().tolist()) if (vt >= 0).all() else None
        out[(key, uv)] += 1
    return out


# ------------------------------------------------------------------------------------------- engine shape


def test_e8_is_a_non_legacy_engine_named_e8():
    engine = E8Solidify()
    assert engine.name == "E8" and engine.legacy is False


@pytest.mark.parametrize("name", SOLIDIFY_FIXTURES)
def test_plan_gives_non_legacy_e8_edits_one_site_per_piece(name):
    mesh = getattr(B, name)()
    ref = _reference(mesh)
    pieces = sorted(set(ref.face_group[ref.face_group >= 0].tolist()))
    assert pieces, f"{name}: the fixture must build a piece the cap guard keeps"
    edits = _plan(mesh)

    assert edits and all(e.engine == "E8" and e.legacy is False for e in edits)
    assert all(e.reason and e.evidence for e in edits)
    assert sorted({e.site for e in edits}) == pieces, "one distinct site per piece solidify kept"
    for site in pieces:
        mine = [e for e in edits if e.site == site]
        builds = [e for e in mine if e.kind in ("add", "cut")]
        assert len(builds) == 1, (name, site, [e.kind for e in mine])
        (build,) = builds
        assert build.new_face_uv is not None and build.new_face_normal is not None
        assert build.evidence["piece"] in ("wall", "bottom")
        assert {"region", "thickness", "solidify", "material"} <= set(build.evidence)
        replaced = np.flatnonzero(ref.replaced_group == site).tolist()
        assert sorted(f for e in mine for f in e.faces) == replaced, "a piece names exactly the faces it replaced"
    assert sorted(f for e in edits for f in e.faces) == np.flatnonzero(ref.replaced).tolist()


@pytest.mark.parametrize("name", SOLIDIFY_FIXTURES)
def test_apply_edits_reproduces_solidifys_own_output(name):
    """Ruling (b): the same faces (K1 keys) with the same UVs, as a multiset; row order and vertex numbering may
    differ (each edit carries its own new points, so a point two pieces share is written once per piece)."""
    mesh = getattr(B, name)()
    ref = _reference(mesh)
    after, _ = apply_edits(mesh, _plan(mesh))
    assert after.n_faces == ref.mesh.n_faces
    assert _faces_and_uvs(after) == _faces_and_uvs(ref.mesh)
    assert np.array_equal(np.sort(after.face_material), np.sort(ref.mesh.face_material))


def test_a_broken_side_is_replaced_by_a_cut():
    mesh = B.slab_with_sawtooth_side()
    ref = _reference(mesh)
    assert ref.replaced.any()
    cuts = [e for e in _plan(mesh) if e.kind == "cut"]
    assert cuts and sorted(f for e in cuts for f in e.faces) == np.flatnonzero(ref.replaced).tolist()


def test_adds_carry_the_points_solidify_invented():
    mesh = B.slab_with_two_depths()
    ref = _reference(mesh)
    n = len(mesh.positions)
    edits = _plan(mesh)
    carried = [e for e in edits if e.new_points is not None and len(e.new_points)]
    assert carried, "this fixture's walls go below every existing vertex"
    used = np.unique(ref.mesh.face_v[ref.face_group >= 0])
    invented = {tuple(p) for p in np.round(ref.mesh.positions[used[used >= n]], 6).tolist()}
    brought = {tuple(p) for e in carried for p in np.round(e.new_points, 6).tolist()}
    assert brought == invented


def test_plan_leaves_the_unit_mesh_alone():
    mesh = slab_with_three_skirts()
    before = (mesh.positions.copy(), mesh.face_v.copy())
    unit = UnitState(mesh=mesh, topo=None, looks={}, viewpoints=None)
    E8Solidify().plan(unit, RepairContext(profile=_FAST, decider=None, validator=None))
    assert unit.mesh is mesh and np.array_equal(mesh.positions, before[0]) and np.array_equal(mesh.face_v, before[1])


# ------------------------------------------------------------------------- the strict rule: a covering piece

def _courtyard(half=300.0, wall=400.0, floor=4.0):
    """A closed floor box (top at z = 0, `2 half` square) and four single walls `wall` high round it, facing in:
    an open-air court nothing outside can look into at a low angle."""
    h = half
    P = [[-h, -h, 0.0], [h, -h, 0.0], [h, h, 0.0], [-h, h, 0.0],
         [-h, -h, -floor], [h, -h, -floor], [h, h, -floor], [-h, h, -floor],
         [-h, -h, wall], [h, -h, wall], [h, h, wall], [-h, h, wall]]
    uvs, fv, fvt, fm = [], [], [], []
    _quads(P, uvs, fv, fvt, fm, [(0, 1, 2, 3), (4, 7, 6, 5), (0, 4, 5, 1), (1, 5, 6, 2), (2, 6, 7, 3),
                                 (3, 7, 4, 0)])
    _quads(P, uvs, fv, fvt, fm, [(0, 1, 9, 8), (1, 2, 10, 9), (2, 3, 11, 10), (3, 0, 8, 11)])
    return _mesh("courtyard", P, uvs, fv, fvt, face_material=fm)


COMPARTMENT = (20, 32)      # the compartment's faces in `_probe_scene`
DEEP_WALL = (30, 31)        # its deep wall (compartment faces 10-11)


def _probe_scene():
    """In the court: `compartment_with_deep_wall` (40 in wide) lifted so its open end (x = 0) spans z = 55..65,
    eye height (63 in) above the court's floor. Its deep wall is seen ONLY by the eye-height probes standing in
    the court: no outside direction and no ring camera reaches it. Far off, outside the court, a
    `slab_with_three_skirts` whose wall and bottom cover nothing anyone sees."""
    comp = _moved(compartment_with_deep_wall(width=40.0), [0.0, -20.0, 65.0])
    scene = _with_plate(_courtyard(), comp)
    return _with_plate(scene, _moved(slab_with_three_skirts(), [2000.0, 0.0, 0.0]))


def _checked(mesh, *, edit_log=None):
    judge = SiteJudge(_looks(*mesh.materials), margin=2.0)
    unit = UnitState(mesh=mesh, topo=None, looks={}, viewpoints=None)
    ctx = RepairContext(profile=_FAST, decider=None, validator=judge)
    return repair_unit(unit, ctx, engines=[E8Solidify()], validate_sites=True, edit_log=edit_log)


def _points_of(edit, mesh):
    local = np.zeros((0, 3)) if edit.new_points is None else edit.new_points
    table = np.vstack([mesh.positions, local])
    return table[edit.new_faces.ravel()]


def test_the_probe_scene_deep_wall_is_seen_only_from_eye_height():
    mesh = _probe_scene()
    s = Settings()
    b, _ = recentred(mesh)
    caster = build_caster(b)
    cams = pedestrian_ring(used_bbox(b), eye_z=used_bbox(b)[0][2] + s.eye, n=s.n_cameras, margin=s.camera_margin)
    probes = interior_probes(b, eye=s.eye, caster=caster)
    dirs = outside_directions(s.n_directions)
    seen = visible_samples(b, face_samples(b, np.array(DEEP_WALL)), dirs, cams, probes, caster).seen
    nd, nc = len(dirs), len(cams)
    assert not seen[:, :nd + nc].any(), "no outside direction and no ring camera sees the deep wall"
    assert seen[:, nd + nc:].any(axis=1).all(), "every sample of it is seen by an eye-height probe"


def test_a_piece_covering_what_only_a_probe_sees_is_rolled_back_and_the_others_are_kept(tmp_path):
    mesh = _probe_scene()
    ref = _reference(mesh)
    log = tmp_path / "edit_log.jsonl"
    got = _checked(mesh, edit_log=log)

    (check,) = got.checks
    assert check["engine"] == "E8" and check["first"] == "FAIL" and check["final"] == "PASS"
    assert check["stage_rolled_back"] is None
    (rolled,) = check["rolled_back"]
    assert set(rolled["reasons"]) == {"covered"} and rolled["reasons"]["covered"] > 0
    assert check["runs"][-1]["kind"] == "confirm" and check["runs"][-1]["failing"] == 0

    # the rolled-back piece is the wall closing the compartment's open end (x = 0, z 55..65) ...
    bad = rolled["site"]
    (wall,) = [e for e in got.rolled_back if e.kind in ("add", "cut")]
    assert wall.site == bad and wall.evidence["piece"] == "wall"
    p = _points_of(wall, mesh)
    assert np.allclose(p[:, 0], 0.0) and p[:, 2].min() >= 55.0 - 1e-6 and p[:, 2].max() <= 65.0 + 1e-6
    # ... which the legacy cap guard KEPT (its threshold reads outside directions only)
    assert bad in set(ref.face_group[ref.face_group >= 0].tolist()) and ref.report["cap_guard_passed"]

    # the far slab's wall and bottom are kept, and the shipped mesh is exactly them
    kept_sites = {e.site for e in got.kept}
    assert len(kept_sites) == 2 and bad not in kept_sites
    assert {e.evidence["piece"] for e in got.kept if e.kind in ("add", "cut")} == {"wall", "bottom"}
    for e in got.kept:
        if e.kind in ("add", "cut"):
            assert _points_of(e, mesh)[:, 0].min() >= 2000.0 - 1e-6
    assert _faces_and_uvs(got.mesh) == _faces_and_uvs(apply_edits(mesh, got.kept)[0])
    assert got.mesh.n_faces == mesh.n_faces + sum(len(e.new_faces) for e in got.kept if e.kind == "add")

    lines = [json.loads(line) for line in log.read_text(encoding="utf-8").splitlines()]
    edits = [line for line in lines if "check" not in line]
    assert {line["site"] for line in edits if line.get("rolled_back")} == {bad}
    assert all(line["engine"] == "E8" and line["stage"] == "E8" for line in edits)
    (check_line,) = [line["check"] for line in lines if "check" in line]
    assert check_line["rolled_back"][0]["reasons"].keys() == {"covered"}


def test_pieces_that_cover_nothing_visible_are_all_kept_and_the_stage_passes():
    for mesh in (slab_with_three_skirts(), B.slab_with_half_side()):
        ref = _reference(mesh)
        got = _checked(mesh)
        (check,) = got.checks
        assert check["first"] == "PASS" and check["final"] == "PASS" and check["rolled_back"] == [], mesh.name
        assert got.rolled_back == [] and {e.site for e in got.kept} == set(
            ref.face_group[ref.face_group >= 0].tolist())
        assert _faces_and_uvs(got.mesh) == _faces_and_uvs(ref.mesh), "everything solidify built ships"
