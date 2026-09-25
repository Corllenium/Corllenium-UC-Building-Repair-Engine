"""The 3D error filter's detector pass: one known answer per kind (spec 2026-09-26)."""
import json

import numpy as np
import pytest

from engine.detectors.errors import KINDS, find_errors
from engine.fixes.pipeline import FixProfile
from engine.tests.fixtures.build import (_mesh, box_with_partition, cube, t_junction_strip,
                                         two_sided_wall)

PROFILE = FixProfile(n_dirs=32)


def test_a_clean_closed_cube_has_no_errors():
    e = find_errors(cube(), PROFILE)
    assert e["n_faces"] == 12
    assert e["counts"] == {k: 0 for k in KINDS}


def test_a_two_sided_wall_is_red_flicker_with_its_partner():
    e = find_errors(two_sided_wall(), PROFILE)
    assert e["faces"]["flicker_diff"] == [0, 1, 2, 3]
    assert e["faces"]["flicker_same"] == []
    pairs = {(i, j) for i, j, _s, _o in e["flicker_pairs"]}
    assert pairs == {(0, 2), (1, 3)}
    assert all(o for *_rest, o in e["flicker_pairs"])
    spot = e["spots"]["flicker_diff"][0]
    assert spot["centre"] == pytest.approx([20.0, 0.0, 20.0], abs=1.0)
    assert spot["value"] > 0  # visible pixels


def test_a_face_sealed_inside_a_box_is_hidden():
    e = find_errors(box_with_partition(), PROFILE)
    assert e["faces"]["hidden"] == [12, 13]
    assert e["counts"]["hidden"] == 2


def test_a_face_turned_inside_out_is_reversed():
    m = cube()
    m.face_v[0] = m.face_v[0][[0, 2, 1]]
    m.face_vt[0] = m.face_vt[0][[0, 2, 1]]
    e = find_errors(m, PROFILE)
    assert e["faces"]["reversed"] == [0]


def test_a_flat_square_has_four_open_edges():
    P = [[0, 0, 0], [10, 0, 0], [10, 10, 0], [0, 10, 0]]
    m = _mesh("square", P, [[0, 0], [1, 0], [1, 1], [0, 1]], [[0, 1, 2], [0, 2, 3]], [[0, 1, 2], [0, 2, 3]])
    e = find_errors(m, PROFILE)
    assert e["counts"]["open_edges"] == 4
    lengths = sorted(round(float(np.linalg.norm(np.subtract(s[3:], s[:3]))), 3) for s in e["open_edges"])
    assert lengths == [10.0, 10.0, 10.0, 10.0]


def test_a_t_junction_is_a_crack_and_its_stitch_is_loose():
    e = find_errors(t_junction_strip(), PROFILE)
    assert [10.0, 10.0, 0.0] in [[round(v, 3) for v in p] for p in e["cracks"]]
    assert e["faces"]["loose"] == [6]  # the zero-area stitching triangle (3, 4, 2)


def test_the_result_is_plain_json():
    e = find_errors(two_sided_wall(), PROFILE)
    assert json.loads(json.dumps(e)) == e
