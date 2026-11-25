from __future__ import annotations

import json
from pathlib import Path

import manifold3d as m3d
import numpy as np
from shapely.geometry import Polygon, box as shapely_box
from shapely.ops import unary_union

from engine.fixes.solid_cutaway_rebuild import (
    geom_to_manifold,
    manifold_to_trimesh,
    run_solid_rebuild,
)


def _write_box_obj(boxes: list[tuple[str, float, float, float, float, float, float]], out_obj: Path, out_mtl: Path) -> None:
    mats = sorted({m for m, *_ in boxes})
    mtl_lines = []
    for m in mats:
        mtl_lines.append(f"newmtl {m}")
        mtl_lines.append("Kd 0.8 0.8 0.8")
    out_mtl.write_text("\n".join(mtl_lines) + "\n", encoding="utf-8")

    v_lines = [f"mtllib {out_mtl.name}"]
    f_lines = []
    v_off = 1
    for mat, x0, y0, z0, x1, y1, z1 in boxes:
        man = geom_to_manifold(shapely_box(x0, z0, x1, z1), y0, y1)
        assert man is not None
        tm = manifold_to_trimesh(man)
        for x, y, z in tm.vertices:
            v_lines.append(f"v {x:.5f} {y:.5f} {z:.5f}")
        f_lines.append(f"usemtl {mat}")
        for a, b, c in tm.faces:
            f_lines.append(f"f {v_off + a} {v_off + b} {v_off + c}")
        v_off += len(tm.vertices)
    out_obj.write_text("\n".join(v_lines + f_lines) + "\n", encoding="utf-8")


def test_solid_rebuild_synthetic_room_column_door_window_and_stairs(tmp_path: Path) -> None:
    obj = tmp_path / "synthetic_floor.obj"
    mtl = tmp_path / "synthetic_floor.mtl"
    out_dir = tmp_path / "out"

    # Build a 10m x 8m synthetic building (floor slab [-1..0], walls [0..3.75], 1.2m square column,
    # doorway gap on South wall, window gap + glass on North wall, 2-step stair, plus LittleTiles trim!)
    boxes = [
        ("minecraft_quartz_block_top_-1", 0.0, -1.0, 0.0, 10.0, 0.0, 8.0),   # Floor slab
        ("minecraft_concrete_white_-1", 0.0, 0.0, 0.0, 4.0, 3.75, 0.5),      # South wall left
        ("minecraft_concrete_white_-1", 5.5, 0.0, 0.0, 10.0, 3.75, 0.5),     # South wall right (doorway 4.0..5.5)
        ("minecraft_concrete_white_-1", 4.0, 2.2, 0.0, 5.5, 3.75, 0.5),      # Door lintel above 2.2m
        ("minecraft_concrete_white_-1", 0.0, 0.0, 7.5, 10.0, 1.1, 8.0),      # North wall sill [0..1.1]
        ("minecraft_concrete_white_-1", 0.0, 2.2, 7.5, 10.0, 3.75, 8.0),     # North wall lintel
        ("minecraft_concrete_white_-1", 0.0, 1.1, 7.5, 3.0, 2.2, 8.0),       # North pier left
        ("minecraft_concrete_white_-1", 7.0, 1.1, 7.5, 10.0, 2.2, 8.0),      # North pier right
        ("minecraft_glass_white_-1", 3.0, 1.1, 7.72, 7.0, 2.2, 7.78),        # North window glass
        ("minecraft_concrete_white_-1", 0.0, 0.0, 0.5, 0.5, 3.75, 7.5),      # West wall
        ("minecraft_concrete_white_-1", 9.5, 0.0, 0.5, 10.0, 3.75, 7.5),     # East wall
        ("minecraft_concrete_white_-1", 4.4, 0.0, 3.4, 5.6, 3.75, 4.6),      # Compact 1.2m x 1.2m interior column
        ("minecraft_quartz_block_side_-1", 1.5, 0.0, 1.5, 2.5, 0.25, 2.5),   # Stair step 1
        ("minecraft_quartz_block_side_-1", 2.5, 0.0, 1.5, 3.5, 0.50, 2.5),   # Stair step 2
        ("littletiles_ltcolored0_-1", -0.3, 1.5, -0.3, 0.0, 2.8, 0.2),       # Exterior LittleTiles spike (must strip!)
    ]
    _write_box_obj(boxes, obj, mtl)

    rep = run_solid_rebuild(obj, out_dir, mtl_path=mtl, low_cut_m=1.25, plinth_m=0.04)
    assert rep.passed is True
    assert rep.audit["all_watertight"] is True
    assert rep.audit["total_open_edges"] == 0
    assert rep.audit["total_nonmanifold_edges"] == 0
    assert rep.audit["narrow_wall_gaps"] == 0
    assert rep.audit["negative_volume_nodes"] == []
    assert rep.manifest["counts"]["columns"] == 1
    assert rep.manifest["counts"]["stair_steps"] == 2
    assert rep.glb_path is not None and rep.glb_path.is_file()

    node_names = {n["node"] for n in rep.audit["nodes"]}
    assert "Floor_Slab" in node_names
    assert "Stairs" in node_names
    assert "Column_01__Plinth" in node_names
    assert "Column_01__Lower" in node_names
    assert "Column_01__Upper" in node_names
    assert "Glass_Openings" in node_names
    assert "OverheadBeams_And_Lintels" in node_names


def test_solid_rebuild_no_baseboard_floor_bleed_or_wall_checkerboard(tmp_path: Path) -> None:
    obj = tmp_path / "bleed_floor.obj"
    mtl = tmp_path / "bleed_floor.mtl"
    out_dir = tmp_path / "out"

    # Synthetic floor with dark baseboard + upward baseboard ledge near floor,
    # white interior wall faces, and green exterior face ONLY on North wall outside.
    boxes = [
        ("minecraft_quartz_block_top_-1", 0.0, -0.5, 0.0, 10.0, 0.0, 8.0),    # Floor slab
        ("minecraft_prismarine_dark_-1", 0.5, 0.0, 0.5, 9.5, 0.45, 0.55),      # South baseboard ledge
        ("minecraft_concrete_white_-1", 0.0, 0.0, 0.0, 10.0, 3.6, 0.5),        # South wall
        ("minecraft_concrete_white_-1", 0.0, 0.0, 7.5, 10.0, 3.6, 7.98),       # North inner/body wall
        ("minecraft_concrete_green_-1", 0.0, 0.45, 7.98, 10.0, 3.6, 8.0),      # North exterior outer skin
        ("minecraft_prismarine_dark_-1", 0.0, 0.0, 7.48, 10.0, 0.45, 7.5),     # North inner baseboard
        ("minecraft_concrete_white_-1", 0.0, 0.0, 0.5, 0.5, 3.6, 7.5),         # West wall
        ("minecraft_concrete_white_-1", 9.5, 0.0, 0.5, 10.0, 3.6, 7.5),        # East wall
    ]
    _write_box_obj(boxes, obj, mtl)

    rep = run_solid_rebuild(obj, out_dir, mtl_path=mtl, low_cut_m=1.25, plinth_m=0.04)
    assert rep.passed is True
    assert rep.glb_path is not None and rep.glb_path.is_file()

    import trimesh

    scene = trimesh.load(rep.glb_path, force="scene")
    floor_mats: set[str] = set()
    upper_planes: dict[tuple[str, float, float, float], set[str]] = {}
    inward_north_mats: set[str] = set()

    for node_name in scene.graph.nodes_geometry:
        transform, geom_name = scene.graph[node_name]
        geom = scene.geometry[geom_name]
        mat_name = str(getattr(geom.visual.material, "name", "") or "")
        if geom_name.startswith("Floor_Slab"):
            floor_mats.add(mat_name.lower())
        if "__Upper" in geom_name:
            base_node = geom_name.split("__Upper")[0] + "__Upper"
            verts = geom.vertices
            faces = geom.faces
            p0, p1, p2 = verts[faces[:, 0]], verts[faces[:, 1]], verts[faces[:, 2]]
            cr = np.cross(p1 - p0, p2 - p0)
            fn = cr / np.maximum(np.linalg.norm(cr, axis=1, keepdims=True), 1e-12)
            fc = (p0 + p1 + p2) / 3.0
            for i in range(len(faces)):
                if abs(float(fn[i, 1])) <= 0.70:
                    nx, nz = round(float(fn[i, 0]), 1), round(float(fn[i, 2]), 1)
                    d = round(float(fc[i, 0] * fn[i, 0] + fc[i, 2] * fn[i, 2]), 1)
                    upper_planes.setdefault((base_node, nx, nz, d), set()).add(mat_name.lower())
                    # Inward-facing surface of North wall (z around 7.5, normal pointing -Z)
                    if nz < -0.7 and float(fc[i, 2]) > 7.0:
                        inward_north_mats.add(mat_name.lower())

    assert floor_mats, "Expected Floor_Slab materials in GLB"
    assert all("prismarine_dark" not in m and "concrete_green" not in m for m in floor_mats), floor_mats
    assert all(len(mats) == 1 for mats in upper_planes.values()), upper_planes
    assert all("concrete_green" not in m for m in inward_north_mats), inward_north_mats
