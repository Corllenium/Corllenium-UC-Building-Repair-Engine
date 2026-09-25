"""Probe: a replaced piece the cap guard RESTORES stays under the new wall that was laid ON it.

`_coincident_new_faces` (solidify.py:1368) never compares a new face with its own group's pieces,
because those are to be removed. But `solidify_feedback` restores a piece and KEEPS the new face
whenever a pixel of that piece fails (compare.py:1514-1516), and gives back every piece of a wall
that lost a triangle (compare.py:1418-1421). Either way the kept wall and the restored piece lie in
one plane: a coincident double layer the fix itself made.

Input: `slab_with_sawtooth_side` with every tooth IN the side plane (offsets 0), in material m1,
and tooth 0 reaching 3 in BELOW the slab (apex at z = -11 against the slab's -8): its tip is not
covered by the 8 in wall, so its pixels fail and it is restored.

Prints the shipped faces lying in the x = 0 plane, per material, and the coplanar overlap between
the two materials there.

usage: PYTHONPATH=<tree at e27eb79> .venv/Scripts/python.exe probe_restored_piece_double_layer.py
"""
from dataclasses import replace

import numpy as np
import shapely

import engine
from engine.fixes.pipeline import FixProfile, fix_object
from engine.tests.fixtures.build import slab_with_sawtooth_side

print("engine:", engine.__file__)

m = slab_with_sawtooth_side(offsets=(0.0, 0.0, 0.0, 0.0, 0.0))
n_slab = 34
teeth = np.arange(n_slab, m.n_faces - 2)
P = m.positions.copy()
apex0 = int(m.face_v[teeth[0]][1])                  # tooth 0 is (b, apex, a)
assert np.isclose(P[apex0, 2], -8.0), P[apex0]
P[apex0, 2] = -11.0                                 # the deep tooth: 3 in below the slab
fm = m.face_material.copy()
fm[teeth] = 1
m = replace(m, positions=P, face_material=fm, materials=["m0_paving", "m1_concrete"])


def on_x0(mesh, tol=1e-6):
    tri = mesh.positions[mesh.face_v]
    return np.nonzero(np.abs(tri[:, :, 0]).max(axis=1) <= tol)[0]


def report(label, mesh):
    faces = on_x0(mesh)
    by = {}
    polys = {}
    for f in faces:
        t = mesh.positions[mesh.face_v[f]]
        poly = shapely.Polygon(t[:, 1:])
        k = mesh.materials[int(mesh.face_material[f])]
        by[k] = round(by.get(k, 0.0) + poly.area, 3)
        polys.setdefault(k, []).append(poly)
    both = 0.0
    if len(polys) == 2:
        a, b = (shapely.union_all(v) for v in polys.values())
        both = a.intersection(b).area
    print(f"  {label}: x=0 plane area by material {by}; covered by BOTH materials: {both:.3f} sq in")


print("input:")
report("input", m)
for profile in (FixProfile(guard_size=(240, 160), n_dirs=64), FixProfile()):
    r = fix_object(m, {}, profile)
    s = r.solidify_report
    print(f"guard {profile.guard_size}: passed={r.passed}")
    print("  cap guard rounds:", [(h["round"], h["failing_pixels"], h["removed"], h["pieces_restored"])
                                  for h in s["cap_guard"]])
    print("  pieces replaced", s["side_pieces_replaced"], "restored", s["side_pieces_restored"],
          "walls refused", s["walls_refused"])
    report("reference", r.reference_mesh)
    report("shipped", r.mesh)
    print("  folds:", r.fold_report.get("n_folds"), [(f["faces"], f["reason"]) for f in r.fold_report.get("folds", [])])
    print("  overlap pairs diff material:", r.overlap_pairs_diff_material)
