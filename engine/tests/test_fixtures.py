import numpy as np
from engine.tests.fixtures.build import cube, grid_slab, t_junction_strip


def test_cube_is_12_outward_triangles():
    m = cube(10.0)
    assert m.n_faces == 12 and m.positions.shape == (8, 3)
    p = m.positions[m.face_v]
    n = np.cross(p[:, 1] - p[:, 0], p[:, 2] - p[:, 0])
    centre = m.positions.mean(axis=0)
    assert (np.einsum("ij,ij->i", n, p.mean(axis=1) - centre) > 0).all()


def test_grid_slab_counts():
    m = grid_slab(10, 10)
    assert m.n_faces == 200 and m.positions.shape == (121, 3) and m.uvs.shape == (400, 2)


def test_t_junction_strip_has_one_zero_area_face():
    m = t_junction_strip()
    p = m.positions[m.face_v]
    area = 0.5 * np.linalg.norm(np.cross(p[:, 1] - p[:, 0], p[:, 2] - p[:, 0]), axis=1)
    assert m.n_faces == 7 and int((area == 0).sum()) == 1
