from __future__ import annotations

import json
from pathlib import Path

from tests.test_solid_cutaway_rebuild import _write_box_obj
from tools.batch_solid_rebuild import (
    _is_non_interior_folder,
    audit_stacked_continuity,
    run_batch_rebuild,
)


def test_is_non_interior_folder_skips_rooftops_sidewalks_and_basements_by_default() -> None:
    assert _is_non_interior_folder("Floor_RF") is True
    assert _is_non_interior_folder("Sidewalk_2F") is True
    assert _is_non_interior_folder("Roof_Deck") is True
    assert _is_non_interior_folder("Floor_1B") is True
    assert _is_non_interior_folder("Floor_4B") is True
    assert _is_non_interior_folder("Floor_4B", include_basements=True) is False
    assert _is_non_interior_folder("Floor_4F") is False
    assert _is_non_interior_folder("Floor_9M") is False


def test_batch_solid_rebuild_writes_report_and_passes_six_gates(tmp_path: Path) -> None:
    src_root = tmp_path / "src"
    out_root = tmp_path / "out"
    floor_dir = src_root / "DEMO" / "Floor_1F"
    floor_dir.mkdir(parents=True)

    obj = floor_dir / "DEMO_1st_floor.fixed.obj"
    mtl = floor_dir / "DEMO_1st_floor.fixed.mtl"
    boxes = [
        ("minecraft_quartz_block_top_-1", 0.0, -0.5, 0.0, 10.0, 0.0, 10.0),
        ("minecraft_concrete_white_-1", 0.0, 0.0, 0.0, 10.0, 3.6, 0.5),
        ("minecraft_concrete_white_-1", 0.0, 0.0, 9.5, 10.0, 3.6, 10.0),
        ("minecraft_concrete_white_-1", 0.0, 0.0, 0.5, 0.5, 3.6, 9.5),
        ("minecraft_concrete_white_-1", 9.5, 0.0, 0.5, 10.0, 3.6, 9.5),
    ]
    _write_box_obj(boxes, obj, mtl)

    summary = run_batch_rebuild(src_root=src_root, out_root=out_root, building="DEMO", floors=["Floor_1F"])
    assert summary["all_passed"] is True
    report_path = out_root / "DEMO" / "batch_qa_report.json"
    assert report_path.is_file()
    report = json.loads(report_path.read_text(encoding="utf-8"))
    fl = report["floors"][0]
    assert fl["all_passed"] is True
    assert all(fl["gates"].values())
    assert fl["metrics"]["stepped_upper"] == []
    assert fl["metrics"]["non_ortho_steps"] == []
    assert fl["metrics"]["parapet_zfight"] == 0
    assert (out_root / "DEMO" / "Floor_1F" / "DEMO_1st_floor.fixed.solid_rebuild.unity.obj").is_file()


def test_audit_stacked_continuity_detects_missing_middle_wall(tmp_path: Path) -> None:
    import trimesh
    from shapely.geometry import box as sbox
    from engine.fixes.solid_cutaway_rebuild import geom_to_manifold, manifold_to_trimesh

    def _make_floor_glb(name: str, include_south: bool, y0: float) -> Path:
        sc = trimesh.Scene()
        walls = [
            ("Wall_Ext_N_00__Lower", sbox(0.0, 9.5, 10.0, 10.0)),
            ("Wall_Ext_W_00__Lower", sbox(0.0, 0.5, 0.5, 9.5)),
            ("Wall_Ext_E_00__Lower", sbox(9.5, 0.5, 10.0, 9.5)),
        ]
        if include_south:
            walls.append(("Wall_Ext_S_00__Lower", sbox(0.0, 0.0, 10.0, 0.5)))
        for node, poly in walls:
            man = geom_to_manifold(poly, y0, y0 + 1.25)
            assert man is not None
            sc.add_geometry(manifold_to_trimesh(man), node_name=node, geom_name=node)
        p = tmp_path / f"{name}.glb"
        p.write_bytes(sc.export(file_type="glb"))
        return p

    ok = audit_stacked_continuity([
        ("Floor_4F", 0.0, _make_floor_glb("4f", True, 0.0)),
        ("Floor_5F", 4.0, _make_floor_glb("5f", True, 4.0)),
        ("Floor_6F", 8.0, _make_floor_glb("6f", True, 8.0)),
    ])
    assert ok["has_large_gaps"] is False

    bad = audit_stacked_continuity([
        ("Floor_4F", 0.0, _make_floor_glb("4f_b", True, 0.0)),
        ("Floor_5F", 4.0, _make_floor_glb("5f_b", False, 4.0)),
        ("Floor_6F", 8.0, _make_floor_glb("6f_b", True, 8.0)),
    ])
    assert bad["has_large_gaps"] is True
    assert bad["flagged_floors"][0]["floor"] == "Floor_5F"
    assert bad["flagged_floors"][0]["missing_m2"] >= 4.5


def test_audit_rebuilt_glb_flags_floating_lower_parapet_and_floor_iron(tmp_path: Path) -> None:
    import trimesh
    from shapely.geometry import box as sbox
    from engine.fixes.solid_cutaway_rebuild import geom_to_manifold, load_raw_floor_obj, manifold_to_trimesh
    from tools.batch_solid_rebuild import audit_rebuilt_glb

    obj = tmp_path / "pit_audit.obj"
    mtl = tmp_path / "pit_audit.mtl"
    out_dir = tmp_path / "out"
    out_dir.mkdir()
    _write_box_obj([
        ("minecraft_quartz_block_top_-1", 0.0, -0.5, 4.0, 10.0, 0.0, 10.0),
        ("minecraft_concrete_white_-1", 0.0, 0.0, 4.0, 0.5, 3.6, 10.0),
    ], obj, mtl)
    for req in ("pit_audit.solid_rebuild.unity.obj", "materials.mtl", "rebuild_manifest.json", "watertight_audit.json"):
        (out_dir / req).write_text("ok", encoding="utf-8")

    sc = trimesh.Scene()
    slab = manifold_to_trimesh(geom_to_manifold(sbox(0.0, 4.0, 10.0, 10.0), -0.5, 0.0))
    sc.add_geometry(slab, node_name="Floor_Slab__tex_texture_0047_minecraft_iron_block__1", geom_name="Floor_Slab__tex_texture_0047_minecraft_iron_block__1")
    tail = manifold_to_trimesh(geom_to_manifold(sbox(5.0, 0.5, 5.25, 4.0), -0.5, 1.2))
    sc.add_geometry(tail, node_name="Stairs_Parapet_01__Lower__tex_texture_0047_minecraft_iron_block__1", geom_name="Stairs_Parapet_01__Lower__tex_texture_0047_minecraft_iron_block__1")
    glb = tmp_path / "bad.glb"
    glb.write_bytes(sc.export(file_type="glb"))

    qa = audit_rebuilt_glb(glb, obj, out_dir, {"all_watertight": True, "total_open_edges": 0, "total_nonmanifold_edges": 0, "narrow_wall_gaps": 0}, True)
    assert qa["gates"]["parapet_bounds_clean"] is False
    reasons = {a["reason"] for a in qa["metrics"]["parapet_anomalies"]}
    assert "floating_lower_parapet_tail" in reasons
    assert "floor_slab_iron_bleed" in reasons
