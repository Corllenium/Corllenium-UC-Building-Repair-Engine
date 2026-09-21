"""Camera views and orthographic first-hit rendering for the facade guard.

`ortho_first_hit` is a direct port of `first_hit` in `spike/11_guard_feedback.py` (itself sharing
its camera framing math with `depth_image` in `spike/10_ds_visibility.py`), generalised to take an
explicit image size and a `RayCaster` factory instead of hard-coding
`trimesh.ray.ray_pyembree.RayMeshIntersector`. `trimesh`/`embreex` are never imported here directly
-- rendering goes through `engine.rays.caster.EmbreeCaster` (the default `caster_factory`).
"""
from __future__ import annotations

import itertools
from typing import Sequence

import numpy as np

from engine.rays.caster import EmbreeCaster

_NUDGE = np.array([0.013, 0.007, 0.011])

#: The 26 axis/diagonal view directions -- every nonzero combination of -1/0/1 on each axis --
#: each nudged by (0.013, 0.007, 0.011) so no view is exactly edge-on to an axis-aligned face.
#: Ported from `spike/11_guard_feedback.py`'s `VIEWS`.
VIEWS_26: tuple[tuple[float, float, float], ...] = tuple(
    tuple((np.asarray(v, dtype=np.float64) + _NUDGE).tolist())
    for v in itertools.product((-1, 0, 1), repeat=3) if any(v)
)


def ortho_first_hit(positions_c: np.ndarray, faces: np.ndarray, face_ids: np.ndarray,
                     view: Sequence[float], frame_points: np.ndarray,
                     size: tuple[int, int] = (900, 600),
                     caster_factory=EmbreeCaster) -> tuple[np.ndarray, np.ndarray]:
    """Orthographic depth / face-id render of `faces` by ray casting, one ray per pixel.

    `positions_c` must already be recentred by the caller (see `engine.rays.caster`). `faces`
    `(F, 3)` are the triangles to cast against; `face_ids` `(F,)` labels each one for the returned
    `tri` buffer, so callers can render a SUBSET of a mesh's faces while `tri` still reports
    original face indices.

    `frame_points` sets the camera framing (extent and standoff distance) -- pass the SAME
    `frame_points` for a BEFORE/AFTER pair so their pixels line up even when `faces` differs
    between the two calls. Since vertices are never moved, one static `frame_points` (e.g. the
    recentred original model's positions) is always correct for both renders.

    `size` is `(width, height)`. Returns `(depth, tri)`, each `(H, W)`: `depth` float64, `inf`
    where no ray hit that pixel; `tri` int64, values drawn from `face_ids`, `-1` where no ray hit.
    """
    W, H = size
    positions_c = np.asarray(positions_c, dtype=np.float64)
    faces = np.asarray(faces, dtype=np.int64)
    face_ids = np.asarray(face_ids, dtype=np.int64)
    frame_points = np.asarray(frame_points, dtype=np.float64)

    d = np.asarray(view, dtype=np.float64)
    d = d / np.linalg.norm(d)
    up_hint = (0.0, 1.0, 0.0) if abs(d[2]) > 0.99 else (0.0, 0.0, 1.0)
    right = np.cross(d, up_hint)
    right = right / np.linalg.norm(right)
    up = np.cross(right, d)

    er, eu = frame_points @ right, frame_points @ up
    half = max((er.max() - er.min()) / W, (eu.max() - eu.min()) / H) * 0.52
    xs = (er.max() + er.min()) / 2 + (np.arange(W) - W / 2 + 0.5) * half * 2
    ys = (eu.max() + eu.min()) / 2 - (np.arange(H) - H / 2 + 0.5) * half * 2
    gx, gy = np.meshgrid(xs, ys)
    diag = np.linalg.norm(frame_points.max(axis=0) - frame_points.min(axis=0))
    origins = (gx[..., None] * right + gy[..., None] * up - d * diag * 2).reshape(-1, 3)
    directions = np.tile(d, (len(origins), 1))

    n = W * H
    if len(faces) == 0:
        return np.full((H, W), np.inf, dtype=np.float64), np.full((H, W), -1, dtype=np.int64)

    caster = caster_factory(positions_c, faces)
    tri_local, t = caster.first_hit(origins, directions)
    tri = np.full(n, -1, dtype=np.int64)
    hit = tri_local >= 0
    tri[hit] = face_ids[tri_local[hit]]
    return t.reshape(H, W), tri.reshape(H, W)
