"""F1: stray fragments and attached slivers, found and removed under a FRAGMENT-mode guard.

A stray is geometry that is not part of anything: a triangle left behind by a delete, a scrap of
a component that was moved away, a needle of a face too thin to be anything. None of it can be
caught by the hidden-face pass, because a stray is usually plainly visible -- which is exactly
why its removal needs a guard of its own, one that permits the pixels the stray itself occupied
and nothing else.
"""
import json

import numpy as np
import pytest

import engine.cli as cli
import engine.fixes.pipeline as fix_pipeline
from engine.detectors.fragments import FragmentResult, detect_fragments
from engine.fixes.merge import default_collinear_tol
from engine.fixes.pipeline import FixProfile, fix_object, sliver_width_bound
from engine.guard.compare import compare_views, fragment_feedback
from engine.guard.views import VIEWS_26, ortho_first_hit
from engine.pipeline import analyse_topology
from engine.rays.caster import EmbreeCaster
from engine.tests.fixtures.build import (printed, slab_with_coplanar_patch, slab_with_infill_patch,
                                         slab_with_interior_strip, slab_with_strays,
                                         slab_with_t_joined_strip)
from engine.vis.exposure import compute_side_exposure

_FAST = FixProfile(guard_size=(120, 80), n_dirs=32, solidify=False)


def _fast(**overrides):
    return FixProfile(guard_size=(120, 80), n_dirs=32, solidify=False, **overrides)


def _detected(mesh, profile=None):
    """The detector exactly as `fix_object` calls it: contact within the T-junction tolerance
    `analyse_topology` uses, 1.5 x the mesh's coarsest print step, and no sliver wider than the
    merge's own border tolerance (`sliver_width_bound`)."""
    profile = profile or _FAST
    topo = analyse_topology(mesh)
    return detect_fragments(topo.positions_w, topo.face_w, profile,
                            contact_tol=1.5 * float(topo.quanta.max()),
                            max_width=sliver_width_bound(topo.quanta, profile))


# --------------------------------------------------------------------------- the detector


def test_a_detached_small_triangle_is_a_fragment_candidate():
    m = slab_with_strays()
    d = _detected(m)

    assert d.report["n_components"] == 3          # slab + needle, stray triangle, stray quad
    assert d.report["n_candidate_components"] == 1
    assert d.fragments.tolist() == [False] * 33 + [True] + [False, False]
    assert d.report["n_fragment_faces"] == 1


def test_a_detached_twenty_square_inch_quad_is_kept_and_reported():
    """Its longest extent is 5 in, UNDER `fragment_max_extent`, so the extent rule alone would
    take it. The rule that saves it is "never a component holding a face bigger than
    `fragment_max_area` on its own" -- each of its triangles is 10 in^2."""
    m = slab_with_strays()
    d = _detected(m)

    assert not d.fragments[34] and not d.fragments[35]
    assert not d.slivers[34] and not d.slivers[35]
    assert d.report["n_above_threshold_components"] == 2       # the slab, and this quad
    areas = [c["area"] for c in d.report["smallest_kept_components"]]
    assert areas[0] == 20.0                                    # reported, with its size


def test_an_attached_needle_is_a_sliver_candidate():
    """Printed like the real files (0.1 in), so the width bound is their 0.15 in: the needle is
    0.02 in wide, shares its long edge with the slab and has its two other long edges open -- a
    ragged border, which removing it moves by at most 0.04 in."""
    m = printed(slab_with_strays())
    d = _detected(m)
    assert d.slivers.tolist() == [False] * 32 + [True] + [False] * 3
    assert d.report["n_sliver_faces"] == 1
    assert d.report["n_thin_faces"] == 1 and d.report["n_sandwiched_thin_faces"] == 0
    assert not d.fragments[32]                 # it is attached, so never a fragment


def test_nothing_is_a_candidate_when_there_is_nothing_stray():
    d = _detected(slab_with_strays(stray=False, needle=False))
    assert not d.fragments.any() and not d.slivers.any()
    assert d.report["n_components"] == 1 and d.report["n_candidate_components"] == 0


def test_the_detector_invents_no_randomness_and_repeats_itself():
    m = slab_with_strays()
    a, b = _detected(m), _detected(m)
    assert a.fragments.tolist() == b.fragments.tolist()
    assert a.slivers.tolist() == b.slivers.tolist()
    assert a.report == b.report


# ------------------------------------------------------------------- through `fix_object`


def test_fix_object_removes_the_stray_triangle_and_the_needle_and_keeps_the_quad():
    # printed like the real files, where a 0.02 in needle is within the merge's own 0.15 in
    m = printed(slab_with_strays())
    r = fix_object(m, {}, _FAST)

    assert r.n_fragment_components == 3
    assert r.n_removed_fragments == 1
    assert r.n_removed_slivers == 1
    assert r.n_restored_fragments == 0
    assert r.removed_fragments[33] and r.removed_fragments[32]
    assert not r.removed_fragments[34] and not r.removed_fragments[35]
    # the 20 in^2 quad is still in the shipped mesh
    z = r.mesh.positions[r.mesh.face_v][:, :, 2]
    assert int((z == 25.0).all(axis=1).sum()) == 2
    assert not (z == 20.0).any()
    assert r.passed is True


def test_the_final_guard_tolerates_exactly_the_fragment_pixels():
    """The strays are plainly visible from above, so removing them DOES change the picture --
    which is the whole point, and the reason the guard the rest of the pipeline uses would refuse
    it. Those pixels are excused BY NAME: any pixel whose BEFORE first hit is one of the faces
    this pass removed is `PX_FRAGMENT_REMOVED` and never a failure. Every other pixel is judged
    exactly as it was.

    Not by leaving those faces out of the BEFORE render, which is a different thing and is wrong
    -- see the comment in `fix_object`, and the 749 phantom pixels on file A that paid for it."""
    r = fix_object(printed(slab_with_strays()), {}, _FAST)
    assert r.n_removed_fragments + r.n_removed_slivers == 2

    assert r.guard_final.totals["fragment_removed"] > 0     # the strays really were visible
    assert r.guard_final.totals["holes"] == 0
    assert r.guard_final.totals["material_changed"] == 0
    assert r.guard_final.totals["moved_other"] == 0
    assert r.guard_final.totals["moved_same_flat"] == 0
    assert r.guard_final.passed is True
    assert r.guard_after_removal.passed is True

    # ...and with the pass off, nothing is excused: the tolerance is tied to the faces this run
    # actually removed, not a blanket allowance the guard carries around.
    off = fix_object(slab_with_strays(), {}, _fast(accept_fragments=False))
    assert off.guard_final.totals["fragment_removed"] == 0


def test_keep_fragments_removes_nothing():
    m = slab_with_strays()
    r = fix_object(m, {}, _fast(accept_fragments=False))

    assert r.n_fragment_components == 0
    assert r.n_removed_fragments == 0 and r.n_removed_slivers == 0
    assert not r.removed_fragments.any()
    z = r.mesh.positions[r.mesh.face_v][:, :, 2]
    assert int((z == 20.0).all(axis=1).sum()) == 1      # the 2 in^2 stray is still there
    assert r.passed is True


def test_fragment_removal_is_deterministic():
    m = printed(slab_with_strays())            # so both kinds of debris are removed
    a, b = fix_object(m, {}, _FAST), fix_object(m, {}, _FAST)
    assert a.n_removed_fragments == 1 and a.n_removed_slivers == 1
    assert a.removed_fragments.tolist() == b.removed_fragments.tolist()
    assert np.array_equal(a.mesh.face_v, b.mesh.face_v)
    assert a.fragment_report == b.fragment_report


def test_the_cli_flag_turns_the_pass_off(tmp_path):
    args = cli.build_parser().parse_args(["fix", "somedir"])
    assert args.fragments is True
    args = cli.build_parser().parse_args(["fix", "somedir", "--keep-fragments"])
    assert args.fragments is False


# ------------------------------------------ the guard renders the SAME BEFORE as the final guard


def _quad(a, b, c, d):
    return [[a, b, c], [a, c, d]]


def test_the_fragment_guard_sees_the_same_before_as_the_final_guard():
    """Found on file A and pinned here at the size of the defect. Three surfaces share one spot:
    a plate H that the hidden pass has ALREADY removed, lying 0.01 in above a 0.5 in strip S
    that is the ONLY surface left there once H is gone -- the floor either side of S stops at its
    edges. S is a fragment candidate.

    Rendered against the POST-HIDDEN mesh, which is what this guard used to do, S is BEFORE's
    first hit at those pixels, they read as the fragment's own, and S goes -- leaving a hole that
    the final guard, whose BEFORE is the WHOLE mesh with H in it, calls damage. (On file A that
    was one pixel, and it rolled the whole merge back.) Rendered against the whole mesh with H
    only in `already_removed`, BEFORE's first hit there is H, the pixel fails, and the blame goes
    to the candidate in H's tie set -- S -- which is restored."""
    from engine.guard.compare import fragment_feedback

    P = np.array([[0, 0, 0], [5, 0, 0], [5, 10, 0], [0, 10, 0],                 # K1, the floor
                  [5, 0, 0], [5.5, 0, 0], [5.5, 10, 0], [5, 10, 0],             # S, the strip
                  [5.5, 0, 0], [10, 0, 0], [10, 10, 0], [5.5, 10, 0],           # K2, the floor
                  [4, 0, 0.01], [6, 0, 0.01], [6, 10, 0.01], [4, 10, 0.01]],    # H, removed
                 dtype=np.float64)
    faces = np.array(_quad(0, 1, 2, 3) + _quad(4, 5, 6, 7) + _quad(8, 9, 10, 11)
                     + _quad(12, 13, 14, 15), dtype=np.int64)
    positions_c = P - (P.min(axis=0) + P.max(axis=0)) / 2.0
    material = np.zeros(len(faces), np.int64)
    candidates = np.array([False, False, True, True, False, False, False, False])
    already_removed = np.array([False] * 6 + [True, True])

    # the old picture: BEFORE is the post-hidden mesh, so S's pixels look like its own
    keep = ~already_removed
    old, _history = fragment_feedback(candidates[keep], positions_c, faces[keep], material[keep],
                                      frozenset(), 0.15, size=(120, 80))
    assert old[2] and old[3]                       # the defect: the strip goes

    # the right picture: BEFORE is the whole mesh, H only dropped from AFTER
    new, history = fragment_feedback(candidates, positions_c, faces, material, frozenset(), 0.15,
                                     already_removed=already_removed, size=(120, 80))
    assert not new.any()                           # S is restored, by name
    assert history[0]["failing_pixels"] > 0 and history[0]["restored"] == 2
    assert history[-1]["failing_pixels"] == 0      # ...and with it back, nothing fails

    # H's OWN removal flickers a few silhouette pixels in the corner views (6, measured). No
    # candidate lies in front of AFTER's hit there, so they are not this pass's to answer for:
    # counted, never blamed on S, and identical whether S is removed or restored. A rule that
    # gave up on anything it could not blame would have thrown the whole pass away over them.
    assert history[0]["not_ours_pixels"] == history[-1]["not_ours_pixels"] > 0


# ------------------------------------- review C2: real surface is never debris, and is judged
#
# The probe (`review-probes/probe_fragment_patch.py`, now the fixture `slab_with_infill_patch`):
# a 3 x 1 in patch of a slab's walking surface met the rest of the top only through T-junctions,
# so the detector called it a stray, the fragment guard never looked at its own pixels, the final
# guard excused them by name, and a hole shipped with `passed` True.


def _patch_faces(m):
    return [m.n_faces - 12, m.n_faces - 11]


def _centred(m):
    topo = analyse_topology(m)
    return topo, topo.positions_w - (topo.positions_w.min(axis=0) + topo.positions_w.max(axis=0)) / 2.0


def _exposed_sides(topo, positions_c):
    """`(F, 2)` bool: each face's FRONT / BACK side exposed on this mesh, as `fix_object` builds
    it for the fragment guards."""
    front, back = compute_side_exposure(positions_c, topo.face_w, topo.ok, n_dirs=32)
    return np.stack([front > 0.0, back > 0.0], axis=1)


def test_a_patch_joined_only_through_t_junctions_is_not_debris():
    m = slab_with_infill_patch()
    d = _detected(m)
    assert not d.fragments[_patch_faces(m)].any()
    assert not d.slivers[_patch_faces(m)].any()
    assert d.report["n_components"] == 1                 # top, patch, sides and bottom: one piece
    # ...where shared welded edges alone make two: the evidence of what the contact rules joined
    assert d.report["n_components_by_shared_edges"] == 2


def test_a_patch_lying_in_a_surface_is_not_debris():
    """A painted mark lying ON the top touches it through no vertex, edge or T-junction -- only
    by lying in its plane. Coplanar contact joins it."""
    d = _detected(slab_with_coplanar_patch())
    assert not d.fragments.any() and not d.slivers.any()
    assert d.report["n_components"] == 1

    # ...and contact means the SAME plane, not the same neighbourhood: 0.5 in above the top the
    # patch touches nothing and is a stray again
    lifted = _detected(slab_with_coplanar_patch(lift=0.5))
    assert lifted.fragments.tolist() == [False, False, True, True] + [False] * 10


def test_a_strip_wider_than_the_sliver_width_bound_is_not_a_sliver():
    """File B's wall strips in miniature: 29.5 in long, 0.26 in wide, a 3.8 sq in triangle whose
    quality (0.014) and area both pass the sliver rule. Removing one opens a slit 0.26 in wide
    through a real surface (measured on B: two of them, on the two faces of one wall, left a
    see-through slit). Printed like the real files, the width bound is their 0.15 in."""
    wide = _detected(printed(slab_with_interior_strip(width=0.26)))
    assert not wide.slivers[0] and not wide.fragments[0]
    assert wide.report["n_thin_faces"] == 0


@pytest.mark.parametrize("width", [0.05, 0.1, 0.14])
def test_a_strip_sandwiched_between_real_faces_is_not_a_sliver(width):
    """Review 2a C1. The same strip, narrow enough for the width bound -- and still real surface:
    all three of its edges are shared with the fat triangles around it, so removing it moves no
    border, it opens a slit onto the inside of the slab. Its width bounds how far every lost
    point lies from the surface left behind, which is exactly why the guards' border-shift
    measurement would excuse the slit; so the detector has to refuse it on its own. A sliver is
    named only when one of its LONG edges is an open border."""
    d = _detected(printed(slab_with_interior_strip(width=width)))
    assert not d.slivers.any() and not d.fragments.any()
    assert d.report["n_thin_faces"] == 1                   # quality, area and width: all thin
    assert d.report["n_sandwiched_thin_faces"] == 1        # ...and sandwiched, so kept
    assert d.report["n_sliver_faces"] == 0


@pytest.mark.parametrize("join", ["vertex", "edge"])
def test_a_strip_joined_to_the_surface_only_through_a_t_junction_is_not_a_sliver(join):
    """The strip's BASE is used by no other face, so "not shared" alone would call it an open
    border -- but the surface below meets it through a T-junction: a vertex lying inside the base
    (`join="vertex"`), or a longer edge the base lies inside (`join="edge"`). A T-junction
    partner is a neighbour, so the base is not open, and the strip is sandwiched."""
    m = printed(slab_with_t_joined_strip(width=0.1, join=join))
    topo = analyse_topology(m)
    base = tuple(sorted(topo.face_w[0][:2].tolist()))
    counts = {tuple(e): c for e, c in zip(topo.table.edges.tolist(), topo.table.counts.tolist())}
    assert counts[base] == 1                                # the premise: nothing shares it
    d = _detected(m)
    assert not d.slivers[0]
    assert d.report["n_sandwiched_thin_faces"] == 1


def test_a_long_edge_is_only_one_the_face_is_thin_along():
    """A needle whose SHORT end is an open border and whose two long sides are shared is not a
    ragged border: removing it opens a crack as long as the needle into the surface. Only an edge
    whose opposite corner lies within the width bound of it counts as a long edge. Here a 40 in
    plate with no sides (so its rim IS open) is a fan from a point 29.5 in in from the rim; the
    fan's triangle over a 0.1 in stretch of the rim is the needle."""
    from engine.tests.fixtures.build import _mesh
    tip, r1, r2 = [29.5, 20.0, 0.0], [0.0, 19.95, 0.0], [0.0, 20.05, 0.0]
    P = [[0.0, 0.0, 0.0], [40.0, 0.0, 0.0], [40.0, 40.0, 0.0], [0.0, 40.0, 0.0], r1, r2, tip]
    fv = [[4, 6, 5],                                      # the needle, short edge 4-5 on the rim
          [0, 1, 6], [1, 2, 6], [2, 3, 6], [3, 5, 6], [4, 0, 6]]
    uvs = (np.asarray(P)[np.asarray(fv).reshape(-1)][:, :2] * 0.05).tolist()
    m = printed(_mesh("rim_needle_plate", P, uvs, fv, np.arange(18).reshape(-1, 3).tolist()))
    d = _detected(m)
    assert d.report["n_thin_faces"] == 1                   # the needle: 0.1 in wide, 1.5 sq in
    assert not d.slivers[0]
    assert d.report["n_sandwiched_thin_faces"] == 1


def test_a_partner_belongs_to_the_edge_it_lies_nearest():
    """A needle 0.02 in wide hangs off a plate's rim, which the plate splits at (5, 0) -- the
    middle of the needle's base -- so the base is T-joined to the plate. That vertex is also
    within the 0.15 in contact tolerance of the needle's two OPEN edges, as is every point of a
    face that thin; it is the partner of the base, which it lies on, not of them. The needle is a
    ragged border and a sliver."""
    from engine.tests.fixtures.build import _mesh
    P = [[0.0, 0.0, 0.0], [5.0, 0.0, 0.0], [10.0, 0.0, 0.0], [40.0, 0.0, 0.0], [40.0, 40.0, 0.0],
         [0.0, 40.0, 0.0], [20.0, 20.0, 0.0], [5.0, -0.02, 0.0]]
    fv = [[0, 2, 7],                                            # the needle, base 0-2
          [0, 1, 6], [1, 2, 6], [2, 3, 6], [3, 4, 6], [4, 5, 6], [5, 0, 6]]
    uvs = (np.asarray(P)[np.asarray(fv).reshape(-1)][:, :2] * 0.05).tolist()
    m = printed(_mesh("plate_with_split_rim_needle", P, uvs, fv,
                      np.arange(21).reshape(-1, 3).tolist()))
    d = _detected(m)
    assert d.report["n_components"] == 1                       # joined through (5, 0)
    assert d.slivers.tolist() == [True] + [False] * 6


def test_the_sliver_width_bound_is_the_merges_border_tolerance():
    """Derived, not a constant: `default_collinear_tol` -- how far the merge may move a border,
    and the border shift the final guard measures and excuses -- clamped to `depth_tol_max`
    exactly as that border-shift tolerance is. 0.15 in on the real files' 0.1 in print step."""
    profile = FixProfile()
    for step, bound in ((0.1, 0.15), (1e-4, 1.5e-4), (1.0, 0.5)):
        quanta = np.array([step, step, step / 10.0])
        assert sliver_width_bound(quanta, profile) == pytest.approx(bound)
        assert sliver_width_bound(quanta, profile) == pytest.approx(
            min(default_collinear_tol(quanta), profile.depth_tol_max))

    # the needle is 0.02 in wide: a sliver where the merge may move a border 0.15 in, and not
    # one at the fixtures' own 1e-4 in print step, where the merge may move it 1.5e-4 in
    real = _detected(printed(slab_with_strays()))
    assert real.slivers[32] and real.report["sliver_max_width"] == pytest.approx(0.15)
    fine = _detected(slab_with_strays())
    assert not fine.slivers[32] and fine.report["sliver_max_width"] == pytest.approx(1.5e-4)
    assert fine.report["n_thin_faces"] == 0


@pytest.mark.parametrize("width", [0.05, 0.1, 0.14])
def test_the_real_scale_sandwiched_strip_is_never_named(width):
    d = _detected(printed(slab_with_interior_strip(width=width, size=2000.0)))
    assert d.report["sliver_max_width"] == pytest.approx(0.15)
    assert not d.slivers.any() and d.report["n_sandwiched_thin_faces"] == 1


def test_fix_object_keeps_a_strip_of_real_surface():
    r = fix_object(slab_with_interior_strip(width=0.26), {}, _FAST)
    assert not r.removed_fragments[0]
    assert r.n_removed_slivers == 0 and r.n_removed_fragments == 0
    assert r.passed is True


def _rays_down_along_the_strip(mesh, size, width, n=97):
    """Where `n` rays cast straight down along `slab_with_interior_strip`'s strip first meet the
    shipped mesh: z of each hit, NaN for a miss. Every one lies inside the strip's footprint (at
    40 % of its local width above the base), so a slit where the strip was reads as z = -height."""
    xs = np.linspace(size / 2 - 12.0, size / 2 + 12.0, n)
    ys = size / 2 + 0.4 * width * (1.0 - np.abs(xs - size / 2) / 14.75)
    origins = np.stack([xs, ys, np.full_like(xs, 50.0)], axis=1)
    tri, t = EmbreeCaster(mesh.positions, mesh.face_v).first_hit(
        origins, np.tile([0.0, 0.0, -1.0], (n, 1)))
    return np.where(tri >= 0, 50.0 - t, np.nan)


@pytest.mark.parametrize("width", [0.05, 0.14])
def test_at_the_real_files_scale_a_sandwiched_strip_ships_no_slit(width):
    """Review 2a C1, experiment E2b as a test: a 29.5 in strip of walking surface `width` in wide,
    sandwiched between fat triangles in a 2000 in slab printed like the real files (0.1 in, so
    every tolerance the engine derives is 0.15 in and the strip is inside all of them). At this
    size a guard pixel spans inches -- 900 x 600 gives about 2 in, the 240 x 160 here about 8 --
    so no guard ray ever meets the strip, and the DETECTOR is the only defence: it used to name
    the strip a sliver, the fragment guard confirmed it unseen, and 97 of 97 rays down the strip
    fell through the slit onto the inside of the bottom with `passed` True. A coarser guard than
    the real one is no weaker a test: it sees even less."""
    size = 2000.0
    m = printed(slab_with_interior_strip(width=width, size=size))
    r = fix_object(m, {}, FixProfile(guard_size=(240, 160), n_dirs=32))
    assert not r.removed_fragments[0]
    assert r.n_removed_slivers == 0
    z = _rays_down_along_the_strip(r.mesh, size, width)
    assert np.isclose(z, 0.0, atol=1e-6).all(), sorted(set(np.round(z, 2).tolist()))
    assert r.passed is True


def test_the_fragment_guard_refuses_a_removal_that_shows_the_inside_of_a_closed_shell():
    """The patch handed to the fragment guard directly, as if the detector had named it. Where
    it goes, AFTER shows the INSIDE of the slab -- the back of its bottom, a side nobody could see
    on the reference -- so those pixels are not the fragment disappearing, they are a hole."""
    m = slab_with_infill_patch()
    topo, pc = _centred(m)
    exposed = _exposed_sides(topo, pc)
    bottom = [m.n_faces - 2, m.n_faces - 1]
    assert exposed[bottom, 0].all() and not exposed[bottom, 1].any()   # the premise: closed
    candidates = np.zeros(m.n_faces, dtype=bool)
    candidates[_patch_faces(m)] = True

    # with no exposure given, only background is a permitted change -- the strictest reading
    strict, _ = fragment_feedback(candidates, pc, topo.face_w, m.face_material, frozenset(), 0.15,
                                  size=(120, 80))
    assert not strict.any()

    kept, history = fragment_feedback(candidates, pc, topo.face_w, m.face_material, frozenset(),
                                      0.15, size=(120, 80), side_exposure=exposed)
    assert not kept.any()
    assert history[0]["failing_pixels"] > 0 and history[0]["restored"] == 2
    assert history[-1]["failing_pixels"] == 0


def test_the_fragment_guard_permits_a_removal_that_shows_an_exposed_side_or_the_sky():
    """The stray triangle above `slab_with_strays`: where it goes, AFTER shows the slab's top --
    exposed on the reference -- or the sky. Both are the stray disappearing."""
    m = slab_with_strays()
    topo, pc = _centred(m)
    candidates = np.zeros(m.n_faces, dtype=bool)
    candidates[33] = True
    kept, history = fragment_feedback(candidates, pc, topo.face_w, m.face_material, frozenset(),
                                      0.15, size=(120, 80),
                                      side_exposure=_exposed_sides(topo, pc))
    assert kept[33] and history[-1]["failing_pixels"] == 0

    # without the exposure, the slab's top is not known to be an outside surface: refused
    strict, _ = fragment_feedback(candidates, pc, topo.face_w, m.face_material, frozenset(), 0.15,
                                  size=(120, 80))
    assert not strict[33]


def _renders(pc, faces, size=(120, 80)):
    ids = np.arange(len(faces), dtype=np.int64)
    return [(v, ortho_first_hit(pc, faces, ids, v, pc, size)) for v in VIEWS_26]


def test_the_final_guard_excuses_a_removed_face_only_where_it_uncovers_an_exposed_side():
    m = slab_with_infill_patch()
    topo, pc = _centred(m)
    exposed = _exposed_sides(topo, pc)
    removed = np.zeros(m.n_faces, dtype=bool)
    removed[_patch_faces(m)] = True
    keep = ~removed
    faces = topo.face_w
    g = compare_views(_renders(pc, faces), _renders(pc, faces[keep]), m.face_material,
                      m.face_material[keep], frozenset({0}), 0.15, strict=True,
                      geometry_before=(pc, faces), geometry_after=(pc, faces[keep]),
                      removed_before=removed, exposed_after=exposed[keep])
    assert g.passed is False
    assert g.totals["fragment_removed"] == 0                # every patch pixel shows the inside
    assert g.totals["moved_same_flat"] > 0


def test_the_final_guard_judges_what_a_removed_fragment_uncovered(monkeypatch):
    """The whole pipeline, with the detector made to name the patch and the fragment guard made to
    confirm it -- the two earlier defences switched off -- so the FINAL guard is the one being
    tested. It used to excuse every pixel of a removed fragment by name, uncapped, and pass."""
    m = slab_with_infill_patch()
    patch = _patch_faces(m)

    def names_the_patch(positions_w, face_w, profile, **_kw):
        fragments = np.zeros(len(face_w), dtype=bool)
        fragments[patch] = True                       # nothing earlier removed anything here
        return FragmentResult(fragments, np.zeros(len(face_w), dtype=bool),
                              np.zeros(len(face_w), dtype=np.int64),
                              {"n_components": 1, "n_candidate_components": 1})

    def confirms_it(candidates, *_a, **_kw):
        return candidates.copy(), [{"round": 0, "candidates_remaining": int(candidates.sum()),
                                    "failing_pixels": 0, "not_ours_pixels": 0, "restored": 0}]

    monkeypatch.setattr(fix_pipeline, "detect_fragments", names_the_patch)
    monkeypatch.setattr(fix_pipeline, "fragment_feedback", confirms_it)
    r = fix_object(m, {}, FixProfile(guard_size=(240, 160), n_dirs=32))
    assert r.removed_fragments[patch].all()
    assert r.guard_final.totals["fragment_removed"] == 0
    assert r.guard_final.passed is False and r.passed is False


def test_the_review_probe_ships_no_hole_in_the_walking_surface():
    m = slab_with_infill_patch()
    r = fix_object(m, {}, FixProfile(guard_size=(240, 160), n_dirs=32))
    assert not r.removed_fragments[_patch_faces(m)].any()
    assert r.passed is True
    caster = EmbreeCaster(r.mesh.positions, r.mesh.face_v)
    tri, t = caster.first_hit(np.array([[20.0, 20.0, 50.0]]), np.array([[0.0, 0.0, -1.0]]))
    assert tri[0] >= 0 and 50.0 - float(t[0]) == pytest.approx(0.0, abs=1e-9)   # the top, z = 0


def test_fragment_pixels_over_the_per_view_cap_fall_back_to_what_they_were():
    """`fragment_removed` is capped per view the way `crack_closed` is: over the cap a view's
    fragment pixels are no longer excused, and say what they really are."""
    m = slab_with_strays()
    topo, pc = _centred(m)
    exposed = _exposed_sides(topo, pc)
    removed = np.zeros(m.n_faces, dtype=bool)
    removed[33] = True
    keep = ~removed
    faces = topo.face_w
    before, after = _renders(pc, faces), _renders(pc, faces[keep])

    def judged(cap):
        return compare_views(before, after, m.face_material, m.face_material[keep],
                             frozenset({0}), 0.15, strict=True, geometry_before=(pc, faces),
                             geometry_after=(pc, faces[keep]), removed_before=removed,
                             exposed_after=exposed[keep], fragment_removed_cap=cap)

    uncapped = judged(float("inf"))
    assert uncapped.passed is True and uncapped.totals["fragment_removed"] > 0
    capped = judged(0.0)
    assert capped.passed is False and capped.totals["fragment_removed"] == 0
    assert capped.totals["moved_same_flat"] + capped.totals["holes"] > 0

    # ...and the REMOVAL guard applies the same cap, so it never confirms what the final guard
    # would then refuse: at a cap of 0 the stray stays
    r = fix_object(m, {}, _fast(fragment_removed_cap=0.0))
    assert not r.removed_fragments[33]
    assert r.passed is True


# ---------------------------- brief 08 item 2: a face solidify invented is part of the shell
#
# File A's one removed "fragment", face 4721, had an id above the input's 4,692 faces: a bottom
# triangle solidify had invented under face 174 (same area, same bbox 9.84 in lower), which the
# detector then named a one-face stray and removed. Solidify invents faces to CLOSE a shell; the
# detector may not second-guess that, and a component holding such a face is that shell.


def _detected_protecting(mesh, protected):
    topo = analyse_topology(mesh)
    return detect_fragments(topo.positions_w, topo.face_w, _FAST,
                            contact_tol=1.5 * float(topo.quanta.max()),
                            max_width=sliver_width_bound(topo.quanta, _FAST),
                            protected=protected)


def test_a_protected_face_is_never_a_fragment_or_a_sliver():
    m = printed(slab_with_strays())
    free = _detected_protecting(m, None)
    assert free.fragments[33] and free.slivers[32]           # the premise: both are debris
    protected = np.zeros(m.n_faces, dtype=bool)
    protected[[32, 33]] = True
    d = _detected_protecting(m, protected)
    assert not d.fragments.any() and not d.slivers.any()
    assert d.report["n_protected_components"] == 1           # the stray triangle's own
    assert d.report["n_protected_faces"] == 2
    assert d.report["n_candidate_components"] == 0


def test_a_component_holding_a_protected_face_is_never_a_fragment():
    """The lifted patch is a two-face stray. Protect ONE of its faces and neither goes: removing
    only the other would leave half a shell hanging."""
    m = slab_with_coplanar_patch(lift=0.5)
    assert _detected_protecting(m, None).fragments[[2, 3]].all()
    protected = np.zeros(m.n_faces, dtype=bool)
    protected[2] = True
    d = _detected_protecting(m, protected)
    assert not d.fragments.any()
    assert d.report["n_protected_components"] == 1 and d.report["n_protected_faces"] == 1


def _with_triangle(mesh, corners):
    """`mesh` plus one detached triangle, material 0."""
    from dataclasses import replace
    base, ub = len(mesh.positions), len(mesh.uvs)
    corners = np.asarray(corners, dtype=np.float64)
    return replace(
        mesh, positions=np.vstack([mesh.positions, corners]),
        uvs=np.vstack([mesh.uvs, corners[:, :2] * 0.05]),
        face_v=np.vstack([mesh.face_v, [[base, base + 1, base + 2]]]),
        face_vt=np.vstack([mesh.face_vt, [[ub, ub + 1, ub + 2]]]),
        face_vn=np.vstack([mesh.face_vn, [[-1, -1, -1]]]),
        face_material=np.append(mesh.face_material, 0),
        face_line=np.append(mesh.face_line, int(mesh.face_line.max()) + 1))


_STRAY = [[5.0, 5.0, 20.0], [7.0, 5.0, 20.0], [5.0, 7.0, 20.0]]      # 2 sq in, 20 in above


def test_fix_object_never_removes_a_face_solidify_invented(monkeypatch):
    """A closed slab, and solidify made to invent one detached 2 sq in triangle above it -- the
    shape the detector removes as a stray when the EXPORT carries it."""
    from engine.fixes.solidify import SolidifyResult
    from engine.tests.fixtures.build import _slab_from_top
    slab = _slab_from_top("closed_slab", [((0, 0), (40, 0), (40, 40)), ((0, 0), (40, 40), (0, 40))])
    profile = FixProfile(guard_size=(120, 80), n_dirs=32)

    exported = fix_object(_with_triangle(slab, _STRAY), {}, profile)
    assert exported.removed_fragments[-1] and exported.n_removed_fragments == 1   # the premise

    real = fix_pipeline.solidify

    def invents_the_stray(mesh, topo, profile_in):
        made = real(mesh, topo, profile_in)
        return SolidifyResult(mesh=_with_triangle(made.mesh, _STRAY),
                              new_faces=np.append(made.new_faces, True), report=made.report)

    monkeypatch.setattr(fix_pipeline, "solidify", invents_the_stray)
    r = fix_object(slab, {}, profile)
    assert r.reference_mesh.n_faces == slab.n_faces + 1
    assert not r.removed_fragments.any() and r.n_removed_fragments == 0
    assert r.fragment_report["n_protected_components"] == 1
    z = r.mesh.positions[r.mesh.face_v][:, :, 2]
    assert int((z == 20.0).all(axis=1).sum()) == 1            # it ships
    assert r.passed is True


def test_every_removed_component_is_reported_with_its_faces_area_and_bbox(tmp_path):
    from engine.tests.test_cli import _write_snapshot

    m = printed(slab_with_strays())
    r = fix_object(m, {}, _FAST)
    assert r.fragment_removals == [
        {"kind": "sliver", "component": 0, "faces": [32], "area": 0.1, "width": 0.02,
         "bbox": [[0.0, -0.02, 0.0], [10.0, 0.0, 0.0]]},
        {"kind": "fragment", "component": 1, "faces": [33], "component_faces": 1, "area": 2.0,
         "bbox": [[0.0, 0.0, 20.0], [2.0, 2.0, 20.0]]}]

    out = tmp_path / "out"
    profile = FixProfile(guard_size=(120, 80), n_dirs=32, qa_size=(160, 100))
    snap = _write_snapshot(tmp_path, m)
    assert cli.cmd_fix(snap, out, accept_slit=False, profile=profile, solidify=False,
                       skp=False) == 0
    report = json.loads((out / m.name / "report.json").read_text(encoding="utf-8"))
    assert report["fragment_removals"] == r.fragment_removals
    assert report["profile"]["fragment_removed_cap"] == profile.fragment_removed_cap
    # the width bound is derived from the print step of the mesh the run READ -- the OBJ round
    # trip re-infers it from the printed text -- and the report says which bound it used
    back = cli._load_snapshot(snap)[1]
    assert report["fragment_report"]["sliver_max_width"] == pytest.approx(
        sliver_width_bound(analyse_topology(back).quanta, profile))
    assert "sliver_max_width" not in report["profile"]
