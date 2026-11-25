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
    assert any(n.startswith("Stairs_") and not n.startswith("Stairs_Upper_") for n in node_names)
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


def test_solid_rebuild_stairs_uniform_side_and_flat_lower_cap(tmp_path: Path) -> None:
    obj = tmp_path / "stairs_lower.obj"
    mtl = tmp_path / "stairs_lower.mtl"
    out_dir = tmp_path / "out"

    boxes = [
        ("minecraft_quartz_block_top_-1", 0.0, -0.5, 0.0, 10.0, 0.0, 8.0),
        ("minecraft_quartz_block_side_-1", 1.5, 0.0, 1.5, 2.8, 0.30, 3.0),
        ("minecraft_quartz_block_side_-1", 2.8, 0.0, 1.5, 4.1, 0.60, 3.0),
        ("minecraft_concrete_white_-1", 0.0, 0.0, 0.0, 10.0, 0.85, 0.5),   # South sill
        ("minecraft_concrete_white_-1", 0.0, 0.85, 0.0, 4.0, 3.6, 0.5),
        ("minecraft_concrete_white_-1", 6.0, 0.85, 0.0, 10.0, 3.6, 0.5),
        ("minecraft_concrete_white_-1", 4.0, 2.2, 0.0, 6.0, 3.6, 0.5),
        ("minecraft_concrete_white_-1", 0.0, 0.0, 7.5, 10.0, 3.6, 8.0),
        ("minecraft_concrete_white_-1", 0.0, 0.0, 0.5, 0.5, 3.6, 7.5),
        ("minecraft_concrete_white_-1", 9.5, 0.0, 0.5, 10.0, 3.6, 7.5),
    ]
    _write_box_obj(boxes, obj, mtl)
    rep = run_solid_rebuild(obj, out_dir, mtl_path=mtl, low_cut_m=1.25, plinth_m=0.04)
    assert rep.passed is True
    assert rep.glb_path is not None

    import trimesh

    sc = trimesh.load(rep.glb_path, force="scene")
    stair_side_mats: set[str] = set()
    for geom_name, geom in sc.geometry.items():
        if geom_name.startswith("Stairs") and "quartz_block_top" not in str(getattr(geom.visual.material, "name", "")).lower():
            stair_side_mats.add(str(getattr(geom.visual.material, "name", "")))
        if "__Lower__cut_cap" in geom_name:
            ys = geom.vertices[:, 1]
            assert ys.max() - ys.min() < 1e-4, f"{geom_name} __Lower cut_cap not flat: {ys.min()}..{ys.max()}"
    assert len(stair_side_mats) <= 1, stair_side_mats


def test_solid_rebuild_real_stairs_no_overhead_stair_lintels(tmp_path: Path) -> None:
    obj = tmp_path / "upper_stairs.obj"
    mtl = tmp_path / "upper_stairs.mtl"
    out_dir = tmp_path / "out"

    boxes = [
        ("minecraft_quartz_block_top_-1", 0.0, -0.5, 0.0, 10.0, 0.0, 8.0),
        ("minecraft_quartz_block_side_-1", 1.5, 0.0, 1.5, 2.8, 0.45, 3.0),   # Lower tread
        ("minecraft_quartz_block_top_-1", 2.8, 0.45, 1.5, 4.1, 1.45, 3.0),   # Mid tread
        ("minecraft_quartz_block_top_-1", 4.1, 1.45, 1.5, 5.4, 2.75, 3.0),   # Upper flight > lintel_y
        ("minecraft_concrete_white_-1", 0.0, 0.0, 0.0, 10.0, 0.85, 0.5),
        ("minecraft_concrete_white_-1", 0.0, 0.85, 0.0, 4.0, 3.6, 0.5),
        ("minecraft_concrete_white_-1", 6.0, 0.85, 0.0, 10.0, 3.6, 0.5),
        ("minecraft_concrete_white_-1", 4.0, 2.2, 0.0, 6.0, 3.6, 0.5),
        ("minecraft_concrete_white_-1", 0.0, 0.0, 7.5, 10.0, 3.6, 8.0),
        ("minecraft_concrete_white_-1", 0.0, 0.0, 0.5, 0.5, 3.6, 7.5),
        ("minecraft_concrete_white_-1", 9.5, 0.0, 0.5, 10.0, 3.6, 7.5),
    ]
    _write_box_obj(boxes, obj, mtl)
    rep = run_solid_rebuild(obj, out_dir, mtl_path=mtl, low_cut_m=1.25, plinth_m=0.04)
    assert rep.passed is True
    assert rep.glb_path is not None

    nodes_by_name = {n["node"]: n for n in rep.audit["nodes"]}
    st_nodes = [n for n in nodes_by_name if n.startswith("Stairs_") and not n.startswith("Stairs_Upper_") and "Parapet" not in n]
    st_up_nodes = [n for n in nodes_by_name if n.startswith("Stairs_Upper_")]
    assert st_nodes
    assert st_up_nodes
    assert nodes_by_name[st_nodes[0]]["zero_area"] == 0
    assert nodes_by_name[st_up_nodes[0]]["zero_area"] == 0

    import trimesh

    sc = trimesh.load(rep.glb_path, force="scene")
    if "OverheadBeams_And_Lintels" in sc.geometry:
        ov = sc.geometry["OverheadBeams_And_Lintels"]
        ov_fc_z = ov.vertices[ov.faces].mean(axis=1)[:, 2]
        assert not ((ov_fc_z > 1.2) & (ov_fc_z < 3.3)).any(), "Upper stairs leaked into OverheadBeams_And_Lintels!"


def test_solid_rebuild_raised_floor_keeps_same_y_stair_and_topdown_dedup(tmp_path: Path) -> None:
    obj = tmp_path / "raised_and_ghost.obj"
    mtl = tmp_path / "raised_and_ghost.mtl"
    out_dir = tmp_path / "out"

    boxes = [
        ("minecraft_quartz_block_top_-1", 0.0, -1.0, 0.0, 12.0, 0.0, 10.0),
        # Raised platform in opposite corner (+0.25m, area 2.5m2 >= 2.0m2)
        ("minecraft_quartz_block_top_-1", 8.0, 0.0, 7.0, 10.5, 0.25, 8.0),
        ("minecraft_quartz_block_top_-1", 8.0, 0.0, 8.0, 10.5, 0.25, 9.0),
        # Descending stair steps into open pit (-0.60m, -0.25m)
        ("minecraft_quartz_block_side_-1", 6.0, -1.0, 1.5, 7.2, -0.25, 3.0),
        ("minecraft_quartz_block_side_-1", 4.8, -1.0, 1.5, 6.0, -0.60, 3.0),
        # Step 1 at SAME +0.25m height as raised floor, plus Step 2 (+0.50m)
        ("minecraft_quartz_block_side_-1", 1.5, 0.0, 1.5, 2.8, 0.25, 3.0),
        ("minecraft_quartz_block_side_-1", 2.8, 0.0, 1.5, 4.1, 0.50, 3.0),
        # Inner shell under upper tread (+1.00m directly beneath +1.75m walkable tread): top-down keeps +1.75m!
        ("minecraft_quartz_block_top_-1", 1.5, 0.90, 1.5, 2.8, 1.00, 3.0),
        ("minecraft_quartz_block_top_-1", 1.5, 1.50, 1.5, 2.8, 1.75, 3.0),
        ("minecraft_concrete_white_-1", 0.0, 0.0, 0.0, 12.0, 3.6, 0.5),
        ("minecraft_concrete_white_-1", 0.0, 0.0, 9.5, 12.0, 3.6, 10.0),
        ("minecraft_concrete_white_-1", 0.0, 0.0, 0.5, 0.5, 3.6, 9.5),
        ("minecraft_concrete_white_-1", 11.5, 0.0, 0.5, 12.0, 3.6, 9.5),
    ]
    _write_box_obj(boxes, obj, mtl)
    rep = run_solid_rebuild(obj, out_dir, mtl_path=mtl, low_cut_m=1.25, plinth_m=0.04)
    assert rep.passed is True
    # Note: +0.25m is 0.75m below +1.00m? No: top-down keeps +1.75m, strips +1.00m (1.75-1.00=0.75 <= 1.35),
    # and keeps +0.25m (1.75-0.25=1.50 > 1.35)! Plus Step 2 (+0.50m) and 2 descending steps = 5.
    assert rep.manifest["counts"]["stair_steps"] == 5, rep.manifest["counts"]

    # Verify exported OBJ + MTL contain material assignments & UVs, and Floor_Slab is open above descending pit
    obj_txt = rep.obj_path.read_text(encoding="utf-8")
    mtl_file = out_dir / "materials.mtl"
    assert mtl_file.is_file()
    assert "newmtl " in mtl_file.read_text(encoding="utf-8")
    assert "usemtl " in obj_txt
    assert "\nvt " in obj_txt

    import trimesh

    sc = trimesh.load(rep.glb_path, force="scene")
    floor_geoms = [g for n, g in sc.geometry.items() if n.startswith("Floor_Slab")]
    assert floor_geoms
    floor_m = trimesh.util.concatenate(floor_geoms) if len(floor_geoms) > 1 else floor_geoms[0]
    fc = floor_m.vertices[floor_m.faces].mean(axis=1)
    fn = floor_m.face_normals
    # Descending step footprint (x in [5.0, 7.0], z in [1.7, 2.8]) must NOT have Floor_Slab top cap at y=0
    pit_top_cap = (fn[:, 1] > 0.8) & (np.abs(fc[:, 1]) < 0.05) & (fc[:, 0] > 5.0) & (fc[:, 0] < 7.0) & (fc[:, 2] > 1.7) & (fc[:, 2] < 2.8)
    assert not pit_top_cap.any(), "Floor_Slab buried descending steps!"


def test_solid_rebuild_preserves_littletiles_facade_and_low_sill_walls(tmp_path: Path) -> None:
    obj = tmp_path / "facade_and_low_win.obj"
    mtl = tmp_path / "facade_and_low_win.mtl"
    out_dir = tmp_path / "out"

    boxes = [
        ("minecraft_quartz_block_top_-1", 0.0, -1.0, 0.0, 10.0, 0.0, 10.0),
        # Low stairwell window on North wall (y=[0.75..1.55] open, below 0.75 solid)
        ("minecraft_concrete_white_-1", 0.0, 0.0, 9.5, 10.0, 0.75, 10.0),
        ("minecraft_concrete_white_-1", 0.0, 1.55, 9.5, 10.0, 3.6, 10.0),
        ("minecraft_concrete_white_-1", 0.0, 0.0, 0.0, 10.0, 3.6, 0.5),
        ("minecraft_concrete_white_-1", 0.0, 0.0, 0.5, 0.5, 3.6, 9.5),
        ("minecraft_concrete_white_-1", 9.5, 0.0, 0.5, 10.0, 3.6, 9.5),
        # Exterior LittleTiles canopy & louver trim along North exterior (z=[10.0..12.0])
        ("littletiles_ltcolored0_-1", 2.0, 2.2, 10.0, 8.0, 2.35, 12.0),
        ("littletiles_ltcolored6_-1", 2.5, 2.4, 10.5, 7.5, 2.55, 11.5),
    ]
    _write_box_obj(boxes, obj, mtl)
    rep = run_solid_rebuild(obj, out_dir, mtl_path=mtl, low_cut_m=1.25, plinth_m=0.04)
    assert rep.passed is True
    assert rep.audit["all_watertight"] is True
    assert rep.audit["total_open_edges"] == 0
    assert rep.audit["total_nonmanifold_edges"] == 0
    nodes = {n["node"]: n for n in rep.audit["nodes"]}
    assert "Facade_Ext_N" in nodes
    assert nodes["Facade_Ext_N"]["passed"] is True
    assert nodes["Facade_Ext_N"]["min_altitude_mm"] >= 1.0
    # Low stairwell wall under y=0.75 window must remain in S_base / Wall_Ext_N
    assert any(k.startswith("Wall_Ext_N_") and k.endswith("__Lower") for k in nodes)


def test_solid_rebuild_slanted_railing_no_concrete_bleed(tmp_path: Path) -> None:
    obj = tmp_path / "slanted_rail.obj"
    mtl = tmp_path / "slanted_rail.mtl"
    out_dir = tmp_path / "out"

    boxes = [
        ("minecraft_quartz_block_top_-1", 0.0, -0.5, 0.0, 10.0, 0.0, 10.0),
        # Ascend stair treads +X along x=[2.0..5.0], z=[3.0..5.0]
        ("minecraft_quartz_block_side_-1", 2.0, 0.0, 3.0, 3.0, 0.45, 5.0),
        ("minecraft_quartz_block_top_-1", 3.0, 0.45, 3.0, 4.0, 1.00, 5.0),
        ("minecraft_quartz_block_top_-1", 4.0, 1.00, 3.0, 5.0, 1.80, 5.0),
        # Flush 0.25m balustrade (z=[5.00..5.25]) + 0.25m iron top rail right against 0.25m white concrete spine (z=[5.25..5.50])
        ("minecraft_quartz_block_side_-15574983", 2.0, 0.0, 5.00, 5.0, 1.50, 5.25),
        ("minecraft_iron_block_-1", 2.0, 1.50, 5.00, 5.0, 1.75, 5.25),
        ("minecraft_concrete_white_-1", 2.0, 0.0, 5.25, 5.0, 2.80, 5.50),
        # Perimeter walls
        ("minecraft_concrete_white_-1", 0.0, 0.0, 0.0, 10.0, 3.6, 0.5),
        ("minecraft_concrete_white_-1", 0.0, 0.0, 9.5, 10.0, 3.6, 10.0),
        ("minecraft_concrete_white_-1", 0.0, 0.0, 0.5, 0.5, 3.6, 9.5),
        ("minecraft_concrete_white_-1", 9.5, 0.0, 0.5, 10.0, 3.6, 9.5),
    ]
    _write_box_obj(boxes, obj, mtl)
    rep = run_solid_rebuild(obj, out_dir, mtl_path=mtl, low_cut_m=1.25, plinth_m=0.04)
    assert rep.passed is True
    assert rep.glb_path is not None

    import trimesh

    sc = trimesh.load(rep.glb_path, force="scene")
    iron_nodes = [n for n in sc.geometry if "Parapet" in n and "iron_block" in n]
    balustrade_nodes = [n for n in sc.geometry if "Parapet" in n and "15574983" in n]
    assert iron_nodes, f"Missing iron handrail in parapet: {list(sc.geometry)}"
    assert balustrade_nodes, f"Missing dark-green balustrade in parapet: {list(sc.geometry)}"
