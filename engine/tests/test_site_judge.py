"""Job P1-K3 item 2: the focus of a site, and the Validator asked about it (`engine.site_judge`).

A site's focus, in BEFORE (the stage's input): the faces its edits remove, flip or replace; every face within its
bounding box grown by the margin; and the cover candidates, the faces lying behind one of its new faces from some
standard viewpoint or eye-height probe. In AFTER: its new faces.
"""
import ast
import dataclasses
from pathlib import Path

import numpy as np

import engine.repair
from engine.site_judge import SiteJudge
from engine.tests.fixtures.build import closed_room, grid_slab
from engine.tests.test_validate_checks import _looks, _moved, _plated, _with_plate, _without_faces
from engine.tests.test_validate_mutations import LOOKS, ROOM_LOOKS, SIZE, two_look_cube
from engine.validate.checks import Settings


def _judge(before, looks, **kw):
    judge = SiteJudge(looks, **kw)
    judge.begin(before)
    return judge


def test_the_focus_holds_the_touched_faces_and_every_face_within_the_grown_box_and_nothing_further():
    slab = grid_slab(20, 20, cell=10.0)                 # 200 x 200 in, two triangles per 10 in cell
    middle = 2 * (10 * 20 + 10)                         # the first triangle of cell (10, 10): x 100..110, y 100..110
    after = _without_faces(slab, [middle])
    focus = _judge(slab, _looks("m0"), margin=24.0).focus(after, [middle], [])
    centres = slab.positions[slab.face_v[focus.before_faces]].mean(axis=1)
    assert middle in focus.before_faces.tolist() and len(focus.after_faces) == 0
    # every face whose box reaches the box of the touched face grown by 24 in: cells 7..13 in x and y
    assert centres[:, 0].min() > 100.0 - 24.0 - 10.0 and centres[:, 0].max() < 110.0 + 24.0 + 10.0
    assert len(focus.before_faces) == 2 * 7 * 7
    tight = _judge(slab, _looks("m0"), margin=0.0).focus(after, [middle], [])
    assert len(tight.before_faces) < len(focus.before_faces), "the margin is what widens it"


def test_a_plate_over_the_top_has_the_top_as_cover_candidates_and_never_the_bottom():
    m = two_look_cube()
    plate = dataclasses.replace(_moved(grid_slab(1, 1, cell=SIZE), [0.0, 0.0, SIZE + 1.0]), materials=["wall"])
    after = _with_plate(m, plate)
    judge = _judge(m, LOOKS, margin=0.0)
    found = set(judge.cover_candidates(after, [12, 13]).tolist())
    assert {2, 3} <= found, "the top lies behind the plate from every direction above"
    assert not found & {0, 1}, "the bottom is never the first face behind the plate"
    focus = judge.focus(after, [], [12, 13])
    assert {2, 3} <= set(focus.before_faces.tolist()) and focus.after_faces.tolist() == [12, 13]


def test_a_new_layer_lying_on_a_face_has_that_face_as_a_cover_candidate():
    before, after = _plated(0.0, n=2)                   # a layer in another look exactly ON the slab
    new = np.arange(before.n_faces, after.n_faces)
    found = set(_judge(before, _looks("m0", "m1"), margin=0.0).cover_candidates(after, new).tolist())
    assert found == set(range(before.n_faces))


def test_the_eye_height_probes_find_the_cover_candidates_inside_a_closed_room():
    room = closed_room()
    panel = _moved(grid_slab(10, 8, cell=10.0), [50.0, 0.0, 20.0])          # x 50..150, y 0..80 at z = 20 ...
    turned = panel.positions[:, [0, 2, 1]].copy()                             # ... stood up: x 50..150, y = 20,
    turned[:, 1] = 12.0                                                       # z 0..80, 12 in in front of the y = 0 wall
    turned[:, 2] += 20.0
    panel = dataclasses.replace(panel, positions=turned, materials=["plaster"])
    after = _with_plate(room, panel)
    new = np.arange(room.n_faces, after.n_faces)
    judge = _judge(room, ROOM_LOOKS, margin=0.0, settings=Settings(n_directions=0, n_cameras=0))
    assert len(judge.stage.viewpoints) > 0, "the room has probes"
    assert {4, 5} <= set(judge.cover_candidates(after, new).tolist()), "the wall behind the panel, seen from inside"


def test_the_check_is_the_validators_focus_run_and_names_its_failing_samples():
    m = two_look_cube()
    judge = _judge(m, LOOKS)
    after = _without_faces(m, [8])
    verdict = judge.check(after, judge.focus(after, [8], []))
    assert verdict.failed and verdict.failing == {(8, i) for i in range(4)}
    assert verdict.summary["status"] == "FAIL" and verdict.summary["nothing_deleted"]["deleted"] == 4
    assert verdict.summary["sites"][0]["faces"] == [8]
    same = judge.check(m, judge.focus(m, [8], []))
    assert not same.failed and same.summary["status"] == "PASS"
    assert judge.calls == 2


def test_the_repair_package_imports_nothing_from_the_validator():
    """K1-R2: the kernel never leans on the judge's code; it is handed a `SiteJudge` (`RepairContext.validator`)."""
    for path in sorted(Path(engine.repair.__file__).parent.rglob("*.py")):
        for node in ast.walk(ast.parse(path.read_text(encoding="utf-8"))):
            names = ([a.name for a in node.names] if isinstance(node, ast.Import)
                     else [node.module or ""] if isinstance(node, ast.ImportFrom) else [])
            for name in names:
                assert not (name == "engine.validate" or name.startswith("engine.validate.")
                            or name == "engine.site_judge"), f"{path.name} imports {name}"
