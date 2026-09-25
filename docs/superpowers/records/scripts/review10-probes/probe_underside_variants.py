"""Probe (review of brief 10, C2's fix 8c729c1): real UNDERSIDES that `_is_underside` still takes for
TOPS, so a bottom is invented under them and the hidden pass deletes them -- review part 2's C2,
surviving for undersides the test does not recognise.

Scene (inches, closed boxes wound outward) -- the review's own `overhang_beside_a_slab`:
  L  a closed slab: top z = 0 over x 0..40, y 0..40, bottom -8. Sees sky.
  B  a closed block overhanging open air beside it: x 40..80, y 0..40, z 0..H. Its underside U
     (faces 12, 13; z = 0, facing down) is flush with L's top, so L's x = 40 edge continues into it.
Variants:
  base    as the fixture (the regression test `test_an_underside_with_a_neighbours_side_along_it_
          is_not_taken_for_a_top`): U should ship whole.
  shaded  + a roof over B (a closed box x 40..80, y 0..40, z 30..34): B's top no longer sees sky.
          `_is_underside`'s ABOVE test counts only SKY-seeing surfaces above, so U fails it.
  tall    B is 60 in tall: its top is beyond `max_thickness + side_band` (52.5 in), so no ray up
          meets it within reach.
  fascia  + a 3 in fascia (one quad, x = 80, z -3..0, facing +x) hanging from U's free x = 80 edge:
          `_is_underside`'s BELOW test takes any own side hanging >= min_thickness (2 in) below a
          free edge for the slab's body.
  shaded+sign  the shaded scene with a sign hanging under the overhang (a closed box x 55..65,
          y 19..21, z -6..-1, m1; hung by wires, touching nothing).

For each: does U ship, what was invented under it, and what `passed` says.
"""
from common import (REAL, SMALL, _mesh, area_at, box, fate, fix_object, np, quad, shapely,
                    solidify_summary, where)

where()


def scene(variant):
    P, uvs, fv, fvt, fm = [], [], [], [], []
    H = 60.0 if variant == "tall" else 20.0
    box(P, uvs, fv, fvt, fm, 0, 40, 0, 40, -8, 0)                  # L: faces 0-11
    ids = box(P, uvs, fv, fvt, fm, 40, 80, 0, 40, 0, H)            # B: 12-23, U = 12, 13
    extra = {}
    if variant.startswith("shaded"):
        extra["roof"] = sum(box(P, uvs, fv, fvt, fm, 40, 80, 0, 40, 30, 34).values(), [])
    if variant == "fascia":
        extra["fascia"] = quad(P, uvs, fv, fvt, fm, [(80, 0, -3), (80, 40, -3), (80, 40, 0),
                                                      (80, 0, 0)])
    if variant.endswith("sign"):
        extra["sign"] = sum(box(P, uvs, fv, fvt, fm, 55, 65, 19, 21, -6, -1, material=1).values(),
                            [])
    m = _mesh(f"overhang_{variant}", P, uvs, fv, fvt, materials=("m0", "m1"), face_material=fm)
    return m, ids["bottom"], extra


beneath = shapely.box(40.0, 0.0, 80.0, 40.0)                     # B's footprint
for variant in ("base", "shaded", "tall", "fascia", "shaded+sign"):
    m, U, extra = scene(variant)
    for profile in (SMALL, REAL):
        r = fix_object(m, {}, profile)
        s = r.solidify_report
        ref = r.reference_mesh
        inv = np.arange(int((~r.replaced_input).sum()), ref.n_faces)
        under = inv[ref.positions[ref.face_v[inv]][:, :, 0].min(axis=1) >= 40 - 1e-9]
        zs = sorted({round(float(z), 3) for z in ref.positions[ref.face_v[under]][:, :, 2].ravel()})
        print(f"[{variant}] guard {profile.guard_size}: passed={r.passed}")
        print("   ", solidify_summary(r))
        print(f"    U (faces {U}): {fate(r, U)}; invented faces under B kept: {len(under)} "
              f"(z levels {zs})")
        print(f"    SHIPPED over B's footprint: area at z = 0 (U) {area_at(r.mesh, beneath, 0.0)}"
              f" | at z = -8 {area_at(r.mesh, beneath, -8.0)} | at z = -3 "
              f"{area_at(r.mesh, beneath, -3.0)}")
        for name, faces in extra.items():
            print(f"    {name}: {fate(r, faces)}")
