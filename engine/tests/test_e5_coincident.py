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
    # a 90 x 60 guard grid: the fixtures are a few faces; the guard-direction pixel test at 900 x 600 (and 2x) costs
    # seconds per plan and proves nothing more on them
    return unit, RepairContext(profile=FixProfile(guard_size=(90, 60)), decider=None, validator=judge), looks


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
    assert engine.report["kept"]["both_exposed"] == 4 and engine.report["kept"]["no_backface_winner"] == 0
    assert all(row["front"] > 0 for row in engine.report["kept_faces"])
    # the audit sample of kept opposite pairs: one row per pair with both faces' exposures
    # the flipped quad's corner order is reversed, so its triangles use the other diagonal: each overlaps both
    pairs = engine.report["kept_pairs"]
    assert engine.report["kept_pairs_total"] == 4
    assert sorted(tuple(r["faces"]) for r in pairs) == [(0, 2), (0, 3), (1, 2), (1, 3)]
    assert all(r["reason"] == "both_exposed" and min(r["front"]) > 0 and len(r["back"]) == 2 for r in pairs)


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


def _partition_with_inward_twin():
    import dataclasses
    from engine.tests.fixtures.build import box_with_partition
    base = box_with_partition()                      # faces 12, 13: the sealed partition nothing sees
    faces = [12, 13]
    return dataclasses.replace(
        base, face_v=np.vstack([base.face_v, base.face_v[faces][:, ::-1]]),
        face_vt=np.vstack([base.face_vt, base.face_vt[faces][:, ::-1]]),
        face_vn=np.vstack([base.face_vn, base.face_vn[faces]]),
        face_material=np.concatenate([base.face_material, [0, 0]]),
        face_line=np.arange(1, base.n_faces + 3, dtype=np.int64))


def _unseen(mesh, faces):
    """A seam view that sees nothing: every face 0 points seen (the sealed partition's truth)."""
    return np.zeros(len(faces), np.int64)


def test_a_back_to_back_pair_both_hidden_is_an_interior_seam_and_both_faces_go_as_one_site():
    before = _partition_with_inward_twin()
    edits, engine = _plan(before, E5Coincident(flatness={}, seam_view=_unseen))
    assert engine.report["interior_filtered"] == {"seams": 2, "seen": 0, "unverified": 0, "planned": 2}
    assert len(edits) == 1 and sorted(edits[0].faces) == [12, 13, 14, 15], "both faces of each pair, one site"
    rows = edits[0].evidence["pairs"]
    assert all(row["rule"] == "interior_twins" and row["front"] == 0.0 for row in rows)
    assert all(all(f == 0.0 for f in row["winner_front"]) for row in rows), "the partner is hidden too"
    assert engine.report["by_rule"]["interior_twins"] == 4 and engine.report["dropped"] == 4
    assert engine.report["kept"]["both_exposed"] == 0 and engine.report["kept"]["no_backface_winner"] == 0
    assert engine.report["kept_pairs"] == [] and engine.report["kept_pairs_total"] == 0
    after, _ = apply_edits(before, edits)
    assert after.n_faces == 12


def test_interior_twins_are_one_site_even_when_their_vertices_are_not_shared():
    # the same partition twin, but the copy has its own (identical) vertices: no welded edge joins the two layers,
    # and the pair still travels as one site
    import dataclasses
    before = _partition_with_inward_twin()
    n_v = len(before.positions)
    copy_v = before.face_v[[14, 15]]
    used = np.unique(copy_v)
    remap = {int(v): n_v + k for k, v in enumerate(used.tolist())}
    fv = before.face_v.copy()
    fv[[14, 15]] = np.vectorize(remap.get)(copy_v)
    before = dataclasses.replace(before, positions=np.vstack([before.positions, before.positions[used]]), face_v=fv)
    edits, _ = _plan(before, E5Coincident(flatness={}, seam_view=_unseen))
    assert len(edits) == 1 and sorted(edits[0].faces) == [12, 13, 14, 15]


def test_a_seam_that_was_the_only_cover_of_a_prior_removed_face_is_kept_covers_prior_removal():
    # real 7F replay round 1: faces E3 removed stayed covered by a coincident pair, E5 dropped that pair as an interior
    # seam, and from some directions nothing covered them any more. The prior stage's removed triangles come in as
    # `prior_removed` (their corners, in the engine frame) and the only-coverage rule extends to them.
    before = _partition_with_inward_twin()
    prior = before.positions[before.face_v[[12, 13]]]                 # removed faces lying exactly on the partition
    edits, engine = _plan(before, E5Coincident(flatness={}, seam_view=_unseen, prior_removed=prior))
    assert edits == []
    assert engine.report["kept"]["covers_prior_removal"] == 4, "both seams and their partners stay"
    # two faces examined (12, then 13 after the first refusal); each refusal takes its seam partner along unexamined
    assert engine.report["prior_removed"] == {"triangles": 2, "faces_checked": 2, "faces_refused": 4}
    rows = [r for r in engine.report["kept_faces"] if r["kept"] == "covers_prior_removal"]
    assert {r["face"] for r in rows} == {12, 13, 14, 15} and all(r["prior_cover"] < 0.98 for r in rows)


def test_a_prior_removed_face_off_the_plane_does_not_hold_the_seam():
    before = _partition_with_inward_twin()
    prior = before.positions[before.face_v[[12]]] + np.array([0.0, 0.0, 100.0])   # lifted off the partition's plane
    edits, engine = _plan(before, E5Coincident(flatness={}, seam_view=_unseen, prior_removed=prior))
    assert len(edits) == 1 and sorted(edits[0].faces) == [12, 13, 14, 15]
    assert engine.report["kept"]["covers_prior_removal"] == 0
    assert engine.report["prior_removed"] == {"triangles": 1, "faces_checked": 4, "faces_refused": 0}


def test_a_prior_removed_face_still_covered_by_the_kept_twin_lets_the_drop_through():
    # the small same-look copy goes; a removed face under it is still covered by the big face that stays
    before = plate(_quad(0, 0, 40, 20), _quad(10, 5, 20, 15))
    prior = before.positions[before.face_v[[2]]]
    edits, engine = _plan(before, E5Coincident(flatness={}, prior_removed=prior))
    assert _dropped(edits) == [2, 3]
    assert engine.report["prior_removed"] == {"triangles": 1, "faces_checked": 2, "faces_refused": 0}
    assert engine.report["kept"]["covers_prior_removal"] == 0


def test_a_seam_some_viewpoint_sees_is_not_planned_and_is_counted():
    # the census says both fronts are hidden, but the Validator's own viewpoints see a point of one face (7F chain
    # run #2: 18,191 `deleted` samples on seams the census called hidden): the seam stays, both faces kept
    before = _partition_with_inward_twin()
    seen_one = lambda mesh, faces: np.array([3 if int(f) == 13 else 0 for f in faces], np.int64)
    edits, engine = _plan(before, E5Coincident(flatness={}, seam_view=seen_one))
    # the seen seam (13, 15) stays whole; the unseen seam (12, 14) is still planned, as one site
    assert [sorted(e.faces) for e in edits] == [[12, 14]]
    assert engine.report["interior_filtered"] == {"seams": 2, "seen": 1, "unverified": 0, "planned": 1}
    assert engine.report["kept"]["seam_seen"] == 2 and engine.report["by_rule"]["interior_twins"] == 2
    rows = [r for r in engine.report["kept_faces"] if r["kept"] == "seam_seen"]
    assert {r["face"]: r["points_seen"] for r in rows} == {13: 3, 15: 0}, "the partner stays because its seam is seen"


def test_without_a_seam_view_or_a_judge_no_seam_is_planned():
    before = _partition_with_inward_twin()
    edits, engine = _plan(before)                     # validator None, no seam_view: unverifiable, so not planned
    assert edits == []
    assert engine.report["interior_filtered"]["unverified"] == 2 and engine.report["kept"]["seam_unverified"] == 4


def test_the_judge_provides_the_seam_view_when_no_callable_is_given():
    from engine.validate.checks import CBR, Settings
    before = _partition_with_inward_twin()
    looks = _looks(*before.materials)
    unit, ctx, _ = _ctx(before, judge=SiteJudge(looks, settings=Settings(allowed_changes={CBR}), margin=2.0))
    engine = E5Coincident(flatness={})
    edits = engine.plan(unit, ctx)
    assert engine.report["interior_filtered"]["unverified"] == 0 and engine.report["interior_filtered"]["planned"] == 2
    assert len(edits) == 1


def test_the_judge_rolls_back_an_interior_seam_it_can_see_and_keeps_one_it_cannot():
    from engine.validate.checks import CBR, Settings
    before = _partition_with_inward_twin()
    looks = _looks(*before.materials)
    unit, ctx, _ = _ctx(before, judge=SiteJudge(looks, settings=Settings(allowed_changes={CBR}), margin=2.0))
    got = repair_unit(unit, ctx, engines=[E5Coincident(flatness={})], validate_sites=True)
    assert [sorted(e.faces) for e in got.kept] == [[12, 13, 14, 15]], "nothing sees the sealed partition"
    assert got.mesh.n_faces == 12


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


# ------------------------------------------------------------- the strict guard's own directions (2026-10-29)

def below_oblique_sliver(side=4.0, hole=0.3, depth=30.0, lid=0.5, ext=100.0, view=(-0.987, -0.993, 1.011)):
    """A back-to-back white pair (faces 0, 1: one triangle each, A facing -z, B facing +z) under a lid at `z = lid`
    and over a plate at `z = -depth` with one `2 * hole` square hole placed on A's centroid ray toward the camera of
    ONE below-oblique strict-guard view (`view`, rays travelling along it: the camera is below, looking up). Side
    walls join the lid and the plate. No 128-direction Fibonacci ray escapes either front (the hole subtends about
    1 degree at the pair, narrower than the lattice spacing), so the 2026-10-23 census calls both faces hidden
    (`interior_twins`); the guard's own ray through the hole sees A's front: the real 4F failure (20 sites, 328 px
    from the eight below-oblique views, diagnosis-below-oblique.json 2026-10-29)."""
    d = np.asarray(view, float)
    d = d / np.linalg.norm(d)
    w = -d                                                   # the escape direction, toward the camera
    centroid = np.array([side / 3, side / 3, 0.0])
    cross = centroid + w * (depth / -w[2])                   # where A's centroid ray crosses the plate
    hx, hy = float(cross[0]), float(cross[1])

    def rect(x0, y0, x1, y1, z, flip=False):
        c = [[x0, y0, z], [x1, y0, z], [x1, y1, z], [x0, y1, z]]
        return c[::-1] if flip else c
    tri_a = [[0, 0, 0.0], [0, side, 0.0], [side, 0, 0.0]]
    tri_b = [[0, 0, 0.0], [side, 0, 0.0], [0, side, 0.0]]
    r = hole
    quads = [rect(-ext, -ext, ext, ext, lid),
             rect(-ext, -ext, hx - r, ext, -depth, flip=True), rect(hx + r, -ext, ext, ext, -depth, flip=True),
             rect(hx - r, -ext, hx + r, hy - r, -depth, flip=True), rect(hx - r, hy + r, hx + r, ext, -depth, flip=True),
             [[-ext, -ext, -depth], [ext, -ext, -depth], [ext, -ext, lid], [-ext, -ext, lid]],
             [[ext, ext, -depth], [-ext, ext, -depth], [-ext, ext, lid], [ext, ext, lid]],
             [[-ext, ext, -depth], [-ext, -ext, -depth], [-ext, -ext, lid], [-ext, ext, lid]],
             [[ext, -ext, -depth], [ext, ext, -depth], [ext, ext, lid], [ext, -ext, lid]]]
    P, uvs, fv, fvt, fm = [], [], [], [], []
    for corners, mat in [(tri_a, 1), (tri_b, 1)] + [(q, 0) for q in quads]:
        b = len(P)
        P.extend(corners)
        for f in ([0, 1, 2], [0, 2, 3])[:1 if len(corners) == 3 else 2]:
            t0 = len(uvs)
            fv.append([b + i for i in f])
            fvt.append([t0, t0 + 1, t0 + 2])
            uvs.extend([[P[b + i][0] * UV_PER_IN, P[b + i][1] * UV_PER_IN] for i in f])
            fm.append(mat)
    return _mesh("below_oblique_sliver", P, uvs, fv, fvt, materials=("m0", "minecraft_concrete_white_-1"),
                 face_material=fm, coord_decimals=6)


def test_the_sliver_fixture_is_hidden_from_the_census_and_seen_by_one_guard_view():
    from engine.vis.exposure import compute_side_exposure
    from engine.vis.guard_exposure import guard_escape_directions, guard_front_escapes
    before = below_oblique_sliver()
    pos = before.positions
    centre = (pos.min(axis=0) + pos.max(axis=0)) / 2
    ok = np.ones(before.n_faces, bool)
    front, _back = compute_side_exposure(pos - centre, before.face_v, ok)
    assert front[0] == 0.0 and front[1] == 0.0, "the 128-direction census calls both fronts hidden"
    dirs = guard_escape_directions()
    assert dirs.shape == (52, 3), "the 26 guard views, both signs"
    escapes = guard_front_escapes(pos - centre, before.face_v, ok, dirs, faces=np.array([0, 1]))
    assert escapes[0] > 0 and escapes[1] == 0, "the guard's ray through the hole sees A's front, not B's"


def test_a_seam_the_strict_guard_can_see_from_a_below_oblique_view_is_kept():
    # the real 4F failure: both fronts hidden from the 128 Fibonacci directions, the Validator's seam view sees
    # nothing, and the strict guard's own below-oblique ray sees A's front through the hole. E5 must keep the pair.
    before = below_oblique_sliver()
    edits, engine = _plan(before, E5Coincident(flatness={}, seam_view=_unseen))
    # A (face 0) is guard-seen and stays; B's front is under the lid, so rule (c) may still drop B alone as the
    # solid-facing twin (the owner's allowed class: the guard's pixel then hits A at the same depth) -- never as an
    # interior seam, and never A
    assert 0 not in _dropped(edits), "a face the guard can see is never removed"
    assert all(row["rule"] == "backface_twin" for e in edits for row in e.evidence["pairs"])
    report = engine.report
    assert report["exposure_n_dirs"] == 128 and report["exposure_directions_total"] == 128 + 52
    guard = report["guard_exposure"]
    assert guard["views"] == 26 and guard["directions"] == 52 and guard["samples_per_face"] >= 7
    assert guard["faces_tested"] >= 2 and guard["seen_front"] >= 1
    assert guard["census_hidden_guard_seen"] >= 1, "A: census front 0, guard-seen"
    assert report["by_rule"]["interior_twins"] == 0 and report["interior_filtered"]["planned"] == 0
    rows = [row for e in edits for row in e.evidence["pairs"]]
    assert all(row["face"] == 1 and row["guard_front"] == 0 and row["front"] == 0.0 for row in rows), "only B, hidden in both tests"
    assert all(row["winners"] == [0] for row in rows), "A, which the guard sees, is the winner"


def test_the_guard_pixel_grid_sees_the_outer_faces_of_a_box_and_not_its_partition():
    from engine.tests.fixtures.build import box_with_partition
    from engine.vis.guard_exposure import guard_pixel_hits
    mesh = box_with_partition()
    pos = mesh.positions
    centre = (pos.min(axis=0) + pos.max(axis=0)) / 2
    ok = np.ones(mesh.n_faces, bool)
    front_px, back_px = guard_pixel_hits(pos - centre, mesh.face_v, ok, size=(90, 60), scales=(1, 2))
    assert front_px.shape == (14,) and back_px.shape == (14,)
    assert (front_px[:12] > 0).all(), "every outward cube face owns a pixel from its front in some view"
    assert front_px[12] == 0 and front_px[13] == 0 and back_px[12] == 0 and back_px[13] == 0, "the sealed partition owns none"
    assert (back_px[:12] == 0).all(), "a closed box's faces are never hit from the back"
