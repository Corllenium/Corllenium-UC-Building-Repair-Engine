"""Viewpoints for the Validator: where it looks from.

Outside, 128 directions over the sphere and a ring of cameras at pedestrian height. Inside, a
probe at eye height above every stretch of floor someone could stand on, because players walk the
floors (AGENTS.md section 5). Everything is deterministic: no randomness anywhere.

Written for the Validator and independent of the code it judges (see `engine.validate`). Meshes
and `bbox` here are in the Validator's frame (`sampling.recentred`), in inches, Z up.
"""
from __future__ import annotations

import numpy as np

from engine.model import MeshData
from engine.validate.sampling import check_frame, face_normals, used_bbox
from engine.validate.visibility import build_caster, check_caster

#: A face is ground to stand on when its normal's z is above this: a slope under about 26 degrees.
UP_NZ = 0.9
#: The headroom ray starts this far above the surface, which steps it over a floor's own thin layers.
HEADROOM_START = 0.5
#: Two candidate probes in one lattice cell are the same probe when their surfaces are within this
#: height band, so a stack of coincident floor layers gives one probe and a staircase gives one per tread.
LEVEL = 2.0
#: Barycentric slack for "is this lattice point inside that triangle": a point exactly on an edge
#: shared by two faces belongs to both, and the lattice cell dedupe keeps one.
_EDGE = 1e-9
#: Candidate points (or rays) handled in one numpy block.
_BATCH = 1 << 20


def outside_directions(n: int = 128) -> np.ndarray:
    """(n, 3) float64 unit view directions spread evenly over the sphere: a Fibonacci lattice, equal
    height bands turned by the golden angle (the measured nearest pair is 15.7 degrees apart at
    n = 128, and no point of the sphere is further than 13.2 degrees from one). Which way is "to
    the viewer" is `visibility`'s business: it looks from `-dir`."""
    i = np.arange(n, dtype=np.float64) + 0.5
    z = 1.0 - 2.0 * i / n
    r = np.sqrt(np.maximum(0.0, 1.0 - z * z))
    theta = np.pi * (1.0 + 5.0 ** 0.5) * i
    d = np.stack([r * np.cos(theta), r * np.sin(theta), z], axis=1)
    return d / np.linalg.norm(d, axis=1, keepdims=True)


def pedestrian_ring(bbox, eye_z: float, n: int = 24, margin: float = 240.0) -> np.ndarray:
    """(n, 3) float64 camera positions at height `eye_z`, evenly spaced along the outline of the
    box `bbox` grown by `margin` in plan, from its lower-left corner counter-clockwise, half a
    step in. Every camera is exactly `margin` outside the box (Chebyshev distance in plan), so
    none can stand inside the building. `bbox` is `(lo, hi)`, e.g. `mesh.bbox()` or `used_bbox`."""
    if n <= 0:
        return np.zeros((0, 3))
    lo, hi = np.asarray(bbox, dtype=np.float64).reshape(2, 3)
    x0, y0, x1, y1 = lo[0] - margin, lo[1] - margin, hi[0] + margin, hi[1] + margin
    w, h = x1 - x0, y1 - y0
    s = (np.arange(n, dtype=np.float64) + 0.5) * (2.0 * (w + h) / n)      # arc length along the outline
    bottom, right, top = s < w, (s >= w) & (s < w + h), (s >= w + h) & (s < 2.0 * w + h)
    zero = np.zeros(n)
    x = np.select([bottom, right, top], [x0 + s, x1 + zero, x1 - (s - w - h)], default=x0 + zero)
    y = np.select([bottom, right, top], [y0 + zero, y0 + (s - w), y1 + zero],
                  default=y1 - (s - 2.0 * w - h))
    return np.stack([x, y, np.full(n, float(eye_z))], axis=1)


def _lattice_points_in(tri: np.ndarray, x0: float, y0: float, grid: float):
    """`(face, points)`: for each triangle of `tri` (m, 3, 3), the points of the plan lattice
    `x = x0 + (i + 0.5) * grid`, `y = y0 + (j + 0.5) * grid` inside its footprint, at the
    triangle's own height there. `face` indexes `tri`. Faces go through in blocks of about
    `_BATCH` points, so a huge floor does not build one huge array."""
    A, B, C = tri[:, 0], tri[:, 1], tri[:, 2]
    foot_lo, foot_hi = tri[:, :, :2].min(axis=1), tri[:, :, :2].max(axis=1)
    i0 = np.ceil((foot_lo[:, 0] - x0) / grid - 0.5).astype(np.int64)
    i1 = np.floor((foot_hi[:, 0] - x0) / grid - 0.5).astype(np.int64)
    j0 = np.ceil((foot_lo[:, 1] - y0) / grid - 0.5).astype(np.int64)
    j1 = np.floor((foot_hi[:, 1] - y0) / grid - 0.5).astype(np.int64)
    ni, nj = np.maximum(i1 - i0 + 1, 0), np.maximum(j1 - j0 + 1, 0)
    count = ni * nj
    ends = np.cumsum(count)

    faces, points = [np.zeros(0, np.int64)], [np.zeros((0, 3))]
    start = 0
    while start < len(tri):
        taken = ends[start - 1] if start else 0
        stop = max(int(np.searchsorted(ends, taken + _BATCH, side="right")), start + 1)
        c = count[start:stop]
        total = int(c.sum())
        if total:
            f = np.repeat(np.arange(start, stop), c)
            local = np.arange(total) - np.repeat(np.cumsum(c) - c, c)
            x = x0 + (i0[f] + local % ni[f] + 0.5) * grid
            y = y0 + (j0[f] + local // ni[f] + 0.5) * grid
            a, b, cc = A[f], B[f], C[f]
            den = (b[:, 1] - cc[:, 1]) * (a[:, 0] - cc[:, 0]) + (cc[:, 0] - b[:, 0]) * (a[:, 1] - cc[:, 1])
            wa = ((b[:, 1] - cc[:, 1]) * (x - cc[:, 0]) + (cc[:, 0] - b[:, 0]) * (y - cc[:, 1])) / den
            wb = ((cc[:, 1] - a[:, 1]) * (x - cc[:, 0]) + (a[:, 0] - cc[:, 0]) * (y - cc[:, 1])) / den
            wc = 1.0 - wa - wb
            inside = (wa >= -_EDGE) & (wb >= -_EDGE) & (wc >= -_EDGE)
            z = wa * a[:, 2] + wb * b[:, 2] + wc * cc[:, 2]
            faces.append(f[inside])
            points.append(np.stack([x, y, z], axis=1)[inside])
        start = stop
    return np.concatenate(faces), np.vstack(points)


def interior_probes(mesh: MeshData, eye: float = 63.0, headroom: float = 83.0,
                    grid: float = 39.37, caster=None) -> np.ndarray:
    """(K, 3) float64 eye-height probe positions, `eye` (63 in = 1.6 m) above ground someone could
    stand on: every upward face (`n_z > 0.9`) whose UPWARD ray from half an inch above it meets
    nothing within `headroom` (83 in = 2.1 m). So a room gets probes and a crawl space does not,
    and nothing is placed under a table, a low slab or a stair above it.

    The ground is sampled on a plan lattice `grid` (39.37 in = 1 m) apart, anchored half a cell in
    from the lower-left corner of the vertices the faces use: the lattice points inside each
    upward face, at the face's height there. A face too small to hold one gets one at its centroid,
    so no upward face with headroom goes without a probe above it. Then one probe is kept per
    lattice cell and `LEVEL` of height (lattice points first), so a floor cut into thousands of
    tiny triangles, or drawn twice, still gets about one probe a metre.

    Probes are not limited to the inside of rooms: an open roof is upward ground with headroom too.
    Reuse the `caster` of `visibility.build_caster(mesh)` when there is one; otherwise one is built.
    The mesh must be in the Validator's frame (`ValueError` if not)."""
    if not grid > 0.0:
        raise ValueError(f"grid must be positive, got {grid!r}")
    check_frame(mesh.positions, "mesh positions")
    up = np.flatnonzero(face_normals(mesh)[:, 2] > UP_NZ)
    if not len(up):
        return np.zeros((0, 3))
    tri = mesh.positions[mesh.face_v[up]]
    x0, y0 = used_bbox(mesh)[0][:2]

    on_face, on_lattice = _lattice_points_in(tri, x0, y0, grid)
    too_small = np.setdiff1d(np.arange(len(up)), on_face)               # no lattice point inside
    candidates = np.vstack([on_lattice, tri[too_small].mean(axis=1)])
    if not len(candidates):
        return np.zeros((0, 3))

    if caster is None:
        caster = build_caster(mesh)
    check_caster(mesh, caster)
    free = np.zeros(len(candidates), dtype=bool)
    for s in range(0, len(candidates), _BATCH):
        origins = candidates[s:s + _BATCH] + [0.0, 0.0, HEADROOM_START]
        _, t = caster.first_hit(origins, np.tile([0.0, 0.0, 1.0], (len(origins), 1)))
        free[s:s + len(origins)] = t > headroom                          # a miss is t = inf
    candidates = candidates[free]
    if not len(candidates):
        return np.zeros((0, 3))

    cell = np.stack([np.floor((candidates[:, 0] - x0) / grid), np.floor((candidates[:, 1] - y0) / grid),
                     np.round(candidates[:, 2] / LEVEL)], axis=1).astype(np.int64)
    _, first = np.unique(cell, axis=0, return_index=True)
    probes = candidates[np.sort(first)]                                 # first come, first kept
    probes[:, 2] += eye
    return probes
