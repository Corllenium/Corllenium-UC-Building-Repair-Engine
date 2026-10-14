"""Job P2-V2 item 1: the owner's visibility floor, measured (AGENTS.md section 5, owner 2026-10-10).

`face_visible_pixels(before, face, viewpoint)` renders an ID buffer of BEFORE along the viewpoint's line, centred on
the face, at `FLOOR_IN_PER_PX` (0.02 in) per pixel, and counts the pixels where that face is the nearest surface:
orthographic for a direction, perspective from a camera or probe with the pixel size taken at the face.
"""
import dataclasses

import numpy as np
import pytest

from engine.tests.fixtures.build import _mesh
from engine.validate.floor import (FLOOR_IN_PER_PX, VISIBLE_FLOOR_PX, Viewpoint, face_pixels, face_visible_pixels)


def _square(size=1.0, z=0.0, x0=0.0, y0=0.0, flip=False):
    """Two triangles making a `size` square at height z, wound upward (downward with `flip`)."""
    P = [[x0, y0, z], [x0 + size, y0, z], [x0 + size, y0 + size, z], [x0, y0 + size, z]]
    fv = [[0, 1, 2], [0, 2, 3]]
    if flip:
        fv = [[0, 2, 1], [0, 3, 2]]
    return _mesh("square", P, [[0, 0], [1, 0], [1, 1], [0, 1]], fv, [[0, 1, 2], [0, 2, 3]])


def _join(*meshes):
    """One mesh holding the faces of all of `meshes`, in order."""
    P, uv, fv, fvt = [], [], [], []
    for m in meshes:
        fv.append(m.face_v + sum(len(p) for p in P))
        fvt.append(m.face_vt + sum(len(u) for u in uv))
        P.append(m.positions)
        uv.append(m.uvs)
    return _mesh("joined", np.vstack(P), np.vstack(uv), np.vstack(fv), np.vstack(fvt))


DOWN = Viewpoint.direction([0.0, 0.0, -1.0])        # a viewer far above, looking down
UP = Viewpoint.direction([0.0, 0.0, 1.0])           # a viewer far below, looking up


def _total(mesh, faces, vp):
    return sum(face_visible_pixels(mesh, f, vp) for f in faces)


def test_the_floor_is_named_four_pixels_at_two_hundredths_of_an_inch():
    assert VISIBLE_FLOOR_PX == 4
    assert FLOOR_IN_PER_PX == 0.02


def test_a_one_inch_square_seen_square_on_is_2500_pixels_from_above_and_from_below():
    m = _square(1.0)
    for vp in (DOWN, UP):                                       # its front, then its back: Unity draws both
        each = [face_visible_pixels(m, f, vp) for f in (0, 1)]
        assert all(1200 <= n <= 1300 for n in each), each
        assert abs(sum(each) - 2500) <= 60, each                # 50 x 50 px; the shared diagonal may count twice


def test_an_oblique_view_sees_the_foreshortened_area():
    m = _square(1.0)
    tilt = np.radians(60.0)
    vp = Viewpoint.direction([np.sin(tilt), 0.0, -np.cos(tilt)])     # 60 degrees off the normal: half the area
    assert abs(_total(m, (0, 1), vp) - 1250) <= 60


def test_an_edge_on_view_and_a_face_with_no_area_show_nothing():
    m = _square(1.0)
    assert _total(m, (0, 1), Viewpoint.direction([1.0, 0.0, 0.0])) == 0
    flat = _mesh("flat", [[0, 0, 0], [1, 0, 0], [2, 0, 0]], [[0, 0]] * 3, [[0, 1, 2]], [[0, 1, 2]])
    assert face_visible_pixels(flat, 0, DOWN) == 0


def test_a_face_half_hidden_by_another_shows_half_and_the_hider_shows_whole():
    m = _join(_square(1.0), _square(1.0, z=1.0, x0=0.5))            # a lid over the half x > 0.5, 1 in up
    under = _total(m, (0, 1), DOWN)
    assert abs(under - 1250) <= 60, under
    assert abs(_total(m, (2, 3), DOWN) - 2500) <= 60
    assert _total(m, (0, 1), UP) > 2400, "from below nothing hides it"


def test_a_layer_within_the_z_fight_distance_does_not_hide_and_one_further_out_does():
    near = _join(_square(1.0), _square(1.0, z=0.01))                # 0.01 in apart: both are drawn in Unity
    assert _total(near, (0, 1), DOWN) > 2400
    far = _join(_square(1.0), _square(1.0, z=0.5))
    assert _total(far, (0, 1), DOWN) == 0


def _rect(x0, x1, y0, y1, z):
    return _mesh("rect", [[x0, y0, z], [x1, y0, z], [x1, y1, z], [x0, y1, z]], [[0, 0], [1, 0], [1, 1], [0, 1]],
                 [[0, 1, 2], [0, 2, 3]], [[0, 1, 2], [0, 2, 3]])


def lid_with_hole(x0, x1, y0, y1, z=1.0, size=1.0):
    """A `size` square lid at height z with a rectangular hole [x0, x1] x [y0, y1], as eight rectangles."""
    xs, ys = (0.0, x0, x1, size), (0.0, y0, y1, size)
    return [_rect(xs[i], xs[i + 1], ys[j], ys[j + 1], z) for i in range(3) for j in range(3) if (i, j) != (1, 1)]


def test_a_hole_shows_only_what_it_lets_through():
    m = _join(_square(1.0), *lid_with_hole(0.45, 0.55, 0.45, 0.55))    # a 0.1 x 0.1 in hole 1 in over the square
    seen = _total(m, (0, 1), DOWN)
    assert 16 <= seen <= 40, seen                                      # 5 x 5 = 25 px, give or take the diagonal


def test_a_camera_sees_with_the_pixel_size_taken_at_the_face():
    m = _square(1.0)
    above = Viewpoint.point([0.5, 0.5, 10.0])                        # 10 in over the middle: nearly square on
    total = _total(m, (0, 1), above)
    assert abs(total - 2500) <= 80, total
    far = Viewpoint.point([0.5, 0.5, 1000.0])
    assert abs(_total(m, (0, 1), far) - 2500) <= 80, "the pixel is 0.02 in at the face, however far the camera"


def test_a_probe_over_a_wide_floor_sees_it_all_round_in_every_direction():
    # a fan of four triangles round the point under the probe, each reaching 82 degrees from straight down at its corners: one
    # image plane cannot hold them, so the measure must look all round the probe; by symmetry each counts the same
    L = 5.0
    P = [[0, 0, 0], [L, -L, 0], [L, L, 0], [-L, L, 0], [-L, -L, 0]]
    fv = [[0, 1, 2], [0, 2, 3], [0, 3, 4], [0, 4, 1]]
    m = _mesh("fan", P, [[0, 0]] * 5, fv, [[0, 0, 0]] * 4)
    probe = Viewpoint.point([0.0, 0.0, 1.0])
    counts = [face_visible_pixels(m, f, probe) for f in range(4)]
    assert min(counts) > 0 and max(counts) - min(counts) <= 0.02 * max(counts), counts


def test_the_pixels_lie_on_the_face_and_point_to_the_viewer():
    m = _square(1.0)
    probe = Viewpoint.point([0.5, 0.5, 3.0])
    blocks = list(face_pixels(m, 0, probe))
    pts = np.vstack([b.points for b in blocks])
    assert np.allclose(pts[:, 2], 0.0)
    toward = np.vstack([b.toward for b in blocks])
    expect = np.array([0.5, 0.5, 3.0]) - pts
    assert np.allclose(toward, expect / np.linalg.norm(expect, axis=1, keepdims=True))
    reach = np.concatenate([b.reach for b in blocks])
    assert np.allclose(reach, np.linalg.norm(expect, axis=1))


def test_a_viewpoint_must_say_what_it_is():
    with pytest.raises(ValueError):
        Viewpoint.direction([0.0, 0.0, 0.0])
    with pytest.raises(ValueError):
        Viewpoint("sideways", np.zeros(3))


def test_a_far_patch_of_a_big_face_counts_its_true_area_at_two_hundredths_across_the_line():
    """P2-V2 review, finding 2. Perspective pixels must count each patch's own area at 0.02 in across the line of sight
    (AGENTS.md section 5: "as projected across the line of sight"), wherever on the face it lies: a 1 x 1 in patch of
    a 400 in floor triangle seen from a probe at (5, 5, 63) counts 2,500 x cos(its angle to the line), within 15 %,
    near the probe and 390 in away alike (taking the pixel size at the centroid, 269 in off, counted 0.52 of that)."""
    L, W = 400.0, 10.0
    m = _mesh("strip", [[0, 0, 0], [L, 0, 0], [L, W, 0], [0, W, 0]], [[0, 0]] * 4, [[0, 1, 2], [0, 2, 3]],
              [[0, 0, 0]] * 2)
    probe = np.array([5.0, 5.0, 63.0])
    blocks = list(face_pixels(m, 0, Viewpoint.point(probe)))
    pts = np.vstack([b.points for b in blocks])
    weight = np.concatenate([b.weight for b in blocks])
    for x0 in (60.0, 100.0, 266.0, 390.0):                       # face 0 is the triangle y < x / 40: rows y 0..1
        inside = (pts[:, 0] >= x0) & (pts[:, 0] < x0 + 1) & (pts[:, 1] >= 0.0) & (pts[:, 1] < 1.0)
        v = probe - np.array([x0 + 0.5, 0.5, 0.0])
        owner = (abs(v[2]) / np.linalg.norm(v)) / FLOOR_IN_PER_PX ** 2           # 2,500 px x cos
        got = float(weight[inside].sum())
        assert abs(got / owner - 1.0) <= 0.15, (x0, got, owner)
