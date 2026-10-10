"""Job P2-E8b item 2: the Validator's one named class for flat fills, `fill_site` (ruling E8b-R6).

A flat fill closes a hole people could see through, so what lay behind it would be "covered": that is the fill's
purpose, the owner's exception made measurable. A BEFORE sample counts as `covered_by_fill`, not `covered`, only when
every line of sight that saw it in BEFORE and is blocked in AFTER ends on a face the edit log marks as an E8 flat fill
(`FillSite`), inside that fill's own loop; and only for an honest fill: its loop is a loop of open edges of BEFORE whose
faces have one look, and the fill has that look. Everything else is unchanged, and three mutations must still FAIL.
"""
from __future__ import annotations

import numpy as np
import pytest

from engine.tests.fixtures.holes import holed_slab
from engine.tests.test_validate_checks import NO_ERRORS, _looks
from engine.validate.checks import FillSite, validate

#: Hole A is cell (2, 2) (x 40..50, y 40..50); a 1 in strip of slab (x 50..51) parts it from hole B (x 51..60).
XS = [0.0, 20.0, 40.0, 50.0, 51.0, 60.0, 80.0, 100.0]
YS = [0.0, 20.0, 40.0, 50.0, 60.0, 80.0, 100.0]


def _scene():
    """An open floor (m0) with holes A and B over a room floor 100 in below (m1), seen through both holes."""
    return holed_slab("floor_over_room", XS, YS, holes={(2, 2), (4, 2)}, closed=False, materials=("m0", "m1"),
                      below=(100.0, 1))


def _vid(i, j):
    return j * len(XS) + i          # the slab's top lattice comes first in `holed_slab`


LOOP_A = [_vid(2, 2), _vid(3, 2), _vid(3, 3), _vid(2, 3)]


def _with_fill(mesh, corners, material=0):
    """`mesh` plus two triangles over the quad `corners` (top lattice ids, counter-clockwise from above), in
    `material`, with the slab's UV continued: (x, y) * 0.05. Returns `(after, the new face ids)`."""
    import dataclasses
    c = list(corners)
    tris = np.array([[c[0], c[1], c[2]], [c[0], c[2], c[3]]], np.int64)
    uv = mesh.positions[tris][..., :2] * 0.05
    base = len(mesh.uvs)
    after = dataclasses.replace(
        mesh, uvs=np.vstack([mesh.uvs, uv.reshape(-1, 2)]), face_v=np.vstack([mesh.face_v, tris]),
        face_vt=np.vstack([mesh.face_vt, base + np.arange(6).reshape(2, 3)]),
        face_vn=np.vstack([mesh.face_vn, np.full((2, 3), -1)]),
        face_material=np.concatenate([mesh.face_material, [material, material]]),
        face_line=np.arange(1, mesh.n_faces + 3))
    return after, np.arange(mesh.n_faces, mesh.n_faces + 2)


def _run(before, after, fills=None):
    v = validate(before, after, _looks("m0", "m1"), errors=(NO_ERRORS, NO_ERRORS), fills=fills)
    c = v.report["checks"]
    return v, c["textures"], c["nothing_deleted"]


def _mark(before, faces, loop=LOOP_A):
    return [FillSite(faces=faces, loop=before.positions[loop])]


def test_a_hole_shows_the_room_below_and_an_unmarked_cover_of_it_is_covered():
    before = _scene()
    after, _ = _with_fill(before, LOOP_A)
    _v, textures, gone = _run(before, after)
    assert gone["status"] == "FAIL" and gone["covered"] > 0, "the room below is seen through hole A, then covered"
    assert "covered_by_fill" not in gone and "covered_by_fill" not in textures, "no fills: no fill keys (fix round 1)"


def test_a_marked_flat_fill_covers_the_room_only_as_covered_by_fill_and_check_3_passes():
    before = _scene()
    after, faces = _with_fill(before, LOOP_A)
    v, textures, gone = _run(before, after, _mark(before, faces))
    assert gone["status"] == "PASS" and gone["covered"] == 0 and gone["covered_by_fill"] > 0
    assert textures["status"] == "PASS" and textures["covered_by_fill"] > 0
    assert v.report["verdict"] == "PASS"
    (site,) = v.report["fill_sites"]
    assert site["honest"] is True and site["samples"] == gone["covered_by_fill"] and site["why"] is None
    assert site["before_faces"], "the room's faces it covers are listed"


def test_without_fills_the_report_has_no_fill_keys():
    """Fix round 1: with no fills `validation.json` is exactly what it was before the class existed."""
    before = _scene()
    for fills in (None, []):
        v, textures, gone = _run(before, before, fills)
        assert "fill_sites" not in v.report and "covered_by_fill" not in gone and "covered_by_fill" not in textures


def test_without_fills_validation_json_is_byte_for_byte_the_76ca35a_validator_s():
    """Fix round 1: the 76ca35a Validator (before the fill_site class), loaded from git, and this one give the same
    validation.json bytes on an existing case (a cube with one visible face deleted), timings aside."""
    import importlib.util
    import json
    import subprocess
    import sys
    from pathlib import Path

    from engine.tests.fixtures.build import cube
    from engine.tests.test_validate_checks import _without_faces

    root = Path(__file__).resolve().parents[2]
    shown = subprocess.run(["git", "-C", str(root), "show", "76ca35a:engine/validate/checks.py"],
                           capture_output=True, text=True, encoding="utf-8")
    if shown.returncode != 0:
        pytest.skip(f"git cannot show the 76ca35a Validator here: {shown.stderr.strip()}")
    old_path = Path(__file__).with_name("_old_checks_76ca35a.py")
    spec = importlib.util.spec_from_loader("old_checks_76ca35a", loader=None)
    old = importlib.util.module_from_spec(spec)
    sys.modules["old_checks_76ca35a"] = old
    exec(compile(shown.stdout, str(old_path), "exec"), old.__dict__)
    m = cube(10.0)
    after = _without_faces(m, [8])
    def dump(r):
        # job P2-V2 added the owner's floor to check 3 (`checks.nothing_deleted.floor`); everything else is as it was
        r = json.loads(json.dumps({k: v for k, v in r.items() if k != "timings_s"}))
        r["checks"]["nothing_deleted"].pop("floor", None)
        return json.dumps(r, indent=2).encode("utf-8")
    # job P2-V2 item 8: the default viewpoints are now the directions at or above the horizon; both get the whole
    # sphere here, so what is compared is the code, not the viewpoint set
    from engine.validate.viewpoints import outside_directions
    sphere = dict(dirs=outside_directions(128), extra_dirs=outside_directions(1024))
    then = old.validate(m, after, _looks("m0"), errors=(NO_ERRORS, NO_ERRORS), **sphere).report
    now = validate(m, after, _looks("m0"), errors=(NO_ERRORS, NO_ERRORS), **sphere).report
    assert then["checks"]["nothing_deleted"]["status"] == "FAIL", "a case with failures, sites and counts"
    assert dump(now) == dump(then)


# ------------------------------------------------------------------------------- mutations that must still FAIL


def test_mutation_a_fill_one_cell_larger_than_its_loop_fails_check_3():
    """The fill reaches over the strip into hole B: the room seen through B is covered OUTSIDE loop A."""
    before = _scene()
    after, faces = _with_fill(before, [_vid(2, 2), _vid(5, 2), _vid(5, 3), _vid(2, 3)])
    _v, _t, gone = _run(before, after, _mark(before, faces))
    assert gone["status"] == "FAIL" and gone["covered"] > 0


def test_mutation_a_fill_the_edit_log_does_not_mark_fails_check_3():
    before = _scene()
    after, _faces = _with_fill(before, LOOP_A)
    _v, _t, gone = _run(before, after, fills=[])
    assert gone["status"] == "FAIL" and gone["covered"] > 0 and "covered_by_fill" not in gone


def test_mutation_a_fill_in_another_look_than_its_neighbours_fails_check_3():
    before = _scene()
    after, faces = _with_fill(before, LOOP_A, material=1)
    v, _t, gone = _run(before, after, _mark(before, faces))
    assert gone["status"] == "FAIL" and gone["covered"] > 0 and gone["covered_by_fill"] == 0
    (site,) = v.report["fill_sites"]
    assert site["honest"] is False and "look" in site["why"]


def test_a_marked_loop_that_is_not_a_hole_of_before_is_not_honest():
    """The Validator checks the mark itself: a loop declared round hole A AND the strip is no loop of open edges."""
    before = _scene()
    after, faces = _with_fill(before, [_vid(2, 2), _vid(4, 2), _vid(4, 3), _vid(2, 3)])
    v, _t, gone = _run(before, after, _mark(before, faces, [_vid(2, 2), _vid(4, 2), _vid(4, 3), _vid(2, 3)]))
    assert gone["status"] == "FAIL"
    (site,) = v.report["fill_sites"]
    assert site["honest"] is False and "open" in site["why"]


def test_fill_site_rejects_a_bad_mark():
    before = _scene()
    with pytest.raises(ValueError):
        validate(before, before, _looks("m0", "m1"), errors=(NO_ERRORS, NO_ERRORS),
                 fills=[FillSite(faces=np.array([before.n_faces + 5]), loop=before.positions[LOOP_A])])


# ------------------------------------------------------------- fix round 1: the honesty check re-measures R2 and R3


def _open_box(size=30.0):
    """A closed-topped box with no bottom: four walls and a lid (m0), floating, wound to face INTO the box (a room
    seen through its open floor), its open bottom a 4-point loop of open edges whose neighbours are the walls, at 90
    degrees to the loop's plane. The faces' fronts are seen only from below, through the opening."""
    from engine.tests.fixtures.build import _mesh
    s = size
    P = [[0, 0, 0], [s, 0, 0], [s, s, 0], [0, s, 0], [0, 0, s], [s, 0, s], [s, s, s], [0, s, s]]
    quads = [q[::-1] for q in [(0, 1, 5, 4), (1, 2, 6, 5), (2, 3, 7, 6), (3, 0, 4, 7), (4, 5, 6, 7)]]
    uvs, fv, fvt = [], [], []
    for q in quads:
        base = len(uvs)
        uvs += [[0, 0], [1, 0], [1, 1], [0, 1]]
        fv += [[q[0], q[1], q[2]], [q[0], q[2], q[3]]]
        fvt += [[base, base + 1, base + 2], [base, base + 2, base + 3]]
    return _mesh("open_box", P, uvs, fv, fvt, materials=("m0", "m1"))


def test_a_fill_over_a_box_s_open_bottom_is_dishonest_but_covers_nothing_seen_from_at_or_above_the_horizon():
    # job P2-V2 item 8 (was: ..._fails_check_3). The box's inside shows only through its open bottom, so only a viewer
    # below the ground saw it; outside views come only from at or above the horizon now (owner, 2026-10-10), so the
    # fill covers nothing visible and check 3 passes. The mark is still refused: not the owner's flat fill.
    before = _open_box()
    after, faces = _with_fill(before, [0, 3, 2, 1])           # wound to face down, out of the box
    v, _t, gone = _run(before, after, [FillSite(faces=faces, loop=before.positions[[0, 3, 2, 1]])])
    assert gone["status"] == "PASS" and gone["covered"] == 0 and gone["covered_by_fill"] == 0
    (site,) = v.report["fill_sites"]
    assert site["honest"] is False and "coplanar" in site["why"]


def test_mutation_a_fill_over_a_hole_1_5_m_wide_fails_check_3():
    xs = [0.0, 20.0, 80.0, 100.0]                              # a 60 in (1.52 m) square hole over the room
    before = holed_slab("wide_over_room", xs, xs, holes={(1, 1)}, closed=False, materials=("m0", "m1"),
                        below=(100.0, 1))
    loop = [1 * 4 + 1, 1 * 4 + 2, 2 * 4 + 2, 2 * 4 + 1]
    after, faces = _with_fill(before, loop)
    v, _t, gone = _run(before, after, [FillSite(faces=faces, loop=before.positions[loop])])
    assert gone["status"] == "FAIL" and gone["covered"] > 0 and gone["covered_by_fill"] == 0
    (site,) = v.report["fill_sites"]
    assert site["honest"] is False and "inscribed" in site["why"]
