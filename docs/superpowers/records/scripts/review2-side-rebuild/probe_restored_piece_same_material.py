"""probe_restored_piece_double_layer.py with the teeth in the TOP's material (m0): does anything
downstream (folds, the duplicate-layer pass) remove the coincident layer when both are one
material? Prints the same x = 0 plane census, and the fold / overlap reports.

usage: PYTHONPATH=<tree at e27eb79> .venv/Scripts/python.exe probe_restored_piece_same_material.py
"""
import numpy as np
import shapely
from dataclasses import replace
from engine.fixes.pipeline import FixProfile, fix_object
from engine.tests.fixtures.build import slab_with_sawtooth_side

m = slab_with_sawtooth_side(offsets=(0.0, 0.0, 0.0, 0.0, 0.0))
teeth = np.arange(34, m.n_faces - 2)
P = m.positions.copy()
P[int(m.face_v[teeth[0]][1]), 2] = -11.0
m = replace(m, positions=P)

def census(mesh):
    tri = mesh.positions[mesh.face_v]
    faces = np.nonzero(np.abs(tri[:, :, 0]).max(axis=1) <= 1e-6)[0]
    polys = [shapely.Polygon(mesh.positions[mesh.face_v[f]][:, 1:]) for f in faces]
    total = sum(p.area for p in polys)
    union = shapely.union_all(polys).area if polys else 0.0
    return round(total, 3), round(union, 3)

r = fix_object(m, {}, FixProfile())
print("passed", r.passed, "| x=0 plane: sum of face areas, area of their union (a double layer "
      "shows as sum > union)")
print("  reference", census(r.reference_mesh), " shipped", census(r.mesh))
print("  folds:", [(f["faces"], f["verdict"], f["reason"]) for f in r.fold_report.get("folds", [])])
print("  overlap removed:", int(r.n_removed_overlap), "pairs same/diff:", r.n_overlap_pairs_same,
      r.n_overlap_pairs_diff)
print("  merge:", {k: r.merge_report.get(k) for k in ("regions_merged", "regions_skipped", "rolled_back")})
