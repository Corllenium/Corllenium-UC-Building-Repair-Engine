"""Measure exactly coincident face pairs in a mesh (brief 13, "measure first").

A pair (i, j) is EXACTLY coincident when every corner of each lies within `plane_tol` (0.001 in,
the print precision) of the other's plane, the planes are parallel, and each triangle covers the
other at least `cover` (0.99) of its area. Reported per pair: winding (opposite or same), material
(same or different), UV mapping (same modulo whole tiles or not, `uv_tol` like
`engine.topo.planes.build_regions`), area, location, and whether the two share their corners.

Also, per face, how much of it the OPPOSITE-wound faces of its own plane cover as a UNION -- so a
copy triangulated differently from its original is not missed by the pairwise test -- and where
every exact pair of the INPUT went in the pipeline (hidden, replaced by solidify, flipped and then
removed as a same-wound duplicate, ...).

Independent of `engine.fixes.overlap.find_coincident_pairs` on purpose (its own search, its own
UV comparison), so the two can be held against each other.

Usage (from the repo root, PYTHONPATH set to it):
  run_fix_keep_result.py <snapshot> <out root> <skp dir> <result.pkl>
  measure_stacked_pairs.py <result.pkl>"""
from __future__ import annotations

import pickle
import sys
from collections import Counter

import numpy as np
import shapely

from engine.topo.planes import plane_basis


def _geometry(positions, face_v):
    tri = np.asarray(positions, dtype=np.float64)[np.asarray(face_v, dtype=np.int64)]
    cross = np.cross(tri[:, 1] - tri[:, 0], tri[:, 2] - tri[:, 0])
    length = np.linalg.norm(cross, axis=1)
    area = 0.5 * length
    normal = np.zeros_like(cross)
    ok = length > 1e-12
    normal[ok] = cross[ok] / length[ok, None]
    return tri, area, normal, ok


def _uv_map(xy, uv):
    """Affine map `[x, y, 1] -> uv` through a triangle's three corners (2 x 3), or None."""
    a = np.column_stack([xy, np.ones(3)])
    if abs(np.linalg.det(a)) < 1e-12:
        return None
    return np.linalg.solve(a, uv).T


def uv_same_modulo_tiles(mesh, i, j, basis, origin, uv_tol=0.02):
    """`(same, residual, shift)`: do faces i and j map every point of their shared plane to the
    same UV up to one whole-tile shift? Both without UVs is the same mapping; one without is not."""
    has_i = (mesh.face_vt[i] >= 0).all()
    has_j = (mesh.face_vt[j] >= 0).all()
    if not has_i and not has_j:
        return True, 0.0, (0, 0)
    if has_i != has_j:
        return False, float("inf"), None
    pos = np.asarray(mesh.positions, dtype=np.float64)
    xy_i = (pos[mesh.face_v[i]] - origin) @ basis
    xy_j = (pos[mesh.face_v[j]] - origin) @ basis
    m_i = _uv_map(xy_i, mesh.uvs[mesh.face_vt[i]])
    m_j = _uv_map(xy_j, mesh.uvs[mesh.face_vt[j]])
    if m_i is None or m_j is None:
        return False, float("inf"), None
    pts = np.column_stack([np.vstack([xy_i, xy_j]), np.ones(6)])
    diff = pts @ m_i.T - pts @ m_j.T
    k = np.round(diff)
    residual = float(np.abs(diff - k).max())
    same_k = bool((k == k[0]).all())
    return bool(same_k and residual <= uv_tol), residual, tuple(int(x) for x in k[0])


def coincident_pairs(mesh, plane_tol=1e-3, cover=0.99, uv_tol=0.02, block=400):
    tri, area, normal, ok = _geometry(mesh.positions, mesh.face_v)
    n = len(tri)
    lo, hi = tri.min(axis=1), tri.max(axis=1)
    idx = np.nonzero(ok)[0]
    pairs = []
    for s in range(0, len(idx), block):
        rows = idx[s:s + block]
        # bbox overlap with the plane tolerance, parallel normals, j after i
        over = ((lo[rows, None, :] <= hi[None, idx, :] + plane_tol)
                & (hi[rows, None, :] >= lo[None, idx, :] - plane_tol)).all(axis=2)
        par = np.abs(normal[rows] @ normal[idx].T) > 0.9999
        later = idx[None, :] > rows[:, None]
        for a, b in zip(*np.nonzero(over & par & later)):
            i, j = int(rows[a]), int(idx[b])
            # every corner of each within plane_tol of the other's plane
            if np.abs((tri[j] - tri[i][0]) @ normal[i]).max() > plane_tol:
                continue
            if np.abs((tri[i] - tri[j][0]) @ normal[j]).max() > plane_tol:
                continue
            e1, e2 = plane_basis(normal[i])
            basis = np.stack([e1, e2], axis=1)
            origin = tri[i][0]
            pi = shapely.Polygon((tri[i] - origin) @ basis)
            pj = shapely.Polygon((tri[j] - origin) @ basis)
            inter = pi.intersection(pj).area
            ci, cj = inter / pi.area, inter / pj.area
            if min(ci, cj) < cover:
                continue
            same_uv, residual, shift = uv_same_modulo_tiles(mesh, i, j, basis, origin, uv_tol)
            centroid = tri[i].mean(axis=0)
            pairs.append({
                "faces": [i, j],
                "opposite": bool(normal[i] @ normal[j] < 0.0),
                "same_material": bool(mesh.face_material[i] == mesh.face_material[j]),
                "materials": [mesh.materials[int(mesh.face_material[i])],
                              mesh.materials[int(mesh.face_material[j])]],
                "same_uv": same_uv, "uv_residual": round(residual, 5), "uv_shift": shift,
                "same_corners": sorted(map(tuple, np.round(tri[i], 4).tolist()))
                                == sorted(map(tuple, np.round(tri[j], 4).tolist())),
                "cover": [round(ci, 5), round(cj, 5)],
                "area": round(float(area[i]), 3),
                "normal_i": np.round(normal[i], 4).tolist(),
                "centroid": np.round(centroid, 2).tolist(),
            })
    return pairs


def union_cover_opposite(mesh, plane_tol=1e-3, block=400):
    """`{face: fraction}` for every face at least 1 % covered by the UNION of the opposite-wound
    faces lying in its plane (every corner within `plane_tol`)."""
    tri, area, normal, ok = _geometry(mesh.positions, mesh.face_v)
    lo, hi = tri.min(axis=1), tri.max(axis=1)
    idx = np.nonzero(ok)[0]
    out = {}
    for s in range(0, len(idx), block):
        rows = idx[s:s + block]
        over = ((lo[rows, None, :] <= hi[None, idx, :] + plane_tol)
                & (hi[rows, None, :] >= lo[None, idx, :] - plane_tol)).all(axis=2)
        opp = (normal[rows] @ normal[idx].T) < -0.9999
        for a in range(len(rows)):
            i = int(rows[a])
            cand = idx[over[a] & opp[a]]
            cand = [int(j) for j in cand
                    if np.abs((tri[j] - tri[i][0]) @ normal[i]).max() <= plane_tol]
            if not cand:
                continue
            e1, e2 = plane_basis(normal[i])
            basis = np.stack([e1, e2], axis=1)
            origin = tri[i][0]
            pi = shapely.Polygon((tri[i] - origin) @ basis)
            union = shapely.union_all([shapely.Polygon((tri[j] - origin) @ basis) for j in cand])
            frac = pi.intersection(union).area / pi.area
            if frac >= 0.01:
                out[i] = round(float(frac), 4)
    return out


def summarise(label, mesh, pairs):
    print(f"--- {label}: {mesh.n_faces} faces, {len(pairs)} exactly coincident pairs")
    c = Counter((("opposite" if p["opposite"] else "same-wound"),
                 ("same material" if p["same_material"] else "different material"),
                 ("same UV" if p["same_uv"] else "different UV")) for p in pairs)
    for k, v in sorted(c.items()):
        print(f"    {v:4d}  {' / '.join(k)}")
    return c


def input_pair_fates(result, input_mesh, pairs) -> Counter:
    """Where each exact pair of the INPUT went: per face, the pass that removed it (or "kept"),
    "+flipped" when the orientation step re-wound it; faces solidify replaced never reach the
    reference. Reference row of input face i (not replaced): `cumsum(~replaced)[i] - 1`."""
    ref_of = np.cumsum(~result.replaced_input) - 1
    fate = Counter()
    for p in pairs:
        out = []
        for i in p["faces"]:
            if result.replaced_input[i]:
                out.append("replaced by solidify")
                continue
            k = ref_of[i]
            tag = ("hidden" if result.removed_hidden[k] else "slit" if result.removed_slit[k]
                   else "fragment/fold" if result.removed_fragments[k]
                   else "same-wound duplicate" if result.removed_overlap[k]
                   else "stacked copy (brief 13)" if result.removed_coincident[k] else "kept")
            out.append(tag + ("+flipped" if result.flipped[k] else ""))
        fate[" | ".join(sorted(out)) + (" [same material]" if p["same_material"]
                                        else " [different materials]")] += 1
    return fate


def main(path):
    with open(path, "rb") as fh:
        cap = pickle.load(fh)
    result, input_mesh = cap["result"], cap["input"]
    for label, mesh in (("input", input_mesh), ("reference", result.reference_mesh),
                        ("final", result.mesh)):
        pairs = coincident_pairs(mesh)
        summarise(label, mesh, pairs)
        if label == "input":
            for key, n in input_pair_fates(result, input_mesh, pairs).most_common():
                print(f"    fate: {n:3d}  {key}")
        if label == "final":
            for p in sorted(pairs, key=lambda p: (not p["opposite"], p["centroid"][2])):
                srcs = [np.asarray(result.source_faces[f]).tolist() for f in p["faces"]]
                print("   ", p["faces"], "opp" if p["opposite"] else "same",
                      p["materials"], "uv" if p["same_uv"] else f"UV DIFF res={p['uv_residual']}",
                      "area", p["area"], "n", p["normal_i"], "at", p["centroid"],
                      "corners", p["same_corners"], "src", srcs)
            cov = union_cover_opposite(mesh)
            paired = {f for p in pairs if p["opposite"] for f in p["faces"]}
            extra = {f: v for f, v in cov.items() if f not in paired}
            print(f"    union cover by opposite-wound faces of the plane: {len(cov)} faces >= 1 %, "
                  f"{sum(v >= 0.99 for v in cov.values())} >= 99 %; not in an exact pair: "
                  f"{len(extra)} ({sum(v >= 0.99 for v in extra.values())} >= 99 %)")
            for f, v in sorted(extra.items()):
                t = mesh.positions[mesh.face_v[f]]
                print(f"      face {f} {mesh.materials[int(mesh.face_material[f])]} covered {v} "
                      f"at {np.round(t.mean(axis=0), 1).tolist()} src "
                      f"{np.asarray(result.source_faces[f]).tolist()[:8]}")


if __name__ == "__main__":
    main(sys.argv[1])
