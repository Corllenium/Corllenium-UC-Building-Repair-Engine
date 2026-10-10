"""Job P2-V2 items 2 and 6: removed faces go to the floor measure, and check 3 fails above the floor.

A removed face goes to the measure when an area-scaled lattice (at least 36 points, plus one per sq in, at most 4,096
per face) finds a point some viewpoint sees, from either side. Check 3 fails when such a face shows more than
`VISIBLE_FLOOR_PX` pixels (at 0.02 in/px) from any one viewpoint. The removed face here lies under a lid, seen only
through a hole over one of its lattice points and none of the Validator's own samples, so today's sampling never
sees it (P2-E3: CHTM 5th face 8480, 0 of 9 samples seen, 190 of 1,770 dense points).
"""
import json

import numpy as np
import pytest
from PIL import Image

from engine.tests.fixtures.build import _mesh
from engine.tests.test_validate_checks import _check, _checks, _looks, _without_faces
from engine.tests.test_validate_floor import _join, _rect
from engine.validate.evidence import write_evidence
from engine.validate.floor import (FLOOR_IN_PER_PX, LATTICE_CAP, LATTICE_MIN, LATTICE_PER_SQ_IN, VISIBLE_FLOOR_PX,
                                   floor_lattice)
from engine.validate.sampling import face_samples

SIZE = 10.0
DOWN = np.array([[0.0, 0.0, -1.0]])
NONE = np.zeros((0, 3))
LOOKS = _looks("m0")
#: one point of face 0's lattice (n = 10: 36 + 50 sq in = 86 points, so a 10 x 10 lattice), far from its 4 samples
POINT_BARY = np.array([1.0 - 14.0 / 30.0, 13.0 / 30.0, 1.0 / 30.0])


def _floor_square():
    """A 10 in square at z = 0 in two triangles (faces 0 and 1), wound upward."""
    return _rect(0.0, SIZE, 0.0, SIZE, 0.0)


def _point():
    sq = _floor_square()
    return POINT_BARY @ sq.positions[sq.face_v[0]]


def covered_square(half_x, half_y):
    """The square under a lid 1 in up, with a hole of half-widths `half_x`, `half_y` centred over `_point()`."""
    p = _point()
    x0, x1, y0, y1 = p[0] - half_x, p[0] + half_x, p[1] - half_y, p[1] + half_y
    xs, ys = (0.0, x0, x1, SIZE), (0.0, y0, y1, SIZE)
    lid = [_rect(xs[i], xs[i + 1], ys[j], ys[j + 1], 1.0) for i in range(3) for j in range(3) if (i, j) != (1, 1)]
    return _join(_floor_square(), *lid)


def _judge(before, after):
    return _check(before, after, LOOKS, dirs=DOWN, cams=NONE, probes=NONE, extra_dirs=NONE)


def test_the_lattice_is_36_points_plus_one_per_square_inch_capped_at_4096():
    assert (LATTICE_MIN, LATTICE_PER_SQ_IN, LATTICE_CAP) == (36, 1.0, 4096)
    tiny = _mesh("t", [[0, 0, 0], [1, 0, 0], [0, 1, 0]], [[0, 0]] * 3, [[0, 1, 2]], [[0, 0, 0]])
    huge = _mesh("h", [[0, 0, 0], [200, 0, 0], [0, 200, 0]], [[0, 0]] * 3, [[0, 1, 2]], [[0, 0, 0]])
    assert len(floor_lattice(tiny, [0])) == 49                      # 36 + 1 -> the 7 x 7 lattice
    assert len(floor_lattice(_floor_square(), [0])) == 100          # 36 + 50 -> 10 x 10
    assert len(floor_lattice(huge, [0])) == 4096                    # 36 + 20,000 -> capped: 64 x 64
    lattice = floor_lattice(_floor_square(), [0])
    assert np.isclose(np.abs(lattice.bary - POINT_BARY).sum(axis=1), 0.0).any(), "the hole's point is a lattice point"
    samples = face_samples(_floor_square(), faces=[0])
    assert not np.isclose(np.abs(samples.bary - POINT_BARY).sum(axis=1), 0.0).any(), "and none of the samples"


def test_mutation_a_removed_face_seen_through_a_half_inch_slot_fails_check_3_on_the_floor():
    before = covered_square(0.25, 0.25)                               # a 0.5 x 0.5 in patch of face 0 shows
    v = _judge(before, _without_faces(before, [0, 1]))
    textures, gone = _checks(v)
    assert gone["deleted"] == 0 and gone["covered"] == 0, "the Validator's own samples never see the face"
    floor = gone["floor"]
    assert gone["status"] == "FAIL" and v.report["verdict"] == "FAIL"
    assert floor["status"] == "FAIL" and floor["faces_failed"] == 1
    (bad,) = floor["failing"]
    assert bad["face"] == 0 and bad["kind"] == "removed"
    assert 600 <= bad["pixels"] <= 650, bad                            # 25 x 25 px
    assert bad["viewpoint"]["kind"] == "direction" and bad["viewpoint"]["index"] == 0
    assert floor["lattice"] == {"min": 36, "per_sq_in": 1.0, "cap": 4096, "faces": 2, "points": 200}
    assert floor["floor_px"] == VISIBLE_FLOOR_PX and floor["in_per_px"] == FLOOR_IN_PER_PX


def test_a_removed_face_whose_worst_view_shows_3_pixels_passes():
    # V2-R1: 3 px in total from its worst viewpoint. The hole spans three pixel centres of face 0's grid in x
    # (0.06 in wide) and one in y (0.02 in), centred on the lattice point, which is itself a pixel centre.
    before = covered_square(0.03, 0.01)
    v = _judge(before, _without_faces(before, [0, 1]))
    floor = v.report["checks"]["nothing_deleted"]["floor"]
    assert floor["status"] == "PASS" and floor["faces_failed"] == 0 and floor["failing"] == []
    (measured,) = floor["measured"]
    assert measured["face"] == 0 and measured["pixels"] == 3, measured
    assert v.report["verdict"] == "PASS"


def test_an_unchanged_floor_measures_nothing():
    before = covered_square(0.25, 0.25)
    v = _judge(before, before)
    floor = v.report["checks"]["nothing_deleted"]["floor"]
    assert floor["status"] == "PASS" and floor["measured"] == [] and floor["lattice"]["faces"] == 0


def test_a_crop_before_and_after_is_written_for_every_face_measured_above_0(tmp_path):
    before = covered_square(0.25, 0.25)
    v = _judge(before, _without_faces(before, [0, 1]))
    write_evidence(v, tmp_path)
    (bad,) = v.report["checks"]["nothing_deleted"]["floor"]["failing"]
    crop = tmp_path / bad["crop"]
    assert crop.is_file()
    with Image.open(crop) as image:
        w, h = image.size
        pixels = np.asarray(image.convert("RGB"))
    assert w > 2 * h - 20, "BEFORE and AFTER side by side"
    left, right = pixels[:, : w // 2], pixels[:, w // 2:]
    assert not np.array_equal(left[:, : right.shape[1]], right[:, : left.shape[1]]), "the face is gone in AFTER"
    measured = v.report["checks"]["nothing_deleted"]["floor"]["measured"]
    assert all(m["crop"] for m in measured if m["pixels"] > 0)
    json.dumps(v.report)                                                 # the report stays JSON
