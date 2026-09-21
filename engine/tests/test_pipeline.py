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
from engine.tests.fixtures.build import _mesh, box_with_partition, gridded_box, open_box_with_cells
from engine.vis.exposure import EXP_HIDDEN, EXP_OUTSIDE, EXP_SLIT

#: Small render settings: only correctness is under test here, not image fidelity (matches the
#: convention in test_guard.py / test_exposure.py).
_FAST = FixProfile(guard_size=(120, 80), n_dirs=32)


def _fast(**overrides):
    return FixProfile(guard_size=(120, 80), n_dirs=32, **overrides)


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

    # task 9: each of the 6 cube faces is a hole-free single-piece region -> a ring for every row.
    assert set(r.rings.keys()) == set(range(12))
    assert all(len(ring) == 4 for ring in r.rings.values())


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

    left_alone = fix_object(m, {}, _fast(accept_slit=False))
    assert left_alone.n_removed_slit == 0
    assert left_alone.mesh.n_faces == 14  # nothing removed beyond zero-area (there is none)
    assert left_alone.feedback_history["slit"] is None
    assert left_alone.passed is True

    # flatness={}: every material (just "m0" here) counts as flat with no texture-std entry, so
    # the colour-tolerant (strict=False) slit guard may accept a moved_same_flat pixel.
    accepted = fix_object(m, {}, _fast(accept_slit=True))
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


def test_fix_object_reports_a_thin_sheet_without_touching_it():
    """A free-standing quad, alone in space: both sides see the same open sky, so it classes
    THIN_SHEET (never FLIP, never removed as hidden/slit, never changed by the merge)."""
    P = [[0, 0, 0], [10, 0, 0], [10, 10, 0], [0, 10, 0]]
    uvs = [[0, 0], [1, 0], [1, 1], [0, 1]]
    fv = [[0, 1, 2], [0, 2, 3]]
    fvt = [[0, 1, 2], [0, 2, 3]]
    m = _mesh("free_quad", P, uvs, fv, fvt)

    r = fix_object(m, {}, _FAST)

    assert r.thin_sheets.tolist() == [True, True]
    assert not r.flipped.any()
    assert r.mesh.n_faces == m.n_faces  # untouched: not removed, not merged differently
    assert r.passed is True
