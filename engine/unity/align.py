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


def _keys(points: np.ndarray, tol: float) -> set:
    return set(map(tuple, np.round(points / tol).astype(np.int64)))


def align(build: MeshData, unity: MeshData, scale: float, tol: float) -> Alignment:
    target = _keys(build.positions, tol)
    bmin = build.positions.min(axis=0)
    best = None
    best_score = (-1.0, -1.0)

    has_faces = build.face_v.size > 0 and unity.face_v.size > 0
    b_faces = None
    if has_faces:
        qb = np.round(build.positions / tol).astype(np.int64)
        b_faces = set()
        for f in build.face_v:
            c = [tuple(qb[i]) for i in f]
            k = min(range(3), key=lambda i: c[i])
            b_faces.add(tuple(c[k:] + c[:k]))

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

            if len(upts) == len(build.positions):
                sec = -float(np.mean(np.linalg.norm(upts - build.positions, axis=1)))
            elif has_faces and b_faces is not None:
                qu = np.round(upts / tol).astype(np.int64)
                det = np.linalg.det(m)
                flip = det < 0
                u_faces = set()
                for f in unity.face_v:
                    c = [tuple(qu[i]) for i in (f[::-1] if flip else f)]
                    k = min(range(3), key=lambda i: c[i])
                    u_faces.add(tuple(c[k:] + c[:k]))
                sec = float(len(b_faces & u_faces))
            else:
                sec = 0.0

            score = (match, sec)
            if best is None or score > best_score:
                best = Alignment(matrix=m, scale=scale, offset=offset, match=match)
                best_score = score

    if best is None or best.match < MIN_MATCH:
        match_val = 0.0 if best is None else best.match
        raise AlignError(f"best match {match_val:.3f} < {MIN_MATCH}: Unity's mesh is not this build")
    return best
