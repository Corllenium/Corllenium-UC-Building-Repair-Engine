"""The shared flicker split by look (P1-H1 item 1): same look = one material (decision-sheet answer 3)."""
from __future__ import annotations

import numpy as np

from engine.detectors.errors import find_errors
from engine.tests.fixtures.build import two_sided_wall


def _pairs(mesh):
    pairs = find_errors(mesh)["flicker_pairs"]
    assert len(pairs) == 2
    return pairs


def test_two_materials_of_one_look_are_same_look():
    from engine.campus.materials import split_flicker_pairs
    mesh = two_sided_wall()                      # concrete and prismarine, facing opposite ways
    pairs = _pairs(mesh)
    same, diff = split_flicker_pairs(mesh, pairs, {"concrete": {"look": "L"}, "prismarine": {"look": "L"}})
    assert same == pairs and diff == []


def test_two_looks_are_different_look():
    from engine.campus.materials import split_flicker_pairs
    mesh = two_sided_wall()
    pairs = _pairs(mesh)
    same, diff = split_flicker_pairs(mesh, pairs, {"concrete": {"look": "A"}, "prismarine": {"look": "B"}})
    assert same == [] and diff == pairs


def test_a_material_missing_from_the_map_is_its_own_look():
    from engine.campus.materials import split_flicker_pairs
    mesh = two_sided_wall()
    pairs = _pairs(mesh)
    # one named, one missing: different looks even though the named one's look key equals the other's name
    same, diff = split_flicker_pairs(mesh, pairs, {"concrete": {"look": "prismarine"}})
    assert same == [] and diff == pairs
    # both missing: still two looks (two materials), not one
    same, diff = split_flicker_pairs(mesh, pairs, {})
    assert same == [] and diff == pairs


def test_the_map_may_be_the_materials_json_with_its_materials_key_or_plain_name_to_look():
    from engine.campus.materials import split_flicker_pairs
    mesh = two_sided_wall()
    pairs = _pairs(mesh)
    wrapped = {"materials": {"concrete": {"look": "L"}, "prismarine": {"look": "L"}}}
    assert split_flicker_pairs(mesh, pairs, wrapped)[0] == pairs
    assert split_flicker_pairs(mesh, pairs, {"concrete": "L", "prismarine": "L"})[0] == pairs


def test_a_pair_of_one_material_is_same_look_even_when_the_map_is_empty():
    from engine.campus.materials import split_flicker_pairs
    mesh = two_sided_wall()
    mesh.face_material[:] = 0                    # every face concrete
    pairs = [(0, 1, 1.0, True)]
    same, diff = split_flicker_pairs(mesh, pairs, {})
    assert same == pairs and diff == []


def test_face_sets_put_a_face_in_diff_when_any_of_its_pairs_differs():
    from engine.campus.materials import flicker_faces_by_look
    mesh = two_sided_wall()
    mesh.face_material[:] = [0] * (len(mesh.face_material) - 1) + [1]
    last = len(mesh.face_material) - 1
    pairs = [(0, 1, 1.0, False), (1, last, 1.0, True)]
    looks = {"concrete": {"look": "A"}, "prismarine": {"look": "B"}}
    same, diff = flicker_faces_by_look(mesh, pairs, looks)
    assert diff == {1, last} and same == {0}     # face 1 is in a same-look and a different-look pair: diff wins


def test_the_census_split_counts_what_the_shared_split_returns():
    from engine.campus.census import flicker_split
    from engine.campus.materials import split_flicker_pairs
    mesh = two_sided_wall()
    pairs = _pairs(mesh)
    for looks in ({"concrete": {"look": "L"}, "prismarine": {"look": "L"}},
                  {"concrete": {"look": "A"}, "prismarine": {"look": "B"}}):
        same, diff = split_flicker_pairs(mesh, pairs, looks)
        split = flicker_split(mesh, pairs, materials=looks)
        assert split["same_look"] == len(same) and split["diff_look"] == len(diff)
