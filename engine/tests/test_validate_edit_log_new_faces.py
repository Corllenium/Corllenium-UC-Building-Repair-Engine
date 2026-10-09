"""Job P2-E8c item 4c (from the P2-E8b re-review): `fills_from_edit_log` refuses a fill whose faces are not new.

A flat fill's `after_faces` are faces the repair ADDED to the shipped AFTER. The AFTER lists the BEFORE's surviving
faces first and the added ones after them, so an id below the number of surviving BEFORE faces names an existing
BEFORE face, which no fill can be. The survivors are the BEFORE's `before_faces` less the faces the kept cuts and
removes of the log took away (a kept E8a cut makes the first new id lower than the BEFORE's face count). A log that
names such a face is refused (`ValueError`; `validate --edit-log` exits 2), even when the face's corners lie on the
fill's loop points.
"""
from __future__ import annotations

import json

import numpy as np
import pytest

from engine import cli
from engine.tests.fixtures.holes import floor_over_room
from engine.tests.test_validate_edit_log_fills import _repaired


def _log(tmp_path, after, face, extra=()):
    """An edit log with one kept flat fill claiming AFTER face `face`, its loop the face's own corners."""
    corners = after.positions[after.face_v[face]]
    fill = {"stage": "E8b", "engine": "E8", "kind": "add", "site": 0, "faces": [], "flat_fill": True, "loop": [0, 1, 2],
            "loop_points": corners.tolist(), "after_faces": [int(face)]}
    path = tmp_path / "edit_log.jsonl"
    path.write_text("".join(json.dumps(line) + "\n" for line in [*extra, fill]), encoding="utf-8")
    return path


def test_a_fill_that_names_a_before_face_is_refused(tmp_path):
    after = floor_over_room()
    n_before = after.n_faces - 6
    with pytest.raises(ValueError, match="BEFORE face"):
        cli.fills_from_edit_log(_log(tmp_path, after, n_before - 1), after, before_faces=n_before)


def test_a_fill_with_a_new_face_is_accepted(tmp_path):
    after = floor_over_room()
    n_before = after.n_faces - 6
    (fill,) = cli.fills_from_edit_log(_log(tmp_path, after, n_before), after, before_faces=n_before)
    assert fill.faces.tolist() == [n_before]


def test_without_the_before_face_count_nothing_is_added_to_the_old_rule(tmp_path):
    after = floor_over_room()
    assert len(cli.fills_from_edit_log(_log(tmp_path, after, 0), after)) == 1


def test_a_kept_cut_lowers_the_first_new_id_by_the_faces_it_removed(tmp_path):
    """A kept E8a cut of 2 faces: the survivors are `before_faces - 2`, so the first new id is 2 below the BEFORE's count."""
    after = floor_over_room()
    n_before = after.n_faces - 6
    cut = {"stage": "E8", "engine": "E8", "kind": "cut", "site": 1, "faces": [4, 5], "n_removed": 2, "n_added": 2}
    rolled = {**cut, "site": 2, "faces": [6, 7, 8], "rolled_back": True}
    ok = _log(tmp_path, after, n_before - 2, extra=[cut, rolled])
    assert len(cli.fills_from_edit_log(ok, after, before_faces=n_before)) == 1
    with pytest.raises(ValueError, match="BEFORE face"):
        cli.fills_from_edit_log(_log(tmp_path, after, n_before - 3, extra=[cut, rolled]), after, before_faces=n_before)
    # a rolled-back cut took nothing away: without the kept cut the same id is a BEFORE face
    with pytest.raises(ValueError, match="BEFORE face"):
        cli.fills_from_edit_log(_log(tmp_path, after, n_before - 2, extra=[rolled]), after, before_faces=n_before)


def test_validate_with_such_a_log_exits_2(tmp_path, capsys):
    mesh, snap, out, paths = _repaired(tmp_path)
    after_path = out / f"{mesh.name}.fixed.obj"
    from engine.io.obj_reader import read_obj
    after = read_obj(after_path)
    bad = _log(tmp_path, after, 0)                                       # face 0 is the floor's, a BEFORE face
    code = cli.cmd_validate(snap, after_path, paths["materials"], tmp_path / "val_bad", edit_log=bad)
    assert code == 2
    err = capsys.readouterr().err
    assert "edit log" in err and "BEFORE face" in err
    assert not (tmp_path / "val_bad" / "validation.json").exists()
