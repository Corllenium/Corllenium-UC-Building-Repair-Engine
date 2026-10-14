# engine/tests/test_unity_align.py
import numpy as np
import pytest

from engine.tests.fixtures.build import cube
from engine.unity.align import AlignError, align, to_build_frame


def _as_unity(mesh, matrix, scale):
    from dataclasses import replace
    return replace(mesh, positions=(mesh.positions @ np.asarray(matrix, float).T) * scale)


def test_a_mirrored_scaled_copy_aligns_exactly():
    b = cube(100.0)
    m = np.array([[-1, 0, 0], [0, 0, 1], [0, 1, 0]])       # x mirrored, y and z swapped
    u = _as_unity(b, m, 0.0254)
    a = align(b, u, 0.0254, tol=1e-3)
    assert a.match == 1.0
    np.testing.assert_allclose(to_build_frame(u.positions, a), b.positions, atol=1e-6)


def test_an_unrelated_mesh_is_refused():
    b = cube(100.0)
    u = _as_unity(cube(37.0), np.eye(3), 1.0)
    with pytest.raises(AlignError, match="match"):
        align(b, u, 1.0, tol=1e-3)
