"""Diagnostic only: for each edge-flicker pixel, how far did the surface border move?

moved pixel (AFTER hit a surface BEFORE did not): distance from the AFTER hit point to the nearest
  ORIGINAL (reference) triangle lying in the same plane as the AFTER face -- 0 means the original
  surface was there too and BEFORE's ray slipped through a crack; > 0 is how far the merged border
  grew past the original.
hole pixel (AFTER missed a surface BEFORE hit): distance from the BEFORE hit point to the nearest
  MERGED triangle lying in the same plane as the BEFORE face -- how far the merged border shrank.
"""
import json
import pickle
import sys
from pathlib import Path

import numpy as np

cap = pickle.load(open(Path(sys.argv[1]) / "flicker_capture.pkl", "rb"))
pos_b, faces_b = cap["geometry_before"]
pos_a, faces_a = cap["geometry_after"]
assert pos_a is pos_b or np.array_equal(pos_a, pos_b)
pos = pos_b


def plane_of(face):
    p = pos[face]
    n = np.cross(p[1] - p[0], p[2] - p[0])
    n = n / np.linalg.norm(n)
    return n, float(n @ p[0])


def coplanar_faces(faces, n, d, tol=0.05):
    p = pos[faces]                                  # (F, 3, 3)
    dist = np.abs(p @ n - d)                        # (F, 3)
    fn = np.cross(p[:, 1] - p[:, 0], p[:, 2] - p[:, 0])
    ln = np.linalg.norm(fn, axis=1)
    ok = ln > 1e-12
    cosang = np.zeros(len(faces))
    cosang[ok] = np.abs(fn[ok] @ n) / ln[ok]
    return np.flatnonzero((dist.max(axis=1) < tol) & (cosang > 0.999))


def point_tri_dist(q, tri):
    """Distance from q to triangle tri (3x3), exact (Ericson)."""
    a, b, c = tri
    ab, ac, ap = b - a, c - a, q - a
    d1, d2 = ab @ ap, ac @ ap
    if d1 <= 0 and d2 <= 0:
        return np.linalg.norm(q - a)
    bp = q - b
    d3, d4 = ab @ bp, ac @ bp
    if d3 >= 0 and d4 <= d3:
        return np.linalg.norm(q - b)
    vc = d1 * d4 - d3 * d2
    if vc <= 0 and d1 >= 0 and d3 <= 0:
        v = d1 / (d1 - d3)
        return np.linalg.norm(q - (a + v * ab))
    cp = q - c
    d5, d6 = ab @ cp, ac @ cp
    if d6 >= 0 and d5 <= d6:
        return np.linalg.norm(q - c)
    vb = d5 * d2 - d1 * d6
    if vb <= 0 and d2 >= 0 and d6 <= 0:
        w = d2 / (d2 - d6)
        return np.linalg.norm(q - (a + w * ac))
    va = d3 * d6 - d5 * d4
    if va <= 0 and (d4 - d3) >= 0 and (d5 - d6) >= 0:
        w = (d4 - d3) / ((d4 - d3) + (d5 - d6))
        return np.linalg.norm(q - (b + w * (c - b)))
    denom = 1.0 / (va + vb + vc)
    v, w = vb * denom, vc * denom
    return np.linalg.norm(q - (a + ab * v + ac * w))


rows = cap["rows"]
out = []
for x in rows:
    if x["base"] == 1:          # hole: BEFORE point vs merged surface in BEFORE face's plane
        q = np.array(x["p_before"])
        n, d = plane_of(faces_b[x["before_tri"]])
        cand = coplanar_faces(faces_a, n, d)
        kind = "hole"
    else:                        # moved: AFTER point vs original surface in AFTER face's plane
        q = np.array(x["p_after"])
        n, d = plane_of(faces_a[x["after_tri"]])
        cand = coplanar_faces(faces_b, n, d)
        kind = "moved"
    dist = min((point_tri_dist(q, pos[f]) for f in faces_a[cand]), default=float("inf")) if kind == "hole" \
        else min((point_tri_dist(q, pos[f]) for f in faces_b[cand]), default=float("inf"))
    out.append((x["view"], kind, x["r"], x["c"], len(cand), dist))

by_kind = {}
for v, kind, r, c, nc, dist in out:
    by_kind.setdefault(kind, []).append(dist)
print("view-0 pixels:")
for v, kind, r, c, nc, dist in out:
    if v == 0:
        print(f"  {kind:5s} r{r} c{c}: coplanar candidates {nc}, border moved {dist:.4f} in")
for kind, ds in by_kind.items():
    ds = np.array(ds)
    print(f"all views, {kind}: n={len(ds)}  max {ds.max():.4f}  median {np.median(ds):.4f}  "
          f"> 0.15 in: {(ds > 0.15).sum()}  == 0: {(ds < 1e-6).sum()}")
