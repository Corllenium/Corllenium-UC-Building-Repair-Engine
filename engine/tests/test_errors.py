"""The 3D error filter's detector pass: one known answer per kind (spec 2026-09-26)."""
import json

import numpy as np
import pytest

from engine.detectors.errors import KINDS, find_errors
from engine.fixes.pipeline import FixProfile
from engine.tests.fixtures.build import (_mesh, box_with_partition, cube, printed, slab_with_strays,
                                         t_junction_strip, t_junction_strip_with_a_stray,
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


def test_a_one_face_stray_is_loose_and_a_zero_area_face_stays_loose():
    """Review I4: "Zero-area and stray bits" also holds the stray-fragment and sliver candidates the
    fix pipeline's own detector names (`detect_fragments`, at `fix_object`'s tolerances)."""
    e = find_errors(t_junction_strip_with_a_stray(), PROFILE)
    assert e["faces"]["loose"] == [6, 7]            # the zero-area stitch, the detached stray
    assert e["counts"]["loose"] == 2
    assert e["loose_parts"] == {"zero_area": 1, "fragments": 1, "slivers": 0}


def test_an_attached_needle_is_loose_as_a_sliver_and_a_big_detached_quad_is_not():
    """Printed like the real files (0.1 in), so the sliver width bound is their 0.15 in and the
    0.02 in needle hanging off the slab is a sliver candidate (as in test_fragments); the detached
    20 sq in quad, faces 34-35, is kept, as the pipeline keeps it."""
    e = find_errors(printed(slab_with_strays()), PROFILE)
    assert e["faces"]["loose"] == [32, 33]          # the needle (a sliver), the stray triangle
    assert e["loose_parts"] == {"zero_area": 0, "fragments": 1, "slivers": 1}


@pytest.mark.parametrize("build", [two_sided_wall, box_with_partition, t_junction_strip_with_a_stray])
def test_finding_errors_changes_nothing_in_the_mesh(build):
    """Review M6: the plan's Global Constraint -- `find_errors` is read-only. Three fixtures between
    them reach every detector it gathers: flicker pairs, hidden and facade faces, zero-area faces,
    a stray fragment, open edges and a crack."""
    m = build()
    positions, face_v, face_material = m.positions.copy(), m.face_v.copy(), m.face_material.copy()
    find_errors(m, PROFILE)
    assert np.array_equal(m.positions, positions)
    assert np.array_equal(m.face_v, face_v)
    assert np.array_equal(m.face_material, face_material)


def test_the_file_carries_the_current_schema_version():
    """Review M2: 2 since I4, and Tasks 14 and 15, changed what the file means; the API serves no
    file of another version."""
    from engine.detectors.errors import ERRORS_VERSION
    assert ERRORS_VERSION == 2
    assert find_errors(cube(), PROFILE)["version"] == ERRORS_VERSION


def test_the_result_is_plain_json():
    e = find_errors(two_sided_wall(), PROFILE)
    assert json.loads(json.dumps(e)) == e


def test_the_facade_layer_is_every_face_seen_from_outside():
    e = find_errors(box_with_partition(), PROFILE)
    assert e["layers"]["facade"] == list(range(12))   # the 12 outer faces, not the sealed partition
    assert e["layer_counts"]["facade"] == 12
    assert e["counts"]["hidden"] == 2
    assert e["spots"]["facade"][0]["value"] > 0


def test_a_clean_cube_is_all_facade_and_still_has_no_errors():
    e = find_errors(cube(), PROFILE)
    assert e["layers"]["facade"] == list(range(12))
    assert e["counts"] == {k: 0 for k in KINDS}


def test_edges_covered_through_a_t_junction_are_not_open():
    e = find_errors(t_junction_strip(), PROFILE)
    assert e["counts"]["open_edges"] == 7            # the strip's outline only
    assert all(not (abs(s[1] - 10.0) < 1e-6 and abs(s[4] - 10.0) < 1e-6) for s in e["open_edges"])  # none on the T line y = 10
    assert e["counts"]["cracks"] == 1                # the T-junction itself stays a crack point
