"""Did the engine's build survive Unity's import? Face-by-face, by cause.

Faces are compared as ORIENTED multisets of snapped corner positions in the build's frame, so two coincident faces
of opposite winding stay two faces. A face is `matched` (same corners, same orientation), `flipped` (same corners,
opposite orientation), `missing` (in the build only) or `extra` (in Unity only).
"""
from __future__ import annotations

from collections import Counter

import numpy as np

from engine.model import MeshData
from engine.repair.types import print_step
from engine.unity.align import align, to_build_frame
from engine.unity.dump import UnityDump

UINT16_MAX_VERTICES = 65535
_EXAMPLES = 20


def _oriented_keys(points: np.ndarray, faces: np.ndarray, tol: float, flip: bool) -> list[tuple]:
    q = np.round(points / tol).astype(np.int64)
    out = []
    for f in faces:
        c = [tuple(q[i]) for i in (f[::-1] if flip else f)]
        k = min(range(3), key=lambda i: c[i])            # rotate so the smallest corner is first
        out.append(tuple(c[k:] + c[:k]))
    return out


def _reverse(key: tuple) -> tuple:
    a, b, c = key
    return (a, c, b)


def geometry_diff(build: MeshData, dump: UnityDump) -> dict:
    tol = print_step(build)
    scale = float(dump.sidecar["importer"]["globalScale"])
    a = align(build, dump.mesh, scale, tol)
    det = float(np.linalg.det(a.matrix))
    upts = to_build_frame(dump.mesh.positions, a)
    bkeys = _oriented_keys(build.positions, build.face_v, tol, flip=False)
    ukeys = _oriented_keys(upts, dump.mesh.face_v, tol, flip=det > 0)   # Unity's dump reverses winding
    bc, uc = Counter(bkeys), Counter(ukeys)
    matched = sum((bc & uc).values())
    b_left, u_left = bc - uc, uc - bc
    flipped = 0
    for k, n in list(b_left.items()):
        r = _reverse(k)
        take = min(n, u_left.get(r, 0))
        if take:
            flipped += take
            b_left[k] -= take
            u_left[r] -= take
    missing = sum(v for v in b_left.values() if v > 0)
    extra = sum(v for v in u_left.values() if v > 0)
    miss_keys = {k for k, v in b_left.items() if v > 0}
    meshes = dump.sidecar.get("meshes", [])
    overflow = any(m.get("index_format") == "UInt16" and m.get("vertex_count", 0) > UINT16_MAX_VERTICES
                   for m in meshes)
    return {
        "alignment": {"match": a.match, "det": det},
        "faces_build": int(build.n_faces), "faces_unity": int(dump.mesh.n_faces),
        "matched": matched, "missing": missing, "extra": extra, "flipped": flipped,
        "index_overflow": overflow,
        "vertex_counts": {m.get("name"): m.get("vertex_count") for m in meshes},
        "examples": {"missing": [i for i, k in enumerate(bkeys) if k in miss_keys][:_EXAMPLES]},
    }


UV_TOL = 1e-4
SMOOTH_DEG = 1.0
NO_MATERIAL = "<none>"


def _name(mesh: MeshData, f: int) -> str:
    m = int(mesh.face_material[f])
    return NO_MATERIAL if m < 0 else mesh.materials[m]


def _tex(mtl: dict, name: str):
    e = mtl.get(name)
    return getattr(e, "map_kd", None) if e is not None else None


def _match_pairs(build: MeshData, dump: UnityDump) -> tuple[list[tuple[int, int, list[int]]], np.ndarray]:
    """(build face, unity face, corner order) for every matched face, and Unity's positions in the build frame."""
    tol = print_step(build)
    a = align(build, dump.mesh, float(dump.sidecar["importer"]["globalScale"]), tol)
    flip = np.linalg.det(a.matrix) > 0
    upts = to_build_frame(dump.mesh.positions, a)
    qb = np.round(build.positions / tol).astype(np.int64)
    qu = np.round(upts / tol).astype(np.int64)
    bkeys = _oriented_keys(build.positions, build.face_v, tol, False)
    by_key: dict = {}
    for j, k in enumerate(_oriented_keys(upts, dump.mesh.face_v, tol, flip)):
        by_key.setdefault(k, []).append(j)
    pairs = []
    for i, k in enumerate(bkeys):
        if by_key.get(k):
            j = by_key[k].pop()
            ucorner = {tuple(qu[v]): c for c, v in enumerate(dump.mesh.face_v[j])}
            order = [ucorner[tuple(qb[v])] for v in build.face_v[i]]
            pairs.append((i, j, order))
    return pairs, upts


def surface_diff(build: MeshData, dump: UnityDump, build_mtl: dict, unity_mtl: dict) -> dict:
    pairs, upts = _match_pairs(build, dump)
    found = {k: [] for k in ("material_remapped", "texture_lost", "uv_changed",
                             "normal_against_face", "normal_smoothed")}
    cos_smooth = np.cos(np.radians(SMOOTH_DEG))
    for i, j, order in pairs:
        bn, un = _name(build, i), _name(dump.mesh, j)
        if bn != un:
            found["material_remapped"].append(i)
        if _tex(build_mtl, bn) and not _tex(unity_mtl, un):
            found["texture_lost"].append(i)
        if build.face_vt.size and dump.mesh.face_vt.size:
            buv = build.uvs[build.face_vt[i]]
            uuv = dump.mesh.uvs[dump.mesh.face_vt[j]][order]
            if np.abs(buv - uuv).max() > UV_TOL:
                found["uv_changed"].append(i)
        fn_u = np.cross(*(dump.mesh.positions[dump.mesh.face_v[j]][1:] - dump.mesh.positions[dump.mesh.face_v[j]][0]))
        fn_u = fn_u / max(np.linalg.norm(fn_u), 1e-300)
        dots = dump.corner_normals[j] @ fn_u
        if (dots < 0).any():
            found["normal_against_face"].append(i)
        elif (dots < cos_smooth).any():
            found["normal_smoothed"].append(i)
    return {k: {"count": len(v), "examples": v[:_EXAMPLES]} for k, v in found.items()}
