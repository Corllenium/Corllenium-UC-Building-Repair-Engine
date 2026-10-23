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
    physical_quanta: tuple[float, float, float] | None = None

    def __post_init__(self):
        if self.physical_quanta is not None:
            values = np.asarray(self.physical_quanta, dtype=float)
            if values.shape != (3,) or not np.isfinite(values).all() or (values <= 0).any():
                raise ValueError("physical_quanta must contain three finite positive axis steps")
            self.physical_quanta = tuple(float(value) for value in values)

    @property
    def n_faces(self) -> int:
        return int(self.face_v.shape[0])

    def bbox(self) -> tuple[np.ndarray, np.ndarray]:
        return self.positions.min(axis=0), self.positions.max(axis=0)
