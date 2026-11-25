"""TDD tests for engine.fixes.solid_wall_groups & obj_writer face_groups support."""
from __future__ import annotations

from pathlib import Path
import numpy as np
import trimesh

from engine.fixes.solid_wall_groups import build_solid_wall_column_groups, export_grouped_glb
from engine.io.obj_writer import write_obj
from engine.model import MeshData


def _closed_box(x0: float, x1: float, y0: float, y1: float, z0: float, z1: float, mat_id: int) -> tuple[np.ndarray, np.ndarray, np.ndarray]:
    p = np.array(
        [
            [x0, y0, z0], [x1, y0, z0], [x1, y1, z0], [x0, y1, z0],
            [x0, y0, z1], [x1, y0, z1], [x1, y1, z1], [x0, y1, z1],
        ],
        dtype=np.float64,
    )
    f = np.array(
        [
            [0, 2, 1], [0, 3, 2],
            [4, 5, 6], [4, 6, 7],
            [0, 1, 5], [0, 5, 4],
            [2, 3, 7], [2, 7, 6],
            [0, 4, 7], [0, 7, 3],
            [1, 2, 6], [1, 6, 5],
        ],
        dtype=np.int64,
    )
    m = np.full(len(f), mat_id, dtype=np.int64)
    return p, f, m


def _combine_boxes(boxes: list[tuple[np.ndarray, np.ndarray, np.ndarray]], materials: list[str]) -> MeshData:
    pos_list, fv_list, fm_list = [], [], []
    off = 0
    for p, f, m in boxes:
        pos_list.append(p)
        fv_list.append(f + off)
        fm_list.append(m)
        off += len(p)
    pos = np.vstack(pos_list)
    fv = np.vstack(fv_list)
    fm = np.concatenate(fm_list)
    uvs = np.column_stack([(pos[:, 0] + pos[:, 1]) / 100.0, pos[:, 2] / 100.0]).astype(np.float64)
    return MeshData(
        name="synthetic_floor",
        mtllib="materials.mtl",
        materials=materials,
        positions=pos,
        uvs=uvs,
        normals=np.zeros((0, 3), dtype=np.float64),
        face_v=fv,
        face_vt=fv.copy(),
        face_vn=np.full((len(fv), 3), -1, dtype=np.int64),
        face_material=fm,
        face_line=np.arange(1, len(fv) + 1, dtype=np.int64),
        coord_decimals=2,
        sig_digits=7,
    )


def test_write_obj_face_groups_backward_compatible_and_emits_g_blocks(tmp_path: Path) -> None:
    p, f, m = _closed_box(0, 10, 0, 10, 0, 10, 0)
    mesh = _combine_boxes([(p, f, m)], ["mat0"])

    out_plain = tmp_path / "plain.obj"
    write_obj(mesh, out_plain)
    txt_plain = out_plain.read_text(encoding="utf-8")
    assert "\ng " not in txt_plain

    out_grp = tmp_path / "grouped.obj"
    groups = ["Floor_Slab"] * 4 + ["Column_01"] * 8
    write_obj(mesh, out_grp, face_groups=groups)
    txt_grp = out_grp.read_text(encoding="utf-8")
    assert "g Floor_Slab\n" in txt_grp
    assert "g Column_01\n" in txt_grp


def test_build_solid_wall_column_groups_separates_floor_column_wall_lintel_glass_and_cuts_cleanly(tmp_path: Path) -> None:
    # Build synthetic CHTM-like floor in inches (1m = 39.37 in):
    # - Floor slab: X=0..400, Y=0..400, Z=0..40 (top at 40 in = 1.016m)
    # - Perimeter South wall: X=0..400, Y=0..16, Z=40..180 (thickness 0.40m, height 3.55m)
    # - Standalone interior column: X=180..212, Y=180..212, Z=40..180 (0.81m x 0.81m square pier)
    # - Overhead beam/lintel: X=100..250, Y=260..276, Z=125..180 (starts at +2.16m above floor)
    # - Glass window pane: X=200..280, Y=390..394, Z=60..140
    # - Plus an internal trapped vertical rib INSIDE the South wall (Y=8, X=20..380, Z=42..178)
    materials = [
        "minecraft_quartz_block_top_-1",
        "minecraft_concrete_white_-1",
        "minecraft_glass_white_-1",
    ]
    floor_box = _closed_box(0.0, 400.0, 0.0, 400.0, 0.0, 40.0, 0)
    wall_box = _closed_box(0.0, 400.0, 0.0, 16.0, 40.0, 180.0, 1)
    col_box = _closed_box(180.0, 212.0, 180.0, 212.0, 40.0, 180.0, 1)
    lintel_box = _closed_box(100.0, 250.0, 260.0, 276.0, 125.0, 180.0, 1)
    glass_box = _closed_box(200.0, 280.0, 390.0, 394.0, 60.0, 140.0, 2)
    # Trapped internal rib inside South wall
    rib_p = np.array([[20.0, 8.0, 42.0], [380.0, 8.0, 42.0], [380.0, 8.0, 178.0], [20.0, 8.0, 178.0]], dtype=np.float64)
    rib_f = np.array([[0, 1, 2], [0, 2, 3]], dtype=np.int64)
    rib_m = np.array([1, 1], dtype=np.int64)

    mesh = _combine_boxes([floor_box, wall_box, col_box, lintel_box, glass_box, (rib_p, rib_f, rib_m)], materials)
    mtl_path = tmp_path / "materials.mtl"
    mtl_path.write_text(
        "newmtl minecraft_quartz_block_top_-1\nKd 0.85 0.82 0.76\n\n"
        "newmtl minecraft_concrete_white_-1\nKd 0.90 0.90 0.88\n\n"
        "newmtl minecraft_glass_white_-1\nKd 0.70 0.88 0.95\nd 0.45\n",
        encoding="utf-8",
    )

    res = build_solid_wall_column_groups(
        mesh,
        mtl_path,
        cut_height_m=1.10,
        per_segment=True,
        run_core_repair=False,  # fast synthetic test focusing on grouping/sealing/cutaway
    )
    grp_names = set(res.face_groups)
    assert "Floor_Slab" in grp_names
    assert "OverheadBeams_And_Lintels" in grp_names
    assert "Glass_Openings" in grp_names
    assert any(g.startswith("Column_") for g in grp_names)
    assert any(g.startswith("Wall_") for g in grp_names)

    # Every wall & column solid group must have 0 non-manifold edges, positive outward volume,
    # and the combined floor must pass unity_preflight with 0 duplicates, 0 reversed, 0 flicker!
    for gname, ginfo in res.manifest["groups"].items():
        if gname.startswith(("Column_", "Wall_")):
            assert ginfo["nonmanifold_edges"] == 0, f"{gname} has non-manifold edges"
            assert ginfo["signed_volume"] > 0.0, f"{gname} has inverted signed volume"
    assert res.audit_after["counts"]["trapped_cavity_faces"] == 0
    assert res.preflight_unity["passed"] is True
    assert res.preflight_unity["checks"]["zero_exact_flicker"]["passed"] is True
    assert res.preflight_unity["checks"]["zero_reversed_normals"]["count"] == 0
    assert res.preflight_unity["checks"]["topology_valid"]["duplicate_triangles"] == 0

    # Horizontal cut plane check: no vertical wall face crosses z_cut = 40 + 1.10 / 0.0254 (= 83.31 in)
    z_cut = 40.0 + 1.10 / 0.0254
    pts = res.mesh_ckpt17.positions[res.mesh_ckpt17.face_v]
    for f_idx, gname in enumerate(res.face_groups):
        if gname.startswith("Wall_"):
            zmin_f = float(pts[f_idx, :, 2].min())
            zmax_f = float(pts[f_idx, :, 2].max())
            assert not (zmin_f < z_cut - 0.2 and zmax_f > z_cut + 0.2), (
                f"{gname} face {f_idx} crosses cut plane {z_cut:.2f}: [{zmin_f:.2f}, {zmax_f:.2f}]"
            )

    # Verify GLB export produces named nodes
    glb_path = tmp_path / "synthetic.glb"
    export_grouped_glb(res.mesh_unity, res.face_groups, mtl_path, glb_path)
    assert glb_path.is_file() and glb_path.stat().st_size > 200
    loaded = trimesh.load(str(glb_path), force="scene")
    nodes = set(loaded.graph.nodes)
    assert nodes >= {"Floor_Slab", "OverheadBeams_And_Lintels", "Glass_Openings"}
    assert any(n.startswith("Column_") for n in nodes)
    assert any(n.startswith("Wall_") for n in nodes)
    assert res.preflight_unity["passed"] is True


def test_solid_wall_groups_keeps_prismarine_baseboards_out_of_stairs_and_preserves_upper_walls(tmp_path: Path) -> None:
    # Regression test for real CHTM 4F defects:
    # 1) `minecraft_prismarine_dark_-1` baseboard strips along walls must NOT be classified as Stairs
    # 2) Stacked upper wall bands directly above a standing lower wall must NOT become OverheadBeams_And_Lintels
    # 3) Exact duplicate triangles and reversed normals must be eliminated so unity_preflight passes
    materials = [
        "minecraft_quartz_block_top_-1",
        "minecraft_concrete_white_-1",
        "minecraft_prismarine_dark_-1",
    ]
    floor_box = _closed_box(0.0, 400.0, 0.0, 400.0, 0.0, 40.0, 0)
    # Lower wall band (Z=40..115) + stacked upper wall band (Z=115..180) directly on top at Y=0..16
    wall_lo = _closed_box(0.0, 400.0, 0.0, 16.0, 40.0, 115.0, 1)
    wall_hi = _closed_box(0.0, 400.0, 0.0, 16.0, 115.0, 180.0, 1)
    # Prismarine baseboard strip hugging the wall (Z=40..58)
    baseboard = _closed_box(10.0, 390.0, 16.0, 18.0, 40.0, 58.0, 2)
    # Genuine floating lintel with open space underneath (Y=260..276, Z=125..180)
    lintel = _closed_box(120.0, 240.0, 260.0, 276.0, 125.0, 180.0, 1)

    mesh = _combine_boxes([floor_box, wall_lo, wall_hi, baseboard, lintel], materials)
    # Inject an exact duplicate triangle and an inverted triangle to verify post-cleanup
    mesh.face_v = np.vstack([mesh.face_v, mesh.face_v[0:1]])
    mesh.face_vt = np.vstack([mesh.face_vt, mesh.face_vt[0:1]])
    mesh.face_vn = np.vstack([mesh.face_vn, mesh.face_vn[0:1]])
    mesh.face_material = np.concatenate([mesh.face_material, mesh.face_material[0:1]])
    mesh.face_line = np.concatenate([mesh.face_line, np.array([9999], dtype=np.int64)])

    mtl_path = tmp_path / "materials.mtl"
    mtl_path.write_text(
        "newmtl minecraft_quartz_block_top_-1\nKd 0.85 0.82 0.76\n\n"
        "newmtl minecraft_concrete_white_-1\nKd 0.90 0.90 0.88\n\n"
        "newmtl minecraft_prismarine_dark_-1\nKd 0.25 0.35 0.32\n",
        encoding="utf-8",
    )

    res = build_solid_wall_column_groups(
        mesh,
        mtl_path,
        cut_height_m=1.10,
        per_segment=True,
        run_core_repair=False,
    )
    assert "Stairs" not in set(res.face_groups), "Baseboard prismarine must not be misclassified as Stairs"
    assert "OverheadBeams_And_Lintels" in set(res.face_groups)

    # Stacked upper wall at Y=0..16, Z>115 must remain in a Wall_ group, NOT OverheadBeams_And_Lintels
    pts = res.mesh_ckpt17.positions[res.mesh_ckpt17.face_v]
    y_cen = pts[:, :, 1].mean(axis=1)
    z_cen = pts[:, :, 2].mean(axis=1)
    upper_south_wall_groups = {
        res.face_groups[i]
        for i in range(res.mesh_ckpt17.n_faces)
        if y_cen[i] < 20.0 and z_cen[i] > 120.0
    }
    assert upper_south_wall_groups
    assert "OverheadBeams_And_Lintels" not in upper_south_wall_groups

    assert res.preflight_unity["checks"]["topology_valid"]["duplicate_triangles"] == 0
    assert res.preflight_unity["checks"]["zero_reversed_normals"]["count"] == 0
    assert res.preflight_unity["checks"]["zero_exact_flicker"]["passed"] is True
    assert res.preflight_unity["passed"] is True
