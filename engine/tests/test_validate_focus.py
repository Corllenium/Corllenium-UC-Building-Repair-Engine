"""Job P1-K3 item 1: the Validator's focus mode.

`validate(..., focus=Focus(before_faces, after_faces))` samples only the given BEFORE faces for checks 1 and 3,
lays only the given AFTER faces over them in the overlay pass, skips check 2 and gives no floor verdict: it only
answers "did these sites break anything?". The proof that it is the same judge: a focus on EVERY face gives checks 1
and 3, and the sites, exactly as the run without a focus, on two fixtures.
"""
import ast
import dataclasses
from pathlib import Path

import numpy as np
import pytest

import engine.validate
from engine.tests.fixtures.build import closed_room, grid_slab
from engine.tests.test_validate_checks import (_check, _checks, _looks, _moved, _plated, _with_flipped,
                                               _with_plate, _with_shifted_uv, _without_faces)
from engine.tests.test_validate_mutations import LOOKS, ROOM_LOOKS, SIZE, two_look_cube
from engine.validate.checks import Focus, validate


def _every_face(before, after):
    return Focus(before_faces=np.arange(before.n_faces), after_faces=np.arange(after.n_faces))


def _cube_with_three_defects():
    """The two-look cube with a deleted side face, a y = 0 side face in shifted UVs and a plate 1 in over the top (a
    UV shift under the plate would fail as `covered`, which comes first, and leave `uv` untested)."""
    m = two_look_cube()
    plate = dataclasses.replace(_moved(grid_slab(1, 1, cell=SIZE), [0.0, 0.0, SIZE + 1.0]), materials=["wall"])
    after = _with_plate(_with_shifted_uv(_without_faces(m, [8]), 4, 0.5), plate)
    return m, after, LOOKS


def _room_with_two_defects():
    """The closed room with an inner wall deleted (only the probes see it) and another inner face flipped."""
    m = closed_room()
    return m, _with_flipped(_without_faces(m, [4, 5]), [6]), ROOM_LOOKS


def _slab_overlaid():
    """A layer in another look lying ON a slab: the overlay pass's case."""
    before, after = _plated(0.0)
    return before, after, _looks("m0", "m1")


#: (fixture, the failure reasons it must show: (check, reason) pairs), so no proof passes on an empty failure set
PROOF = [(_cube_with_three_defects, [("nothing_deleted", "deleted"), ("textures", "uv"), ("nothing_deleted", "covered")]),
         (_room_with_two_defects, [("nothing_deleted", "deleted"), ("textures", "side")]),
         (_slab_overlaid, [("nothing_deleted", "overlaid"), ("textures", "overlaid")])]


def _reason(report, check, reason):
    c = report["checks"][check]
    return c["reasons"][reason] if check == "textures" else c[reason]


@pytest.mark.parametrize("build, reasons", PROOF, ids=["cube", "room", "overlaid"])
def test_a_focus_on_every_face_gives_checks_1_and_3_and_the_sites_exactly_as_no_focus(build, reasons):
    before, after, looks = build()
    full = _check(before, after, looks)
    focus = _check(before, after, looks, focus=_every_face(before, after))
    assert full.report["verdict"] == "FAIL", "the fixture must have something to find"
    for check, reason in reasons:
        assert _reason(full.report, check, reason) > 0, (check, reason, "the fixture must show this failure")
    for key in ("textures", "nothing_deleted"):
        assert focus.report["checks"][key] == full.report["checks"][key], key
    assert focus.report["sites"] == full.report["sites"] and focus.report["sites_total"] == full.report["sites_total"]
    assert focus.report["before"] == full.report["before"] and focus.report["after"] == full.report["after"]
    assert focus.report["viewpoints"] == full.report["viewpoints"]
    assert [m.tolist() for m in focus.members] == [m.tolist() for m in full.members]
    assert np.array_equal(focus.wit_col, full.wit_col) and np.array_equal(focus.wit_extra, full.wit_extra)


def test_a_focus_run_skips_check_2_gives_no_floor_verdict_and_says_whether_its_faces_broke(monkeypatch):
    import engine.detectors.errors as errors

    def refuse(*_a, **_k):
        raise AssertionError("a focus run must not run find_errors")

    monkeypatch.setattr(errors, "find_errors", refuse)
    m = two_look_cube()
    broken = validate(m, _without_faces(m, [8]), LOOKS, focus=_every_face(m, _without_faces(m, [8])))
    assert broken.report["checks"]["problems"] == {"status": "skipped (focus)"}
    assert broken.report["verdict"] is None and not broken.passed, "never a floor verdict"
    assert broken.report["focus"] == {"before_faces": 12, "after_faces": 11, "status": "FAIL"}
    same = validate(m, m, LOOKS, focus=Focus(before_faces=np.array([8, 9]), after_faces=np.zeros(0, np.int64)))
    assert same.report["focus"] == {"before_faces": 2, "after_faces": 0, "status": "PASS"}
    assert same.report["verdict"] is None


def test_a_focus_run_says_in_its_notes_that_it_is_not_a_floor_verdict():
    m = two_look_cube()
    focused = validate(m, m, LOOKS, focus=Focus(before_faces=np.array([8, 9]), after_faces=np.zeros(0, np.int64)))
    assert "FOCUS RUN on 2/12 faces: NOT A FLOOR VERDICT" in focused.report["notes"]
    plain = _check(m, m, LOOKS)
    assert not any("FOCUS" in note for note in plain.report["notes"])


def test_a_focus_samples_only_its_before_faces_and_finds_a_defect_inside_it_as_the_full_run_does():
    m = two_look_cube()
    # x = 10 face 8 gone; top face 2 in shifted UVs (P2-V2 item 8: it was the bottom, which nobody sees any more)
    after = _with_shifted_uv(_without_faces(m, [8]), 2, 0.5)
    full = _check(m, after, LOOKS)
    side = _check(m, after, LOOKS, focus=Focus(before_faces=np.array([8, 9]), after_faces=np.arange(after.n_faces)))
    textures, gone = _checks(side)
    assert textures["faces"] == 2 and textures["samples"] == 8, "only the x = 10 side is sampled"
    assert gone["deleted"] == full.report["checks"]["nothing_deleted"]["deleted"] == 4
    assert textures["reasons"]["uv"] == 0 < full.report["checks"]["textures"]["reasons"]["uv"], "the top is not in it"
    assert [s["faces"] for s in side.report["sites"]] == [[8]]
    # ids are a set: repeats and order do not change what is sampled, and a boolean mask is the same set
    again = _check(m, after, LOOKS, focus=Focus(before_faces=np.array([9, 8, 8]), after_faces=np.arange(after.n_faces)))
    mask = np.zeros(m.n_faces, dtype=bool)
    mask[[8, 9]] = True
    masked = _check(m, after, LOOKS, focus=Focus(before_faces=mask, after_faces=np.ones(after.n_faces, dtype=bool)))
    for other in (again, masked):
        assert _checks(other) == _checks(side) and other.report["sites"] == side.report["sites"]


def test_the_after_faces_of_a_focus_are_the_new_faces_the_overlay_pass_lays_over_the_samples():
    before, after = _plated(0.0)                                      # a layer in another look ON the slab: overlaid
    every = _check(before, after, _looks("m0", "m1"), focus=_every_face(before, after))
    assert _checks(every)[1]["overlaid"] == 128
    layer = np.arange(before.n_faces, after.n_faces)
    only_layer = _check(before, after, _looks("m0", "m1"),
                        focus=Focus(before_faces=np.arange(before.n_faces), after_faces=layer))
    assert _checks(only_layer) == _checks(every)
    not_layer = _check(before, after, _looks("m0", "m1"),
                       focus=Focus(before_faces=np.arange(before.n_faces), after_faces=np.arange(before.n_faces)))
    assert _checks(not_layer)[1]["overlaid"] == 0 and _checks(not_layer)[1]["status"] == "PASS"


def test_a_focus_with_face_ids_outside_the_meshes_is_refused():
    m = two_look_cube()
    with pytest.raises(ValueError):
        validate(m, m, LOOKS, focus=Focus(before_faces=np.array([12]), after_faces=np.zeros(0, np.int64)))
    with pytest.raises(ValueError):
        validate(m, m, LOOKS, focus=Focus(before_faces=np.array([0]), after_faces=np.array([-1])))


def test_the_validator_imports_nothing_from_the_repair_kernel_the_fixes_or_the_guard():
    """K3 adds `engine.repair` to what the Validator must never be built on (the existing independence test keeps its
    own list unchanged)."""
    banned = ("engine.repair", "engine.fixes", "engine.guard")
    for path in sorted(Path(engine.validate.__file__).parent.glob("*.py")):
        tree = ast.parse(path.read_text(encoding="utf-8"))
        for node in ast.walk(tree):
            if isinstance(node, ast.Import):
                names = [a.name for a in node.names]
            elif isinstance(node, ast.ImportFrom):
                names = [node.module or ""]
            else:
                continue
            for name in names:
                if name == "engine.detectors.errors":
                    continue                     # check 2's lazy import, which a focus run never reaches
                assert not any(name == b or name.startswith(b + ".") for b in banned), f"{path.name} imports {name}"
