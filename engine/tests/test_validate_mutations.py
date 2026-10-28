"""Job P0-16: the Validator's proof by mutation (AGENTS.md section 6).

The brief's table: BEFORE is a textured fixture (a cube in two looks, and the closed room), AFTER is BEFORE with
exactly ONE defect, and the named check must FAIL with a reported site AT the defect. AFTER = BEFORE must pass
everything. A Validator that passes a broken floor is worse than none, so these seven rows are the contract.

Face order of `cube()` (two triangles per quad): 0-1 the bottom (z = 0), 2-3 the top (z = 10), 4-5 the y = 0 side,
6-7 the y = 10 side, 8-9 the x = 10 side, 10-11 the x = 0 side.
"""
import dataclasses

import numpy as np

from engine.tests.fixtures.build import closed_room, cube, grid_slab
from engine.tests.test_validate_checks import (_check, _checks, _looks, _moved, _with_flipped, _with_material,
                                               _with_plate, _with_shifted_uv, _without_faces)

SIZE = 10.0
TOP, X_SIDE = [2, 3], [8, 9]


def two_look_cube():
    """The cube in two looks: the top is "roof", the five other sides are "wall"."""
    m = cube(SIZE)
    fm = np.zeros(m.n_faces, dtype=np.int64)
    fm[TOP] = 1
    return dataclasses.replace(m, materials=["wall", "roof"], face_material=fm)


LOOKS = _looks("wall", "roof")
ROOM_LOOKS = _looks("plaster", "brick")


def _site_at(v, point, within=SIZE):
    """Some reported site has its centre within `within` of `point` (the defect)."""
    return any(np.linalg.norm(np.asarray(s["centre"]) - np.asarray(point)) <= within for s in v.report["sites"])


def _failed(v, check):
    """The check's status, and that a site names it."""
    assert v.report["checks"][check]["status"] == "FAIL", (check, v.report["checks"][check])
    assert v.report["verdict"] == "FAIL" and not v.passed
    assert any(check in s["checks"] for s in v.report["sites"]), f"no site names {check}"


# row 1: delete one visible face -> check 3 ---------------------------------------------------------------------

def test_mutation_1_delete_one_visible_face_fails_check_3_at_that_face():
    m = two_look_cube()
    v = _check(m, _without_faces(m, [8]), LOOKS)                      # one triangle of the x = 10 side
    _failed(v, "nothing_deleted")
    gone = v.report["checks"]["nothing_deleted"]
    assert gone["deleted"] == 4 and gone["faces_unmet"] == 1
    (site,) = v.report["sites"]
    assert site["faces"] == [8]
    assert abs(site["centre"][0] - SIZE) < 0.01, "on x = 10"


# row 2: change one visible face's material to a different look -> check 1 ---------------------------------------

def test_mutation_2_a_visible_face_in_a_different_look_fails_check_1_at_that_face():
    m = two_look_cube()
    v = _check(m, _with_material(m, [8], 1), LOOKS)                   # an x = 10 triangle turns "roof"
    _failed(v, "textures")
    textures = v.report["checks"]["textures"]
    assert textures["reasons"]["look"] == 4 and textures["samples_failed"] == 4
    assert textures["reasons"]["deleted"] == textures["reasons"]["uv"] == textures["reasons"]["side"] == 0
    assert v.report["sites"][0]["faces"] == [8] and "textures" in v.report["sites"][0]["checks"]
    assert abs(v.report["sites"][0]["centre"][0] - SIZE) < 0.01, "on x = 10"


# row 3: shift its UVs by 0.5 -> check 1 --------------------------------------------------------------------------

def test_mutation_3_uvs_shifted_by_half_fail_check_1_at_that_face():
    m = two_look_cube()
    v = _check(m, _with_shifted_uv(m, 2, 0.5), LOOKS)                 # a top triangle, UV + 0.5
    _failed(v, "textures")
    textures = v.report["checks"]["textures"]
    assert textures["reasons"]["uv"] == 4 and textures["samples_failed"] == 4
    assert v.report["checks"]["nothing_deleted"]["status"] == "PASS", "the surface and its look are all still there"
    assert v.report["sites"][0]["faces"] == [2] and abs(v.report["sites"][0]["centre"][2] - SIZE) < 0.01, "on z = 10"


# row 4: flip one visible face's winding -> check 1 (back_seen) --------------------------------------------------

def test_mutation_4_a_flipped_visible_face_is_seen_from_behind_and_fails_check_1_at_that_face():
    m = two_look_cube()
    v = _check(m, _with_flipped(m, [2]), LOOKS)
    _failed(v, "textures")
    textures = v.report["checks"]["textures"]
    assert textures["reasons"]["side"] == 4, "`side` is the count of samples whose viewer now sees the back"
    assert v.report["sites"][0]["faces"] == [2] and abs(v.report["sites"][0]["centre"][2] - SIZE) < 0.01


# row 5: add a face 1 in in front of a visible face -> check 3 (covered) -------------------------------------------

def test_mutation_5_a_face_one_inch_in_front_of_a_visible_face_covers_it_for_check_3():
    m = two_look_cube()
    plate = _moved(grid_slab(1, 1, cell=SIZE), [0.0, 0.0, SIZE + 1.0])      # 1 in over the top, same plane normal
    plate = dataclasses.replace(plate, materials=["wall"])
    v = _check(m, _with_plate(m, plate), LOOKS)
    _failed(v, "nothing_deleted")
    gone = v.report["checks"]["nothing_deleted"]
    assert gone["covered"] == 8 and gone["deleted"] == 0 and gone["faces_covered"] == 2, "the top's 2 faces x 4 samples"
    assert v.report["sites"][0]["faces"] == [2, 3] and v.report["sites"][0]["reasons"]["covered"] == 8
    assert abs(v.report["sites"][0]["centre"][2] - SIZE) < 0.01, "the site is the covered top, on z = 10"


# row 6: delete one inner wall of the closed room, seen only by an interior probe -> check 3 ----------------------

def test_mutation_6_a_deleted_inner_wall_only_a_probe_sees_fails_check_3_at_that_wall():
    m = closed_room()
    v = _check(m, _without_faces(m, [4, 5]), ROOM_LOOKS)                   # the wall y = 0, facing into the room
    _failed(v, "nothing_deleted")
    gone = v.report["checks"]["nothing_deleted"]
    assert gone["faces_unmet"] == 2 and gone["deleted"] > 0
    assert all(set(s["faces"]) <= {4, 5} for s in v.report["sites"]), "nothing else of the room is reported"
    assert any(abs(s["centre"][1]) < 0.01 for s in v.report["sites"]), "at y = 0, inside the room"
    # the room's outer skin is untouched: no outside viewpoint ever saw the wall, only the probes did
    assert v.report["viewpoints"]["probes"] == 40


# row 7: AFTER = BEFORE -> all PASS ---------------------------------------------------------------------------------

def test_mutation_7_after_equals_before_passes_everything():
    for before, looks in ((two_look_cube(), LOOKS), (closed_room(), ROOM_LOOKS)):
        v = _check(before, before, looks)
        textures, gone = _checks(v)
        assert (textures["status"], gone["status"], v.report["verdict"]) == ("PASS", "PASS", "PASS")
        assert v.passed and v.report["sites"] == []
        assert textures["samples_failed"] == 0 and gone["deleted"] == gone["covered"] == gone["replaced"] == 0
