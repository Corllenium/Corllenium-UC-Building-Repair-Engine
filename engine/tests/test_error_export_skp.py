from pathlib import Path

import pytest

from engine.campus import error_export as ee
from engine.io import skp_writer
from engine.io.skp_writer import SketchUpUnavailable
from engine.tests.test_error_export_plan import _plan, campus  # noqa: F401  (fixture)


@pytest.fixture
def sketchup():
    try:
        skp_writer.load_api()
    except SketchUpUnavailable as exc:
        pytest.skip(f"SketchUp C API unavailable: {exc}")


@pytest.mark.parametrize("bad", [
    r"D:\PROJECTS\UC MODEL FIXER\MODEL FIXER ENGINE FILES\02-SKETCHUP-MODELS\CHECKPOINT-17-BACKUP\x.skp",
    r"D:\PROJECTS\UC\02-SKETCHUP\current\x.skp",
    r"D:\PROJECTS\UC ENVIRONMENT BUILDING\REQUIREMENTS\x.skp",
    r"D:\PROJECTS\UC MODEL FIXER\..\UC\02-SKETCHUP\current\x.skp",
    "D:/PROJECTS/UC MODEL FIXER/../UC/02-SKETCHUP/current/x.skp",
    "d:/projects/uc/02-sketchup/current/sub/../x.skp",
])
def test_outputs_inside_the_protected_folders_are_refused(campus, bad):
    with pytest.raises(ValueError, match="protected"):
        ee.write_building_skp(_plan(campus), Path(bad))


def test_the_written_file_reads_back_with_every_kind_on_its_own_tag(campus, sketchup, tmp_path):
    plan = _plan(campus)
    out = tmp_path / "B-errors.skp"
    report = ee.write_building_skp(plan, out)
    assert out.is_file() and report["rejected_faces"] == 0
    back = ee.read_back(out)
    faces = back["faces_by_tag"]
    assert faces["base"] == 5                       # A 2 + S band 1 1 + S band 2 2
    assert faces["error_flicker_diff"] == 1
    assert faces["error_hidden"] == 1
    assert faces["error_reversed"] == 1
    assert faces["error_loose"] == 8                # one octahedron marker
    assert faces["error_open_edges"] == 3 * 3       # three tubes of three sides
    assert faces["error_cracks"] == 2 * 8           # two crack cells
    assert faces["grouping_excluded"] >= 4 + 4      # the excluded copy's faces plus its plate ring
    assert faces["grouping_split"] > 0 and faces["grouping_pending"] > 0 and faces["grouping_skp_mismatch"] > 0
    assert faces["labels"] > 0
    assert set(report["faces_by_tag"]) <= set(back["tags"])
    assert report["faces_by_tag"] == {k: v for k, v in faces.items() if v}
    assert "UNIT | L01 B-L01" in back["group_names"]
    assert "MEMBER | S_building" in back["group_names"]


def test_a_relative_output_inside_a_protected_folder_is_refused(campus, tmp_path, monkeypatch):
    inside = tmp_path / "CHECKPOINT-17-BACKUP"
    inside.mkdir()
    monkeypatch.chdir(inside)
    with pytest.raises(ValueError, match="protected"):
        ee.write_building_skp(_plan(campus), Path("x.skp"))


def test_identical_triangles_in_one_group_read_back_once(sketchup, tmp_path):
    import numpy as np
    tri = np.array([[[0, 0, 0], [10, 0, 0], [0, 10, 0]]], float)
    tris = np.concatenate([tri, tri[:, ::-1], tri + [20, 0, 0]])
    member = ee.MemberPlan(group="G", tris={"base": tris})
    col = ee.ColumnPlan("U", "L01 U", "floor", 0.0, 30.0, 10.0, [member], [], {})
    plan = ee.BuildingPlan("B", [col], {k: 0 for k in ee.ERROR_KINDS + ee.LINE_KINDS})
    out = tmp_path / "dup.skp"
    written = ee.write_building_skp(plan, out)
    back = ee.read_back(out)
    assert written["faces_by_tag"]["base"] == 3
    assert ee.exact_duplicates(tris) == 1
    assert back["faces_by_tag"]["base"] == 3 - ee.exact_duplicates(tris)
