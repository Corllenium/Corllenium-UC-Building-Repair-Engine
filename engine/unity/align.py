"""Map Unity's frame onto the build's: a signed axis permutation, Unity's import scale and an offset.

Found by trying all 48 signed permutations, not assumed. Unity's OBJ importer mirrors an axis, and a project could
rotate. The winner is the one under which the most Unity vertices land on a build vertex (snapped at `tol`).
"""
from __future__ import annotations

import itertools
from dataclasses import dataclass

import numpy as np

from engine.model import MeshData

MIN_MATCH = 0.99


class AlignError(ValueError):
    """Unity's mesh does not land on the build under any signed axis permutation."""


@dataclass(frozen=True)
class Alignment:
    matrix: np.ndarray   # build = (matrix @ (unity / scale)) + offset
    scale: float
    offset: np.ndarray
    match: float


def to_build_frame(points: np.ndarray, a: Alignment) -> np.ndarray:
    return (np.asarray(points, float) / a.scale) @ a.matrix.T + a.offset


def dump_winding_flips(matrix_or_det: np.ndarray | float) -> bool:
    """Unity uses clockwise winding (left-handed). When Unity's triangles are mapped to the build frame:
    if det > 0, the coordinate transformation preserves clockwise winding, which opposes the build's
    counter-clockwise convention, so the face vertices must be reversed (flip=True).
    If det < 0, the coordinate transformation itself inverts winding, aligning it with the build (flip=False).
    """
    det = float(np.linalg.det(matrix_or_det)) if isinstance(matrix_or_det, np.ndarray) else float(matrix_or_det)
    return det > 0


def _keys(points: np.ndarray, tol: float) -> set:
    return set(map(tuple, np.round(points / tol).astype(np.int64)))


def _face_keys(points: np.ndarray, faces: np.ndarray, tol: float, flip: bool) -> set[tuple]:
    q = np.round(points / tol).astype(np.int64)
    out = set()
    for f in faces:
        c = [tuple(q[i]) for i in (f[::-1] if flip else f)]
        k = min(range(3), key=lambda i: c[i])
        out.add(tuple(c[k:] + c[:k]))
    return out


def _uv_overlap(build: MeshData, unity: MeshData, upts: np.ndarray, tol: float, flip: bool) -> int:
    qb = np.round(build.positions / tol).astype(np.int64)
    qu = np.round(upts / tol).astype(np.int64)
    b_uvs = {}
    for i, f in enumerate(build.face_v):
        corners = tuple(tuple(qb[v]) for v in f)
        b_uvs[corners] = build.uvs[build.face_vt[i]]
    matched = 0
    for j, f in enumerate(unity.face_v):
        corners = tuple(tuple(qu[v]) for v in (f[::-1] if flip else f))
        for rot in range(3):
            c_rot = corners[rot:] + corners[:rot]
            if c_rot in b_uvs:
                u_uv = unity.uvs[unity.face_vt[j]]
                if flip:
                    u_uv = u_uv[::-1]
                u_uv_rot = np.roll(u_uv, -rot, axis=0)
                if np.max(np.abs(b_uvs[c_rot] - u_uv_rot)) < 1e-3:
                    matched += 1
                break
    return matched


def align(build: MeshData, unity: MeshData, scale: float, tol: float) -> Alignment:
    target = _keys(build.positions, tol)
    bmin = build.positions.min(axis=0)

    # 1. Compute match for all 48 permutations first
    candidates: list[tuple[float, np.ndarray, np.ndarray]] = []
    best_match = -1.0
    for perm in itertools.permutations(range(3)):
        for signs in itertools.product((1.0, -1.0), repeat=3):
            m = np.zeros((3, 3))
            for row, (col, s) in enumerate(zip(perm, signs)):
                m[row, col] = s
            p = (unity.positions / scale) @ m.T
            offset = bmin - p.min(axis=0)
            upts = p + offset
            got = _keys(upts, tol)
            match = len(got & target) / max(len(got), 1)
            candidates.append((match, m, offset))
            if match > best_match:
                best_match = match

    if best_match < MIN_MATCH:
        raise AlignError(f"best match {best_match:.3f} < {MIN_MATCH}: Unity's mesh is not this build")

    tied = [c for c in candidates if c[0] == best_match]

    # 2. If single winner, skip face-overlap computation
    if len(tied) == 1:
        match, m, offset = tied[0]
        return Alignment(matrix=m, scale=scale, offset=offset, match=match)

    # 3. If tied, compute order-free oriented face-overlap only for tied candidates (b_faces built lazily)
    b_faces = _face_keys(build.positions, build.face_v, tol, flip=False) if build.face_v.size > 0 else set()
    has_uv = build.face_vt.size > 0 and unity.face_vt.size > 0
    scored = []
    for match, m, offset in tied:
        upts = (unity.positions / scale) @ m.T + offset
        flip = dump_winding_flips(m)

        # Face overlap (order-free, tolerant to dump vs raw winding)
        fo1 = len(b_faces & _face_keys(upts, unity.face_v, tol, flip=flip)) if b_faces else 0
        fo2 = len(b_faces & _face_keys(upts, unity.face_v, tol, flip=not flip)) if b_faces else 0
        face_overlap = max(fo1, fo2)

        # UV overlap when tied
        uv_overlap = 0
        if has_uv:
            uv1 = _uv_overlap(build, unity, upts, tol, flip=flip)
            uv2 = _uv_overlap(build, unity, upts, tol, flip=not flip)
            uv_overlap = max(uv1, uv2)

        x_mirrored = 1 if m[0, 0] < 0 else 0
        scored.append(((face_overlap, uv_overlap, x_mirrored), m, offset, match))

    scored.sort(key=lambda s: s[0], reverse=True)
    winner = scored[0]
    return Alignment(matrix=winner[1], scale=scale, offset=winner[2], match=winner[3])
