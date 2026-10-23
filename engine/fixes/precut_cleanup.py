"""Exact duplicate-only route for pre-cut floors; no visibility heuristics or repair stages."""
from __future__ import annotations

from dataclasses import dataclass

import numpy as np

from engine.fixes.remove import remove_faces
from engine.model import MeshData


DISABLED = ("solidify", "holes", "material_preparation", "recolor", "fragments", "slits",
            "normal_unification", "partial_overlap", "hidden", "merge")


class CoverageError(ValueError):
    pass


@dataclass
class CleanupResult:
    mesh: MeshData
    source_faces: np.ndarray
    removed_to_survivor: dict[int, int]
    coverage: dict
    executed: tuple[str, ...]
    disabled: tuple[str, ...] = DISABLED


def _face_keys(mesh: MeshData) -> list[tuple]:
    for values in (mesh.positions, mesh.uvs, mesh.normals):
        if not np.isfinite(values).all():
            raise CoverageError("nonfinite corner attributes")
    for indices, count, minimum in ((mesh.face_v, len(mesh.positions), 0),
                                     (mesh.face_vt, len(mesh.uvs), -1),
                                     (mesh.face_vn, len(mesh.normals), -1)):
        if indices.shape != (mesh.n_faces, 3) or (indices < minimum).any() or (indices >= count).any():
            raise CoverageError("invalid corner indices")
    if ((mesh.face_material < -1) | (mesh.face_material >= len(mesh.materials))).any():
        raise CoverageError("invalid material index")
    keys = []
    for f in range(mesh.n_faces):
        corners = []
        for v, t, n in zip(mesh.face_v[f], mesh.face_vt[f], mesh.face_vn[f]):
            corners.append((tuple(mesh.positions[v]), tuple(mesh.uvs[t]) if t >= 0 else (),
                            tuple(mesh.normals[n]) if n >= 0 else ()))
        # Cyclic permutations preserve winding. Reflections never enter this key.
        oriented = min(tuple(corners[k:] + corners[:k]) for k in range(3))
        material = int(mesh.face_material[f])
        keys.append((material >= 0, mesh.materials[material] if material >= 0 else "", oriented))
    return keys


def verify_exact_coverage(before: MeshData, after: MeshData) -> dict:
    original, candidate = set(_face_keys(before)), set(_face_keys(after))
    missing, added = original - candidate, candidate - original
    if missing or added:
        raise CoverageError(f"missing {len(missing)} oriented appearance triangles; added {len(added)}")
    return {"exact_coverage": True, "unique_oriented_appearance_triangles": len(original),
            "missing": 0, "added": 0, "method": "exact corner values, cyclic winding, material names; no tolerances"}


def cleanup(mesh: MeshData, *, stages=("exact_duplicates",)) -> CleanupResult:
    stages = tuple(stages)
    if any(s != "exact_duplicates" for s in stages) or len(set(stages)) != len(stages):
        raise ValueError(f"unsupported or repeated stage request: {stages}")
    keys = _face_keys(mesh)
    seen, removed = {}, {}
    if stages:
        for i, key in enumerate(keys):
            if key in seen:
                removed[i] = seen[key]
            else:
                seen[key] = i
    drop = np.zeros(mesh.n_faces, bool)
    drop[list(removed)] = True
    candidate, source_faces = remove_faces(mesh, drop)
    coverage = verify_exact_coverage(mesh, candidate)
    return CleanupResult(candidate, source_faces, removed, coverage, stages)
