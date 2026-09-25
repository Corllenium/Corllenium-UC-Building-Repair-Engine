"""Unit probe of `_refuse_together` (9f64ae9, compare.py:1431-1440 at dc24e9a): WHO PAYS when a
rule-6 pixel is lost and what BEFORE showed there is a REPLACED piece. The docstring (and the main
loop, compare.py:1809-1813) say: the piece is restored and the new face kept. The code restores the
piece for the FIRST such pixel only; a second pixel on the same piece -- or one on a piece the main
loop already chose to restore this round -- falls through to `elif f not in refused` and refuses
the new face.

Scene: the suite's own (`test_a_face_held_up_by_a_refused_face_is_refused_with_it_unless_another_
holds_it`): walls at y = 0 (faces 0-1, wound -y), y = 20 (2-3, +y), y = 30 (4-5, +y); the slab ends
at y = 20; the wall at y = 20 is refused this round. The pixels' BEFORE hit is piece 7 (removed).
"""
import numpy as np

from engine.guard.compare import (INTERIOR_BELOW_BOTTOM, INTERIOR_INSIDE, INTERIOR_OUTSIDE_FOOTPRINT,
                                  _refuse_together, face_planes)
from engine.rays.caster import EmbreeCaster
import engine
print("engine:", engine.__file__)

P, faces = [], []
for y, sign in ((0.0, -1), (20.0, 1), (30.0, 1)):
    b = len(P)
    P += [[0, y, 0], [40, y, 0], [40, y, -10], [0, y, -10]]
    faces += ([[b, b + 2, b + 1], [b, b + 3, b + 2]] if sign < 0 else [[b, b + 1, b + 2], [b, b + 2, b + 3]])
P, faces = np.array(P, dtype=np.float64), np.array(faces, dtype=np.int64)
planes = face_planes(P, faces)


def interior(face_ids, points):
    inside = (points[:, 2] >= -2.0) & (points[:, 2] <= 0.0) & (points[:, 1] <= 20.0)
    return np.where(inside, INTERIOR_INSIDE, INTERIOR_BELOW_BOTTOM)


def run(n_pixels, already_restoring):
    starts = np.array([[20.0 + k, 0.0, -1.0] for k in range(n_pixels)])
    records = [[np.array([0.0, 1.0, 0.0]), starts, np.full(n_pixels, 40.0),
                np.zeros(n_pixels, np.int64), np.full(n_pixels, 7),
                np.full(n_pixels, INTERIOR_OUTSIDE_FOOTPRINT), np.full(n_pixels, 2)]]
    refuse, restore = {2: [1], 3: [1]}, ({7} if already_restoring else set())
    removed = np.zeros(10, dtype=bool)
    removed[7] = True
    together = _refuse_together(refuse, restore, removed, records, np.arange(6), planes, P, faces,
                                EmbreeCaster, interior)
    return together, sorted(refuse), sorted(restore)


print("one pixel on piece 7                      :", run(1, False),
      " (the suite's case: face 0 kept, 7 restored)")
print("two pixels on piece 7                     :", run(2, False),
      " (docstring: face 0 kept, 7 restored)")
print("one pixel, 7 already restored this round  :", run(1, True),
      " (docstring: face 0 kept)")
