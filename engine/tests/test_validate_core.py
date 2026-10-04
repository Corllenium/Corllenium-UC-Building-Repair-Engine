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
from engine.rays.caster import BruteCaster
from engine.tests.fixtures.build import closed_room, cube, grid_slab, sloped_slab, two_sided_wall
from engine.validate.sampling import (MAX_FRAME_COORD, bbox_centre, check_frame, face_areas,
                                      face_normals, face_samples, recentred, used_bbox, uv_at)
from engine.validate.viewpoints import (INSIDE_VOTES, _back_votes, interior_probes, outside_directions,
                                        pedestrian_ring)
from engine.validate.visibility import MIN_COS, build_caster, visible_samples


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


# ---------------------------------------------------------------------------------------------
# Item 3: what each viewpoint sees -- escape toward -dir for a direction, a clear segment for a
# camera or a probe, and whether the viewer is on the FRONT or the BACK of the face
# ---------------------------------------------------------------------------------------------

def _no_points():
    return np.zeros((0, 3))


def _outside_views(mesh):
    """128 directions and the ring of 24 cameras at the box's mid-height."""
    lo, hi = mesh.bbox()
    return outside_directions(128), pedestrian_ring((lo, hi), eye_z=(lo[2] + hi[2]) / 2.0)


def _cos_to(points, normals, viewpoints):
    """cos of the angle between each face normal and the line from each sample to each viewpoint."""
    v = viewpoints[None, :, :] - points[:, None, :]
    return np.einsum("nk,nck->nc", normals, v) / np.linalg.norm(v, axis=2)


def test_on_a_convex_solid_a_sample_is_seen_exactly_by_the_viewpoints_its_face_looks_at():
    m = cube(10.0)
    s = face_samples(m)
    dirs, cams = _outside_views(m)
    vs = visible_samples(m, s, dirs, cams, _no_points(), build_caster(m))
    assert vs.seen.shape == vs.front.shape == (len(s), 128 + 24)
    assert vs.seen.dtype == vs.front.dtype == np.bool_

    n = face_normals(m)[s.face]
    # nothing in the way of a convex solid, so a viewpoint sees a sample iff it is on the face's front side
    assert np.array_equal(vs.seen[:, vs.dir_cols], (n @ (-dirs).T) > MIN_COS)
    assert np.array_equal(vs.seen[:, vs.cam_cols], _cos_to(s.points, n, cams) > MIN_COS)
    assert np.array_equal(vs.front, vs.seen), "and what it sees is a front, never a back"

    assert vs.visible.all(), "every outside face is visible from some direction"
    assert vs.front_seen.all() and not vs.back_seen.any(), "the inside of a closed box is seen by nobody"
    side = s.face >= 4                                        # faces 4-11, the four sides
    assert vs.seen[side][:, vs.cam_cols].any(axis=1).all()
    assert not vs.seen[~side][:, vs.cam_cols].any(), "the ring at mid-height never sees the top or bottom"


def test_an_opening_lets_the_outside_see_the_inside():
    m = cube(10.0)
    keep = np.ones(m.n_faces, bool)
    keep[[8, 9]] = False                                      # the x = 10 face
    open_box = dataclasses.replace(
        m, face_v=m.face_v[keep], face_vt=m.face_vt[keep], face_vn=m.face_vn[keep],
        face_material=m.face_material[keep], face_line=m.face_line[keep])
    s = face_samples(open_box)
    dirs, cams = _outside_views(open_box)
    vs = visible_samples(open_box, s, dirs, cams, _no_points(), build_caster(open_box))
    far_wall = np.isin(s.face, [8, 9])                        # the x = 0 wall, now faces 8-9
    assert vs.back_seen[far_wall].any(), "its inside, through the opening"
    assert vs.seen[far_wall][:, vs.dir_cols].any() and vs.seen[far_wall][:, vs.cam_cols].any()
    assert vs.front_seen.all(), "the outsides are still seen from the front"


def test_a_closed_room_is_seen_inside_by_the_probes_standing_in_it_and_never_from_outside():
    m = closed_room()
    s = face_samples(m, area_per_sample=500.0)
    probes = interior_probes(m)
    inside = _inside_the_room(probes)
    dirs, cams = _outside_views(m)
    vs = visible_samples(m, s, dirs, cams, probes, build_caster(m))
    assert vs.seen.shape == (len(s), 128 + 24 + len(probes))

    all_cols = np.arange(vs.seen.shape[1])
    room = all_cols[vs.probe_cols][inside]                    # the probes standing in the room
    elsewhere = np.setdiff1d(all_cols, room)                  # directions, cameras, roof probes
    inner = s.face < 12
    wall = np.isin(s.face, np.arange(4, 12))                  # the four inner walls

    assert vs.seen[np.ix_(wall, room)].all(), "all 4 inner walls, from every probe in the room"
    assert vs.front[np.ix_(wall, room)].all(), "from the front: they face the room"
    assert vs.seen[np.ix_(inner, room)].any(axis=1).all(), "the floor and the ceiling too"
    assert not vs.seen[np.ix_(inner, elsewhere)].any(), "no direction, camera or roof probe reaches in"
    assert vs.seen_inside[inner].all() and not vs.seen_outside[inner].any()

    outer = ~inner                                            # the mirror image: the building's outside
    assert not vs.seen[np.ix_(outer, room)].any(), "the probes in the room cannot see out"
    assert vs.seen_outside[outer].all()


def test_a_wall_whose_front_points_away_from_every_viewpoint_is_back_seen():
    room = _flipped(closed_room(), [6, 7])                    # the wall x = 200 now faces out, into the void
    s = face_samples(room, area_per_sample=500.0)
    probes = interior_probes(room)
    dirs, cams = _outside_views(room)
    vs = visible_samples(room, s, dirs, cams, probes, build_caster(room))
    wall = np.isin(s.face, [6, 7])
    assert vs.visible[wall].all(), "the probes in the room still see it"
    assert vs.back_seen[wall].all() and not vs.front_seen[wall].any()
    assert vs.front_seen[~wall].all() and not vs.back_seen[~wall].any(), "every other face still faces its viewers"

    box = _flipped(cube(10.0), [8, 9])                        # the x = 10 face turned to look into the cube
    s = face_samples(box)
    dirs, cams = _outside_views(box)
    vs = visible_samples(box, s, dirs, cams, _no_points(), build_caster(box))
    face = np.isin(s.face, [8, 9])
    assert vs.back_seen[face].all() and not vs.front_seen[face].any()
    from_the_x_side = np.tile(-dirs[:, 0] > MIN_COS, (int(face.sum()), 1))
    assert np.array_equal(vs.seen[face][:, vs.dir_cols], from_the_x_side), "seen from the half-space behind it"
    assert not vs.front[face].any()


def test_both_layers_of_a_two_sided_wall_are_seen_from_both_sides():
    m = two_sided_wall()               # faces 0-1 face -y, faces 2-3 face +y: one place, two layers
    s = face_samples(m)
    dirs = outside_directions(128)
    vs = visible_samples(m, s, dirs, _no_points(), _no_points(), build_caster(m))
    u_y = -dirs[:, 1]                  # toward the viewer
    both_layers = np.tile(np.abs(u_y) > MIN_COS, (len(s), 1))
    assert np.array_equal(vs.seen, both_layers), "Unity draws both sides: all four faces, from every side"
    layer_a = (s.face < 2)[:, None]
    front = np.where(layer_a, u_y[None, :] < 0.0, u_y[None, :] > 0.0)
    assert np.array_equal(vs.front, both_layers & front), "each layer's front is on its own side"
    assert vs.front_seen.all() and vs.back_seen.all()


def test_a_camera_or_probe_sees_a_sample_only_along_a_clear_segment():
    floor = grid_slab(4, 4)                                   # 40 x 40 in at z = 0, faces +z: faces 0-31
    ceiling = _lifted(grid_slab(4, 4), 10.0)                  # the same, 10 in above it: faces 32-63
    m = _merged(floor, ceiling)
    s = face_samples(m, area_per_sample=500.0)
    spots = np.array([[20.0, 20.0, 5.0],                      # between the two
                      [20.0, 20.0, 30.0],                     # above both
                      [20.0, 20.0, -5.0],                     # below both
                      [100.0, 20.0, 0.0]])                    # level with the floor, beside it
    caster = build_caster(m)
    as_cams = visible_samples(m, s, _no_points(), spots, _no_points(), caster)
    as_probes = visible_samples(m, s, _no_points(), _no_points(), spots, caster)
    assert np.array_equal(as_cams.seen, as_probes.seen) and np.array_equal(as_cams.front, as_probes.front)

    low, high = s.face < 32, s.face >= 32

    def rows(mask, row):
        return np.tile(row, (int(mask.sum()), 1))

    # the floor: its front from between the plates, its back from below; not from above (the
    # ceiling is in the way) and not from level with it (edge-on). The ceiling that lies BEYOND the
    # camera between the plates does not hide it.
    assert np.array_equal(as_cams.seen[low], rows(low, [True, False, True, False]))
    assert np.array_equal(as_cams.front[low], rows(low, [True, False, False, False]))
    # the ceiling: its back from between and from beside, its front from above; not from below
    assert np.array_equal(as_cams.seen[high], rows(high, [True, True, False, True]))
    assert np.array_equal(as_cams.front[high], rows(high, [False, True, False, False]))


def test_the_embree_visibility_agrees_with_a_float64_brute_force_oracle():
    ground = grid_slab(4, 4)                                  # 40 x 40 in
    block = dataclasses.replace(cube(10.0), positions=cube(10.0).positions + [15.0, 15.0, 0.0])   # on it
    m = _merged(ground, block)
    s = face_samples(m)
    dirs, cams = _outside_views(m)
    probes = interior_probes(m)
    assert len(probes) > 0

    e = visible_samples(m, s, dirs, cams, probes, build_caster(m))
    b = visible_samples(m, s, dirs, cams, probes, BruteCaster(m.positions, m.face_v))
    assert (e.seen == b.seen).mean() >= 0.999
    assert (e.front == b.front).mean() >= 0.999
    facing = (face_normals(m)[s.face] @ (-dirs).T) > MIN_COS
    assert (facing & ~b.seen[:, b.dir_cols]).any(), "the block really does throw shadows"
    assert b.seen[:, b.dir_cols].any()


def test_visibility_repeats_exactly():
    m = closed_room()
    s = face_samples(m, area_per_sample=500.0)
    probes = interior_probes(m)
    dirs, cams = _outside_views(m)
    caster = build_caster(m)
    first = visible_samples(m, s, dirs, cams, probes, caster)
    again = visible_samples(m, s, dirs, cams, probes, caster)
    assert np.array_equal(first.seen, again.seen) and np.array_equal(first.front, again.front)


def test_a_face_with_no_area_is_never_visible():
    m = grid_slab(1, 1, cell=10.0)
    m.face_v[1] = [0, 0, 3]
    s = face_samples(m)
    vs = visible_samples(m, s, outside_directions(64), _no_points(), _no_points(), build_caster(m))
    assert vs.visible[s.face == 0].all() and not vs.visible[s.face == 1].any()


def test_no_samples_give_empty_matrices_and_no_viewpoints_give_no_columns():
    m = cube(10.0)
    ring = pedestrian_ring(m.bbox(), 5.0, n=3)
    empty = visible_samples(m, face_samples(m, faces=[]), outside_directions(8), ring, _no_points(),
                            build_caster(m))
    assert empty.seen.shape == empty.front.shape == (0, 11) and len(empty.visible) == 0
    bare = visible_samples(m, face_samples(m), _no_points(), _no_points(), _no_points(), build_caster(m))
    assert bare.seen.shape == (m.n_faces * 4, 0) and not bare.visible.any()


def test_visible_samples_refuses_a_caster_of_another_mesh_and_points_outside_the_frame():
    m = cube(10.0)
    s = face_samples(m)
    dirs = outside_directions(8)
    with pytest.raises(ValueError, match="caster"):
        visible_samples(m, s, dirs, _no_points(), _no_points(), build_caster(closed_room()))
    far = dataclasses.replace(s, points=s.points + 24000.0)
    with pytest.raises(ValueError, match="recentre"):
        visible_samples(m, far, dirs, _no_points(), _no_points(), build_caster(m))
    with pytest.raises(ValueError, match="recentre"):
        visible_samples(m, s, dirs, np.array([[0.0, 24000.0, 0.0]]), _no_points(), build_caster(m))
    with pytest.raises(ValueError, match="direction"):
        visible_samples(m, s, np.zeros((1, 3)), _no_points(), _no_points(), build_caster(m))


def test_the_whole_flow_works_on_a_model_far_from_the_origin_once_it_is_recentred():
    near = closed_room()
    far = dataclasses.replace(near, positions=near.positions + [24000.0, 24000.0, 0.0])
    centred, _ = recentred(far)
    runs = []
    for m in (near, centred):
        s = face_samples(m, area_per_sample=500.0)
        dirs, cams = _outside_views(m)
        runs.append(visible_samples(m, s, dirs, cams, interior_probes(m), build_caster(m)))
    a, b = runs
    assert a.seen.shape == b.seen.shape
    assert (a.seen == b.seen).mean() >= 0.999 and (a.front == b.front).mean() >= 0.999


def test_a_grazing_view_across_a_tessellated_floor_is_not_blocked_by_its_own_neighbours():
    m = grid_slab(10, 10)                                     # 200 coplanar triangles, faces +z
    s = face_samples(m)
    caster = build_caster(m)
    for elevation in (5.0, 1.0, 0.1):                         # degrees above the floor, looking down across it
        el, az = np.radians(elevation), np.radians(np.arange(16) * 22.5 + 3.0)
        look = np.stack([np.cos(az) * np.cos(el), np.sin(az) * np.cos(el), -np.sin(el) * np.ones(16)], axis=1)
        vs = visible_samples(m, s, look, _no_points(), _no_points(), caster)
        assert vs.seen.all() and vs.front.all(), f"at {elevation} degrees"


def test_interior_probes_refuses_a_caster_of_another_mesh_and_reusing_one_changes_nothing():
    room = closed_room()
    with pytest.raises(ValueError, match="caster"):
        interior_probes(room, caster=build_caster(cube(10.0)))
    assert np.array_equal(interior_probes(room, caster=build_caster(room)), interior_probes(room))


def test_nonsense_arguments_are_refused_not_guessed_at():
    m = cube(10.0)
    with pytest.raises(ValueError, match="area_per_sample"):
        face_samples(m, area_per_sample=0.0)
    with pytest.raises(ValueError, match="one entry per face"):
        face_samples(m, faces=np.ones(3, dtype=bool))
    with pytest.raises(ValueError, match="grid"):
        interior_probes(m, grid=0.0)
    with pytest.raises(ValueError, match="cams"):
        visible_samples(m, face_samples(m), outside_directions(4), np.zeros((2, 2)), _no_points(),
                        build_caster(m))


# ---------------------------------------------------------------------------------------------
# Fix round 0: no probe stands inside a solid. The headroom ray cannot tell open air from the
# inside of a wall taller than the headroom (it runs up inside the wall to its top), so each
# candidate probe also casts VOTES rays from eye height and is dropped when MORE THAN HALF of them
# first meet a face from BEHIND -- the signature of standing inside something closed.
# ---------------------------------------------------------------------------------------------

VOTES = 26                                  # the rays each candidate probe casts; the majority is > 13


def test_the_vote_casts_26_rays_and_needs_more_than_13_backs():
    assert INSIDE_VOTES == VOTES == 26


def _wall(x0, x1, y0, y1, z0, z1, bottom=True):
    """A closed box, wound outward: `cube(1)` stretched to these extents (faces 0-1 are its bottom,
    which `bottom=False` leaves off, like the skirts of a real slab)."""
    unit = cube(1.0)
    box = dataclasses.replace(unit, positions=unit.positions * [x1 - x0, y1 - y0, z1 - z0] + [x0, y0, z0])
    if bottom:
        return box
    keep = np.arange(box.n_faces) >= 2
    return dataclasses.replace(box, face_v=box.face_v[keep], face_vt=box.face_vt[keep],
                               face_vn=box.face_vn[keep], face_material=box.face_material[keep],
                               face_line=box.face_line[keep])


def _back_rays(mesh, points):
    """For each point, how many of the VOTES directions first meet a face from BEHIND. Worked out
    with the float64 brute-force caster, so the test does not lean on the code under test."""
    caster = BruteCaster(mesh.positions, mesh.face_v)
    normals = face_normals(mesh)
    dirs = outside_directions(VOTES)
    counts = []
    for p in np.atleast_2d(points):
        tri, _ = caster.first_hit(np.tile(p, (VOTES, 1)), dirs)
        hit = tri >= 0
        counts.append(int((hit & (np.einsum("ij,ij->i", normals[np.maximum(tri, 0)], dirs) > 0.0)).sum()))
    return np.array(counts)


def _in_the_box(points, lo, hi):
    return ((points > np.asarray(lo)) & (points < np.asarray(hi))).all(axis=1)


def test_no_probe_stands_inside_a_wall_taller_than_the_headroom():
    floor = grid_slab(10, 10)                                           # 100 x 100 in at z = 0, faces +z
    m = _merged(floor, _wall(40.0, 60.0, 0.0, 100.0, 0.0, 120.0))        # a closed box standing on it, 120 in tall
    # the premise: from half an inch above the floor under the wall, the headroom ray runs up INSIDE
    # the wall to its top, 119.5 in away, which clears 83 in -- the headroom rule alone lets it through
    _, t = build_caster(m).first_hit(np.array([[59.055, 59.055, 0.5]]), np.array([[0.0, 0.0, 1.0]]))
    assert t[0] > 83.0

    probes = interior_probes(m)
    in_the_wall = _in_the_box(probes, (40.0, 0.0, 0.0), (60.0, 100.0, 120.0))
    assert not in_the_wall.any(), f"{int(in_the_wall.sum())} probes inside the wall: {probes[in_the_wall]}"

    # the open floor beside the wall keeps every probe it had without the wall, and the strip of
    # floor in the wall's own grid cell still gets one
    bare = interior_probes(floor)
    beside = bare[(bare[:, 0] < 40.0) | (bare[:, 0] > 60.0)]
    assert len(beside) == 6
    for p in beside:
        assert np.isclose(probes, p).all(axis=1).any(), f"lost the open-floor probe at {p}"
    on_the_floor = probes[np.isclose(probes[:, 2], 63.0)]
    assert ((on_the_floor[:, 0] < 40.0) | (on_the_floor[:, 0] > 60.0)).all()
    assert len(on_the_floor) == 9, "3 rows x (the strip west of the wall, the strip beside it, the strip east)"
    # the top of the wall is open air and keeps its probes, 63 in above it
    top = probes[probes[:, 2] > 120.0]
    assert len(top) == 3 and np.allclose(top[:, 2], 183.0)


def test_no_probe_stands_inside_a_wall_whose_bottom_is_missing():
    # the skirts of a real slab have no bottom: the rays DOWN from inside escape through it onto the floor
    # and count as air, so only the sides and the top vote, and they are still the majority
    floor = grid_slab(10, 10)
    m = _merged(floor, _wall(40.0, 60.0, 0.0, 100.0, 0.0, 120.0, bottom=False))
    _, t = build_caster(m).first_hit(np.array([[59.055, 59.055, 0.5]]), np.array([[0.0, 0.0, 1.0]]))
    assert t[0] > 83.0
    inside = np.array([[59.055, 59.055, 63.0], [59.055, 19.685, 63.0], [59.055, 98.425, 63.0]])
    assert (_back_rays(m, inside) > VOTES // 2).all(), "the premise: a probe in there sees mostly backs"
    probes = interior_probes(m)
    assert not _in_the_box(probes, (40.0, 0.0, 0.0), (60.0, 100.0, 120.0)).any()
    assert len(probes[np.isclose(probes[:, 2], 63.0)]) == 9


def test_the_vote_keeps_every_probe_in_a_closed_room_and_they_still_see_all_four_walls():
    m = closed_room()
    probes = interior_probes(m)
    inside = _inside_the_room(probes)
    assert inside.sum() == 20 and len(probes) == 40, "the room's 20 and the roof's 20, none dropped"
    assert (_back_rays(m, probes) <= VOTES // 2).all(), "no probe is anywhere near a majority of backs"
    s = face_samples(m, area_per_sample=500.0)
    vs = visible_samples(m, s, _no_points(), _no_points(), probes[inside], build_caster(m))
    assert vs.seen.shape[1] == 20
    walls = np.isin(s.face, np.arange(4, 12))
    assert vs.seen[walls].all() and vs.front[walls].all(), "all 4 inner walls, from the front, from every probe"


def test_a_room_with_a_reversed_ceiling_keeps_its_probes():
    room = _flipped(closed_room(), [2, 3])                    # the inner ceiling now faces UP, away from the room
    assert np.allclose(face_normals(room)[2:4], [[0.0, 0.0, 1.0]] * 2)
    probes = interior_probes(room)
    inside = _inside_the_room(probes)
    assert inside.sum() == 20 and len(probes) == 40
    # only the rays that reach the ceiling meet a back, and they are never more than the 13 that point
    # up, so they can never be a majority: the vote cannot mistake a room for a solid over one reversed plane
    back = _back_rays(room, probes[inside])
    assert back.min() >= 1, "the reversed ceiling really does give backs"
    assert back.max() <= VOTES // 2


def test_the_probes_of_a_floor_with_a_wall_repeat_exactly():
    m = _merged(grid_slab(10, 10), _wall(40.0, 60.0, 0.0, 100.0, 0.0, 120.0))
    assert np.array_equal(interior_probes(m), interior_probes(m))
    room = closed_room()
    assert np.array_equal(interior_probes(room), interior_probes(room))


def test_the_votes_equal_an_independent_brute_force_count_and_repeat_exactly():
    wall = _merged(grid_slab(10, 10), _wall(40.0, 60.0, 0.0, 100.0, 0.0, 120.0))
    open_bottom = _merged(grid_slab(10, 10), _wall(40.0, 60.0, 0.0, 100.0, 0.0, 120.0, bottom=False))
    reversed_ceiling = _flipped(closed_room(), [2, 3])
    inside_wall = np.array([[59.055, 59.055, 63.0], [59.055, 19.685, 63.0]])
    beside_wall = np.array([[19.685, 59.055, 63.0], [98.425, 98.425, 63.0]])
    above_wall = np.array([[59.055, 59.055, 183.0]])
    scenes = {
        "wall": (wall, np.vstack([inside_wall, beside_wall, above_wall])),
        "open-bottom wall": (open_bottom, np.vstack([inside_wall, beside_wall])),
        "reversed ceiling": (reversed_ceiling, interior_probes(reversed_ceiling)),
        "closed room": (closed_room(), interior_probes(closed_room())),
    }
    for name, (mesh, points) in scenes.items():
        caster, normals = build_caster(mesh), face_normals(mesh)
        votes = _back_votes(caster, normals, points)
        assert np.array_equal(votes, _back_rays(mesh, points)), name
        assert np.array_equal(votes, _back_votes(caster, normals, points)), f"{name}: not repeatable"
    caster, normals = build_caster(wall), face_normals(wall)
    assert (_back_votes(caster, normals, inside_wall) == VOTES).all(), "inside the wall: every ray a back"
    assert (_back_votes(caster, normals, beside_wall) == 0).all(), "in the open beside it: none"
    assert (_back_votes(caster, normals, above_wall) == 0).all(), "above it: none"


def test_a_probe_low_in_a_wall_is_a_majority_of_backs_whichever_way_a_coincident_pair_ties():
    # 10 in above the floor, inside the wall: the rays down meet the floor's top (a front) and the wall's
    # bottom (a back) at ONE depth, and Embree and the brute-force caster break that tie differently
    # (23 and 21 backs here). At most 13 rays point down, so the 13 up and the sides settle it either way.
    m = _merged(grid_slab(10, 10), _wall(40.0, 60.0, 0.0, 100.0, 0.0, 120.0))
    low = np.array([[50.0, 50.0, 10.0]])
    embree = _back_votes(build_caster(m), face_normals(m), low)[0]
    brute = _back_rays(m, low)[0]
    assert embree > VOTES // 2 and brute > VOTES // 2
    assert abs(int(embree) - int(brute)) <= 13, "they can differ only by the rays that go down"


def test_exactly_half_of_the_rays_meeting_backs_is_not_a_majority():
    # A 1 in tile facing up (no one of the 26 rays can hit it) over a huge plate facing DOWN, 0.5 in
    # below: the 13 rays that point down all meet the plate's back, the 13 that point up escape. 13 is
    # exactly half, which is not more than half: the probe stays.
    tile = grid_slab(1, 1, cell=1.0)
    big = grid_slab(1, 1, cell=6000.0)
    below = _flipped(dataclasses.replace(big, positions=big.positions + [-3000.0, -3000.0, -0.5]))
    m = _merged(tile, below)
    probes = interior_probes(m)
    assert probes.shape == (1, 3) and np.isclose(probes[0, 2], 63.0)
    assert _back_rays(m, probes)[0] == VOTES // 2 == 13

# ---------------------------------------------------------------------------------------------
# Job P0-15, carried from the P0-14 review. Item 1: a floor wound DOWNWARD (a reversed face, which
# the engine will flip) still gets its probes, so the Validator sees it from inside.
# ---------------------------------------------------------------------------------------------

def test_a_reversed_floor_keeps_its_probes_and_they_see_it_from_behind():
    room = _flipped(closed_room(), [0, 1])                    # the inner floor now faces DOWN, into the void
    assert np.allclose(face_normals(room)[0:2], [[0.0, 0.0, -1.0]] * 2)
    probes = interior_probes(room)
    inside = _inside_the_room(probes)
    assert inside.sum() == 20 and len(probes) == 40, "the room's 20 and the roof's 20, as for the intact room"
    assert (probes[inside, 2] == 63.0).all(), "1.6 m above the floor at z = 0, on the +z side of it"
    s = face_samples(room, area_per_sample=500.0)
    vs = visible_samples(room, s, _no_points(), _no_points(), probes[inside], build_caster(room))
    walls = np.isin(s.face, np.arange(4, 12))
    assert vs.seen[walls].all() and vs.front[walls].all(), "all 4 inner walls, from the front, from every probe"
    floor = s.face < 2
    assert vs.seen[floor].all() and not vs.front[floor].any(), "the reversed floor itself, from behind"


def test_a_downward_face_is_ground_only_under_a_lid():
    floor = _flipped(grid_slab(10, 10))                       # 100 x 100 in at z = 0, wound DOWN
    assert interior_probes(floor).shape == (0, 3), "in the open it is an awning or a canopy, not a floor"
    lid = _lifted(_flipped(grid_slab(10, 10)), 120.0)         # a ceiling 120 in above it, facing down
    probes = interior_probes(_merged(floor, lid))
    assert len(probes) == 9 and np.allclose(probes[:, 2], 63.0), "under a lid it is a reversed floor: 3 x 3"
    assert not (probes[:, 2] > 120.0).any(), "and the lid's own top side, open to the sky, gets none"


def test_a_floor_drawn_once_each_way_gets_one_probe_per_cell():
    floor = grid_slab(10, 10)
    lid = _lifted(_flipped(grid_slab(10, 10)), 120.0)
    assert len(interior_probes(_merged(floor, lid))) == 9
    both_ways = interior_probes(_merged(floor, _flipped(floor), lid))
    assert len(both_ways) == 9, "the up layer and the down layer share every cell and height: one probe each"


def test_a_downward_ceiling_of_a_solid_taller_than_the_headroom_adds_no_probe_inside_it():
    floor = grid_slab(10, 10)                                           # 100 x 100 in at z = 0, faces +z
    block = _wall(0.0, 100.0, 0.0, 100.0, 100.0, 400.0)                 # a closed solid, 300 in thick, 100 in up
    m = _merged(floor, block)
    assert np.allclose(face_normals(m)[floor.n_faces:floor.n_faces + 2], [[0.0, 0.0, -1.0]] * 2), \
        "premise: the block's bottom is wound downward, like a true ceiling"
    # premise: from half an inch above that bottom the headroom ray runs up INSIDE the block to its top
    _, t = build_caster(m).first_hit(np.array([[50.0, 50.0, 100.5]]), np.array([[0.0, 0.0, 1.0]]))
    assert t[0] > 83.0
    probes = interior_probes(m)
    assert not _in_the_box(probes, (0.0, 0.0, 100.0), (100.0, 100.0, 400.0)).any()
    assert len(probes) == 18, "9 on the floor under it and 9 on the block's top, none from its bottom"


# ---------------------------------------------------------------------------------------------
# Item 6: the limits the `interior_probes` docstring names are the measured ones
# ---------------------------------------------------------------------------------------------

def test_the_limits_named_in_the_interior_probes_docstring_are_the_measured_ones():
    def kept(*reversed_faces):
        return int(_inside_the_room(interior_probes(_flipped(closed_room(), list(reversed_faces)))).sum())

    assert kept(2, 3) == 20, "one reversed ceiling alone costs nothing"
    assert kept(2, 3, 6, 7) == 18, "the reversed ceiling and the wall x = 200"
    assert kept(2, 3, 6, 7, 10, 11) == 13, "the reversed ceiling and the walls x = 200 and x = 0"
    assert kept(0, 1) == 20, "a reversed floor alone is fine (item 1)"
    assert kept(0, 1, 2, 3) == 20, "so are a reversed floor and ceiling together: the walls still face the room"
    assert kept(*range(12)) == 0, "every inner face reversed: the room reads as the inside of a solid"
