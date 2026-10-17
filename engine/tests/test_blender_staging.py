"""Unit tests for Blender Staging (02_STAGING_DEVELOPMENT) path resolution and applier helpers."""
from __future__ import annotations

from pathlib import Path

from engine.campus.blender_staging import (
    BUILDING_TO_BLENDER_BUCKET,
    collect_repaired_floor_objs,
    resolve_staging_targets,
)


def test_resolve_staging_targets_maps_building_to_staging_blend_files(tmp_path: Path) -> None:
    staging_root = tmp_path / "02_STAGING_DEVELOPMENT"
    (staging_root / "BUILDINGS").mkdir(parents=True)
    (staging_root / "BUILDINGS_AND_ENVIRONMENT" / "libraries").mkdir(parents=True)

    b_only = staging_root / "BUILDINGS" / "UC-BUILDINGS-STAGING.blend"
    b_env = staging_root / "BUILDINGS_AND_ENVIRONMENT" / "UC-BUILDINGS-AND-ENVIRONMENT-STAGING.blend"
    lib_chtm = staging_root / "BUILDINGS_AND_ENVIRONMENT" / "libraries" / "CHTM.blend"
    for p in (b_only, b_env, lib_chtm):
        p.write_bytes(b"BLENDER")

    targets = resolve_staging_targets(tmp_path, "CHTM")
    assert targets["bucket"] == "CHTM"
    assert targets["buildings_staging_blend"] == b_only
    assert targets["environment_staging_blend"] == b_env
    assert targets["library_blend"] == lib_chtm
    assert BUILDING_TO_BLENDER_BUCKET["Main-Infrastructure"] == "INFRA"
    assert BUILDING_TO_BLENDER_BUCKET["MAIN_INFRA"] == "INFRA"


def test_collect_repaired_floor_objs_discovers_all_fixed_floor_packages(tmp_path: Path) -> None:
    by_b = tmp_path / "Exports/Repaired-Buildings-20261015/ByBuilding/CHTM"
    f1 = by_b / "Floor_4B"
    f1.mkdir(parents=True)
    (f1 / "CHTM_1st_floor_obj.fixed.obj").write_text("v 0 0 0\n", encoding="utf-8")
    (f1 / "CHTM_1st_floor_obj.mtl").write_text("newmtl m\n", encoding="utf-8")

    found = collect_repaired_floor_objs(tmp_path, "CHTM")
    assert len(found) == 1
    assert found[0]["floor_code"] == "Floor_4B"
    assert found[0]["stem"] == "CHTM_1st_floor_obj"
    assert found[0]["fixed_obj"] == f1 / "CHTM_1st_floor_obj.fixed.obj"
