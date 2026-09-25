"""Probe: two top regions lying on each other (a duplicate layer of two materials, which the
export carries -- "texture on texture") each get their OWN invented bottom, at the same depth.
`_coincident_new_faces` (solidify.py:1342) compares a new face only with ORIGINAL faces, walls are
deduplicated through `built_walls`, but nothing deduplicates bottoms: the fix itself ships a
z-fighting double layer on the underside.

Scene: a 40 x 40 in slab, sides 8 in deep and closed, NO bottom; its top is two coincident sheets,
one in m0 and one in m1 (the duplicate layer the owner wants gone, left in place by the overlap
pass because the materials differ).

usage: PYTHONPATH=<tree at e27eb79> .venv/Scripts/python.exe probe_double_bottom.py
"""
import numpy as np
import shapely

import engine
from engine.fixes.pipeline import FixProfile, fix_object
from engine.tests.fixtures.build import _mesh, _quads

print("engine:", engine.__file__)

P = [[0, 0, 0], [40, 0, 0], [40, 40, 0], [0, 40, 0], [0, 0, -8], [40, 0, -8], [40, 40, -8], [0, 40, -8]]
uvs, fv, fvt, fm = [], [], [], []
_quads(P, uvs, fv, fvt, fm, [(0, 1, 2, 3)], material=0)                    # top, m0
_quads(P, uvs, fv, fvt, fm, [(0, 1, 2, 3)], material=1)                    # the same top again, m1
_quads(P, uvs, fv, fvt, fm, [(4, 5, 1, 0), (5, 6, 2, 1), (6, 7, 3, 2), (7, 4, 0, 3)], material=0)
# the second layer as its own vertices, as a separate export layer would be
m = _mesh("double_layer_top_no_bottom", P, uvs, fv, fvt, materials=("m0", "m1"), face_material=fm)
P2 = np.asarray(P, float).tolist() + [[0, 0, 0], [40, 0, 0], [40, 40, 0], [0, 40, 0]]
fv2 = np.asarray(fv).copy()
fv2[2:4] = fv2[2:4] + 8                                                    # layer 2 on its own rows
m = _mesh("double_layer_top_no_bottom", P2, uvs, fv2.tolist(), fvt, materials=("m0", "m1"),
          face_material=fm)


def z_census(mesh, z):
    tri = mesh.positions[mesh.face_v]
    on = np.nonzero(np.abs(tri[:, :, 2] - z).max(axis=1) <= 1e-6)[0]
    by = {}
    for f in on:
        k = mesh.materials[int(mesh.face_material[f])]
        by[k] = round(by.get(k, 0.0) + shapely.Polygon(tri[f][:, :2]).area, 3)
    return by


for profile in (FixProfile(guard_size=(240, 160), n_dirs=64), FixProfile()):
    r = fix_object(m, {}, profile)
    s = r.solidify_report
    print(f"guard {profile.guard_size}: passed={r.passed}; regions processed {s['regions_processed']}, "
          f"bottoms added {s['bottoms_added']}, bottom faces refused {s['bottom_faces_refused']}")
    print("   shipped area at z = -8 by material:", z_census(r.mesh, -8.0),
          "| at z = 0:", z_census(r.mesh, 0.0))
    print("   overlap pairs of different materials reported:", len(r.overlap_pairs_diff_material),
          [(p["faces"], p["materials"], p["area"]) for p in r.overlap_pairs_diff_material])
