"""Job P2-E8b item 4: `repair-unit`'s review list of the narrow flat fill (ruling E8b-R8).

`report.json` gets `fills`, one row per kept fill (site, loop vertex count, area, inscribed diameter, look, centroid,
normal, and a BEFORE | AFTER crop from a viewpoint that sees through the hole), and `not_filled`, every hole refused
with the rule that refused it, a fill the site check charged included (E8c reads that list); `fill_stats` counts the
loops, the patch outer borders (counted, not listed) and the inscribed-diameter histogram.
"""
from __future__ import annotations

import dataclasses
import json

import numpy as np
from PIL import Image

from engine import cli
from engine.io.obj_reader import read_obj
from engine.repair.engines import e8_fill
from engine.tests.fixtures.holes import floor_over_room
from engine.tests.test_cli_repair_unit import _FAST, _campus


def _run(tmp_path, mesh, engines=("E8",)):
    paths, snap = _campus(tmp_path, mesh)
    # the room below (m1) in another colour than the floor (m0), so the crops tell them apart
    (snap / "materials.mtl").write_text("newmtl m0\nKd 0.8 0.8 0.8\n\nnewmtl m1\nKd 0.2 0.4 0.8\n\n", encoding="utf-8")
    out = tmp_path / "out"
    code = cli.cmd_repair_unit(out, unit="T-L01", engines=list(engines), campus_map=paths["map"],
                               source=paths["source"], materials=paths["materials"], profile=_FAST)
    return code, out, json.loads((out / "report.json").read_text(encoding="utf-8"))


def test_one_fillable_and_one_refused_hole_give_one_fill_and_one_not_filled_row(tmp_path):
    mesh = floor_over_room()
    code, out, report = _run(tmp_path, mesh)
    assert code == 0 and report["exit_code"] == 0
    (fill,) = report["fills"]
    assert fill["vertices"] == 8 and abs(fill["area"] - 400.0) < 1e-6 and abs(fill["inscribed_diameter"] - 20.0) < 0.05
    assert fill["look"] == "material:m0" and fill["normal"] == [0.0, 0.0, 1.0]
    assert {"site", "centroid", "crop"} <= set(fill)
    (row,) = report["not_filled"]
    assert (row["rule"], row["reason"]) == ("E8b-R3", "too_wide") and row["vertices"] == 24
    stats = report["fill_stats"]
    assert (stats["holes"], stats["kept"], stats["rolled_back"], stats["outer_boundaries"]) == (2, 1, 0, 2)
    assert stats["not_filled_by_reason"] == {"too_wide": 1}
    assert sum(stats["diameter_histogram"]["counts"]) == 2
    # the edit log has the fill as an add with no new points
    lines = [json.loads(line) for line in (out / "edit_log.jsonl").read_text(encoding="utf-8").splitlines()]
    (edit,) = [line for line in lines if "check" not in line]
    assert (edit["engine"], edit["kind"], edit["n_new_points"], edit["flat_fill"]) == ("E8", "add", 0, True)
    assert read_obj(out / "T-L01.fixed.obj").n_faces == mesh.n_faces + 6


def test_each_kept_fill_has_a_before_after_crop_through_the_hole(tmp_path):
    _code, out, report = _run(tmp_path, floor_over_room())
    (fill,) = report["fills"]
    crop = out / fill["crop"]
    assert crop.is_file()
    image = np.asarray(Image.open(crop).convert("RGB"))
    half = (image.shape[1] - 4) // 2
    before, after = image[:, :half], image[:, half + 4:]
    assert before.shape == after.shape and image.shape[0] == half
    centre = (slice(half // 2 - 4, half // 2 + 4), slice(half // 2 - 4, half // 2 + 4))
    assert not np.array_equal(before[centre], after[centre]), "BEFORE shows the room through the hole, AFTER the fill"


def test_a_fill_the_check_charges_is_listed_in_not_filled(tmp_path, monkeypatch):
    class OtherLook(e8_fill.E8FlatFill):
        def plan(self, unit, ctx):
            return [dataclasses.replace(e, evidence={**e.evidence, "material": 1}) for e in super().plan(unit, ctx)]
    monkeypatch.setattr(e8_fill, "E8FlatFill", OtherLook)
    code, _out, report = _run(tmp_path, floor_over_room(), engines=("E8b",))
    assert code == 0 and report["fills"] == []
    charged = [r for r in report["not_filled"] if r["rule"] == "E8b-R7"]
    assert len(charged) == 1 and charged[0]["reason"] == "charged" and charged[0]["vertices"] == 8
    assert charged[0]["detail"].get("covered", 0) > 0
    assert report["fill_stats"]["rolled_back"] == 1 and report["fill_stats"]["kept"] == 0


def test_without_e8b_the_report_has_no_fills(tmp_path):
    _code, _out, report = _run(tmp_path, floor_over_room(), engines=("E8a",))
    assert report["fills"] == [] and report["not_filled"] == [] and report["fill_stats"] is None


def test_the_diameter_histogram_bins_follow_the_engine_s_cap(monkeypatch):
    monkeypatch.setattr(e8_fill, "FILL_MAX_DIAMETER", 30.0)
    assert 30.0 in cli.fill_diameter_bins() and 39.37 not in cli.fill_diameter_bins()
