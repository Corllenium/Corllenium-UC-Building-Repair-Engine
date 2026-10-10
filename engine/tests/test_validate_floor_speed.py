"""P2-V2 review, finding 3: the removed faces' lattice asks `present` once per (lattice point, side), not once per
viewpoint, and casts `blocker` only for the lines whose point is not already gone. The verdicts must not change:
the per-line path is kept as the reference (`checks._FLOOR_LATTICE_PER_LINE`), and both give the same report.
"""
import numpy as np
import pytest

from engine.tests.test_site_judge_floor import boxed_square
from engine.tests.test_validate_checks import NO_ERRORS, _looks, _with_plate, _without_faces
from engine.tests.test_validate_floor import _rect
from engine.validate import checks

LOOKS = _looks("m0")


def _cases():
    before = boxed_square(0.25, 0.25)
    yield "removed through a hole", before, _without_faces(before, [0, 1])
    plate = _rect(4.0, 5.5, 0.0, 1.0, 0.5)                            # a new plate over part of the removed face
    yield "removed and partly covered", before, _with_plate(_without_faces(before, [1]), plate)
    yield "removed lid piece", before, _without_faces(before, [2, 3, 5])


@pytest.mark.parametrize("name, before, after", list(_cases()), ids=lambda x: x if isinstance(x, str) else "")
def test_present_once_per_point_and_side_gives_the_per_line_verdicts(monkeypatch, name, before, after):
    sphere = dict(errors=(NO_ERRORS, NO_ERRORS))
    monkeypatch.setattr(checks, "_FLOOR_LATTICE_PER_LINE", True)
    reference = checks.validate(before, after, LOOKS, **sphere).report
    monkeypatch.setattr(checks, "_FLOOR_LATTICE_PER_LINE", False)
    fast = checks.validate(before, after, LOOKS, **sphere).report
    drop = lambda r: {k: v for k, v in r.items() if k != "timings_s"}
    assert drop(fast) == drop(reference), name
    assert reference["checks"]["nothing_deleted"]["floor"]["candidates"]["removed_seen"] > 0, "the lattice saw some"
