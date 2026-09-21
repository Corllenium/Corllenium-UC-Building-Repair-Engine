"""Why did G2 fail? Attribute the lost reduction to each stage, one variable at a time.

A polygon with n ring vertices and h holes triangulates into exactly n + 2h - 2 triangles.
So triangle count is decided by how many ring vertices survive, not by the interior grid.

Variables:
  uv      : respect UV classes (True) or merge by plane + material only (False)
  border  : 'all'    keep every ring vertex (what 03 did)
            'strict' drop ring vertices that are EXACTLY collinear in every region that uses them
            'loose'  same, collinear within 1.5 x coarsest quantum
"""
import importlib.util
from pathlib import Path

import numpy as np
import shapely

from _common import FILES, SNAP, load_obj, save, tri_geometry, weld

spec = importlib.util.spec_from_file_location("r", Path(__file__).with_name("_region.py"))
R = importlib.util.module_from_spec(spec)
spec.loader.exec_module(R)


def ring_ids(coords, verts2d, ids):
    d = np.linalg.norm(coords[:, None, :] - verts2d[None, :, :], axis=2)
    j = d.argmin(axis=1)
    return ids[j], d.min(axis=1)


def corner_mask(coords, tol):
    a, b, c = np.roll(coords, 1, axis=0), coords, np.roll(coords, -1, axis=0)
    ac = c - a
    L = np.linalg.norm(ac, axis=1)
    cross = np.abs(ac[:, 0] * (b - a)[:, 1] - ac[:, 1] * (b - a)[:, 0])
    dist = np.where(L > 1e-12, cross / np.maximum(L, 1e-12), np.linalg.norm(b - a, axis=1))
    # also a corner when the path doubles back (b outside segment a-c)
    t = np.einsum("ij,ij->i", b - a, ac) / np.maximum(L ** 2, 1e-24)
    return (dist > tol) | (t < 0) | (t > 1)


def analyse(name, use_uv, flag=True):
    path = SNAP / name
    m = load_obj(path)
    P, fw = weld(m)
    area, normals, _, degenerate = tri_geometry(P, fw)
    ok = ~degenerate
    _, quanta = R.axis_quanta(path, P)
    tri = P[fw]
    uv_all = m["vt"][m["fvt"]]
    plabel, planes = R.cluster_planes(tri, normals, area, m["fm"], ok, quanta)

    rings = []          # (vertex ids, coords2d, n_holes_of_its_polygon, is_exterior)
    flagged_tris = 0
    flagged_vertices = set()
    max_snap = 0.0
    for pi, (n, p0, _tol) in enumerate(planes):
        members = np.nonzero(plabel == pi)[0]
        e1, e2 = R.plane_basis(n)
        xy = np.stack([(tri[members] - p0) @ e1, (tri[members] - p0) @ e2], axis=2)
        if use_uv:
            ulabel, fits = R.cluster_uv(xy, uv_all[members], area[members])
            groups = [ulabel == ui for ui in range(len(fits))]
        else:
            groups = [np.ones(len(members), bool)]
        for sel in groups:
            X = xy[sel]
            ids = fw[members[sel]].reshape(-1)
            polys = shapely.polygons(np.concatenate([X, X[:, :1]], axis=1))
            sum_area = float(shapely.area(polys).sum())
            u = shapely.union_all(polys, grid_size=R.GRID)
            if flag and sum_area - u.area > 1e-6 * sum_area + 1e-9:
                flagged_tris += int(sel.sum())
                flagged_vertices.update(ids.tolist())
                continue
            v2 = X.reshape(-1, 2)
            for poly in R.pieces(u):
                for k, ring in enumerate([poly.exterior, *poly.interiors]):
                    c = np.asarray(ring.coords)[:-1]
                    rid, snap = ring_ids(c, v2, ids)
                    max_snap = max(max_snap, float(snap.max()))
                    rings.append((rid, c, len(poly.interiors) if k == 0 else 0, k == 0))

    def count(tol):
        if tol is None:
            return flagged_tris + sum(len(rid) + 2 * h - 2 if ext else len(rid) for rid, _, h, ext in rings)
        needed = set(flagged_vertices)
        for rid, c, _, _ in rings:
            needed.update(rid[corner_mask(c, tol)].tolist())
        total = flagged_tris
        for rid, _, h, ext in rings:
            kept = max(3, int(np.isin(rid, list(needed)).sum()))
            total += kept + 2 * h - 2 if ext else kept
        return total

    n_ok = int(ok.sum())
    loose = 1.5 * float(quanta.max())
    res = {
        "tris_before_nondegenerate": n_ok,
        "tris_in_flagged_overlap_clusters": flagged_tris,
        "rings": len(rings),
        "max_ring_vertex_snap_in": max_snap,
    }
    for label, tol in (("border_all", None), ("border_strict", 1e-6), ("border_loose", loose)):
        t = count(tol)
        res[label] = {"tris_after": t, "reduction_pct": round(100 * (1 - t / n_ok), 2)}
    return res


out = {}
for name in FILES:
    out[name] = {"uv_ignored_no_plane_flag": analyse(name, False, flag=False),
                 "uv_respected_no_class_flag": analyse(name, True, flag=False)}
save("region_diagnose_h3", out)
for name, r in out.items():
    print("==", name)
    for mode, vals in r.items():
        print("  --", mode)
        for k, v in vals.items():
            print(f"     {k}: {v}")
