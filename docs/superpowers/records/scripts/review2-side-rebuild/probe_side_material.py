"""Probe: a broken side of a DIFFERENT material from its top is rebuilt in the top's material.

Input: `slab_with_sawtooth_side` (the SR2 fixture), with the teeth -- the broken x = 0 side --
given material m1 ("concrete") while the top and every other face keep m0 ("paving").

Prints, for the x = 0 side plane of the INPUT and of the SHIPPED mesh, the area per material, and
the run's verdict. Expected if the side rebuild respected the side's own look: the side stays m1.

usage: PYTHONPATH=<tree at e27eb79> .venv/Scripts/python.exe probe_side_material.py
"""
import numpy as np

import engine
from engine.fixes.pipeline import FixProfile, fix_object
from engine.tests.fixtures.build import slab_with_sawtooth_side
from dataclasses import replace

print("engine:", engine.__file__)

m = slab_with_sawtooth_side()
n_slab = 5 * 3 * 2 + 2 * 2          # _slab_rows: 5 rows x (top, bottom, x=s skirt) quads + 2 skirts
teeth = np.arange(n_slab, m.n_faces - 2)          # the teeth, before the rib's two triangles
fm = m.face_material.copy()
fm[teeth] = 1
m = replace(m, face_material=fm, materials=["m0_paving", "m1_concrete"])


def side_area(mesh, x_max=1.0):
    tri = mesh.positions[mesh.face_v]
    n = np.cross(tri[:, 1] - tri[:, 0], tri[:, 2] - tri[:, 0])
    area = 0.5 * np.linalg.norm(n, axis=1)
    on_side = (np.abs(tri[:, :, 0]).max(axis=1) <= x_max) & (np.abs(n[:, 0]) > 0.9 * 2 * area)
    out = {}
    for f in np.nonzero(on_side)[0]:
        name = mesh.materials[int(mesh.face_material[f])]
        out[name] = round(out.get(name, 0.0) + float(area[f]), 3)
    return out


print("input  x=0 side area by material:", side_area(m))
for profile in (FixProfile(guard_size=(240, 160), n_dirs=64), FixProfile()):
    r = fix_object(m, {}, profile)
    s = r.solidify_report
    print(f"guard {profile.guard_size}: passed={r.passed} invariants={r.invariants}")
    print("  sides_rebuilt", s["sides_rebuilt"], "pieces replaced", s["side_pieces_replaced"],
          "refused", s["walls_refused"])
    print("  reference x=0 side by material:", side_area(r.reference_mesh))
    print("  shipped   x=0 side by material:", side_area(r.mesh))
    print("  guard_final totals:", {k: v for k, v in r.guard_final.totals.items() if v})
