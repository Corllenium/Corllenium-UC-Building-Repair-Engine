"""Job P2-V2 item 8: outside views come only from directions at or above the horizon (owner, 2026-10-10, AGENTS.md
section 5, Viewpoints). Nobody looks up from under the ground, so a surface seen only from below it (a slab's open
underside) is not visible. Ring cameras and eye-height probes are unchanged.

Sign rule: a direction `d` is a LOOK direction; the viewer stands infinitely far off at `-d`. The viewer is at or above
the horizon when `-d` has z >= 0, that is `d_z <= 0`: the view ray travels downward or level (the frame is Z up).
"""
import numpy as np

from engine.tests.fixtures.build import _mesh
from engine.tests.test_validate_checks import NO_ERRORS, _check, _looks, _with_plate, _without_faces
from engine.tests.test_site_judge_floor import boxed_square
from engine.validate.checks import validate
from engine.validate.viewpoints import above_horizon_directions, outside_directions

LOOKS = _looks("m0")


def _box(size=40.0, height=8.0, bottom=False):
    """A `size` x `size` x `height` box of outward-wound quads: the top and four sides, and the bottom when asked
    (its two faces last)."""
    s, h = size, height
    quads = [[(0, 0, h), (s, 0, h), (s, s, h), (0, s, h)],
             [(0, 0, 0), (s, 0, 0), (s, 0, h), (0, 0, h)], [(s, 0, 0), (s, s, 0), (s, s, h), (s, 0, h)],
             [(s, s, 0), (0, s, 0), (0, s, h), (s, s, h)], [(0, s, 0), (0, 0, 0), (0, 0, h), (0, s, h)]]
    if bottom:
        quads.append([(0, 0, 0), (0, s, 0), (s, s, 0), (s, 0, 0)])
    P, fv = [], []
    centre = np.array([s / 2, s / 2, h / 2])
    for q in quads:
        q = np.asarray(q, dtype=float)
        n = np.cross(q[1] - q[0], q[2] - q[0])
        if n @ (q.mean(axis=0) - centre) < 0:
            q = q[::-1]
        k = len(P)
        P.extend(q.tolist())
        fv += [[k, k + 1, k + 2], [k, k + 2, k + 3]]
    return _mesh("box", P, [[0, 0]] * len(P), fv, [[0, 0, 0]] * len(fv))


def test_the_directions_kept_are_those_whose_viewer_is_at_or_above_the_horizon():
    for n in (128, 1024):
        all_dirs, kept = outside_directions(n), above_horizon_directions(n)
        assert (kept[:, 2] <= 0.0).all(), "the view ray travels downward or level"
        assert len(kept) == int((all_dirs[:, 2] <= 0.0).sum()) == n // 2
        assert {tuple(d) for d in kept} <= {tuple(d) for d in all_dirs}, "the same directions, restricted"


def test_closing_a_slabs_underside_that_only_a_viewer_below_the_ground_sees_passes():
    before, after = _box(), _box(bottom=True)
    v = _check(before, after, LOOKS)
    textures, gone = v.report["checks"]["textures"], v.report["checks"]["nothing_deleted"]
    assert v.report["viewpoints"]["directions"] == 64 and v.report["viewpoints"]["extra_directions"] == 512
    assert gone["status"] == "PASS" and gone["covered"] == 0 and gone["floor"]["faces_failed"] == 0
    assert textures["status"] == "PASS" and v.report["verdict"] == "PASS"


def test_a_cover_seen_from_above_is_judged_as_before():
    before = _box()
    lid = _mesh("lid", [[0, 0, 9.0], [40, 0, 9.0], [40, 40, 9.0], [0, 40, 9.0]], [[0, 0]] * 4,
                [[0, 1, 2], [0, 2, 3]], [[0, 0, 0]] * 2)                 # a plate 1 in over the top, seen from above
    v = _check(before, _with_plate(before, lid), LOOKS)
    gone = v.report["checks"]["nothing_deleted"]
    assert gone["status"] == "FAIL" and gone["covered"] > 0 and gone["floor"]["faces_failed"] >= 2


def test_the_slot_mutation_still_fails_from_the_owners_viewpoints():
    before = boxed_square(0.25, 0.25)                    # the 0.5 x 0.5 in patch of a removed face, under a lid
    v = validate(before, _without_faces(before, [0, 1]), LOOKS, errors=(NO_ERRORS, NO_ERRORS))
    floor = v.report["checks"]["nothing_deleted"]["floor"]
    assert floor["status"] == "FAIL" and {e["face"] for e in floor["failing"]} & {0, 1}
