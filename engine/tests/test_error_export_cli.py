import hashlib
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


OBJ_SHA = hashlib.sha256(OBJ.encode("utf-8")).hexdigest()

#: one triangle drawn twice (1 in apart, as two triangles are in a real plane) in two materials (a, b) of ONE look
OBJ_LOOKS = """o G
v 0 0 100
v 10 0 100
v 10 10 100
v 1 0 100
v 11 0 100
v 11 10 100
usemtl a
f 1 2 3
usemtl b
f 4 5 6
"""
OBJ_LOOKS_SHA = hashlib.sha256(OBJ_LOOKS.encode("utf-8")).hexdigest()


def _campus(tmp_path, source_sha=OBJ_SHA, map_sha=OBJ_SHA, obj=OBJ, error_map=None, looks=None):
    """`source_sha` / `map_sha`: the sha256 that source.json / campus_map.json give the member (None: leave it out).
    P1-H1b item 8 edit: they used to be a made-up "s" * 64 in source.json and absent from the map; the export now
    checks them against the snapshot file, so the fixture carries the real hash."""
    snap = tmp_path / "snap" / "abc"
    snap.mkdir(parents=True)
    (snap / "B_1st_floor.obj").write_bytes(obj.encode("utf-8"))      # bytes: write_text would add CRs on Windows
    source = tmp_path / "source.json"
    row = {"group": "B_1st_floor", "file": "B_1st_floor.obj", "dir": str(snap), "tris": 2}
    if source_sha is not None:
        row["sha256"] = source_sha
    source.write_text(json.dumps({"snapshots": [row]}), encoding="utf-8")
    errors = tmp_path / "errors"
    errors.mkdir()
    materials = tmp_path / "materials.json"          # P1-H1b item 9: the command now needs the looks
    materials.write_text(json.dumps({"materials": looks or {"a": {"look": "L1"}, "b": {"look": "L2"}}}),
                         encoding="utf-8")
    (errors / "B_1st_floor.json").write_text(json.dumps(error_map or {
        "n_faces": 2, "faces": {"reversed": [1]}, "open_edges": [[0, 0, 100, 10, 0, 100]], "cracks": [],
        "counts": {"reversed": 1, "open_edges": 1, "cracks": 0}}), encoding="utf-8")
    cmap = tmp_path / "campus_map.json"
    cmap.write_text(json.dumps({"units": [{"unit": "BRS-L01", "building": "BRS", "level": "L01", "type": "floor",
                                           "base": 100.0, "flags": [], "confirmed_by_owner": True,
                                           "members": [{"group": "B_1st_floor", "file": "B_1st_floor.obj",
                                                        "faces": "all",
                                                        **({} if map_sha is None else {"sha256": map_sha})}]}],
                                "excluded": []}), encoding="utf-8")
    check = tmp_path / "skp_check.json"
    check.write_text(json.dumps({"mismatches": []}), encoding="utf-8")
    return ["--map", str(cmap), "--source", str(source), "--errors", str(errors), "--skp-check", str(check),
            "--materials", str(materials)]


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
    assert set(report["inputs"]) == {"campus_map", "skp_check", "errors", "source", "snapshots", "materials"}
    assert report["inputs"]["snapshots"] == {"B_1st_floor": OBJ_SHA}
    assert report["legend"] == list(("base",) + ee.ERROR_KINDS + ee.LINE_KINDS + ee.GROUPING_KINDS)
    assert "BRS" in capsys.readouterr().out


# --------------------------------------------------------- the export checks its inputs (P1-H1b item 8)


def _refused(tmp_path, **kw):
    args = _campus(tmp_path, **kw) + ["--out", str(tmp_path / "out")]
    with pytest.raises(ValueError, match="B_1st_floor") as raised:
        cli.main(["campus-errors-skp", *args])
    assert not (tmp_path / "out" / "BRS").exists()                # nothing was written
    return str(raised.value)


def test_a_snapshot_whose_bytes_are_not_the_sha256_in_the_map_is_refused(tmp_path):
    text = _refused(tmp_path, map_sha="m" * 64, source_sha="m" * 64)       # source and map agree, the file does not
    assert "sha256" in text and "campus_map.json" in text


def test_a_source_json_sha256_that_differs_from_the_map_is_refused(tmp_path):
    text = _refused(tmp_path, source_sha="s" * 64)                         # the file matches the map, source.json not
    assert "sha256" in text and "source.json" in text


def test_a_member_without_a_sha256_in_the_map_is_refused(tmp_path):
    text = _refused(tmp_path, map_sha=None)
    assert "sha256" in text and "campus_map.json" in text


def test_an_excluded_duplicate_is_checked_against_source_json_alone(tmp_path):
    obj = tmp_path / "D.obj"
    obj.write_bytes(OBJ.encode("utf-8"))
    assert ee.check_member_input("D", obj, None, OBJ_SHA, in_map=False) == OBJ_SHA
    with pytest.raises(ValueError, match="D: the snapshot .* source.json froze"):
        ee.check_member_input("D", obj, None, "x" * 64, in_map=False)
    with pytest.raises(ValueError, match="D: source.json gives it no sha256"):
        ee.check_member_input("D", obj, None, None, in_map=False)


def test_two_materials_of_one_look_come_out_as_same_look_flicker(tmp_path):
    """P1-H1b item 9, through the command: find_errors listed both faces as flicker_diff (two material indices);
    the export reads the look and draws them, and counts them, as flicker_same."""
    try:
        skp_writer.load_api()
    except SketchUpUnavailable as exc:
        pytest.skip(f"SketchUp C API unavailable: {exc}")
    error_map = {"n_faces": 2, "faces": {"flicker_diff": [0, 1]}, "open_edges": [], "cracks": [],
                 "flicker_pairs": [[0, 1, 50.0, False]], "counts": {"flicker_diff": 2}}
    args = _campus(tmp_path, source_sha=OBJ_LOOKS_SHA, map_sha=OBJ_LOOKS_SHA, obj=OBJ_LOOKS, error_map=error_map,
                   looks={"a": {"look": "L1"}, "b": {"look": "L1"}})
    out = tmp_path / "out"
    assert cli.main(["campus-errors-skp", *args, "--out", str(out)]) == 0
    report = json.loads((out / "BRS" / "BRS-errors.json").read_text(encoding="utf-8"))
    assert report["counts"]["flicker_same"] == 2 and report["counts"]["flicker_diff"] == 0
    assert report["read_back"]["faces_by_tag"]["error_flicker_same"] == 2
    assert report["read_back"]["faces_by_tag"].get("error_flicker_diff", 0) == 0


def test_a_missing_materials_map_is_refused_and_named(tmp_path):
    args = _campus(tmp_path)
    args[args.index("--materials") + 1] = str(tmp_path / "nope.json")
    with pytest.raises(FileNotFoundError, match="Materials map not found.*nope.json.*--materials"):
        cli.main(["campus-errors-skp", *args, "--out", str(tmp_path / "out")])
