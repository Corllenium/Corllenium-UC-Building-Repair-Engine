"""Ray casters against a triangle mesh. `trimesh`/`embreex` are imported ONLY in this module.

Callers must recentre `positions` (e.g. to the model's bbox centre) before constructing a
caster: coordinates in the real models sit near 24,000 inches, and `EmbreeCaster` stores
vertices as float32 internally, which loses precision far from the origin.
"""
from __future__ import annotations

from typing import Protocol

import numpy as np
import trimesh
from trimesh.ray.ray_pyembree import RayMeshIntersector

_CHUNK = 256

#: Relative slack for the "is this hit point also inside THAT triangle" test that recovers hits
#: embree's multi-hit walk skips (see `EmbreeCaster.all_hits`), as a fraction of the mesh's
#: bounding-box diagonal. 1e-6 matches trimesh's own ray offset, so it is exactly the width of the
#: band embree steps over; the guard's own `depth_tol` is thousands of times larger.
_COINCIDENT_REL_TOL = 1e-6


class RayCaster(Protocol):
    def any_hit(self, origins: np.ndarray, directions: np.ndarray) -> np.ndarray:
        """origins, directions: (R,3). Returns bool (R,)."""
        ...

    def first_hit(self, origins: np.ndarray, directions: np.ndarray) -> tuple[np.ndarray, np.ndarray]:
        """origins, directions: (R,3). Returns (tri int64 (R,) [-1 = miss], t float64 (R,) [inf = miss]).
        `tri` indexes into the `faces` array passed to the constructor."""
        ...

    def all_hits(self, origins: np.ndarray, directions: np.ndarray) -> tuple[np.ndarray, np.ndarray, np.ndarray]:
        """EVERY surface each ray meets, not just the nearest: three parallel arrays
        `(ray_index int64 (H,), tri int64 (H,), t float64 (H,))`, one entry per hit, `tri` indexing
        the `faces` passed to the constructor. A ray that hits nothing contributes no entry, so
        `H` is unrelated to `len(origins)`; the order within one ray is unspecified.

        Two triangles that overlap in the SAME plane are both reported, at the same `t` -- that
        ambiguity (which one a first-hit cast happens to return) is precisely what the guard's
        z-fight tie test reads."""
        ...


class EmbreeCaster:
    """Wraps `trimesh.ray.ray_pyembree.RayMeshIntersector`. `tri` in `first_hit` indexes into
    the `faces` passed here (the mesh is built with `process=False` so face order is preserved)."""

    def __init__(self, positions: np.ndarray, faces: np.ndarray):
        positions = np.asarray(positions, dtype=np.float64)
        self.faces = np.asarray(faces, dtype=np.int64)
        self._positions = positions
        mesh = trimesh.Trimesh(vertices=positions.astype(np.float32), faces=self.faces, process=False)
        self._rmi = RayMeshIntersector(mesh)
        extent = positions.max(axis=0) - positions.min(axis=0) if len(positions) else np.zeros(3)
        self._coincident_tol = max(1e-8, float(np.linalg.norm(extent)) * _COINCIDENT_REL_TOL)
        self._vertex_faces = None   # built on first all_hits, never for a plain render

    def any_hit(self, origins: np.ndarray, directions: np.ndarray) -> np.ndarray:
        origins = np.asarray(origins, dtype=np.float64)
        directions = np.asarray(directions, dtype=np.float64)
        return np.asarray(self._rmi.intersects_any(origins, directions), dtype=np.bool_)

    def first_hit(self, origins: np.ndarray, directions: np.ndarray) -> tuple[np.ndarray, np.ndarray]:
        origins = np.asarray(origins, dtype=np.float64)
        directions = np.asarray(directions, dtype=np.float64)
        loc, iray, itri = self._rmi.intersects_location(origins, directions, multiple_hits=False)
        n = len(origins)
        tri = np.full(n, -1, dtype=np.int64)
        t = np.full(n, np.inf, dtype=np.float64)
        if len(iray):
            tri[iray] = itri
            t[iray] = np.einsum("ij,ij->i", loc - origins[iray], directions[iray])
        return tri, t

    def all_hits(self, origins: np.ndarray, directions: np.ndarray) -> tuple[np.ndarray, np.ndarray, np.ndarray]:
        """See `RayCaster.all_hits`. Two passes, because embree alone cannot answer this:

        1. `intersects_location(multiple_hits=True)`, which walks the ray surface by surface.
        2. A recovery pass for the hits that walk SKIPS. It advances the ray past each hit by
           `max(1e-8, mesh.scale * 1e-6)`, so two triangles at the SAME depth can never both be
           reported -- it returns one of them and moves on. That is exactly the z-fight overlap
           the guard's tie test exists to recognise (measured on file B: faces 2654 and 73 share
           an edge, lie in one plane, overlap, and carry different materials), so the second one
           is recovered analytically: each reported hit POINT is re-tested against the other
           triangles that SHARE A VERTEX with the triangle it hit, and any that contains it
           (within `_coincident_tol` of its plane and of its edges) is reported at the same `t`.

        LIMIT: a coincident triangle sharing NO vertex with the one embree returned is still
        missed. Overlapping faces in a SketchUp export come from one face loop and do share
        vertices, but a pair welded from two independently drawn loops need not; the tie test
        then sees a one-member tie set and reports the pixel under its real class, which is the
        safe direction (a missed tie is a reported failure, never a tolerated change)."""
        origins = np.asarray(origins, dtype=np.float64)
        directions = np.asarray(directions, dtype=np.float64)
        if not len(origins) or not len(self.faces):
            return (np.zeros(0, np.int64), np.zeros(0, np.int64), np.zeros(0, np.float64))

        loc, iray, itri = self._rmi.intersects_location(origins, directions, multiple_hits=True)
        iray = np.asarray(iray, dtype=np.int64)
        itri = np.asarray(itri, dtype=np.int64)
        if not len(iray):
            return iray, itri, np.zeros(0, np.float64)
        loc = np.asarray(loc, dtype=np.float64)
        t = np.einsum("ij,ij->i", loc - origins[iray], directions[iray])

        extra_hit, extra_tri = self._coincident_with(itri, loc)
        if len(extra_hit):
            iray = np.concatenate([iray, iray[extra_hit]])
            itri = np.concatenate([itri, extra_tri])
            t = np.concatenate([t, t[extra_hit]])
        return iray, itri, t

    def _vertex_face_table(self) -> tuple[np.ndarray, np.ndarray]:
        """`(starts, faces_by_vertex)`: `faces_by_vertex[starts[v]:starts[v + 1]]` are the faces
        using vertex `v`. Built once, on the first `all_hits` call -- a plain render never pays
        for it."""
        if self._vertex_faces is None:
            n_vertices = len(self._positions)
            v = self.faces.reshape(-1)
            f = np.repeat(np.arange(len(self.faces), dtype=np.int64), 3)
            order = np.argsort(v, kind="stable")
            counts = np.bincount(v, minlength=n_vertices)
            starts = np.concatenate([[0], np.cumsum(counts)]).astype(np.int64)
            self._vertex_faces = (starts, f[order])
        return self._vertex_faces

    def _coincident_with(self, itri: np.ndarray, points: np.ndarray) -> tuple[np.ndarray, np.ndarray]:
        """`(hit_index, tri)` pairs: for each reported hit, the OTHER triangles sharing one of its
        vertices that also contain its hit point. `hit_index` indexes into `itri`/`points`."""
        starts, faces_by_vertex = self._vertex_face_table()
        corner_v = self.faces[itri]                                  # (H, 3)
        lo, hi = starts[corner_v], starts[corner_v + 1]              # (H, 3)
        counts = (hi - lo).reshape(-1)                               # (3H,)
        total = int(counts.sum())
        if not total:
            return np.zeros(0, np.int64), np.zeros(0, np.int64)

        # ragged gather: one flat run of faces_by_vertex per (hit, corner)
        offsets = np.concatenate([[0], np.cumsum(counts)])[:-1]
        pos = np.arange(total, dtype=np.int64) - np.repeat(offsets, counts)
        cand_tri = faces_by_vertex[np.repeat(lo.reshape(-1), counts) + pos]
        cand_hit = np.repeat(np.repeat(np.arange(len(itri), dtype=np.int64), 3), counts)

        keep = cand_tri != itri[cand_hit]
        cand_hit, cand_tri = cand_hit[keep], cand_tri[keep]
        if not len(cand_hit):
            return cand_hit, cand_tri
        pair = np.unique(np.stack([cand_hit, cand_tri], axis=1), axis=0)
        cand_hit, cand_tri = pair[:, 0], pair[:, 1]

        inside = self._contains(cand_tri, points[cand_hit])
        return cand_hit[inside], cand_tri[inside]

    def _contains(self, tri_index: np.ndarray, points: np.ndarray) -> np.ndarray:
        """Is each point inside its triangle -- within `_coincident_tol` of the triangle's plane
        AND no further than `_coincident_tol` outside any of its three edges?"""
        tol = self._coincident_tol
        T = self._positions[self.faces[tri_index]]                   # (C, 3, 3)
        a, b, c = T[:, 0], T[:, 1], T[:, 2]
        normal = np.cross(b - a, c - a)
        length = np.linalg.norm(normal, axis=1)
        good = length > 0.0
        unit = np.zeros_like(normal)
        unit[good] = normal[good] / length[good, None]
        on_plane = np.abs(np.einsum("ij,ij->i", points - a, unit)) <= tol

        out = good & on_plane
        for p0, p1 in ((a, b), (b, c), (c, a)):
            edge = p1 - p0
            edge_len = np.linalg.norm(edge, axis=1)
            side = np.einsum("ij,ij->i", np.cross(edge, points - p0), unit)
            with np.errstate(invalid="ignore", divide="ignore"):
                distance = np.where(edge_len > 0.0, side / np.where(edge_len > 0.0, edge_len, 1.0), -np.inf)
            out &= distance >= -tol
        return out


class ReusableCaster:
    """Wraps a `caster_factory` to build at most one underlying caster per distinct `(positions,
    faces)` array-object PAIR (identity, `is` -- not equality), returning the cached instance for
    repeat calls with the SAME objects. A caller that renders many views of the SAME geometry (a
    26-view guard pass, `guard_feedback`'s per-round `after` render, `one_sided_holes`) was
    building a fresh `EmbreeCaster` -- and its embree BVH -- once per view; that construction, not
    the ray casts themselves, was the dominant cost of the ~30s-per-object pipeline. A new pair of
    objects (a different round's kept faces, a different mesh) still builds fresh: this is a
    size-1 cache, not a general memoiser. Results are bit-identical to building fresh every call
    -- only construction is skipped, never a ray-cast."""

    def __init__(self, factory=EmbreeCaster):
        self._factory = factory
        self._positions = None
        self._faces = None
        self._caster = None

    def __call__(self, positions: np.ndarray, faces: np.ndarray):
        if positions is not self._positions or faces is not self._faces:
            self._positions, self._faces = positions, faces
            self._caster = self._factory(positions, faces)
        return self._caster


class BruteCaster:
    """Moller-Trumbore ray/triangle intersection, ported from `spike/04_front_hit_oracle.py`
    (`brute`) and generalised to a per-ray direction. float64, chunked by 256 rays, hit when
    `t > 1e-9`. Used as a correctness oracle for `EmbreeCaster`, not for performance."""

    def __init__(self, positions: np.ndarray, faces: np.ndarray):
        positions = np.asarray(positions, dtype=np.float64)
        self.faces = np.asarray(faces, dtype=np.int64)
        self._tri = positions[self.faces]  # (M, 3, 3)

    def any_hit(self, origins: np.ndarray, directions: np.ndarray) -> np.ndarray:
        tri, _t = self.first_hit(origins, directions)
        return tri >= 0

    def all_hits(self, origins: np.ndarray, directions: np.ndarray) -> tuple[np.ndarray, np.ndarray, np.ndarray]:
        """See `RayCaster.all_hits`. The analytic test needs no walk along the ray and so no
        recovery pass: two triangles overlapping in one plane both satisfy it, at the same `t`."""
        origins = np.asarray(origins, dtype=np.float64)
        directions = np.asarray(directions, dtype=np.float64)
        rays, tris, ts = [], [], []
        T = self._tri
        e1, e2 = T[:, 1] - T[:, 0], T[:, 2] - T[:, 0]
        for s in range(0, len(origins), _CHUNK):
            o, d = origins[s:s + _CHUNK], directions[s:s + _CHUNK]
            h = np.cross(d[:, None, :], e2[None, :, :])
            a = np.einsum("mk,rmk->rm", e1, h)
            good = np.abs(a) > 1e-12
            inv = np.where(good, 1.0 / np.where(good, a, 1.0), 0.0)
            sv = o[:, None, :] - T[None, :, 0, :]
            u = np.einsum("rmk,rmk->rm", sv, h) * inv
            q = np.cross(sv, e1[None, :, :])
            v = np.einsum("rmk,rmk->rm", q, d[:, None, :]) * inv
            t = np.einsum("rmk,mk->rm", q, e2) * inv
            hit = good & (u >= 0) & (v >= 0) & (u + v <= 1) & (t > 1e-9)
            r_idx, m_idx = np.nonzero(hit)
            rays.append(r_idx + s)
            tris.append(m_idx)
            ts.append(t[r_idx, m_idx])
        return (np.concatenate(rays).astype(np.int64) if rays else np.zeros(0, np.int64),
                np.concatenate(tris).astype(np.int64) if tris else np.zeros(0, np.int64),
                np.concatenate(ts).astype(np.float64) if ts else np.zeros(0, np.float64))

    def first_hit(self, origins: np.ndarray, directions: np.ndarray) -> tuple[np.ndarray, np.ndarray]:
        origins = np.asarray(origins, dtype=np.float64)
        directions = np.asarray(directions, dtype=np.float64)
        n = len(origins)
        tri = np.full(n, -1, dtype=np.int64)
        t_out = np.full(n, np.inf, dtype=np.float64)
        T = self._tri
        e1, e2 = T[:, 1] - T[:, 0], T[:, 2] - T[:, 0]
        for s in range(0, n, _CHUNK):
            o, d = origins[s:s + _CHUNK], directions[s:s + _CHUNK]
            h = np.cross(d[:, None, :], e2[None, :, :])  # (chunk, M, 3)
            a = np.einsum("mk,rmk->rm", e1, h)  # (chunk, M)
            good = np.abs(a) > 1e-12
            inv = np.where(good, 1.0 / np.where(good, a, 1.0), 0.0)
            sv = o[:, None, :] - T[None, :, 0, :]  # (chunk, M, 3)
            u = np.einsum("rmk,rmk->rm", sv, h) * inv
            q = np.cross(sv, e1[None, :, :])  # (chunk, M, 3)
            v = np.einsum("rmk,rmk->rm", q, d[:, None, :]) * inv
            t = np.einsum("rmk,mk->rm", q, e2) * inv
            hit = good & (u >= 0) & (v >= 0) & (u + v <= 1) & (t > 1e-9)
            tt = np.where(hit, t, np.inf)
            idx = np.argmin(tt, axis=1)
            tmin = tt[np.arange(len(o)), idx]
            found = np.isfinite(tmin)
            t_out[s:s + _CHUNK] = tmin
            tri[s:s + _CHUNK] = np.where(found, idx, -1)
        return tri, t_out
