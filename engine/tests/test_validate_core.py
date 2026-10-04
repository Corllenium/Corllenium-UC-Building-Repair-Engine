"""Job P0-14: the Validator's core -- face samples, viewpoints (outside, and at eye height inside)
and what each viewpoint sees.

`engine/validate/` judges the repair engine, so it is written from scratch: nothing in it may be
built on `engine/guard/` (see `test_the_validator_imports_nothing_it_judges`).
"""
import dataclasses

import numpy as np

from engine.tests.fixtures.build import cube, grid_slab
from engine.validate.sampling import (bbox_centre, face_areas, face_normals, face_samples,
                                      recentred, uv_at)


# ---------------------------------------------------------------------------------------------
# Item 1: face samples and UV interpolation
# ---------------------------------------------------------------------------------------------

def _weights_of(mesh, face, points):
    """Barycentric weights of `points` in their own triangles and their distance from the
    triangle's plane, recomputed from scratch (Gram-matrix form), so the test does not simply echo
    the code under test."""
    T = mesh.positions[mesh.face_v[face]]
    a, b, c = T[:, 0], T[:, 1], T[:, 2]
    v0, v1, v2 = b - a, c - a, points - a
    d00, d01, d11 = (v0 * v0).sum(1), (v0 * v1).sum(1), (v1 * v1).sum(1)
    d20, d21 = (v2 * v0).sum(1), (v2 * v1).sum(1)
    den = d00 * d11 - d01 * d01
    wb = (d11 * d20 - d01 * d21) / den
    wc = (d00 * d21 - d01 * d20) / den
    normal = np.cross(v0, v1)
    normal /= np.linalg.norm(normal, axis=1, keepdims=True)
    return np.stack([1.0 - wb - wc, wb, wc], axis=1), np.abs((v2 * normal).sum(1))


def test_face_samples_gives_at_least_four_inside_each_triangle_and_repeats_exactly():
    m = grid_slab(3, 3)                                    # 18 triangles of 50 sq in
    s = face_samples(m)

    counts = np.bincount(s.face, minlength=m.n_faces)
    assert (counts >= 4).all()
    assert s.points.shape == (len(s.face), 3) and s.points.dtype == np.float64
    assert s.bary.shape == (len(s.face), 3) and s.face.dtype == np.int64

    w, off_plane = _weights_of(m, s.face, s.points)
    assert (w > 0.0).all(), "every sample lies strictly inside its triangle, not on an edge"
    assert np.allclose(w.sum(axis=1), 1.0)
    assert np.allclose(w, s.bary, atol=1e-9), "the reported weights are the point's real weights"
    assert off_plane.max() < 1e-9

    again = face_samples(m)
    assert np.array_equal(s.points, again.points)
    assert np.array_equal(s.face, again.face)
    assert np.array_equal(s.bary, again.bary)


def test_face_samples_spreads_by_area_and_every_sample_stands_for_the_same_area():
    # one 120 x 120 in cell = two triangles of 7200 sq in: ceil(7200 / 36) = 200 wanted, so the
    # lattice is 15 x 15 = 225 per triangle; a 10 in cell's triangles (50 sq in) keep the minimum 4
    big, small = grid_slab(1, 1, cell=120.0), grid_slab(1, 1, cell=10.0)
    assert np.allclose(face_areas(big), 7200.0) and np.allclose(face_areas(small), 50.0)
    assert np.bincount(face_samples(big).face).tolist() == [225, 225]
    assert np.bincount(face_samples(small).face).tolist() == [4, 4]

    # the parameters mean what they say
    assert np.bincount(face_samples(big, area_per_sample=1800.0).face).tolist() == [4, 4]
    assert np.bincount(face_samples(small, min_per_face=9).face).tolist() == [9, 9]
    assert np.bincount(face_samples(small, min_per_face=1, area_per_sample=100.0).face).tolist() == [1, 1]

    # equal areas per sample: the lattice's cells are congruent, so the samples of one face
    # average to its centroid whatever their number
    for mesh in (big, small):
        s = face_samples(mesh)
        for f in range(mesh.n_faces):
            assert np.allclose(s.bary[s.face == f].mean(axis=0), 1.0 / 3.0, atol=1e-12)


def test_face_samples_can_be_limited_to_some_faces_in_the_order_given():
    m = grid_slab(3, 3)
    s = face_samples(m, faces=np.array([7, 2]))
    assert sorted(set(s.face.tolist())) == [2, 7]
    assert s.face[0] == 7 and s.face[-1] == 2, "in the order given, not sorted"
    assert np.array_equal(s.points[s.face == 2], face_samples(m).points[face_samples(m).face == 2])

    mask = np.zeros(m.n_faces, bool)
    mask[[0, 17]] = True
    assert sorted(set(face_samples(m, faces=mask).face.tolist())) == [0, 17]
    assert len(face_samples(m, faces=np.zeros(0, np.int64))) == 0


def test_face_samples_on_a_zero_area_face_still_gives_points_on_the_face_but_no_normal():
    m = grid_slab(1, 1, cell=10.0)
    m.face_v[1] = [0, 0, 3]                                # the second triangle becomes the diagonal
    s = face_samples(m)
    assert (np.bincount(s.face) == 4).all()
    on_line = s.points[s.face == 1]
    assert np.allclose(on_line[:, 1], on_line[:, 0]), "points of the line from (0,0) to (10,10)"
    assert (on_line[:, 0] > 0).all() and (on_line[:, 0] < 10).all()
    assert face_areas(m)[1] == 0.0
    assert np.array_equal(face_normals(m)[1], np.zeros(3)), "no area, no normal"
    assert np.allclose(face_normals(m)[0], [0.0, 0.0, 1.0])


def test_a_face_collinear_up_to_float_noise_has_no_normal_but_a_real_sliver_has_one():
    m = grid_slab(1, 1, cell=10.0)
    m.positions = np.array([[0.0, 0.0, 0.0], [5.0, 5.0, 0.0], [10.0, 10.0 + 1e-12, 0.0],
                            [500.0, 1e-3, 0.0], [1000.0, 0.0, 0.0]])
    m.face_v = np.array([[0, 1, 2], [0, 4, 3]], dtype=np.int64)
    m.face_vt = m.face_vt[:2]
    assert 0.0 < face_areas(m)[0] < 1e-9, "a hair of area: collinear to 1e-12"
    assert np.array_equal(face_normals(m)[0], np.zeros(3)), "a random direction is not a normal"
    assert np.isclose(face_areas(m)[1], 0.5)
    assert np.allclose(face_normals(m)[1], [0.0, 0.0, 1.0]), "1000 in long, 0.001 in wide: real"


def test_face_normals_follow_the_winding():
    m = cube(10.0)
    n = face_normals(m)
    assert np.allclose(np.linalg.norm(n, axis=1), 1.0)
    # cube(): faces 0-1 bottom, 2-3 top, 4-5 y = 0, 6-7 y = s, 8-9 x = s, 10-11 x = 0
    expect = np.repeat([[0, 0, -1], [0, 0, 1], [0, -1, 0], [0, 1, 0], [1, 0, 0], [-1, 0, 0]], 2, axis=0)
    assert np.allclose(n, expect)


def test_uv_at_a_corners_weight_returns_that_corners_uv():
    m = cube()
    f = np.arange(m.n_faces)
    for k in range(3):
        bary = np.zeros((m.n_faces, 3))
        bary[:, k] = 1.0
        assert np.array_equal(uv_at(m, f, bary), m.uvs[m.face_vt[f, k]])
    centre = uv_at(m, f, np.full((m.n_faces, 3), 1.0 / 3.0))
    assert np.allclose(centre, m.uvs[m.face_vt[f]].mean(axis=1))


def test_uv_at_follows_the_surface_when_the_texture_is_linear_in_position():
    m = grid_slab(3, 3, uv_per_unit=0.05)                  # uv = (x, y) * 0.05 in every cell
    s = face_samples(m)
    uv = uv_at(m, s.face, s.bary)
    assert uv.shape == (len(s), 2) and uv.dtype == np.float64
    assert np.allclose(uv, s.points[:, :2] * 0.05, atol=1e-9)


def test_uv_at_is_nan_for_a_face_without_texture_coordinates():
    m = cube()
    m.face_vt[0] = -1                                      # the OBJ reader's mark for "no vt"
    uv = uv_at(m, np.array([0, 1]), np.full((2, 3), 1.0 / 3.0))
    assert np.isnan(uv[0]).all(), "not the last UV, which a bare index of -1 would silently read"
    assert np.isfinite(uv[1]).all()
    bare = dataclasses.replace(m, uvs=np.zeros((0, 2)), face_vt=np.full_like(m.face_vt, -1))
    assert np.isnan(uv_at(bare, np.array([3]), np.full((1, 3), 1.0 / 3.0))).all()


def test_recentred_puts_the_bbox_centre_at_the_origin_and_touches_nothing_else():
    m = cube(10.0)
    far = dataclasses.replace(m, positions=m.positions + [24000.0, -3000.0, 5.0])
    before = far.positions.copy()
    centred, centre = recentred(far)
    assert np.allclose(centre, [24005.0, -2995.0, 10.0])
    lo, hi = centred.bbox()
    assert np.allclose(lo, -hi)
    assert np.allclose(centred.positions + centre, far.positions)
    assert centred.face_v is far.face_v and centred.uvs is far.uvs
    assert np.array_equal(far.positions, before), "the input mesh is not changed"

    # a second mesh is put in the SAME frame by handing it the first one's centre
    other, again = recentred(far, centre)
    assert np.array_equal(again, centre) and np.array_equal(other.positions, centred.positions)


def test_the_bbox_centre_ignores_vertices_no_face_uses():
    m = cube(10.0)
    stray = dataclasses.replace(m, positions=np.vstack([m.positions, [[9000.0, 9000.0, 9000.0]]]))
    assert np.allclose(bbox_centre(stray), [5.0, 5.0, 5.0])
