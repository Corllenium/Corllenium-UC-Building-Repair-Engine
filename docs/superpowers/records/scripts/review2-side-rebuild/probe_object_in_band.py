"""Probe: a separate object standing in front of a broken side, inside the 2.5 in side band and
below the top, is taken as a PIECE of that side and deleted (rule 4), although it lies outside
the slab's volume and is another material. The railing test (`slab_with_railing_outside`) is
protected only because the railing reaches above the top (`_PIECE_INSIDE_FRACTION`); nothing asks
whether a face in the band belongs to the slab -- no connectivity, material or shell test. Only
the cap guard's pixels (`reveal`) can put it back, and at the real files' scale none meets it.

Input: `slab_with_half_side(size)` (the x = 0 side exists over the first half of the edge and is
missing over the second; a post stands at x = -10) plus a SIGN in material m1 in front of the
missing half, 1.2 in out, z -6..-2, 8 in long: either a closed 0.2 in plate (front, back, rim) or
ONE face (SketchUp faces are two-sided). Run on a 40 in slab and on a 2000 in slab (a guard pixel
~2-3 in, like the real files).

Prints each sign face's fate: replaced by the wall (deleted), or shipped.

usage: PYTHONPATH=<tree at e27eb79> .venv/Scripts/python.exe probe_object_in_band.py
"""
import numpy as np

import engine
from engine.fixes.pipeline import FixProfile, fix_object
from engine.tests.fixtures.build import _mesh, _quads, slab_with_half_side

print("engine:", engine.__file__)



def build(single_face, size=40.0):
    base = slab_with_half_side(size=size)
    P = base.positions.tolist()
    uvs, fv, fvt = base.uvs.tolist(), base.face_v.tolist(), base.face_vt.tolist()
    fm = base.face_material.tolist()
    first = len(fv)
    b = len(P)
    k = size / 40.0
    x0, x1, y0, y1, z0, z1 = -1.2, -1.0, 24.0 * k, 24.0 * k + 8.0, -6.0, -2.0
    if single_face:
        # a sign modelled as ONE face (SketchUp faces are two-sided), 1.2 in out, facing -x
        P += [[x0, y0, z0], [x0, y1, z0], [x0, y1, z1], [x0, y0, z1]]
        _quads(P, uvs, fv, fvt, fm, [(b + 0, b + 3, b + 2, b + 1)], material=1)
        names = ["panel (x=-1.2)", "panel (x=-1.2)"]
    else:
        P += [[x0, y0, z0], [x1, y0, z0], [x1, y1, z0], [x0, y1, z0],
              [x0, y0, z1], [x1, y0, z1], [x1, y1, z1], [x0, y1, z1]]
        _quads(P, uvs, fv, fvt, fm, [(b + 0, b + 3, b + 2, b + 1), (b + 4, b + 5, b + 6, b + 7),
                                     (b + 0, b + 1, b + 5, b + 4), (b + 1, b + 2, b + 6, b + 5),
                                     (b + 2, b + 3, b + 7, b + 6), (b + 3, b + 0, b + 4, b + 7)],
               material=1)
        names = ["bottom", "bottom", "top", "top", "y0 rim", "y0 rim", "back (x=-1.0)",
                 "back (x=-1.0)", "y1 rim", "y1 rim", "front (x=-1.2)", "front (x=-1.2)"]
    m = _mesh("half_side_with_a_sign", P, uvs, fv, fvt, materials=("m0", "m1"), face_material=fm)
    return m, np.arange(first, m.n_faces), names


for single_face, size in ((False, 40.0), (True, 40.0), (True, 2000.0)):
  m, sign, names = build(single_face, size)
  print("SIGN:", "one face" if single_face else "closed 0.2 in plate", "| slab", size, "in")
  for profile in (FixProfile(guard_size=(240, 160), n_dirs=64), FixProfile()):
      r = fix_object(m, {}, profile)
      s = r.solidify_report
      ref_of = {int(f): i for i, f in enumerate(np.nonzero(~r.replaced_input)[0])}
      src = set(np.concatenate([np.asarray(x).reshape(-1) for x in r.source_faces]).tolist())
      print(f"guard {profile.guard_size}: passed={r.passed}; sides rebuilt {s['sides_rebuilt']}, "
              f"pieces replaced {s['side_pieces_replaced']}, walls refused {s['walls_refused']}")
      for f, name in zip(sign, names):
            state = ("REPLACED by the wall" if r.replaced_input[f]
                     else "shipped" if ref_of[int(f)] in src else "removed later")
            print(f"   sign face {f} {name}: {state}")
