from __future__ import annotations

import json
from pathlib import Path

from tests.test_solid_cutaway_rebuild import _write_box_obj
from tools.batch_solid_rebuild import _is_non_interior_folder, run_batch_rebuild


def test_is_non_interior_folder_skips_rooftops_and_sidewalks() -> None:
    assert _is_non_interior_folder("Floor_RF") is True
    assert _is_non_interior_folder("Sidewalk_2F") is True
    assert _is_non_interior_folder("Roof_Deck") is True
    assert _is_non_interior_folder("Floor_4F") is False
    assert _is_non_interior_folder("Floor_9M") is False
    assert _is_non_interior_folder("Floor_4B") is False


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
