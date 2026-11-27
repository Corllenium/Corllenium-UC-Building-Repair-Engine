"""Tests for Real-Model Engine v2 per-floor builder helpers."""
from __future__ import annotations

import numpy as np
from pathlib import Path

from engine.fixes.building_repair import remove_coplanar_overlaps
from engine.model import MeshData
from tools.build_real_v2_floor import (
    _build_error_overlay_payload,
    _drop_degenerate_faces,
    _resolve_texture_file,
    _summarize_audit_full,
    ckpt17_to_blender_zup_metres,
    ckpt17_to_gltf_yup_metres,
    drop_phantom_bridges,
    normalize_uv_tile_offsets,
    resolve_and_copy_textures,
    resolve_residual_double_layers,
)


def _make_mesh(positions: np.ndarray, face_v: np.ndarray, materials: list[str], face_material: np.ndarray) -> MeshData:
    n_f = len(face_v)
    return MeshData(
        name="test",
        mtllib=None,
        positions=np.asarray(positions, dtype=np.float64),
        uvs=np.array([[0.0, 0.0], [1.0, 0.0], [1.0, 1.0]], dtype=np.float64),
        normals=np.zeros((0, 3), dtype=np.float64),
        materials=list(materials),
        face_v=np.asarray(face_v, dtype=np.int64),
        face_vt=np.tile(np.array([[0, 1, 2]], dtype=np.int64), (n_f, 1)),
        face_vn=np.full((n_f, 3), -1, dtype=np.int64),
        face_material=np.asarray(face_material, dtype=np.int64),
        face_line=np.zeros(n_f, dtype=np.int64),
        coord_decimals=4,
        sig_digits=4,
    )


def test_ckpt17_to_blender_zup_metres_det_positive_and_unit_scale() -> None:
    pts_in = np.array([[100.0, 200.0, 50.0]], dtype=np.float64)
    out = ckpt17_to_blender_zup_metres(pts_in)
    assert np.allclose(out, [[-2.54, -5.08, 1.27]], atol=1e-6)
    # Determinant of diag(-1, -1, +1) is +1 (preserves winding / outward normals)
    mat = np.diag([-1.0, -1.0, 1.0])
    assert np.linalg.det(mat) == 1.0


def test_ckpt17_to_gltf_yup_metres_matches_blender_export_transform() -> None:
    pts_in = np.array([[100.0, 200.0, 50.0]], dtype=np.float64)
    zup = ckpt17_to_blender_zup_metres(pts_in)
    # Blender export_scene.gltf(export_yup=True) maps (X_b, Y_b, Z_b) -> (X_b, Z_b, -Y_b)
    expected = np.column_stack([zup[:, 0], zup[:, 2], -zup[:, 1]])
    actual = ckpt17_to_gltf_yup_metres(pts_in)
    assert np.allclose(actual, expected, atol=1e-6)
    assert np.allclose(actual, [[-2.54, 1.27, 5.08]], atol=1e-6)


def test_build_error_overlay_payload_records_v1_vs_v2_diffs() -> None:
    pos = np.array(
        [
            [0.0, 0.0, 0.0],
            [100.0, 0.0, 0.0],
            [100.0, 100.0, 0.0],
            [0.0, 0.0, 0.0],
            [100.0, 0.0, 0.0],
            [100.0, 100.0, 0.0],
        ],
        dtype=np.float64,
    )
    before = _make_mesh(pos[:3], np.array([[0, 1, 2]], dtype=np.int64), ["quartz_block_top"], np.array([0], dtype=np.int64))
    v1_bad = _make_mesh(pos, np.array([[0, 1, 2], [3, 4, 5]], dtype=np.int64), ["quartz_block_top"], np.array([0, 0], dtype=np.int64))
    v2_clean = _make_mesh(pos[:3], np.array([[0, 1, 2]], dtype=np.int64), ["quartz_block_top"], np.array([0], dtype=np.int64))
    v1_tuple = _summarize_audit_full("V1", before, v1_bad)
    v2_tuple = _summarize_audit_full("V2", before, v2_clean)
    payload = _build_error_overlay_payload("CHTM", "Floor_4F", "chtm_5ft_floor_obj", before, v1_bad, v1_tuple, v2_clean, v2_tuple, phantom_tris_v2=0)
    assert payload["version"] == 2
    assert payload["v1"]["counts"]["flicker_same"] >= 2
    assert payload["v2"]["counts"]["flicker_same"] == 0
    assert len(payload["v1"]["trisByKind"]["flicker_same"]) >= 9
    assert any(item["kind"] == "flicker_same" and item["status"] == "fixed" for item in payload["v1ErrorList"])


def test_resolve_and_copy_textures_prefers_valid_png(tmp_path: Path) -> None:
    raw_dir = tmp_path / "raw"
    v1_dir = tmp_path / "v1"
    raw_dir.mkdir()
    (v1_dir / "textures").mkdir(parents=True)
    png_bytes = b"\x89PNG\r\n\x1a\nfake"
    (v1_dir / "textures" / "texture_0067_minecraft_concrete_green_-1.png").write_bytes(png_bytes)

    raw_mtl = raw_dir / "floor.mtl"
    raw_mtl.write_text(
        "newmtl mat_green\nKd 1 1 1\nd 1\nmap_Kd -s 1 1 1 ../../../textures/texture_0067_minecraft_concrete_green_-1.png\n",
        encoding="utf-8",
    )

    out_mtl = tmp_path / "out" / "floor.v2.mtl"
    out_tex = tmp_path / "out" / "textures"
    copied = resolve_and_copy_textures(raw_mtl, v1_dir, None, out_mtl, out_tex)

    assert copied == {"mat_green": "texture_0067_minecraft_concrete_green_-1.png"}
    assert (out_tex / "texture_0067_minecraft_concrete_green_-1.png").read_bytes() == png_bytes
    assert "map_Kd textures/texture_0067_minecraft_concrete_green_-1.png" in out_mtl.read_text(encoding="utf-8")


def test_resolve_texture_file_falls_back_to_stripped_name(tmp_path: Path) -> None:
    dash_tex = tmp_path / "dash" / "tex"
    dash_tex.mkdir(parents=True)
    target = dash_tex / "minecraft_concrete_green_-1.png"
    target.write_bytes(b"png")

    found = _resolve_texture_file("../../../textures/texture_0067_minecraft_concrete_green_-1.png", [tmp_path / "dash"])
    assert found == target


def test_remove_coplanar_overlaps_outer_priority_single_layer() -> None:
    # Two coplanar opposite-normal faces at z=0: interior concrete (0, +z) vs outer facade (1, -z)
    pos = np.array(
        [
            [0.0, 0.0, 0.0],
            [10.0, 0.0, 0.0],
            [10.0, 10.0, 0.0],
            [0.0, 0.0, 0.0],
            [10.0, 10.0, 0.0],
            [10.0, 0.0, 0.0],
        ],
        dtype=np.float64,
    )
    fv = np.array([[0, 1, 2], [3, 4, 5]], dtype=np.int64)
    mesh = _make_mesh(pos, fv, ["concrete_buried", "facade_green"], np.array([0, 1], dtype=np.int64))
    out, dropped = remove_coplanar_overlaps(
        mesh,
        dist_tol=0.04,
        rebuild=True,
        visible=np.array([True, True], dtype=bool),
        outer_priority=np.array([False, True], dtype=bool),
        allow_same_plane_back_to_back=False,
    )
    assert dropped == 1
    assert out.n_faces == 1
    assert out.materials[int(out.face_material[0])] == "facade_green"


def test_drop_phantom_bridges_removes_unbacked_air_triangle() -> None:
    pos = np.array(
        [
            [0.0, 0.0, 0.0],
            [12.0, 0.0, 0.0],
            [0.0, 12.0, 0.0],
            [0.0, 0.0, 48.0],
            [12.0, 0.0, 48.0],
            [0.0, 12.0, 48.0],
        ],
        dtype=np.float64,
    )
    raw = _make_mesh(pos[:3], np.array([[0, 1, 2]], dtype=np.int64), ["mat"], np.array([0], dtype=np.int64))
    cand = _make_mesh(pos, np.array([[0, 1, 2], [3, 4, 5]], dtype=np.int64), ["mat"], np.array([0, 0], dtype=np.int64))
    cleaned, n_dropped = drop_phantom_bridges(raw, cand)
    assert n_dropped == 1
    assert cleaned.n_faces == 1


def test_drop_degenerate_faces_removes_zero_area_tri() -> None:
    pos = np.array(
        [
            [0.0, 0.0, 0.0],
            [10.0, 0.0, 0.0],
            [0.0, 10.0, 0.0],
            [20.0, 0.0, 0.0],
            [25.0, 0.0, 0.0],
            [30.0, 0.0, 0.0],
        ],
        dtype=np.float64,
    )
    mesh = _make_mesh(pos, np.array([[0, 1, 2], [3, 4, 5]], dtype=np.int64), ["mat"], np.array([0, 0], dtype=np.int64))
    cleaned, n_dropped = _drop_degenerate_faces(mesh)
    assert n_dropped == 1
    assert cleaned.n_faces == 1


def test_resolve_residual_double_layers_removes_exact_duplicate_pair() -> None:
    pos = np.array(
        [
            [0.0, 0.0, 0.0],
            [24.0, 0.0, 0.0],
            [24.0, 24.0, 0.0],
            [0.0, 0.0, 0.0],
            [24.0, 0.0, 0.0],
            [24.0, 24.0, 0.0],
        ],
        dtype=np.float64,
    )
    mesh = _make_mesh(pos, np.array([[0, 1, 2], [3, 4, 5]], dtype=np.int64), ["a", "b"], np.array([0, 1], dtype=np.int64))
    out, n_drop = resolve_residual_double_layers(
        mesh,
        outer_mask=np.array([True, False], dtype=bool),
        vis_mask=np.array([True, True], dtype=bool),
    )
    assert n_drop == 1
    assert out.n_faces == 1
    assert out.materials[int(out.face_material[0])] == "a"


def test_normalize_uv_tile_offsets_preserves_fractional_tiling() -> None:
    pos = np.array([[0.0, 0.0, 0.0], [10.0, 0.0, 0.0], [10.0, 10.0, 0.0]], dtype=np.float64)
    mesh = _make_mesh(pos, np.array([[0, 1, 2]], dtype=np.int64), ["mat"], np.array([0], dtype=np.int64))
    mesh.uvs = np.array([[104.25, -48.5], [105.75, -48.5], [105.75, -47.0]], dtype=np.float64)
    out, n_shifted, max_abs = normalize_uv_tile_offsets(mesh)
    assert n_shifted == 1
    assert max_abs <= 2.0
    tri_uv = out.uvs[out.face_vt[0]]
    assert np.allclose(tri_uv, [[0.25, 0.5], [1.75, 0.5], [1.75, 2.0]], atol=1e-6)
