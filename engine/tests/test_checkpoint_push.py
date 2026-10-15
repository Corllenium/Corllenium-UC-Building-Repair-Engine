"""Tests for engine/campus/checkpoint_push.py: publishing verified floor models to 04-Corllenium-Building-Model-Repair."""
from __future__ import annotations

import json
from pathlib import Path
import numpy as np
import pytest

from engine.campus.checkpoint_push import (
    CheckpointGateError,
    convert_ckpt17_to_unity_coords,
    convert_unity_to_ckpt17_coords,
    detect_inter_floor_seam_conflicts,
    publish_floor_to_repair_repo,
    sha256_file,
)


def _make_verified_bundle(tmp_path: Path, ready: bool = True, verdict: str = "approved"):
    unit_dir = tmp_path / "output" / "CHTM_1st_floor_zone"
    unit_dir.mkdir(parents=True)
    fixed_obj = unit_dir / "CHTM_1st_floor_zone.fixed.obj"
    fixed_obj.write_text("v 0 0 0\nv 1 0 0\nv 0 1 0\nf 1 2 3\n", encoding="utf-8")
    report_json = unit_dir / "report.json"
    report_json.write_text(json.dumps({"passed": ready, "tris_before": 7856, "tris_after": 1820}), encoding="utf-8")
    val_json = unit_dir / "validation.json"
    val_json.write_text(json.dumps({"passed": ready}), encoding="utf-8")
    bundle = {
        "building": "CHTM",
        "unit": "CHTM_1st_floor_zone",
        "tris_before": 7856,
        "tris_after": 1820,
        "owner_verdict": verdict,
        "jev_gate": {
            "deterministic_passed": ready,
            "ready_for_owner_approval": ready,
            "recommended_action": "approve_for_unity_checkpoint" if ready else "reject_regression",
        },
    }
    return unit_dir, fixed_obj, report_json, val_json, bundle


def test_refuses_to_publish_when_jev_or_validator_gate_failed(tmp_path):
    unit_dir, fixed_obj, report_json, val_json, bundle = _make_verified_bundle(tmp_path, ready=False, verdict="approved")
    repair_repo = tmp_path / "04-Corllenium-Building-Model-Repair"
    repair_repo.mkdir()
    with pytest.raises(CheckpointGateError, match="gate"):
        publish_floor_to_repair_repo(
            bundle=bundle,
            artifacts={"fixed_obj": fixed_obj, "report_json": report_json, "validation_json": val_json},
            repair_repo_root=repair_repo,
        )


def test_refuses_to_publish_when_owner_has_not_approved(tmp_path):
    unit_dir, fixed_obj, report_json, val_json, bundle = _make_verified_bundle(tmp_path, ready=True, verdict="pending")
    repair_repo = tmp_path / "04-Corllenium-Building-Model-Repair"
    repair_repo.mkdir()
    with pytest.raises(CheckpointGateError, match="owner"):
        publish_floor_to_repair_repo(
            bundle=bundle,
            artifacts={"fixed_obj": fixed_obj, "report_json": report_json, "validation_json": val_json},
            repair_repo_root=repair_repo,
        )


def test_publishes_verified_files_and_writes_sha256_session_receipt(tmp_path):
    unit_dir, fixed_obj, report_json, val_json, bundle = _make_verified_bundle(tmp_path, ready=True, verdict="approved")
    repair_repo = tmp_path / "04-Corllenium-Building-Model-Repair"
    repair_repo.mkdir()

    receipt = publish_floor_to_repair_repo(
        bundle=bundle,
        artifacts={"fixed_obj": fixed_obj, "report_json": report_json, "validation_json": val_json},
        repair_repo_root=repair_repo,
        session_date="2026-10-14",
    )

    dst_obj = repair_repo / "Unity/Assets/Models/Campus/Repaired/CHTM/CHTM_1st_floor_zone/CHTM_1st_floor_zone.fixed.obj"
    assert dst_obj.is_file()
    assert sha256_file(dst_obj) == sha256_file(fixed_obj)
    assert receipt["building"] == "CHTM"
    assert receipt["unit"] == "CHTM_1st_floor_zone"
    assert len(receipt["files"]) == 4  # 3 artifacts + pipeline_bundle.json
    assert receipt["stage6_capabilities"]["step_6a_checkpoint_repo"]["sha256_verified"] is True
    assert receipt["stage6_capabilities"]["step_6b_unity_mirror_import"]["status"] == "verified"
    session_file = repair_repo / receipt["session_record"]
    assert session_file.is_file()


def test_ckpt17_to_unity_coord_roundtrip_and_stacked_seam_conflict_detection():
    pts_in = np.array([[100.0, 200.0, 1582.68], [150.0, 200.0, 1582.68], [100.0, 250.0, 1582.68]])
    pts_m = convert_ckpt17_to_unity_coords(pts_in)
    roundtrip = convert_unity_to_ckpt17_coords(pts_m)
    assert np.allclose(pts_in, roundtrip)

    faces = np.array([[0, 1, 2]])
    # Neighbor floor with overlapping horizontal slab at Z = 1582.70 (within 0.20 in seam tolerance)
    n_pts = np.array([[110.0, 210.0, 1582.70], [160.0, 210.0, 1582.70], [110.0, 260.0, 1582.70]])
    seam = detect_inter_floor_seam_conflicts(pts_in, faces, n_pts, faces, z_tol=0.20)
    assert seam["conflict_count"] == 1
    assert seam["base_conflict_faces"] == [0]
    assert seam["neighbor_conflict_faces"] == [0]

