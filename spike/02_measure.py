"""Re-measure the snapshot. Compare against the previous-export numbers in the spec."""
import numpy as np

from _common import FILES, SNAP, load_obj, save, tri_geometry, weld


def same_winding(a, b):
    a, b = list(a), list(b)
    i = b.index(a[0])
    return b[(i + 1) % 3] == a[1]


def measure(name):
    m = load_obj(SNAP / name)
    P, fw = weld(m)
    area, n, longest, degenerate = tri_geometry(P, fw)

    pairs = np.sort(np.stack([fw[:, [0, 1]], fw[:, [1, 2]], fw[:, [2, 0]]], axis=1).reshape(-1, 2), axis=1)
    _, cnt = np.unique(pairs, axis=0, return_counts=True)

    distinct = (fw[:, 0] != fw[:, 1]) & (fw[:, 1] != fw[:, 2]) & (fw[:, 0] != fw[:, 2])
    idx = np.nonzero(distinct)[0]
    key = np.sort(fw[idx], axis=1)
    _, inv, kcnt = np.unique(key, axis=0, return_inverse=True, return_counts=True)
    inv = inv.reshape(-1)
    dup_same = dup_opp = dup_mat_differs = 0
    for g in np.nonzero(kcnt > 1)[0]:
        members = idx[inv == g]
        for other in members[1:]:
            if same_winding(fw[members[0]], fw[other]):
                dup_same += 1
            else:
                dup_opp += 1
            if m["fm"][members[0]] != m["fm"][other]:
                dup_mat_differs += 1

    lo, hi = m["v"].min(axis=0), m["v"].max(axis=0)
    return {
        "v": int(len(m["v"])), "vt": int(len(m["vt"])), "vn": int(len(m["vn"])), "tris": int(len(fw)),
        "materials": m["mats"],
        "printed_decimals": m["decimals"], "coord_quantum_in": 10.0 ** -m["decimals"],
        "unique_positions": int(len(P)),
        "zero_area_tris": int(degenerate.sum()),
        "edge_valence": {"1": int((cnt == 1).sum()), "2": int((cnt == 2).sum()),
                         "3": int((cnt == 3).sum()), "4+": int((cnt >= 4).sum())},
        "duplicate_faces_same_winding": dup_same,
        "duplicate_faces_opposite_winding": dup_opp,
        "duplicate_pairs_material_differs": dup_mat_differs,
        "faces_without_uv": int((m["fvt"] < 0).any(axis=1).sum()),
        "bbox_in": [lo.round(2).tolist(), hi.round(2).tolist()],
        "size_m": ((hi - lo) * 0.0254).round(2).tolist(),
        "largest_tri_area_in2": float(area.max()),
    }


out = {name: measure(name) for name in FILES}
save("measure", out)
for name, r in out.items():
    print("==", name)
    for k, v in r.items():
        print(f"  {k}: {v}")
