"""Probe: S-C1's scenario with the real underside wound the other way (its normal into the slab,
the 'purple' side seen from below). Rule 2 of the cap guard allows covering any back-side hit."""
import numpy as np

from engine.fixes.pipeline import FixProfile, fix_object
from engine.fixes.solidify import solidify
from engine.pipeline import analyse_topology
from engine.tests.fixtures.build import slab_with_partial_underside
from engine.topo.weld import weld_exact
from engine.vis.exposure import compute_side_exposure

FAST = FixProfile(guard_size=(120, 80), n_dirs=32)


def front_back(mesh, n_dirs=32):
    positions_w, remap = weld_exact(mesh.positions, mesh.coord_decimals)
    face_w = remap[mesh.face_v]
    c = (positions_w.min(0) + positions_w.max(0)) / 2
    return compute_side_exposure(positions_w - c, face_w, np.ones(len(face_w), bool), n_dirs=n_dirs)


for label, reverse in (("as committed (underside wound -z)", False),
                       ("underside REVERSED (wound +z)", True)):
    m = slab_with_partial_underside()
    if reverse:
        m.face_v[8:10] = m.face_v[8:10][:, ::-1].copy()
        m.face_vt[8:10] = m.face_vt[8:10][:, ::-1].copy()
    f0, b0 = front_back(m)
    r = solidify(m, analyse_topology(m), FAST)
    f1, b1 = front_back(r.mesh)
    res = fix_object(m, {}, FAST)
    print(f"--- {label}")
    print(f"  original exposure faces 8,9: front {f0[8]:.3f},{f0[9]:.3f} back {b0[8]:.3f},{b0[9]:.3f}")
    print(f"  bottoms_added {r.report['bottoms_added']}  cap_guard_removed {r.report['cap_guard_removed']}"
          f"  cap_guard_passed {r.report['cap_guard_passed']}")
    print(f"  solidified exposure faces 8,9: front {f1[8]:.3f},{f1[9]:.3f} back {b1[8]:.3f},{b1[9]:.3f}")
    print(f"  fix_object: removed_hidden[8,9] = {bool(res.removed_hidden[8])},{bool(res.removed_hidden[9])}"
          f"  passed={res.passed}  guard_final holes={res.guard_final.totals['holes']}"
          f" moved={res.guard_final.totals['moved_same_flat'] + res.guard_final.totals['moved_other']}")
    zs = sorted({round(float(z), 3) for z in res.mesh.positions[res.mesh.face_v].reshape(-1, 3)[:, 2]})
    print(f"  z levels used by the shipped faces: {zs}")
