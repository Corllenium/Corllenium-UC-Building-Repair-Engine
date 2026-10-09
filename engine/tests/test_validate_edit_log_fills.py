"""Fix round 1 of P2-E8b, ruling P2-E8b-R11: the floor Validator receives the fills.

Each flat-fill line of `edit_log.jsonl` carries its loop as model-coordinate points (`loop_points`) and the fill's
face ids in the shipped AFTER (`after_faces`). `engine.cli validate --edit-log <path>` reads the kept fills from it and
hands them to the Validator's `fill_site` class, so a fill that ships passes check 3 as `covered_by_fill`; without
the edit log the same pair fails check 3 (the room seen through the hole is covered).
"""
from __future__ import annotations

import json

import numpy as np

from engine import cli
from engine.io.obj_reader import read_obj
from engine.tests.fixtures.holes import floor_over_room
from engine.tests.test_cli_repair_unit import _FAST, _campus


def _repaired(tmp_path):
    """`floor_over_room` (one 20 in hole filled, one 60 in hole refused) repaired by E8b from a snapshot folder."""
    mesh = floor_over_room()
    paths, snap = _campus(tmp_path, mesh)
    out = tmp_path / "out"
    assert cli.cmd_repair_unit(out, snapshot=snap, engines=["E8b"], materials=paths["materials"], profile=_FAST) == 0
    return mesh, snap, out, paths


def _fill_lines(log):
    return [json.loads(line) for line in log.read_text(encoding="utf-8").splitlines()
            if "check" not in json.loads(line) and json.loads(line).get("flat_fill")]


def test_a_fill_line_carries_its_loop_points_and_its_after_face_ids(tmp_path):
    mesh, snap, out, _ = _repaired(tmp_path)
    (line,) = _fill_lines(out / "edit_log.jsonl")
    before = read_obj(next(snap.glob("*.obj")))
    assert np.allclose(line["loop_points"], before.positions[line["loop"]])
    after = read_obj(out / f"{mesh.name}.fixed.obj")
    assert len(line["after_faces"]) == 6 and all(before.n_faces <= f < after.n_faces for f in line["after_faces"])
    corners = after.positions[after.face_v[line["after_faces"]]].reshape(-1, 3)
    loop = np.asarray(line["loop_points"])
    assert (np.linalg.norm(corners[:, None] - loop[None], axis=2).min(axis=1) < 1e-6).all(), "the fill's own faces"


def _validate(tmp_path, mesh, snap, out, paths, **kw):
    val = tmp_path / f"val_{len(kw)}"
    code = cli.cmd_validate(snap, out / f"{mesh.name}.fixed.obj", paths["materials"], val, **kw)
    return code, json.loads((val / "validation.json").read_text(encoding="utf-8"))


def test_validate_with_the_edit_log_passes_check_3_by_fill_and_without_it_fails(tmp_path):
    mesh, snap, out, paths = _repaired(tmp_path)
    _code, with_log = _validate(tmp_path, mesh, snap, out, paths, edit_log=out / "edit_log.jsonl")
    gone = with_log["checks"]["nothing_deleted"]
    assert gone["status"] == "PASS" and gone["covered"] == 0 and gone["covered_by_fill"] > 0
    assert with_log["inputs"]["edit_log"] == str(out / "edit_log.jsonl")
    _code, without = _validate(tmp_path, mesh, snap, out, paths)
    assert without["checks"]["nothing_deleted"]["status"] == "FAIL"
    assert without["checks"]["nothing_deleted"]["covered"] > 0


def test_an_edit_log_whose_fill_faces_are_not_the_fill_is_refused(tmp_path, capsys):
    mesh, snap, out, paths = _repaired(tmp_path)
    log = out / "edit_log.jsonl"
    lines = [json.loads(line) for line in log.read_text(encoding="utf-8").splitlines()]
    for line in lines:
        if line.get("flat_fill"):
            line["after_faces"] = [0, 1, 2, 3, 4, 5]               # faces of the floor, not the fill
    bad = tmp_path / "bad_log.jsonl"
    bad.write_text("".join(json.dumps(line) + "\n" for line in lines), encoding="utf-8")
    code = cli.cmd_validate(snap, out / f"{mesh.name}.fixed.obj", paths["materials"], tmp_path / "val_bad",
                            edit_log=bad)
    assert code == 2 and "edit log" in capsys.readouterr().err
    assert not (tmp_path / "val_bad" / "validation.json").exists()


def test_the_validate_parser_takes_an_edit_log():
    args = cli.build_parser().parse_args(["validate", "--before", "b", "--after", "a.obj", "--out", "o",
                                          "--edit-log", "e.jsonl"])
    assert str(args.edit_log) == "e.jsonl"
    assert cli.build_parser().parse_args(["validate", "--before", "b", "--after", "a.obj", "--out", "o"]).edit_log is None


def test_a_rolled_back_fill_line_has_no_after_faces(tmp_path):
    import dataclasses

    from engine.tests.test_e8_flat_fill_kernel import _Altered, _run, _scene

    def other_look(e):
        return dataclasses.replace(e, evidence={**e.evidence, "material": 1})
    log = tmp_path / "edit_log.jsonl"
    got = _run(_Altered(other_look), _scene(), log)
    assert got.kept == []
    (line,) = _fill_lines(log)
    assert line["rolled_back"] is True and line["after_faces"] == [] and len(line["loop_points"]) == 8
