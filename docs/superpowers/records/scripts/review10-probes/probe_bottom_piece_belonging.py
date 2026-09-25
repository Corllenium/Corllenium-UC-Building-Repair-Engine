"""01cc420 applied "a piece belongs to the slab" to WALLS only: `_bottom_pieces` (solidify.py:867-888)
still takes any eligible face within side_band of the bottom plane, above OR below it, parallel,
nearer the bottom than the top, centroid over the footprint. Scene: a slab `size` square, four 8 in
skirts, NO bottom; under it hangs a lamp -- a closed box 6 x 6 x 2 in, m1, centred, its top face 2 in
BELOW the slab's bottom plane (z -12..-10), touching nothing. Solidify builds the bottom at -8."""
from common import FixProfile, _mesh, box, np, where
from engine.fixes.solidify import solidify
from engine.pipeline import analyse_topology
where()
for size in (40.0, 2000.0):
    P, uvs, fv, fvt, fm = [], [], [], [], []
    box(P, uvs, fv, fvt, fm, 0, size, 0, size, -8, 0, skip=("bottom",))
    c = size / 2.0
    lamp = box(P, uvs, fv, fvt, fm, c - 3, c + 3, c - 3, c + 3, -12, -10, material=1)
    m = _mesh("lamp_under_a_slab", P, uvs, fv, fvt, materials=("m0", "m1"), face_material=fm)
    r = solidify(m, analyse_topology(m), FixProfile(guard_size=(900, 600), n_dirs=32))
    s = r.report
    print(f"size {size:g}: cap_guard_passed={s['cap_guard_passed']}, bottoms {s['bottoms_added']}, "
          f"pieces replaced {s['side_pieces_replaced']} {s['side_pieces_replaced_by']}, restored "
          f"{s['side_pieces_restored']}")
    print("    lamp faces replaced:", {k: r.replaced[v].tolist() for k, v in lamp.items()})
