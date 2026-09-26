"""O1: covered same-material duplicate layers, found and removed under the strict guard.

Measured on file A's removal-stage mesh: 120 overlapping coplanar pairs, all the same material,
over 133 faces in 25 regions -- the walkway carries a second copy of its own surface. The merge
excludes an overlapping triangle from its union (rule 3) and skips a region whose union still
overlaps, so those 133 faces and every triangle around them were copied through unmerged and
their gridlines drawn.
"""
import numpy as np
import pytest

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


# ------------------------------------------ brief 15 item 1: what can still flicker, every run


def test_double_layers_measures_two_layers_of_one_plane():
    """Brief 15 item 1 (brief 14's measurement, made cheap enough for every run): a DOUBLE LAYER
    is two faces sharing more than 1 sq in within one plane -- any winding, any material -- and
    its pixels are those of the 26 views whose first hit is one of the two and whose ray meets the
    other within the depth tolerance: where the two can trade places in Unity's depth test. The
    fins overlap over exactly half of each, 187.5 sq in, in the slab's top plane, seen from above."""
    from engine.fixes.overlap import double_layers
    m = partially_overlapping_fins()
    topo, positions_c = _centred(m)
    fins = [m.n_faces - 2, m.n_faces - 1]
    d = double_layers(positions_c, topo.face_w, 0.15, size=_SIZE)
    assert d["count"] == 1
    assert d["area"] == pytest.approx(187.5, abs=1e-3)
    assert d["px"] > 0
    [plane] = d["planes"]
    assert sorted(plane["faces"]) == fins
    assert (plane["pairs"], plane["opposite"]) == (1, 0)
    assert plane["area"] == d["area"] and plane["px"] == d["px"]
    assert plane["normal"] == pytest.approx([0.0, 0.0, 1.0])


def test_double_layers_counts_an_opposite_wound_pair_and_nothing_on_a_single_layer():
    """The same fins with one of them wound the other way are still one double layer -- opposite,
    now -- and the slab alone, a single layer everywhere, has none."""
    from dataclasses import replace
    from engine.fixes.overlap import double_layers
    m = partially_overlapping_fins()
    fv = m.face_v.copy()
    fv[-1] = fv[-1][[0, 2, 1]]
    flipped = replace(m, face_v=fv)
    topo, positions_c = _centred(flipped)
    d = double_layers(positions_c, topo.face_w, 0.15, size=_SIZE)
    assert (d["count"], d["planes"][0]["opposite"]) == (1, 1)
    single = grid_slab()
    topo, positions_c = _centred(single)
    assert double_layers(positions_c, topo.face_w, 0.15, size=_SIZE) == {
        "count": 0, "area": 0.0, "px": 0, "planes": [], "pair_list": []}


def test_double_layers_lists_every_pair_with_its_partner():
    from engine.fixes.overlap import double_layers
    from engine.tests.fixtures.build import back_to_back_pair
    m = back_to_back_pair()
    pos = np.asarray(m.positions, float)
    centre = (pos.min(axis=0) + pos.max(axis=0)) / 2
    d = double_layers(pos - centre, np.asarray(m.face_v), depth_tol=0.01, centre=centre)
    assert d["count"] == 1
    [(i, j, shared, opposite)] = d["pair_list"]
    assert (i, j) == (0, 1)
    assert opposite is True
    assert shared == pytest.approx(d["area"])


def test_double_layers_pair_list_sorted_by_descending_shared_area():
    """Verify pair_list is sorted by (-shared_area, i, j). With multiple pairs having different
    shared areas, the sort order is tested (not just a single-element list that passes any sort)."""
    from engine.fixes.overlap import double_layers
    from engine.tests.fixtures.build import split_double_layer

    m = split_double_layer()
    pos = np.asarray(m.positions, float)
    centre = (pos.min(axis=0) + pos.max(axis=0)) / 2
    d = double_layers(pos - centre, np.asarray(m.face_v), depth_tol=0.01, centre=centre)

    pair_list = d["pair_list"]

    # Verify we have at least one pair (split_double_layer has overlapping triangles)
    assert len(pair_list) > 0, f"Expected at least one pair, got {len(pair_list)}"

    # Verify i < j on every row and types are correct
    for i, j, shared, opposite in pair_list:
        assert i < j, f"Expected i < j, got i={i}, j={j}"
        assert isinstance(shared, (int, float)), f"Expected shared area numeric, got {type(shared)}"
        assert isinstance(opposite, bool), f"Expected opposite bool, got {type(opposite)}"

    # Verify sorted by descending shared area (largest first)
    # If two pairs have the same area, they're sorted by (i, j)
    areas = [shared for _, _, shared, _ in pair_list]
    for idx in range(len(areas) - 1):
        if areas[idx] == areas[idx + 1]:
            # Equal areas: check (i, j) ordering
            i1, j1, _, _ = pair_list[idx]
            i2, j2, _, _ = pair_list[idx + 1]
            assert (i1, j1) < (i2, j2), f"For equal areas, expected (i,j) ordering: ({i1},{j1}) vs ({i2},{j2})"
        else:
            assert areas[idx] >= areas[idx + 1], f"pair_list not sorted by descending area: {areas}"


def _reference_px(positions_c, faces, result, depth_tol, views, size):
    """The visible-pixel total exactly as double_layers counted it before 2026-09-26: every surface
    along the ray, from the caster's all_hits."""
    from engine.guard.views import ortho_first_hit
    from engine.rays.caster import EmbreeCaster, ReusableCaster
    partners = {}
    for i, j, _s, _o in result["pair_list"]:
        partners.setdefault(i, set()).add(j)
        partners.setdefault(j, set()).add(i)
    watched = np.array(sorted(partners), dtype=np.int64)
    caster = EmbreeCaster(positions_c, faces)
    reusable = ReusableCaster(EmbreeCaster)
    ids_all = np.arange(len(faces), dtype=np.int64)
    total = 0
    for view in views:
        buf = ortho_first_hit(positions_c, faces, ids_all, view, positions_c, size, reusable)
        mask = (buf.tri >= 0) & np.isin(buf.tri, watched)
        if not mask.any():
            continue
        rows, cols = np.nonzero(mask)
        origins = buf.xs[cols][:, None] * buf.right + buf.ys[rows][:, None] * buf.up + buf.standoff
        ray, hit, t = caster.all_hits(origins, np.tile(np.asarray(buf.direction, float), (len(origins), 1)))
        first_f, first_t = buf.tri[rows, cols], buf.depth[rows, cols]
        near = np.abs(t - first_t[ray]) <= depth_tol
        met = {}
        for q, f in zip(ray[near].tolist(), hit[near].tolist()):
            met.setdefault(q, set()).add(f)
        total += sum(1 for q in range(len(rows)) if partners[int(first_f[q])] & met.get(q, set()))
    return total


@pytest.mark.parametrize("build", ["back_to_back_pair", "split_double_layer", "two_sided_wall"])
def test_double_layers_counts_the_same_pixels_as_every_surface_along_the_ray(build):
    from engine.fixes.overlap import double_layers
    from engine.guard.views import VIEWS_26
    from engine.tests.fixtures import build as fixtures
    m = getattr(fixtures, build)()
    pos = np.asarray(m.positions, float)
    centre = (pos.min(axis=0) + pos.max(axis=0)) / 2
    faces = np.asarray(m.face_v)
    d = double_layers(pos - centre, faces, 0.01, VIEWS_26, (300, 200), centre=centre)
    assert d["px"] > 0
    reference = _reference_px(pos - centre, faces, d, 0.01, VIEWS_26, (300, 200))
    if build == "two_sided_wall":
        assert d["px"] == reference
    else:
        # rays grazing exactly a partner's edge: reference is Embree's float32 mesh plus the
        # caster's coincident tolerance, the new count is a float64 barycentric test at eps=1e-6;
        # 1 px of 153028 (back_to_back_pair) and 3 px of 102022 (split_double_layer), measured 2026-09-26
        assert abs(d["px"] - reference) <= max(5, reference * 1e-4)


def test_double_layers_no_longer_asks_the_caster_for_every_surface(monkeypatch):
    from engine.fixes import overlap
    from engine.rays.caster import EmbreeCaster
    from engine.tests.fixtures.build import two_sided_wall

    def forbidden(*a, **k):
        raise AssertionError("all_hits called")

    monkeypatch.setattr(EmbreeCaster, "all_hits", forbidden)
    m = two_sided_wall()
    pos = np.asarray(m.positions, float)
    overlap.double_layers(pos - pos.mean(axis=0), np.asarray(m.face_v), 0.01)
