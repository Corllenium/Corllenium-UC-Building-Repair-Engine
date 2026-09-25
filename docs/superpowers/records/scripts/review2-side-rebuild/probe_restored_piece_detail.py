"""Detail for probe_restored_piece_double_layer.py: solidify alone at the default guard size --
which teeth were replaced or restored, which wall faces were kept, and the coplanar overlap of
each kept wall face with each tooth still present.

usage: PYTHONPATH=<tree at e27eb79> .venv/Scripts/python.exe probe_restored_piece_detail.py
"""
from dataclasses import replace

import numpy as np
import shapely

from engine.fixes.pipeline import FixProfile
from engine.fixes.solidify import solidify
from engine.pipeline import analyse_topology
from engine.tests.fixtures.build import slab_with_sawtooth_side

m = slab_with_sawtooth_side(offsets=(0.0, 0.0, 0.0, 0.0, 0.0))
teeth = np.arange(34, m.n_faces - 2)
P = m.positions.copy()
P[int(m.face_v[teeth[0]][1]), 2] = -11.0
fm = m.face_material.copy()
fm[teeth] = 1
m = replace(m, positions=P, face_material=fm, materials=["m0_paving", "m1_concrete"])

r = solidify(m, analyse_topology(m), FixProfile())
print("cap guard:", [(h["round"], h["failing_pixels"], h["removed"], h["pieces_restored"]) for h in r.report["cap_guard"]])
print("refused:", r.report["walls_refused"])
print("teeth (input ids) replaced:", [int(t) for t in teeth if r.replaced[t]],
      "kept in the mesh:", [int(t) for t in teeth if not r.replaced[t]])
kept_in = np.nonzero(~r.replaced)[0]
row_of = {int(f): i for i, f in enumerate(kept_in)}
new = np.nonzero(r.new_faces)[0]
for f in new:
    t = r.mesh.positions[r.mesh.face_v[f]]
    if np.abs(t[:, 0]).max() > 1e-9:
        continue
    wall = shapely.Polygon(t[:, 1:])
    for tooth in teeth:
        if r.replaced[tooth]:
            continue
        g = row_of[int(tooth)]
        tp = r.mesh.positions[r.mesh.face_v[g]]
        shared = wall.intersection(shapely.Polygon(tp[:, 1:])).area
        if shared > 1e-6:
            print(f"kept new face {f} (y {t[:,1].min():.0f}..{t[:,1].max():.0f}, z {t[:,2].min():.0f}..0, "
                  f"material {r.mesh.face_material[f]}) lies ON tooth {tooth} (material "
                  f"{r.mesh.face_material[g]}): {shared:.3f} sq in coplanar overlap")
