"""E4: a legitimate merge drops a border vertex 0.1 in (one print step) off a straight edge -- the
plate's unique max-x vertex. Does the M2 invariant now fail a run the guard passes?"""
import numpy as np
from engine.fixes.pipeline import FixProfile, fix_object
from engine.tests.fixtures.build import _mesh

def plate(jitter, closed):
    P = [[20, 20, 0], [0, 0, 0], [40, 0, 0], [40 + jitter, 20, 0], [40, 40, 0], [0, 40, 0]]
    fv = [[0, 1, 2], [0, 2, 3], [0, 3, 4], [0, 4, 5], [0, 5, 1]]
    if closed:   # a closed 8 in slab under it: sides and bottom follow the same outline
        base = len(P)
        P += [[p[0], p[1], -8.0] for p in P[1:]]
        ring = [1, 2, 3, 4, 5]
        for i in range(5):
            a, b = ring[i], ring[(i + 1) % 5]
            fv += [[a, base + a - 1, base + b - 1], [a, base + b - 1, b]]
        fv += [[base + 0, base + 4, base + 3], [base + 0, base + 3, base + 2], [base + 0, base + 2, base + 1]]
    P = np.asarray(P, float)
    uvs = (P[np.asarray(fv).reshape(-1)][:, :2] * 0.05).tolist()
    fvt = np.arange(len(fv) * 3).reshape(-1, 3).tolist()
    return _mesh(f"plate_j{jitter}", P, uvs, fv, fvt, coord_decimals=1, sig_digits=3)

for closed in (False, True):
    for jitter in (0.0, 0.1):
        m = plate(jitter, closed)
        r = fix_object(m, {}, FixProfile(guard_size=(240, 160), n_dirs=32, solidify=False))
        used = np.unique(r.mesh.face_v)
        g = r.guard_final.totals
        print(f"closed={closed} jitter={jitter}: faces {m.n_faces}->{r.mesh.n_faces}, vertex 3 used={3 in used}, "
              f"used max x={r.mesh.positions[used][:, 0].max():.2f}, bbox_same={r.invariants['bbox_same']}, "
              f"guard_passed={r.invariants['guard_passed']}, passed={r.passed}, "
              f"border_shift={g['border_shift']}, rolled_back={r.merge_report.get('rolled_back', False)}, "
              f"dropped={r.merge_report.get('vertices_dropped')}")
