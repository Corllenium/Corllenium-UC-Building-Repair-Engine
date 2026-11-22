"""Unit tests for Stage 5 Outer Facade & Mesh Integrity Verifier (D01-D14) and patch protection."""
from __future__ import annotations

import numpy as np
import pytest

from engine.fixes.patch_protect import detect_piercing_needle_slivers, propagate_coplanar_patch_reachability, purge_piercing_needle_slivers
from engine.model import MeshData
from engine.validate.facade_integrity import verify_facade_and_mesh_integrity


def _make_closed_box(size: float = 200.0, mat_wall: str = "minecraft_concrete_white_-147", mat_floor: str = "minecraft_quartz_block_top_-1") -> MeshData:
    """Create a watertight 200x200x200 in room box with outward-facing normals and 12 triangles."""
    s = size
    verts = np.array(
        [
            [0, 0, 0], [s, 0, 0], [s, s, 0], [0, s, 0],
            [0, 0, s], [s, 0, s], [s, s, s], [0, s, s],
        ],
        dtype=np.float64,
    )
    faces = np.array(
        [
            # bottom (normal -Z)
            [0, 2, 1], [0, 3, 2],
            # top / floor (normal +Z)
            [4, 5, 6], [4, 6, 7],
            # front y=0 (normal -Y)
            [0, 1, 5], [0, 5, 4],
            # back y=s (normal +Y)
            [3, 7, 6], [3, 6, 2],
            # left x=0 (normal -X)
            [0, 4, 7], [0, 7, 3],
            # right x=s (normal +X)
            [1, 2, 6], [1, 6, 5],
        ],
        dtype=np.int64,
    )
    mats = [mat_wall, mat_floor, "minecraft_concrete_white_-146"]
    fmat = np.array([0, 0, 1, 1, 0, 0, 0, 0, 0, 0, 0, 0], dtype=np.int64)
    return MeshData(
        name="test_box",
        mtllib="test.mtl",
        materials=mats,
        positions=verts,
        uvs=np.zeros((1, 2), dtype=np.float64),
        normals=np.zeros((0, 3), dtype=np.float64),
        face_v=faces,
        face_vt=np.zeros_like(faces),
        face_vn=np.full_like(faces, -1),
        face_material=fmat,
        face_line=np.arange(len(faces), dtype=np.int64),
        coord_decimals=4,
        sig_digits=7,
    )


def test_clean_box_passes_all_automated_checks() -> None:
    b = _make_closed_box()
    a = _make_closed_box()
    rep = verify_facade_and_mesh_integrity(b, a, n_probe_dirs=64, n_ext_dirs=64)
    assert rep["automatedPassed"] is True
    assert rep["failedCheckIds"] == []


def test_missing_outer_facade_half_quad_fails_d04_and_d03() -> None:
    b = _make_closed_box()
    a = _make_closed_box()
    # Delete 1 triangle on the front outer wall (simulates D04/D06 diagonal missing half-quad!)
    keep = np.ones(a.n_faces, dtype=bool)
    keep[4] = False
    a.face_v = a.face_v[keep]
    a.face_vt = a.face_vt[keep]
    a.face_vn = a.face_vn[keep]
    a.face_material = a.face_material[keep]
    a.face_line = a.face_line[keep]

    rep = verify_facade_and_mesh_integrity(b, a, n_probe_dirs=64, n_ext_dirs=64)
    assert rep["automatedPassed"] is False
    assert "outer_facade_completeness" in rep["failedCheckIds"]
    c1 = next(c for c in rep["checks"] if c["id"] == "outer_facade_completeness")
    assert len(c1["spots"]) >= 1


def test_piercing_needle_sliver_detected_and_purged_d02() -> None:
    m = _make_closed_box()
    # Attach a razor-thin needle sliver (20 in long, 0.3 in wide -> aspect ~66) jutting off the wall!
    extra_v = np.array([[200.0, 50.0, 50.0], [220.0, 50.0, 50.0], [200.0, 50.3, 50.0]], dtype=np.float64)
    vb = len(m.positions)
    m.positions = np.vstack([m.positions, extra_v])
    m.face_v = np.vstack([m.face_v, np.array([[vb, vb + 1, vb + 2]], dtype=np.int64)])
    m.face_vt = np.vstack([m.face_vt, np.zeros((1, 3), dtype=np.int64)])
    m.face_vn = np.vstack([m.face_vn, np.full((1, 3), -1, dtype=np.int64)])
    m.face_material = np.concatenate([m.face_material, np.array([2], dtype=np.int64)])
    m.face_line = np.concatenate([m.face_line, np.array([99], dtype=np.int64)])

    mask, spots = detect_piercing_needle_slivers(m)
    assert int(mask.sum()) == 1
    assert spots[0]["defectClass"] == "D02"

    cleaned, n_drop = purge_piercing_needle_slivers(m)
    assert n_drop == 1
    assert cleaned.n_faces == 12


def test_floor_texture_override_fails_d09() -> None:
    b = _make_closed_box()
    a = _make_closed_box()
    # Swap quartz floor tile (index 2, 3) to raw concrete (index 2 in mats)
    a.face_material[2] = 2
    a.face_material[3] = 2
    rep = verify_facade_and_mesh_integrity(b, a, n_probe_dirs=64, n_ext_dirs=64)
    assert rep["automatedPassed"] is False
    assert "original_texture_fidelity" in rep["failedCheckIds"]


def test_atomic_coplanar_patch_propagation_rescues_twin_half_quad() -> None:
    m = _make_closed_box()
    # Only one half of the front wall quad (face 4) is marked reachable; face 5 is its diagonal twin
    reach = np.zeros(m.n_faces, dtype=bool)
    reach[4] = True
    out, added = propagate_coplanar_patch_reachability(m, reach, max_hops=2)
    assert added == 1
    assert out[4] and out[5]
