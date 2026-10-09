"""Job P2-E8c item 1: `engine.campus.needs_modelling.build_needs_modelling(report, edit_log, before_mesh)`.

The owner's rule for holes (AGENTS.md section 5): the engine closes only the narrow flat fills, and every other open
spot is listed per floor so a person can model it in SketchUp. One entry per spot: every `not_filled` row of
report.json (patch outer borders are only counted: they are not in that list, `fill_stats` counts them), and every
E8a piece the site check rolled back on its own charge (kind `slab_side` for a wall, `slab_bottom` for a bottom).
Each entry has a stable id (sha256 of the sorted, print-step-snapped border points), its geometry, and a suggested
camera 1.6 m from the spot on a side the Validator's viewpoints saw it from in BEFORE.
"""
from __future__ import annotations

import copy
import dataclasses

import numpy as np
import pytest

from engine.campus import needs_modelling as nm
from engine.tests.fixtures.build import cube
from engine.tests.fixtures.holes import holed_slab

EYE = 63.0


def _closed_slab():
    """A closed 100 x 100 x 8 in slab (top z = 0) with a 20 in square hole in its top (cells 4..5 x 4..5)."""
    return holed_slab("slab", holes={(i, j) for i in (4, 5) for j in (4, 5)})


RING = [[40, 40, 0], [50, 40, 0], [60, 40, 0], [60, 50, 0], [60, 60, 0], [50, 60, 0], [40, 60, 0], [40, 50, 0]]


def _hole_row(reason="too_wide", rule="E8b-R3", points=None):
    points = RING if points is None else points
    pts = np.asarray(points, float)
    return {"loop": 7, "rule": rule, "reason": reason, "detail": "wider than one block", "vertices": len(points),
            "centroid": [round(float(v), 3) for v in pts.mean(axis=0)], "points": [list(map(float, p)) for p in points],
            "planarity": 0.0}


def _piece_row(site=3, piece="wall", reasons=None, **kw):
    row = {"site": site, "piece": piece, "region": 5, "kinds": ["cut"], "faces": 2, "new_points": 0, "replaced": 2,
           "length": 100.0, "thickness": [8.0, 8.0], "kept": False, "reasons": reasons or {"covered": 12, "uv": 3},
           "charged": 15, "reason": "E8 solidify: a wall under an outline edge",
           "border": [[0, 0, 0], [100, 0, 0], [100, 0, -8], [0, 0, -8]], "border_rings": 1, "area_in2": 800.0,
           "normal": [0.0, -1.0, 0.0]}
    row.update(kw)
    return row


def _report(rows=(), pieces=(), outer=2):
    return {"unit": "T-L01", "snapshot": None, "not_filled": [dict(r) for r in rows],
            "pieces": [dict(p) for p in pieces],
            "fill_stats": {"outer_boundaries": outer, "holes": len(rows)}, "fills": []}


def _log(*sites, stage="E8"):
    lines = [{"stage": stage, "engine": "E8", "kind": "cut", "site": s, "reason": "E8 solidify: a wall", "faces": [1],
              "rolled_back": True} for s in sites]
    return lines + [{"check": {"stage": stage, "rolled_back": [{"site": s} for s in sites]}}]


def _build(report=None, log=None, mesh=None):
    report = _report([_hole_row()], [_piece_row()]) if report is None else report
    return nm.build_needs_modelling(report, _log(3) if log is None else log, _closed_slab() if mesh is None else mesh)


def test_one_refused_hole_and_one_rolled_back_slab_side_give_two_entries():
    doc = _build()
    assert doc["schema_version"] == 1 and doc["unit"] == "T-L01"
    kinds = {e["kind"]: e for e in doc["entries"]}
    assert set(kinds) == {"hole", "slab_side"} and len(doc["entries"]) == 2
    assert kinds["hole"]["reason"] == "too_wide" and kinds["slab_side"]["reason"] == "covered"
    assert kinds["slab_side"]["detail"] == {"covered": 12, "uv": 3}, "the dominant reason names it, all are listed"
    assert doc["counts"]["entries"] == 2 and doc["counts"]["by_kind"] == {"hole": 1, "slab_side": 1}
    assert doc["counts"]["by_reason"] == {"covered": 1, "too_wide": 1}
    for e in doc["entries"]:
        assert len(e["id"]) == 12 and int(e["id"], 16) >= 0 and e["unit"] == "T-L01"


def test_a_rolled_back_bottom_is_a_slab_bottom():
    doc = _build(_report([], [_piece_row(site=4, piece="bottom", reasons={"overlaid": 2})]), _log(4))
    (entry,) = doc["entries"]
    assert (entry["kind"], entry["reason"]) == ("slab_bottom", "overlaid")


def test_the_geometry_of_a_hole_and_of_a_slab_side():
    doc = _build()
    hole = next(e for e in doc["entries"] if e["kind"] == "hole")
    assert np.allclose(hole["centroid"], [50, 50, 0], atol=1e-3)
    assert np.allclose(np.abs(hole["normal"]), [0, 0, 1], atol=1e-6) and hole["normal"][2] > 0
    assert np.allclose(hole["bbox"], [[40, 40, 0], [60, 60, 0]])
    assert abs(hole["area_in2"] - 400.0) < 1e-6 and abs(hole["length_in"] - 80.0) < 1e-6
    assert len(hole["border"]) == 8 and hole["ordered"] is True
    side = next(e for e in doc["entries"] if e["kind"] == "slab_side")
    assert abs(side["area_in2"] - 800.0) < 1e-6 and abs(side["length_in"] - 216.0) < 1e-6
    assert np.allclose(side["bbox"], [[0, 0, -8], [100, 0, 0]])
    assert np.allclose(side["centroid"], [50, 0, -4], atol=1e-3)


def test_entries_are_sorted_by_area_then_length_descending():
    rows = [_hole_row(points=[[0, 0, 0], [10, 0, 0], [10, 10, 0], [0, 10, 0]]), _hole_row(), _hole_row(
        points=[[0, 0, 0], [30, 0, 0], [30, 30, 0], [0, 30, 0]])]
    rows[2]["loop"], rows[1]["loop"] = 9, 8
    doc = _build(_report(rows, [_piece_row()]), _log(3))
    areas = [e["area_in2"] for e in doc["entries"]]
    assert areas == [900.0, 800.0, 400.0, 100.0]
    # no area (an unordered set of open-edge points): after those with one, longest first
    loose = _hole_row(reason="not_a_simple_loop", rule="E8b-R1", points=[[0, 0, 0], [30, 0, 0], [60, 0, 0]])
    doc = _build(_report([loose, _hole_row()], []), _log())
    assert [e["reason"] for e in doc["entries"]] == ["too_wide", "not_a_simple_loop"]
    assert doc["entries"][1]["area_in2"] is None and doc["entries"][1]["ordered"] is False


def test_the_ids_are_stable_whatever_the_face_order_or_the_point_order():
    mesh = _closed_slab()
    ids = {e["kind"]: e["id"] for e in _build(mesh=mesh)["entries"]}
    order = np.random.default_rng(7).permutation(mesh.n_faces)
    shuffled = dataclasses.replace(mesh, face_v=mesh.face_v[order], face_vt=mesh.face_vt[order],
                                   face_vn=mesh.face_vn[order], face_material=mesh.face_material[order],
                                   face_line=mesh.face_line[order])
    assert {e["kind"]: e["id"] for e in _build(mesh=shuffled)["entries"]} == ids
    rows = [_hole_row(points=RING[3:] + RING[:3])]
    rows2 = [_hole_row(points=RING[::-1])]
    a = nm.build_needs_modelling(_report(rows, []), _log(), mesh)["entries"][0]["id"]
    b = nm.build_needs_modelling(_report(rows2, []), _log(), mesh)["entries"][0]["id"]
    assert a == b == ids["hole"], "the border points sorted: where the loop starts and which way it runs do not matter"
    # print-step snapping: a point 0.004 in off (coord_decimals 2) is the same point
    jitter = [[x + 0.004, y, z] for x, y, z in RING]
    assert nm.build_needs_modelling(_report([_hole_row(points=jitter)], []), _log(), mesh)["entries"][0]["id"] == a
    moved = [[x + 0.5, y, z] for x, y, z in RING]
    assert nm.build_needs_modelling(_report([_hole_row(points=moved)], []), _log(), mesh)["entries"][0]["id"] != a


def test_patch_outer_borders_are_counted_and_not_listed():
    doc = _build(_report([_hole_row()], [], outer=5), _log())
    assert doc["counts"]["outer_boundaries"] == 5 and len(doc["entries"]) == 1
    # a row that is an outer border (should it ever be in the list) is counted too, not listed
    row = _hole_row(reason="outer_boundary", rule="E8b-R1")
    doc = _build(_report([row, _hole_row()], [], outer=5), _log())
    assert len(doc["entries"]) == 1 and doc["counts"]["outer_boundaries"] == 6


def test_only_pieces_rolled_back_on_their_own_charge_are_listed():
    kept = _piece_row(site=1, kept=True, reasons={})
    whole = _piece_row(site=2, reasons={"stage_rolled_back": 0})
    own = _piece_row(site=3)
    doc = _build(_report([], [kept, whole, own]), _log(2, 3))
    (entry,) = doc["entries"]
    assert entry["site"] == 3
    assert doc["counts"]["stage_rolled_back_not_listed"] == 1


def test_a_report_and_an_edit_log_that_disagree_are_refused():
    with pytest.raises(ValueError, match="site 3"):
        _build(_report([], [_piece_row()]), _log(9))            # the log never rolled site 3 back


def test_two_spots_with_one_border_are_one_entry_that_names_both():
    wall = _piece_row(border=[list(map(float, p)) for p in RING], area_in2=400.0)
    doc = _build(_report([_hole_row()], [wall]), _log(3))
    (entry,) = doc["entries"]
    assert entry["kind"] == "hole" and entry["also"] == [{"kind": "slab_side", "reason": "covered", "site": 3}]
    assert doc["counts"]["merged"] == 1


def test_the_suggested_view_stands_1_6_m_out_where_a_viewpoint_saw_the_spot():
    doc = _build()
    hole = next(e for e in doc["entries"] if e["kind"] == "hole")
    view = hole["suggested_view"]
    eye, target = np.asarray(view["eye"]), np.asarray(view["target"])
    assert np.allclose(target, hole["centroid"], atol=1e-3)
    assert abs(np.linalg.norm(eye - target) - EYE) < 0.01 and view["distance_in"] == EYE
    assert view["source"] in ("direction", "camera", "probe")
    assert eye[2] > 0.5 * EYE, "the hole is in the TOP of a closed slab: a viewer reaches it from above"
    assert np.allclose(view["up"], [0, 0, 1]) or abs(view["up"][2]) < 1.0
    side = next(e for e in doc["entries"] if e["kind"] == "slab_side")
    assert side["suggested_view"]["eye"][1] < -0.5 * EYE, "the wall at y = 0 is reached from outside, y < 0"


def test_a_spot_no_viewpoint_sees_gets_a_view_along_its_normal():
    sealed = cube(200.0)
    row = _hole_row(points=[[100, 90, 20], [100, 110, 20], [100, 110, 40], [100, 90, 40]])
    doc = nm.build_needs_modelling(_report([row], []), _log(), sealed)
    (entry,) = doc["entries"]
    view = entry["suggested_view"]
    assert view["source"] == "normal"
    assert np.allclose(view["eye"], np.asarray(entry["centroid"]) + EYE * np.array(entry["normal"]), atol=0.01) \
        or np.allclose(view["eye"], np.asarray(entry["centroid"]) - EYE * np.array(entry["normal"]), atol=0.01)
    assert np.allclose(np.abs(entry["normal"]), [1, 0, 0], atol=1e-6)


def test_the_input_report_is_not_changed():
    report = _report([_hole_row()], [_piece_row()])
    before = copy.deepcopy(report)
    _build(report)
    assert report == before


def test_a_rolled_back_piece_with_no_border_is_counted_not_silently_dropped():
    bare = _piece_row(site=5, border=[])
    gone = {k: v for k, v in _piece_row(site=6).items() if k != "border"}
    doc = _build(_report([], [_piece_row(), bare, gone]), _log(3, 5, 6))
    assert len(doc["entries"]) == 1 and doc["counts"]["no_border_not_listed"] == 2
    assert _build()["counts"]["no_border_not_listed"] == 0


def test_a_unit_with_no_faces_gets_a_view_along_the_normal_and_the_viewer_is_whole():
    empty = dataclasses.replace(_closed_slab(), face_v=np.zeros((0, 3), np.int64), face_vt=np.zeros((0, 3), np.int64),
                                face_vn=np.zeros((0, 3), np.int64), face_material=np.zeros(0, np.int64),
                                face_line=np.zeros(0, np.int64))
    viewer = nm._Viewer(empty)
    assert (viewer.n_dirs, viewer.n_cams) == (0, 0), "set on the early return too"
    assert nm._Viewer(None).n_dirs == 0
    doc = nm.build_needs_modelling(_report([_hole_row()], []), _log(), empty)
    assert doc["entries"][0]["suggested_view"]["source"] == "normal"


def test_fill_review_has_one_spot_drawer_and_no_unused_wrapper():
    from engine import fill_review
    assert hasattr(fill_review, "SpotCropper") and not hasattr(fill_review, "write_spot_crop")
