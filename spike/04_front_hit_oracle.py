"""Gate G3: 'scene of front-facing triangles only' + embree first hit  ==  brute-force culled first hit."""
import numpy as np
import trimesh
from trimesh.ray.ray_pyembree import RayMeshIntersector

from _common import FILES, SNAP, load_obj, save, tri_geometry, weld

N_DIRS, RAYS, CHUNK, DEPTH_TOL = 8, 2000, 256, 1e-3


def fib_dirs(n):
    i = np.arange(n) + 0.5
    phi = np.arccos(1 - 2 * i / n)
    th = np.pi * (1 + 5 ** 0.5) * i
    return np.stack([np.cos(th) * np.sin(phi), np.sin(th) * np.sin(phi), np.cos(phi)], axis=1)


def brute(o, d, T):
    """Nearest hit distance per ray (inf = miss). o (R,3), d (3,), T (M,3,3). float64 Moller-Trumbore."""
    e1, e2 = T[:, 1] - T[:, 0], T[:, 2] - T[:, 0]
    h = np.cross(d, e2)
    a = np.einsum("ij,ij->i", e1, h)
    good = np.abs(a) > 1e-12
    inv = np.where(good, 1.0 / np.where(good, a, 1.0), 0.0)
    best = np.full(len(o), np.inf)
    for s in range(0, len(o), CHUNK):
        oc = o[s:s + CHUNK]
        sv = oc[:, None, :] - T[None, :, 0, :]
        u = np.einsum("rmk,mk->rm", sv, h) * inv
        q = np.cross(sv, e1[None, :, :])
        v = (q @ d) * inv
        t = np.einsum("rmk,mk->rm", q, e2) * inv
        hit = good[None, :] & (u >= 0) & (v >= 0) & (u + v <= 1) & (t > 1e-9)
        best[s:s + CHUNK] = np.where(hit, t, np.inf).min(axis=1)
    return best


def run(name):
    m = load_obj(SNAP / name)
    P, fw = weld(m)
    _, normals, _, degenerate = tri_geometry(P, fw)
    ok = ~degenerate
    Pc = P - (P.min(axis=0) + P.max(axis=0)) / 2
    lo, hi = Pc.min(axis=0), Pc.max(axis=0)
    diag = float(np.linalg.norm(hi - lo))
    rng = np.random.default_rng(7)
    rays = both = miss_disagree = depth_disagree = 0
    worst = 0.0
    for d in fib_dirs(N_DIRS):
        front = np.nonzero(ok & (normals @ d < -1e-6))[0]
        o = rng.uniform(lo, hi, size=(RAYS, 3)) - d * diag * 2
        rmi = RayMeshIntersector(trimesh.Trimesh(vertices=Pc.astype(np.float32), faces=fw[front], process=False))
        loc, iray, _ = rmi.intersects_location(o, np.tile(d, (RAYS, 1)), multiple_hits=False)
        t_e = np.full(RAYS, np.inf)
        t_e[iray] = (loc - o[iray]) @ d
        t_b = brute(o, d, Pc[fw[front]])
        he, hb = np.isfinite(t_e), np.isfinite(t_b)
        rays += RAYS
        miss_disagree += int((he != hb).sum())
        b = he & hb
        both += int(b.sum())
        diff = np.abs(t_e[b] - t_b[b])
        depth_disagree += int((diff > DEPTH_TOL).sum())
        if diff.size:
            worst = max(worst, float(diff.max()))
    return {"rays": rays, "both_hit": both,
            "hit_miss_disagreements": miss_disagree,
            "hit_miss_disagreement_pct": round(100 * miss_disagree / rays, 4),
            "depth_disagreements_over_1e-3_in": depth_disagree,
            "depth_disagreement_pct": round(100 * depth_disagree / max(both, 1), 4),
            "worst_depth_diff_in": worst}


out = {name: run(name) for name in FILES}
out["gate_G3"] = bool(all(r["hit_miss_disagreement_pct"] <= 0.1 and r["depth_disagreement_pct"] <= 0.1
                          for r in out.values() if isinstance(r, dict)))
save("front_hit_oracle", out)
for k, v in out.items():
    print(k, "=>", v)
