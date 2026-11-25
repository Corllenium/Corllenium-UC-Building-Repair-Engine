"""TDD tests for engine.fixes.tjunction_stitch (Cross-Plane T-Junction Stitcher)."""
from __future__ import annotations

import numpy as np

from engine.fixes.tjunction_stitch import stitch_cross_plane_tjunctions
from engine.model import MeshData
from engine.pipeline import analyse_topology


def _make_mesh(positions: np.ndarray, face_v: np.ndarray) -> MeshData:
    n = len(face_v)
    uvs = np.column_stack([positions[:, 0] / 100.0, (positions[:, 1] + positions[:, 2]) / 100.0]).astype(np.float64)
    return MeshData(
        name="test_tjunc",
        mtllib="materials.mtl",
        materials=["mat0"],
        positions=np.asarray(positions, dtype=np.float64),
        uvs=uvs,
        normals=np.zeros((0, 3), dtype=np.float64),
        face_v=np.asarray(face_v, dtype=np.int64),
        face_vt=np.asarray(face_v, dtype=np.int64).copy(),
        face_vn=np.full((n, 3), -1, dtype=np.int64),
        face_material=np.zeros(n, dtype=np.int64),
        face_line=np.arange(1, n + 1, dtype=np.int64),
        coord_decimals=3,
        sig_digits=7,
    )


def test_stitch_cross_plane_tjunctions_splits_orthogonal_wall_floor_seam_without_moving_vertices() -> None:
    # Floor quad in Z=0 plane from X=0..100, Y=0..100 (2 triangles)
    # Orthogonal vertical wall in Y=0 plane standing from X=50..100, Z=0..80.
    # Vertex 4 at (50, 0, 0) sits right in the middle of floor edge (0 -> 1) = (0,0,0)->(100,0,0)!
    positions = np.array(
        [
            [0.0, 0.0, 0.0],     # 0
            [100.0, 0.0, 0.0],   # 1
            [100.0, 100.0, 0.0], # 2
            [0.0, 100.0, 0.0],   # 3
            [50.0, 0.0, 0.0],    # 4 -> T-vertex on floor edge (0, 1)
            [50.0, 0.0, 80.0],   # 5
            [100.0, 0.0, 80.0],  # 6
        ],
        dtype=np.float64,
    )
    face_v = np.array(
        [
            [0, 1, 2],  # floor tri 0 -> edge (0,1) has T-vertex 4!
            [0, 2, 3],  # floor tri 1
            [4, 1, 6],  # wall tri 0
            [4, 6, 5],  # wall tri 1
        ],
        dtype=np.int64,
    )
    mesh = _make_mesh(positions, face_v)
    topo_before = analyse_topology(mesh)
    assert len(topo_before.t_vertices) >= 1

    stitched, report = stitch_cross_plane_tjunctions(mesh, search_tol_in=0.05)
    assert report["edges_split"] >= 1
    assert stitched.n_faces == 5  # floor tri 0 split into 2 conformal tris
    # Zero vertex displacement (AGENTS.md §4 compliance)
    assert np.allclose(stitched.positions[: len(positions)], positions, atol=1e-9)

    topo_after = analyse_topology(stitched)
    assert len(topo_after.t_vertices) == 0


def test_stitch_cross_plane_tjunctions_respects_min_altitude_sliver_guard() -> None:
    # A floor triangle whose third vertex is only 0.02 in off the split edge would produce a sub-2mm sliver
    positions = np.array(
        [
            [0.0, 0.0, 0.0],
            [100.0, 0.0, 0.0],
            [50.0, 0.02, 0.0],   # razor-thin height 0.02 in (< 2mm = 0.079 in)
            [50.0, 0.0, 0.0],    # T-vertex
            [50.0, 0.0, 50.0],
            [100.0, 0.0, 50.0],
        ],
        dtype=np.float64,
    )
    face_v = np.array([[0, 1, 2], [3, 1, 5], [3, 5, 4]], dtype=np.int64)
    mesh = _make_mesh(positions, face_v)
    stitched, report = stitch_cross_plane_tjunctions(mesh, search_tol_in=0.05, min_subtri_alt_in=0.079)
    assert report["edges_split"] == 0
    assert stitched.n_faces == mesh.n_faces
