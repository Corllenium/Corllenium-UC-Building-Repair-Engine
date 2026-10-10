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
