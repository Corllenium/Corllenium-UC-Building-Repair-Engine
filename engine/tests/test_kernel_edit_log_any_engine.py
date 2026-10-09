"""Job P2-K0 item 2: the edit log works for any engine. The kernel computes the removed and added face keys from the
stage input and `apply_edits`, and takes the stage name from the engine; a non-legacy `Edit` needs no legacy evidence.
"""
from __future__ import annotations

import dataclasses
import json
import pathlib
from dataclasses import dataclass

import pytest

from engine.fixes.pipeline import FixProfile
from engine.repair.kernel import repair_unit
from engine.repair.types import Edit, RepairContext, UnitState, apply_edits, face_keys
from engine.tests.fixtures.build import box_with_partition_and_stitch
from engine.tests.test_kernel_site_checks import BAD, GOOD_CUT, _cube_scene, _good_edits, _run
from engine.tests.test_validate_mutations import LOOKS

_FAST = FixProfile(guard_size=(120, 80), n_dirs=32)


@dataclass
class _Mini:
    """The minimal non-legacy engine: a `name` and a `plan()` that returns `Edit`s directly, no legacy stage."""
    name: str
    edits: list

    def plan(self, unit, ctx):
        return list(self.edits)


def _bare(edits):
    """`edits` without any legacy evidence (a P2 engine's edits carry none of it)."""
    return [dataclasses.replace(e, evidence={k: v for k, v in e.evidence.items() if k == "material"})
            for e in edits]


def _lines(path: pathlib.Path) -> list[dict]:
    return [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines()]


def _mini_edits(before, dup, cut):
    """Three edits that carry no legacy evidence: a remove, a cut (it inherits its material) and an E8 add."""
    remove, cut_edit = _bare(_good_edits(before, dup, cut))
    add = Edit(engine="E8", kind="add", faces=(), new_faces=before.face_v[:1], new_points=None, site=BAD,
               reason="fill", evidence={"material": 1}, new_face_uv=before.uvs[before.face_vt[:1]])
    return remove, cut_edit, add


@pytest.mark.parametrize("validate", [False, True])
def test_the_edit_log_of_a_non_legacy_engine_has_its_stage_name_and_the_face_keys(tmp_path, validate):
    before, dup, cut = _cube_scene()
    remove, cut_edit, _ = _mini_edits(before, dup, cut)
    log = tmp_path / "edit_log.jsonl"
    if validate:
        got, _ = _run(before, LOOKS, [_Mini("mini", [remove, cut_edit])], edit_log=log)
    else:
        unit = UnitState(mesh=before, topo=None, looks={}, viewpoints=None)
        got = repair_unit(unit, RepairContext(profile=_FAST, decider=None, validator=None),
                          engines=[_Mini("mini", [remove, cut_edit])], edit_log=log)
    lines = [line for line in _lines(log) if "check" not in line]
    assert [line["stage"] for line in lines] == ["mini", "mini"]
    assert [(line["engine"], line["kind"]) for line in lines] == [("E4", "remove"), ("E7", "cut")]
    keys = face_keys(before, {})
    assert lines[0]["removed"] == [keys[i] for i in remove.faces] and lines[0]["added"] == []
    assert lines[0]["n_removed"] == 8 and lines[0]["n_added"] == 0 and lines[0]["material"] is None
    after = apply_edits(before, [cut_edit])[0]
    appended = face_keys(after, {})[-len(cut_edit.new_faces):]
    assert lines[1]["removed"] == [keys[i] for i in cut_edit.faces] and lines[1]["added"] == appended
    assert lines[1]["material"] == int(before.face_material[cut_edit.faces[0]]), "a cut's material is inherited"
    assert lines[1]["n_new_points"] == 0 and lines[1]["site"] == GOOD_CUT
    assert (any("check" in line for line in _lines(log))) is validate
    assert got.kept == [remove, cut_edit]


def test_the_edit_log_names_the_material_of_an_e8_add_and_the_keys_of_a_flip(tmp_path):
    before, dup, cut = _cube_scene()
    _, _, add = _mini_edits(before, dup, cut)
    flip = Edit(engine="E2", kind="flip", faces=(2,), new_faces=None, new_points=None, site=7, reason="r",
                evidence={})
    log = tmp_path / "edit_log.jsonl"
    unit = UnitState(mesh=before, topo=None, looks={}, viewpoints=None)
    repair_unit(unit, RepairContext(profile=_FAST, decider=None, validator=None),
                engines=[_Mini("mini", [flip, add])], edit_log=log)
    flipped, added = _lines(log)
    keys = face_keys(before, {})
    reversed_key = face_keys(dataclasses.replace(before, face_v=before.face_v[:, ::-1]), {})[2]
    assert flipped["removed"] == [keys[2]] and flipped["added"] == [reversed_key] and flipped["material"] is None
    assert added["material"] == 1 and added["removed"] == [] and len(added["added"]) == 1


def test_the_computed_keys_of_a_legacy_run_equal_the_keys_its_observer_recorded(tmp_path):
    mesh = box_with_partition_and_stitch()
    log = tmp_path / "edit_log.jsonl"
    unit = UnitState(mesh=mesh, topo=None, looks={}, viewpoints=None)
    got = repair_unit(unit, RepairContext(profile=_FAST, decider=None, validator=None), flatness={}, edit_log=log)
    lines = _lines(log)
    assert got.edits and len(lines) == len(got.edits)
    for line, edit in zip(lines, got.edits):
        assert line["removed"] == edit.evidence["removed_keys"], line
        assert line["added"] == edit.evidence["added_keys"], line
        assert line["stage"] == edit.evidence["stage"] and line["material"] == edit.evidence.get("material")
