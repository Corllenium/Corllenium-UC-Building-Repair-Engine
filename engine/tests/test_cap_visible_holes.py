"""TDD tests for engine.fixes.cap_visible_holes (Planar Visible-Hole Auto-Capper)."""
from __future__ import annotations

import numpy as np

from engine.fixes.cap_visible_holes import cap_visible_planar_holes
from engine.model import MeshData
from engine.validate.hole_detector import detect_new_mesh_holes


def _make_mesh(positions: np.ndarray, face_v: np.ndarray, materials: list[str] | None = None) -> MeshData:
    n = len(face_v)
    mats = materials or ["wall_concrete"]
    uvs = np.column_stack([positions[:, 0] / 100.0, positions[:, 2] / 100.0]).astype(np.float64)
    return MeshData(
        name="test_hole",
        mtllib="materials.mtl",
        materials=mats,
        positions=np.asarray(positions, dtype=np.float64),
        uvs=uvs,
        normals=np.zeros((0, 3), dtype=np.float64),
        face_v=np.asarray(face_v, dtype=np.int64),
        face_vt=np.asarray(face_v, dtype=np.int64).copy(),
        face_vn=np.full((n, 3), -1, dtype=np.int64),
        face_material=np.zeros(n, dtype=np.int64),
        face_line=np.arange(1, n + 1, dtype=np.int64),
        coord_decimals=2,
        sig_digits=7,
    )


def _wall_grid_3x3() -> tuple[np.ndarray, np.ndarray]:
    """3x3 planar vertical wall in Y=0 plane, X in [0, 300], Z in [0, 300], facing -Y."""
    xs = [0.0, 100.0, 200.0, 300.0]
    zs = [0.0, 100.0, 200.0, 300.0]
    verts = [[x, 0.0, z] for z in zs for x in xs]
    faces = []
    for iz in range(3):
        for ix in range(3):
            v00 = iz * 4 + ix
            v10 = v00 + 1
            v01 = v00 + 4
            v11 = v01 + 1
            faces.append([v00, v10, v11])
            faces.append([v00, v11, v01])
    return np.asarray(verts, dtype=np.float64), np.asarray(faces, dtype=np.int64)


def test_hole_detector_emits_closed_loops_and_capper_closes_triangle_and_quad_holes() -> None:
    verts, faces = _wall_grid_3x3()
    before = _make_mesh(verts, faces)

    # Drop 1 triangle from center cell (cell (1,1) = faces index 8,9 -> drop face 8 = triangle hole)
    after_tri = _make_mesh(verts, np.delete(faces, [8], axis=0))
    rep_tri = detect_new_mesh_holes(before, after_tri, visible_only=False)
    assert rep_tri["holeCount"] == 1
    assert "loops" in rep_tri and len(rep_tri["loops"]) == 1
    assert rep_tri["loops"][0]["closed"] is True
    assert len(rep_tri["loops"][0]["ordered_vertices"]) == 3

    capped_tri, stats_tri = cap_visible_planar_holes(before, after_tri, visible_only=False)
    assert stats_tri["loops_capped"] == 1
    assert stats_tri["tris_added"] == 1
    assert stats_tri["holes_after"] == 0
    # E8 strict rule: NO new vertices invented
    assert len(capped_tri.positions) == len(after_tri.positions)
    assert detect_new_mesh_holes(before, capped_tri, visible_only=False)["holeCount"] == 0

    # Drop BOTH triangles of center cell (faces 8 & 9 -> 4-edge quad hole)
    after_quad = _make_mesh(verts, np.delete(faces, [8, 9], axis=0))
    capped_quad, stats_quad = cap_visible_planar_holes(before, after_quad, visible_only=False)
    assert stats_quad["loops_capped"] == 1
    assert stats_quad["tris_added"] == 2
    assert stats_quad["holes_after"] == 0
    assert len(capped_quad.positions) == len(after_quad.positions)
    assert detect_new_mesh_holes(before, capped_quad, visible_only=False)["holeCount"] == 0


def test_cap_visible_holes_rejects_non_planar_loop() -> None:
    verts, faces = _wall_grid_3x3()
    before = _make_mesh(verts, faces)
    verts_bent = verts.copy()
    # Bend one corner of the center quad 10 inches out of plane
    verts_bent[5, 1] = 10.0
    after_bent = _make_mesh(verts_bent, np.delete(faces, [8, 9], axis=0))
    capped, stats = cap_visible_planar_holes(before, after_bent, visible_only=False, max_plane_dev_in=0.15)
    assert stats["loops_capped"] == 0
    assert capped.n_faces == after_bent.n_faces
