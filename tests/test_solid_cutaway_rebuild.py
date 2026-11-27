from __future__ import annotations

import json
from pathlib import Path

import manifold3d as m3d
import numpy as np
from shapely.geometry import Polygon, box as shapely_box
from shapely.ops import unary_union

from engine.fixes.solid_cutaway_rebuild import (
    _count_non_ortho_edges,
    _extract_solid_slice,
    _is_clean_angled_tread,
    _repair_notched_stair_treads,
    _polygon_to_manifold,
    _raw_manifold_to_trimesh,
    _separate_columns_and_split_walls,
    _split_mesh_by_material_and_flat_uvs,
    _trimesh_min_altitude_mm,
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
        # Wall-embedded LittleTiles window mullion/grille trim along North window (z=[9.60..9.95])
        ("littletiles_ltcolored0_-1", 2.0, 0.75, 9.60, 8.0, 1.55, 9.95),
        ("littletiles_ltcolored6_-1", 4.8, 0.75, 9.60, 5.2, 1.55, 9.95),
        # Protruding exterior white roof overhang beyond the building envelope (z=[10.5..14.0]) -> must be excluded
        ("littletiles_ltcolored0_-1", 2.0, 2.2, 10.5, 8.0, 2.40, 14.0),
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
    assert rep.glb_path is not None

    import trimesh

    sc = trimesh.load(rep.glb_path, force="scene")
    facade_n = [g for n, g in sc.geometry.items() if n.startswith("Facade_Ext_N")]
    assert facade_n
    max_z = max(float(g.bounds[1][2]) for g in facade_n)
    assert max_z <= 10.45, f"Overhanging exterior canopy leaked into Facade_Ext_N: max_z={max_z}"
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


def test_solid_rebuild_preserves_column_with_missing_low_face_and_claims_green_parapet(tmp_path: Path) -> None:
    obj = tmp_path / "col_consensus_and_parapet.obj"
    mtl = tmp_path / "col_consensus_and_parapet.mtl"
    out_dir = tmp_path / "out"

    boxes = [
        ("minecraft_quartz_block_top_-1", 0.0, -1.0, 0.0, 12.0, 0.0, 12.0),
        # Full-height column missing its bottom [0.0..0.45] chunk (only solid at y=[0.45..3.6])
        ("minecraft_concrete_white_-1", 2.0, 0.45, 2.0, 3.5, 3.6, 3.5),
        # Stairs + concrete_green parapet (must NOT duplicate into Wall_Int_* or OverheadBeams)
        ("minecraft_quartz_block_side_-1", 5.0, 0.0, 4.0, 6.0, 0.50, 7.0),
        ("minecraft_quartz_block_top_-1", 6.0, 0.50, 4.0, 7.0, 1.80, 7.0),
        ("minecraft_concrete_green_-1", 5.0, 0.0, 7.0, 7.0, 2.60, 7.25),
        # Perimeter walls
        ("minecraft_concrete_white_-1", 0.0, 0.0, 0.0, 12.0, 3.6, 0.5),
        ("minecraft_concrete_white_-1", 0.0, 0.0, 11.5, 12.0, 3.6, 12.0),
        ("minecraft_concrete_white_-1", 0.0, 0.0, 0.5, 0.5, 3.6, 11.5),
        ("minecraft_concrete_white_-1", 11.5, 0.0, 0.5, 12.0, 3.6, 11.5),
    ]
    _write_box_obj(boxes, obj, mtl)
    rep = run_solid_rebuild(obj, out_dir, mtl_path=mtl, low_cut_m=1.25, plinth_m=0.04)
    assert rep.passed is True
    assert rep.manifest["counts"]["columns"] >= 1

    import trimesh

    sc = trimesh.load(rep.glb_path, force="scene")
    col_geoms = [g for n, g in sc.geometry.items() if n.startswith("Column_")]
    assert any(g.bounds[0][0] <= 2.2 and g.bounds[1][0] >= 3.3 and g.bounds[0][2] <= 2.2 and g.bounds[1][2] >= 3.3 for g in col_geoms), (
        f"Column missing from {[g.bounds.tolist() for g in col_geoms]}"
    )
    # Green parapet footprint [5..7, 7..7.25] must NOT also emit Wall_Int_* or OverheadBeams_And_Lintels
    for n, g in sc.geometry.items():
        if n.startswith("Wall_Int_") or n.startswith("OverheadBeams_"):
            fc = g.vertices[g.faces].mean(axis=1)
            overlap = (fc[:, 0] > 5.05) & (fc[:, 0] < 6.95) & (fc[:, 2] > 7.02) & (fc[:, 2] < 7.23)
            assert not overlap.any(), f"{n} Z-fights with green parapet!"


def test_solid_rebuild_recovers_flipped_stair_tread_repairs_notch_and_skips_stair_raised_level(tmp_path: Path) -> None:
    from engine.fixes.solid_cutaway_rebuild import load_raw_floor_obj

    obj = tmp_path / "stair_repairs.obj"
    mtl = tmp_path / "stair_repairs.mtl"
    out_dir = tmp_path / "out"

    boxes = [
        ("minecraft_quartz_block_top_-1", 0.0, -0.5, 0.0, 12.0, 0.0, 12.0),
        # Step 1 at y=0.25 with large bottom shell (4.5 m2) overlapped 50% by Step 2 -> must NOT become Floor_Raised
        ("minecraft_quartz_block_top_-1", 3.0, 0.0, 2.0, 6.0, 0.25, 3.5),
        ("minecraft_quartz_block_top_-1", 3.0, 0.0, 2.75, 6.0, 0.50, 4.25),
        # Step 3 at y=0.75 is omitted from boxes and appended manually with flipped top normal (ny = -1)
        # Step 4 at y=1.00 is emitted as an L/notched polygon (missing one corner) and appended manually
        ("minecraft_concrete_white_-1", 0.0, 0.0, 0.0, 12.0, 3.6, 0.5),
        ("minecraft_concrete_white_-1", 0.0, 0.0, 11.5, 12.0, 3.6, 12.0),
        ("minecraft_concrete_white_-1", 0.0, 0.0, 0.5, 0.5, 3.6, 11.5),
        ("minecraft_concrete_white_-1", 11.5, 0.0, 0.5, 12.0, 3.6, 11.5),
    ]
    _write_box_obj(boxes, obj, mtl)

    # Append flipped-normal Step 3 (y=0.75, x=[3.0..6.0], z=[4.25..5.0]) and notched Step 4 (y=1.00, x=[3.0..6.0], z=[5.0..5.75])
    extra_v = [
        # Step 3 flipped quad at y=0.75 (CW from +Y -> outward normal ny = -1)
        (3.0, 0.75, 4.25),
        (6.0, 0.75, 4.25),
        (6.0, 0.75, 5.00),
        (3.0, 0.75, 5.00),
        # Step 4 notched 5-vertex polygon at y=1.00 (corner (6.0, 5.75) beveled back to (5.2, 5.75) and (6.0, 5.0))
        (3.0, 1.00, 5.00),
        (3.0, 1.00, 5.75),
        (5.2, 1.00, 5.75),
        (6.0, 1.00, 5.00),
        # Step 5 landing at y=1.25 to anchor upper end
        (3.0, 1.25, 5.75),
        (3.0, 1.25, 7.25),
        (6.0, 1.25, 7.25),
        (6.0, 1.25, 5.75),
    ]
    base_lines = obj.read_text(encoding="utf-8").splitlines()
    v_count = sum(1 for ln in base_lines if ln.startswith("v "))
    add_v_lines = [f"v {x:.5f} {y:.5f} {z:.5f}" for x, y, z in extra_v]
    s3 = v_count + 1
    s4 = v_count + 5
    s5 = v_count + 9
    add_f_lines = [
        "usemtl minecraft_quartz_block_top_-1",
        # Step 3 downward normal (-Y) in Y-up: (0,1,2) with x increasing then z increasing -> normal (0, -1, 0)
        f"f {s3} {s3 + 1} {s3 + 2}",
        f"f {s3} {s3 + 2} {s3 + 3}",
        # Step 4 upward normal (+Y) notched pentagon
        f"f {s4} {s4 + 1} {s4 + 2}",
        f"f {s4} {s4 + 2} {s4 + 3}",
        # Step 5 upward normal (+Y) landing
        f"f {s5} {s5 + 1} {s5 + 2}",
        f"f {s5} {s5 + 2} {s5 + 3}",
    ]
    v_lines = [ln for ln in base_lines if ln.startswith("mtllib ") or ln.startswith("v ")]
    f_lines = [ln for ln in base_lines if not (ln.startswith("mtllib ") or ln.startswith("v "))]
    obj.write_text("\n".join(v_lines + add_v_lines + f_lines + add_f_lines) + "\n", encoding="utf-8")

    raw = load_raw_floor_obj(obj, mtl_path=mtl)
    assert raw.raised_levels == [], f"Stair bottom shell misclassified as raised floor: {raw.raised_levels}"

    rep = run_solid_rebuild(obj, out_dir, mtl_path=mtl, low_cut_m=1.25, plinth_m=0.04)
    assert rep.passed is True
    assert rep.audit["all_watertight"] is True
    assert rep.audit["total_open_edges"] == 0
    assert rep.glb_path is not None

    import trimesh

    sc = trimesh.load(rep.glb_path, force="scene")
    stair_geoms = [g for n, g in sc.geometry.items() if n.startswith("Stairs_")]
    assert stair_geoms
    st = trimesh.util.concatenate(stair_geoms) if len(stair_geoms) > 1 else stair_geoms[0]
    fc = st.vertices[st.faces].mean(axis=1)
    fn = st.face_normals
    # Step 1 (0.25), Step 2 (0.50), flipped Step 3 (0.75), and repaired corner on Step 4 (1.00 near (5.8, 5.6)) must all exist
    assert ((fn[:, 1] > 0.8) & (np.abs(fc[:, 1] - 0.25) < 0.04)).any(), "Bottom step y=0.25 missing!"
    assert ((fn[:, 1] > 0.8) & (np.abs(fc[:, 1] - 0.50) < 0.04)).any(), "Step 2 y=0.50 missing!"
    assert ((fn[:, 1] > 0.8) & (np.abs(fc[:, 1] - 0.75) < 0.04)).any(), "Flipped-normal Step 3 y=0.75 was not recovered!"
    up_100 = (fn[:, 1] > 0.8) & (np.abs(fc[:, 1] - 1.00) < 0.04)
    assert up_100.any(), "Step 4 y=1.00 missing!"
    area_100 = float(st.area_faces[up_100].sum())
    assert area_100 >= 2.20, f"Diagonal notch at Step 4 y=1.00 was not repaired (area={area_100:.3f} < 2.25)!"
    has_corner_v = (
        (st.vertices[:, 0] > 5.95)
        & (np.abs(st.vertices[:, 1] - 1.00) < 0.04)
        & (st.vertices[:, 2] > 5.70)
    )
    assert has_corner_v.any(), "Repaired rectangular corner vertex (6.0, 1.0, 5.75) missing!"


def test_solid_rebuild_standing_column_never_chops_at_lintel_when_top_slice_missing(tmp_path: Path) -> None:
    obj = tmp_path / "stepped_col.obj"
    mtl = tmp_path / "stepped_col.mtl"
    out_dir = tmp_path / "out"

    boxes = [
        ("minecraft_quartz_block_top_-1", 0.0, -0.5, 0.0, 12.0, 0.0, 12.0),
        # Standing 2.0m x 2.0m column [4..6, 4..6] solid up to y=3.0 (above mid-height & lintel),
        # with top [3.0..3.6] missing 75% of its footprint (leaving only [4.0..4.5, 4.0..4.5]).
        ("minecraft_concrete_white_-1", 4.0, 0.0, 4.0, 6.0, 3.0, 6.0),
        ("minecraft_concrete_white_-1", 4.0, 3.0, 4.0, 4.5, 3.6, 4.5),
        # Perimeter walls: South wall has real window opening [1.1..2.4] at x=[2..8] with solid header [2.4..3.6]
        ("minecraft_concrete_white_-1", 0.0, 0.0, 0.0, 12.0, 1.1, 0.5),
        ("minecraft_concrete_white_-1", 0.0, 1.1, 0.0, 2.0, 2.4, 0.5),
        ("minecraft_concrete_white_-1", 8.0, 1.1, 0.0, 12.0, 2.4, 0.5),
        ("minecraft_concrete_white_-1", 0.0, 2.4, 0.0, 12.0, 3.6, 0.5),
        ("minecraft_glass_white_-1", 2.0, 1.1, 0.2, 8.0, 2.4, 0.3),
        ("minecraft_concrete_white_-1", 0.0, 0.0, 11.5, 12.0, 3.6, 12.0),
        ("minecraft_concrete_white_-1", 0.0, 0.0, 0.5, 0.5, 3.6, 11.5),
        ("minecraft_concrete_white_-1", 11.5, 0.0, 0.5, 12.0, 3.6, 11.5),
    ]
    _write_box_obj(boxes, obj, mtl)
    rep = run_solid_rebuild(obj, out_dir, mtl_path=mtl, low_cut_m=1.25, plinth_m=0.04)
    assert rep.passed is True
    assert rep.audit["all_watertight"] is True
    assert rep.audit["total_open_edges"] == 0
    assert rep.glb_path is not None

    import trimesh

    sc = trimesh.load(rep.glb_path, force="scene")
    col_ups = [g for n, g in sc.geometry.items() if n.startswith("Column_") and "__Upper" in n]
    assert col_ups, f"Missing Column__Upper: {list(sc.geometry)}"
    cm = trimesh.util.concatenate(col_ups)
    up = cm.face_normals[:, 1] > 0.9
    fc_y = cm.vertices[cm.faces].mean(axis=1)[:, 1]
    a_mid = float(cm.area_faces[up & (fc_y < 3.4)].sum())
    a_top = float(cm.area_faces[up & (fc_y >= 3.55)].sum())
    assert a_mid < 0.05, f"Column__Upper still chopped at mid-height (a_mid={a_mid:.3f})!"
    assert a_top >= 3.8, f"Column__Upper top area shrunk below full 2x2 footprint (a_top={a_top:.3f})!"

    # Window opening in South exterior wall must stay open at mid-height (y~1.8) and solid at top (y=3.6)
    south_ups = [g for n, g in sc.geometry.items() if n.startswith("Wall_Ext_S_") and "__Upper" in n]
    assert south_ups
    sm = trimesh.util.concatenate(south_ups)
    win_hits = trimesh.intersections.mesh_plane(sm, [0.0, 1.0, 0.0], [0.0, 1.8, 0.0])
    # Segments at y=1.8 should NOT cross x=[2.5..7.5]
    win_mid_cross = [s for s in win_hits if s[:, 0].mean() > 2.5 and s[:, 0].mean() < 7.5]
    assert not win_mid_cross, "South window opening was closed!"
    hdr_hits = trimesh.intersections.mesh_plane(sm, [0.0, 1.0, 0.0], [0.0, 3.0, 0.0])
    hdr_cross = [s for s in hdr_hits if s[:, 0].mean() > 2.5 and s[:, 0].mean() < 7.5]
    assert hdr_cross, "South window header at y=3.0 is missing!"


def test_manifold_to_trimesh_eliminates_sub_mm_sliver() -> None:
    # Polygon with a tiny ~0.2mm dent that creates a sub-1mm sliver triangle before simplify
    poly = Polygon([
        (0.0, 0.0),
        (2.0, 0.0),
        (2.0, 1.0),
        (1.0, 1.0),
        (1.0, 1.0002),
        (0.998, 1.0),
        (0.0, 1.0),
    ])
    man = m3d.Manifold.extrude(m3d.CrossSection([np.asarray(poly.exterior.coords[:-1], dtype=np.float64)]), 1.0)
    tm = manifold_to_trimesh(man)
    assert tm.is_watertight
    assert tm.volume > 1.9
    assert _trimesh_min_altitude_mm(tm) >= 1.0


def test_repair_notched_stair_treads_heals_half_tri_and_l_corner_but_keeps_winders() -> None:
    half_quad = Polygon([(0.0, 0.0), (0.71, 0.0), (0.71, 1.91), (0.67, 1.92)])
    l_bevel = Polygon([(0.0, 0.0), (1.38, 0.0), (1.38, -0.38), (-0.11, -0.38), (-0.11, 0.58), (0.0, 0.37)])
    winder_tri = Polygon([(0.0, 0.0), (0.74, 0.0), (0.0, 0.98)])
    ramp_para = Polygon([(0.0, 0.0), (0.0, 1.0), (0.97, 0.51), (0.97, -0.49)])
    slit_para = Polygon([
        (-50.02, 584.3),
        (-50.4814, 584.0181),
        (-50.4783, 584.0125),
        (-49.91, 584.3),
        (-49.91, 583.31),
        (-50.88, 583.81),
        (-50.88, 584.8),
    ])
    micro_bevel = Polygon([(-64.88, 601.55), (-64.88, 601.93), (-63.39, 601.93), (-63.39, 601.57), (-63.41, 601.55)])
    clipped_bay = Polygon([(-39.91, 580.78), (-39.91, 579.8), (-40.32, 579.8), (-40.42, 580.1)])
    ortho_nibble = Polygon([
        (-63.39, 601.93), (-63.39, 601.57), (-63.41, 601.57), (-63.41, 601.55), (-64.88, 601.55), (-64.88, 601.93)
    ])

    assert _is_clean_angled_tread(winder_tri) is True
    assert _is_clean_angled_tread(ramp_para) is True
    assert _is_clean_angled_tread(half_quad) is False
    assert _is_clean_angled_tread(l_bevel) is False
    assert _is_clean_angled_tread(slit_para) is False

    out = _repair_notched_stair_treads(
        [
            (3.0, half_quad),
            (2.5, l_bevel),
            (2.0, winder_tri),
            (1.5, ramp_para),
            (1.0, slit_para),
            (0.75, ortho_nibble),
            (0.5, micro_bevel),
            (0.25, clipped_bay),
        ],
        excl_low=Polygon(),
        excl_high=Polygon(),
        floor_y=0.0,
    )
    by_y = dict(out)
    assert _count_non_ortho_edges(by_y[3.0]) == 0, f"half_quad failed: {list(by_y[3.0].exterior.coords)}"
    assert _count_non_ortho_edges(by_y[2.5]) == 0, f"l_bevel failed: {list(by_y[2.5].exterior.coords)}"
    assert _count_non_ortho_edges(by_y[0.5]) == 0, f"micro_bevel failed: {list(by_y[0.5].exterior.coords)}"
    assert _count_non_ortho_edges(by_y[0.25]) == 0, f"clipped_bay failed: {list(by_y[0.25].exterior.coords)}"
    nibble_tm = manifold_to_trimesh(geom_to_manifold(by_y[0.75], 38.90, 39.20))
    nibble_top = unary_union([
        Polygon(nibble_tm.vertices[f][:, [0, 2]]).buffer(0)
        for f in nibble_tm.faces[nibble_tm.face_normals[:, 1] > 0.95]
    ])
    assert _count_non_ortho_edges(nibble_top) == 0, f"ortho_nibble extruded chamfer: {list(nibble_top.exterior.coords)}"
    direct_tm = manifold_to_trimesh(geom_to_manifold(ortho_nibble, 38.90, 39.20))
    assert _trimesh_min_altitude_mm(direct_tm) >= 1.0
    direct_top = unary_union([
        Polygon(direct_tm.vertices[f][:, [0, 2]]).buffer(0)
        for f in direct_tm.faces[direct_tm.face_normals[:, 1] > 0.95]
    ])
    assert _count_non_ortho_edges(direct_top) == 0, f"direct CrossSection simplify created chamfer: {list(direct_top.exterior.coords)}"
    assert _is_clean_angled_tread(by_y[2.0]) is True
    assert _is_clean_angled_tread(by_y[1.5]) is True
    assert _is_clean_angled_tread(by_y[1.0]) is True


def test_polygon_to_manifold_strips_collinear_sliver_vertices() -> None:
    poly = Polygon([
        (-35.5, 609.8),
        (-34.93, 609.8),
        (-34.89, 609.8),
        (-32.89, 609.8),
        (-32.86, 609.8),
        (-26.14, 609.93),
        (-26.14, 600.0),
        (-35.5, 600.0),
    ])
    man = geom_to_manifold(poly, 89.08, 89.198)
    assert man is not None
    tm = manifold_to_trimesh(man)
    assert tm.is_watertight
    assert _trimesh_min_altitude_mm(tm) >= 1.0


def test_extract_solid_slice_recovers_open_shell_wall_while_keeping_doorway_open() -> None:
    import trimesh

    # Solid wall wing [0..4, 0..0.5] + lintel span above doorway [4..6, 0..0.5] at y=[2.2..3.6],
    # plus a wall wing [6..10, 0..0.5], where the outer face z=0 on [0..4] is MISSING (open shell).
    wall_a = manifold_to_trimesh(geom_to_manifold(shapely_box(0.0, 0.0, 4.0, 0.5), 0.0, 3.6))
    # Delete south-facing triangles (z ~ 0) on wall_a so horizontal slice at y=0.6 is an open U-loop
    fc_a = wall_a.vertices[wall_a.faces].mean(axis=1)
    fn_a = wall_a.face_normals
    keep_a = ~((fn_a[:, 2] < -0.9) & (fc_a[:, 2] < 0.05))
    open_wall_a = trimesh.Trimesh(vertices=wall_a.vertices, faces=wall_a.faces[keep_a], process=False)

    wall_b = manifold_to_trimesh(geom_to_manifold(shapely_box(6.0, 0.0, 10.0, 0.5), 0.0, 3.6))
    lintel = manifold_to_trimesh(geom_to_manifold(shapely_box(4.0, 0.0, 6.0, 0.5), 2.2, 3.6))
    wall_tm = trimesh.util.concatenate([open_wall_a, wall_b, lintel])

    up_caps = unary_union([shapely_box(0.0, 0.0, 10.0, 0.5)])
    recovered = _extract_solid_slice(wall_tm, 0.60, up_caps, caps_above_y=up_caps)

    # Open-shell wall [0..4] & closed wall [6..10] are solid; doorway [4..6] at y=0.60 stays open!
    assert recovered.intersection(shapely_box(0.2, 0.1, 3.8, 0.4)).area > 0.95
    assert recovered.intersection(shapely_box(6.2, 0.1, 9.8, 0.4)).area > 0.95
    assert recovered.intersection(shapely_box(4.2, 0.1, 5.8, 0.4)).area < 0.05


def test_solid_rebuild_clips_parapet_ceiling_belly_and_protrusion(tmp_path: Path) -> None:
    obj = tmp_path / "parapet_wedge.obj"
    mtl = tmp_path / "parapet_wedge.mtl"
    out_dir = tmp_path / "out"

    # Build a stairwell with lower & upper flights spanning x=[2.0..7.0], z=[3.0..5.0],
    # plus a genuine handrail + balustrade on z=[5.00..5.25], AND an inverted ceiling-hung
    # quartz_15574983 soffit wedge + protrusion extending to x=8.2 on y=[1.6..3.6]!
    boxes = [
        ("minecraft_quartz_block_top_-1", 0.0, -0.5, 0.0, 12.0, 0.0, 10.0),
        ("minecraft_quartz_block_side_-1", 2.0, 0.0, 3.0, 3.5, 0.45, 5.0),
        ("minecraft_quartz_block_top_-1", 3.5, 0.45, 3.0, 5.0, 1.00, 5.0),
        ("minecraft_quartz_block_top_-1", 5.0, 1.00, 3.0, 7.0, 1.80, 5.0),
        # Genuine iron handrail + balustrade below it on x=[2.0..7.0]
        ("minecraft_quartz_block_side_-15574983", 2.0, 0.0, 5.00, 7.0, 1.50, 5.25),
        ("minecraft_iron_block_-1", 2.0, 1.50, 5.00, 7.0, 1.75, 5.25),
        # Anomalous ceiling-hung soffit belly (y=[1.85..3.60]) + protrusion past stairwell (x=[5.0..8.2])
        ("minecraft_quartz_block_side_-15574983", 5.0, 1.85, 5.00, 8.2, 3.60, 5.25),
        ("minecraft_concrete_white_-1", 0.0, 0.0, 0.0, 12.0, 3.6, 0.5),
        ("minecraft_concrete_white_-1", 0.0, 0.0, 9.5, 12.0, 3.6, 10.0),
        ("minecraft_concrete_white_-1", 0.0, 0.0, 0.5, 0.5, 3.6, 9.5),
        ("minecraft_concrete_white_-1", 11.5, 0.0, 0.5, 12.0, 3.6, 9.5),
    ]
    _write_box_obj(boxes, obj, mtl)
    rep = run_solid_rebuild(obj, out_dir, mtl_path=mtl, low_cut_m=1.25, plinth_m=0.04)
    assert rep.passed is True
    assert rep.glb_path is not None

    import trimesh

    sc = trimesh.load(rep.glb_path, force="scene")
    q_parapets = [g for n, g in sc.geometry.items() if "Parapet" in n and "15574983" in n and "cut_cap" not in n]
    assert q_parapets, "Expected balustrade mesh to survive"
    for g in q_parapets:
        assert float(g.bounds[1][0]) <= 7.20, f"Parapet protruded past stairwell x=7.0: {g.bounds}"
        assert float(g.bounds[1][1]) <= 1.85, f"Ceiling-hung soffit belly survived: {g.bounds}"


def test_extract_solid_slice_never_bricks_narrow_doorway_under_lintel() -> None:
    import trimesh

    # Narrow 0.96m x 0.50m doorway [4.0..4.96, 0..0.5] under a lintel [4.0..4.96, 0..0.5] at y=[2.2..3.6],
    # flanked by closed walls [0..4] and [4.96..10] plus an open-shell wing [10..13] missing south face.
    wall_a = manifold_to_trimesh(geom_to_manifold(shapely_box(0.0, 0.0, 4.0, 0.5), 0.0, 3.6))
    wall_b = manifold_to_trimesh(geom_to_manifold(shapely_box(4.96, 0.0, 10.0, 0.5), 0.0, 3.6))
    lintel = manifold_to_trimesh(geom_to_manifold(shapely_box(4.0, 0.0, 4.96, 0.5), 2.2, 3.6))

    open_full = manifold_to_trimesh(geom_to_manifold(shapely_box(10.0, 0.0, 13.0, 0.5), 0.0, 3.6))
    fc_o = open_full.vertices[open_full.faces].mean(axis=1)
    fn_o = open_full.face_normals
    keep_o = ~((fn_o[:, 2] < -0.9) & (fc_o[:, 2] < 0.05))
    open_wing = trimesh.Trimesh(vertices=open_full.vertices, faces=open_full.faces[keep_o], process=False)

    wall_tm = trimesh.util.concatenate([wall_a, wall_b, lintel, open_wing])
    up_caps = unary_union([shapely_box(0.0, 0.0, 13.0, 0.5)])
    recovered = _extract_solid_slice(wall_tm, 0.60, up_caps, caps_above_y=up_caps)

    assert recovered.intersection(shapely_box(0.2, 0.1, 3.8, 0.4)).area > 0.95
    assert recovered.intersection(shapely_box(5.1, 0.1, 9.8, 0.4)).area > 0.95
    assert recovered.intersection(shapely_box(10.2, 0.1, 12.8, 0.4)).area > 0.70
    assert recovered.intersection(shapely_box(4.05, 0.05, 4.91, 0.45)).area < 0.05


def test_solid_rebuild_clips_floating_lower_parapet_tail_and_blocks_floor_iron(tmp_path: Path) -> None:
    obj = tmp_path / "stair_pit.obj"
    mtl = tmp_path / "stair_pit.mtl"
    out_dir = tmp_path / "out"

    # Floor slab covers z=[0..10] EXCEPT an open stairwell pit x=[2..6], z=[0.5..3.5]
    # Lower stairs only occupy x=[2.0..5.0], z=[2.0..3.5]; upper railing extends southward to z=0.6
    boxes = [
        ("minecraft_quartz_block_top_-1", 0.0, -1.0, 3.5, 10.0, 0.0, 10.0),
        ("minecraft_quartz_block_top_-1", 0.0, -1.0, 0.0, 2.0, 0.0, 3.5),
        ("minecraft_quartz_block_top_-1", 6.0, -1.0, 0.0, 10.0, 0.0, 3.5),
        ("minecraft_quartz_block_top_-1", 2.0, -1.0, 0.0, 6.0, 0.0, 0.5),
        # Pit-bottom metal strip that previously polluted recessed Floor_Slab pit cover
        ("minecraft_iron_block_-1", 2.0, -1.02, 0.5, 5.2, -1.00, 0.75),
        # Lower stairs on z=[2.0..3.5] + upper stair flight spanning z=[0.6..2.0]
        ("minecraft_quartz_block_side_-1", 2.0, 0.0, 2.0, 5.0, 0.50, 3.5),
        ("minecraft_quartz_block_top_-1", 2.0, 0.50, 2.0, 5.0, 1.00, 2.75),
        ("minecraft_quartz_block_top_-1", 2.0, 1.40, 0.6, 5.0, 2.40, 2.0),
        # Continuous balustrade + iron handrail along x=[5.00..5.25], z=[0.6..3.5]
        ("minecraft_quartz_block_side_-15574983", 5.00, 0.0, 2.0, 5.25, 1.20, 3.5),
        ("minecraft_quartz_block_side_-15574983", 5.00, 1.25, 0.6, 5.25, 2.80, 2.0),
        ("minecraft_iron_block_-1", 5.00, 0.0, 0.6, 5.25, 1.50, 3.5),
        ("minecraft_iron_block_-1", 5.00, 1.50, 0.6, 5.25, 3.10, 2.0),
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
    assert not any(
        n.startswith("Floor_Slab") and ("iron_block" in n.lower() or "metal_block" in n.lower())
        for n in sc.geometry
    ), f"Floor_Slab received iron/metal material: {list(sc.geometry)}"
    lo_parapets = [g for n, g in sc.geometry.items() if "Parapet" in n and "__Lower" in n and "cut_cap" not in n]
    assert lo_parapets, "Expected lower parapet above stairs"
    for g in lo_parapets:
        assert float(g.bounds[0][2]) >= 1.60, f"Floating lower parapet tail leaked into empty pit: {g.bounds}"
    hi_parapets = [g for n, g in sc.geometry.items() if "Parapet" in n and "__Upper" in n]
    assert hi_parapets and any(float(g.bounds[0][2]) <= 0.70 for g in hi_parapets), "Upper parapet should retain full span"


def test_separate_columns_and_split_walls_empty_s_base_no_crash() -> None:
    cols, walls = _separate_columns_and_split_walls(Polygon(), Polygon(), shapely_box(0.0, 0.0, 5.0, 5.0))
    assert cols == []
    assert walls == []


def test_10cm_column_wall_micro_slit_sealed_while_doorway_stays_open(tmp_path: Path) -> None:
    obj = tmp_path / "slit_and_door.obj"
    mtl = tmp_path / "slit_and_door.mtl"
    out_dir = tmp_path / "out"

    boxes = [
        ("minecraft_quartz_block_top_-1", 0.0, -0.5, 0.0, 10.0, 0.0, 10.0),
        ("minecraft_concrete_white_-1", 0.0, 0.0, 0.0, 10.0, 3.6, 0.5),
        ("minecraft_concrete_white_-1", 0.0, 0.0, 9.5, 10.0, 3.6, 10.0),
        ("minecraft_concrete_white_-1", 0.0, 0.0, 0.5, 0.5, 3.6, 9.5),
        ("minecraft_concrete_white_-1", 9.5, 0.0, 0.5, 10.0, 3.6, 9.5),
        ("minecraft_concrete_white_-1", 3.0, 0.0, 4.5, 3.6, 3.6, 5.1),
        ("minecraft_concrete_white_-1", 3.7, 0.0, 4.6, 5.5, 3.6, 5.0),
        ("minecraft_concrete_white_-1", 6.4, 0.0, 4.6, 9.5, 3.6, 5.0),
        ("minecraft_concrete_white_-1", 5.5, 2.2, 4.6, 6.4, 3.6, 5.0),
    ]
    _write_box_obj(boxes, obj, mtl)
    rep = run_solid_rebuild(obj, out_dir, mtl_path=mtl, low_cut_m=1.25, plinth_m=0.04)
    assert rep.passed is True
    assert rep.audit["narrow_wall_gaps"] == 0, rep.audit["narrow_wall_gap_pairs"]

    import trimesh
    sc = trimesh.load(rep.glb_path, force="scene")
    door_hits = [
        n for n, g in sc.geometry.items()
        if "__Lower" in n and (n.startswith("Wall_") or n.startswith("Column_"))
        and float(g.bounds[0][0]) < 6.2 and float(g.bounds[1][0]) > 5.7
        and float(g.bounds[0][2]) < 5.0 and float(g.bounds[1][2]) > 4.6
    ]
    assert door_hits == [], f"0.90m doorway unexpectedly filled: {door_hits}"
def test_pinched_diagonal_junction_polygon_avoids_sub_mm_sliver() -> None:
    pts = [
        (91.83451, 566.2735),
        (88.9905, 567.2215),
        (89.07, 567.46002),
        (91.915, 566.51001),
        (91.83814, 566.27393),
        (92.30838, 566.11556),
        (92.47, 566.59003),
        (92.665, 566.78497),
        (92.905, 566.70502),
        (92.30991, 566.11505),
        (92.785, 565.95502),
        (92.47, 565.01001),
        (91.52, 565.32501),
        (91.83451, 566.2735),
    ]
    man = _polygon_to_manifold(Polygon(pts), 0.0, 0.04)
    assert man is not None
    min_alt = _trimesh_min_altitude_mm(_raw_manifold_to_trimesh(man))
    assert min_alt >= 1.0, f"Expected min_altitude_mm >= 1.0, got {min_alt:.4f}"


def test_split_mesh_by_material_preserves_distinct_3um_vertices_and_no_repeated_indices() -> None:
    import trimesh

    verts = np.array(
        [
            [0.0, 0.0, 0.0],
            [1.0, 0.0, 0.0],
            [1.0 + 3e-6, 0.0, 1.0],
            [1.0, 0.0, 1.0 + 3e-6],
        ],
        dtype=np.float64,
    )
    faces = np.array([[0, 1, 2], [0, 2, 3]], dtype=np.int64)
    tm = trimesh.Trimesh(vertices=verts, faces=faces, process=False)
    mat = trimesh.visual.material.PBRMaterial(name="test_mat")
    prims = _split_mesh_by_material_and_flat_uvs(tm, ["m0", "m0"], {"m0": mat})
    assert len(prims) == 1
    _, sub_tm = prims[0]
    for f in sub_tm.faces:
        assert f[0] != f[1] and f[1] != f[2] and f[2] != f[0], f"Degenerate face emitted: {f}"


def test_bridge_narrow_wall_gaps_closes_sub12cm_seams_and_preserves_doorways() -> None:
    from engine.fixes.solid_cutaway_rebuild import _bridge_narrow_wall_gaps, _iter_polygons

    # Column + wall 0.10m apart, two diagonal-stepped walls 0.004m apart, plus a real 0.85m doorway
    w1 = shapely_box(0.0, 0.0, 2.0, 0.5)
    col = shapely_box(2.10, 0.0, 2.8, 0.5)
    w2 = Polygon([(2.804, 0.0), (4.5, 0.0), (4.5, 0.5), (2.804, 0.5)])
    w3 = shapely_box(5.35, 0.0, 7.0, 0.5)  # 0.85m doorway from x=4.5..5.35
    u = unary_union([w1, col, w2, w3])
    bridged = _bridge_narrow_wall_gaps(u, min_gap_m=0.0005, max_gap_m=0.12)
    polys = sorted(_iter_polygons(bridged), key=lambda p: p.bounds[0])
    assert len(polys) == 2, f"Expected 2 walls separated only by 0.85m doorway, got {len(polys)}"
    door_gap = polys[0].distance(polys[1])
    assert door_gap >= 0.80, f"Doorway gap narrowed unexpectedly: {door_gap:.4f}m"


def test_polygon_to_manifold_rotated_micro_kink_has_min_alt_ge_1mm() -> None:
    # Rotated wall with a 0.2mm stepped kink along one edge (similar to Architecture 03/05/06)
    pts = [
        (0.0, 0.0),
        (3.0, 1.0),
        (3.0002, 1.0001),
        (2.85, 1.45),
        (-0.15, 0.45),
        (0.0, 0.0),
    ]
    man = _polygon_to_manifold(Polygon(pts), 0.0, 2.5)
    assert man is not None
    tm = manifold_to_trimesh(man)
    assert tm.is_watertight and tm.volume > 0.0
    min_alt = _trimesh_min_altitude_mm(tm)
    assert min_alt >= 1.0, f"Expected min_altitude_mm >= 1.0, got {min_alt:.4f}"


def test_doorway_open_at_60cm_not_bricked_by_s30_smid_consensus(tmp_path: Path) -> None:
    obj = tmp_path / "door_60cm_open.obj"
    mtl = tmp_path / "door_60cm_open.mtl"
    out_dir = tmp_path / "out"

    # Room with a 0.90m doorway open at y=[0.35..1.50], low 0.30m threshold sill, and 1.50..3.60 lintel
    boxes = [
        ("minecraft_quartz_block_top_-1", 0.0, -0.5, 0.0, 10.0, 0.0, 10.0),
        ("minecraft_concrete_white_-1", 0.0, 0.0, 0.0, 10.0, 3.6, 0.5),
        ("minecraft_concrete_white_-1", 0.0, 0.0, 9.5, 10.0, 3.6, 10.0),
        ("minecraft_concrete_white_-1", 0.0, 0.0, 0.5, 0.5, 3.6, 9.5),
        ("minecraft_concrete_white_-1", 9.5, 0.0, 0.5, 10.0, 3.6, 9.5),
        # Interior wall with 0.90m doorway at x=[4.5..5.4], z=[4.6..5.0]
        ("minecraft_concrete_white_-1", 0.5, 0.0, 4.6, 4.5, 3.6, 5.0),
        ("minecraft_concrete_white_-1", 5.4, 0.0, 4.6, 9.5, 3.6, 5.0),
        # Low threshold block only in [0.0..0.35] so S_30 sees solid, S_60 is open
        ("minecraft_concrete_white_-1", 4.5, 0.0, 4.6, 5.4, 0.35, 5.0),
        # Doorway lintel spanning [1.45..3.6] so S_mid at y=1.50 sees solid
        ("minecraft_concrete_white_-1", 4.5, 1.45, 4.6, 5.4, 3.6, 5.0),
    ]
    _write_box_obj(boxes, obj, mtl)
    rep = run_solid_rebuild(obj, out_dir, mtl_path=mtl, low_cut_m=1.25, plinth_m=0.04)
    assert rep.passed is True
    import trimesh

    sc = trimesh.load(rep.glb_path, force="scene")
    door_hits = [
        n for n, g in sc.geometry.items()
        if "__Lower" in n and (n.startswith("Wall_") or n.startswith("Column_"))
        and float(g.bounds[0][0]) < 5.2 and float(g.bounds[1][0]) > 4.7
        and float(g.bounds[0][2]) < 5.0 and float(g.bounds[1][2]) > 4.6
    ]
    assert door_hits == [], f"Doorway open at y=0.60 was bricked by S_30 & S_mid consensus: {door_hits}"


def test_floor_slab_dom_top_excludes_iron_and_metal_block() -> None:
    from engine.fixes.solid_cutaway_rebuild import _is_non_floor_metal_key

    assert _is_non_floor_metal_key("tex_texture_0058_minecraft_iron_block__30") is True
    assert _is_non_floor_metal_key("mat_minecraft_metal_block") is True
    assert _is_non_floor_metal_key("tex_quartz_block_top__1") is False


def test_repair_notched_stair_treads_heals_2cm_edge_bump_and_rotated_tread() -> None:
    # Case A: MI/02-style 2cm x 0.26m Embree edge bump on long axis-aligned landing
    mi_poly = Polygon([
        (14.5, 43.75), (14.5, 35.76), (14.02, 35.76), (14.02, 36.02),
        (14.0, 36.02), (14.0, 42.34), (14.02, 42.37), (14.02, 42.63),
        (14.0, 42.66), (14.0, 43.75), (14.5, 43.75),
    ])
    # Case B: SciA/05-style rotated 4-gon tread with unequal opposite edges (0.20m vs 0.16m chord noise)
    scia_poly = Polygon([
        (59.36, 546.35), (58.89, 546.51), (59.61, 548.67), (60.04, 548.40), (59.36, 546.35),
    ])
    rep = _repair_notched_stair_treads([(2.0, mi_poly), (2.5, scia_poly)], Polygon(), Polygon(), floor_y=0.0)
    by_y = dict(rep)
    assert _count_non_ortho_edges(by_y[2.0]) == 0, f"MI bump still non-ortho: {list(by_y[2.0].exterior.coords)}"
    assert _is_clean_angled_tread(by_y[2.5]) is True, f"Rotated tread not healed: {list(by_y[2.5].exterior.coords)}"


def test_repair_notched_stair_treads_strips_exact_2cm_edge_bump_with_wall_blocker() -> None:
    mi_poly = Polygon([
        (14.0, 43.75), (14.5, 43.75), (14.5, 35.76), (14.02, 35.76),
        (14.02, 36.02), (14.0, 36.02), (14.0, 42.34), (14.02, 42.37),
        (14.02, 42.63), (14.0, 42.66), (14.0, 43.75),
    ])
    wall_blocker = shapely_box(13.5, 35.5, 14.0, 44.0)
    rep = _repair_notched_stair_treads([(2.0, mi_poly)], wall_blocker, wall_blocker, floor_y=0.0)
    by_y = dict(rep)
    assert _count_non_ortho_edges(by_y[2.0]) == 0, f"Blocked 2cm bump still non-ortho: {list(by_y[2.0].exterior.coords)}"


def test_tiered_upper_solid_never_steps_at_lintel_y(tmp_path: Path) -> None:
    obj = tmp_path / "stepped_upper.obj"
    mtl = tmp_path / "stepped_upper.mtl"
    out_dir = tmp_path / "out"

    # Exterior wall with a recessed window band at lintel_y..ceil_y that previously triggered
    # stepped_upper when p_mid was split into [y_cut..lintel_y] + [lintel_y..ceil_y]
    boxes = [
        ("minecraft_quartz_block_top_-1", 0.0, -0.5, 0.0, 12.0, 0.0, 8.0),
        ("minecraft_concrete_white_-1", 0.0, 0.0, 0.0, 12.0, 5.0, 0.6),
        ("minecraft_concrete_white_-1", 0.0, 0.0, 7.4, 12.0, 5.0, 8.0),
        ("minecraft_concrete_white_-1", 0.0, 0.0, 0.6, 0.6, 5.0, 7.4),
        ("minecraft_concrete_white_-1", 11.4, 0.0, 0.6, 12.0, 5.0, 7.4),
        # Upper sill/header corbel near ceiling along south wall that widens p_mid slightly below ceil_y
        ("minecraft_concrete_white_-1", 1.0, 0.0, 0.2, 5.0, 2.0, 0.6),
        ("minecraft_concrete_white_-1", 5.0, 2.0, 0.0, 8.0, 5.0, 0.6),
    ]
    _write_box_obj(boxes, obj, mtl)
    rep = run_solid_rebuild(obj, out_dir, mtl_path=mtl, low_cut_m=1.25, plinth_m=0.04)
    assert rep.passed is True
    import trimesh

    sc = trimesh.load(rep.glb_path, force="scene")
    for n, g in sc.geometry.items():
        if not ((n.startswith("Wall_") or n.startswith("Column_")) and "__Upper" in n):
            continue
        fn = g.face_normals
        fc = g.vertices[g.faces].mean(axis=1)
        up = fn[:, 1] > 0.9
        if up.any():
            max_y = float(g.bounds[1][1])
            mid_m = up & (fc[:, 1] < max_y - 0.3)
            if mid_m.any():
                assert float(g.area_faces[mid_m].sum()) <= 0.25, f"Stepped upper on {n}"


def test_solid_rebuild_preserves_attached_exterior_canopy_and_rejects_interior_roof(tmp_path: Path) -> None:
    obj = tmp_path / "canopy_and_roof.obj"
    mtl = tmp_path / "canopy_and_roof.mtl"
    out_dir = tmp_path / "out"

    boxes = [
        ("minecraft_quartz_block_top_-1", 0.0, -0.5, 0.0, 10.0, 0.0, 10.0),
        ("minecraft_concrete_white_-1", 0.0, 0.0, 0.0, 10.0, 3.6, 0.5),
        ("minecraft_concrete_white_-1", 0.0, 0.0, 9.5, 10.0, 3.6, 10.0),
        ("minecraft_concrete_white_-1", 0.0, 0.0, 0.5, 0.5, 3.6, 9.5),
        ("minecraft_concrete_white_-1", 9.5, 0.0, 0.5, 10.0, 3.6, 9.5),
        # Exterior projecting veranda canopy (z=9.8..12.5, x=2.0..8.0, y=2.6..2.9) -> MUST be preserved as Facade_Canopy_*
        ("littletiles_ltcolored0_-1", 2.0, 2.6, 9.8, 8.0, 2.9, 12.5),
        # Interior ceiling slab inside floor footprint (x=1.0..9.0, z=1.0..9.0, y=3.4..3.6) -> MUST stay rejected
        ("littletiles_ltcolored0_-1", 1.0, 3.4, 1.0, 9.0, 3.6, 9.0),
    ]
    _write_box_obj(boxes, obj, mtl)
    rep = run_solid_rebuild(obj, out_dir, mtl_path=mtl, low_cut_m=1.25, plinth_m=0.04)
    assert rep.passed is True
    assert rep.audit["all_watertight"] is True
    import trimesh

    sc = trimesh.load(rep.glb_path, force="scene")
    canopy_nodes = [(n, g) for n, g in sc.geometry.items() if n.startswith("Facade_Canopy_")]
    assert canopy_nodes, f"Missing Facade_Canopy_* node: {list(sc.geometry)}"
    cm = trimesh.util.concatenate([g for _, g in canopy_nodes])
    assert cm.bounds[1][2] >= 12.3, f"Exterior canopy overhang truncated: max_z={cm.bounds[1][2]:.2f}"
    # Interior ceiling slab inside z=[1.5..8.5] must NOT leak into Facade_* nodes
    facade_geoms = [g for n, g in sc.geometry.items() if n.startswith("Facade_")]
    fm = trimesh.util.concatenate(facade_geoms) if len(facade_geoms) > 1 else facade_geoms[0]
    assert fm.bounds[0][2] >= 9.0, f"Interior roof slab leaked into Facade_*: min_z={fm.bounds[0][2]:.2f}"


def test_snap_near_ortho_tread_edges_heals_2cm_skew_but_keeps_angled_treads() -> None:
    from engine.fixes.solid_cutaway_rebuild import (
        _count_non_ortho_edges,
        _is_clean_angled_tread,
        _snap_near_ortho_tread_edges,
    )

    # Exact CHTM 4F RAW-style tread with 2cm transverse drift
    wobble = Polygon([
        (-41.38, 586.30), (-38.16, 586.30), (-38.16, 585.82),
        (-38.39, 585.80), (-38.39, 585.57), (-41.38, 585.55), (-41.38, 586.30),
    ])
    healed = _snap_near_ortho_tread_edges(wobble)
    assert _count_non_ortho_edges(healed) == 0, f"Expected 0 non-ortho edges, got {list(healed.exterior.coords)}"

    # Genuine 45-degree angled tread must remain untouched
    angled = Polygon([(0.0, 0.0), (1.0, 1.0), (0.5, 1.5), (-0.5, 0.5), (0.0, 0.0)])
    assert _is_clean_angled_tread(angled) is True
    assert _snap_near_ortho_tread_edges(angled).equals(angled)


def test_load_raw_floor_obj_resolves_sibling_mtl_when_mtllib_broken(tmp_path: Path) -> None:
    from engine.fixes.solid_cutaway_rebuild import load_raw_floor_obj

    obj = tmp_path / "DEMO_3rd_Floor.fixed.obj"
    sib_mtl = tmp_path / "DEMO_3rd_Floor.mtl"
    sib_mtl.write_text(
        "newmtl trim_mat\nKd 0.9 0.9 0.9\nmap_Kd textures/littletiles_ltcolored0_-1.png\n",
        encoding="utf-8",
    )
    obj.write_text(
        "mtllib materials.mtl\n"
        "usemtl trim_mat\n"
        "v 0 0 0\nv 1 0 0\nv 1 1 0\nv 0 0 3\n"
        "f 1 2 3\n",
        encoding="utf-8",
    )
    raw = load_raw_floor_obj(obj)
    assert "trim_mat" in raw.materials
    assert raw.materials["trim_mat"].category == "littletiles_trim"


def test_hybrid_v1_plus_raw_recovers_missing_wall_and_canopy(tmp_path: Path) -> None:
    raw_obj = tmp_path / "floor_raw.obj"
    raw_mtl = tmp_path / "floor_raw.mtl"
    v1_obj = tmp_path / "floor.fixed.obj"
    v1_mtl = tmp_path / "floor.mtl"
    out_dir = tmp_path / "out"

    raw_boxes = [
        ("minecraft_quartz_block_top_-1", 0.0, -0.5, 0.0, 10.0, 0.0, 10.0),
        ("minecraft_concrete_white_-1", 0.0, 0.0, 0.0, 10.0, 3.6, 0.5),
        ("minecraft_concrete_white_-1", 0.0, 0.0, 9.5, 10.0, 3.6, 10.0),
        ("minecraft_concrete_white_-1", 0.0, 0.0, 0.5, 0.5, 3.6, 9.5),
        ("minecraft_concrete_white_-1", 9.5, 0.0, 0.5, 10.0, 3.6, 9.5),
        # Interior wall + exterior canopy present in RAW, culled from v1
        ("minecraft_concrete_white_-1", 4.5, 0.0, 2.0, 5.0, 3.6, 8.0),
        ("littletiles_ltcolored0_-1", 2.0, 2.6, 9.8, 8.0, 2.9, 12.2),
    ]
    v1_boxes = raw_boxes[:5]
    _write_box_obj(raw_boxes, raw_obj, raw_mtl)
    _write_box_obj(v1_boxes, v1_obj, v1_mtl)

    rep = run_solid_rebuild(v1_obj, out_dir, raw_ref_obj=raw_obj, low_cut_m=1.25, plinth_m=0.04)
    assert rep.passed is True
    assert rep.manifest["raw_recovery"]["recovered_wall_m2"] > 2.0
    assert any(n.startswith("Facade_Canopy_") for n in rep.manifest["raw_recovery"]["facade_nodes_from_raw"])

    import trimesh
    from tools.batch_solid_rebuild import audit_rebuilt_glb

    sc = trimesh.load(rep.glb_path, force="scene")
    assert any(n.startswith("Facade_Canopy_") for n in sc.geometry)
    assert any(n.startswith("Wall_Int_") for n in sc.geometry)
    qa = audit_rebuilt_glb(rep.glb_path, v1_obj, out_dir, rep.audit, rep.passed, raw_ref_obj=raw_obj)
    assert qa["gates"]["raw_completeness"] is True
    assert qa["all_passed"] is True


def test_parapet_extraction_strips_ceiling_hanging_quartz_soffit(tmp_path: Path) -> None:
    from engine.fixes.solid_cutaway_rebuild import _extract_slanted_stair_parapets, load_raw_floor_obj

    obj = tmp_path / "ceil_parapet.obj"
    mtl = tmp_path / "ceil_parapet.mtl"
    # Build floor [0..8, 0..8], sloped quartz stair steps rising 0..1.5, plus a 3m-long quartz_15574983
    # ceiling soffit slab hanging at y=[2.5..3.6] (ceil_y=3.6) that previously tripped Gate 7 ceil_hang_span.
    boxes = [
        ("minecraft_quartz_block_top_-1", 0.0, -0.5, 0.0, 8.0, 0.0, 8.0),
        ("minecraft_concrete_white_-1", 0.0, 0.0, 0.0, 8.0, 3.6, 0.4),
        ("minecraft_quartz_block_top_-1", 2.0, 0.0, 2.0, 4.0, 0.25, 2.6),
        ("minecraft_quartz_block_top_-1", 2.0, 0.25, 2.6, 4.0, 0.50, 3.2),
        ("minecraft_quartz_block_side_-15574983", 1.75, 2.50, 2.0, 2.00, 3.60, 5.2),
    ]
    _write_box_obj(boxes, obj, mtl)
    raw = load_raw_floor_obj(obj, mtl_path=mtl)
    roi = shapely_box(1.5, 1.5, 4.5, 5.5)
    lo_tm, hi_tm, _ = _extract_slanted_stair_parapets(raw, roi, Polygon(), y_stair_split=1.5)
    assert hi_tm is None or float(hi_tm.area) < 0.1, f"Ceiling soffit hang should be stripped, got bounds={hi_tm.bounds if hi_tm else None}"


def test_repair_notched_stair_treads_collapses_short_winder_bevel_regardless_of_start() -> None:
    from engine.fixes.solid_cutaway_rebuild import _is_clean_angled_tread, _repair_notched_stair_treads

    # Ring starts at (-20.89, 585.8), leaving a 1cm corner bevel at (-20.90, 586.79)
    q_bevel = Polygon([(-20.89, 585.8), (-21.88, 585.8), (-20.90, 586.79), (-20.89, 586.79)])
    res = _repair_notched_stair_treads([(55.55, q_bevel)], Polygon(), Polygon(), 55.2)
    assert len(res) == 1
    _, healed = res[0]
    assert _is_clean_angled_tread(healed) is True
    assert len(healed.exterior.coords) - 1 == 3

    # 4-gon with near-collinear midpoint on hypotenuse (1.8mm offset, all edges >= 0.6m)
    q_col = Polygon([(-20.89, 586.8), (-20.89, 585.804), (-21.8804, 585.804), (-21.3328, 586.3572)])
    res_col = _repair_notched_stair_treads([(55.55, q_col)], Polygon(), Polygon(), 55.2)
    assert len(res_col) == 1
    _, healed_col = res_col[0]
    assert _is_clean_angled_tread(healed_col) is True
    assert len(healed_col.exterior.coords) - 1 == 3


def test_safe_unary_union_and_v1_floor_y_shift_preserves_complete_v1(tmp_path: Path) -> None:
    from engine.fixes.solid_cutaway_rebuild import _safe_unary_union, run_solid_rebuild

    u = _safe_unary_union([shapely_box(0, 0, 2, 2), shapely_box(1, 1, 3, 3)])
    assert abs(u.area - 7.0) < 1e-6

    raw_obj = tmp_path / "raw_complete.obj"
    raw_mtl = tmp_path / "raw_complete.mtl"
    v1_obj = tmp_path / "v1_complete.fixed.obj"
    v1_mtl = tmp_path / "v1_complete.fixed.mtl"
    out_dir = tmp_path / "out_keep_v1"

    raw_boxes = [
        ("minecraft_quartz_block_top_-1", 0.0, 0.0, 0.0, 8.0, 1.0, 8.0),
        ("minecraft_concrete_white_-1", 0.0, 1.0, 0.0, 8.0, 4.0, 0.5),
        ("minecraft_concrete_white_-1", 0.0, 1.0, 7.5, 8.0, 4.0, 8.0),
        ("minecraft_concrete_white_-1", 0.0, 1.0, 0.5, 0.5, 4.0, 7.5),
        ("minecraft_concrete_white_-1", 7.5, 1.0, 0.5, 8.0, 4.0, 7.5),
    ]
    # Simulated healthy v1 shifted down by 1.0m (same floor/wall footprint, only slab floor_y shifted)
    v1_boxes = [(m, x0, y0 - 1.0, z0, x1, y1 - 1.0, z1) for m, x0, y0, z0, x1, y1, z1 in raw_boxes]
    _write_box_obj(raw_boxes, raw_obj, raw_mtl)
    _write_box_obj(v1_boxes, v1_obj, v1_mtl)

    rep = run_solid_rebuild(v1_obj, out_dir, raw_ref_obj=raw_obj, low_cut_m=1.25, plinth_m=0.04)
    assert rep.passed is True
    assert rep.manifest["raw_recovery"]["used_raw_structural_fallback"] is False
    assert abs(rep.manifest["elevations_m"]["floor_y"] - 0.0) < 0.05
