"""Probe: SR6's underside test (solidify.py:773 -- a no-sky region a top runs into is an underside
when every own side of it stands UP) takes a REAL top for an underside when that top's hanging
sides are the ones missing, which is the very case the side rebuild exists for.

Scene (inches): one slab whose top is two regions at z = 0 -- L (x 0..40, m0) sees sky, R (x 40..80,
m1) lies under an upper landing U (a closed box x 40..80, z 10..20) and sees none. L has 10 in
skirts on x = 0, y = 0, y = 40. Under R the export left its sides OPEN (y = 0 and y = 40 over
x 40..80) and there is no bottom anywhere. The only own side R has is a RISER at x = 80, standing
up from its edge to the landing (the step up to U).

Expected of a correct rule: R is a top (L continues into it); its two open sides are walled and
the whole slab gets its bottom. Prints what solidify did instead.

usage: PYTHONPATH=<tree at e27eb79> .venv/Scripts/python.exe probe_real_top_taken_for_underside.py
"""
import numpy as np

import engine
from engine.fixes.pipeline import FixProfile
from engine.fixes.solidify import solidify
from engine.pipeline import analyse_topology
from engine.tests.fixtures.build import _mesh, _quads

print("engine:", engine.__file__)

P, uvs, fv, fvt, fm = [], [], [], [], []


def v(x, y, z):
    P.append([float(x), float(y), float(z)])
    return len(P) - 1


a = [v(0, 0, 0), v(40, 0, 0), v(40, 40, 0), v(0, 40, 0)]
_quads(P, uvs, fv, fvt, fm, [tuple(a)], material=0)                       # L's top, +z
b = [a[1], v(80, 0, 0), v(80, 40, 0), a[2]]
_quads(P, uvs, fv, fvt, fm, [tuple(b)], material=1)                       # R's top, +z
lo = [v(0, 0, -10), v(40, 0, -10), v(40, 40, -10), v(0, 40, -10)]
_quads(P, uvs, fv, fvt, fm, [(lo[3], lo[0], a[0], a[3]),                  # L x = 0, -x
                             (lo[0], lo[1], a[1], a[0]),                  # L y = 0, -y
                             (lo[2], lo[3], a[3], a[2])], material=0)     # L y = 40, +y
r_top = [v(80, 0, 10), v(80, 40, 10)]            # the riser, up to U's underside
_quads(P, uvs, fv, fvt, fm, [(b[1], b[2], r_top[1], r_top[0])], material=0)   # riser x = 80, +x
t = [v(40, 0, 20), v(80, 0, 20), v(80, 40, 20), v(40, 40, 20)]
u = [v(40, 0, 10), v(80, 0, 10), v(80, 40, 10), v(40, 40, 10)]
_quads(P, uvs, fv, fvt, fm, [(t[0], t[1], t[2], t[3]), (u[0], u[3], u[2], u[1]),
                             (u[0], u[1], t[1], t[0]), (u[2], u[3], t[3], t[2]),
                             (u[3], u[0], t[0], t[3]), (u[1], u[2], t[2], t[1])], material=0)  # U
m = _mesh("real_top_under_a_landing", P, uvs, fv, fvt, materials=("m0", "m1"), face_material=fm)

topo = analyse_topology(m)
region_R = int(topo.face_region[2])
r = solidify(m, topo, FixProfile(guard_size=(240, 160), n_dirs=64))
s = r.report
print("R's region", region_R, "| undersides_not_tops:", s["undersides_not_tops"],
      "| regions processed:", s["regions_processed"], "| edges continued:", s["edges_continued"])
new = np.nonzero(r.new_faces)[0]
for f in new:
    tri = r.mesh.positions[r.mesh.face_v[f]]
    print(f"   kept new face {f}: x {tri[:, 0].min():.0f}..{tri[:, 0].max():.0f}, "
          f"y {tri[:, 1].min():.0f}..{tri[:, 1].max():.0f}, z {tri[:, 2].min():.0f}..{tri[:, 2].max():.0f}")
print("   walls refused:", s["walls_refused"], "| bottoms added:", s["bottoms_added"])
under_r = [f for f in new if r.mesh.positions[r.mesh.face_v[f]][:, 0].min() >= 40 - 1e-9]
print("   new faces under R (x >= 40):", len(under_r))
