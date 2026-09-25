"""Probe (review of brief 10, item 1 / 9f64ae9): rule 6 takes away the one check the cap guard had on
a WRONG slab volume -- something seen from outside through the space the plan closes.

Scene: `probe_underside_variants.py`'s "shaded" overhang (L a closed slab at z -8..0; B a closed
block x 40..80, z 0..20, overhanging open air, its underside U flush with L's top; a roof over B),
which `_is_underside` takes for a top, plus a POST beyond the overhang: a closed box x 50..70,
y 50..51, z -6..-2 (m1), outside every slab. From -y a person looks under the overhang, through
the open air below U, and sees the post.

The plan walls U's free edges 8 in down and puts a bottom 8 in below it (the space under a real
overhang). Every wall pixel that covers the post is judged:
  rule 6 OFF  (dc24e9a with `_through_closed_shell` returning False: the guard as it was before
              9f64ae9, for this scene) -- the post lies outside every volume, the walls covering it
              are refused, and the overhang's underside stays visible;
  rule 6 ON   (dc24e9a as committed) -- the ray enters the y = 0 wall from outside, runs under U
              inside the planned volume and leaves through the y = 40 wall: "seen through a closed
              slab", allowed.
"""
from common import (REAL, SMALL, _mesh, area_at, box, fate, fix_object, rule6_off, shapely,
                    solidify_summary, where)

where()


def scene():
    P, uvs, fv, fvt, fm = [], [], [], [], []
    box(P, uvs, fv, fvt, fm, 0, 40, 0, 40, -8, 0)                  # L: faces 0-11
    ids = box(P, uvs, fv, fvt, fm, 40, 80, 0, 40, 0, 20)           # B: 12-23, U = 12, 13
    box(P, uvs, fv, fvt, fm, 40, 80, 0, 40, 30, 34)                # the roof: 24-35
    post = sum(box(P, uvs, fv, fvt, fm, 50, 70, 50, 51, -6, -2, material=1).values(), [])
    return (_mesh("overhang_shaded_with_a_post", P, uvs, fv, fvt, materials=("m0", "m1"),
                  face_material=fm), ids["bottom"], post)


m, U, post = scene()
beneath = shapely.box(40.0, 0.0, 80.0, 40.0)
for profile in (SMALL, REAL):
    for label in ("rule 6 OFF", "rule 6 ON"):
        if label == "rule 6 OFF":
            with rule6_off():
                r = fix_object(m, {}, profile)
        else:
            r = fix_object(m, {}, profile)
        print(f"[{label}] guard {profile.guard_size}: passed={r.passed}")
        print("   ", solidify_summary(r))
        print(f"    U: {fate(r, U)} | post: {sorted(set(fate(r, post)))}")
        print(f"    SHIPPED over B's footprint: z = 0 (U) {area_at(r.mesh, beneath, 0.0)}"
              f" | z = -8 (invented) {area_at(r.mesh, beneath, -8.0)}")
