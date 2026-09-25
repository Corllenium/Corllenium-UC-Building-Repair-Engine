"""Probe: an UNDERSIDE a top runs into is still processed as a top when a NEIGHBOUR's side hangs
along one of its edges (the SR6 underside test at solidify.py:773 needs every own side to stand
up), and then its invented bottom is let through by the cap guard's shell exemption: the region's
own faces are `shell_faces` (solidify.py:994-995), so a bottom may cover them as "interior"
(compare.py:1504), and the hidden pass deletes the real underside. SR6 item 3's failure, alive
for the regions the author's concern 1 lists (A 467, 166, 244: a little own side hanging).

Scene (inches; closed boxes wound outward):
  L  a closed slab: top z = 0 over x 0..40, y 0..40, sides down to -8, bottom at -8. Sees sky.
  B  a closed block overhanging open air beside L: x 40..80, y 0..40, z 0..20. Its underside
     (z = 0, facing down) is flush with L's top, so L's x = 40 edge CONTINUES into it -- and
     L's own x = 40 side, hanging 8 in, lies along the underside's x = 40 edge.

Prints what solidify built under B, and whether B's underside ships.

usage: PYTHONPATH=<tree at e27eb79> .venv/Scripts/python.exe probe_underside_with_hanging_neighbour.py
"""
import numpy as np
import shapely

import engine
from engine.fixes.pipeline import FixProfile, fix_object
from engine.tests.fixtures.build import _mesh, _quads

print("engine:", engine.__file__)


def box(P, uvs, fv, fvt, fm, x0, x1, y0, y1, z0, z1, material=0):
    b = len(P)
    P += [[x0, y0, z0], [x1, y0, z0], [x1, y1, z0], [x0, y1, z0],
          [x0, y0, z1], [x1, y0, z1], [x1, y1, z1], [x0, y1, z1]]
    _quads(P, uvs, fv, fvt, fm, [(b + 0, b + 3, b + 2, b + 1),     # bottom, -z   (faces +0, +1)
                                 (b + 4, b + 5, b + 6, b + 7),     # top, +z      (+2, +3)
                                 (b + 0, b + 1, b + 5, b + 4),     # y0, -y
                                 (b + 1, b + 2, b + 6, b + 5),     # x1, +x
                                 (b + 2, b + 3, b + 7, b + 6),     # y1, +y
                                 (b + 3, b + 0, b + 4, b + 7)],    # x0, -x
           material=material)


P, uvs, fv, fvt, fm = [], [], [], [], []
box(P, uvs, fv, fvt, fm, 0, 40, 0, 40, -8, 0)       # L: faces 0-11
box(P, uvs, fv, fvt, fm, 40, 80, 0, 40, 0, 20)      # B: faces 12-23; its underside is 12, 13
m = _mesh("overhang_beside_a_slab", P, uvs, fv, fvt, face_material=fm)
UNDERSIDE = [12, 13]

for profile in (FixProfile(guard_size=(240, 160), n_dirs=64), FixProfile()):
    r = fix_object(m, {}, profile)
    s = r.solidify_report
    n_kept_in = int((~r.replaced_input).sum())
    ref = r.reference_mesh
    inv = np.arange(n_kept_in, ref.n_faces)
    tri = ref.positions[ref.face_v[inv]]
    under_b = inv[(tri[:, :, 0].min(axis=1) >= 40 - 1e-9)]
    print(f"guard {profile.guard_size}: passed={r.passed}")
    print("   regions processed:", s["regions_processed"], "continued:", s["top_regions_continued"],
          "undersides_not_tops:", s["undersides_not_tops"], "rep:", s["representative_side_per_region"])
    print("   bottoms added:", s["bottoms_added"], "walls built:", s["skirts_added"],
          "refused walls/bottom faces:", s["walls_refused"]["faces"], s["bottom_faces_refused"]["faces"])
    if len(under_b):
        zb = ref.positions[ref.face_v[under_b]][:, :, 2]
        print(f"   invented faces under B kept: {len(under_b)}, z from {zb.min():.1f} to {zb.max():.1f}")
    ref_id = {int(f): i for i, f in enumerate(np.nonzero(~r.replaced_input)[0])}
    print("   B's real underside replaced:", r.replaced_input[UNDERSIDE].tolist(),
          "| removed by the hidden pass:", [bool(r.removed_hidden[ref_id[f]]) for f in UNDERSIDE if f in ref_id])
    shipped = r.mesh.positions[r.mesh.face_v]
    beneath = shapely.box(40.0, 0.0, 80.0, 40.0)             # B's footprint
    flat = np.ptp(shipped[:, :, 2], axis=1) <= 1e-9

    def area_at(z):
        polys = [shapely.Polygon(t[:, :2]) for t in shipped[flat & np.isclose(shipped[:, 0, 2], z)]]
        return round(sum(p.intersection(beneath).area for p in polys), 3)
    print("   SHIPPED over B's footprint (x 40..80): horizontal area at z = 0 (B's underside):",
          area_at(0.0), "| at z = -8 (the invented floor):", area_at(-8.0))
    print("   guard_final:", {k: v for k, v in r.guard_final.totals.items() if v and k != "model_px"},
          "| cap guard rounds:", [(h["round"], h["failing_pixels"], h["removed"]) for h in s["cap_guard"]])
