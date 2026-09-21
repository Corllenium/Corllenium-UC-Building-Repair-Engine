from __future__ import annotations

from dataclasses import dataclass

import numpy as np


@dataclass
class MeshData:
    name: str
    positions: np.ndarray
    uvs: np.ndarray
    normals: np.ndarray
    face_v: np.ndarray
    face_vt: np.ndarray
    face_vn: np.ndarray
    face_material: np.ndarray
    face_line: np.ndarray
    materials: list[str]
    mtllib: str | None
    coord_decimals: int
    sig_digits: int
    units: str = "inches"

    @property
    def n_faces(self) -> int:
        return int(self.face_v.shape[0])

    def bbox(self) -> tuple[np.ndarray, np.ndarray]:
        return self.positions.min(axis=0), self.positions.max(axis=0)
