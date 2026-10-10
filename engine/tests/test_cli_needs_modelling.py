"""Job P2-E8c item 2: `repair-unit` writes `<out>/needs_modelling.json` and a BEFORE crop per entry.

The file is `engine.campus.needs_modelling.build_needs_modelling` on the run's report, edit log and BEFORE:
schema version 1, the unit, the counts by kind and reason, and the entries, each with `crop`, a BEFORE image from its
`suggested_view` under `<out>/needs_modelling/<id>.png`. Item 4a: a unit whose BEFORE differs from the campus map
(exit 1) removes the outputs an earlier run left in `--out`.
"""
from __future__ import annotations

import json

import numpy as np
import pytest
from PIL import Image

from engine import cli
from engine.campus.needs_modelling import validate_document
from engine.fill_review import OUTLINE
from engine.tests.fixtures.build import compartment_with_deep_wall, slab_with_three_skirts
from engine.tests.fixtures.holes import floor_over_room
from engine.tests.test_cli_repair_unit import _FAST, _campus


def _run(tmp_path, mesh, engines=("E8",), out=None):
    paths, snap = _campus(tmp_path, mesh)
    out = tmp_path / "out" if out is None else out
    code = cli.cmd_repair_unit(out, unit="T-L01", engines=list(engines), campus_map=paths["map"],
                               source=paths["source"], materials=paths["materials"], profile=_FAST)
    return code, out, paths


def _doc(out):
    return json.loads((out / "needs_modelling.json").read_text(encoding="utf-8"))


def test_the_file_is_written_valid_and_lists_the_refused_hole(tmp_path):
    code, out, _ = _run(tmp_path, floor_over_room())
    assert code == 0
    doc = _doc(out)
    validate_document(doc)                                      # the schema
    assert doc["schema_version"] == 1 and doc["unit"] == "T-L01"
    (entry,) = doc["entries"]
    assert (entry["kind"], entry["reason"]) == ("hole", "too_wide") and len(entry["border"]) == 24
    assert doc["counts"] == {"entries": 1, "by_kind": {"hole": 1}, "by_reason": {"too_wide": 1}, "outer_boundaries": 2,
                             "stage_rolled_back_not_listed": 0, "no_border_not_listed": 0, "merged": 0}
    assert abs(entry["area_in2"] - 3600.0) < 1e-3, "the 60 in square hole"
    report = json.loads((out / "report.json").read_text(encoding="utf-8"))
    assert report["needs_modelling"]["entries"] == 1 and report["needs_modelling"]["file"] == "needs_modelling.json"


def test_every_entry_has_a_crop_that_exists_and_shows_its_border(tmp_path):
    _code, out, _ = _run(tmp_path, floor_over_room())
    (entry,) = _doc(out)["entries"]
    assert entry["crop"] == f"needs_modelling/{entry['id']}.png"
    image = np.asarray(Image.open(out / entry["crop"]).convert("RGB"))
    assert image.shape == (256, 256, 3)
    outline = (image == np.array(OUTLINE)).all(axis=2)
    assert outline.sum() > 100, "the hole's border is outlined"
    floor = (image == np.array([203, 203, 203])).all(axis=2)       # the floor, in the look's flat colour
    sky = (image == np.array([236, 238, 241])).all(axis=2)         # a ray that meets nothing
    assert floor.sum() > 5000 and sky.sum() > 1000, "BEFORE is drawn, not blank"


def test_a_rolled_back_slab_side_is_listed_with_its_reason_and_an_outline(tmp_path):
    code, out, _ = _run(tmp_path, compartment_with_deep_wall(), engines=("E8a",))
    assert code == 0
    doc = _doc(out)
    validate_document(doc)
    (entry,) = doc["entries"]
    assert entry["kind"] == "slab_side" and entry["reason"] == "covered"
    assert entry["site"] == 0 and entry["area_in2"] > 0 and entry["ordered"] is True
    assert (out / entry["crop"]).is_file()
    report = json.loads((out / "report.json").read_text(encoding="utf-8"))
    (piece,) = report["pieces"]
    assert piece["border"] and piece["area_in2"] > 0, "a rolled-back piece carries its border"


def test_a_refused_hole_and_the_slab_side_closing_it_are_one_spot(tmp_path):
    """The compartment's open mouth is E8b's refused hole AND the outline of the wall E8a built and the check
    rolled back: one border, one spot, one entry that names both."""
    _code, out, _ = _run(tmp_path, compartment_with_deep_wall())
    doc = _doc(out)
    (entry,) = doc["entries"]
    assert (entry["kind"], entry["reason"]) == ("hole", "neighbour_not_coplanar")
    assert [(a["kind"], a["reason"]) for a in entry["also"]] == [("slab_side", "covered")] and doc["counts"]["merged"] == 1


def test_a_piece_rolled_back_on_its_own_charge_is_listed(tmp_path):
    # job P2-V2 (was: a kept piece is not listed). Covered is asked on every line, from both sides, so the three-skirt
    # slab's wall and bottom, kept until then, now hide its inside from the viewers below and beside it: both are
    # rolled back on their own charge and listed, `covered`, beside E8b's refused hole
    code, out, _ = _run(tmp_path, slab_with_three_skirts())
    assert code == 0
    doc = _doc(out)
    validate_document(doc)
    assert sorted((e["kind"], e["reason"]) for e in doc["entries"]) == [
        ("hole", "not_planar"), ("slab_bottom", "covered"), ("slab_side", "covered")]
    assert doc["counts"]["entries"] == 3


def test_an_old_crop_does_not_survive_a_new_run(tmp_path):
    out = tmp_path / "out"
    (out / "needs_modelling").mkdir(parents=True)
    (out / "needs_modelling" / "old.png").write_bytes(b"x")
    (out / "needs_modelling.json").write_text("{}", encoding="utf-8")
    _code, out, _ = _run(tmp_path, floor_over_room(), out=out)
    assert not (out / "needs_modelling" / "old.png").exists()
    assert _doc(out)["entries"]


def test_the_document_checker_refuses_a_malformed_file(tmp_path):
    _code, out, _ = _run(tmp_path, floor_over_room())
    doc = _doc(out)
    bad = json.loads(json.dumps(doc))
    bad["schema_version"] = 2
    with pytest.raises(ValueError, match="schema_version"):
        validate_document(bad)
    bad = json.loads(json.dumps(doc))
    del bad["entries"][0]["suggested_view"]
    with pytest.raises(ValueError, match="suggested_view"):
        validate_document(bad)
    bad = json.loads(json.dumps(doc))
    bad["entries"][0]["kind"] = "ceiling"
    with pytest.raises(ValueError, match="kind"):
        validate_document(bad)
    bad = json.loads(json.dumps(doc))
    bad["counts"]["entries"] = 7
    with pytest.raises(ValueError, match="counts"):
        validate_document(bad)


# -------------------------------------------------------------------------- item 4a: the exit-1 path cleans up

def test_a_unit_whose_before_differs_from_the_map_removes_the_outputs_an_earlier_run_left(tmp_path, capsys):
    mesh = slab_with_three_skirts()
    paths, _snap = _campus(tmp_path, mesh)
    out = tmp_path / "out"
    (out / "needs_modelling").mkdir(parents=True)
    stale = [out / "report.json", out / "T-L01.fixed.obj", out / "needs_modelling.json", out / "edit_log.jsonl",
             out / "needs_modelling" / "abc.png"]
    for path in stale:
        path.write_text("stale", encoding="utf-8")
    keep = out / "notes.txt"
    keep.write_text("mine", encoding="utf-8")
    cmap = json.loads(paths["map"].read_text(encoding="utf-8"))
    cmap["units"][0]["members"][0]["tris"] = mesh.n_faces + 1
    paths["map"].write_text(json.dumps(cmap), encoding="utf-8")
    code = cli.main(["repair-unit", "--unit", "T-L01", "--engines", "E8", "--out", str(out), "--map", str(paths["map"]),
                     "--source", str(paths["source"]), "--materials", str(paths["materials"])])
    assert code == 1 and "DIFFERS from the campus map" in capsys.readouterr().err
    assert [p for p in stale if p.exists()] == [], "nothing of the earlier run is left to be mistaken for this one"
    assert keep.read_text(encoding="utf-8") == "mine", "a file the tool never writes stays"


def test_a_large_spot_is_not_cropped_by_the_fill_review_window(tmp_path):
    """A slab bottom can be 40 ft across: the spot crop's window grows to 1200 in (the fill review's stops at 400),
    so a 600 in border is a 128 px square in the 256 px picture, with the border all in view."""
    from engine.fill_review import SPOT_MAX_WINDOW, SpotCropper
    from engine.tests.fixtures.holes import holed_slab
    from engine.validate.checks import Looks
    mesh = holed_slab("big", nx=10, ny=10, cell=100.0)
    border = [[200, 200, 0], [800, 200, 0], [800, 800, 0], [200, 800, 0]]
    view = {"eye": [500, 500, 63], "target": [500, 500, 0]}
    path = SpotCropper(mesh, Looks({})).write(border, True, view, tmp_path / "big.png")
    image = np.asarray(Image.open(path).convert("RGB"))
    mask = (image == np.array(OUTLINE)).all(axis=2)
    mask[:8, :] = False                       # the crop's own tick marks (same yellow) on the top and left edge
    mask[:, :8] = False
    ys, xs = np.nonzero(mask)
    assert SPOT_MAX_WINDOW == 1200.0
    assert 120 <= xs.max() - xs.min() <= 136 and 120 <= ys.max() - ys.min() <= 136
    assert xs.min() > 20 and xs.max() < 236 and ys.min() > 20 and ys.max() < 236


def test_pieces_dropped_with_their_whole_stage_are_counted_not_listed(tmp_path, monkeypatch):
    """Exit 3: the stage was rolled back whole. Its pieces failed no check of their own, so they are not listed (the
    brief: rolled back on its OWN charge), only counted; the file is still written."""
    import engine.site_judge
    from engine.tests.test_cli_repair_unit import _FarNoiseJudge
    monkeypatch.setattr(engine.site_judge, "SiteJudge", _FarNoiseJudge)
    code, out, _ = _run(tmp_path, slab_with_three_skirts())
    assert code == 3
    doc = _doc(out)
    validate_document(doc)
    report = json.loads((out / "report.json").read_text(encoding="utf-8"))
    assert doc["counts"]["stage_rolled_back_not_listed"] == report["sites"]["built"] > 0
    assert {e["kind"] for e in doc["entries"]} <= {"hole"}, "no slab piece is listed; E8b's refused holes still are"


# ------------------------------------------------------------------------------- fix round, item 5

def test_exit_1_deletes_only_the_crops_in_its_folders_and_a_foreign_file_survives(tmp_path, capsys):
    mesh = slab_with_three_skirts()
    paths, _snap = _campus(tmp_path, mesh)
    out = tmp_path / "out"
    for folder in ("needs_modelling", "fills", "empty_after"):
        (out / folder).mkdir(parents=True)
    (out / "needs_modelling" / "abc.png").write_bytes(b"x")
    (out / "needs_modelling" / "my-notes.txt").write_text("keep", encoding="utf-8")
    (out / "fills" / "fill-0001.png").write_bytes(b"x")                 # only crops: its folder is then empty
    cmap = json.loads(paths["map"].read_text(encoding="utf-8"))
    cmap["units"][0]["members"][0]["tris"] = mesh.n_faces + 1
    paths["map"].write_text(json.dumps(cmap), encoding="utf-8")
    code = cli.main(["repair-unit", "--unit", "T-L01", "--engines", "E8", "--out", str(out), "--map", str(paths["map"]),
                     "--source", str(paths["source"]), "--materials", str(paths["materials"])])
    assert code == 1
    assert not (out / "needs_modelling" / "abc.png").exists() and not (out / "fills" / "fill-0001.png").exists()
    assert (out / "needs_modelling" / "my-notes.txt").read_text(encoding="utf-8") == "keep"
    assert not (out / "fills").exists(), "an empty folder of crops is removed"
    assert (out / "empty_after").is_dir(), "a folder the tool never writes stays"
