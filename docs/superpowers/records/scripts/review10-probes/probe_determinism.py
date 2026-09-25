"""Determinism at dc24e9a on the paths brief 10 added: rule 6 and the same-round re-cast
(`slab_beside_a_lower_top`, the shaded overhang with a post), the block standing on a slab
(`slab_with_a_block_standing_on_it(at_edge=True)`), a piece given back (`slab_with_a_deep_tooth_
in_its_side`). Each scene runs twice through `fix_object` (default 900 x 600 profile) in ONE
process and once more in a second process (run this script twice and compare the lines); the
shipped mesh (faces, materials, positions) and the solidify / fragment / fold reports (json,
sorted keys, runtime removed) are hashed.
"""
import hashlib
import json

from common import REAL, _mesh, box, fix_object, np, where
from engine.tests.fixtures.build import (slab_beside_a_lower_top, slab_with_a_block_standing_on_it,
                                         slab_with_a_deep_tooth_in_its_side)

where()


def shaded_overhang_with_post():
    P, uvs, fv, fvt, fm = [], [], [], [], []
    box(P, uvs, fv, fvt, fm, 0, 40, 0, 40, -8, 0)
    box(P, uvs, fv, fvt, fm, 40, 80, 0, 40, 0, 20)
    box(P, uvs, fv, fvt, fm, 40, 80, 0, 40, 30, 34)
    box(P, uvs, fv, fvt, fm, 50, 70, 50, 51, -6, -2, material=1)
    return _mesh("shaded_overhang_with_post", P, uvs, fv, fvt, materials=("m0", "m1"),
                 face_material=fm)


scenes = {"slab_beside_a_lower_top": slab_beside_a_lower_top(),
          "shaded overhang + post": shaded_overhang_with_post(),
          "block at the slab's edge": slab_with_a_block_standing_on_it(at_edge=True),
          "deep tooth (m1)": slab_with_a_deep_tooth_in_its_side(1)}


def digest(r):
    def clean(d):
        return {k: v for k, v in d.items() if k != "runtime_s"}
    blob = json.dumps({"solidify": clean(r.solidify_report), "fragments": r.fragment_report,
                       "folds": r.fold_report, "passed": r.passed}, sort_keys=True, default=str)
    h = hashlib.sha256(blob.encode())
    h.update(np.ascontiguousarray(r.mesh.face_v).tobytes())
    h.update(np.ascontiguousarray(r.mesh.face_material).tobytes())
    h.update(np.ascontiguousarray(r.mesh.positions).tobytes())
    return h.hexdigest()[:16]


for name, m in scenes.items():
    d = [digest(fix_object(m, {}, REAL)) for _ in range(2)]
    print(f"{name}: {d[0]} {d[1]} {'identical' if d[0] == d[1] else 'DIFFERENT'}")
