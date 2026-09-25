"""Probe: one deep OWN side lets `_lower_surface` take the floor under an open slab for the slab's
underside; the walls then box the open space down to that floor, rule 5 counts everything in it
as the slab's inside, and the hidden pass deletes what stood there.

Scene (inches; every closed box wound outward):
  S  a thin upper slab: top z = 0 over x, y in [0, 40]; 2 in skirts on y = 0, y = 40, x = 40;
     NO bottom (the export's "almost no bottom").
  W  the wall S is attached to: one face in the plane x = 0, y -10..50 (or 0..40), z 0 down to -32, facing
     +x. Its top edge lies along S's x = 0 outline edge, so it is one of S's OWN sides (32 in).
  L  a lower slab with S's footprint: top z = -24, bottom z = -32, closed. 22 in of open space
     lies between S's skirts and L's top.
  B  a bench standing on L under S: a closed box x, y in [15, 25], z -24..-12.

S's representative depth is 2 in (three 2 in skirts outweigh W), so the review-I1 test
"no deeper than the slab's own sides go, + band" reads W's 32 in, and L's top 24 in down passes.

Three runs: W wider than S (y -10..50) -- the cap guard sees W beyond S's footprint through the
open space and refuses every wall; W along S's edge only (y 0..40), with and without the bench --
nothing is refused, the 2 in skirts are replaced by 24 in walls, and the hidden pass deletes the
bench and L's top. Each at 240 x 160 and 900 x 600.

usage: PYTHONPATH=<tree at e27eb79> .venv/Scripts/python.exe probe_lower_surface_floor.py
"""
import numpy as np

import engine
from engine.fixes.pipeline import FixProfile, fix_object
from engine.tests.fixtures.build import _mesh, _quads

print("engine:", engine.__file__)


def box(P, uvs, fv, fvt, fm, x0, x1, y0, y1, z0, z1, material=0, skip=()):
    """A closed axis-aligned box, wound outward; `skip` names faces left out."""
    b = len(P)
    P += [[x0, y0, z0], [x1, y0, z0], [x1, y1, z0], [x0, y1, z0],
          [x0, y0, z1], [x1, y0, z1], [x1, y1, z1], [x0, y1, z1]]
    loops = {"bottom": (b + 0, b + 3, b + 2, b + 1), "top": (b + 4, b + 5, b + 6, b + 7),
             "y0": (b + 0, b + 1, b + 5, b + 4), "x1": (b + 1, b + 2, b + 6, b + 5),
             "y1": (b + 2, b + 3, b + 7, b + 6), "x0": (b + 3, b + 0, b + 4, b + 7)}
    _quads(P, uvs, fv, fvt, fm, [q for k, q in loops.items() if k not in skip], material=material)


def scene(with_bench=True, w_span=(-10, 50)):
    P, uvs, fv, fvt, fm = [], [], [], [], []
    # S: top + three 2 in skirts, no bottom, no x = 0 side (W is there)
    s = len(P)
    P += [[0, 0, 0], [40, 0, 0], [40, 40, 0], [0, 40, 0],
          [0, 0, -2], [40, 0, -2], [40, 40, -2], [0, 40, -2]]
    _quads(P, uvs, fv, fvt, fm, [(s + 0, s + 1, s + 2, s + 3),        # top +z
                                 (s + 4, s + 5, s + 1, s + 0),        # y = 0, -y
                                 (s + 5, s + 6, s + 2, s + 1),        # x = 40, +x
                                 (s + 6, s + 7, s + 3, s + 2)])       # y = 40, +y
    # W: the wall face at x = 0, facing +x
    w = len(P)
    y0, y1 = w_span
    P += [[0, y0, 0], [0, y1, 0], [0, y1, -32], [0, y0, -32]]
    _quads(P, uvs, fv, fvt, fm, [(w + 0, w + 3, w + 2, w + 1)])       # normal +x
    # L: the lower slab, closed except its x = 0 side (W closes it)
    box(P, uvs, fv, fvt, fm, 0, 40, 0, 40, -32, -24, skip=("x0",))
    if with_bench:
        box(P, uvs, fv, fvt, fm, 15, 25, 15, 25, -24, -12, material=1)
    return _mesh("slab_over_a_floor", P, uvs, fv, fvt, materials=("m0", "m1"), face_material=fm)


for with_bench, w_span in ((True, (-10, 50)), (True, (0, 40)), (False, (0, 40))):
    m = scene(with_bench, w_span)
    for profile in (FixProfile(guard_size=(240, 160), n_dirs=64), FixProfile()):
        r = fix_object(m, {}, profile)
        s = r.solidify_report
        ref = r.reference_mesh
        n_ref_in = int((~r.replaced_input).sum())
        # map every shipped face back to its reference face, then to the input face
        src = np.concatenate([np.asarray(x).reshape(-1) for x in r.source_faces]) if r.source_faces else []
        shipped_ref = np.unique(src)
        input_of_ref = np.nonzero(~r.replaced_input)[0]
        shipped_input = set(input_of_ref[shipped_ref[shipped_ref < n_ref_in]].tolist())
        bench = list(range(20, 32)) if with_bench else []
        l_top = [12, 13]
        print(f"bench={with_bench} W y{w_span} guard {profile.guard_size}: passed={r.passed}")
        print("   lower surface:", s["walls_to_lower_surface"], "rep:", s["representative_side_per_region"],
              "bottom depth:", s["bottom_depth_per_region"])
        print("   sides rebuilt:", s["sides_rebuilt"], "walls refused:", s["walls_refused"],
              "pieces replaced:", s["side_pieces_replaced"], "interior covered:", s["interior_faces_covered"])
        inv = np.arange(n_ref_in, ref.n_faces)
        z = ref.positions[ref.face_v[inv]][:, :, 2] if len(inv) else np.zeros((0, 3))
        print("   invented faces reach z", float(z.min()) if len(z) else None)
        print("   L's top shipped:", [f in shipped_input for f in l_top],
              "| bench faces shipped:", sum(f in shipped_input for f in bench), "of", len(bench))
        print("   hidden removed:", r.n_removed_hidden, "| guard_final:",
              {k: v for k, v in r.guard_final.totals.items() if v and k != "model_px"})
