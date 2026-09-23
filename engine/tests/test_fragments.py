"""F1: stray fragments and attached slivers, found and removed under a FRAGMENT-mode guard.

A stray is geometry that is not part of anything: a triangle left behind by a delete, a scrap of
a component that was moved away, a needle of a face too thin to be anything. None of it can be
caught by the hidden-face pass, because a stray is usually plainly visible -- which is exactly
why its removal needs a guard of its own, one that permits the pixels the stray itself occupied
and nothing else.
"""
import numpy as np

import engine.cli as cli
from engine.detectors.fragments import detect_fragments
from engine.fixes.pipeline import FixProfile, fix_object
from engine.pipeline import analyse_topology
from engine.tests.fixtures.build import slab_with_strays

_FAST = FixProfile(guard_size=(120, 80), n_dirs=32, solidify=False)


def _fast(**overrides):
    return FixProfile(guard_size=(120, 80), n_dirs=32, solidify=False, **overrides)


def _detected(mesh, profile=None):
    topo = analyse_topology(mesh)
    return detect_fragments(topo.positions_w, topo.face_w, profile or _FAST)


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
    m = slab_with_strays()
    d = _detected(m)
    assert d.slivers.tolist() == [False] * 32 + [True] + [False] * 3
    assert d.report["n_sliver_faces"] == 1
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
    m = slab_with_strays()
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
    r = fix_object(slab_with_strays(), {}, _FAST)
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
    m = slab_with_strays()
    a, b = fix_object(m, {}, _FAST), fix_object(m, {}, _FAST)
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
