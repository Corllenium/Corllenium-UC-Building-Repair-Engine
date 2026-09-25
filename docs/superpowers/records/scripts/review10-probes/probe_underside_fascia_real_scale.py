"""`probe_underside_variants.py`'s "fascia" scene at the real files' scale, where a guard pixel spans
2 to 3 in at 900 x 600: L a closed slab x 0..W, y 0..W, z -8..0; B a closed block x W..2W, z 0..20
overhanging open air; a 3 in fascia (one quad, facing +x) hanging from B's underside's free edge
x = 2W. At W = 40 the default guard refused the walls (covers_below_bottom) and U shipped."""
from common import REAL, _mesh, area_at, box, fate, fix_object, quad, shapely, solidify_summary, where

where()
for W in (40.0, 400.0, 2000.0):
    P, uvs, fv, fvt, fm = [], [], [], [], []
    box(P, uvs, fv, fvt, fm, 0, W, 0, W, -8, 0)
    ids = box(P, uvs, fv, fvt, fm, W, 2 * W, 0, W, 0, 20)
    quad(P, uvs, fv, fvt, fm, [(2 * W, 0, -3), (2 * W, W, -3), (2 * W, W, 0), (2 * W, 0, 0)])
    m = _mesh("overhang_fascia", P, uvs, fv, fvt, face_material=fm)
    r = fix_object(m, {}, REAL)
    beneath = shapely.box(W, 0.0, 2 * W, W)
    print(f"[W = {W:g}] passed={r.passed}")
    print("   ", solidify_summary(r))
    print(f"    U: {fate(r, ids['bottom'])}; SHIPPED over B: z = 0 {area_at(r.mesh, beneath, 0.0)}, "
          f"z = -3 {area_at(r.mesh, beneath, -3.0)} (of {W * W:g})")
