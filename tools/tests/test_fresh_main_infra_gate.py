from pathlib import Path

from tools.repair_fresh_main_infra import pilot_gate, verify_frozen


def test_nonplanar_pilot_stops_without_candidate(tmp_path):
    raw = tmp_path / "raw"
    raw.mkdir()
    (raw / "pilot.obj").write_text("v 0 0 0\nv 1 0 0\nv 1 1 .01\nv 0 1 0\nf 1 2 3 4\n")
    result = pilot_gate(raw, pilots={"1F": "pilot.obj"})
    assert result["status"] == "blocked"
    assert result["pilots"]["1F"]["status"] == "blocked_ingest"
    assert "nonplanar" in result["pilots"]["1F"]["error"]
    assert not list(tmp_path.rglob("*.fixed.obj"))


def test_planar_pilot_still_requires_units_and_baseline_gates(tmp_path):
    (tmp_path / "pilot.obj").write_text("v 0 0 0\nv 1 0 0\nv 0 1 0\nf 1 2 3\n")
    result = pilot_gate(tmp_path, pilots={"1F": "pilot.obj"})
    assert result["status"] == "blocked"
    assert "physical_scale_evidence" in result["missing_gates"]
    assert "raw_vs_normalized_render_comparison" in result["missing_gates"]
    assert result["candidate_count"] == 0


def test_frozen_manifest_tamper_is_blocked(tmp_path):
    raw = tmp_path / "raw"
    raw.mkdir()
    (raw / "source.obj").write_text("changed")
    result = verify_frozen(tmp_path, {"files": [{"path": "source.obj", "sha256": "wrong", "size": 7}]})
    assert result["status"] == "blocked"
    assert result["failures"]


def test_manifest_traversal_is_blocked_without_reading_outside(tmp_path):
    result = verify_frozen(tmp_path, {"files": [{"path": "../outside.obj", "sha256": "wrong", "size": 7}]})
    assert result["status"] == "blocked"
    assert "outside raw" in result["failures"][0]
