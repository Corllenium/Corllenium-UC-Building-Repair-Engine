"""Camera views and orthographic first-hit rendering for the facade guard.

`ortho_first_hit` is a direct port of `first_hit` in `spike/11_guard_feedback.py` (itself sharing
its camera framing math with `depth_image` in `spike/10_ds_visibility.py`), generalised to take an
explicit image size and a `RayCaster` factory instead of hard-coding
`trimesh.ray.ray_pyembree.RayMeshIntersector`. `trimesh`/`embreex` are never imported here directly
-- rendering goes through `engine.rays.caster.EmbreeCaster` (the default `caster_factory`).
"""
from __future__ import annotations

import itertools
from dataclasses import dataclass
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


@dataclass(frozen=True)
class HitBuffers:
    """One `ortho_first_hit` render, with enough of the camera kept to recover each pixel's hit
    POINT (`origins[i, j] + depth[i, j] * direction`), which is what the guard's displacement
    metric needs.

    It behaves like the `(depth, tri)` pair `ortho_first_hit` used to return -- `depth, tri = buf`,
    `buf[0]`, `len(buf) == 2` -- so callers that only want the two buffers need no change.

    `origins` is a PROPERTY, not a stored array: a 900x600 render's origins are 13 MB, and the
    guard holds 26 of them at once, so they are rebuilt from the camera frame on access
    (`origins[i, j] == xs[j] * right + ys[i] * up + standoff`).
    """
    depth: np.ndarray       #: `(H, W)` float64 distance along `direction`, `inf` where the ray missed
    tri: np.ndarray         #: `(H, W)` int64 drawn from `face_ids`, `-1` where the ray missed
    direction: np.ndarray   #: `(3,)` unit view direction, the same for every pixel
    right: np.ndarray       #: `(3,)` unit image x axis
    up: np.ndarray          #: `(3,)` unit image y axis
    xs: np.ndarray          #: `(W,)` offset along `right` of each pixel column
    ys: np.ndarray          #: `(H,)` offset along `up` of each pixel row
    standoff: np.ndarray    #: `(3,)` constant every ray origin is pushed back by

    @property
    def origins(self) -> np.ndarray:
        """`(H, W, 3)` float64 ray origin of every pixel."""
        return (self.xs[None, :, None] * self.right + self.ys[:, None, None] * self.up
                + self.standoff)

    def ring_origins(self, rows: np.ndarray, cols: np.ndarray, radii, n_angles: int = 8) -> np.ndarray:
        """`(len(rows) * len(radii) * n_angles, 3)` ray origins on concentric rings around the
        given pixels' own rays: each radius in `radii` at `n_angles` evenly spaced angles from 0,
        offset in the IMAGE PLANE (`right`/`up`). Ordered pixel-major, then radius, then angle,
        with the pixels in the order `rows`/`cols` are given (which is `np.nonzero`'s order when
        they come from a mask). Cast along `direction` to ask what the geometry looks like just
        beside a pixel.

        The radii are in WORLD units, not pixels, because the question they answer is geometric:
        could a boundary that moved by at most `depth_tol` explain this pixel? A ring is therefore
        independent of image resolution, and may well sit inside the pixel's own footprint."""
        rows = np.asarray(rows, dtype=np.int64).reshape(-1)
        cols = np.asarray(cols, dtype=np.int64).reshape(-1)
        theta = np.arange(n_angles, dtype=np.float64) * (2.0 * np.pi / n_angles)
        radii = np.asarray(radii, dtype=np.float64).reshape(-1)
        dx = (radii[:, None] * np.cos(theta)[None, :]).reshape(-1)          # (R * n_angles,)
        dy = (radii[:, None] * np.sin(theta)[None, :]).reshape(-1)
        x = self.xs[cols][:, None] + dx[None, :]                            # (P, R * n_angles)
        y = self.ys[rows][:, None] + dy[None, :]
        return (x[..., None] * self.right + y[..., None] * self.up
                + self.standoff).reshape(-1, 3)

    def __iter__(self):
        return iter((self.depth, self.tri))

    def __getitem__(self, i):
        return (self.depth, self.tri)[i]

    def __len__(self) -> int:
        return 2


def ortho_first_hit(positions_c: np.ndarray, faces: np.ndarray, face_ids: np.ndarray,
                     view: Sequence[float], frame_points: np.ndarray,
                     size: tuple[int, int] = (900, 600),
                     caster_factory=EmbreeCaster) -> HitBuffers:
    """Orthographic depth / face-id render of `faces` by ray casting, one ray per pixel.

    `positions_c` must already be recentred by the caller (see `engine.rays.caster`). `faces`
    `(F, 3)` are the triangles to cast against; `face_ids` `(F,)` labels each one for the returned
    `tri` buffer, so callers can render a SUBSET of a mesh's faces while `tri` still reports
    original face indices.

    `frame_points` sets the camera framing (extent and standoff distance) -- pass the SAME
    `frame_points` for a BEFORE/AFTER pair so their pixels line up even when `faces` differs
    between the two calls. Since vertices are never moved, one static `frame_points` (e.g. the
    recentred original model's positions) is always correct for both renders.

    `size` is `(width, height)`. Returns a `HitBuffers`: `depth` and `tri`, each `(H, W)` (`depth`
    float64, `inf` where no ray hit that pixel; `tri` int64, values drawn from `face_ids`, `-1`
    where no ray hit), plus the camera frame, so a caller can recover the hit POINT of any pixel
    as `origins[i, j] + depth[i, j] * direction`. A `HitBuffers` unpacks as the `(depth, tri)`
    pair this used to return.
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
    diag = np.linalg.norm(frame_points.max(axis=0) - frame_points.min(axis=0))
    standoff = -d * diag * 2
    frame = dict(direction=d, right=right, up=up, xs=xs, ys=ys, standoff=standoff)

    n = W * H
    if len(faces) == 0:
        return HitBuffers(depth=np.full((H, W), np.inf, dtype=np.float64),
                          tri=np.full((H, W), -1, dtype=np.int64), **frame)

    gx, gy = np.meshgrid(xs, ys)
    origins = (gx[..., None] * right + gy[..., None] * up + standoff).reshape(-1, 3)
    directions = np.tile(d, (len(origins), 1))

    caster = caster_factory(positions_c, faces)
    tri_local, t = caster.first_hit(origins, directions)
    tri = np.full(n, -1, dtype=np.int64)
    hit = tri_local >= 0
    tri[hit] = face_ids[tri_local[hit]]
    return HitBuffers(depth=t.reshape(H, W), tri=tri.reshape(H, W), **frame)
