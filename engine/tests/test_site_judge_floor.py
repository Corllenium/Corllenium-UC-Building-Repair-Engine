"""Job P2-V2 item 5: the site judge uses the floor measure in its focus runs, so the kernel's rollback and the floor
verdict agree.

A focus run of `SiteJudge.check` reports the floor's failing faces as failing samples, each with the point of a lost
pixel and the viewpoint that measured it, so `SiteJudge.attribute` charges them to the site that caused them under
its own rules (ruling E3-R8 included: a face only removed is charged to the site that removed it).
"""
import numpy as np

from engine.site_judge import SiteJudge
from engine.tests.fixtures.build import _mesh
from engine.tests.test_validate_checks import _looks, _without_faces
from engine.tests.test_validate_floor import _join, _rect
from engine.tests.test_validate_floor_checks import SIZE, covered_square
from engine.validate.checks import validate


def boxed_square(half_x, half_y):
    """`covered_square` closed into a box -- a base 0.5 in under the square and four walls up to the lid -- so the
    square (faces 0 and 1) shows only through the hole, and last a triangle sealed between the square and the base,
    which nothing sees."""
    def wall(a, b):
        (x0, y0), (x1, y1) = a, b
        return _mesh("wall", [[x0, y0, -0.5], [x1, y1, -0.5], [x1, y1, 1.0], [x0, y0, 1.0]],
                     [[0, 0], [1, 0], [1, 1], [0, 1]], [[0, 1, 2], [0, 2, 3]], [[0, 1, 2], [0, 2, 3]])
    corners = [(0.0, 0.0), (SIZE, 0.0), (SIZE, SIZE), (0.0, SIZE)]
    walls = [wall(corners[k], corners[(k + 1) % 4]) for k in range(4)]
    sealed = _mesh("sealed", [[2.0, 2.0, -0.25], [8.0, 2.0, -0.25], [5.0, 8.0, -0.25]], [[0, 0]] * 3, [[0, 1, 2]],
                   [[0, 0, 0]])
    return _join(covered_square(half_x, half_y), _rect(0.0, SIZE, 0.0, SIZE, -0.5), *walls, sealed)


def _judge_of(before):
    judge = SiteJudge(_looks("m0"))
    judge.begin(before)
    return judge


def test_a_focus_run_fails_a_removed_face_the_floor_fails_and_charges_the_site_that_removed_it():
    before = boxed_square(0.25, 0.25)                    # face 0 shows a 0.5 x 0.5 in patch through a hole in the lid
    after = _without_faces(before, [0, 1])
    judge = _judge_of(before)
    sites = {7: judge.site_focus(after, np.array([0, 1]), np.zeros(0, np.int64))}
    verdict = judge.check(after, judge.union(list(sites.values())))
    floor = verdict.summary["floor"]
    assert verdict.failed and floor["status"] == "FAIL" and floor["faces_failed"] >= 1
    s = verdict.samples
    rows = np.flatnonzero(s.index < 0)                      # the floor's rows: (face, -1 - viewpoint)
    assert len(rows) and set(s.face[rows].tolist()) <= {0, 1}
    assert all({0, 1} >= {f} for f, _i in verdict.failing)
    att = judge.attribute(verdict, sites)
    assert set(att.charged) == {7} and len(att.unknown) == 0 and att.how[7]["touched"] == len(s)

    # the floor verdict of the full Validator, with the judge's own viewpoints, agrees
    full = validate(before, after, _looks("m0"), errors=({"counts": {}, "spots": {}},) * 2)
    assert full.report["checks"]["nothing_deleted"]["floor"]["status"] == "FAIL"


def test_a_focus_run_that_removes_nothing_visible_passes_the_floor():
    before = boxed_square(0.25, 0.25)
    sealed = before.n_faces - 1
    after = _without_faces(before, [sealed])
    judge = _judge_of(before)
    sites = {3: judge.site_focus(after, np.array([sealed]), np.zeros(0, np.int64))}
    verdict = judge.check(after, judge.union(list(sites.values())))
    assert verdict.summary["floor"]["faces_failed"] == 0 and not verdict.failed
