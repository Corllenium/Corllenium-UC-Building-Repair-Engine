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
from engine.fixes.overlap import (COVERED_FRACTION, covered_fractions, find_overlaps,
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
