"""Probe: N3's region 38 in miniature. A closed-sided slab whose x = 0 side EXISTS but is split at
the midpoint of its top edge, so the top's outline edge 0-3 is used by the top triangle alone
(edge-table count 1). Does solidify hang a skirt over the existing side (a coplanar duplicate),
does the cap guard see it, and does it ship?"""
import numpy as np

from engine.fixes.pipeline import FixProfile, fix_object
from engine.fixes.solidify import solidify
from engine.pipeline import analyse_topology
from engine.tests.fixtures.build import _mesh, _quads

s, h = 40.0, 8.0
P = [[0, 0, 0], [s, 0, 0], [s, s, 0], [0, s, 0],                  # 0-3 top corners
     [0, 0, -h], [s, 0, -h], [s, s, -h], [0, s, -h],              # 4-7 bottom corners
     [0, s / 2, 0], [0, s / 2, -h]]                                # 8-9 the x = 0 side's midline
uvs, fv, fvt, fm = [], [], [], []
_quads(P, uvs, fv, fvt, fm, [(0, 1, 2, 3),                        # top, +z
                             (0, 4, 5, 1), (1, 5, 6, 2), (2, 6, 7, 3),   # three skirts, outward
                             (0, 8, 9, 4), (8, 3, 7, 9),           # the x = 0 side, in two halves
                             (4, 7, 6, 5)])                        # bottom, -z
for reverse_side in (False, True):
    fvv = [list(f) for f in fv]
    if reverse_side:                                               # the x = 0 side wound inward
        for k in (8, 9, 10, 11):
            fvv[k] = fvv[k][::-1]
    m = _mesh("closed_slab_with_split_side", P, uvs, fvv, fvt, face_material=fm)
    prof = FixProfile(guard_size=(240, 160), n_dirs=32)
    r = solidify(m, analyse_topology(m), prof)
    new = np.nonzero(r.new_faces)[0]
    tri = r.mesh.positions[r.mesh.face_v[new]]
    on_x0 = [int(f) for f, t in zip(new, tri) if np.allclose(t[:, 0], 0.0)]
    res = fix_object(m, {}, prof)
    final = res.mesh.positions[res.mesh.face_v]
    x0_faces = int(np.all(np.isclose(final[:, :, 0], 0.0), axis=1).sum())
    area_x0 = float(sum(0.5 * np.linalg.norm(np.cross(t[1] - t[0], t[2] - t[0]))
                        for t in final if np.allclose(t[:, 0], 0.0)))
    print(f"--- x = 0 side wound {'INWARD' if reverse_side else 'outward'}")
    print(f"  solidify: skirts {r.report['skirts_added']}, new faces kept {len(new)} "
          f"(on x = 0: {len(on_x0)}), cap_guard_removed {r.report['cap_guard_removed']}")
    print(f"  fix_object: passed {res.passed}, removed_overlap {res.n_removed_overlap}, "
          f"shipped faces on x = 0: {x0_faces}, their area {area_x0:.1f} sq in "
          f"(the side itself is {s * h:.0f})")
