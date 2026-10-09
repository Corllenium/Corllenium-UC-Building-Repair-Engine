"""Job P2-E8b item 3: the flat fill in the repair kernel, and `repair-unit`'s engine choice (ruling E8b-R7).

Each fill is its own site, judged with `validate_sites=True`: the kernel hands the site judge the fills the edit log
marks (`evidence["flat_fill"]`, `evidence["loop"]`), and the Validator's `fill_site` class accepts what they cover
inside their own loops. A fill the check charges is rolled back. `repair-unit --engines E8` runs E8a (solidify) and
then E8b (fill) as two kernel stages; `--engines E8a` or `E8b` runs one.
"""
from __future__ import annotations

import dataclasses
import json
from dataclasses import dataclass

import numpy as np

from engine import cli
from engine.fixes.pipeline import FixProfile
from engine.repair.engines.e8_fill import E8FlatFill
from engine.repair.kernel import repair_unit
from engine.repair.types import Edit, RepairContext, UnitState, apply_edits
from engine.site_judge import SiteJudge
from engine.tests.fixtures.build import slab_with_three_skirts
from engine.tests.fixtures.holes import floor_over_room
from engine.tests.test_cli_repair_unit import _FAST, _campus
from engine.tests.test_validate_checks import _looks

LOOKS = _looks("m0", "m1")


def _scene():
    """The floor over a room with only its 20 in hole."""
    return floor_over_room(holes={(i, j) for i in (1, 2) for j in (1, 2)})


@dataclass
class _Altered:
    """E8b, with each planned edit passed through `change` (a mutation the check must catch)."""
    change: object
    name: str = "E8b"
    legacy: bool = False

    def plan(self, unit, ctx):
        return [self.change(e) for e in E8FlatFill().plan(unit, ctx)]


def _run(engine, mesh, log=None):
    unit = UnitState(mesh=mesh, topo=None, looks={}, viewpoints=None)
    ctx = RepairContext(profile=FixProfile(), decider=None, validator=SiteJudge(LOOKS))
    return repair_unit(unit, ctx, engines=[engine], validate_sites=True, edit_log=log)


def test_a_fill_is_its_own_site_judged_by_the_fill_site_class_and_kept(tmp_path):
    before = _scene()
    log = tmp_path / "edit_log.jsonl"
    got = _run(E8FlatFill(), before, log)
    (fill,) = got.kept
    assert got.rolled_back == [] and fill.evidence["flat_fill"] is True
    (check,) = got.checks
    assert (check["stage"], check["first"], check["final"]) == ("E8b", "PASS", "PASS")
    run = check["runs"][0]
    assert run["nothing_deleted"]["covered"] == 0 and run["covered_by_fill"] > 0, "the room below is covered by fill"
    shipped, _ = apply_edits(before, [fill])
    assert np.array_equal(got.mesh.face_v, shipped.face_v)
    lines = [json.loads(line) for line in log.read_text(encoding="utf-8").splitlines()]
    (edit,) = [line for line in lines if "check" not in line]
    assert (edit["engine"], edit["kind"], edit["n_new_points"], edit["stage"]) == ("E8", "add", 0, "E8b")
    assert edit["flat_fill"] is True and edit["loop"] == fill.evidence["loop"] and edit["n_added"] == 6


def test_a_fill_the_check_charges_is_rolled_back():
    """A fill in another look than its neighbours (a mutation of E8b's plan) covers the room below as plain
    `covered`: the check charges it and rolls it back, and the BEFORE ships."""
    def other_look(e: Edit) -> Edit:
        return dataclasses.replace(e, evidence={**e.evidence, "material": 1})
    before = _scene()
    got = _run(_Altered(other_look), before)
    assert got.kept == [] and len(got.rolled_back) == 1
    (check,) = got.checks
    assert check["first"] == "FAIL" and check["rolled_back"][0]["reasons"].get("covered", 0) > 0
    assert got.mesh.n_faces == before.n_faces


def test_the_kernel_hands_the_judge_the_mark_without_it_the_fill_is_rolled_back():
    def unmarked(e: Edit) -> Edit:
        evidence = {k: v for k, v in e.evidence.items() if k != "flat_fill"}
        return dataclasses.replace(e, evidence=evidence)
    got = _run(_Altered(unmarked), _scene())
    assert got.kept == [] and len(got.rolled_back) == 1


def test_a_stage_that_planned_nothing_still_writes_its_check_line(tmp_path):
    """Ruling P2-E8b-R10: every stage writes its check line; the edit log is the audit trail."""
    log = tmp_path / "edit_log.jsonl"
    mesh = floor_over_room(holes=set())                      # no hole: E8b plans nothing
    got = _run(E8FlatFill(), mesh, log)
    assert got.checks[0]["edits"] == 0 and got.checks[0]["final"] == "PASS"
    (line,) = [json.loads(x) for x in log.read_text(encoding="utf-8").splitlines()]
    assert line["check"]["stage"] == "E8b" and line["check"]["edits"] == 0


# ------------------------------------------------------------------------------------- repair-unit engines


def _cli(tmp_path, mesh, engines):
    paths, _snap = _campus(tmp_path, mesh)
    out = tmp_path / f"out_{'_'.join(engines)}"
    code = cli.cmd_repair_unit(out, unit="T-L01", engines=engines, campus_map=paths["map"], source=paths["source"],
                               materials=paths["materials"], profile=_FAST)
    return code, json.loads((out / "report.json").read_text(encoding="utf-8"))


def test_repair_unit_e8_runs_e8a_then_e8b_as_two_stages(tmp_path):
    code, report = _cli(tmp_path, _scene(), ["E8"])
    assert code == 0 and [s["stage"] for s in report["stages"]] == ["E8", "E8b"]
    assert report["engines"] == ["E8"]


def test_repair_unit_e8a_or_e8b_runs_one_stage(tmp_path):
    code, report = _cli(tmp_path / "a", _scene(), ["E8a"])
    assert code == 0 and [s["stage"] for s in report["stages"]] == ["E8"]
    code, report = _cli(tmp_path / "b", _scene(), ["E8b"])
    assert code == 0 and [s["stage"] for s in report["stages"]] == ["E8b"]


def test_repair_unit_e8_on_a_slab_e8a_closes_writes_one_check_line_per_stage(tmp_path):
    """E8b finds nothing left after E8a on slab_with_three_skirts; both stages still write their check line (R10)."""
    paths, _snap = _campus(tmp_path, slab_with_three_skirts())
    out = tmp_path / "out"
    assert cli.cmd_repair_unit(out, unit="T-L01", engines=["E8"], campus_map=paths["map"], source=paths["source"],
                               materials=paths["materials"], profile=_FAST) == 0
    lines = [json.loads(line) for line in (out / "edit_log.jsonl").read_text(encoding="utf-8").splitlines()]
    assert [line["check"]["stage"] for line in lines if "check" in line] == ["E8", "E8b"]


def test_the_parser_and_help_name_e8a_and_e8b():
    import argparse
    args = cli.build_parser().parse_args(["repair-unit", "--unit", "U", "--engines", "E8b", "--out", "o"])
    assert args.engines == ["E8b"]
    sub = next(a for a in cli.build_parser()._actions if isinstance(a, argparse._SubParsersAction))
    text = " ".join(sub.choices["repair-unit"].format_help().split())
    assert "E8a" in text and "E8b" in text
