"""E5, the checked coincident-layer cull (MAIN-INFRA-E4-MERGE-20261023): one `remove` site per edge-connected group
of dropped twin-layer faces, the loser decided by look (same look: the larger face wins; different look: the facade
priority, then the larger area), never both faces of a pair, never a face that is the only coverage of its footprint,
judged by the kernel's site checks.
"""
from __future__ import annotations

import numpy as np
import pytest
import shapely

from engine.fixes.pipeline import FixProfile
from engine.repair.engines.e5_coincident import DEFAULT_LOSER_PATTERNS, DEFAULT_WIN_PATTERNS, E5Coincident, \
    default_priority
from engine.repair.kernel import repair_unit
from engine.repair.types import RepairContext, UnitState, apply_edits
from engine.site_judge import SiteJudge
from engine.tests.fixtures.build import _mesh
from engine.tests.test_validate_checks import _looks

UV_PER_IN = 0.05


def _quad(x0, y0, x1, y1, *, material=0, flip=False, z=0.0):
    """Two triangles over the rectangle [x0, x1] x [y0, y1] at height `z`, UVs by one affine map of the plane (so two
    copies of one place carry the same UV), facing +z (or -z with `flip`)."""
    corners = [[x0, y0, z], [x1, y0, z], [x1, y1, z], [x0, y1, z]]
    if flip:
        corners = corners[::-1]
    fv = [[0, 1, 2], [0, 2, 3]]
    return corners, fv, material


def plate(*quads, materials=("m0",)):
    P, uvs, fv, fvt, fm = [], [], [], [], []
    for corners, faces, material in quads:
        base_v = len(P)
        P.extend(corners)
        for f in faces:
            t0 = len(uvs)
            fv.append([base_v + i for i in f])
            fvt.append([t0, t0 + 1, t0 + 2])
            uvs.extend([[P[base_v + i][0] * UV_PER_IN, P[base_v + i][1] * UV_PER_IN] for i in f])
            fm.append(material)
    return _mesh("plate", P, uvs, fv, fvt, materials=materials, face_material=fm, coord_decimals=6)


def _ctx(mesh, judge=None):
    looks = _looks(*mesh.materials)
    unit = UnitState(mesh=mesh, topo=None, looks={i: looks.key_of(m) for i, m in enumerate(mesh.materials)},
                     viewpoints=None)
    return unit, RepairContext(profile=FixProfile(), decider=None, validator=judge), looks


def _plan(mesh, engine=None):
    engine = engine or E5Coincident(flatness={})
    unit, ctx, _ = _ctx(mesh)
    return engine.plan(unit, ctx), engine


def _footprint(mesh):
    """The union of the z = 0 faces' footprints (every fixture here lies in that plane)."""
    tri = mesh.positions[mesh.face_v][:, :, :2]
    return shapely.unary_union([shapely.Polygon(t) for t in tri])


def _dropped(edits):
    return sorted(f for e in edits for f in e.faces)


# -------------------------------------------------------------------------------------------- same look

def test_an_exact_smaller_twin_of_the_same_look_is_dropped_and_the_footprint_stays():
    before = plate(_quad(0, 0, 40, 20), _quad(10, 5, 20, 15))
    edits, engine = _plan(before)
    assert len(edits) == 1
    (edit,) = edits
    assert edit.engine == "E5" and edit.kind == "remove" and not edit.legacy
    assert edit.new_faces is None and edit.new_points is None
    assert edit.faces == (2, 3), "the small twin's two triangles, never the big face"
    for row in edit.evidence["pairs"]:
        assert row["rule"] == "same_look" and row["overlap_fraction"] >= 0.98
        assert row["look"] == row["winner_looks"][0] and row["area"] < min(row["winner_areas"])
    after, _ = apply_edits(before, edits)
    assert _footprint(after).symmetric_difference(_footprint(before)).area < 1e-9
    assert engine.report["sites"] == 1 and engine.report["dropped"] == 2


def test_an_identical_copy_drops_the_higher_face_ids_only():
    before = plate(_quad(0, 0, 40, 20), _quad(0, 0, 40, 20))
    edits, _ = _plan(before)
    assert _dropped(edits) == [2, 3], "equal areas: the later copy loses, the first stays"


def test_a_face_covered_98_percent_by_the_union_of_larger_same_look_faces_is_dropped():
    before = plate(_quad(0, 0, 20, 10), _quad(-20, -10, 19.9, 20))
    edits, _ = _plan(before)
    assert _dropped(edits) == [0, 1]
    fractions = sorted(row["overlap_fraction"] for e in edits for row in e.evidence["pairs"])
    assert 0.98 <= fractions[0] < 1.0, "partly covered, above the 98 % bar"


def test_a_face_half_overlapped_is_kept():
    before = plate(_quad(0, 0, 20, 10), _quad(10, -10, 50, 20))
    edits, engine = _plan(before)
    assert edits == []
    kept = engine.report["kept"]
    assert kept["uncovered"] == 2 and kept["no_winner"] == 1, "the one big triangle over them has nothing beating it"
    rows = [row for row in engine.report["kept_faces"] if row["kept"] == "uncovered"]
    # half the quad is under the big face: a quarter of one triangle, three quarters of the other
    assert sorted(row["overlap_fraction"] for row in rows) == pytest.approx([0.25, 0.75])


# ---------------------------------------------------------------------------------------- different look

def test_the_default_priority_ranks_facade_patterns_over_plain_over_generic_concrete():
    assert default_priority("UC_PAL_05") > default_priority("plaster") > default_priority("concrete_white")
    assert default_priority("minecraft:quartz_block_top") == default_priority("UC_PAL_12")
    assert default_priority("CONCRETE_GRAY") == default_priority("concrete_gray")
    assert all(p.lower() in {s.lower() for s in DEFAULT_WIN_PATTERNS} for p in ("UC_PAL_00", "iron_block", "wool"))
    assert set(DEFAULT_LOSER_PATTERNS) == {"concrete_white", "concrete_gray"}


def test_a_different_look_pair_drops_the_generic_concrete_under_the_facade():
    before = plate(_quad(0, 0, 40, 20, material=0), _quad(0, 0, 40, 20, material=1),
                   materials=("concrete_white", "UC_PAL_05"))
    edits, _ = _plan(before)
    assert _dropped(edits) == [0, 1]
    rows = [row for e in edits for row in e.evidence["pairs"]]
    assert all(row["rule"] == "priority" and row["look"] != row["winner_looks"][0] for row in rows)


def test_equal_priority_different_looks_fall_back_to_the_larger_area_or_keep_both():
    bigger = plate(_quad(0, 0, 20, 10, material=0), _quad(-10, -10, 30, 20, material=1), materials=("plainA", "plainB"))
    edits, _ = _plan(bigger)
    assert _dropped(edits) == [0, 1]
    assert {row["rule"] for e in edits for row in e.evidence["pairs"]} == {"larger_area"}
    same = plate(_quad(0, 0, 20, 10, material=0), _quad(0, 0, 20, 10, material=1), materials=("plainA", "plainB"))
    edits, engine = _plan(same)
    assert edits == [] and engine.report["kept"]["no_winner"] == 4, "no priority, no larger face: the owner decides"


def test_a_custom_priority_function_is_used():
    before = plate(_quad(0, 0, 40, 20, material=0), _quad(0, 0, 40, 20, material=1), materials=("a", "b"))
    edits, _ = _plan(before, E5Coincident(flatness={}, priority=lambda name: {"a": 5, "b": 1}[name]))
    assert _dropped(edits) == [2, 3]


# ------------------------------------------------------------------------------------------- never

def test_opposite_facing_sheets_both_exposed_are_left_alone():
    # two free-standing back-to-back sheets: both fronts see open space, so neither is the solid-facing twin
    before = plate(_quad(0, 0, 40, 20), _quad(0, 0, 40, 20, flip=True))
    edits, engine = _plan(before)
    assert edits == []
    assert engine.report["pairs"]["double_layers"] == 4 and engine.report["pairs"]["opposite"] == 4
    assert engine.report["pairs"]["same_facing"] == 0
    assert engine.report["kept"]["no_backface_winner"] == 4
    assert all(row["front"] > 0 for row in engine.report["kept_faces"])


# ------------------------------------------------------------------------------------- backface twins

def _cube_with_inward_twin(material=1):
    """A closed 10 in cube whose x = s side (faces 8, 9) carries an inward-facing coincident copy (faces 12, 13) in
    `material`: the Minecraft export's back-to-back twin, its front pointing into the solid."""
    import dataclasses
    from engine.tests.fixtures.build import cube
    base = cube()
    faces = [8, 9]
    return dataclasses.replace(
        base, face_v=np.vstack([base.face_v, base.face_v[faces][:, ::-1]]),
        face_vt=np.vstack([base.face_vt, base.face_vt[faces][:, ::-1]]),
        face_vn=np.vstack([base.face_vn, base.face_vn[faces]]),
        face_material=np.concatenate([base.face_material, [material, material]]),
        face_line=np.arange(1, base.n_faces + 3, dtype=np.int64), materials=["m0", "m1"])


def test_the_solid_facing_twin_of_a_back_to_back_pair_is_dropped_whatever_its_look():
    before = _cube_with_inward_twin()
    edits, engine = _plan(before)
    assert _dropped(edits) == [12, 13], "the inward copy goes, the outward face stays"
    rows = [row for e in edits for row in e.evidence["pairs"]]
    assert all(row["rule"] == "backface_twin" and row["front"] == 0.0 and row["back"] > 0 for row in rows)
    assert all(row["look"] != row["winner_looks"][0] for row in rows), "a different look does not protect it"
    assert all(min(row["winner_front"]) > 0 for row in rows)
    assert engine.report["by_rule"]["backface_twin"] == 2 and engine.report["pairs"]["opposite"] >= 2
    assert engine.report["cull_opposite_backfaces"] is True
    after, _ = apply_edits(before, edits)
    assert after.n_faces == 12


def test_the_backface_rule_can_be_switched_off():
    edits, engine = _plan(_cube_with_inward_twin(), E5Coincident(flatness={}, cull_opposite_backfaces=False))
    assert edits == [] and engine.report["cull_opposite_backfaces"] is False
    assert engine.report["pairs"]["opposite"] >= 2 and engine.report["kept"]["no_backface_winner"] == 0


def test_a_back_to_back_pair_both_hidden_is_kept():
    import dataclasses
    from engine.tests.fixtures.build import box_with_partition
    base = box_with_partition()                      # faces 12, 13: the sealed partition nothing sees
    faces = [12, 13]
    before = dataclasses.replace(
        base, face_v=np.vstack([base.face_v, base.face_v[faces][:, ::-1]]),
        face_vt=np.vstack([base.face_vt, base.face_vt[faces][:, ::-1]]),
        face_vn=np.vstack([base.face_vn, base.face_vn[faces]]),
        face_material=np.concatenate([base.face_material, [0, 0]]),
        face_line=np.arange(1, base.n_faces + 3, dtype=np.int64))
    edits, engine = _plan(before)
    assert edits == []
    assert engine.report["kept"]["no_backface_winner"] == 4
    assert all(row["front"] == 0.0 for row in engine.report["kept_faces"])


def test_the_judge_with_the_owner_class_keeps_a_backface_site_and_without_it_rolls_it_back():
    from engine.validate.checks import CBR, Settings
    before = _cube_with_inward_twin()
    looks = _looks(*before.materials)
    for settings, kept_faces, rolled_faces in ((Settings(allowed_changes={CBR}), [[12, 13]], []),
                                               (Settings(), [], [[12, 13]])):
        unit, ctx, _ = _ctx(before, judge=SiteJudge(looks, settings=settings, margin=2.0))
        got = repair_unit(unit, ctx, engines=[E5Coincident(flatness={})], validate_sites=True)
        (check,) = got.checks
        assert check["final"] == ("PASS" if kept_faces else "NOTHING KEPT"), settings.allowed_changes
        assert [sorted(e.faces) for e in got.kept] == kept_faces, settings.allowed_changes
        assert [sorted(e.faces) for e in got.rolled_back] == rolled_faces
        assert got.mesh.n_faces == (12 if kept_faces else 14)


def test_a_face_that_is_the_only_coverage_of_part_of_its_footprint_is_never_dropped():
    # the facade wins on priority, yet it covers only 80 % of the concrete (96 % of its upper triangle): dropping
    # the concrete would open a hole, so both its triangles stay
    before = plate(_quad(0, 0, 20, 10, material=0), _quad(0, 0, 16, 10, material=1),
                   materials=("concrete_white", "UC_PAL_05"))
    edits, engine = _plan(before)
    assert edits == []
    assert engine.report["kept"]["uncovered"] == 2
    rows = [row for row in engine.report["kept_faces"] if row["kept"] == "uncovered"]
    assert len(rows) == 2
    assert all(set(row["winner_looks"]) == {"look-UC_PAL_05"} and row["overlap_fraction"] < 0.98 for row in rows)
    assert max(row["overlap_fraction"] for row in rows) > 0.9, "one triangle is 96 % covered and still stays"


def test_never_both_faces_of_a_pair_a_winner_is_anchored():
    # small inside medium inside large, one look: the small face loses to the medium one, which then cannot lose to
    # the large one in the same run (its pair with the small face would have lost both faces)
    before = plate(_quad(10, 5, 20, 10), _quad(5, 2, 30, 15), _quad(0, 0, 40, 20))
    edits, engine = _plan(before)
    assert _dropped(edits) == [0, 1]
    assert engine.report["kept"]["anchored"] == 2
    after, _ = apply_edits(before, edits)
    again, engine2 = _plan(after)
    assert _dropped(again) == [0, 1], "a second run drops the medium copy, the large face stays"


def test_a_group_over_the_cap_is_split_into_several_sites():
    quads = [_quad(0, 0, 40, 20)] + [_quad(i * 4.0, 2, i * 4.0 + 4.0, 18) for i in range(10)]
    before = plate(*quads)
    edits, _ = _plan(before, E5Coincident(flatness={}, max_site_faces=4))
    assert all(len(e.faces) <= 4 for e in edits) and len(edits) >= 5
    assert _dropped(edits) == list(range(2, 22))


# ----------------------------------------------------------------------------------------------- kernel

def _twin_and_flicker():
    """Two sites far apart: an identical same-look copy (faces 2-3 over 0-1) and a concrete sheet (4-5) under a
    facade (6-7) 300 in away."""
    return plate(_quad(0, 0, 40, 20, material=0), _quad(0, 0, 40, 20, material=0),
                 _quad(300, 0, 340, 20, material=1), _quad(300, 0, 340, 20, material=2),
                 materials=("m0", "concrete_white", "UC_PAL_05"))


def test_the_judge_keeps_the_identical_twin_drop_and_rolls_back_the_different_look_drop():
    before = _twin_and_flicker()
    unit, ctx, looks = _ctx(before, judge=SiteJudge(_looks(*before.materials), margin=2.0))
    engine = E5Coincident(flatness={})
    got = repair_unit(unit, ctx, engines=[engine], validate_sites=True)
    assert sorted(f for e in engine.report["planned"] for f in e) == [2, 3, 4, 5]
    (check,) = got.checks
    assert check["stage"] == "E5" and check["engine"] == "E5" and check["legacy"] is False
    assert check["first"] == "FAIL" and check["final"] == "PASS"
    assert [sorted(e.faces) for e in got.kept] == [[2, 3]], "deleting an identical coplanar copy is no change"
    assert [sorted(e.faces) for e in got.rolled_back] == [[4, 5]], "the concrete's look is gone from that place"
    assert {r for row in check["rolled_back"] for r in row["reasons"]} & {"look", "replaced"}
    np.testing.assert_array_equal(got.mesh.positions, before.positions)
    assert got.mesh.n_faces == 6
    np.testing.assert_array_equal(got.mesh.face_v, before.face_v[[0, 1, 4, 5, 6, 7]])
    lines = [r for r in got.records if "check" not in r]
    assert [(line["kind"], line.get("rolled_back", False)) for line in lines] == [("remove", False), ("remove", True)]
