"""Per-face exposure: how visible each non-degenerate face is from outside, by ray sampling.

Exposure is DOUBLE-SIDED: one caster is built from ALL non-degenerate ("ok") faces, and every
ok face is sampled from BOTH sides against it (a face renders and blocks from either side, the
way SketchUp/Unity draw it). Ported from `escapes_double_sided` in `spike/10_ds_visibility.py`.

Precondition: `positions_c` passed to `compute_exposure` must already be recentred by the
caller (e.g. to the mesh's bbox centre) -- see `engine.rays.caster` for why: real-model
coordinates sit near 24,000 inches and embree stores vertices as float32 internally.
`compute_exposure` does NOT recentre again; it uses `positions_c` as given.
"""
from __future__ import annotations

import numpy as np

from engine.rays.caster import EmbreeCaster

EPS_IN = 0.02

# Sample points per triangle: centroid, then three corner-biased points (0.6/0.2/0.2).
BARY = np.array([
    [1 / 3, 1 / 3, 1 / 3],
    [0.6, 0.2, 0.2],
    [0.2, 0.6, 0.2],
    [0.2, 0.2, 0.6],
])

EXP_DEGENERATE = 0
EXP_HIDDEN = 1
EXP_SLIT = 2
EXP_OUTSIDE = 3


def fib_dirs(n: int) -> np.ndarray:
    """n unit directions spread evenly over the sphere (Fibonacci lattice)."""
    i = np.arange(n) + 0.5
    phi = np.arccos(1 - 2 * i / n)
    th = np.pi * (1 + 5 ** 0.5) * i
    return np.stack([np.cos(th) * np.sin(phi), np.sin(th) * np.sin(phi), np.cos(phi)], axis=1)


def compute_exposure(positions_c: np.ndarray, face_w: np.ndarray, ok: np.ndarray,
                      caster_factory=EmbreeCaster, n_dirs: int = 128) -> np.ndarray:
    """Fraction of sampled rays that escape each face, double-sided: escaping rays /
    (n_dirs * len(BARY)). 0.0 for degenerate (`not ok`) faces.

    Precondition: `positions_c` is already recentred by the caller (see module docstring).
    Face normals come from `positions_c[face_w]` (the welded mesh geometry), not from the
    source file's `vn`.

    For each of `n_dirs` Fibonacci-lattice directions `w`: faces with `normal . w > 1e-6` cast
    from `sample point + EPS_IN * normal` (the front side); faces with `normal . w < -1e-6`
    cast from `sample point - EPS_IN * normal` (the back side); both cast along `w`, against
    ONE caster built from `caster_factory(positions_c, face_w[ok])` -- all ok faces, built once
    and reused across every direction and side.
    """
    positions_c = np.asarray(positions_c, dtype=np.float64)
    face_w = np.asarray(face_w, dtype=np.int64)
    ok = np.asarray(ok, dtype=bool)
    n_faces = len(face_w)

    tri = positions_c[face_w]  # (F, 3, 3)
    cross = np.cross(tri[:, 1] - tri[:, 0], tri[:, 2] - tri[:, 0])
    lengths = np.linalg.norm(cross, axis=1)
    normals = np.zeros_like(cross)
    safe = ok & (lengths > 0)
    normals[safe] = cross[safe] / lengths[safe, None]

    escapes = np.zeros(n_faces, dtype=np.int64)
    caster = caster_factory(positions_c, face_w[ok])
    for w in fib_dirs(n_dirs):
        dot = normals @ w
        for ids, sign in ((np.nonzero(ok & (dot > 1e-6))[0], 1.0),
                          (np.nonzero(ok & (dot < -1e-6))[0], -1.0)):
            if len(ids) == 0:
                continue
            pts = np.einsum("sb,fbk->fsk", BARY, tri[ids]) + sign * EPS_IN * normals[ids][:, None, :]
            origins = pts.reshape(-1, 3)
            directions = np.tile(w, (len(origins), 1))
            hit = caster.any_hit(origins, directions)
            escapes[ids] += (~hit).reshape(len(ids), len(BARY)).sum(axis=1)

    exposure = np.zeros(n_faces, dtype=np.float64)
    exposure[ok] = escapes[ok] / (n_dirs * len(BARY))
    return exposure


def classify_exposure(exposure: np.ndarray, ok: np.ndarray, slit_threshold: float = 0.05) -> np.ndarray:
    """EXP_DEGENERATE for `not ok` faces (regardless of their exposure value); else
    EXP_HIDDEN (exposure == 0), EXP_SLIT (0 < exposure < slit_threshold), or EXP_OUTSIDE
    (exposure >= slit_threshold)."""
    exposure = np.asarray(exposure, dtype=np.float64)
    ok = np.asarray(ok, dtype=bool)
    out = np.full(len(exposure), EXP_DEGENERATE, dtype=np.uint8)
    out[ok & (exposure <= 0.0)] = EXP_HIDDEN
    out[ok & (exposure > 0.0) & (exposure < slit_threshold)] = EXP_SLIT
    out[ok & (exposure >= slit_threshold)] = EXP_OUTSIDE
    return out
