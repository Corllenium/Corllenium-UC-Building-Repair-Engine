"""Tests for engine/decide/floor_gate.py: Jev + Validator final gate and 6-stage pipeline bundle."""
from __future__ import annotations

from pathlib import Path
from types import SimpleNamespace
import pytest

from engine.decide import jev
from engine.decide.jev import ChoiceQ, Decision, JevDecider, NoulQ, ScoreQ
from engine.decide.floor_gate import (
    STAGE_CODES,
    build_floor_questions,
    build_floor_state,
    build_pipeline_bundle,
    evaluate_floor_gate,
)


@pytest.fixture(autouse=True)
def _isolated_env(monkeypatch, tmp_path_factory):
    monkeypatch.setattr(jev, "DEFAULT_ENV_FILE", tmp_path_factory.mktemp("noenv") / "absent.env")


def _sample_inputs(passed: bool = True, val_passed: bool = True):
    errors_before = {
        "version": 2,
        "n_faces": 7856,
        "counts": {
            "flicker_diff": 4616,
            "flicker_same": 206,
            "reversed": 71,
            "hidden": 4085,
            "loose": 136,
            "open_edges": 454,
            "cracks": 954,
        },
    }
    errors_after = {
        "version": 2,
        "n_faces": 1820,
        "counts": {
            "flicker_diff": 0 if passed else 120,
            "flicker_same": 0,
            "reversed": 0,
            "hidden": 0,
            "loose": 0,
            "open_edges": 12,
            "cracks": 4,
        },
    }
    fix_report = {
        "tris_before": 7856,
        "tris_after": 1820,
        "passed": passed,
        "invariants": {
            "area_non_increasing": passed,
            "materials_unchanged": True,
            "bbox_unchanged": True,
            "cap_guard_passed": True,
            "final_guard_passed": passed,
        },
        "merge_report": {"rolled_back": not passed},
        "guard_final": {
            "totals": {
                "holes": 0 if passed else 5,
                "material_changed": 0,
                "moved_same_flat": 0,
                "moved_other": 0,
            }
        },
    }
    validation_report = {
        "passed": val_passed,
        "check1_textures_there": {"passed": val_passed, "failed_samples": 0 if val_passed else 3},
        "check2_problems_solved": {"passed": val_passed},
        "check3_nothing_deleted_or_covered": {
            "passed": val_passed,
            "max_pixels_per_viewpoint": 0 if val_passed else 9,
        },
    }
    return errors_before, errors_after, fix_report, validation_report


class _FakeJevAsk:
    def __init__(self, approve: bool = True):
        self.approve = approve
        self.calls = []

    def ask(self, state, questions):
        self.calls.append((state, questions))
        return {
            "invariants_intact": Decision(self.approve, 0.96, {"yes": 0.96, "no": 0.04}, "jev", True),
            "facade_preserved": Decision(self.approve, 0.94, {"yes": 0.94, "no": 0.06}, "jev", True),
            "error_reduction_score": Decision(9 if self.approve else 3, 0.91, {9: 0.91}, "jev", True),
            "release_action": Decision(
                "approve_for_unity_checkpoint" if self.approve else "needs_engine_tuning",
                0.93,
                {"approve_for_unity_checkpoint": 0.93},
                "jev",
                True,
            ),
        }


def test_questions_use_all_three_jev_primitives_and_respect_limits():
    qs = build_floor_questions("CHTM_1st_floor_zone")
    assert set(qs.keys()) == {
        "invariants_intact",
        "facade_preserved",
        "error_reduction_score",
        "release_action",
    }
    assert isinstance(qs["invariants_intact"], NoulQ)
    assert isinstance(qs["facade_preserved"], NoulQ)
    assert isinstance(qs["error_reduction_score"], ScoreQ)
    assert len(qs["error_reduction_score"].criteria) <= jev.MAX_SCORE_LEVELS
    assert isinstance(qs["release_action"], ChoiceQ)
    jev.check_question_limits(qs)


def test_floor_state_contains_only_structured_text_and_counts():
    eb, ea, fix_rep, val_rep = _sample_inputs()
    state = build_floor_state("CHTM", "CHTM_1st_floor_zone", eb, ea, fix_rep, val_rep)
    assert state["building"] == "CHTM"
    assert state["unit"] == "CHTM_1st_floor_zone"
    assert state["tris_before"] == 7856
    assert state["tris_after"] == 1820
    assert state["reduction_pct"] > 70.0
    assert state["errors_before"]["hidden"] == 4085
    assert state["errors_after"]["hidden"] == 0
    assert "positions" not in state and "vertices" not in state


def test_evaluate_floor_gate_combines_deterministic_checks_with_jev_decisions():
    eb, ea, fix_rep, val_rep = _sample_inputs(passed=True, val_passed=True)
    fake = _FakeJevAsk(approve=True)
    gate = evaluate_floor_gate(
        "CHTM",
        "CHTM_1st_floor_zone",
        eb,
        ea,
        fix_rep,
        val_rep,
        decider=fake,
    )
    assert gate["deterministic_passed"] is True
    assert gate["jev_available"] is True
    assert gate["ready_for_owner_approval"] is True
    assert gate["recommended_action"] == "approve_for_unity_checkpoint"
    assert gate["decisions"]["error_reduction_score"]["answer"] == 9


def test_evaluate_floor_gate_blocks_when_deterministic_validator_fails_even_if_jev_approves():
    """Hard rule (AGENTS.md §6 & §9): Jev never overrides the mathematical Validator or guards."""
    eb, ea, fix_rep, val_rep = _sample_inputs(passed=True, val_passed=False)
    fake = _FakeJevAsk(approve=True)
    gate = evaluate_floor_gate(
        "CHTM",
        "CHTM_1st_floor_zone",
        eb,
        ea,
        fix_rep,
        val_rep,
        decider=fake,
    )
    assert gate["deterministic_passed"] is False
    assert gate["ready_for_owner_approval"] is False


def test_build_pipeline_bundle_produces_six_horizontal_stages():
    eb, ea, fix_rep, val_rep = _sample_inputs(passed=True, val_passed=True)
    fake = _FakeJevAsk(approve=True)
    bundle = build_pipeline_bundle(
        building="CHTM",
        unit="CHTM_1st_floor_zone",
        errors_before=eb,
        errors_after=ea,
        fix_report=fix_rep,
        validation_report=val_rep,
        decider=fake,
    )
    assert [s["code"] for s in bundle["stages"]] == list(STAGE_CODES)
    assert len(bundle["stages"]) == 6
    assert bundle["stages"][0]["status"] == "done"
    assert bundle["stages"][4]["status"] == "done"
    assert bundle["stages"][5]["status"] == "doing"  # Waiting for owner review & push


def test_coplanar_region_joins_across_internal_wall_edge_on_all_buildings():
    """Verify two coplanar horizontal faces join into the same region even when a perpendicular
    internal wall (with lower face index 0) shares their common edge."""
    import numpy as np
    from engine.model import MeshData
    from engine.pipeline import analyse_topology

    positions = np.array([
        [0.0, 0.0, 10.0],   # 0: shared edge A
        [0.0, 10.0, 10.0],  # 1: shared edge B
        [0.0, 5.0, 0.0],    # 2: bottom of internal vertical wall
        [-10.0, 5.0, 10.0], # 3: left horizontal top
        [10.0, 5.0, 10.0],  # 4: right horizontal top
    ])
    # Face 0 is the vertical wall under edge (0,1); faces 1 and 2 are the flat horizontal top
    face_v = np.array([
        [0, 1, 2],  # face 0: vertical wall
        [0, 1, 3],  # face 1: left horizontal top (+Z normal)
        [1, 0, 4],  # face 2: right horizontal top (+Z normal)
    ], dtype=np.int64)
    mesh = MeshData(
        name="col_top",
        positions=positions,
        uvs=np.zeros((0, 2)),
        normals=np.zeros((0, 3)),
        face_v=face_v,
        face_vt=np.full((3, 3), -1, dtype=np.int64),
        face_vn=np.full((3, 3), -1, dtype=np.int64),
        face_material=np.array([0, 0, 0], dtype=np.int64),
        face_line=np.array([1, 2, 3], dtype=np.int64),
        materials=["silver_concrete"],
        mtllib=None,
        coord_decimals=2,
        sig_digits=4,
    )
    topo = analyse_topology(mesh, flat_materials=frozenset({0}))
    assert topo.face_region[1] >= 0
    assert topo.face_region[1] == topo.face_region[2]

