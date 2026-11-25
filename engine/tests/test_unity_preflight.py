"""TDD tests for engine.validate.unity_preflight (Near-Coplanar Z-Fight Guard & Unity 6 Gate)."""
from __future__ import annotations

import numpy as np

from engine.model import MeshData
from engine.validate.unity_preflight import (
    detect_near_coplanar_zfight,
    resolve_near_coplanar_zfight,
    run_unity_preflight_gate,
)


def _box_mesh(x0: float, x1: float, y0: float, y1: float, z0: float, z1: float, *, flip_face0: bool = False, units: str = "metres") -> MeshData:
    """Closed outward-wound axis-aligned box."""
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
    if flip_face0:
        f[0] = f[0, [0, 2, 1]]
    uvs = np.array([[0.0, 0.0], [1.0, 0.0], [1.0, 1.0], [0.0, 1.0]], dtype=np.float64)
    fvt = np.tile(np.array([[0, 1, 2]], dtype=np.int64), (len(f), 1))
    return MeshData(
        name="box",
        mtllib="materials.mtl",
        materials=["mat_finish"],
        positions=p,
        uvs=uvs,
        normals=np.zeros((0, 3), dtype=np.float64),
        face_v=f,
        face_vt=fvt,
        face_vn=np.full((len(f), 3), -1, dtype=np.int64),
        face_material=np.zeros(len(f), dtype=np.int64),
        face_line=np.arange(1, len(f) + 1, dtype=np.int64),
        coord_decimals=4,
        sig_digits=7,
        units=units,
    )


def test_detect_and_resolve_near_coplanar_zfight_drops_buried_2mm_duplicate() -> None:
    # Wall finish face at Y=0 (X=0..100, Z=0..100), buried concrete patch 0.08 in (~2mm) behind at Y=0.08
    positions = np.array(
        [
            [0.0, 0.0, 0.0], [100.0, 0.0, 0.0], [100.0, 0.0, 100.0], [0.0, 0.0, 100.0],
            [10.0, 0.08, 10.0], [90.0, 0.08, 10.0], [90.0, 0.08, 90.0], [10.0, 0.08, 90.0],
        ],
        dtype=np.float64,
    )
    face_v = np.array([[0, 1, 2], [0, 2, 3], [4, 5, 6], [4, 6, 7]], dtype=np.int64)
    face_mat = np.array([0, 0, 1, 1], dtype=np.int64)
    mesh = MeshData(
        name="zfight_test",
        mtllib="materials.mtl",
        materials=["minecraft_quartz_block_side_-1", "minecraft_concrete_white_-1"],
        positions=positions,
        uvs=np.zeros((0, 2), dtype=np.float64),
        normals=np.zeros((0, 3), dtype=np.float64),
        face_v=face_v,
        face_vt=np.full((4, 3), -1, dtype=np.int64),
        face_vn=np.full((4, 3), -1, dtype=np.int64),
        face_material=face_mat,
        face_line=np.arange(1, 5, dtype=np.int64),
        coord_decimals=3,
        sig_digits=7,
        units="inches",
    )

    rep = detect_near_coplanar_zfight(mesh, min_dist_in=0.01, max_dist_in=0.25)
    assert rep["pair_count"] >= 2

    cleaned, rstats = resolve_near_coplanar_zfight(mesh, min_dist_in=0.01, max_dist_in=0.25)
    assert rstats["faces_dropped"] == 2
    assert cleaned.n_faces == 2
    assert set(cleaned.face_material.tolist()) == {0}  # finish face kept, buried concrete dropped
    assert detect_near_coplanar_zfight(cleaned, min_dist_in=0.01, max_dist_in=0.25)["pair_count"] == 0


def test_unity_preflight_gate_passes_clean_metre_box_and_fails_reversed_face() -> None:
    # Clean 4m x 3m x 4m Y-up metre box
    good = _box_mesh(0.0, 4.0, 0.0, 3.0, 0.0, 4.0, flip_face0=False, units="metres")
    gate_ok = run_unity_preflight_gate(good, expected_units="metres", min_alt_mm=2.0)
    assert gate_ok["passed"] is True
    assert gate_ok["checks"]["zero_reversed_normals"]["passed"] is True
    assert gate_ok["checks"]["zero_area_faces"]["passed"] is True
    assert gate_ok["checks"]["topology_valid"]["passed"] is True

    bad = _box_mesh(0.0, 4.0, 0.0, 3.0, 0.0, 4.0, flip_face0=True, units="metres")
    gate_bad = run_unity_preflight_gate(bad, expected_units="metres", min_alt_mm=2.0)
    assert gate_bad["passed"] is False
    assert gate_bad["checks"]["zero_reversed_normals"]["passed"] is False
