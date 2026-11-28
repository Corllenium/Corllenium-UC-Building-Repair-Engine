"""Tests for Real-Model Engine v2 per-floor builder helpers."""
from __future__ import annotations

import numpy as np
from pathlib import Path

from engine.fixes.building_repair import (
    _triangulate_clipped_face,
    detect_internal_voxel_stack_plates,
    remove_coplanar_overlaps,
)
from engine.fixes.patch_protect import detect_piercing_needle_slivers
from engine.model import MeshData
from engine.rays.caster import EmbreeCaster
from engine.topo.planes import face_normals
from engine.validate.facade_integrity import _coverage_7pt
from tools.build_real_v2_floor import (
    _build_error_overlay_payload,
    _drop_degenerate_faces,
    _resolve_texture_file,
    _summarize_audit_full,
    ckpt17_to_blender_zup_metres,
    ckpt17_to_gltf_yup_metres,
    drop_phantom_bridges,
    normalize_uv_tile_offsets,
    purge_internal_voxel_stack_plates,
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


def _box_tris(x0: float, x1: float, y0: float, y1: float, z0: float, z1: float) -> list[list[list[float]]]:
    p = [
        [x0, y0, z0], [x1, y0, z0], [x1, y1, z0], [x0, y1, z0],
        [x0, y0, z1], [x1, y0, z1], [x1, y1, z1], [x0, y1, z1],
    ]
    quads = [
        (0, 3, 2, 1),  # bottom (-z)
        (4, 5, 6, 7),  # top (+z)
        (0, 1, 5, 4),  # front (-y)
        (2, 3, 7, 6),  # back (+y)
        (1, 2, 6, 5),  # right (+x)
        (3, 0, 4, 7),  # left (-x)
    ]
    tris = []
    for a, b, c, d in quads:
        tris.append([p[a], p[b], p[c]])
        tris.append([p[a], p[c], p[d]])
    return tris


def _quad_tris(x0: float, x1: float, y0: float, y1: float, z: float) -> list[list[list[float]]]:
    return [
        [[x0, y0, z], [x1, y0, z], [x1, y1, z]],
        [[x0, y0, z], [x1, y1, z], [x0, y1, z]],
    ]


def test_detect_and_purge_internal_voxel_stack_plates() -> None:
    # Sealed 100x100x118.11 in box (3 Minecraft blocks tall) with 2 internal 1-block plates at 39.37 & 78.74
    tris: list[list[list[float]]] = []
    mats: list[int] = []
    # 0..11: closed outer box walls/top/bottom (mat=0)
    box = _box_tris(0.0, 100.0, 0.0, 100.0, 0.0, 118.11)
    tris.extend(box)
    mats.extend([0] * len(box))
    # 12..15: internal 1-block horizontal plates inside closed box (mat=1)
    for pz in (39.37, 78.74):
        qt = _quad_tris(5.0, 95.0, 5.0, 95.0, pz)
        tris.extend(qt)
        mats.extend([1] * len(qt))
    # 16..17: exterior open canopy (EXP_OUTSIDE, mat=2) - must stay
    canopy = _quad_tris(110.0, 160.0, 10.0, 50.0, 60.0)
    tris.extend(canopy)
    mats.extend([2] * len(canopy))
    # 18..19: thin doorway louver 6 in below box ceiling inside closed box (t_up=5.5 < 28, mat=2) - must stay
    louver = _quad_tris(10.0, 90.0, 10.0, 90.0, 112.11)
    tris.extend(louver)
    mats.extend([2] * len(louver))

    pos = np.asarray(tris, dtype=np.float64).reshape(-1, 3)
    fv = np.arange(len(pos), dtype=np.int64).reshape(-1, 3)
    mesh = _make_mesh(pos, fv, ["wall", "clay_plate", "facade"], np.asarray(mats, dtype=np.int64))

    mask = detect_internal_voxel_stack_plates(mesh)
    assert int(mask.sum()) == 4
    assert mask[12:16].all()
    assert not mask[:12].any()
    assert not mask[16:].any()

    purged, n_drop = purge_internal_voxel_stack_plates(mesh, mesh, mask)
    assert n_drop == 4
    assert purged.n_faces == mesh.n_faces - 4
    assert "clay_plate" not in purged.materials or not (
        purged.face_material == purged.materials.index("clay_plate")
    ).any()


def test_resolve_residual_double_layers_blocks_transitive_hole() -> None:
    # A (largest) overlaps B (medium), which overlaps C (outermost extension): A>B>C
    # Pass 1 must drop/clip B WITHOUT letting B delete C in the same pass (zero hole).
    pos = np.array(
        [
            [0.0, 0.0, 0.0], [100.0, 0.0, 0.0], [100.0, 40.0, 0.0],   # A (area 2000)
            [0.0, 0.0, 0.0], [120.0, 0.0, 0.0], [100.0, 20.0, 0.0],   # B (area 1200)
            [80.0, 0.0, 0.0], [120.0, 0.0, 0.0], [100.0, 20.0, 0.0],  # C (area 400, outside A's main overlap)
        ],
        dtype=np.float64,
    )
    fv = np.array([[0, 1, 2], [3, 4, 5], [6, 7, 8]], dtype=np.int64)
    mesh = _make_mesh(pos, fv, ["a", "b", "c"], np.array([0, 1, 2], dtype=np.int64))
    out, n_drop = resolve_residual_double_layers(
        mesh,
        outer_mask=np.array([True, True, True], dtype=bool),
        vis_mask=np.array([True, True, True], dtype=bool),
    )
    assert n_drop >= 1
    assert "c" in out.materials and (out.face_material == out.materials.index("c")).any()


def test_resolve_residual_double_layers_ignores_angled_wall() -> None:
    # Two nearby faces whose normals differ by ~26.6 degrees must never clip/delete each other.
    pos = np.array(
        [
            [0.0, 0.0, 0.0], [50.0, 0.0, 0.0], [50.0, 0.0, 50.0],
            [10.0, 0.05, 0.0], [40.0, -14.95, 0.0], [40.0, -14.95, 50.0],
        ],
        dtype=np.float64,
    )
    fv = np.array([[0, 1, 2], [3, 4, 5]], dtype=np.int64)
    mesh = _make_mesh(pos, fv, ["ortho", "angled"], np.array([0, 1], dtype=np.int64))
    out, n_drop = resolve_residual_double_layers(
        mesh,
        outer_mask=np.array([True, True], dtype=bool),
        vis_mask=np.array([True, True], dtype=bool),
    )
    assert n_drop == 0
    assert out.n_faces == 2


def test_drop_phantom_bridges_keeps_real_face_near_angled_wall() -> None:
    # Real face on Y=0 with an angled wall sitting 0.02 in in front/behind one side
    # must stay 13/13 backed via the 0.005 in close-range probe.
    pos = np.array(
        [
            [0.0, 0.0, 0.0], [20.0, 0.0, 0.0], [0.0, 0.0, 20.0],
            [-2.0, -0.02, -2.0], [18.0, 10.0, -2.0], [18.0, 10.0, 22.0],
            [-2.0, 0.02, -2.0], [18.0, -10.0, -2.0], [18.0, -10.0, 22.0],
        ],
        dtype=np.float64,
    )
    fv = np.array([[0, 1, 2], [3, 4, 5], [6, 7, 8]], dtype=np.int64)
    raw = _make_mesh(pos, fv, ["real", "angled1", "angled2"], np.array([0, 1, 2], dtype=np.int64))
    cleaned, n_dropped = drop_phantom_bridges(raw, raw)
    assert n_dropped == 0
    assert cleaned.n_faces == 3


def test_clipped_diagonal_seam_keeps_4dec_plane_and_100pct_bary7() -> None:
    # Half-overlapping coplanar triangles on x=999.794 (matching Floor_3B #4817 / #4972)
    # must stay at 4-decimal plane precision and achieve 100% 7-point Embree coverage.
    pos = np.array(
        [
            [999.794, 22708.7992, 1661.4201],
            [999.794, 22708.7992, 1700.7900],
            [999.794, 22748.1992, 1661.4201],
            [999.794, 22748.1992, 1700.7900],
        ],
        dtype=np.float64,
    )
    fv = np.array([[0, 1, 2], [0, 3, 2]], dtype=np.int64)
    mesh = _make_mesh(pos, fv, ["wall_a", "wall_b"], np.array([0, 1], dtype=np.int64))
    clipped, n_changed = remove_coplanar_overlaps(
        mesh,
        dist_tol=0.04,
        rebuild=True,
        allow_same_plane_back_to_back=False,
    )
    assert n_changed >= 1
    assert float(np.max(np.abs(clipped.positions[:, 0] - 999.794))) <= 1e-4

    center = 0.5 * (mesh.positions.min(axis=0) + mesh.positions.max(axis=0))
    fn_b = face_normals(mesh.positions, mesh.face_v, np.ones(mesh.n_faces, dtype=bool))
    caster = EmbreeCaster(clipped.positions - center, clipped.face_v)
    pct, missing = _coverage_7pt(mesh, caster, center, fn_b, np.array([0, 1], dtype=np.int64), tol=0.12)
    assert pct == 100.0
    assert len(missing) == 0


def test_triangulate_clipped_face_rejects_hairline_ribbon() -> None:
    from shapely.geometry import Polygon

    pts_f = np.array([[0.0, 0.0, 0.0], [20.0, 0.0, 0.0], [0.0, 10.0, 0.0]], dtype=np.float64)
    p2_f = pts_f[:, :2].copy()
    orig_fv = np.array([0, 1, 2], dtype=np.int64)
    orig_fvt = np.array([0, 1, 2], dtype=np.int64)
    f_normal = np.array([0.0, 0.0, 1.0], dtype=np.float64)
    ribbon = Polygon([(0.0, 0.0), (15.0, 0.0), (15.0, 0.003), (0.0, 0.003)])
    _, _, nfv, _, _, _, _ = _triangulate_clipped_face(
        pts_f, p2_f, orig_fv, orig_fvt, None, f_normal, 0, ribbon, 3, 0, min_part_area=0.005
    )
    assert len(nfv) == 0

    real_tri = Polygon([(0.0, 0.0), (10.0, 0.0), (0.0, 5.0)])
    _, _, nfv_real, _, _, _, _ = _triangulate_clipped_face(
        pts_f, p2_f, orig_fv, orig_fvt, None, f_normal, 0, real_tri, 3, 0, min_part_area=0.005
    )
    assert len(nfv_real) >= 1


def test_purge_internal_voxel_stack_plates_preserves_non_stack_raw_interior() -> None:
    # A horizontal face at z=40 in with an opposite-normal horizontal face 39.37 in below
    # looks like a stack plate on the candidate mesh if side walls were trimmed away,
    # but when RAW marked it non-stack (`raw_stack_mask == False`), it must be preserved.
    pos = np.array(
        [
            [0.0, 0.0, 0.63], [40.0, 0.0, 0.63], [40.0, 40.0, 0.63], [0.0, 40.0, 0.63],
            [0.0, 0.0, 40.0], [40.0, 0.0, 40.0], [40.0, 40.0, 40.0], [0.0, 40.0, 40.0],
        ],
        dtype=np.float64,
    )
    fv = np.array(
        [
            [0, 2, 1], [0, 3, 2],  # bottom (-Z)
            [4, 5, 6], [4, 6, 7],  # top (+Z)
        ],
        dtype=np.int64,
    )
    cand = _make_mesh(pos, fv, ["slab"], np.zeros(4, dtype=np.int64))
    raw_stack_false = np.zeros(4, dtype=bool)
    kept, n_dropped_false = purge_internal_voxel_stack_plates(cand, cand, raw_stack_false)
    assert n_dropped_false == 0
    assert kept.n_faces == 4

    raw_stack_true = np.ones(4, dtype=bool)
    purged, n_dropped_true = purge_internal_voxel_stack_plates(cand, cand, raw_stack_true)
    assert n_dropped_true == 4
    assert purged.n_faces == 0


def test_detect_piercing_needle_slivers_protects_coplanar_tjunction_wedge() -> None:
    # A 0.25 in x 25 in triangle sharing an unwelded coplanar T-junction edge with a
    # same-material wall quad must NOT be flagged as a piercing needle, whereas an
    # isolated protruding 0.25 in x 25 in needle with zero coplanar neighbors IS flagged.
    pos = np.array(
        [
            [0.0, 0.0, 0.0], [40.0, 0.0, 0.0], [40.0, 0.0, 40.0], [0.0, 0.0, 40.0],
            [5.0, 0.0, 0.0], [5.0, 0.0, -0.25], [30.0, 0.0, 0.0],
            [100.0, 0.0, 0.0], [100.0, 0.0, 0.25], [125.0, 0.0, 0.0],
        ],
        dtype=np.float64,
    )
    fv = np.array(
        [
            [0, 1, 2], [0, 2, 3],  # wall quad
            [4, 5, 6],             # coplanar T-junction wedge abutting y=0 wall
            [7, 8, 9],             # isolated protruding needle
        ],
        dtype=np.int64,
    )
    mesh = _make_mesh(pos, fv, ["wall", "wall", "wall", "wall"], np.zeros(4, dtype=np.int64))
    mask, _ = detect_piercing_needle_slivers(mesh)
    assert not bool(mask[2])
    assert bool(mask[3])


def test_heal_walkable_floor_slab_cracks_seals_needle_crack_and_notch_preserving_uvs() -> None:
    from shapely.geometry import Polygon as SPoly
    import trimesh
    from engine.validate.facade_integrity import count_walkable_floor_cracks
    from tools.build_real_v2_floor import INCH_TO_METRE, heal_walkable_floor_slab_cracks

    # Walkable floor [0..8] x [0..6] m (48m2 >= 25m2) with:
    # 1) 6m needle crack (0.006 m2): [0.5..6.5] x [1.0..1.001]
    # 2) 0.0625 m2 notch: [1.0..1.25] x [2.5..2.75]
    # 3) 2m x 2m column cutout (should remain open): [5.0..7.0] x [3.0..5.0]
    poly_m = SPoly(
        [(0.0, 0.0), (8.0, 0.0), (8.0, 6.0), (0.0, 6.0)],
        holes=[
            [(0.5, 1.0), (6.5, 1.0), (6.5, 1.001), (0.5, 1.001)],
            [(1.0, 2.5), (1.25, 2.5), (1.25, 2.75), (1.0, 2.75)],
            [(5.0, 3.0), (7.0, 3.0), (7.0, 5.0), (5.0, 5.0)],
        ],
    )
    v2d_m, f2d = trimesh.creation.triangulate_polygon(poly_m, engine="earcut")
    pos_in = np.column_stack([v2d_m[:, 0] / INCH_TO_METRE, v2d_m[:, 1] / INCH_TO_METRE, np.zeros(len(v2d_m))])
    uvs = np.column_stack([v2d_m[:, 0] * 0.5, v2d_m[:, 1] * 0.5])
    mesh = _make_mesh(pos_in, f2d.astype(np.int64), ["floor_tile"], np.zeros(len(f2d), dtype=np.int64))
    mesh.uvs = uvs
    mesh.face_vt = f2d.astype(np.int64)
    n_before, _ = count_walkable_floor_cracks(mesh)
    assert n_before == 2

    healed, n_healed = heal_walkable_floor_slab_cracks(mesh)
    assert n_healed == 2
    n_after, _ = count_walkable_floor_cracks(healed)
    assert n_after == 0

    # Verify newly added vertices have exact UVs (x_m * 0.5, y_m * 0.5) and column cutout [5..7]x[3..5] remains un-filled
    fn_h = face_normals(healed.positions, healed.face_v, np.ones(healed.n_faces, dtype=bool))
    assert np.all(fn_h[:, 2] > 0.99)
    fc_m = healed.positions[healed.face_v].mean(axis=1) * INCH_TO_METRE
    in_col = (fc_m[:, 0] > 5.1) & (fc_m[:, 0] < 6.9) & (fc_m[:, 1] > 3.1) & (fc_m[:, 1] < 4.9)
    assert not np.any(in_col)
    for fi in range(healed.n_faces):
        pts_m_f = healed.positions[healed.face_v[fi]] * INCH_TO_METRE
        uv_f = healed.uvs[healed.face_vt[fi]]
        assert np.allclose(uv_f, pts_m_f[:, :2] * 0.5, atol=1e-4)


def test_heal_walkable_floor_slab_cracks_skips_hole_covered_by_nearby_threshold() -> None:
    from shapely.geometry import Polygon as SPoly
    import trimesh
    from engine.validate.facade_integrity import count_walkable_floor_cracks
    from tools.build_real_v2_floor import INCH_TO_METRE, heal_walkable_floor_slab_cracks

    # Walkable floor [0..8] x [0..6] m at z=0 with an interior slit [1.0..5.0] x [2.0..2.1]
    # already covered by a doorway threshold quad at z = -0.05m (different material).
    poly_m = SPoly(
        [(0.0, 0.0), (8.0, 0.0), (8.0, 6.0), (0.0, 6.0)],
        holes=[[(1.0, 2.0), (5.0, 2.0), (5.0, 2.1), (1.0, 2.1)]],
    )
    v2d_m, f2d = trimesh.creation.triangulate_polygon(poly_m, engine="earcut")
    pos_fl = np.column_stack([v2d_m[:, 0] / INCH_TO_METRE, v2d_m[:, 1] / INCH_TO_METRE, np.zeros(len(v2d_m))])
    z_thr = -0.05 / INCH_TO_METRE
    pos_thr = np.array(
        [
            [0.95 / INCH_TO_METRE, 1.95 / INCH_TO_METRE, z_thr],
            [5.05 / INCH_TO_METRE, 1.95 / INCH_TO_METRE, z_thr],
            [5.05 / INCH_TO_METRE, 2.15 / INCH_TO_METRE, z_thr],
            [0.95 / INCH_TO_METRE, 2.15 / INCH_TO_METRE, z_thr],
        ],
        dtype=np.float64,
    )
    nv_fl = len(pos_fl)
    pos_all = np.vstack([pos_fl, pos_thr])
    fv_all = np.vstack([
        f2d.astype(np.int64),
        np.array([[nv_fl, nv_fl + 1, nv_fl + 2], [nv_fl, nv_fl + 2, nv_fl + 3]], dtype=np.int64),
    ])
    fmat_all = np.concatenate([np.zeros(len(f2d), dtype=np.int64), np.ones(2, dtype=np.int64)])
    mesh = _make_mesh(pos_all, fv_all, ["floor_tile", "threshold"], fmat_all)

    n_cracks, _ = count_walkable_floor_cracks(mesh)
    assert n_cracks == 0
    healed, n_healed = heal_walkable_floor_slab_cracks(mesh)
    assert n_healed == 0
    assert healed.n_faces == mesh.n_faces




