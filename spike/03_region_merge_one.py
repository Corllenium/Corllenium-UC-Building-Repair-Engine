"""Gate G2: planar region merge. Is it worth building, and is it safe.

Vertices are never moved. A region is re-triangulated over its EXISTING vertices only.
"""
import math

import numpy as np
import shapely

from _common import FILES, OUT, SNAP, load_obj, save, tri_geometry, weld

UV_TOL = 0.02
FACING_DOT = 0.9
DIST_TOL_QUANTA = 1.5
MAX_REFIT = 6
GRID = 1e-4


def axis_quanta(path, P):
    """SketchUp prints N significant digits, so the coordinate step depends on magnitude."""
    sig = 0
    for line in open(path, encoding="utf-8", errors="replace"):
        if line.startswith("v "):
            for tok in line.split()[1:4]:
                digits = tok.lstrip("-").replace(".", "").lstrip("0")
                sig = max(sig, len(digits))
    max_abs = np.abs(P).max(axis=0)
    q = np.array([10.0 ** (math.ceil(math.log10(max(a, 1e-9))) - sig) for a in max_abs])
    return sig, q


def plane_basis(n):
    a = np.array([1.0, 0.0, 0.0]) if abs(n[0]) < 0.9 else np.array([0.0, 1.0, 0.0])
    e1 = np.cross(n, a)
    e1 /= np.linalg.norm(e1)
    return e1, np.cross(n, e1)


def cluster_planes(tri, normals, area, mat, ok, quanta):
    label = np.full(len(tri), -1)
    planes = []
    for s in np.argsort(-area):
        if not ok[s] or label[s] != -1:
            continue
        n, p0 = normals[s], tri[s, 0]
        tol = DIST_TOL_QUANTA * float(np.abs(n) @ quanta)
        cand = ok & (label == -1) & (mat == mat[s]) & (normals @ n > FACING_DOT)
        cand &= np.abs((tri - p0) @ n).max(axis=1) <= tol
        label[cand] = len(planes)
        planes.append((n, p0, tol))
    return label, planes


def fit_uv(xy, uv):
    A = np.column_stack([xy, np.ones(len(xy))])
    coef, *_ = np.linalg.lstsq(A, uv, rcond=None)
    return coef[:2].T, coef[2]


def cluster_uv(xy, uv, area):
    """xy, uv: (k,3,2). Greedy seeds by area, iterative least-squares refit."""
    k = len(xy)
    label = np.full(k, -1)
    fits = []
    for s in np.argsort(-area):
        if label[s] != -1:
            continue
        J, o = fit_uv(xy[s], uv[s])
        member = np.zeros(k, bool)
        member[s] = True
        kk = np.zeros_like(uv)
        for _ in range(MAX_REFIT):
            r = uv - (xy @ J.T + o)
            kk = np.round(r)
            same_k = (kk == kk[:, :1, :]).all(axis=(1, 2))
            close = (np.abs(r - kk) <= UV_TOL).all(axis=(1, 2))
            new = (label == -1) & same_k & close
            new[s] = True
            if (new == member).all():
                break
            member = new
            J, o = fit_uv(xy[member].reshape(-1, 2), (uv[member] - kk[member]).reshape(-1, 2))
        r = uv[member] - (xy[member] @ J.T + o)
        resid = np.abs(r - np.round(r)).max(axis=(1, 2))
        label[member] = len(fits)
        fits.append((J, o, resid))
    return label, fits


def pieces(geom):
    if geom.geom_type == "Polygon":
        return [geom]
    return [g for g in getattr(geom, "geoms", []) if g.geom_type == "Polygon"]


def run(name):
    path = SNAP / name
    m = load_obj(path)
    P, fw = weld(m)
    area, normals, _, degenerate = tri_geometry(P, fw)
    ok = ~degenerate
    sig, quanta = axis_quanta(path, P)
    tri = P[fw]
    uv_all = m["vt"][m["fvt"]]

    plabel, planes = cluster_planes(tri, normals, area, m["fm"], ok, quanta)

    tris_after = 0
    n_uv_classes = n_regions = n_flagged = n_holes = n_new_vertices = 0
    flagged_tris = 0
    max_area_err = 0.0
    all_resid = []
    loose_facing = 0
    biggest = None  # (members, plane, J, o, triangles2d)
    top = []

    for pi, (n, p0, _tol) in enumerate(planes):
        members = np.nonzero(plabel == pi)[0]
        loose_facing += int((normals[members] @ n < 0.999).sum())
        e1, e2 = plane_basis(n)
        xy = np.stack([(tri[members] - p0) @ e1, (tri[members] - p0) @ e2], axis=2)
        ulabel, fits = cluster_uv(xy, uv_all[members], area[members])
        n_uv_classes += len(fits)
        for ui, (J, o, resid) in enumerate(fits):
            sel = ulabel == ui
            X = xy[sel]
            all_resid.append(resid)
            rings = np.concatenate([X, X[:, :1]], axis=1)
            polys = shapely.polygons(rings)
            sum_area = float(shapely.area(polys).sum())
            try:
                u = shapely.union_all(polys, grid_size=GRID)
            except shapely.errors.GEOSException:
                u = shapely.union_all(polys)
            if sum_area - u.area > 1e-6 * sum_area + 1e-9:
                n_flagged += 1
                flagged_tris += int(sel.sum())
                tris_after += int(sel.sum())
                continue
            verts2d = X.reshape(-1, 2)
            out_tris = []
            for poly in pieces(u):
                n_regions += 1
                n_holes += len(poly.interiors)
                cdt = shapely.constrained_delaunay_triangles(poly)
                parts = [g for g in cdt.geoms if g.geom_type == "Polygon"]
                got = sum(g.area for g in parts)
                max_area_err = max(max_area_err, abs(got - poly.area) / max(poly.area, 1e-12))
                out_tris.extend(parts)
            tris_after += len(out_tris)
            top.append((int(sel.sum()), len(out_tris)))
            if out_tris:
                c = np.array([g.exterior.coords[:3] for g in out_tris]).reshape(-1, 2)
                uniq = np.unique(c.round(6), axis=0)
                d = np.linalg.norm(uniq[:, None, :] - verts2d[None, :, :], axis=2).min(axis=1) \
                    if len(uniq) * len(verts2d) < 4e7 else np.zeros(1)
                n_new_vertices += int((d > 10 * GRID).sum())
            if biggest is None or sel.sum() > len(biggest[0]):
                biggest = (members[sel], (n, p0, e1, e2), J, o, out_tris)

    resid = np.concatenate(all_resid) if all_resid else np.zeros(1)
    top.sort(reverse=True)
    n_ok = int(ok.sum())
    result = {
        "significant_digits": sig,
        "axis_quanta_in": quanta.tolist(),
        "tris_total": int(len(fw)),
        "tris_zero_area_dropped": int(degenerate.sum()),
        "tris_before_nondegenerate": n_ok,
        "plane_clusters": len(planes),
        "uv_classes": n_uv_classes,
        "regions": n_regions,
        "union_holes": n_holes,
        "clusters_flagged_overlap": n_flagged,
        "tris_in_flagged_clusters": flagged_tris,
        "faces_admitted_with_loose_facing": loose_facing,
        "new_vertices_created_by_union": n_new_vertices,
        "tris_after": tris_after,
        "reduction_vs_nondegenerate_pct": round(100 * (1 - tris_after / n_ok), 2),
        "reduction_vs_total_pct": round(100 * (1 - tris_after / len(fw)), 2),
        "max_relative_area_error": max_area_err,
        "uv_residual_p50": float(np.percentile(resid, 50)),
        "uv_residual_p99": float(np.percentile(resid, 99)),
        "uv_residual_max": float(resid.max()),
        "top5_regions_before_after": top[:5],
    }

    members, (n, p0, e1, e2), J, o, out_tris = biggest
    stem = name[:-4]
    with open(OUT / f"{stem}__region_before.obj", "w") as fh:
        for t in tri[members].reshape(-1, 3):
            fh.write(f"v {t[0]:.4f} {t[1]:.4f} {t[2]:.4f}\n")
        for i in range(len(members)):
            fh.write(f"f {3*i+1} {3*i+2} {3*i+3}\n")
    with open(OUT / f"{stem}__region_after.obj", "w") as fh:
        i = 0
        for g in out_tris:
            for x, y in g.exterior.coords[:3]:
                p = p0 + x * e1 + y * e2
                u_, v_ = J @ np.array([x, y]) + o
                fh.write(f"v {p[0]:.4f} {p[1]:.4f} {p[2]:.4f}\nvt {u_:.5f} {v_:.5f}\n")
            fh.write(f"f {i+1}/{i+1} {i+2}/{i+2} {i+3}/{i+3}\n")
            i += 3
    result["largest_region"] = {"tris_before": int(len(members)), "tris_after": len(out_tris)}
    return result


out = {name: run(name) for name in FILES}
best = max(r["reduction_vs_nondegenerate_pct"] for r in out.values())
worst_area = max(r["max_relative_area_error"] for r in out.values())
worst_uv = max(r["uv_residual_max"] for r in out.values())
out["gate_G2"] = bool(best >= 40.0 and worst_area <= 1e-6 and worst_uv <= UV_TOL)
save("region_merge", out)
for name in FILES:
    print("==", name)
    for k, v in out[name].items():
        print(f"  {k}: {v}")
print("gate_G2:", out["gate_G2"])
