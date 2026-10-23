import numpy as np
import pytest

from engine.rays.caster import BruteCaster
from engine.rays.bounded_brute import BoundedBruteCaster


def assert_matches(positions, faces, origins, directions):
    caster, oracle = BoundedBruteCaster(positions, faces), BruteCaster(positions, faces)
    for actual, expected in zip(caster.first_hit(origins, directions), oracle.first_hit(origins, directions)):
        np.testing.assert_array_equal(actual, expected)
    actual = np.array(caster.all_hits(origins, directions)).T
    expected = np.array(oracle.all_hits(origins, directions)).T
    actual = actual[np.lexsort((actual[:, 1], actual[:, 0]))] if len(actual) else actual
    np.testing.assert_array_equal(actual, expected)
    np.testing.assert_array_equal(caster.any_hit(origins, directions), oracle.any_hit(origins, directions))
    return caster


@pytest.mark.parametrize('seed', range(5))
def test_exhaustive_random_original_mesh_equivalence(seed):
    rng = np.random.default_rng(seed)
    positions = rng.normal(size=(180, 3)) * 800
    faces = np.arange(180).reshape(-1, 3)
    origins = rng.normal(size=(130, 3)) * 1600
    targets = positions[faces[rng.integers(len(faces), size=130)]].mean(axis=1)
    directions = targets - origins
    directions /= np.linalg.norm(directions, axis=1, keepdims=True)
    assert_matches(positions, faces, origins, directions)


def test_collapsed_native_sheets_corners_parallel_and_near_parallel():
    y = 800.123456789
    triangle = np.array([[-1., y, -1.], [1., y, -1.], [0., y, 1.]])
    positions = np.concatenate([triangle, triangle + [0, .00002, 0], triangle])
    faces = np.arange(9).reshape(-1, 3)
    origins = np.array([[0, y + 10, 0], [-1, y + 10, -1], [2, y, 0], [0, y, 0], [0, y - 10, 0.]])
    directions = np.array([[0, -1, 0], [0, -1, 0], [-1, 0, 0], [1, 1e-12, 0], [0, 1, 0.]])
    assert_matches(positions, faces, origins, directions)


def test_grazing_false_native_hit_is_not_an_original_hit():
    y, slope = 800.123456789, 1e-5
    positions = np.array([[-.05, y - .05 * slope, -10.], [.05, y + .05 * slope, -10.], [0., y, 10.]])
    direction = np.array([1., slope + 1e-12, 0.])
    direction /= np.linalg.norm(direction)
    origin = positions.astype(np.float32).astype(float).mean(axis=0) - 10 * direction
    assert_matches(positions, np.array([[0, 1, 2]]), origin[None], direction[None])


def test_sparse_work_and_empty_inputs():
    cells = np.arange(1024) * 10.
    triangle = np.array([[0., 0., 0.], [1., 0., 0.], [0., 1., 0.]])
    positions = (triangle[None] + np.column_stack([cells, cells, np.zeros_like(cells)])[:, None]).reshape(-1, 3)
    faces = np.arange(len(positions)).reshape(-1, 3)
    origins = np.column_stack([cells + .2, cells + .2, np.ones_like(cells)])
    directions = np.tile([0., 0., -1.], (len(cells), 1))
    caster = assert_matches(positions, faces, origins, directions)
    assert caster.search_stats['leaf_pairs'] < len(origins) * len(faces) // 8
    empty = BoundedBruteCaster(np.zeros((0, 3)), np.zeros((0, 3), int))
    assert empty.first_hit(origins[:1], directions[:1])[0].tolist() == [-1]
    assert all(len(x) == 0 for x in empty.all_hits(origins[:1], directions[:1]))


def test_near_parallel_oracle_corner_is_not_pruned_by_a_nearer_box_entry():
    corner = np.array([[0., 0., 0.], [1., 1., 0.], [1., 0., 1.]])
    direction = np.array([[2. + 3e-11, 1., 1.]])
    direction /= np.linalg.norm(direction)
    origin = -3.14 * direction
    corner_t = BruteCaster(corner, np.array([[0, 1, 2]])).first_hit(origin, direction)[1][0]
    q = origin[0] + (corner_t + 3.14) / 2 * direction[0]
    wall = np.array([[q[0], q[1] - .01, q[2] - .01], [q[0], q[1] + .01, q[2] - .01],
                     [q[0], q[1], q[2] + .01]])
    positions = np.concatenate([np.tile(corner, (32, 1)), np.tile(wall, (32, 1))])
    assert_matches(positions, np.arange(len(positions)).reshape(-1, 3), origin, direction)
