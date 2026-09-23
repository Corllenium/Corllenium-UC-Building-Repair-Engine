import pytest

from engine.pipeline import FLAT_TEXTURE_STD, analyse_topology, flat_material_indices
from engine.tests.fixtures.build import cube


def _mesh_with_materials(names):
    m = cube(10.0)
    m.materials = list(names)
    return m


def test_flat_material_indices_maps_names_to_indices():
    m = _mesh_with_materials(["stone", "paint", "brick"])
    flatness = {"stone": 40.0, "brick": 2.0}
    assert flat_material_indices(m, flatness) == frozenset({1, 2})


def test_untextured_material_with_no_flatness_entry_is_flat():
    m = _mesh_with_materials(["plain"])
    assert flat_material_indices(m, {}) == frozenset({0})


def test_patterned_material_above_threshold_is_not_flat():
    m = _mesh_with_materials(["pattern"])
    assert FLAT_TEXTURE_STD == 8.0
    assert flat_material_indices(m, {"pattern": 120.0}) == frozenset()


def test_analyse_topology_raises_type_error_on_material_name_in_flat_materials():
    m = cube(10.0)
    with pytest.raises(TypeError):
        analyse_topology(m, flat_materials=frozenset({"m0"}))


# ---------------------------------------------------------------------------------------------
# Task 6: engine.fixes.pipeline.fix_object -- the full remove+merge+guard pipeline.
#
# This file already existed for engine.pipeline (analyse_topology, above); the task-6 brief names
# this same path ("engine/tests/test_pipeline.py") for fix_object's tests too, so they are
# appended here rather than creating a second, confusingly-similar file name.
# ---------------------------------------------------------------------------------------------
import numpy as np

import engine.fixes.pipeline as fix_pipeline
from engine.fixes.merge import MergeResult
from engine.fixes.orient import ORIENT_FLIP
from engine.fixes.pipeline import FixProfile, fix_object
from engine.fixes.remove import remove_faces
from engine.tests.fixtures.build import _mesh, box_with_partition, gridded_box, open_box_with_cells
from engine.vis.exposure import EXP_HIDDEN, EXP_OUTSIDE, EXP_SLIT, compute_side_exposure

#: Small render settings: only correctness is under test here, not image fidelity (matches the
#: convention in test_guard.py / test_exposure.py).
_FAST = FixProfile(guard_size=(120, 80), n_dirs=32)


def _fast(**overrides):
    return FixProfile(guard_size=(120, 80), n_dirs=32, **overrides)


def _centered(mesh):
    """analyse_topology + recentre positions_w to the bbox centre, as compute_exposure/
    ortho_first_hit require."""
    topo = analyse_topology(mesh)
    centre = (topo.positions_w.min(axis=0) + topo.positions_w.max(axis=0)) / 2
    return topo, topo.positions_w - centre


def test_box_with_partition_removes_only_the_sealed_partition():
    m = box_with_partition()
    r = fix_object(m, {}, _FAST)

    assert r.exposure_class[12] == EXP_HIDDEN and r.exposure_class[13] == EXP_HIDDEN
    assert (r.exposure_class[:12] == EXP_OUTSIDE).all()
    assert r.n_hidden_candidates == 2
    assert r.n_removed_hidden == 2 and r.n_restored_by_guard == 0
    assert r.n_removed_slit == 0 and r.n_zero_area_dropped == 0
    assert r.removed_hidden.tolist() == [i in (12, 13) for i in range(m.n_faces)]
    assert not r.removed_slit.any()

    # the 12 outer cube triangles are untouched by removal and cannot merge further (each cube
    # face is already the minimal 2 triangles), so the mesh stays at exactly 12.
    assert m.n_faces == 14 and r.mesh.n_faces == 12
    assert r.merge_report["regions_merged"] == 6
    assert "rolled_back" not in r.merge_report

    assert r.invariants == {"material_count_same": True, "bbox_same": True,
                            "area_not_grown": True, "guard_passed": True}
    assert r.passed is True
    assert r.guard_final.totals["holes"] == 0
    assert r.guard_final.totals["moved_same_flat"] == 0
    assert r.guard_final.totals["moved_other"] == 0
    assert r.feedback_history["hidden"][0]["candidates_remaining"] == 2
    assert r.feedback_history["slit"] is None  # no slit pass ran: no slit candidates exist here

    # task 8: a correctly-wound cube needs no flips, has no thin sheets, and is already complete
    # one-sided (a closed convex box's outward faces are never back-facing to any outside camera).
    assert not r.flipped.any()
    assert not r.thin_sheets.any()
    assert r.one_sided_holes_before == 0
    assert r.one_sided_holes_after == 0

    # source_faces: each output face's provenance is its whole (unchanged, 2-member) region --
    # merge_regions never split a region across output triangles, so both triangles of a cube
    # face share the same 2-member source list.
    assert len(r.source_faces) == 12
    assert sorted(len(s) for s in r.source_faces) == [2] * 12
    assert sorted(set(int(f) for s in r.source_faces for f in s)) == list(range(12))

    # task 9 / M2: each of the 6 cube faces is a hole-free single-piece region -> loops for every
    # row, a 4-vertex outer loop and no inner one.
    assert set(r.rings.keys()) == set(range(12))
    assert all(len(loops["outer"]) == 4 and loops["inners"] == [] for loops in r.rings.values())


def test_gridded_closed_box_has_nothing_hidden_and_merges_to_twelve_triangles():
    m = gridded_box(4, 2.5)
    r = fix_object(m, {}, _FAST)

    assert m.n_faces == 192
    assert not (r.exposure_class == EXP_HIDDEN).any()
    assert not (r.exposure_class == EXP_SLIT).any()
    assert r.n_hidden_candidates == 0 and r.n_removed_hidden == 0
    assert r.n_removed_slit == 0 and r.n_zero_area_dropped == 0

    assert r.mesh.n_faces == 12
    assert r.merge_report["regions_merged"] == 6
    assert r.merge_report["tris_before"] == 192 and r.merge_report["tris_after"] == 12
    assert "rolled_back" not in r.merge_report

    assert r.passed is True
    assert r.invariants["guard_passed"] is True
    assert r.guard_final.totals["holes"] == 0
    assert r.guard_final.totals["moved_same_flat"] == 0
    assert r.guard_final.totals["moved_other"] == 0

    # every merged face's provenance is its whole 32-triangle grid region (a 4x4 cell face, 2
    # triangles per cell); each of the 6 regions' 2 output triangles share that same source list.
    assert len(r.source_faces) == 12
    assert sorted(len(s) for s in r.source_faces) == [32] * 12
    assert sorted(set(int(f) for s in r.source_faces for f in s)) == list(range(192))


def test_fix_object_is_deterministic():
    m = gridded_box(3, 2.5)
    a = fix_object(m, {}, _FAST)
    b = fix_object(m, {}, _FAST)

    assert np.array_equal(a.mesh.face_v, b.mesh.face_v)
    assert np.array_equal(a.mesh.face_vt, b.mesh.face_vt)
    assert np.array_equal(a.mesh.face_vn, b.mesh.face_vn)
    assert np.array_equal(a.mesh.uvs, b.mesh.uvs)
    assert a.merge_report == b.merge_report
    assert a.invariants == b.invariants
    assert a.passed == b.passed
    assert a.guard_final.totals == b.guard_final.totals
    assert [s.tolist() for s in a.source_faces] == [s.tolist() for s in b.source_faces]


def test_accept_slit_removes_a_barely_exposed_interior_face_under_a_colour_tolerant_guard():
    m = open_box_with_cells()  # faces 12-13 ("deep" partition) are EXP_SLIT, not EXP_HIDDEN

    left_alone = fix_object(m, {}, _fast(accept_slit=False, solidify=False))
    assert left_alone.n_removed_slit == 0
    assert left_alone.mesh.n_faces == 14  # nothing removed beyond zero-area (there is none)
    assert left_alone.feedback_history["slit"] is None
    assert left_alone.passed is True

    # flatness={}: every material (just "m0" here) counts as flat with no texture-std entry, so
    # the colour-tolerant (strict=False) slit guard may accept a moved_same_flat pixel.
    accepted = fix_object(m, {}, _fast(accept_slit=True, solidify=False))
    assert accepted.n_removed_slit == 2
    assert accepted.removed_slit.tolist() == [i in (12, 13) for i in range(m.n_faces)]
    assert accepted.mesh.n_faces == 12  # the two deep-partition triangles are gone
    assert accepted.feedback_history["slit"] is not None
    assert accepted.passed is True
    assert accepted.guard_final.totals["holes"] == 0


def test_rolled_back_when_merge_does_not_converge(monkeypatch):
    """A merge whose own report says `converged: False` is treated exactly like a failed final
    guard: roll back to the removal-only mesh and record why."""
    m = gridded_box(4, 2.5)  # merge_regions would otherwise collapse this 192 -> 12
    real_merge_regions = fix_pipeline.merge_regions

    def not_converged(mesh, topo, flat_materials=frozenset(), **kw):
        real = real_merge_regions(mesh, topo, flat_materials, **kw)
        report = dict(real.report)
        report["converged"] = False
        return MergeResult(mesh=real.mesh, source_faces=real.source_faces, report=report)

    monkeypatch.setattr(fix_pipeline, "merge_regions", not_converged)
    r = fix_object(m, {}, _FAST)

    assert r.merge_report["rolled_back"] is True
    assert r.merge_report["rolled_back_reason"] == "not_converged"
    # the un-merged (removal-only) mesh: identical to the input, nothing was hidden to remove
    assert r.mesh.n_faces == m.n_faces == 192
    assert np.array_equal(r.mesh.face_v, m.face_v)
    assert np.array_equal(r.mesh.face_vt, m.face_vt)
    assert [s.tolist() for s in r.source_faces] == [[i] for i in range(192)]
    assert r.passed is True  # the fallback's own guard: identical geometry, so it still passes
    assert r.invariants["guard_passed"] is True
    assert r.rings == {}  # rolled back to the unmerged mesh: no merge rings apply to it
    # a merge that never converged produced no mesh to guard, so there is no report to keep
    assert r.guard_merge_attempt is None


# ---------------------------------------------------------------------------------------------
# Task 8: outward orientation wired into fix_object.
# ---------------------------------------------------------------------------------------------

def test_fix_object_flips_a_reversed_interior_triangle_and_still_fully_merges():
    """gridded_box's cell-(1,1) triangle on the z=0 face (global index 10, an interior cell of
    that face -- not on any face boundary) is deliberately reversed, as a SketchUp export might
    export one mis-wound triangle inside an otherwise-consistent panel. Before the flip step, a
    reversed triangle fails cluster_planes' facing_dot test against its neighbours (normals point
    opposite ways) and so cannot join their region; after the flip it rejoins them, and the panel
    still merges down to its minimal 2 triangles."""
    m = gridded_box(4, 2.5)
    reversed_face = 10
    m.face_v[reversed_face] = m.face_v[reversed_face][::-1]

    r = fix_object(m, {}, _FAST)

    assert r.flipped.tolist() == [i == reversed_face for i in range(m.n_faces)]
    assert not r.thin_sheets.any()
    assert r.one_sided_holes_before > 0
    assert r.one_sided_holes_after == 0

    assert r.mesh.n_faces == 12
    assert r.merge_report["regions_merged"] == 6
    assert "rolled_back" not in r.merge_report
    assert r.passed is True
    assert r.invariants["guard_passed"] is True


def test_flip_step_never_introduces_guard_damage():
    """A model with one legitimately reversed triangle still ends with a spotless (all-zero)
    guard report, exactly like the unmodified fixture -- flipping never changes a double-sided
    render (test_orient.py pins that at the primitive level), so it can never be what causes a
    guard failure."""
    baseline = fix_object(gridded_box(4, 2.5), {}, _FAST)
    m = gridded_box(4, 2.5)
    m.face_v[10] = m.face_v[10][::-1]
    reversed_input = fix_object(m, {}, _FAST)

    assert baseline.passed and reversed_input.passed
    assert baseline.guard_after_removal.totals == reversed_input.guard_after_removal.totals
    assert baseline.guard_final.totals == reversed_input.guard_final.totals


def test_render_reuses_one_caster_across_all_26_views(monkeypatch):
    """Task 7 perf fix: fix_object's internal `_render` (used for the before/after facade-guard
    renders) builds ONE caster for its geometry and reuses it across all 26 views."""
    from engine.rays.caster import EmbreeCaster

    builds = []
    real_init = EmbreeCaster.__init__

    def counting_init(self, positions, faces):
        builds.append(1)
        real_init(self, positions, faces)

    monkeypatch.setattr(EmbreeCaster, "__init__", counting_init)

    m = box_with_partition()
    topo, Pc = _centered(m)
    fix_pipeline._render(Pc, topo.face_w, (60, 40))
    assert len(builds) == 1


def test_fix_object_reports_a_thin_sheet_without_touching_it():
    """A free-standing quad, alone in space: both sides see the same open sky, so it classes
    THIN_SHEET (never FLIP, never removed as hidden/slit, never changed by the merge)."""
    P = [[0, 0, 0], [10, 0, 0], [10, 10, 0], [0, 10, 0]]
    uvs = [[0, 0], [1, 0], [1, 1], [0, 1]]
    fv = [[0, 1, 2], [0, 2, 3]]
    fvt = [[0, 1, 2], [0, 2, 3]]
    m = _mesh("free_quad", P, uvs, fv, fvt)

    # `solidify=False`: a free quad IS a top surface with four open edges, so the default profile
    # skirts it and puts a bottom under it, which is S1's own subject (`test_solidify.py`). This
    # test is about ORIENTATION -- what `classify_orientation` does with a sheet seen from both
    # sides -- and it needs the two faces it was written for.
    r = fix_object(m, {}, _fast(solidify=False))

    assert r.thin_sheets.tolist() == [True, True]
    assert not r.flipped.any()
    assert r.mesh.n_faces == m.n_faces  # untouched: not removed, not merged differently
    assert r.passed is True


def test_a_free_standing_quad_seen_from_both_sides_is_a_sheet_not_a_flip():
    """R1a, end to end. A 10x10 quad with a 6x6 awning floating 3 in over it: the awning takes a
    bite out of the quad's FRONT hemisphere, so its back sees more sky (measured front 0.391 /
    back 0.500) and the old `back > front` rule flipped it. Both sides are plainly exposed, so it
    is a sheet -- reported, never touched. The review found about 35 such faces flipped on file A,
    each opening a one-sided hole."""
    P = [[0, 0, 0], [10, 0, 0], [10, 10, 0], [0, 10, 0],
         [2, 2, 3], [8, 2, 3], [8, 8, 3], [2, 8, 3]]
    uvs = [[0, 0], [1, 0], [1, 1], [0, 1]]
    fv = [[0, 1, 2], [0, 2, 3], [4, 5, 6], [4, 6, 7]]
    fvt = [[0, 1, 2], [0, 2, 3], [0, 1, 2], [0, 2, 3]]
    m = _mesh("sheet_under_awning", P, uvs, fv, fvt)

    topo, Pc = _centered(m)
    front, back = compute_side_exposure(Pc, topo.face_w, topo.ok, n_dirs=_FAST.n_dirs)
    assert (back[:2] > front[:2]).all()                       # the old rule's whole test
    assert (np.minimum(front, back)[:2] / np.maximum(front, back)[:2] >= 0.5).all()

    r = fix_object(m, {}, _FAST)

    assert not r.flipped.any()                                # nothing here was wound backwards
    assert r.thin_sheets[0] and r.thin_sheets[1]
    assert r.one_sided_holes_after <= r.one_sided_holes_before
    assert r.passed is True


# ---------------------------------------------------------------------------------------------
# E1: degenerate faces are removed only through the strict guard.
#
# `degenerate_mask` is RELATIVE (`area <= 1e-7 * longest**2`), so a 1,000 in sliver up to 0.0002 in
# wide counts as "zero area" although it is a real, hittable surface. Dropping those unconditionally
# (as the pipeline did) changed the picture with no guard check at all -- 12 `material_changed`
# pixels on file B. They are now ordinary pass-1 candidates, judged by the same strict guard.
# ---------------------------------------------------------------------------------------------

from engine.guard.views import VIEWS_26, ortho_first_hit
from engine.tests.fixtures.build import box_with_partition_and_stitch, floor_with_sliver, t_junction_strip


def _empty_camera(positions_c, view, size):
    """The camera `ortho_first_hit` builds for `positions_c` at `size`, with no geometry at all:
    `xs`/`ys` are the image-plane offsets of every pixel centre, so a test can aim a chosen
    pixel's ray at a chosen point."""
    return ortho_first_hit(positions_c, np.zeros((0, 3), np.int64), np.zeros(0, np.int64),
                            view, positions_c, size)


def test_a_genuinely_collinear_zero_area_face_is_still_removed():
    """The T-junction stitching triangle `(0,10,0)-(10,10,0)-(20,10,0)` has exactly zero area: no
    ray can ever hit it, so the strict guard sees not one changed pixel and confirms the drop."""
    m = t_junction_strip()
    r = fix_object(m, {}, _FAST)

    assert m.n_faces == 7
    assert r.n_zero_area_dropped == 1
    assert r.n_degenerate_restored == 0
    assert not r.restored_degenerate.any()
    assert r.guard_after_removal.passed is True
    assert r.passed is True


def test_hidden_numbers_are_unchanged_by_a_zero_area_face_sharing_the_mesh():
    """The hidden pass now runs over ALL faces (degenerate ones included) and splits the guard's
    verdict afterwards, so a stitching triangle in the same mesh must not move a single hidden
    number: same candidates, same removals, same restores as the stitch-free fixture."""
    plain = fix_object(box_with_partition(), {}, _FAST)
    stitched = fix_object(box_with_partition_and_stitch(), {}, _FAST)

    assert (stitched.n_hidden_candidates, stitched.n_removed_hidden, stitched.n_restored_by_guard) \
        == (plain.n_hidden_candidates, plain.n_removed_hidden, plain.n_restored_by_guard) == (2, 2, 0)
    assert stitched.removed_hidden.tolist()[:14] == plain.removed_hidden.tolist()
    assert stitched.removed_hidden[14] == False  # the stitch is degenerate, never "hidden"
    assert stitched.n_zero_area_dropped == 1 and stitched.n_degenerate_restored == 0
    assert stitched.mesh.n_faces == plain.mesh.n_faces == 12
    assert stitched.passed is True


def test_a_sliver_that_only_the_relative_test_calls_zero_area_is_kept_by_the_guard():
    """A 1,000 in x 0.0001 in sliver of material 1, floating over a floor of material 0: real,
    hittable geometry that `degenerate_mask`'s relative test calls zero-area. A pixel ray is aimed
    straight through it (framing computed from `ortho_first_hit`'s own camera), so dropping it
    swaps that pixel's material -- which the strict guard must refuse.

    The view has to be the STRAIGHT-DOWN one, not merely one that looks downwards: embree takes
    ray origins as float32 and `ortho_first_hit` stands the camera off by `2 * diag` (~3,400
    here), so on a corner-diagonal view all three origin components are ~2,000 and lateral
    position quantises to ~1.2e-4 -- wider than the sliver itself. Straight down, only the z
    component is large (and z error slides along the ray, not across it) while x/y are ~40,
    quantised to ~4e-6, which resolves a 1e-4 sliver comfortably."""
    view = min(VIEWS_26, key=lambda v: float(np.linalg.norm(np.asarray(v) - np.array([0.0, 0.0, -1.0]))))
    size = _FAST.guard_size

    # The framing depends on the floor corners and the sliver's x/z extent, never on where along
    # y its centre line sits -- so a placeholder build gives the same camera as the final one.
    topo_p, pc_p = _centered(floor_with_sliver())
    cam = _empty_camera(pc_p, view, size)
    centre = (topo_p.positions_w.min(axis=0) + topo_p.positions_w.max(axis=0)) / 2.0

    row, col = size[1] // 2, size[0] // 2
    origin = float(cam.xs[col]) * cam.right + float(cam.ys[row]) * cam.up + cam.standoff
    z_plane = 5.0 - centre[2]                   # the sliver's own plane, in the recentred frame
    aim = origin + (z_plane - origin[2]) / cam.direction[2] * cam.direction

    m = floor_with_sliver(apex_x=round(float(aim[0] + centre[0]), 6),
                          centre_y=round(float(aim[1] + centre[1]), 6))
    topo, pc = _centered(m)
    cam2 = _empty_camera(pc, view, size)
    assert np.array_equal(cam.xs, cam2.xs) and np.array_equal(cam.ys, cam2.ys)
    assert np.array_equal(cam.standoff, cam2.standoff)

    # the sliver really is "degenerate", and that pixel's ray really does hit it in BEFORE
    assert topo.ok.tolist() == [True, True, False]
    before = ortho_first_hit(pc, topo.face_w, np.arange(m.n_faces), view, pc, size)
    assert before.tri[row, col] == 2

    # `solidify=False`: the floor is a top surface with four open edges, so the default profile
    # skirts it -- which changes the scene this test aimed a pixel at. The subject here is the
    # degenerate-sliver guard, unchanged by S1.
    r = fix_object(m, {}, _fast(solidify=False))

    assert r.n_degenerate_restored >= 1
    assert r.restored_degenerate.tolist() == [False, False, True]
    assert r.n_zero_area_dropped == 0
    assert r.guard_after_removal.passed is True
    assert int((r.mesh.face_material == 1).sum()) == 1   # the sliver survives into the result


# ---------------------------------------------------------------------------------------------
# E3: what the pipeline does when the FINAL guard fails, and what the post-removal guard says.
# ---------------------------------------------------------------------------------------------

def test_rolled_back_when_the_final_guard_fails_and_guard_final_is_the_shipped_mesh(monkeypatch):
    """A merge that converges but loses a visible face must be discarded, and `guard_final` must
    then describe the mesh actually SHIPPED -- not the candidate that was thrown away. If it
    described the candidate it would be full of holes and `passed` would be False; it is spotless,
    because the shipped mesh is the flipped-but-unmerged one, which is this fixture unchanged."""
    m = gridded_box(4, 2.5)       # 192 tris, nothing hidden, nothing degenerate, merges to 12
    real_merge_regions = fix_pipeline.merge_regions

    def loses_a_visible_face(mesh, topo, flat_materials=frozenset(), **kw):
        real = real_merge_regions(mesh, topo, flat_materials, **kw)
        drop = np.zeros(real.mesh.n_faces, dtype=bool)
        drop[0] = True            # half of one outer cube side: a hole nobody can miss
        broken, kept = remove_faces(real.mesh, drop)
        return MergeResult(mesh=broken, source_faces=[real.source_faces[i] for i in kept],
                           report=dict(real.report))

    monkeypatch.setattr(fix_pipeline, "merge_regions", loses_a_visible_face)
    r = fix_object(m, {}, _FAST)

    assert r.merge_report["converged"] is True          # the merge itself was fine; its RESULT was not
    assert r.merge_report["rolled_back"] is True
    assert r.merge_report["rolled_back_reason"] == "guard_failed"

    # the flipped-but-unmerged mesh: this fixture needs no flips and loses no faces, so 192
    assert r.mesh.n_faces == m.n_faces == 192
    assert np.array_equal(r.mesh.face_v, m.face_v)
    assert [s.tolist() for s in r.source_faces] == [[i] for i in range(192)]
    assert r.rings == {}

    # guard_final is THAT mesh's guard, and it passes
    assert r.guard_final.passed is True
    assert {k: v for k, v in r.guard_final.totals.items() if k != "model_px"} \
        == {k: 0 for k in r.guard_final.totals if k != "model_px"}
    assert r.guard_final.totals["model_px"] > 0
    assert r.invariants["guard_passed"] is True
    assert r.passed is True

    # M0: the report that CAUSED the rollback is kept, or the failure is invisible. It describes
    # the discarded candidate, so it fails and says exactly which views and pixels did it.
    assert r.guard_merge_attempt is not None
    assert r.guard_merge_attempt.passed is False
    # the fixture is a CLOSED box, so a lost outer face shows the far inner wall rather than sky:
    # the damage is `moved_same_flat`, which fails because this run's final guard is strict.
    assert r.guard_merge_attempt.totals["moved_same_flat"] > 0
    assert r.guard_merge_attempt.totals["holes"] == 0
    assert len(r.guard_merge_attempt.views) == 26
    assert sum(v.moved_same_flat > 0 for v in r.guard_merge_attempt.views) > 1
    assert r.guard_merge_attempt is not r.guard_final


def test_guard_merge_attempt_is_the_final_guard_when_the_merge_is_kept():
    """No rollback: the merged mesh IS the shipped mesh, so its guard is both the merge attempt's
    report and the final one."""
    r = fix_object(box_with_partition(), {}, _FAST)

    assert "rolled_back" not in r.merge_report
    assert r.guard_merge_attempt is not None
    assert r.guard_merge_attempt.passed is True
    assert r.guard_merge_attempt.totals == r.guard_final.totals


def test_guard_after_removal_is_spotless_on_box_with_partition():
    """The post-removal (pre-merge) guard compares the flipped, hidden-face-free mesh against the
    pristine original over all 26 views. Removing a partition sealed inside a closed box cannot
    change one pixel of it, so every total -- holes, material changes, moves, and every flicker
    class -- has to be exactly zero."""
    r = fix_object(box_with_partition(), {}, _FAST)

    assert r.n_removed_hidden == 2
    assert r.guard_after_removal.passed is True
    assert {k: v for k, v in r.guard_after_removal.totals.items() if k != "model_px"} \
        == {k: 0 for k in r.guard_after_removal.totals if k != "model_px"}
    assert r.guard_after_removal.totals["model_px"] > 0
    assert len(r.guard_after_removal.views) == 26
    assert all(v.holes == 0 and v.material_changed == 0 and v.moved_same_flat == 0
               and v.moved_other == 0 and v.edge_flicker == 0 for v in r.guard_after_removal.views)


# ---------------------------------------------------------------------------------------------
# G1: the guard's depth tolerance has a CEILING. It is derived from the mesh's own print
# precision (`1.5 * max(axis quanta)`), which is right for a model near 24,000 in (0.15 in) and
# wrong for one exported in survey coordinates near 240,000 in, where the same formula gives
# 1.5 in -- and the crack test's ring radius IS that tolerance, so anything thinner than it reads
# as a closed crack. `FixProfile.depth_tol_max` bounds it.
# ---------------------------------------------------------------------------------------------

def _far_from_origin(mesh, offset=240_000.0):
    """The same mesh, shifted so `axis_quanta` gives it a 1.0 in print step on x."""
    from dataclasses import replace
    return replace(mesh, positions=mesh.positions + np.array([offset, 0.0, 0.0]))


def test_guard_depth_tol_is_one_and_a_half_quanta_until_it_hits_the_ceiling():
    profile = FixProfile()
    assert profile.depth_tol_max == 0.5
    assert fix_pipeline.guard_depth_tol(np.array([0.001, 0.1, 0.001]), profile) == 1.5 * 0.1
    assert fix_pipeline.guard_depth_tol(np.array([1.0, 0.1, 0.001]), profile) == 0.5
    assert fix_pipeline.guard_depth_tol(np.array([1.0, 0.1, 0.001]),
                                        _fast(depth_tol_max=10.0)) == 1.5


def test_fix_object_clamps_the_depth_tolerance_of_a_survey_coordinate_model(monkeypatch):
    """End to end: the number `guard_feedback` and both `compare_views` calls are handed."""
    seen = []
    real = fix_pipeline.guard_feedback

    def spy(candidates, positions_c, faces, material, flat, depth_tol, *args, **kwargs):
        seen.append(depth_tol)
        return real(candidates, positions_c, faces, material, flat, depth_tol, *args, **kwargs)

    monkeypatch.setattr(fix_pipeline, "guard_feedback", spy)

    near = box_with_partition(10.0)
    topo = analyse_topology(_far_from_origin(near))
    assert 1.5 * float(topo.quanta.max()) == 1.5      # unclamped, this model would get 1.5 in

    fix_object(_far_from_origin(near), {}, _fast())
    assert seen and set(seen) == {0.5}

    seen.clear()
    fix_object(near, {}, _fast())
    assert seen and max(seen) < 0.5                    # a small model is nowhere near the ceiling


# ---------------------------------------------------------------------------------------------
# O1: the duplicate-layer removal, seen from `fix_object` -- in the pipeline, before the merge,
# with every face id reported against the ORIGINAL mesh.
# ---------------------------------------------------------------------------------------------

def test_fix_object_removes_a_duplicate_layer_and_then_merges_the_slab():
    from engine.tests.fixtures.build import stacked_duplicate_slab
    m = stacked_duplicate_slab(nx=3, ny=3)
    n = m.n_faces // 2
    r = fix_object(m, {}, _fast())

    assert r.n_overlap_pairs_same == n and r.n_overlap_pairs_diff == 0
    assert r.n_removed_overlap == n and r.n_restored_overlap == 0
    assert r.removed_overlap.tolist() == [False] * n + [True] * n
    assert not r.restored_overlap.any()
    # the duplicate is what stopped the merge: with it gone the slab is one region again
    assert r.merge_report["regions_merged"] == 1
    assert r.merge_report["regions_skipped"] == {}
    assert r.mesh.n_faces == 2
    assert r.passed is True


def test_fix_object_reports_a_different_material_overlap_with_original_face_ids():
    from engine.tests.fixtures.build import stacked_duplicate_slab
    m = stacked_duplicate_slab(nx=3, ny=3, top_material=1)
    n = m.n_faces // 2
    r = fix_object(m, {}, _fast())

    assert r.n_overlap_pairs_same == 0 and r.n_overlap_pairs_diff == n
    assert r.n_removed_overlap == 0 and not r.removed_overlap.any()
    pairs = r.overlap_pairs_diff_material
    assert len(pairs) == n
    assert sorted(tuple(e["faces"]) for e in pairs) == [(f, f + n) for f in range(n)]
    assert all(sorted(e["materials"]) == [0, 1] for e in pairs)


def test_a_mesh_with_no_overlap_reports_zeroes_and_is_otherwise_unchanged():
    r = fix_object(box_with_partition(), {}, _fast())
    assert (r.n_overlap_pairs_same, r.n_overlap_pairs_diff) == (0, 0)
    assert (r.n_removed_overlap, r.n_restored_overlap) == (0, 0)
    assert r.overlap_pairs_diff_material == []
    assert r.mesh.n_faces == 12 and r.passed is True
