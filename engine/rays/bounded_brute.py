"""Bound the existing float64 oracle by original-face boxes for precision-sensitive pilots."""
import numpy as np

from engine.rays.caster import BruteCaster, _FaceBoundsTree


class BoundedBruteCaster:
    def __init__(self, positions, faces):
        self.positions = np.asarray(positions, dtype=np.float64)
        self.faces = np.asarray(faces, dtype=np.int64)
        triangles = self.positions[self.faces]
        self.tree = _FaceBoundsTree(triangles.min(axis=1), triangles.max(axis=1)) if len(self.faces) else None
        self.search_stats = {'leaf_pairs': 0}

    @staticmethod
    def _intersects(bounds, origins, directions):
        lo, hi = bounds
        # Broad-phase rounding only; the original oracle decides every triangle hit.
        padding = 64 * np.finfo(float).eps * np.maximum(1., np.maximum(np.abs(origins), np.maximum(np.abs(lo), np.abs(hi))))
        lower = np.nextafter(lo - padding - origins, -np.inf)
        upper = np.nextafter(hi + padding - origins, np.inf)
        parallel = directions == 0
        safe = np.where(parallel, 1., directions)
        with np.errstate(over='ignore', invalid='ignore', divide='ignore'):
            a, b = lower / safe, upper / safe
        near = np.nextafter(np.minimum(a, b), -np.inf)
        far = np.nextafter(np.maximum(a, b), np.inf)
        near[parallel], far[parallel] = -np.inf, np.inf
        outside_parallel = (parallel & ((origins < lo - padding) | (origins > hi + padding))).any(axis=1)
        uncertain = np.isnan(near).any(axis=1) | np.isnan(far).any(axis=1)
        return ~outside_parallel & (uncertain | (np.maximum(near.max(axis=1), 0.) <= far.min(axis=1)))

    def _leaves(self, origins, directions):
        if self.tree is None:
            return
        for start in range(0, len(origins), 2048):
            pending = [(self.tree.root, np.arange(start, min(start + 2048, len(origins))))]
            while pending:
                (bounds, left, right), rays = pending.pop()
                rays = rays[self._intersects(bounds, origins[rays], directions[rays])]
                if not len(rays):
                    continue
                if right is None:
                    faces = np.sort(left)
                    self.search_stats['leaf_pairs'] += len(rays) * len(faces)
                    yield rays, faces
                else:
                    pending.extend([(right, rays), (left, rays)])

    def first_hit(self, origins, directions):
        origins, directions = np.asarray(origins, dtype=float), np.asarray(directions, dtype=float)
        face, depth = np.full(len(origins), -1, np.int64), np.full(len(origins), np.inf)
        self.search_stats = {'leaf_pairs': 0}
        for rays, faces in self._leaves(origins, directions):
            local, distance = BruteCaster(self.positions, self.faces[faces]).first_hit(origins[rays], directions[rays])
            found = local >= 0
            candidate = faces[np.maximum(local, 0)]
            better = found & ((distance < depth[rays]) | ((distance == depth[rays]) & ((face[rays] < 0) | (candidate < face[rays]))))
            face[rays[better]], depth[rays[better]] = candidate[better], distance[better]
        return face, depth

    def any_hit(self, origins, directions):
        return self.first_hit(origins, directions)[0] >= 0

    def all_hits(self, origins, directions):
        origins, directions = np.asarray(origins, dtype=float), np.asarray(directions, dtype=float)
        ray_parts, face_parts, depth_parts = [], [], []
        self.search_stats = {'leaf_pairs': 0}
        for rays, faces in self._leaves(origins, directions):
            local, face, depth = BruteCaster(self.positions, self.faces[faces]).all_hits(origins[rays], directions[rays])
            ray_parts.append(rays[local])
            face_parts.append(faces[face])
            depth_parts.append(depth)
        return (np.concatenate(ray_parts).astype(np.int64) if ray_parts else np.zeros(0, np.int64),
                np.concatenate(face_parts).astype(np.int64) if face_parts else np.zeros(0, np.int64),
                np.concatenate(depth_parts) if depth_parts else np.zeros(0, float))
