"""Remove faces from a mesh while remembering where each surviving face came from.

Positions, UVs, normals, and materials are left untouched (no re-indexing, no compaction) so
vertex/UV/normal ids stay comparable to the original mesh across versions -- only the per-face
arrays (`face_v`, `face_vt`, `face_vn`, `face_material`, `face_line`) are subset."""
from __future__ import annotations

from dataclasses import replace

import numpy as np

from engine.model import MeshData


def remove_faces(mesh: MeshData, drop: np.ndarray) -> tuple[MeshData, np.ndarray]:
    """Drop the faces where `drop` (bool, `(mesh.n_faces,)`) is True.

    Returns `(new_mesh, source_face)`: `new_mesh` has every per-face array (`face_v`, `face_vt`,
    `face_vn`, `face_material`, `face_line`) subset to the survivors, in their original relative
    order; `positions`/`uvs`/`normals`/`materials` are the SAME arrays/list as `mesh`, not
    re-indexed or compacted. `source_face` (int64, `(new_mesh.n_faces,)`) maps a new face index to
    its original face index, so `new_mesh.face_v[i] == mesh.face_v[source_face[i]]` (and likewise
    for every other per-face field) for every `i`.

    `drop` all-False is the identity: the same faces, in the same order, `source_face ==
    arange(mesh.n_faces)`.
    """
    drop = np.asarray(drop, dtype=bool)
    if drop.shape != (mesh.n_faces,):
        raise ValueError(f"drop must have shape ({mesh.n_faces},), got {drop.shape}")

    keep = ~drop
    source_face = np.nonzero(keep)[0].astype(np.int64)
    new_mesh = replace(
        mesh,
        face_v=mesh.face_v[keep],
        face_vt=mesh.face_vt[keep],
        face_vn=mesh.face_vn[keep],
        face_material=mesh.face_material[keep],
        face_line=mesh.face_line[keep],
    )
    return new_mesh, source_face
