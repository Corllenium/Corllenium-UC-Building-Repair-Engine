"""Job P0-14: the Validator's core -- face samples, viewpoints (outside, and at eye height inside)
and what each viewpoint sees.

`engine/validate/` judges the repair engine, so it is written from scratch: nothing in it may be
built on `engine/guard/` (see `test_the_validator_imports_nothing_it_judges`).
"""
import ast
import dataclasses
from pathlib import Path

import numpy as np
import pytest

import engine.validate
from engine.tests.fixtures.build import closed_room, cube, grid_slab, sloped_slab
from engine.validate.sampling import (MAX_FRAME_COORD, bbox_centre, check_frame, face_areas,
                                      face_normals, face_samples, recentred, used_bbox, uv_at)
from engine.validate.viewpoints import interior_probes, outside_directions, pedestrian_ring
from engine.validate.visibility import build_caster


def _merged(*meshes):
    """The meshes as ONE: vertex blocks stacked, face indices offset, the first one's materials."""
    v_off = np.cumsum([0] + [len(m.positions) for m in meshes[:-1]])
    t_off = np.cumsum([0] + [len(m.uvs) for m in meshes[:-1]])
    n_faces = sum(m.n_faces for m in meshes)
    return dataclasses.replace(
        meshes[0],
        positions=np.vstack([m.positions for m in meshes]),
        uvs=np.vstack([m.uvs for m in meshes]),
        face_v=np.vstack([m.face_v + o for m, o in zip(meshes, v_off)]),
        face_vt=np.vstack([m.face_vt + o for m, o in zip(meshes, t_off)]),
        face_vn=np.vstack([m.face_vn for m in meshes]),
        face_material=np.concatenate([m.face_material for m in meshes]),
        face_line=np.arange(1, n_faces + 1, dtype=np.int64))


def _flipped(mesh, faces=None):
    """A copy of `mesh` with the winding of `faces` (all by default) reversed, UV corners with it."""
    which = np.arange(mesh.n_faces) if faces is None else np.asarray(faces)
    fv, fvt = mesh.face_v.copy(), mesh.face_vt.copy()
    fv[which] = fv[which][:, [0, 2, 1]]
    fvt[which] = fvt[which][:, [0, 2, 1]]
    return dataclasses.replace(mesh, face_v=fv, face_vt=fvt)


def _lifted(mesh, dz):
    return dataclasses.replace(mesh, positions=mesh.positions + [0.0, 0.0, dz])


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


def test_used_bbox_is_the_box_of_the_vertices_some_face_uses():
    m = cube(10.0)
    lo, hi = used_bbox(m)
    assert np.array_equal(lo, [0.0, 0.0, 0.0]) and np.array_equal(hi, [10.0, 10.0, 10.0])
    stray = dataclasses.replace(m, positions=np.vstack([m.positions, [[9000.0, 9000.0, 9000.0]]]))
    assert np.array_equal(used_bbox(stray)[1], [10.0, 10.0, 10.0])


# ---------------------------------------------------------------------------------------------
# Item 2: viewpoints -- outside directions, a pedestrian ring, probes at eye height inside
# ---------------------------------------------------------------------------------------------

def test_outside_directions_are_unit_fibonacci_vectors_spread_over_the_sphere():
    d = outside_directions()
    assert d.shape == (128, 3) and d.dtype == np.float64
    assert np.allclose(np.linalg.norm(d, axis=1), 1.0, atol=1e-12)
    assert np.array_equal(d, outside_directions()), "the same every call"
    assert outside_directions(32).shape == (32, 3)

    # a Fibonacci lattice: equal-height bands, so the heights are 1 - (2 i + 1) / n
    assert np.allclose(d[:, 2], 1.0 - (2.0 * np.arange(128) + 1.0) / 128.0, atol=1e-12)
    # evenly spread: no two within 12 degrees (measured 15.7), and no part of the sphere further
    # than 16 degrees from one of them (measured 13.2); balanced: no hemisphere is favoured
    gram = d @ d.T
    np.fill_diagonal(gram, -1.0)
    assert gram.max() < np.cos(np.radians(12.0))
    fine = outside_directions(4000)
    assert (fine @ d.T).max(axis=1).min() > np.cos(np.radians(16.0))
    assert np.linalg.norm(d.mean(axis=0)) < 0.01


def test_pedestrian_ring_stands_n_cameras_at_eye_height_a_margin_outside_the_bbox():
    lo, hi = np.array([-8.0, -8.0, -8.0]), np.array([208.0, 168.0, 128.0])

    def gap(points):                       # how far each point is from the box, in plan, Chebyshev
        return np.maximum(np.maximum(lo[:2] - points[:, :2], points[:, :2] - hi[:2]), 0.0).max(axis=1)

    ring = pedestrian_ring((lo, hi), eye_z=63.0)
    assert ring.shape == (24, 3) and ring.dtype == np.float64
    assert (ring[:, 2] == 63.0).all()
    assert np.allclose(gap(ring), 240.0), "each exactly 240 in outside the box: none inside the building"
    assert len(np.unique(ring.round(9), axis=0)) == 24
    assert ring[:, 0].min() < lo[0] and ring[:, 0].max() > hi[0]
    assert ring[:, 1].min() < lo[1] and ring[:, 1].max() > hi[1], "all four sides are covered"
    assert np.array_equal(ring, pedestrian_ring((lo, hi), 63.0)), "the same every call"

    # evenly spaced round the perimeter of the grown box (696 x 656 in): 2704 / 24 apart
    bottom = ring[np.isclose(ring[:, 1], lo[1] - 240.0)]
    assert len(bottom) == 6 and np.allclose(np.diff(bottom[:, 0]), 2.0 * (696.0 + 656.0) / 24.0)

    assert pedestrian_ring((lo, hi), 63.0, n=7).shape == (7, 3)
    assert pedestrian_ring((lo, hi), 63.0, n=0).shape == (0, 3)
    assert np.allclose(gap(pedestrian_ring((lo, hi), 63.0, margin=500.0)), 500.0)
    assert np.array_equal(pedestrian_ring(np.array([lo, hi]), 63.0), ring), "a (2, 3) array works too"


ROOM = (200.0, 160.0, 120.0)           # the default inner size of `closed_room`


def _inside_the_room(points, size=ROOM):
    return ((points > 0.0) & (points < np.asarray(size))).all(axis=1)


def test_the_closed_room_fixture_is_wound_as_documented():
    m = closed_room()
    assert m.n_faces == 24 and m.materials == ["plaster", "brick"]
    assert (m.face_material[:12] == 0).all() and (m.face_material[12:] == 1).all()
    n = face_normals(m)
    into_the_room = [[0, 0, 1], [0, 0, -1], [0, 1, 0], [-1, 0, 0], [0, -1, 0], [1, 0, 0]]
    outward = [[0, 0, -1], [0, 0, 1], [0, -1, 0], [1, 0, 0], [0, 1, 0], [-1, 0, 0]]
    assert np.allclose(n[:12], np.repeat(into_the_room, 2, axis=0)), "floor, ceiling, y0, x1, y1, x0"
    assert np.allclose(n[12:], np.repeat(outward, 2, axis=0)), "bottom, top, y0, x1, y1, x0"
    lo, hi = m.bbox()
    assert np.allclose(lo, [-8.0, -8.0, -8.0]) and np.allclose(hi, [208.0, 168.0, 128.0])


def test_the_closed_room_has_probes_at_eye_height_standing_on_its_floor():
    probes = interior_probes(closed_room())
    assert probes.shape[1] == 3 and probes.dtype == np.float64
    inside = _inside_the_room(probes)
    # the lattice starts half a cell from the outer skin's corner (-8, -8): x = 11.7, 51.1, ... 169.2
    # (5 columns) and y = 11.7 ... 129.8 (4 rows) fall on the 200 x 160 floor
    assert inside.sum() == 20
    assert (probes[inside, 2] == 63.0).all(), "1.6 m above the floor at z = 0"
    xs = np.unique(probes[inside, 0].round(6))
    assert len(xs) == 5 and np.allclose(np.diff(xs), 39.37)
    assert np.isclose(xs[0], -8.0 + 39.37 / 2.0), "anchored half a cell in from the box corner"
    # the roof is upward, open ground too: its probes stand 63 in above it, outside the room.
    # Nothing is in the void between the skins and nothing under the floor.
    roof = probes[~inside]
    assert len(roof) == 20 and np.allclose(roof[:, 2], 128.0 + 63.0)


def test_a_probe_needs_headroom_counted_from_half_an_inch_above_the_floor():
    m = closed_room()                       # the ceiling is 119.5 in above the headroom ray's start
    assert _inside_the_room(interior_probes(m, headroom=119.4)).sum() == 20
    assert _inside_the_room(interior_probes(m, headroom=119.6)).sum() == 0

    low = closed_room(height=70.0)          # a crawl space: the 83 in of headroom is not there
    probes = interior_probes(low)
    assert _inside_the_room(probes, (200.0, 160.0, 70.0)).sum() == 0
    assert len(probes) == 20 and np.allclose(probes[:, 2], 70.0 + 8.0 + 63.0), "only the roof's"


def test_probe_eye_height_and_grid_follow_their_parameters():
    probes = interior_probes(closed_room(), eye=40.0, grid=80.0)
    inside = _inside_the_room(probes)
    assert (probes[inside, 2] == 40.0).all()
    assert inside.sum() == 6                # x = 32, 112, 192; y = 32, 112


def test_a_plate_overhead_takes_the_probes_beneath_it():
    floor = grid_slab(10, 10)                                           # 100 x 100 in, z = 0, faces +z
    plate = _lifted(_flipped(grid_slab(5, 10)), 60.0)                   # x 0..50 at z = 60, faces -z
    assert len(interior_probes(floor)) == 9
    both = interior_probes(_merged(floor, plate))
    assert len(both) == 6 and (both[:, 0] > 50.0).all() and np.allclose(both[:, 2], 63.0)


def test_only_upward_faces_get_probes_and_they_follow_the_surface():
    steep = sloped_slab(length=80.0, rise=80.0)           # 45 degrees: n_z = 0.71, not walkable
    assert interior_probes(steep).shape == (0, 3)
    gentle = sloped_slab(length=80.0, rise=20.0)          # 14 degrees: n_z = 0.97
    probes = interior_probes(gentle)
    assert len(probes) == 2
    assert np.allclose(probes[:, 2], 20.0 * probes[:, 0] / 80.0 + 63.0, atol=1e-6)


def test_a_face_smaller_than_the_grid_still_gets_a_probe():
    probes = interior_probes(cube(10.0))                  # the 10 in top holds no lattice point
    assert probes.shape == (1, 3), "its two triangles share a cell: one probe, not two"
    assert 0.0 < probes[0, 0] < 10.0 and 0.0 < probes[0, 1] < 10.0
    assert np.isclose(probes[0, 2], 10.0 + 63.0)


def test_a_finely_tessellated_floor_gets_one_probe_per_grid_cell_not_one_per_face():
    probes = interior_probes(grid_slab(10, 10))           # 200 triangles of 10 in; cells of 39.37 in
    assert len(probes) == 9
    assert np.allclose(sorted(set(probes[:, 0].round(6))), [19.685, 59.055, 98.425])


def test_interior_probes_repeat_exactly():
    m = closed_room()
    assert np.array_equal(interior_probes(m), interior_probes(m))


def test_a_mesh_that_was_not_recentred_is_refused_before_embree_rounds_it_to_float32():
    near = cube(10.0)
    far = dataclasses.replace(near, positions=near.positions + [0.0, 24000.0, 0.0])
    with pytest.raises(ValueError, match="recentre"):
        build_caster(far)
    with pytest.raises(ValueError, match="recentre"):
        interior_probes(far)
    centred, _ = recentred(far)
    assert len(build_caster(centred).faces) == 12
    check_frame(np.array([[MAX_FRAME_COORD, -MAX_FRAME_COORD, 0.0]]), "a point")
    with pytest.raises(ValueError, match="recentre"):
        check_frame(np.array([[0.0, 0.0, MAX_FRAME_COORD + 1.0]]), "a point")


def test_the_validator_imports_nothing_it_judges():
    """`engine/validate/` judges the guard and the fixes, so it is not built on them: the guard's
    `compare_views` (or anything else in `engine/guard/`), the fixes, and `engine/vis/`, which the
    hidden-face fix reuses."""
    banned = ("engine.guard", "engine.fixes", "engine.vis")
    package = Path(engine.validate.__file__).parent
    sources = sorted(package.glob("*.py"))
    assert {p.name for p in sources} >= {"__init__.py", "sampling.py", "viewpoints.py", "visibility.py"}
    for path in sources:
        for node in ast.walk(ast.parse(path.read_text(encoding="utf-8"))):
            if isinstance(node, ast.Import):
                names = [a.name for a in node.names]
            elif isinstance(node, ast.ImportFrom):
                assert node.level < 2, f"{path.name}: a relative import out of the package"
                names = [node.module or ""]
            else:
                continue
            for name in names:
                assert not any(name == b or name.startswith(b + ".") for b in banned), \
                    f"{path.name} imports {name}"
