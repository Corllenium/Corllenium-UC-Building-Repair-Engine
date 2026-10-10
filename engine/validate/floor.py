"""The owner's visibility floor, measured (AGENTS.md section 5, the owner's decision of 2026-10-10).

No removed or covered face may show more than `VISIBLE_FLOOR_PX` pixels at `FLOOR_IN_PER_PX` inches per pixel from
any Validator viewpoint, on every line of sight and from both sides (Unity draws both, `_Cull = 0`). This module is
the measure: an ID buffer of a mesh along one viewpoint's lines, centred on one face, at that resolution, and the
pixels where that face is the nearest surface (`face_visible_pixels`; the pixels themselves, block by block, are
`face_pixels`). Counts are per face and per viewpoint, never summed over viewpoints (ruling V2-R1).

HOW A VIEW IS DRAWN.

* A DIRECTION (a viewer infinitely far off at `-dir`, looking along `dir`) is drawn ORTHOGRAPHICALLY: a square
  pixel grid of pitch `px` on the plane through the face's centroid square to `dir`, one pixel centre on the
  centroid. Each pixel's ray comes from outside the mesh's bounding box along `dir`.
* A CAMERA OR PROBE (a point `e`) is drawn in PERSPECTIVE, as a cube map round `e`: six square image planes at unit
  distance, one along the line from `e` to the face's centroid and the other five square to it, each with an angular
  pitch of `px / D`, where `D` is the distance from `e` to the face's centroid. So a pixel is `px` wide AT THE FACE
  (ruling: "the pixel size taken at the face"), and a face that wraps round a probe (the floor under it) is drawn
  whole, on as many of the six planes as it reaches. A ray belongs to the one plane its direction is most along
  (ties to the first), so no pixel is drawn twice.

WHAT "NEAREST" MEANS. A pixel shows the face when the pixel's ray crosses the face (in float64, inside the triangle,
its edges included) and Embree's first hit along the same ray is not more than `ZFIGHT` in front of that crossing.
Two layers that close are both drawn in Unity (the same z-fight distance `visibility.EPS_ORIGIN` uses), and a ray
Embree lets slip past the face's own edge still counts the face: the crossing is the face's own float64 geometry,
never a float32 tie. A view edge-on to the face (`|cos| <= visibility.MIN_COS`) and a face with no area show nothing.

Meshes are in the Validator's frame (`sampling.recentred`), like everything here. Written for the Validator and
independent of the code it judges (see `engine.validate`).
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Iterator

import numpy as np

from engine.model import MeshData
from engine.validate.sampling import check_frame, used_bbox
from engine.validate.visibility import EPS_ORIGIN, MIN_COS, build_caster, check_caster

#: The owner's floor: a removed or covered face may show at most this many pixels from any one viewpoint.
VISIBLE_FLOOR_PX = 4
#: ...at this many inches per pixel, measured at the face.
FLOOR_IN_PER_PX = 0.02
#: A face this close behind the nearest surface along a pixel's ray is drawn there too (it z-fights).
ZFIGHT = EPS_ORIGIN
#: Pixel rays cast in one block.
_BLOCK = 1 << 19
#: Slack, in pixels, on the rasteriser's row intervals: it offers a pixel centre a hair outside the outline, and the
#: exact float64 test on the face decides.
_RASTER_SLACK = 1e-6
#: A clipped polygon's corner this close to the eye's plane (relative to the face's distance) is not projected.
_NEAR = 1e-9


@dataclass(frozen=True, eq=False)
class Viewpoint:
    """Where the Validator looks from: `kind` "direction" (`at` the unit look direction; the viewer is infinitely far
    off at `-at`) or "point" (`at` the camera or probe position, in the Validator's frame)."""
    kind: str
    at: np.ndarray

    def __post_init__(self):
        if self.kind not in ("direction", "point"):
            raise ValueError(f"a viewpoint is a 'direction' or a 'point', not {self.kind!r}")
        at = np.asarray(self.at, dtype=np.float64).reshape(3)
        if self.kind == "direction":
            length = float(np.linalg.norm(at))
            if not length > 0.0:
                raise ValueError("a view direction has zero length")
            at = at / length
        object.__setattr__(self, "at", at)

    @classmethod
    def direction(cls, d) -> "Viewpoint":
        return cls("direction", d)

    @classmethod
    def point(cls, p) -> "Viewpoint":
        return cls("point", p)


@dataclass(frozen=True, eq=False)
class PixelBlock:
    """Pixels of one face, from one viewpoint, where the face is the nearest surface: `points` (k, 3) where each
    pixel's ray crosses the face; `toward` (k, 3) the unit vector from there to the viewer; `reach` (k,) how far the
    viewer is (inf for a direction); `ij` (k, 2) the pixel's column and row on its image plane, `plane` (k,) which
    plane (always 0 for a direction; 0-5 of the cube map for a point); `t` (k,) the ray's distance to the face."""
    points: np.ndarray
    toward: np.ndarray
    reach: np.ndarray
    ij: np.ndarray
    plane: np.ndarray
    t: np.ndarray

    def __len__(self) -> int:
        return int(len(self.points))


@dataclass(frozen=True, eq=False)
class _Plane:
    """One image plane: pixel centre (i, j) is the ray `origin(i, j)` along `dir(i, j)`. For an orthographic view
    `centre`, `right` and `up` place the pixel on the plane through the face's centroid; for a cube-map plane `axis`,
    `right` and `up` give the direction `axis + s right + t up` with `(s, t) = (i, j) * pitch`."""
    kind: str
    index: int
    pitch: float
    poly: np.ndarray                 # (m, 2) the face's outline on this plane, in its (s, t) coordinates
    right: np.ndarray
    up: np.ndarray
    axis: np.ndarray                 # the look direction (ortho) or the plane's axis (cube map)
    centre: np.ndarray               # the face's centroid (ortho) or the eye (cube map)
    back: float = 0.0                # ortho: how far behind the plane the rays start (outside the bounding box)


def basis(u: np.ndarray) -> tuple[np.ndarray, np.ndarray]:
    """`(right, up)`: unit vectors that with the viewing direction `u` make a right-handed frame, `up` as near the
    world's +z as the view allows (+y when looking nearly straight up or down)."""
    u = np.asarray(u, dtype=np.float64)
    ref = np.array([0.0, 0.0, 1.0]) if abs(u[2]) < 0.99 else np.array([0.0, 1.0, 0.0])
    right = np.cross(u, ref)
    right /= np.linalg.norm(right)
    return right, np.cross(right, u)


def _clip(poly: np.ndarray, normal: np.ndarray, offset: float) -> np.ndarray:
    """The part of the convex polygon `poly` (m, 3) where `x . normal >= offset` (Sutherland-Hodgman, one plane)."""
    if not len(poly):
        return poly
    d = poly @ normal - offset
    out = []
    for k in range(len(poly)):
        a, b, da, db = poly[k], poly[(k + 1) % len(poly)], d[k], d[(k + 1) % len(poly)]
        if da >= 0.0:
            out.append(a)
        if (da >= 0.0) != (db >= 0.0):
            out.append(a + (b - a) * (da / (da - db)))
    return np.asarray(out, dtype=np.float64).reshape(-1, 3)


def _planes(tri: np.ndarray, vp: Viewpoint, px: float, lo: np.ndarray, hi: np.ndarray) -> list[_Plane]:
    """The image planes a face `tri` (3, 3) is drawn on from `vp`, each with the face's outline on it."""
    centroid = tri.mean(axis=0)
    if vp.kind == "direction":
        u = vp.at
        right, up = basis(u)
        rel = tri - centroid
        poly = np.stack([rel @ right, rel @ up], axis=1)
        corners = np.array([[x, y, z] for x in (lo[0], hi[0]) for y in (lo[1], hi[1]) for z in (lo[2], hi[2])])
        back = float(max(((corners - centroid) @ -u).max(), 0.0)) + 1.0
        return [_Plane("ortho", 0, px, poly, right, up, u, centroid, back)]
    e = vp.at
    D = float(np.linalg.norm(centroid - e))
    if not D > 0.0:
        return []
    a0 = (centroid - e) / D
    r0, u0 = basis(a0)
    axes = [(a0, r0, u0), (-a0, -r0, u0), (r0, -a0, u0), (-r0, a0, u0), (u0, r0, -a0), (-u0, r0, a0)]
    rel = tri - e
    planes = []
    for k, (a, b, c) in enumerate(axes):
        poly = rel
        for n in (a - b, a + b, a - c, a + c):                    # the pyramid of directions mostly along `a`
            poly = _clip(poly, n, 0.0)
        if len(poly) < 3:
            continue
        depth = poly @ a
        if (depth <= _NEAR * D).any():
            poly = _clip(poly, a, _NEAR * D)
            if len(poly) < 3:
                continue
            depth = poly @ a
        st = np.stack([(poly @ b) / depth, (poly @ c) / depth], axis=1)
        planes.append(_Plane("cube", k, px / D, st, b, c, a, e))
    return planes


def _bit_reversed(n: int) -> np.ndarray:
    """0..n-1 in bit-reversed order: a coarse spread of rows first, then the rows between them."""
    if n <= 1:
        return np.arange(n)
    bits = int(np.ceil(np.log2(n)))
    k = np.arange(1 << bits, dtype=np.int64)
    rev = np.zeros_like(k)
    for b in range(bits):
        rev |= ((k >> b) & 1) << (bits - 1 - b)
    return rev[rev < n]


def _raster_rows(poly: np.ndarray, pitch: float):
    """`(rows, lo, hi)`: the pixel rows `j` the convex outline `poly` (m, 2) reaches, in bit-reversed order, and for
    each the columns `lo..hi` whose centres `(i, j) * pitch` lie inside it (give or take `_RASTER_SLACK`)."""
    g = poly / pitch
    j0, j1 = int(np.ceil(g[:, 1].min() - _RASTER_SLACK)), int(np.floor(g[:, 1].max() + _RASTER_SLACK))
    if j1 < j0:
        return np.zeros(0, np.int64), np.zeros(0, np.int64), np.zeros(0, np.int64)
    rows = np.arange(j0, j1 + 1, dtype=np.int64)
    y = rows.astype(np.float64)
    a, b = g, np.roll(g, -1, axis=0)
    ylo, yhi = np.minimum(a[:, 1], b[:, 1]), np.maximum(a[:, 1], b[:, 1])
    span = (y[:, None] >= ylo[None] - _RASTER_SLACK) & (y[:, None] <= yhi[None] + _RASTER_SLACK)
    dy = b[:, 1] - a[:, 1]
    flat = np.abs(dy) < 1e-15
    with np.errstate(divide="ignore", invalid="ignore"):
        x = a[None, :, 0] + (y[:, None] - a[None, :, 1]) * (b[:, 0] - a[:, 0])[None] / np.where(flat, 1.0, dy)[None]
    x_lo = np.where(span & ~flat[None], x, np.inf).min(axis=1)
    x_hi = np.where(span & ~flat[None], x, -np.inf).max(axis=1)
    # a flat edge lying on the row gives both its ends
    on = span & flat[None]
    x_lo = np.minimum(x_lo, np.where(on, np.minimum(a[:, 0], b[:, 0])[None], np.inf).min(axis=1))
    x_hi = np.maximum(x_hi, np.where(on, np.maximum(a[:, 0], b[:, 0])[None], -np.inf).max(axis=1))
    lo = np.ceil(x_lo - _RASTER_SLACK)
    hi = np.floor(x_hi + _RASTER_SLACK)
    ok = np.isfinite(lo) & np.isfinite(hi) & (hi >= lo)
    order = _bit_reversed(len(rows))
    order = order[ok[order]]
    return rows[order], lo[order].astype(np.int64), hi[order].astype(np.int64)


def _cube_axes(e_axis: np.ndarray) -> np.ndarray:
    """The cube map's six axes in the order `_planes` numbers its planes: a ray belongs to the first it is most
    along."""
    a0 = e_axis
    r0, u0 = basis(a0)
    return np.stack([a0, -a0, r0, -r0, u0, -u0])


def face_pixels(mesh: MeshData, face: int, viewpoint: Viewpoint, caster=None, *, px: float = FLOOR_IN_PER_PX
                ) -> Iterator[PixelBlock]:
    """The pixels of `face` that it shows from `viewpoint` (see the module docstring), as blocks of at most
    `_BLOCK` candidate rays, the rows of each image plane in bit-reversed order (a coarse spread first), so a caller
    that only needs to know whether there are more than a few may stop early. `caster` is `build_caster(mesh)`,
    built here when not given. Deterministic."""
    if not px > 0.0:
        raise ValueError(f"px must be positive, got {px!r}")
    check_frame(mesh.positions, "mesh positions")
    face = int(face)
    if not 0 <= face < mesh.n_faces:
        raise ValueError(f"face {face} is not a face of the mesh ({mesh.n_faces} faces)")
    tri = mesh.positions[mesh.face_v[face]].astype(np.float64)
    a, b, c = tri
    n = np.cross(b - a, c - a)
    nn = float(n @ n)
    longest2 = max(float((b - a) @ (b - a)), float((c - a) @ (c - a)), float((c - b) @ (c - b)))
    if not nn > 0.0 or np.sqrt(nn) <= 1e-9 * longest2:
        return
    unit_n = n / np.sqrt(nn)
    if viewpoint.kind == "direction" and abs(float(unit_n @ viewpoint.at)) <= MIN_COS:
        return
    if viewpoint.kind == "point":
        check_frame(viewpoint.at[None], "viewpoint")
        if abs(float((viewpoint.at - a) @ unit_n)) <= 1e-12:
            return                                                   # the eye lies in the face's plane
    if caster is None:
        caster = build_caster(mesh)
    check_caster(mesh, caster)
    lo, hi = used_bbox(mesh)
    cube = _cube_axes((tri.mean(axis=0) - viewpoint.at) / np.linalg.norm(tri.mean(axis=0) - viewpoint.at)) \
        if viewpoint.kind == "point" else None
    for plane in _planes(tri, viewpoint, px, lo, hi):
        rows, c_lo, c_hi = _raster_rows(plane.poly, plane.pitch)
        count = c_hi - c_lo + 1
        start = 0
        while start < len(rows):
            ends = np.cumsum(count[start:])
            stop = start + max(1, int(np.searchsorted(ends, _BLOCK, side="right")))
            cnt = count[start:stop]
            j = np.repeat(rows[start:stop], cnt)
            i = np.repeat(c_lo[start:stop], cnt) + (np.arange(int(cnt.sum())) - np.repeat(np.cumsum(cnt) - cnt, cnt))
            start = stop
            s, t = i * plane.pitch, j * plane.pitch
            if plane.kind == "ortho":
                d = np.broadcast_to(plane.axis, (len(i), 3))
                origin = plane.centre + s[:, None] * plane.right + t[:, None] * plane.up - plane.back * plane.axis
            else:
                d = plane.axis + s[:, None] * plane.right + t[:, None] * plane.up
                d = d / np.linalg.norm(d, axis=1, keepdims=True)
                mine = np.argmax(d @ cube.T, axis=1) == plane.index
                i, j, d = i[mine], j[mine], d[mine]
                origin = np.broadcast_to(plane.centre, d.shape)
            den = d @ n
            with np.errstate(divide="ignore", invalid="ignore"):
                tf = ((a - origin) @ n) / den
            ok = (np.abs(den) > MIN_COS * np.sqrt(nn)) & np.isfinite(tf) & (tf > 0.0)
            q = origin + np.where(ok, tf, 0.0)[:, None] * d
            # barycentric weights by areas, in float64 (edges included)
            wb = (np.cross(q - a, c - a) @ n) / nn
            wc = (np.cross(b - a, q - a) @ n) / nn
            ok &= (wb >= 0.0) & (wc >= 0.0) & (wb + wc <= 1.0)
            idx = np.flatnonzero(ok)
            if not len(idx):
                continue
            o_k, d_k = np.ascontiguousarray(origin[idx]), np.ascontiguousarray(d[idx])
            _, t_hit = caster.first_hit(o_k, d_k)
            shown = tf[idx] <= t_hit + ZFIGHT
            idx = idx[shown]
            if not len(idx):
                continue
            pts = q[idx]
            if viewpoint.kind == "direction":
                toward = np.broadcast_to(-viewpoint.at, pts.shape).copy()
                reach = np.full(len(idx), np.inf)
            else:
                v = viewpoint.at - pts
                reach = np.linalg.norm(v, axis=1)
                toward = v / np.maximum(reach, 1e-300)[:, None]
            yield PixelBlock(points=pts, toward=toward, reach=reach, ij=np.stack([i[idx], j[idx]], axis=1),
                             plane=np.full(len(idx), plane.index, dtype=np.int64), t=tf[idx])


def face_visible_pixels(before_mesh: MeshData, face: int, viewpoint: Viewpoint, caster=None, *,
                        px: float = FLOOR_IN_PER_PX) -> int:
    """How many pixels, at `px` (0.02 in) per pixel, `face` of `before_mesh` shows from `viewpoint`: the pixels of an
    ID buffer of the mesh along that viewpoint's lines, centred on the face, where the face is the nearest surface
    (see the module docstring). From either side of the face. `caster`: `build_caster(before_mesh)`, to reuse."""
    return int(sum(len(block) for block in face_pixels(before_mesh, face, viewpoint, caster, px=px)))
