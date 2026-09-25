"""O1: covered same-material duplicate layers, found and removed under the strict guard.

Measured on file A's removal-stage mesh: 120 overlapping coplanar pairs, all the same material,
over 133 faces in 25 regions -- the walkway carries a second copy of its own surface. The merge
excludes an overlapping triangle from its union (rule 3) and skips a region whose union still
overlaps, so those 133 faces and every triangle around them were copied through unmerged and
their gridlines drawn.
"""
import numpy as np

from engine.fixes import merge as merge_module
from engine.fixes import overlap as overlap_module
from engine.fixes.merge import merge_regions
from engine.fixes.overlap import (COVERED_FRACTION, _patch_of, covered_fractions, find_overlaps,
                                  plan_overlap_removal, remove_overlaps)
from engine.pipeline import analyse_topology
from engine.tests.fixtures.build import (grid_slab, partially_overlapping_fins,
                                         stacked_duplicate_slab)

_SIZE = (120, 80)   #: small renders: correctness only, per the convention in the other files


def _centred(mesh):
    topo = analyse_topology(mesh)
    centre = (topo.positions_w.min(axis=0) + topo.positions_w.max(axis=0)) / 2.0
    return topo, topo.positions_w - centre


def _removed(mesh, **kw):
    topo, positions_c = _centred(mesh)
    return remove_overlaps(mesh, topo, positions_c, frozenset({0, 1}),
                           1.5 * float(topo.quanta.max()), guard_size=_SIZE, **kw)


# --------------------------------------------------------------------------------- find_overlaps


def test_find_overlaps_pairs_every_duplicated_face_with_its_own_copy():
    m = stacked_duplicate_slab(nx=3, ny=3)
    topo = analyse_topology(m)
    pairs = find_overlaps(m, topo)
    n = m.n_faces // 2

    assert len(pairs) == n                       # one pair per duplicated face, nothing else
    assert all(same for _i, _j, _a, same in pairs)
    assert sorted((i, j) for i, j, _a, _s in pairs) == [(f, f + n) for f in range(n)]
    assert all(a > 0.0 for _i, _j, a, _s in pairs)


def test_find_overlaps_sees_across_regions_into_the_same_plane():
    """The different-material copies are their own regions, so a per-region search could not see
    them at all. The unit of an overlap is the PLANE, not the region."""
    m = stacked_duplicate_slab(nx=3, ny=3, top_material=1)
    topo = analyse_topology(m)
    n = m.n_faces // 2
    assert len(set(topo.face_region[:n].tolist())) < len(set(topo.face_region.tolist()))

    pairs = find_overlaps(m, topo)
    assert len(pairs) == n
    assert not any(same for _i, _j, _a, same in pairs)


def test_find_overlaps_ignores_faces_that_merely_touch_along_an_edge():
    """Every neighbouring pair in a grid shares an edge and so `intersects`; none of them
    overlaps. The area threshold, not the STRtree predicate, is what decides."""
    assert find_overlaps(grid_slab(6, 6), analyse_topology(grid_slab(6, 6))) == []


def test_find_overlaps_is_the_test_the_merge_excludes_triangles_with():
    """Rule 3 of the merge is the same question, asked of one region's own triangles."""
    assert merge_module._overlap_excluded is overlap_module.overlap_excluded


# -------------------------------------------------------------------------------------- coverage


def test_a_duplicated_face_is_fully_covered_by_the_rest_of_its_region():
    m = stacked_duplicate_slab(nx=3, ny=3)
    topo = analyse_topology(m)
    covered = covered_fractions(topo, list(range(m.n_faces)))
    assert min(covered.values()) > 0.999


def test_a_partial_overlap_is_never_a_candidate():
    """The two fins overlap each other over exactly half of each (187.5 of 375 sq in) and overlap
    no slab face, so they are a real same-material pair in which neither face is covered."""
    m = partially_overlapping_fins()
    topo = analyse_topology(m)
    fins = [m.n_faces - 2, m.n_faces - 1]

    pairs = find_overlaps(m, topo)
    assert [(i, j, s) for i, j, _a, s in pairs] == [(fins[0], fins[1], True)]

    covered = covered_fractions(topo, fins)
    assert all(abs(covered[f] - 0.5) < 1e-9 for f in fins), covered
    plan = plan_overlap_removal(m, topo)
    assert not plan.candidates.any()
    assert not plan.remove.any()


# -------------------------------------------------------------------------------- the removal


def test_an_exactly_duplicated_layer_loses_exactly_one_copy():
    m = stacked_duplicate_slab(nx=3, ny=3)
    n = m.n_faces // 2
    result = _removed(m)

    assert result.report["n_overlap_pairs_same"] == n
    assert result.report["n_overlap_pairs_diff"] == 0
    assert result.report["n_removed_overlap"] == n
    assert result.report["n_restored_overlap"] == 0
    assert result.removed.tolist() == [False] * n + [True] * n   # the COPY goes, not the original
    assert result.mesh.n_faces == n
    assert result.source_faces.tolist() == list(range(n))


def test_the_de_duplicated_slab_merges_back_to_one_region():
    m = stacked_duplicate_slab(nx=3, ny=3)
    result = _removed(m)
    topo = analyse_topology(result.mesh)
    merged = merge_regions(result.mesh, topo)

    assert len(set(topo.face_region[topo.face_region >= 0].tolist())) == 1
    assert merged.report["regions_merged"] == 1
    assert merged.report["regions_skipped"] == {}
    assert merged.mesh.n_faces == 2


def test_the_duplicated_slab_is_what_stops_the_merge_before_the_removal():
    """The other half of the same measurement: left alone, the duplicate makes the merge exclude
    every triangle of the region (rule 3) and skip it, so nothing merges at all."""
    m = stacked_duplicate_slab(nx=3, ny=3)
    merged = merge_regions(m, analyse_topology(m))
    assert merged.report["regions_merged"] == 0
    assert merged.report["regions_skipped"] == {"overlap": 1}
    assert merged.mesh.n_faces == m.n_faces


def test_a_different_material_overlap_is_reported_and_never_removed():
    m = stacked_duplicate_slab(nx=3, ny=3, top_material=1)
    n = m.n_faces // 2
    result = _removed(m)

    assert result.report["n_overlap_pairs_same"] == 0
    assert result.report["n_overlap_pairs_diff"] == n
    assert result.report["n_removed_overlap"] == 0
    assert not result.removed.any()
    assert result.mesh.n_faces == m.n_faces

    reported = result.report["overlap_pairs_diff_material"]
    assert len(reported) == n
    for entry in reported:
        assert sorted(entry["materials"]) == [0, 1]
        assert entry["faces"][0] < entry["faces"][1]
        assert entry["area"] > 0.0


def test_overlap_removal_is_deterministic():
    m = stacked_duplicate_slab(nx=3, ny=3)
    a, b = _removed(m), _removed(m)
    assert a.removed.tolist() == b.removed.tolist()
    assert a.candidates.tolist() == b.candidates.tolist()
    assert np.array_equal(a.mesh.face_v, b.mesh.face_v)
    assert find_overlaps(m, analyse_topology(m)) == find_overlaps(m, analyse_topology(m))


def test_nothing_is_removed_from_a_slab_with_no_overlap_at_all():
    m = grid_slab(6, 6)
    result = _removed(m)
    assert result.report["n_overlap_pairs_same"] == 0
    assert result.mesh.n_faces == m.n_faces
    assert result.source_faces.tolist() == list(range(m.n_faces))


def test_a_candidate_the_guard_refuses_stays_and_is_counted():
    """The guard has the last word. Forcing every candidate to be restored must leave the mesh
    untouched and say so, exactly as a hidden-face restore does."""
    m = stacked_duplicate_slab(nx=3, ny=3)
    n = m.n_faces // 2
    topo, positions_c = _centred(m)
    result = remove_overlaps(
        m, topo, positions_c, frozenset({0}), 1.5 * float(topo.quanta.max()), guard_size=_SIZE,
        guard=lambda candidates, *a, **kw: (np.zeros_like(candidates), [{"round": 0}]))

    assert result.report["n_removed_overlap"] == 0
    assert result.report["n_restored_overlap"] == n
    assert result.restored.sum() == n
    assert result.mesh.n_faces == m.n_faces


def test_the_covered_threshold_is_a_parameter():
    """At the default 0.99 the fins are safe; asked for anything they clear, they become
    candidates -- so the threshold really is what decides, not some other accident of the
    fixture."""
    m = partially_overlapping_fins()
    topo = analyse_topology(m)
    assert COVERED_FRACTION == 0.99
    assert not plan_overlap_removal(m, topo).candidates.any()
    loose = plan_overlap_removal(m, topo, covered_fraction=0.4)
    assert loose.candidates.sum() == 2
    assert loose.remove.sum() == 1        # twins: one of the two is protected, never both


def test_two_exactly_stacked_layers_are_one_patch_not_two():
    """`plan_overlap_removal`'s tie-break sorts by patch size first, and its docstring used to
    claim "a whole stacked layer is one patch, so the smaller LAYER loses". That is false for the
    case the rule exists for: two EXACTLY coincident layers weld to the same vertices, so they
    share the same welded edges and `_patch_of` unions them into ONE patch.

    What actually decides a stacked pair is the second key -- the higher face id goes first --
    and the docstring now says so."""
    m = stacked_duplicate_slab()
    topo = analyse_topology(m)
    plan = plan_overlap_removal(m, topo)

    patch = _patch_of(topo, plan.candidates)
    assert int(plan.candidates.sum()) == m.n_faces
    assert len(np.unique(patch[patch >= 0])) == 1          # one patch, not two layers
    # the upper half of the face ids -- the second copy -- is what goes
    assert int(plan.remove.sum()) == m.n_faces // 2
    assert plan.remove[m.n_faces // 2:].all()
    assert not plan.remove[: m.n_faces // 2].any()


# ---------------------------------------------------------------------- brief 13: stacked copies
# One copy of an exactly stacked, opposite-wound, same-material surface goes (the owner's
# decision of 2026-09-25); `engine/tests/test_pipeline.py` has the brief's four cases end to end.

from dataclasses import replace

import pytest

from engine.fixes.overlap import find_coincident_pairs, plan_coincident_removal
from engine.tests.fixtures.build import open_tray_with_a_copy_of_its_top
from engine.vis.exposure import compute_side_exposure


def _tray_exposure(mesh):
    topo, positions_c = _centred(mesh)
    front, back = compute_side_exposure(positions_c, topo.face_w, topo.ok, n_dirs=32)
    return topo, positions_c, front, back


def _with_a_second_copy_wound_up(mesh):
    """The tray with a THIRD layer: faces 10-11, the top's own two triangles again, wound up."""
    return replace(mesh, face_v=np.vstack([mesh.face_v, mesh.face_v[:2]]),
                   face_vt=np.vstack([mesh.face_vt, mesh.face_vt[:2]]),
                   face_vn=np.vstack([mesh.face_vn, mesh.face_vn[:2]]),
                   face_material=np.concatenate([mesh.face_material, mesh.face_material[:2]]),
                   face_line=np.arange(1, mesh.n_faces + 3, dtype=np.int64))


def test_find_coincident_pairs_pairs_each_face_of_the_copy_with_the_face_it_lies_on():
    m = open_tray_with_a_copy_of_its_top()
    topo, positions_c = _centred(m)
    pairs = find_coincident_pairs(positions_c, topo.face_w, topo.ok)
    assert [(i, j) for i, j, _a in pairs] == [(0, 8), (1, 9)]
    assert [a for _i, _j, a in pairs] == pytest.approx([800.0, 800.0])


def test_find_coincident_pairs_leaves_a_same_wound_duplicate_to_the_overlap_pass():
    m = stacked_duplicate_slab(nx=3, ny=3)
    topo, positions_c = _centred(m)
    assert find_coincident_pairs(positions_c, topo.face_w, topo.ok) == []


def test_an_exposure_tie_keeps_both_faces():
    """Seen exactly as much from each side, neither face has the better claim: both stay. Fails
    if a tie falls to either face."""
    m = open_tray_with_a_copy_of_its_top()
    topo, positions_c, _front, _back = _tray_exposure(m)
    even = np.full(m.n_faces, 0.25)
    plan = plan_coincident_removal(m, topo, positions_c, even, even, size=_SIZE)

    assert not plan.remove.any()
    assert [p["reason"] for p in plan.pairs] == ["exposure tie"] * 2
    assert all(p["kept"] is None and p["removed"] is None for p in plan.pairs)


def test_the_side_the_guard_views_see_less_is_never_the_one_kept():
    """Condition 4's purpose, measured: back pixels seen from outside must not go up. Told the
    underside is the more exposed side (the exposure arrays swapped), the rule would keep the
    copy facing DOWN -- but the guard views see the tray's top more from above, so the pair is
    left as it is. Fails if exposure alone decides."""
    m = open_tray_with_a_copy_of_its_top()
    topo, positions_c, front, back = _tray_exposure(m)
    honest = plan_coincident_removal(m, topo, positions_c, front, back, size=_SIZE)
    assert np.nonzero(honest.remove)[0].tolist() == [8, 9]
    for p in honest.pairs:
        assert p["px"][0] > p["px"][1] > 0                  # more pixels see it from above

    swapped = plan_coincident_removal(m, topo, positions_c, back, front, size=_SIZE)
    assert not swapped.remove.any()
    assert [p["reason"] for p in swapped.pairs] == ["the guard views see the other side more"] * 2
    assert [p["px"] for p in swapped.pairs] == [p["px"] for p in honest.pairs]


def test_two_pairs_that_disagree_about_one_face_never_remove_the_face_one_of_them_keeps(
        monkeypatch):
    """Three layers: the top (up), the copy (down) and the top again (up, faces 10-11). Each
    exposure estimate is a sample, and here the second pair's samples say the copy's side is the
    more exposed: it would keep the copy the first pair removed. The first decision stands and the
    second pair keeps both, so every position keeps a face. Fails if a pair may remove the face
    another pair kept, or keep the face another pair removed.

    The guard views are taken out of the question (no pixel on either side), because on a real
    stack they side with the first pair: one render counts the same pixels for both."""
    m = _with_a_second_copy_wound_up(open_tray_with_a_copy_of_its_top())
    topo, positions_c, front, back = _tray_exposure(m)
    front, back = front.copy(), back.copy()
    front[[10, 11]], back[[10, 11]] = 0.0, 1.0      # faces 10-11 sample their up side as blind
    none = np.zeros(m.n_faces, dtype=np.int64)
    monkeypatch.setattr(overlap_module, "side_pixels", lambda *a, **kw: (none, none))
    plan = plan_coincident_removal(m, topo, positions_c, front, back, size=_SIZE)

    pairs = {tuple(p["faces"]): p for p in plan.pairs}
    assert sorted(pairs) == [(0, 8), (1, 9), (8, 10), (9, 11)]
    assert np.nonzero(plan.remove)[0].tolist() == [8, 9]
    assert all(pairs[k]["removed"] == k[1] for k in [(0, 8), (1, 9)])
    assert all(pairs[k]["reason"] == "conflicts with another pair" for k in [(8, 10), (9, 11)])


def test_a_pair_the_guard_puts_back_is_reported_as_kept():
    m = open_tray_with_a_copy_of_its_top()
    topo, positions_c, front, back = _tray_exposure(m)
    result = remove_overlaps(
        m, topo, positions_c, frozenset({0}), 1.5 * float(topo.quanta.max()), guard_size=_SIZE,
        side_exposure=(front, back),
        guard=lambda candidates, *a, **kw: (np.zeros_like(candidates), [{"round": 0}]))

    assert not result.removed_coincident.any() and result.mesh.n_faces == m.n_faces
    assert result.report["n_coincident_pairs"] == 2
    assert result.report["n_removed_coincident"] == 0
    assert result.restored.tolist() == [False] * 8 + [True, True]
    assert all(p["verdict"] == "kept" and p["reason"] == "put back by the guard"
               and p["kept"] is None and p["removed"] is None for p in result.coincident_pairs)


def test_no_side_exposure_means_no_stacked_copy_is_touched():
    """`remove_overlaps` as it was called before brief 13: the rule needs the exposure to decide
    which side a pair is seen from, and without it proposes nothing."""
    m = open_tray_with_a_copy_of_its_top()
    result = _removed(m)
    assert result.mesh.n_faces == m.n_faces
    assert result.coincident_pairs == [] and not result.removed_coincident.any()
