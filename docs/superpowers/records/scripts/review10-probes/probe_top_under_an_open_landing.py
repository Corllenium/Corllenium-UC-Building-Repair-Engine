"""Probe (review of brief 10, 8c729c1): a REAL TOP taken for an underside when the slab above it has no
underside of its own -- review part 2's M2 again, whenever the landing is as open as the files'.

Scene: the regression fixture `real_top_under_a_landing` (one slab whose top is two regions at
z = 0 -- L x 0..40 sees sky, R x 40..80 lies under a landing -- L skirted 10 in on x = 0, y = 0,
y = 40, R's two sides open, no bottom anywhere, R's only own side a riser up to the landing), with
ONE change: the landing (x 40..80, z 10..20) has NO underside -- the export's usual state ("a top
sheet with partial skirts and almost no bottom", solidify's module docstring).

`_is_underside`'s ABOVE test looks for a SKY-seeing surface within max_thickness + side_band
straight above; through the landing's missing underside the rays meet the landing's TOP from
inside, 20 in up. The fixture's test (`test_a_floor_under_a_landing_with_its_sides_missing_is_a_
top`) only has the landing closed.
"""
from common import (SMALL, _mesh, area_at, fix_object, np, shapely, solidify_summary, where)
from engine.tests.fixtures.build import _quads

where()


def scene(open_landing):
    P, uvs, fv, fvt, fm = [], [], [], [], []

    def v(x, y, z):
        P.append([float(x), float(y), float(z)])
        return len(P) - 1

    a = [v(0, 0, 0), v(40, 0, 0), v(40, 40, 0), v(0, 40, 0)]
    _quads(P, uvs, fv, fvt, fm, [tuple(a)], material=0)                       # L's top, +z
    b = [a[1], v(80, 0, 0), v(80, 40, 0), a[2]]
    _quads(P, uvs, fv, fvt, fm, [tuple(b)], material=1)                       # R's top, +z
    lo = [v(0, 0, -10), v(40, 0, -10), v(40, 40, -10), v(0, 40, -10)]
    _quads(P, uvs, fv, fvt, fm, [(lo[3], lo[0], a[0], a[3]), (lo[0], lo[1], a[1], a[0]),
                                 (lo[2], lo[3], a[3], a[2])], material=0)     # L's skirts
    r_top = [v(80, 0, 10), v(80, 40, 10)]
    _quads(P, uvs, fv, fvt, fm, [(b[1], b[2], r_top[1], r_top[0])], material=0)   # riser, +x
    t = [v(40, 0, 20), v(80, 0, 20), v(80, 40, 20), v(40, 40, 20)]
    u = [v(40, 0, 10), v(80, 0, 10), v(80, 40, 10), v(40, 40, 10)]
    loops = [(t[0], t[1], t[2], t[3])]
    if not open_landing:
        loops.append((u[0], u[3], u[2], u[1]))                                # its underside
    loops += [(u[0], u[1], t[1], t[0]), (u[2], u[3], t[3], t[2]),
              (u[3], u[0], t[0], t[3]), (u[1], u[2], t[2], t[1])]
    _quads(P, uvs, fv, fvt, fm, loops, material=0)                            # the landing
    return _mesh("top_under_a_landing", P, uvs, fv, fvt, materials=("m0", "m1"),
                 face_material=fm)


under_r = shapely.box(40.0, 0.0, 80.0, 40.0)
for open_landing in (False, True):
    m = scene(open_landing)
    r = fix_object(m, {}, SMALL)
    ref = r.reference_mesh
    n_in = int((~r.replaced_input).sum())
    inv = ref.positions[ref.face_v[n_in:]]
    inside_wall = [t for t in inv if np.allclose(t[:, 0], 40.0) and np.ptp(t[:, 2]) > 1e-6]
    under = [t for t in inv if t[:, 0].min() >= 40.0 - 1e-9]
    print(f"[landing {'OPEN below' if open_landing else 'closed (the fixture)'}] "
          f"passed={r.passed}")
    print("   ", solidify_summary(r))
    print(f"    invented faces under R: {len(under)}; walls at x = 40 (inside the slab): "
          f"{len(inside_wall)}")
    print(f"    SHIPPED under R: bottom area at z = -10: {area_at(r.mesh, under_r, -10.0)} "
          f"(of 1600); under L: {area_at(r.mesh, shapely.box(0, 0, 40, 40), -10.0)}")
