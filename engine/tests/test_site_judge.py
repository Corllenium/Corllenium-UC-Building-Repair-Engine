"""Job P1-K3 item 2: the focus of a site, and the Validator asked about it (`engine.site_judge`).

A site's focus, in BEFORE (the stage's input): the faces its edits remove, flip or replace; every face within its
bounding box grown by the margin; and the cover candidates, the faces lying behind one of its new faces from some
standard viewpoint or eye-height probe. In AFTER: its new faces.
"""
import ast
import dataclasses
from pathlib import Path

import numpy as np
import pytest

import engine.repair
from engine.site_judge import SiteJudge
from engine.tests.fixtures.build import closed_room, grid_slab
from engine.tests.test_validate_checks import (NO_ERRORS, _looks, _moved, _plated, _two_looks, _with_material,
                                               _with_plate, _without_faces)
from engine.tests.test_validate_mutations import LOOKS, ROOM_LOOKS, SIZE, two_look_cube
from engine.validate.checks import Settings, validate


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


def test_a_plate_over_the_top_has_the_top_as_cover_candidates_and_the_box_shadow_over_approximates():
    m = two_look_cube()
    plate = dataclasses.replace(_moved(grid_slab(1, 1, cell=SIZE), [0.0, 0.0, SIZE + 1.0]), materials=["wall"])
    after = _with_plate(m, plate)
    judge = _judge(m, LOOKS, margin=0.0)
    found = set(judge.cover_candidates(after, [12, 13]).tolist())
    assert {2, 3} <= found, "the top lies behind the plate from every direction above"
    # boxes know nothing of what hides what: the bottom, which the top hides from the plate, is in the shadow too
    # (fix round 1: candidates are a superset by construction, never a lattice of rays that can miss a small face)
    assert {0, 1} <= found
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


# ---------------------------------------------------------------------------------------------------------------
# Fix round 1 (review CRITICAL): the cover candidates must be conservative BY CONSTRUCTION. Rays through the new
# faces' sample lattice (6-7.5 in apart) missed a BEFORE face smaller than that gap, beyond the margin.
# ---------------------------------------------------------------------------------------------------------------

def _tiny_under_plate(small, height, plate=60.0, at=30.0):
    """A visible `small` in square at (at, at, 0) in look m0, and a `plate` in square plate `height` in above it in
    look m1: the plate covers the small face from every direction above."""
    face = _two_looks(_moved(grid_slab(1, 1, cell=small), [at, at, 0.0]))
    cover = _moved(grid_slab(1, 1, cell=plate), [0.0, 0.0, height])
    cover = _with_material(_two_looks(cover), np.arange(cover.n_faces), 1)
    return face, _with_plate(face, cover), _looks("m0", "m1")


def _scattered_specks():
    """0.4 in specks every 7 in over a 70 in field (none on the lattice of a plate's samples, by construction of
    the spacing), and a 70 in plate 25 in above, offset by 3 in."""
    specks = [_moved(grid_slab(1, 1, cell=0.4), [3.3 + 7.0 * i, 2.9 + 7.0 * j, 0.0]) for i in range(10) for j in range(10)]
    before = specks[0]
    for s in specks[1:]:
        before = _with_plate(before, s)
    before = _two_looks(before)
    cover = _moved(grid_slab(1, 1, cell=70.0), [3.0, 3.0, 25.0])
    cover = _with_material(_two_looks(cover), np.arange(cover.n_faces), 1)
    return before, _with_plate(before, cover), _looks("m0", "m1")


def _cube_plate_and_removal():
    m = two_look_cube()
    plate = dataclasses.replace(_moved(grid_slab(1, 1, cell=SIZE), [0.0, 0.0, SIZE + 1.0]), materials=["wall"])
    return m, _with_plate(_without_faces(m, [8]), plate), LOOKS


def _room_panel():
    room = closed_room()
    panel = _moved(grid_slab(10, 8, cell=10.0), [50.0, 0.0, 20.0])
    turned = panel.positions[:, [0, 2, 1]].copy()
    turned[:, 1] = 12.0
    turned[:, 2] += 20.0
    return room, _with_plate(room, dataclasses.replace(panel, positions=turned, materials=["plaster"])), ROOM_LOOKS


def _overlaid():
    before, after = _plated(0.0)
    return before, after, _looks("m0", "m1")


#: (name, builder, the BEFORE faces the site's edits touch). AFTER is BEFORE plus this one site's edits, with the
#: site's new faces appended after BEFORE's surviving faces.
SITES = [("tiny 0.5 in, 40 in under", lambda: _tiny_under_plate(0.5, 40.0), []),
         ("tiny 2 in, 40 in under", lambda: _tiny_under_plate(2.0, 40.0), []),
         ("tiny 0.5 in, 30 in under", lambda: _tiny_under_plate(0.5, 30.0), []),
         ("scattered specks", _scattered_specks, []),
         ("cube plate and removal", _cube_plate_and_removal, [8]),
         ("room panel, probes", _room_panel, []),
         ("overlaid layer", _overlaid, [])]


def _failing(v):
    """`(BEFORE face, sample index within the face)` of every failing sample of a Validation (all sites)."""
    first, out = {}, set()
    for i, f in enumerate(v.samples.face.tolist()):
        first.setdefault(f, i)
    for members in v.members:
        for i in members.tolist():
            f = int(v.samples.face[i])
            out.add((f, i - first[f]))
    return out


def _site(before, after, touched):
    n_kept = before.n_faces - len(touched)
    return np.asarray(touched, dtype=np.int64), np.arange(n_kept, after.n_faces)


def test_a_visible_face_smaller_than_the_sample_gap_under_a_new_plate_fails_the_focus_run_like_the_full_run():
    before, after, looks = _tiny_under_plate(0.5, 40.0)
    full = validate(before, after, looks, errors=(NO_ERRORS, NO_ERRORS))
    assert full.report["checks"]["nothing_deleted"]["covered"] > 0 and full.report["verdict"] == "FAIL"
    judge = _judge(before, looks)
    touched, new = _site(before, after, [])
    focus = judge.focus(after, touched, new)
    assert {0, 1} <= set(focus.before_faces.tolist()), "the small face is a cover candidate"
    verdict = judge.check(after, focus)
    assert verdict.failed and verdict.summary["nothing_deleted"]["covered"] > 0


@pytest.mark.parametrize("name, build, touched", SITES, ids=[s[0] for s in SITES])
def test_every_failing_sample_of_the_full_run_is_a_failing_sample_of_the_sites_focus_run(name, build, touched):
    before, after, looks = build()
    full = validate(before, after, looks, errors=(NO_ERRORS, NO_ERRORS), settings=Settings(max_sites=1 << 30))
    expected = _failing(full)
    assert expected, f"{name}: the fixture must fail somewhere"
    judge = _judge(before, looks)
    t, new = _site(before, after, touched)
    verdict = judge.check(after, judge.focus(after, t, new))
    assert expected <= verdict.failing, f"{name}: {len(expected - verdict.failing)} failing samples missed"


def test_the_repair_package_imports_nothing_from_the_validator():
    """K1-R2: the kernel never leans on the judge's code; it is handed a `SiteJudge` (`RepairContext.validator`)."""
    for path in sorted(Path(engine.repair.__file__).parent.rglob("*.py")):
        for node in ast.walk(ast.parse(path.read_text(encoding="utf-8"))):
            names = ([a.name for a in node.names] if isinstance(node, ast.Import)
                     else [node.module or ""] if isinstance(node, ast.ImportFrom) else [])
            for name in names:
                assert not (name == "engine.validate" or name.startswith("engine.validate.")
                            or name == "engine.site_judge"), f"{path.name} imports {name}"
