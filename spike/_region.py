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


