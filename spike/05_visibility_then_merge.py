"""Hypothesis 4: interior partitions are what keeps file A from reducing.

Step 1  oriented visibility under Unity culling (back faces neither render nor block):
        for a direction w, blockers are only triangles with n.w > 0. A face is front-visible from w
        when a ray from its front side along w hits no blocker.
Step 2  merge floor on front-visible faces only: plane + material regions, UV ignored,
        ring vertices kept only where some region needs them as a corner.
"""
import importlib.util
from pathlib import Path

import numpy as np
import shapely
import trimesh
from trimesh.ray.ray_pyembree import RayMeshIntersector

from _common import FILES, SNAP, load_obj, save, tri_geometry, weld

spec = importlib.util.spec_from_file_location("r", Path(__file__).with_name("_region.py"))
R = importlib.util.module_from_spec(spec)
spec.loader.exec_module(R)

N_DIRS = 96
EPS = 0.02  # inches, push off the surface
BARY = np.array([[1 / 3, 1 / 3, 1 / 3], [0.6, 0.2, 0.2], [0.2, 0.6, 0.2], [0.2, 0.2, 0.6]])


def fib_dirs(n):
    i = np.arange(n) + 0.5
    phi = np.arccos(1 - 2 * i / n)
    th = np.pi * (1 + 5 ** 0.5) * i
    return np.stack([np.cos(th) * np.sin(phi), np.sin(th) * np.sin(phi), np.cos(phi)], axis=1)


def front_visible_counts(Pc, fw, normals, ok):
    """Returns per-face number of (sample, direction) rays that escape."""
    tri = Pc[fw]
    escapes = np.zeros(len(fw), np.int64)
    P32 = Pc.astype(np.float32)
    for w in fib_dirs(N_DIRS):
        facing = ok & (normals @ w > 1e-6)
        ids = np.nonzero(facing)[0]
        if len(ids) == 0:
            continue
        scene = trimesh.Trimesh(vertices=P32, faces=fw[ids], process=False)
        rmi = RayMeshIntersector(scene)
        pts = np.einsum("sb,fbk->fsk", BARY, tri[ids]) + EPS * normals[ids][:, None, :]
        o = pts.reshape(-1, 3)
        d = np.tile(w, (len(o), 1))
        hit = rmi.intersects_any(o, d)
        escapes[ids] += (~hit).reshape(len(ids), len(BARY)).sum(axis=1)
    return escapes


def ring_ids(coords, verts2d, ids):
    d = np.linalg.norm(coords[:, None, :] - verts2d[None, :, :], axis=2)
    return ids[d.argmin(axis=1)]


def corner_mask(coords, tol):
    a, b, c = np.roll(coords, 1, axis=0), coords, np.roll(coords, -1, axis=0)
    ac = c - a
    L = np.linalg.norm(ac, axis=1)
    cross = np.abs(ac[:, 0] * (b - a)[:, 1] - ac[:, 1] * (b - a)[:, 0])
    dist = np.where(L > 1e-12, cross / np.maximum(L, 1e-12), np.linalg.norm(b - a, axis=1))
    t = np.einsum("ij,ij->i", b - a, ac) / np.maximum(L ** 2, 1e-24)
    return (dist > tol) | (t < 0) | (t > 1)


def merge_floor(tri, fw, normals, area, mat, keep, quanta):
    plabel, planes = R.cluster_planes(tri, normals, area, mat, keep, quanta)
    rings = []
    for pi, (n, p0, _tol) in enumerate(planes):
        members = np.nonzero(plabel == pi)[0]
        e1, e2 = R.plane_basis(n)
        xy = np.stack([(tri[members] - p0) @ e1, (tri[members] - p0) @ e2], axis=2)
        ids = fw[members].reshape(-1)
        u = shapely.union_all(shapely.polygons(np.concatenate([xy, xy[:, :1]], axis=1)), grid_size=R.GRID)
        v2 = xy.reshape(-1, 2)
        for poly in R.pieces(u):
            for k, ring in enumerate([poly.exterior, *poly.interiors]):
                c = np.asarray(ring.coords)[:-1]
                rings.append((ring_ids(c, v2, ids), c, len(poly.interiors) if k == 0 else 0, k == 0))
    tol = 1.5 * float(quanta.max())
    needed = set()
    for rid, c, _, _ in rings:
        needed.update(rid[corner_mask(c, tol)].tolist())
    needed = np.fromiter(needed, np.int64) if needed else np.zeros(0, np.int64)
    total = 0
    for rid, _, h, ext in rings:
        kept = max(3, int(np.isin(rid, needed).sum()))
        total += kept + 2 * h - 2 if ext else kept
    return total, len(planes), len(rings)


def run(name):
    path = SNAP / name
    m = load_obj(path)
    P, fw = weld(m)
    area, normals, _, degenerate = tri_geometry(P, fw)
    ok = ~degenerate
    _, quanta = R.axis_quanta(path, P)
    Pc = P - (P.min(axis=0) + P.max(axis=0)) / 2
    escapes = front_visible_counts(Pc, fw, normals, ok)
    visible = ok & (escapes > 0)
    never = ok & (escapes == 0)
    barely = ok & (escapes > 0) & (escapes <= 2)

    tri = P[fw]
    all_after, _, all_rings = merge_floor(tri, fw, normals, area, m["fm"], ok, quanta)
    vis_after, vis_planes, vis_rings = merge_floor(tri, fw, normals, area, m["fm"], visible, quanta)
    n_ok = int(ok.sum())
    return {
        "rays_cast": int(N_DIRS * len(BARY) * n_ok / 2),
        "tris_nondegenerate": n_ok,
        "never_visible_tris": int(never.sum()),
        "never_visible_pct": round(100 * never.sum() / n_ok, 2),
        "never_visible_area_pct": round(100 * area[never].sum() / area[ok].sum(), 2),
        "barely_visible_tris_1_or_2_rays": int(barely.sum()),
        "front_visible_tris": int(visible.sum()),
        "merge_only": {"tris_after": all_after, "rings": all_rings,
                       "reduction_pct": round(100 * (1 - all_after / n_ok), 2)},
        "interior_removed_then_merge": {"tris_after": vis_after, "planes": vis_planes, "rings": vis_rings,
                                        "reduction_pct": round(100 * (1 - vis_after / n_ok), 2)},
    }


out = {name: run(name) for name in FILES}
save("visibility_then_merge", out)
for name, r in out.items():
    print("==", name)
    for k, v in r.items():
        print(f"  {k}: {v}")
