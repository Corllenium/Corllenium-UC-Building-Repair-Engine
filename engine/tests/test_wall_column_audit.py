"""TDD tests for engine.detectors.wall_column_audit."""
from __future__ import annotations

import numpy as np

from engine.detectors.wall_column_audit import audit_wall_column_health
from engine.model import MeshData


def _closed_box_faces(x0: float, x1: float, y0: float, y1: float, z0: float, z1: float) -> tuple[np.ndarray, np.ndarray]:
    p = np.array(
        [
            [x0, y0, z0], [x1, y0, z0], [x1, y1, z0], [x0, y1, z0],
            [x0, y0, z1], [x1, y0, z1], [x1, y1, z1], [x0, y1, z1],
        ],
        dtype=np.float64,
    )
    f = np.array(
        [
            [0, 2, 1], [0, 3, 2],  # -Z
            [4, 5, 6], [4, 6, 7],  # +Z
            [0, 1, 5], [0, 5, 4],  # -Y
            [2, 3, 7], [2, 7, 6],  # +Y
            [0, 4, 7], [0, 7, 3],  # -X
            [1, 2, 6], [1, 6, 5],  # +X
        ],
        dtype=np.int64,
    )
    return p, f


def _make_mesh(p: np.ndarray, f: np.ndarray) -> MeshData:
    n = len(f)
    return MeshData(
        name="audit_box",
        mtllib="materials.mtl",
        materials=["wall"],
        positions=p,
        uvs=np.zeros((0, 2), dtype=np.float64),
        normals=np.zeros((0, 3), dtype=np.float64),
        face_v=f,
        face_vt=np.full((n, 3), -1, dtype=np.int64),
        face_vn=np.full((n, 3), -1, dtype=np.int64),
        face_material=np.zeros(n, dtype=np.int64),
        face_line=np.arange(1, n + 1, dtype=np.int64),
        coord_decimals=2,
        sig_digits=7,
    )


def test_audit_detects_trapped_cavity_rib_open_cap_and_verifies_closed_solid_group() -> None:
    # A clean solid column 24 in x 24 in x 140 in (Z-up inches)
    p, f = _closed_box_faces(0.0, 24.0, 0.0, 24.0, 0.0, 140.0)
    clean_mesh = _make_mesh(p, f)
    rep_clean = audit_wall_column_health(clean_mesh, face_groups=["Column_01"] * len(f))
    assert rep_clean["counts"]["trapped_cavity_faces"] == 0
    assert rep_clean["counts"]["open_wall_edges"] == 0
    assert rep_clean["counts"]["nonmanifold_wall_edges"] == 0
    assert rep_clean["per_group_solids"]["Column_01"]["watertight"] is True
    assert rep_clean["per_group_solids"]["Column_01"]["signed_volume"] > 0.0

    # Add an internal trapped vertical rib inside the column at X=12 in AND remove the top cap (+Z faces 2,3)
    rib_p = np.array([[12.0, 0.0, 0.0], [12.0, 24.0, 0.0], [12.0, 24.0, 140.0], [12.0, 0.0, 140.0]], dtype=np.float64)
    p_bad = np.vstack([p, rib_p])
    f_bad = np.vstack([np.delete(f, [2, 3], axis=0), np.array([[8, 9, 10], [8, 10, 11]], dtype=np.int64)])
    bad_mesh = _make_mesh(p_bad, f_bad)
    rep_bad = audit_wall_column_health(bad_mesh, face_groups=["Column_01"] * len(f_bad))
    assert rep_bad["counts"]["trapped_cavity_faces"] >= 2
    assert rep_bad["counts"]["open_wall_edges"] >= 4
    assert rep_bad["per_group_solids"]["Column_01"]["watertight"] is False
