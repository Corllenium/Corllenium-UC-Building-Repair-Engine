"""Job P2-K0 item 1: a non-legacy stage whose final check verdict is not PASS (failures charged to no site, or rounds
exhausted) is rolled back as a whole and logged; the unit continues from the stage input. Legacy stages keep their
behaviour (ruling K3-R2). Fixtures: a minimal NON-legacy engine (`plan()` returns `Edit`s directly).
"""
from __future__ import annotations

import json
import pathlib
from dataclasses import dataclass

from engine.repair.types import Edit, apply_edits
from engine.tests.test_kernel_site_checks import (BAD, GOOD_CUT, GOOD_DUP, _bad, _cube_scene, _ev, _good_edits,
                                                  _NoisyJudge, _run, _same)
from engine.tests.test_validate_mutations import LOOKS


@dataclass
class _Mini:
    """The minimal non-legacy engine: a `name` and a `plan()` that returns `Edit`s directly, no legacy stage."""
    name: str
    edits: list

    def plan(self, unit, ctx):
        return list(self.edits)


def _lines(path: pathlib.Path) -> list[dict]:
    return [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines()]


def test_a_non_legacy_stage_with_a_failure_charged_to_no_site_is_rolled_back_as_a_whole(tmp_path):
    before, dup, cut = _cube_scene()
    good = _good_edits(before, dup, cut)
    log = tmp_path / "edit_log.jsonl"
    got, ctx = _run(before, LOOKS, [_Mini("mini", good)], judge=_NoisyJudge(LOOKS, margin=2.0), edit_log=log)
    (check,) = got.checks
    assert check["first"] == "FAIL" and check["final"] == "FAIL" and check["unknown"]["samples"] == 1
    assert [r["site"] for r in check["rolled_back"]] == [GOOD_DUP, GOOD_CUT]
    assert all(r["stage_rolled_back"] and r["charged"] == 0 for r in check["rolled_back"])
    assert check["stage_rolled_back"] and "FAIL" in check["stage_rolled_back"]
    assert got.kept == [] and got.rolled_back == good
    assert ctx.log == good, "every planned edit stays in the context's log"
    _same(got.mesh, before)
    lines = _lines(log)
    assert [line.get("rolled_back", False) for line in lines if "check" not in line] == [True, True]
    assert lines[-1]["check"]["stage_rolled_back"] == check["stage_rolled_back"]


def _exhausted_edits(before, dup, cut):
    """The unmasking chain of K3b (BAD plate + a copy, GOOD_DUP removal) plus the good re-triangulation GOOD_CUT.
    With one round, the chain runs out of rounds while GOOD_CUT is still kept and never re-checked."""
    n_dup = int(dup[0]) - 8
    plate = _bad("5 a face one inch in front of a visible face", before)
    copy = Edit(engine="E8", kind="add", faces=(), new_faces=before.face_v[n_dup][None], new_points=None,
                site=BAD, reason="copy", evidence=_ev(material=0), new_face_uv=before.uvs[before.face_vt[n_dup]][None])
    remove = Edit(engine="E4", kind="remove", faces=(n_dup, n_dup + 8), new_faces=None, new_points=None,
                  site=GOOD_DUP, reason="both copies", evidence=_ev())
    return [*plate, copy, remove, _good_edits(before, dup, cut)[1]]


def test_a_non_legacy_stage_that_runs_out_of_rounds_is_rolled_back_as_a_whole():
    before, dup, cut = _cube_scene()
    edits = _exhausted_edits(before, dup, cut)
    got, _ = _run(before, LOOKS, [_Mini("mini", edits)], max_rounds=1)
    (check,) = got.checks
    assert check["rounds_exhausted"] is True and check["final"].startswith("UNCONFIRMED")
    assert [(r["site"], r["round"]) for r in check["rolled_back"]][:2] == [(BAD, 1), (GOOD_DUP, 2)]
    assert GOOD_CUT in [r["site"] for r in check["rolled_back"]], "the kept, never re-checked site is dropped too"
    assert "rounds exhausted" in check["stage_rolled_back"]
    assert got.kept == [] and got.rolled_back == edits
    _same(got.mesh, before)


def test_a_non_legacy_stage_that_passes_keeps_its_edits():
    before, dup, cut = _cube_scene()
    good = _good_edits(before, dup, cut)
    got, _ = _run(before, LOOKS, [_Mini("mini", good)])
    (check,) = got.checks
    assert check["final"] == "PASS" and not check["stage_rolled_back"]
    assert got.kept == good and got.rolled_back == []
    _same(got.mesh, apply_edits(before, good)[0])


def test_the_next_stage_continues_from_the_input_of_a_stage_that_was_rolled_back():
    before, dup, cut = _cube_scene()
    seen = []

    @dataclass
    class _Second:
        name: str = "second"

        def plan(self, unit, ctx):
            seen.append(unit.mesh)
            return []

    _run(before, LOOKS, [_Mini("mini", _good_edits(before, dup, cut)), _Second()],
         judge=_NoisyJudge(LOOKS, margin=2.0))
    _same(seen[0], before)
