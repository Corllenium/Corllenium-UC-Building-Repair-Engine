"""The observe-only repair kernel (P1-K2).

`repair_unit(unit, ctx)` runs today's `fix_object` stages through the legacy engines
(`engine.repair.engines.legacy`), in the same order and with the same parameters, and returns the
same final mesh and the same `FixResult` -- hence the same report.json -- as `fix_object`. Each
engine also returns the `Edit`s it OBSERVED its stage make; the kernel collects them (and appends
them to `ctx.log`) and, when asked, writes them to `edit_log.jsonl`. The edits are a record only:
nothing here applies them or changes what a stage produced. K3 starts applying them.

`edit_log.jsonl`: one JSON object per `Edit`, in run order, with the keys
`stage, engine, kind, site, reason, faces, removed, added, n_removed, n_added, n_new_points,
material`. `faces` are input face ids of the stage's own input face set; `removed` / `added` are
the K1 face keys the edit takes away and brings (a flip takes the old winding's key and brings
the reversed one). No path and no timestamp, so two runs of the same unit write the same bytes.
"""
from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path

from engine.fixes.pipeline import FixResult, finish_fix
from engine.model import MeshData
from engine.repair.engines.legacy import LegacyRun, StageRecord, legacy_engines
from engine.repair.types import Edit, RepairContext, UnitState


@dataclass
class KernelResult:
    mesh: MeshData             # the shipped mesh: `result.mesh`
    result: FixResult          # exactly what `fix_object` returns for the same input
    edits: list[Edit]          # every observed edit, in run order
    stages: list[StageRecord]  # per stage: its input and output face sets and its edits
    report: dict | None        # `engine.cli`'s report.json dict (without `qa`/`skp`), given `obj_path`


def edit_record(edit: Edit) -> dict:
    """One line of `edit_log.jsonl`."""
    evidence = edit.evidence
    removed, added = list(evidence["removed_keys"]), list(evidence["added_keys"])
    return {"stage": evidence["stage"], "engine": edit.engine, "kind": edit.kind,
            "site": int(edit.site), "reason": edit.reason, "faces": [int(f) for f in edit.faces],
            "removed": removed, "added": added, "n_removed": len(removed), "n_added": len(added),
            "n_new_points": 0 if edit.new_points is None else int(len(edit.new_points)),
            "material": evidence.get("material")}


def write_edit_log(path: Path, edits: list[Edit]) -> None:
    with open(path, "w", encoding="utf-8", newline="\n") as fh:
        for edit in edits:
            fh.write(json.dumps(edit_record(edit)) + "\n")


def repair_unit(unit: UnitState, ctx: RepairContext, *, flatness: dict[str, float] | None = None,
                obj_path: Path | None = None, edit_log: Path | None = None) -> KernelResult:
    """Run the legacy engines over `unit.mesh` with `ctx.profile` and `flatness` (per-material
    texture std, as `fix_object` takes it); `unit.looks` keys the faces. With `obj_path` (the input
    OBJ) the result carries `engine.cli`'s report dict; with `edit_log` the edits are written there.
    `unit.mesh` is set to the shipped mesh afterwards."""
    input_mesh = unit.mesh
    run = LegacyRun(input_mesh, {} if flatness is None else flatness, ctx.profile, unit.looks)
    edits: list[Edit] = []
    for engine in legacy_engines(run):
        planned = engine.plan(unit, ctx)
        edits.extend(planned)
        ctx.log.extend(planned)
    result = finish_fix(run.state)

    report = None
    if obj_path is not None:
        from engine.cli import _build_report   # engine.cli imports this module lazily too
        report = _build_report(input_mesh.name, Path(obj_path), input_mesh, result, ctx.profile)
    if edit_log is not None:
        write_edit_log(Path(edit_log), edits)
    unit.mesh = result.mesh
    return KernelResult(mesh=result.mesh, result=result, edits=edits, stages=run.stages,
                        report=report)
