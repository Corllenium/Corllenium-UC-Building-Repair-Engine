"""Unit tests for universal building/floor repair helpers in engine.fixes.building_repair."""
from __future__ import annotations

import numpy as np
import pytest

from engine.fixes.building_repair import (
    REPAIR_STAGE_ORDER,
    cluster_coplanar_faces,
    compact_mesh,
    normalize_enabled_stages,
    remove_coplanar_overlaps,
    restore_missing_visible_wall_faces,
)
from engine.model import MeshData
from engine.topo.planes import face_normals


def _make_mesh(
    positions: np.ndarray,
    face_v: np.ndarray,
    face_material: np.ndarray,
    materials: list[str],
    uvs: np.ndarray | None = None,
    face_vt: np.ndarray | None = None,
) -> MeshData:
    n_faces = len(face_v)
    if uvs is None:
        uvs = np.array([[0.0, 0.0], [1.0, 0.0], [0.0, 1.0]], dtype=np.float64)
    if face_vt is None:
        face_vt = np.tile(np.array([[0, 1, 2]], dtype=np.int64), (n_faces, 1))
    normals = np.zeros((0, 3), dtype=np.float64)
    face_vn = np.full((n_faces, 3), -1, dtype=np.int64)
    return MeshData(
        name="test_floor",
        mtllib="materials.mtl",
        materials=list(materials),
        positions=np.asarray(positions, dtype=np.float64),
        uvs=np.asarray(uvs, dtype=np.float64),
        normals=normals,
        face_v=np.asarray(face_v, dtype=np.int64),
        face_vt=np.asarray(face_vt, dtype=np.int64),
        face_vn=face_vn,
        face_material=np.asarray(face_material, dtype=np.int64),
        face_line=np.arange(1, n_faces + 1, dtype=np.int64),
        coord_decimals=2,
        sig_digits=7,
    )


def test_cluster_coplanar_faces_groups_across_half_inch_rounding_boundary() -> None:
    positions = np.array(
        [
            [0.0, 23536.498, 0.0],
            [100.0, 23536.498, 0.0],
            [0.0, 23536.498, 100.0],
            [0.0, 23536.504, 0.0],
            [20.0, 23536.504, 0.0],
            [0.0, 23536.504, 20.0],
        ],
        dtype=np.float64,
    )
    face_v = np.array([[0, 1, 2], [3, 4, 5]], dtype=np.int64)
    fn = face_normals(positions, face_v, np.ones(2, dtype=bool))
    clusters = cluster_coplanar_faces(positions, face_v, fn, np.ones(2, dtype=bool))
    assert len(clusters) == 1
    assert sorted(clusters[0][1]) == [0, 1]


def test_remove_coplanar_overlaps_drops_buried_minority_material_patch() -> None:
    positions = np.array(
        [
            [0.0, 23536.504, 0.0],
            [100.0, 23536.504, 0.0],
            [100.0, 23536.504, 100.0],
            [0.0, 23536.504, 100.0],
            [10.0, 23536.498, 10.0],
            [30.0, 23536.498, 10.0],
            [10.0, 23536.498, 30.0],
        ],
        dtype=np.float64,
    )
    face_v = np.array([[0, 1, 2], [0, 2, 3], [4, 5, 6]], dtype=np.int64)
    face_mat = np.array([0, 0, 1], dtype=np.int64)
    mesh = _make_mesh(positions, face_v, face_mat, ["mat_wall", "mat_buried"])
    cleaned, n_dropped = remove_coplanar_overlaps(mesh, overlap_ratio=0.10)
    assert n_dropped == 1
    assert cleaned.n_faces == 2
    assert list(cleaned.face_material) == [0, 0]


def test_compact_mesh_strips_unreferenced_vertices_and_uvs() -> None:
    positions = np.array(
        [
            [999.0, 999.0, 999.0],
            [0.0, 0.0, 0.0],
            [10.0, 0.0, 0.0],
            [0.0, 10.0, 0.0],
            [888.0, 888.0, 888.0],
        ],
        dtype=np.float64,
    )
    uvs = np.array(
        [
            [9.0, 9.0],
            [0.0, 0.0],
            [1.0, 0.0],
            [0.0, 1.0],
            [8.0, 8.0],
        ],
        dtype=np.float64,
    )
    face_v = np.array([[1, 2, 3]], dtype=np.int64)
    face_vt = np.array([[1, 2, 3]], dtype=np.int64)
    mesh = _make_mesh(positions, face_v, np.array([0]), ["mat0"], uvs=uvs, face_vt=face_vt)
    rings = {0: {"outer": [1, 2, 3], "inners": []}}
    compacted, rings_out = compact_mesh(mesh, rings)
    assert len(compacted.positions) == 3
    assert len(compacted.uvs) == 3
    assert compacted.face_v.tolist() == [[0, 1, 2]]
    assert compacted.face_vt.tolist() == [[0, 1, 2]]
    assert rings_out[0]["outer"] == [0, 1, 2]


def test_remove_coplanar_overlaps_clips_partial_overlap_without_losing_wall_area() -> None:
    positions = np.array(
        [
            [0.0, 23500.0, 0.0],
            [60.0, 23500.0, 0.0],
            [60.0, 23500.0, 60.0],
            [0.0, 23500.0, 60.0],
            [30.0, 23500.0, 0.0],
            [100.0, 23500.0, 0.0],
            [100.0, 23500.0, 60.0],
        ],
        dtype=np.float64,
    )
    face_v = np.array([[0, 1, 2], [0, 2, 3], [4, 5, 6]], dtype=np.int64)
    face_mat = np.array([0, 0, 1], dtype=np.int64)
    mesh = _make_mesh(positions, face_v, face_mat, ["mat_dom", "mat_part"])
    cleaned, n_mod = remove_coplanar_overlaps(mesh, overlap_ratio=0.10)
    assert n_mod == 1
    assert 1 in set(cleaned.face_material.tolist())


def test_restore_missing_visible_wall_faces_recovers_dropped_wall_polygon() -> None:
    positions = np.array(
        [
            [0.0, 23500.0, 0.0],
            [50.0, 23500.0, 0.0],
            [50.0, 23500.0, 50.0],
            [0.0, 23500.0, 50.0],
        ],
        dtype=np.float64,
    )
    ref_fv = np.array([[0, 1, 2], [0, 2, 3]], dtype=np.int64)
    ref_mesh = _make_mesh(positions, ref_fv, np.array([0, 0]), ["mat_wall"])
    rep_mesh = _make_mesh(positions, np.array([[0, 1, 2]], dtype=np.int64), np.array([0]), ["mat_wall"])
    vis_mask = np.array([True, True], dtype=bool)
    restored, n_rest = restore_missing_visible_wall_faces(ref_mesh, rep_mesh, vis_mask, min_missing_area=20.0)
    assert n_rest == 1
    assert restored.n_faces >= 2


def test_normalize_enabled_stages_validates_and_filters() -> None:
    all_stages = normalize_enabled_stages(None)
    assert all_stages == frozenset(REPAIR_STAGE_ORDER)
    assert "cavity_liners" in all_stages
    assert "restore_visible_surfaces" in all_stages

    subset = normalize_enabled_stages(["prepare_materials", "coplanar_overlaps", "merge"])
    assert subset == frozenset({"prepare_materials", "coplanar_overlaps", "merge"})

    with pytest.raises(ValueError, match="Unknown building repair stage"):
        normalize_enabled_stages(["not_a_real_stage"])


