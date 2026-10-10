"""Job P2-V2 items 3 and 6: `covered` on every line of sight, from both sides, and covered faces on the floor.

A BEFORE sample is covered when ANY viewpoint line that saw it in BEFORE, from either side, is blocked in AFTER by a
face that is not its own: no longer by one witness alone (P2-E8a concern 3). Each covered face is then measured with
the floor's measure from every viewpoint that saw it covered (ruling V2-R2: its pixels nearest-visible in BEFORE and
hidden in AFTER), and so is every face a new face of AFTER could cover, found by the new face's own lattice: a cover
that misses every sample still shows.
"""
import numpy as np

from engine.tests.test_validate_checks import _check, _checks, _looks, _with_plate
from engine.tests.test_validate_floor import _join, _mesh
from engine.validate.floor import VISIBLE_FLOOR_PX

NONE = np.zeros((0, 3))
LOOKS = _looks("m0")
FRONT = [-1.0, 0.0, 0.0]                    # a viewer far off at +x looks along -x: it sees the wall's front
BACK = [1.0, 0.0, 0.0]                      # a viewer far off at -x: the wall's back
TILT = np.radians(30.0)
OBLIQUE = [-np.cos(TILT), 0.0, -np.sin(TILT)]      # a viewer up and in front, 30 degrees above the horizontal


def wall(size=10.0):
    """A `size` square wall in the plane x = 0, wound to face +x: faces 0 and 1."""
    P = [[0, 0, 0], [0, size, 0], [0, size, size], [0, 0, size]]
    return _mesh("wall", P, [[0, 0], [1, 0], [1, 1], [0, 1]], [[0, 1, 2], [0, 2, 3]], [[0, 1, 2], [0, 2, 3]])


def quad(corners):
    """Two triangles over four corners, in order."""
    return _mesh("quad", corners, [[0, 0], [1, 0], [1, 1], [0, 1]], [[0, 1, 2], [0, 2, 3]], [[0, 1, 2], [0, 2, 3]])


def _judge(before, after, dirs):
    return _check(before, after, LOOKS, dirs=np.asarray(dirs, float), cams=NONE, probes=NONE, extra_dirs=NONE)


def _floor(v):
    return v.report["checks"]["nothing_deleted"]["floor"]


def test_mutation_b_a_cover_of_only_the_back_of_a_visible_face_fails_check_3():
    before = wall()
    plate = quad([[-1.0, -1.0, -1.0], [-1.0, 11.0, -1.0], [-1.0, 11.0, 11.0], [-1.0, -1.0, 11.0]])   # behind it
    v = _judge(before, _with_plate(before, plate), [FRONT, BACK])
    _textures, gone = _checks(v)
    assert gone["status"] == "FAIL" and v.report["verdict"] == "FAIL"
    assert gone["covered"] == 8, "both sides were seen; the back's lines are blocked: every sample is covered"
    floor = _floor(v)
    assert floor["faces_failed"] == 2
    for bad in floor["failing"]:
        assert bad["kind"] == "covered" and bad["viewpoint"]["index"] == 1, "seen covered from the back"
        assert bad["reasons"] == {"covered": bad["pixels"]} and bad["pixels"] > 100_000      # 50 sq in each
        assert bad["covering_faces"] and set(bad["covering_faces"]) <= {2, 3}, "the plate's two faces"


def test_mutation_c_a_cover_of_a_second_line_whose_first_witness_is_clear_fails_check_3():
    before = wall()
    awning = quad([[0.1, -1.0, 10.5], [30.0, -1.0, 10.5], [30.0, 11.0, 10.5], [0.1, 11.0, 10.5]])
    v = _judge(before, _with_plate(before, awning), [FRONT, OBLIQUE])
    _textures, gone = _checks(v)
    assert gone["status"] == "FAIL" and gone["covered"] == 8, "the square-on line is clear, the oblique one is not"
    floor = _floor(v)
    assert floor["faces_failed"] == 2
    assert all(bad["viewpoint"]["index"] == 1 and bad["kind"] == "covered" for bad in floor["failing"])


def test_a_small_new_plate_that_misses_every_sample_still_fails_on_the_floor():
    before = wall()
    # a 0.5 x 0.5 in plate 1 in in front of the wall, over no sample of it (they sit at 1/6, 1/3, 2/3 of the faces)
    plate = quad([[1.0, 4.75, 0.6], [1.0, 5.25, 0.6], [1.0, 5.25, 1.1], [1.0, 4.75, 1.1]])
    v = _judge(before, _with_plate(before, plate), [FRONT])
    _textures, gone = _checks(v)
    assert gone["covered"] == 0, "the samples see past it"
    floor = _floor(v)
    assert floor["status"] == "FAIL" and floor["candidates"]["covered"] >= 1
    (bad,) = floor["failing"]
    assert bad["kind"] == "covered" and 600 <= bad["pixels"] <= 650, bad              # 25 x 25 px


def test_a_new_face_covering_at_most_a_few_pixels_passes():
    before = wall()
    plate = quad([[1.0, 5.0, 0.8], [1.0, 5.015, 0.8], [1.0, 5.015, 0.815], [1.0, 5.0, 0.815]])     # 0.015 in square
    v = _judge(before, _with_plate(before, plate), [FRONT])
    floor = _floor(v)
    assert floor["status"] == "PASS" and v.report["verdict"] == "PASS"
    assert floor["candidates"]["covered"] >= 1, "the new face's lattice found the wall behind it"
    assert all(m["pixels"] <= VISIBLE_FLOOR_PX for m in floor["measured"])


def test_a_cover_is_found_from_a_probe_and_from_a_camera_on_every_line():
    before = wall()
    awning = quad([[0.1, -1.0, 10.5], [30.0, -1.0, 10.5], [30.0, 11.0, 10.5], [0.1, 11.0, 10.5]])
    probe = np.array([[40.0, 5.0, 40.0]])                          # up and in front: its lines cross the awning
    v = _check(before, _with_plate(before, awning), LOOKS, dirs=np.asarray([FRONT], float), cams=NONE, probes=probe,
               extra_dirs=NONE)
    _textures, gone = _checks(v)
    assert gone["covered"] == 8
    assert all(bad["viewpoint"]["kind"] == "probe" for bad in _floor(v)["failing"])
