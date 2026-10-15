"""Jev + Validator final verification gate and 6-stage horizontal pipeline bundle per floor unit.

Hard rules (AGENTS.md §3, §6, §9):
- Jev evaluates structured text and counts only (never meshes, vertex coordinates, or pixels).
- Jev is a decision & suggestion gate that works alongside the mathematical Validator (`engine.validate`).
  It NEVER overrides a failed mathematical invariant or Validator check: `ready_for_owner_approval`
  requires `deterministic_passed == True`.
"""
from __future__ import annotations

from typing import Any, Mapping

from engine.decide import jev, wire
from engine.decide.jev import ChoiceQ, Decision, JevDecider, NoulQ, ScoreQ

STAGE_CODES: tuple[str, ...] = (
    "source_import",
    "error_census",
    "engine_fix",
    "before_after_review",
    "validator_jev_gate",
    "checkpoint_push",
)

ERROR_KEYS: tuple[str, ...] = (
    "flicker_diff",
    "flicker_same",
    "reversed",
    "hidden",
    "loose",
    "open_edges",
    "cracks",
)

SCORE_RUBRIC: list[str] = [
    "0: Regression or catastrophic geometry loss",
    "1: Severe errors remain across most categories",
    "2: Minimal error reduction (<25%)",
    "3: Partial reduction but major flicker or holes remain",
    "4: Moderate cleanup (~50%) with unresolved structural gaps",
    "5: Majority of interior hidden faces removed but surface flicker remains",
    "6: Good cleanup (>70%) with minor open edges or cracks",
    "7: Strong cleanup (>80%) with all invariants holding",
    "8: Near-complete repair (>90%) with clean facade preservation",
    "9: Complete repair: invariants intact, facade preserved, target errors resolved",
]

RELEASE_ACTIONS: dict[str, str] = {
    "approve_for_unity_checkpoint": "All invariants and Validator checks pass; ready for owner approval and push to 04-Corllenium-Building-Model-Repair.",
    "needs_engine_tuning": "Engine fixers left resolvable errors or rolled back a pass; tune engine module before checkpointing.",
    "needs_manual_modelling": "Remaining defects are architectural gaps outside automated rules (e.g. non-planar missing geometry).",
    "reject_regression": "Guard or Validator detected visible surface loss, hole creation, or texture shift.",
}


def build_floor_questions(unit: str) -> dict[str, NoulQ | ChoiceQ | ScoreQ]:
    """The 4 typed Jev questions evaluated at Stage 5 of the building floor repair pipeline."""
    qs: dict[str, NoulQ | ChoiceQ | ScoreQ] = {
        "invariants_intact": NoulQ(
            instructions=(
                f"For floor unit '{unit}', do all geometric repair invariants hold "
                "(fix_passed is True, all invariants are True, merge was not rolled back, "
                "and guard_final reports 0 holes and 0 moved surfaces)?"
            ),
            qtype="gate.invariants_intact",
            subject=unit,
        ),
        "facade_preserved": NoulQ(
            instructions=(
                f"For floor unit '{unit}', are all visible exterior and interior eye-height "
                "facade textures preserved within the 4-pixel tolerance in Validator Check 1 and Check 3?"
            ),
            qtype="gate.facade_preserved",
            subject=unit,
        ),
        "error_reduction_score": ScoreQ(
            instructions=(
                f"Rate the overall geometry error reduction and repair quality for floor unit '{unit}' "
                "comparing errors_before vs errors_after and triangle reduction."
            ),
            criteria=list(SCORE_RUBRIC),
            qtype="gate.error_reduction_score",
            subject=unit,
        ),
        "release_action": ChoiceQ(
            instructions=(
                f"Select the appropriate pipeline release action for floor unit '{unit}' "
                "before publishing to the Unity checkpoint repository."
            ),
            criteria=dict(RELEASE_ACTIONS),
            qtype="gate.release_action",
            subject=unit,
        ),
    }
    jev.check_question_limits(qs)
    return qs


def _clean_counts(errors_doc: Mapping[str, Any] | None) -> dict[str, int]:
    if not errors_doc:
        return {k: 0 for k in ERROR_KEYS}
    raw = errors_doc.get("counts", errors_doc)
    return {k: int(raw.get(k, 0)) for k in ERROR_KEYS}


def build_floor_state(
    building: str,
    unit: str,
    errors_before: Mapping[str, Any] | None,
    errors_after: Mapping[str, Any] | None = None,
    fix_report: Mapping[str, Any] | None = None,
    validation_report: Mapping[str, Any] | None = None,
) -> dict[str, Any]:
    """Build a strictly text-and-numbers state dictionary for Jev evaluation (zero geometry/mesh bytes)."""
    eb = _clean_counts(errors_before)
    ea = _clean_counts(errors_after) if errors_after is not None else None

    tris_before = int(
        (fix_report or {}).get("tris_before")
        or (errors_before or {}).get("n_faces")
        or 0
    )
    tris_after = int(
        (fix_report or {}).get("tris_after")
        or (errors_after or {}).get("n_faces")
        or tris_before
    )
    reduction_pct = (
        round((1.0 - (tris_after / tris_before)) * 100.0, 2)
        if tris_before > 0 and tris_after <= tris_before
        else 0.0
    )

    invariants = dict((fix_report or {}).get("invariants") or {})
    guard_totals = dict(((fix_report or {}).get("guard_final") or {}).get("totals") or {})
    rolled_back = bool(((fix_report or {}).get("merge_report") or {}).get("rolled_back", False))

    val_passed = bool((validation_report or {}).get("passed", False))
    c1 = dict((validation_report or {}).get("check1_textures_there") or {})
    c2 = dict((validation_report or {}).get("check2_problems_solved") or {})
    c3 = dict((validation_report or {}).get("check3_nothing_deleted_or_covered") or {})

    return {
        "building": str(building),
        "unit": str(unit),
        "tris_before": tris_before,
        "tris_after": tris_after,
        "reduction_pct": reduction_pct,
        "errors_before": eb,
        "errors_after": ea,
        "fix_passed": bool((fix_report or {}).get("passed", False)),
        "invariants": {k: bool(v) for k, v in invariants.items()},
        "merge_rolled_back": rolled_back,
        "guard_holes": int(guard_totals.get("holes", 0)),
        "guard_material_changed": int(guard_totals.get("material_changed", 0)),
        "guard_moved_surfaces": int(guard_totals.get("moved_same_flat", 0))
        + int(guard_totals.get("moved_other", 0)),
        "validator": {
            "passed": val_passed,
            "check1_textures_there": bool(c1.get("passed", False)),
            "check2_problems_solved": bool(c2.get("passed", False)),
            "check3_nothing_deleted_or_covered": bool(c3.get("passed", False)),
            "max_deleted_pixels_per_view": int(c3.get("max_pixels_per_viewpoint", 0)),
        },
    }


def _is_deterministic_pass(state: Mapping[str, Any]) -> bool:
    if not state.get("fix_passed"):
        return False
    invariants = state.get("invariants") or {}
    if not invariants or not all(bool(v) for v in invariants.values()):
        return False
    if state.get("merge_rolled_back"):
        return False
    if int(state.get("guard_holes", 0)) > 0 or int(state.get("guard_moved_surfaces", 0)) > 0:
        return False
    validator = state.get("validator") or {}
    if not validator.get("passed"):
        return False
    return True


def evaluate_floor_gate(
    building: str,
    unit: str,
    errors_before: Mapping[str, Any] | None,
    errors_after: Mapping[str, Any] | None = None,
    fix_report: Mapping[str, Any] | None = None,
    validation_report: Mapping[str, Any] | None = None,
    decider: Any | None = None,
) -> dict[str, Any]:
    """Run deterministic checks + Jev typed questions on a floor unit."""
    state = build_floor_state(building, unit, errors_before, errors_after, fix_report, validation_report)
    det_passed = _is_deterministic_pass(state)
    questions = build_floor_questions(unit)

    active_decider = decider if decider is not None else JevDecider()
    raw_decisions: Mapping[str, Decision] = active_decider.ask(state, questions)

    serialized = {qid: wire.decision_to_json(dec) for qid, dec in raw_decisions.items()}
    jev_available = any(dec.source in ("jev", "pilot-import", "owner") for dec in raw_decisions.values())

    rel_dec = raw_decisions.get("release_action")
    if det_passed:
        if rel_dec and rel_dec.accepted and isinstance(rel_dec.answer, str):
            recommended = rel_dec.answer
        else:
            recommended = "approve_for_unity_checkpoint"
    else:
        if state.get("guard_holes", 0) > 0 or not (state.get("validator") or {}).get("passed", True):
            recommended = "reject_regression"
        else:
            recommended = "needs_engine_tuning"

    jev_approves = (
        not jev_available
        or (
            bool(raw_decisions.get("invariants_intact") and raw_decisions["invariants_intact"].answer is not False)
            and bool(raw_decisions.get("facade_preserved") and raw_decisions["facade_preserved"].answer is not False)
        )
    )

    return {
        "building": building,
        "unit": unit,
        "deterministic_passed": det_passed,
        "jev_available": jev_available,
        "ready_for_owner_approval": bool(det_passed and jev_approves),
        "recommended_action": recommended,
        "state": state,
        "decisions": serialized,
    }


def build_pipeline_bundle(
    building: str,
    unit: str,
    errors_before: Mapping[str, Any] | None,
    errors_after: Mapping[str, Any] | None = None,
    fix_report: Mapping[str, Any] | None = None,
    validation_report: Mapping[str, Any] | None = None,
    checkpoint_commit: str | None = None,
    owner_verdict: str = "pending",
    decider: Any | None = None,
) -> dict[str, Any]:
    """Assemble the 6-stage horizontal pipeline bundle consumed by the Corllenium Siege /buildings page."""
    has_before = errors_before is not None
    has_fix = fix_report is not None and errors_after is not None
    has_val = validation_report is not None

    gate = (
        evaluate_floor_gate(
            building,
            unit,
            errors_before,
            errors_after,
            fix_report,
            validation_report,
            decider=decider,
        )
        if has_fix and has_val
        else None
    )

    eb_counts = _clean_counts(errors_before)
    ea_counts = _clean_counts(errors_after) if errors_after is not None else None
    total_errors_before = sum(eb_counts.values())
    total_errors_after = sum(ea_counts.values()) if ea_counts is not None else None

    tris_before = int((fix_report or {}).get("tris_before") or (errors_before or {}).get("n_faces") or 0)
    tris_after = int((fix_report or {}).get("tris_after") or (errors_after or {}).get("n_faces") or 0) if has_fix else None

    fix_passed = bool((fix_report or {}).get("passed", False))
    stages = [
        {
            "stageNo": 1,
            "code": "source_import",
            "title": "1. Source Floor Model",
            "shortName": "Import",
            "status": "done" if has_before else "not_started",
            "gate": "passed" if has_before else "open",
            "summary": f"{building} / {unit} ({tris_before:,} faces)",
        },
        {
            "stageNo": 2,
            "code": "error_census",
            "title": "2. Error Census (7 Kinds)",
            "shortName": "Errors",
            "status": "done" if has_before else "not_started",
            "gate": "passed" if has_before else "open",
            "summary": f"{total_errors_before:,} total error instances identified" if has_before else "Awaiting scan",
        },
        {
            "stageNo": 3,
            "code": "engine_fix",
            "title": "3. Engine Repair Pass",
            "shortName": "Repair",
            "status": (
                "done"
                if has_fix and fix_passed
                else ("blocked" if has_fix and not fix_passed else ("doing" if has_before else "not_started"))
            ),
            "gate": "passed" if has_fix and fix_passed else "open",
            "summary": (
                f"{tris_before:,} → {tris_after:,} tris ({total_errors_after:,} errors left)"
                if has_fix and tris_after is not None and total_errors_after is not None
                else "Ready for local engine fix"
            ),
        },
        {
            "stageNo": 4,
            "code": "before_after_review",
            "title": "4. Before / After 3D & Guard",
            "shortName": "3D & Guard",
            "status": "done" if has_fix and fix_passed else "not_started",
            "gate": "passed" if has_fix and fix_passed else "open",
            "summary": "26-view orthographic guard + synced 3D meshbuf ready" if has_fix else "Awaiting engine output",
        },
        {
            "stageNo": 5,
            "code": "validator_jev_gate",
            "title": "5. Validator + Jev Gate",
            "shortName": "Jev Gate",
            "status": (
                "done"
                if gate and gate["ready_for_owner_approval"]
                else ("blocked" if gate and not gate["ready_for_owner_approval"] else "not_started")
            ),
            "gate": "passed" if gate and gate["ready_for_owner_approval"] else "open",
            "summary": (
                f"Action: {gate['recommended_action']}"
                if gate
                else "Awaiting Validator + Jev evaluation"
            ),
        },
        {
            "stageNo": 6,
            "code": "checkpoint_push",
            "title": "6. Owner Review & Push to 04-Repair",
            "shortName": "Push to 04",
            "status": (
                "done"
                if checkpoint_commit
                else ("doing" if gate and gate["ready_for_owner_approval"] else "not_started")
            ),
            "gate": "passed" if checkpoint_commit else "open",
            "summary": (
                f"Published to 04-Corllenium-Building-Model-Repair ({checkpoint_commit[:8]})"
                if checkpoint_commit
                else f"Owner verdict: {owner_verdict}"
            ),
        },
    ]

    return {
        "building": building,
        "unit": unit,
        "tris_before": tris_before,
        "tris_after": tris_after,
        "errors_before": eb_counts,
        "errors_after": ea_counts,
        "fix_report": dict(fix_report) if fix_report else None,
        "validation_report": dict(validation_report) if validation_report else None,
        "jev_gate": gate,
        "owner_verdict": owner_verdict,
        "checkpoint_commit": checkpoint_commit,
        "stages": stages,
    }
