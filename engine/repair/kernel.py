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
from collections import Counter
from dataclasses import dataclass, field
from pathlib import Path

import numpy as np

from engine.fixes.pipeline import FixResult, finish_fix
from engine.model import MeshData
from engine.repair.engines.legacy import LegacyEngine, LegacyRun, StageRecord, legacy_engines
from engine.repair.types import Edit, RepairContext, UnitState, apply_edits

#: Rounds of attribute, roll back and confirm per stage (P1-K3b); then what is still charged is rolled back.
MAX_ROUNDS = 3


@dataclass
class KernelResult:
    mesh: MeshData             # the shipped mesh: `result.mesh`
    result: FixResult | None   # exactly what `fix_object` returns for the same input (None: see `repair_unit`)
    edits: list[Edit]          # every observed edit, in run order
    stages: list[StageRecord]  # per stage: its input and output face sets and its edits
    report: dict | None        # `engine.cli`'s report.json dict (without `qa`/`skp`), given `obj_path`
    kept: list[Edit] = field(default_factory=list)         # the edits the shipped mesh carries
    rolled_back: list[Edit] = field(default_factory=list)  # the edits the site checks dropped
    checks: list[dict] = field(default_factory=list)       # one record per stage, with `validate_sites`
    records: list[dict] = field(default_factory=list)      # the lines of `edit_log.jsonl`, with `validate_sites`


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


def write_records(path: Path, records: list[dict]) -> None:
    """`edit_log.jsonl` of a checked run: the edit lines (a rolled-back one with `"rolled_back": true`), each
    stage's followed by its `{"check": {...}}` line."""
    with open(path, "w", encoding="utf-8", newline="\n") as fh:
        for record in records:
            fh.write(json.dumps(record) + "\n")


def repair_unit(unit: UnitState, ctx: RepairContext, *, flatness: dict[str, float] | None = None,
                obj_path: Path | None = None, edit_log: Path | None = None, engines: list | None = None,
                validate_sites: bool = False, rollback_legacy: bool = False,
                max_rounds: int = MAX_ROUNDS) -> KernelResult:
    """Run the legacy engines over `unit.mesh` with `ctx.profile` and `flatness` (per-material
    texture std, as `fix_object` takes it); `unit.looks` keys the faces. With `obj_path` (the input
    OBJ) the result carries `engine.cli`'s report dict; with `edit_log` the edits are written there.
    `unit.mesh` is set to the shipped mesh afterwards.

    `engines` (default: the legacy engines) runs other engines instead, each planning against the
    mesh the stage before it kept (`unit.mesh` when it plans); they give no `FixResult` (`result`
    and `report` are None).

    `validate_sites` (P1-K3b) checks every stage with the site judge in `ctx.validator` (see
    `_check_stage`): sites whose edits could have broken something visible are rolled back, and the
    next stage runs on `apply_edits(stage_input, kept_edits)`. A LEGACY stage is one site and is not
    rolled back (ruling K3-R2): its verdict is logged and its edits kept, so the shipped mesh, the
    `FixResult` and the report are the unchecked run's. `rollback_legacy` (tests only) rolls a
    failing legacy stage back too; the legacy stages share one state, so the later ones are then
    skipped (logged), and `result` / `report` are None. Without `validate_sites` nothing here
    differs from P1-K2."""
    if validate_sites or engines is not None:
        return _repair_checked(unit, ctx, flatness=flatness, obj_path=obj_path, edit_log=edit_log,
                               engines=engines, validate_sites=validate_sites,
                               rollback_legacy=rollback_legacy, max_rounds=max_rounds)
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


# ------------------------------------------------------------------------------------ site checks

_SKIPPED = ("an earlier legacy stage was rolled back; the legacy stages share one state and cannot "
            "run on a kept result")


def _site_parts(stage_input: MeshData, edits: list[Edit], sites: list[int]):
    """`(after, parts)`: `after = apply_edits(stage_input, edits of sites)`, and per site the input
    faces its edits remove, flip or replace and the AFTER faces they add, cut or flip."""
    chosen = [e for e in edits if e.site in set(sites)]
    after, new_to_old = apply_edits(stage_input, chosen)
    survived = new_to_old >= 0
    at = np.full(stage_input.n_faces, -1, np.int64)
    at[new_to_old[survived]] = np.flatnonzero(survived)
    appended = int(survived.sum())
    parts = {s: ([], []) for s in sites}
    for e in chosen:
        touched, new = parts[e.site]
        if e.kind in ("remove", "flip", "cut"):
            touched.extend(e.faces)
        if e.kind == "flip":
            new.extend(at[list(e.faces)].tolist())
        if e.kind in ("add", "cut"):
            new.extend(range(appended, appended + len(e.new_faces)))
            appended += len(e.new_faces)
    return after, parts


def _status(verdict) -> str:
    """A focus run's verdict on the sites it judged: FAIL when any sample failed."""
    return "FAIL" if verdict.failed else "PASS"


def _merged(reasons: list[dict]) -> dict:
    out: Counter = Counter()
    for r in reasons:
        out.update(r)
    return {k: int(v) for k, v in sorted(out.items()) if v}


def _check_stage(judge, stage_input: MeshData, edits: list[Edit], *, stage: str, engine: str,
                 legacy: bool, rollback: bool, max_rounds: int) -> tuple[set, dict]:
    """Check one stage's edits; returns `(rolled-back site ids, the stage's check record)`.

    1. ONE focus run of the Validator (`judge.check`) on the union of every site's focus, AFTER
       being `apply_edits(stage_input, edits)`.
    2. Each failing sample is charged (`judge.attribute`) to every site that could have caused it;
       one charged to none is an unknown failure, logged and never dropped.
    3. With `rollback`, every charged site is rolled back (all its edits), and ONE confirming run on
       the kept sites follows; while it charges kept sites, again, at most `max_rounds` rounds;
       then what is still charged is rolled back with `rounds_exhausted`.

    The record: `runs` (per run: its kind, status, failing / charged / unknown sample counts, the
    Validator's counts by reason, faces in focus and seconds), `rolled_back` (per site: the round,
    the samples charged, how, the reasons of the Validator's sites holding them, their faces and the
    site's edit count), `unknown` (distinct samples over all runs, their faces and reasons), `first`
    and `final` (the stage's verdict before and after the rounds). Durations only, no timestamps."""
    sites = list(dict.fromkeys(e.site for e in edits))
    record = {"stage": stage, "engine": engine, "legacy": legacy, "rollback": rollback,
              "sites": len(sites), "edits": len(edits), "first": "PASS", "final": "PASS",
              "runs": [], "rolled_back": [], "unknown": {"samples": 0, "faces": [], "reasons": {}},
              "rounds": 0, "rounds_exhausted": False}
    if not edits:
        return set(), record
    judge.begin(stage_input)
    unknown_samples, unknown_faces, unknown_reasons = set(), set(), []

    def run(kept: list[int], kind: str):
        seconds = dict(judge.seconds)
        after, parts = _site_parts(stage_input, edits, kept)
        foci = {s: judge.site_focus(after, np.array(parts[s][0], np.int64),
                                    np.array(parts[s][1], np.int64)) for s in kept}
        verdict = judge.check(after, judge.union(list(foci.values())))
        att = judge.attribute(verdict, foci)
        s, summary = verdict.samples, verdict.summary
        charged = (np.unique(np.concatenate(list(att.charged.values()))) if att.charged
                   else np.zeros(0, np.int64))
        unknown = att.unknown
        unknown_samples.update(zip(s.face[unknown].tolist(), s.index[unknown].tolist()))
        unknown_faces.update(s.face[unknown].tolist())
        unknown_reasons.extend(s.clusters[c] for c in np.unique(s.cluster[unknown]).tolist())
        record["runs"].append({
            "kind": kind, "sites": len(kept), "status": _status(verdict), "failing": len(s),
            "charged": int(len(charged)), "unknown": int(len(unknown)),
            "textures": dict(summary["textures"]["reasons"]),
            "nothing_deleted": {k: summary["nothing_deleted"][k]
                                for k in ("deleted", "replaced", "covered", "overlaid")},
            "before_faces": summary["before_faces"], "after_faces": summary["after_faces"],
            "seconds": round(verdict.seconds, 2),
            "focus_seconds": round(judge.seconds["focus"] - seconds["focus"], 2),
            "cover_seconds": round(judge.seconds["cover"] - seconds["cover"], 2)})
        return verdict, att

    kept = list(sites)
    rolled: set = set()
    verdict, att = run(kept, "first")
    record["first"] = _status(verdict)
    rounds = 0
    while rollback:
        charged = [s for s in kept if s in att.charged]
        if not charged:
            break
        exhausted = rounds >= max_rounds
        samples = verdict.samples
        for site in charged:
            mine = att.charged[site]
            record["rolled_back"].append({
                "site": int(site), "round": rounds + 1, "charged": int(len(mine)),
                "how": dict(att.how[site]),
                "reasons": _merged([samples.clusters[c] for c in np.unique(samples.cluster[mine]).tolist()]),
                "faces": sorted(set(samples.face[mine].tolist()))[:50],
                "edits": sum(e.site == site for e in edits), "rounds_exhausted": exhausted})
        rolled.update(charged)
        kept = [s for s in kept if s not in rolled]
        if exhausted:
            record["rounds_exhausted"] = True
            break
        rounds += 1
        if not kept:
            break
        verdict, att = run(kept, "confirm")
    record["rounds"] = rounds
    record["unknown"] = {"samples": len(unknown_samples), "faces": sorted(unknown_faces)[:50],
                         "reasons": _merged(unknown_reasons)}
    if not kept:
        record["final"] = "NOTHING KEPT"
    elif record["rounds_exhausted"]:
        record["final"] = "UNCONFIRMED (rounds exhausted)"
    elif legacy and not rollback and verdict.failed:
        record["final"] = "FAIL (legacy stage kept, ruling K3-R2)"
    else:
        record["final"] = _status(verdict)
    return rolled, record


def _repair_checked(unit: UnitState, ctx: RepairContext, *, flatness, obj_path, edit_log, engines,
                    validate_sites: bool, rollback_legacy: bool, max_rounds: int) -> KernelResult:
    """`repair_unit` with site checks, or with engines of the caller's (see there)."""
    judge = ctx.validator
    if validate_sites and judge is None:
        raise ValueError("validate_sites needs the site judge in ctx.validator")
    input_mesh = unit.mesh
    run = None
    if engines is None:
        run = LegacyRun(input_mesh, {} if flatness is None else flatness, ctx.profile, unit.looks)
        engines = legacy_engines(run)
    current = input_mesh
    edits, kept_all, rolled_all, checks, records = [], [], [], [], []
    legacy_stopped = False
    for engine in engines:
        is_legacy = isinstance(engine, LegacyEngine)
        stage = engine.stage if is_legacy else engine.name
        if is_legacy and legacy_stopped:
            check = {"stage": stage, "engine": engine.name, "legacy": True, "skipped": _SKIPPED}
            checks.append(check)
            records.append({"check": check})
            continue
        stage_input = engine.run.current.as_mesh() if is_legacy else current
        unit.mesh = stage_input
        planned = engine.plan(unit, ctx)
        edits.extend(planned)
        ctx.log.extend(planned)
        rolled: set = set()
        check = None
        if validate_sites:
            rolled, check = _check_stage(judge, stage_input, planned, stage=stage, engine=engine.name,
                                         legacy=is_legacy, rollback=rollback_legacy or not is_legacy,
                                         max_rounds=max_rounds)
        kept = [e for e in planned if e.site not in rolled]
        kept_all.extend(kept)
        rolled_all.extend(e for e in planned if e.site in rolled)
        for e in planned:
            records.append({**edit_record(e), "rolled_back": True} if e.site in rolled else edit_record(e))
        if check is not None:
            checks.append(check)
            records.append({"check": check})
        if is_legacy and not rolled:
            current = engine.run.current.as_mesh()
        else:
            current = apply_edits(stage_input, kept)[0]
            legacy_stopped = legacy_stopped or is_legacy

    result = report = None
    mesh = current
    if run is not None and not legacy_stopped:
        result = finish_fix(run.state)
        mesh = result.mesh
        if obj_path is not None:
            from engine.cli import _build_report   # engine.cli imports this module lazily too
            report = _build_report(input_mesh.name, Path(obj_path), input_mesh, result, ctx.profile)
    if edit_log is not None:
        if validate_sites:
            write_records(Path(edit_log), records)
        else:
            write_edit_log(Path(edit_log), edits)
    unit.mesh = mesh
    return KernelResult(mesh=mesh, result=result, edits=edits,
                        stages=[] if run is None else run.stages, report=report, kept=kept_all,
                        rolled_back=rolled_all, checks=checks,
                        records=records if validate_sites else [])
