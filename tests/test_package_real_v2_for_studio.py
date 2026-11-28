"""Unit tests for tools/package_real_v2_for_studio.py (Real-Model v2 -> Interior Studio GLB)."""

from __future__ import annotations

from pathlib import Path
import sys

import numpy as np
import trimesh
from trimesh.visual.material import PBRMaterial
from trimesh.visual.texture import TextureVisuals

REPO_ROOT = Path(__file__).resolve().parent.parent
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from tools.package_real_v2_for_studio import package_real_v2_floor, slice_triangles_by_y


def test_slice_triangles_by_y_preserves_area_and_interpolated_uvs() -> None:
    # Vertical quad [0..2] x [0..4] split at y=1.25
    verts = np.array(
        [
            [0.0, 0.0, 0.0],
            [2.0, 0.0, 0.0],
            [2.0, 4.0, 0.0],
            [0.0, 4.0, 0.0],
        ],
        dtype=np.float64,
    )
    faces = np.array([[0, 1, 2], [0, 2, 3]], dtype=np.int64)
    uvs = np.array([[0.0, 0.0], [1.0, 0.0], [1.0, 1.0], [0.0, 1.0]], dtype=np.float64)

    (bv, bf, bu), (av, af, au) = slice_triangles_by_y(verts, faces, uvs, 1.25)

    assert len(bf) >= 2 and len(af) >= 2
    assert bu is not None and au is not None
    assert np.isclose(bv[:, 1].max(), 1.25, atol=1e-5)
    assert np.isclose(av[:, 1].min(), 1.25, atol=1e-5)

    # At y = 1.25 out of 4.0, interpolated V must be 1.25 / 4.0 = 0.3125
    cut_b = np.isclose(bv[:, 1], 1.25, atol=1e-5)
    cut_a = np.isclose(av[:, 1], 1.25, atol=1e-5)
    assert np.allclose(bu[cut_b, 1], 0.3125, atol=1e-4)
    assert np.allclose(au[cut_a, 1], 0.3125, atol=1e-4)

    # Total area preserved exactly (2.0 * 4.0 = 8.0)
    bm = trimesh.Trimesh(vertices=bv, faces=bf, process=False)
    am = trimesh.Trimesh(vertices=av, faces=af, process=False)
    assert np.isclose(bm.area + am.area, 8.0, atol=1e-5)


def test_package_real_v2_floor_synthetic_room_creates_semantic_tiers_and_caps(tmp_path: Path) -> None:
    # Build a synthetic room: 10m x 8m slab at y=56.2, perimeter walls + 1 interior partition to y=59.95, ceiling at y=59.95
    mat_wall = PBRMaterial(name="mat_wall_real", baseColorFactor=[0.85, 0.85, 0.82, 1.0], doubleSided=True)
    mat_floor = PBRMaterial(name="mat_floor_real", baseColorFactor=[0.70, 0.72, 0.70, 1.0], doubleSided=True)

    slab = trimesh.creation.box(extents=[10.0, 0.4, 8.0])
    slab.apply_translation([0.0, 56.0, 0.0])
    slab.visual = TextureVisuals(uv=np.zeros((len(slab.vertices), 2)), material=mat_floor)

    wall_w = trimesh.creation.box(extents=[0.2, 3.75, 8.0])
    wall_w.apply_translation([-4.9, 58.075, 0.0])
    wall_e = trimesh.creation.box(extents=[0.2, 3.75, 8.0])
    wall_e.apply_translation([4.9, 58.075, 0.0])
    wall_n = trimesh.creation.box(extents=[10.0, 3.75, 0.2])
    wall_n.apply_translation([0.0, 58.075, 3.9])
    wall_s = trimesh.creation.box(extents=[10.0, 3.75, 0.2])
    wall_s.apply_translation([0.0, 58.075, -3.9])
    wall_in = trimesh.creation.box(extents=[0.2, 3.75, 6.0])
    wall_in.apply_translation([0.0, 58.075, 0.0])
    ceil = trimesh.creation.box(extents=[10.0, 0.15, 8.0])
    ceil.apply_translation([0.0, 59.925, 0.0])

    walls = trimesh.util.concatenate([wall_w, wall_e, wall_n, wall_s, wall_in, ceil])
    walls.visual = TextureVisuals(uv=np.zeros((len(walls.vertices), 2)), material=mat_wall)

    sc = trimesh.Scene()
    sc.add_geometry(slab, node_name="real_floor_mesh", geom_name="real_floor_mesh")
    sc.add_geometry(walls, node_name="real_walls_mesh", geom_name="real_walls_mesh")

    in_glb = tmp_path / "SYNTH_Floor_4F.glb"
    out_glb = tmp_path / "SYNTH_Floor_4F.real_v2.studio.glb"
    sc.export(in_glb, file_type="glb")

    mf = package_real_v2_floor(
        input_glb=in_glb,
        output_glb=out_glb,
        building="SYNTH",
        floor="Floor_4F",
        floor_y=56.2,
        lintel_y=58.68,
        ceil_y=59.95,
    )

    assert mf["qa_passed"] is True
    assert mf["max_bbox_delta_m"] <= 0.02
    assert mf["overhead_top_area_m2"] <= 65.0
    assert mf["preserved_materials_count"] == 2
    assert mf["group_triangles"].get("Floor_Slab", 0) > 0
    assert mf["group_triangles"].get("Wall_Ext_W_01", 0) > 0
    assert mf["group_triangles"].get("Wall_Interior_01", 0) > 0
    assert mf["cutcap_triangles"].get("CutCap_Interior", 0) > 0


def test_solid_cutcap_fills_1m_hollow_wall_and_column_without_bridging_doorway(tmp_path: Path) -> None:
    # Hollow 0.8m thick perimeter/interior wall shell (only 4 vertical outer skins, open at y=cut_y)
    # with a 1.0m doorway + hollow 1.0m x 1.0m square column shell inside the room.
    mat_wall = PBRMaterial(name="mat_wall_real", baseColorFactor=[0.85, 0.85, 0.82, 1.0], doubleSided=True)
    mat_floor = PBRMaterial(name="mat_floor_real", baseColorFactor=[0.70, 0.72, 0.70, 1.0], doubleSided=True)

    slab = trimesh.creation.box(extents=[14.0, 0.2, 12.0])
    slab.apply_translation([0.0, -0.1, 0.0])
    slab.visual = TextureVisuals(uv=np.zeros((len(slab.vertices), 2)), material=mat_floor)

    def _open_box_sides(cx: float, cz: float, sx: float, sz: float, h: float = 3.75) -> trimesh.Trimesh:
        b = trimesh.creation.box(extents=[sx, h, sz])
        b.apply_translation([cx, h * 0.5, cz])
        keep = np.abs(b.face_normals[:, 1]) < 0.5  # hollow shell (no top/bottom caps!)
        return trimesh.Trimesh(vertices=b.vertices, faces=b.faces[keep], process=False)

    # Interior 0.8m thick wall split by a 1.0m doorway z in [-0.5, +0.5], plus 1.0m x 1.0m hollow column
    w_s = _open_box_sides(0.0, -3.0, 0.8, 5.0)   # z=[-5.5, -0.5]
    w_n = _open_box_sides(0.0, +3.0, 0.8, 5.0)   # z=[+0.5, +5.5]
    col = _open_box_sides(3.5, 0.0, 1.0, 1.0)    # 1.0m x 1.0m hollow square column
    walls = trimesh.util.concatenate([w_s, w_n, col])
    walls.visual = TextureVisuals(uv=np.zeros((len(walls.vertices), 2)), material=mat_wall)

    sc = trimesh.Scene()
    sc.add_geometry(slab, node_name="floor", geom_name="floor")
    sc.add_geometry(walls, node_name="walls", geom_name="walls")

    in_glb = tmp_path / "HOLLOW_4F.glb"
    out_glb = tmp_path / "HOLLOW_4F.real_v2.studio.glb"
    sc.export(in_glb, file_type="glb")

    mf = package_real_v2_floor(
        input_glb=in_glb,
        output_glb=out_glb,
        building="HOLLOW",
        floor="Floor_4F",
        floor_y=0.0,
        lintel_y=2.5,
        ceil_y=3.75,
    )
    assert mf["qa_passed"] is True
    out_sc = trimesh.load(out_glb, force="scene")
    caps = [g for k, g in out_sc.geometry.items() if k.startswith("CutCap_")]
    assert caps
    cap_u = trimesh.util.concatenate(caps)
    # Expected solid XZ area: two 0.8x5.0 walls (8.0 m^2) + 1.0x1.0 column (1.0 m^2) = 9.0 m^2
    assert float(cap_u.area) >= 0.95 * 9.0
    # 1.0m doorway center (x=0, z=0) must remain 100% open (no cap triangle near x in [-0.3,0.3], z in [-0.3,0.3])
    cc = cap_u.vertices[cap_u.faces].mean(axis=1)
    in_door = (np.abs(cc[:, 0]) < 0.30) & (np.abs(cc[:, 2]) < 0.30)
    assert not np.any(in_door)


def test_slanted_exterior_wall_stays_unified_without_stair_contamination(tmp_path: Path) -> None:
    mat_wall = PBRMaterial(name="mat_wall_real", baseColorFactor=[0.85, 0.85, 0.82, 1.0], doubleSided=True)
    mat_floor = PBRMaterial(name="mat_floor_real", baseColorFactor=[0.70, 0.72, 0.70, 1.0], doubleSided=True)

    # Diagonal-right pentagon floor with a 45-degree slanted exterior wall from (10,-5) to (2,-5) -> wait:
    # Make main slab [0..10] x [-5..5] plus slanted east wing to (14, 0):
    from shapely.geometry import Polygon as SPoly
    fp = SPoly([(0.0, -5.0), (10.0, -5.0), (14.0, 0.0), (10.0, 5.0), (0.0, 5.0)])
    fv2d, ff2d = trimesh.creation.triangulate_polygon(fp, engine="earcut")
    slab = trimesh.Trimesh(
        vertices=np.column_stack([fv2d[:, 0], np.zeros(len(fv2d)), fv2d[:, 1]]),
        faces=ff2d,
        process=False,
    )
    slab.visual = TextureVisuals(uv=np.zeros((len(slab.vertices), 2)), material=mat_floor)

    # Slanted exterior wall along (10,-5)->(14,0)->(10,5), including a slanted window sill
    pts_ext = [(10.0, -5.0), (14.0, 0.0), (10.0, 5.0)]
    wall_meshes = []
    for (x0, z0), (x1, z1) in zip(pts_ext[:-1], pts_ext[1:]):
        wv = np.array([
            [x0, 0.0, z0], [x1, 0.0, z1], [x1, 3.75, z1], [x0, 3.75, z0],
        ], dtype=np.float64)
        wf = np.array([[0, 1, 2], [0, 2, 3]], dtype=np.int64)
        wall_meshes.append(trimesh.Trimesh(vertices=wv, faces=wf, process=False))
    # Also an interior sloped diagonal strut far inside (x=5..6)
    sloped_ext = trimesh.Trimesh(
        vertices=np.array([[10.0, 0.5, -5.0], [14.0, 0.5, 0.0], [12.0, 2.0, -2.5]]),
        faces=np.array([[0, 1, 2]]),
        process=False,
    )
    walls = trimesh.util.concatenate(wall_meshes + [sloped_ext])
    walls.visual = TextureVisuals(uv=np.zeros((len(walls.vertices), 2)), material=mat_wall)

    sc = trimesh.Scene()
    sc.add_geometry(slab, node_name="floor", geom_name="floor")
    sc.add_geometry(walls, node_name="walls", geom_name="walls")

    in_glb = tmp_path / "SLANT_4F.glb"
    out_glb = tmp_path / "SLANT_4F.real_v2.studio.glb"
    sc.export(in_glb, file_type="glb")

    mf = package_real_v2_floor(
        input_glb=in_glb,
        output_glb=out_glb,
        building="SLANT",
        floor="Floor_4F",
        floor_y=0.0,
        lintel_y=2.5,
        ceil_y=3.75,
    )
    assert mf["group_triangles"].get("Stairs_Upper_01", 0) == 0
    assert mf["group_triangles"].get("Wall_Interior_01", 0) == 0
    assert mf["group_triangles"].get("Wall_Ext_E_01", 0) > 0


def test_2m_capped_solid_pier_gets_filled_while_room_stays_open(tmp_path: Path) -> None:
    mat_wall = PBRMaterial(name="mat_wall_pier", baseColorFactor=[0.85, 0.85, 0.82, 1.0], doubleSided=True)
    mat_floor = PBRMaterial(name="mat_floor_pier", baseColorFactor=[0.70, 0.72, 0.70, 1.0], doubleSided=True)

    # Walkable floor ONLY around the outside & inside the 3x3 room (leaving [1..3]x[1..3] pier core without walkable floor)
    from shapely.geometry import Polygon as SPoly

    pier_box = trimesh.creation.box(extents=[2.0, 3.75, 2.0])
    pier_box.apply_translation([2.0, 1.875, 2.0])  # [1..3] x [0..3.75] x [1..3], capped at y=3.75
    pier_box.visual = TextureVisuals(uv=np.zeros((len(pier_box.vertices), 2)), material=mat_wall)

    # 3m x 3m closed-loop room walls around [5..8] x [0..3] with an open walkable floor at y=0
    room_walls = []
    for cx, cz, sx, sz in [
        (6.5, 0.05, 3.0, 0.10),
        (6.5, 2.95, 3.0, 0.10),
        (5.05, 1.5, 0.10, 3.0),
        (7.95, 1.5, 0.10, 3.0),
    ]:
        wb = trimesh.creation.box(extents=[sx, 3.75, sz])
        wb.apply_translation([cx, 1.875, cz])
        room_walls.append(wb)
    all_walls = trimesh.util.concatenate([pier_box, *room_walls])
    all_walls.visual = TextureVisuals(uv=np.zeros((len(all_walls.vertices), 2)), material=mat_wall)

    fp = SPoly([(0.0, -1.0), (9.0, -1.0), (9.0, 4.0), (0.0, 4.0)], holes=[[(1.05, 1.05), (2.95, 1.05), (2.95, 2.95), (1.05, 2.95)]])
    fv2d, ff2d = trimesh.creation.triangulate_polygon(fp, engine="earcut")
    slab = trimesh.Trimesh(
        vertices=np.column_stack([fv2d[:, 0], np.zeros(len(fv2d)), fv2d[:, 1]]),
        faces=ff2d[:, ::-1],
        process=False,
    )
    slab.visual = TextureVisuals(uv=np.zeros((len(slab.vertices), 2)), material=mat_floor)

    sc = trimesh.Scene()
    sc.add_geometry(slab, node_name="floor", geom_name="floor")
    sc.add_geometry(all_walls, node_name="walls", geom_name="walls")

    in_glb = tmp_path / "PIER_4F.glb"
    out_glb = tmp_path / "PIER_4F.real_v2.studio.glb"
    sc.export(in_glb, file_type="glb")

    mf = package_real_v2_floor(
        input_glb=in_glb,
        output_glb=out_glb,
        building="PIER",
        floor="Floor_4F",
        floor_y=0.0,
        lintel_y=2.5,
        ceil_y=3.75,
    )
    assert mf["qa_passed"] is True

    reloaded = trimesh.load(out_glb, force="scene")
    caps = [g for k, g in reloaded.geometry.items() if k.startswith("CutCap_") and "__Lower__" not in k]
    cap_u = trimesh.util.concatenate(caps)
    cap_polys = [
        SPoly([(float(cap_u.vertices[v, 0]), float(cap_u.vertices[v, 2])) for v in f]).buffer(0)
        for f in cap_u.faces
    ]
    from shapely.ops import unary_union
    cap_2d = unary_union(cap_polys).buffer(0)
    pier_2d = SPoly([(1.0, 1.0), (3.0, 1.0), (3.0, 3.0), (1.0, 3.0)])
    room_core = SPoly([(5.5, 0.5), (7.5, 0.5), (7.5, 2.5), (5.5, 2.5)])
    assert cap_2d.intersection(pier_2d).area / pier_2d.area >= 0.90
    assert cap_2d.intersection(room_core).area / room_core.area == 0.0

    # Full mode: 2m x 2m pier top cap (y ~= 3.75) stays on Wall_*__Upper__* (not stripped by wide_ceil_core or OverheadBeams)
    upper_caps = []
    for k, g in reloaded.geometry.items():
        if "__Upper__" not in k or k.startswith("OverheadBeams_"):
            continue
        up = (g.face_normals[:, 1] > 0.70) & (g.vertices[g.faces].mean(axis=1)[:, 1] >= 3.70)
        for f in g.faces[up]:
            upper_caps.append(SPoly([(float(g.vertices[v, 0]), float(g.vertices[v, 2])) for v in f]).buffer(0))
    assert upper_caps, "Expected Wall_*__Upper__ top cap over 2m x 2m pier in Full mode"
    upper_cap_2d = unary_union(upper_caps).buffer(0)
    assert upper_cap_2d.intersection(pier_2d).area / pier_2d.area >= 0.90

    # Floor mode: Wall_*__Plinth__cut_cap covers >= 90% of pier at y ~= plinth_y + 0.002 and 0% of room core
    pl_caps = [g for k, g in reloaded.geometry.items() if k.endswith("__Plinth__cut_cap")]
    assert len(pl_caps) >= 1
    pl_u = trimesh.util.concatenate(pl_caps)
    assert np.allclose(pl_u.vertices[:, 1], 0.062, atol=0.01)
    pl_polys = [
        SPoly([(float(pl_u.vertices[v, 0]), float(pl_u.vertices[v, 2])) for v in f]).buffer(0)
        for f in pl_u.faces
    ]
    pl_2d = unary_union(pl_polys).buffer(0)
    assert pl_2d.intersection(pier_2d).area / pier_2d.area >= 0.90
    assert pl_2d.intersection(room_core).area / room_core.area == 0.0


def test_coplanar_slanted_wall_and_t_junction_never_split_channels(tmp_path: Path) -> None:
    mat_wall = PBRMaterial(name="mat_wall_tj", baseColorFactor=[0.85, 0.85, 0.82, 1.0], doubleSided=True)
    mat_floor = PBRMaterial(name="mat_floor_tj", baseColorFactor=[0.70, 0.72, 0.70, 1.0], doubleSided=True)
    from shapely.geometry import Polygon as SPoly

    # Slab [0..14] x [-5..5] with slanted east wing to (14,0)
    fp = SPoly([(0.0, -5.0), (10.0, -5.0), (14.0, 0.0), (10.0, 5.0), (0.0, 5.0)])
    fv2d, ff2d = trimesh.creation.triangulate_polygon(fp, engine="earcut")
    slab = trimesh.Trimesh(
        vertices=np.column_stack([fv2d[:, 0], np.zeros(len(fv2d)), fv2d[:, 1]]),
        faces=ff2d[:, ::-1],
        process=False,
    )
    slab.visual = TextureVisuals(uv=np.zeros((len(slab.vertices), 2)), material=mat_floor)

    # 10m-span slanted exterior wall along (10,-5)->(14,0)->(10,5) PLUS perpendicular 8m interior T-junction wall from x=4 to x=14 at z=0
    ext_seg = trimesh.Trimesh(
        vertices=np.array([[10.0, 0.0, -5.0], [14.0, 0.0, 0.0], [14.0, 3.75, 0.0], [10.0, 3.75, -5.0]], dtype=np.float64),
        faces=np.array([[0, 1, 2], [0, 2, 3]], dtype=np.int64),
        process=False,
    )
    ext_seg2 = trimesh.Trimesh(
        vertices=np.array([[14.0, 0.0, 0.0], [10.0, 0.0, 5.0], [10.0, 3.75, 5.0], [14.0, 3.75, 0.0]], dtype=np.float64),
        faces=np.array([[0, 1, 2], [0, 2, 3]], dtype=np.int64),
        process=False,
    )
    t_junc = trimesh.Trimesh(
        vertices=np.array([[4.0, 0.0, 0.0], [14.0, 0.0, 0.0], [14.0, 3.75, 0.0], [4.0, 3.75, 0.0]], dtype=np.float64),
        faces=np.array([[0, 1, 2], [0, 2, 3]], dtype=np.int64),
        process=False,
    )
    walls = trimesh.util.concatenate([ext_seg, ext_seg2, t_junc])
    walls.visual = TextureVisuals(uv=np.zeros((len(walls.vertices), 2)), material=mat_wall)

    sc = trimesh.Scene()
    sc.add_geometry(slab, node_name="floor", geom_name="floor")
    sc.add_geometry(walls, node_name="walls", geom_name="walls")

    in_glb = tmp_path / "TJ_4F.glb"
    out_glb = tmp_path / "TJ_4F.real_v2.studio.glb"
    sc.export(in_glb, file_type="glb")

    package_real_v2_floor(
        input_glb=in_glb,
        output_glb=out_glb,
        building="TJ",
        floor="Floor_4F",
        floor_y=0.0,
        lintel_y=2.5,
        ceil_y=3.75,
    )

    reloaded = trimesh.load(out_glb, force="scene")
    upper_ext_e = [g for k, g in reloaded.geometry.items() if k.startswith("Wall_Ext_E_01__Upper__")]
    upper_ext_other = [
        g for k, g in reloaded.geometry.items()
        if any(k.startswith(p) for p in ("Wall_Ext_W_01__Upper__", "Wall_Ext_N_01__Upper__", "Wall_Ext_S_01__Upper__"))
    ]
    upper_int = [g for k, g in reloaded.geometry.items() if k.startswith("Wall_Interior_01__Upper__")]

    assert sum(len(g.faces) for g in upper_ext_e) >= 4
    assert sum(len(g.faces) for g in upper_ext_other) == 0
    assert sum(len(g.faces) for g in upper_int) >= 2
    # Every Interior Upper triangle must lie strictly on z ~= 0 (the T-junction wall), never on the slanted exterior wall
    int_u = trimesh.util.concatenate(upper_int)
    assert np.all(np.abs(int_u.vertices[int_u.faces, 2]) < 1e-4)
