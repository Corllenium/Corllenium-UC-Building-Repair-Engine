import json

import pytest

from engine import cli
from engine.campus import error_export as ee
from engine.io import skp_writer
from engine.io.skp_writer import SketchUpUnavailable

OBJ = """o G
v 0 0 100
v 10 0 100
v 10 10 100
v 0 10 100
f 1 2 3
f 1 3 4
"""


def _campus(tmp_path):
    snap = tmp_path / "snap" / "abc"
    snap.mkdir(parents=True)
    (snap / "B_1st_floor.obj").write_text(OBJ, encoding="utf-8")
    source = tmp_path / "source.json"
    source.write_text(json.dumps({"snapshots": [{"group": "B_1st_floor", "file": "B_1st_floor.obj",
                                                 "dir": str(snap), "tris": 2}]}), encoding="utf-8")
    errors = tmp_path / "errors"
    errors.mkdir()
    (errors / "B_1st_floor.json").write_text(json.dumps({
        "n_faces": 2, "faces": {"reversed": [1]}, "open_edges": [[0, 0, 100, 10, 0, 100]], "cracks": [],
        "counts": {"reversed": 1, "open_edges": 1, "cracks": 0}}), encoding="utf-8")
    cmap = tmp_path / "campus_map.json"
    cmap.write_text(json.dumps({"units": [{"unit": "BRS-L01", "building": "BRS", "level": "L01", "type": "floor",
                                           "base": 100.0, "flags": [], "confirmed_by_owner": True,
                                           "members": [{"group": "B_1st_floor", "file": "B_1st_floor.obj",
                                                        "faces": "all"}]}],
                                "excluded": []}), encoding="utf-8")
    check = tmp_path / "skp_check.json"
    check.write_text(json.dumps({"mismatches": []}), encoding="utf-8")
    return ["--map", str(cmap), "--source", str(source), "--errors", str(errors), "--skp-check", str(check)]


def test_the_cli_refuses_a_protected_output_folder(tmp_path):
    args = _campus(tmp_path) + ["--out", r"D:\PROJECTS\UC\02-SKETCHUP\current\x"]
    with pytest.raises(ValueError, match="protected"):
        cli.main(["campus-errors-skp", *args])


def test_the_cli_writes_one_file_and_report_per_building(tmp_path, capsys):
    try:
        skp_writer.load_api()
    except SketchUpUnavailable as exc:
        pytest.skip(f"SketchUp C API unavailable: {exc}")
    out = tmp_path / "out"
    assert cli.main(["campus-errors-skp", *_campus(tmp_path), "--out", str(out)]) == 0
    skp = out / "BRS" / "BRS-errors.skp"
    report = json.loads((out / "BRS" / "BRS-errors.json").read_text(encoding="utf-8"))
    assert skp.is_file()
    assert report["building"] == "BRS"
    assert report["counts"]["reversed"] == 1 and report["counts"]["open_edges"] == 1
    assert report["read_back"]["faces_by_tag"]["base"] == 1
    assert report["read_back"]["faces_by_tag"]["error_reversed"] == 1
    assert report["written"]["faces_by_tag"] == report["read_back"]["faces_by_tag"]
    assert report["duplicates_by_tag"] == {} and report["unexplained_by_tag"] == {}
    assert report["columns"][0]["unit"] == "BRS-L01"
    assert set(report["inputs"]) == {"campus_map", "skp_check", "errors"}
    assert "BRS" in capsys.readouterr().out
