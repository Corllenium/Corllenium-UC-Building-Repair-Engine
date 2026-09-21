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


class RayCaster(Protocol):
    def any_hit(self, origins: np.ndarray, directions: np.ndarray) -> np.ndarray:
        """origins, directions: (R,3). Returns bool (R,)."""
        ...

    def first_hit(self, origins: np.ndarray, directions: np.ndarray) -> tuple[np.ndarray, np.ndarray]:
        """origins, directions: (R,3). Returns (tri int64 (R,) [-1 = miss], t float64 (R,) [inf = miss]).
        `tri` indexes into the `faces` array passed to the constructor."""
        ...


class EmbreeCaster:
    """Wraps `trimesh.ray.ray_pyembree.RayMeshIntersector`. `tri` in `first_hit` indexes into
    the `faces` passed here (the mesh is built with `process=False` so face order is preserved)."""

    def __init__(self, positions: np.ndarray, faces: np.ndarray):
        positions = np.asarray(positions, dtype=np.float64)
        self.faces = np.asarray(faces, dtype=np.int64)
        mesh = trimesh.Trimesh(vertices=positions.astype(np.float32), faces=self.faces, process=False)
        self._rmi = RayMeshIntersector(mesh)

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
