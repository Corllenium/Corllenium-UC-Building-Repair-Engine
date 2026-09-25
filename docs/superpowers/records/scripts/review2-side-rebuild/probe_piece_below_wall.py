"""Probe: a replaced piece may reach BELOW the wall that replaces it (`_wall_pieces` takes any band
face at least half inside a window reaching down to what hangs from the edge, solidify.py:634-643,
while the wall stops at the slab's depth). The part below is deleted with nothing in its place,
and only the cap guard's PIXELS (`reveal`, compare.py:1448-1451) can put it back -- the removal is
never confirmed by rays, unlike debris since brief 09.

Scene: a closed slab `size` x `size` x 8 in (bottom and three skirts, outward) whose x = 0 side is
missing except ONE tooth in the side plane: base on the top edge over y = size/2 .. size/2 + 8,
apex 11 in down -- 3 in below the slab, a fin hanging under it.

Prints, at fixture scale (40 in) and at the real files' scale (2000 in, a guard pixel ~2-3 in),
what became of the tooth: replaced (its fin gone, nothing below the wall), or restored under the
kept wall (a coincident double layer).

usage: PYTHONPATH=<tree at e27eb79> .venv/Scripts/python.exe probe_piece_below_wall.py
"""
import numpy as np
import shapely

import engine
from engine.fixes.pipeline import FixProfile, fix_object
from engine.tests.fixtures.build import _mesh, _quads

print("engine:", engine.__file__)


def scene(size):
    s, h = size, 8.0
    P = [[0, 0, 0], [s, 0, 0], [s, s, 0], [0, s, 0], [0, 0, -h], [s, 0, -h], [s, s, -h], [0, s, -h]]
    uvs, fv, fvt, fm = [], [], [], []
    _quads(P, uvs, fv, fvt, fm, [(0, 1, 2, 3), (4, 7, 6, 5), (4, 5, 1, 0), (5, 6, 2, 1), (6, 7, 3, 2)])
    y0 = s / 2.0
    b = len(P)
    P += [[0, y0, 0], [0, y0 + 8.0, 0], [0, y0 + 4.0, -11.0]]
    fv.append([b + 1, b + 2, b + 0])                       # normal -x, outward
    base = len(uvs)
    uvs += [[P[v][1] * 0.05, P[v][2] * 0.05] for v in (b + 1, b + 2, b + 0)]
    fvt.append([base, base + 1, base + 2])
    fm.append(0)
    return _mesh("slab_with_one_deep_tooth", P, uvs, fv, fvt, face_material=fm), len(fv) - 1


def x0_census(mesh, tooth_ref=None):
    tri = mesh.positions[mesh.face_v]
    on = np.nonzero(np.abs(tri[:, :, 0]).max(axis=1) <= 1e-6)[0]
    polys = [shapely.Polygon(tri[f][:, 1:]) for f in on]
    below = sum(p.intersection(shapely.box(-1e9, -1e9, 1e9, -8.0)).area for p in polys)
    total = sum(p.area for p in polys)
    union = shapely.union_all(polys).area if polys else 0.0
    return round(total, 3), round(union, 3), round(below, 3)


for size in (40.0, 2000.0):
    m, tooth = scene(size)
    r = fix_object(m, {}, FixProfile())
    s = r.solidify_report
    print(f"slab {size} in: passed={r.passed}; tooth replaced={bool(r.replaced_input[tooth])}; "
          f"walls refused {s['walls_refused']}; cap rounds "
          f"{[(h['round'], h['failing_pixels'], h['removed'], h['pieces_restored']) for h in s['cap_guard']]}")
    t, u, below = x0_census(r.mesh)
    print(f"   shipped x = 0 plane: sum of face areas {t}, union {u} (double layer = {t - u:.3f} sq in), "
          f"area below the slab (z < -8) {below} (the tooth fin: 3.27 sq in)")
