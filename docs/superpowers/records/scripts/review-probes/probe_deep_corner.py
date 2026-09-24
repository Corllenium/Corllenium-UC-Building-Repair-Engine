"""Probe: a 2 in slab (top + three 2 in outward skirts, x = 0 edge open) whose corner (0,0,0) is
also the top corner of a 30 in retaining wall running outward in -x. `_edge_thickness` takes the
deepest side face at either endpoint, and the bottom goes at the shallowest OPEN-edge height."""
import numpy as np

from engine.fixes.pipeline import FixProfile, fix_object
from engine.tests.fixtures.build import _mesh, _quads

s, h, deep = 40.0, 2.0, 30.0
P = [[0, 0, 0], [s, 0, 0], [s, s, 0], [0, s, 0],
     [0, 0, -h], [s, 0, -h], [s, s, -h], [0, s, -h],
     [-10, 0, 0], [-10, 0, -deep], [0, 0, -deep]]            # 8-10: the retaining wall
uvs, fv, fvt, fm = [], [], [], []
_quads(P, uvs, fv, fvt, fm, [(0, 1, 2, 3),                    # top, +z
                             (0, 4, 5, 1), (1, 5, 6, 2), (2, 6, 7, 3),   # 2 in skirts, outward
                             (8, 9, 10, 0)])                  # the wall in y = 0, x from -10 to 0
m = _mesh("thin_slab_beside_a_deep_wall", P, uvs, fv, fvt, face_material=fm)
r = fix_object(m, {}, FixProfile(guard_size=(240, 160), n_dirs=32))
sr = r.solidify_report
print("thickness_per_region:", sr["thickness_per_region"], " bottom_depth_per_region:",
      sr["bottom_depth_per_region"])
print("skirts", sr["skirts_added"], " bottoms", sr["bottoms_added"], " cap_guard_removed",
      sr["cap_guard_removed"], " cap_guard_passed", sr["cap_guard_passed"])
used = r.mesh.positions[r.mesh.face_v]
in_slab = np.all((used[:, :, 0] >= -1e-9), axis=1)            # ignore the wall itself
print("passed:", r.passed, " lowest z of shipped faces over the slab footprint:",
      round(float(used[in_slab][:, :, 2].min()), 2), "(the slab is 2 in thick)")
