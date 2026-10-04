from __future__ import annotations

import json
from pathlib import Path
import pytest


def test_find_errors_timings_five_stage_keys():
    """`find_errors(..., timings=t)` fills 5 stage keys and gives the same result as without it (on `two_sided_wall`)."""
    from engine.detectors.errors import find_errors
    from engine.tests.fixtures.build import two_sided_wall

    mesh = two_sided_wall()
    timings: dict[str, float] = {}
    errs_with_timings = find_errors(mesh, timings=timings)
    errs_without = find_errors(mesh)

    # Output is unchanged when timings is provided
    assert errs_with_timings == errs_without

    # Fills 5 stage keys: topology, exposure, double_layers, fragments, assemble
    expected_stages = {"topology", "exposure", "double_layers", "fragments", "assemble"}
    assert set(timings.keys()) == expected_stages
    for stage in expected_stages:
        assert isinstance(timings[stage], float)
        assert timings[stage] >= 0.0


def test_flicker_split_two_sided_wall_sums_to_total_pairs():
    """The flicker split on `two_sided_wall` sums to the total pair count."""
    from engine.campus.census import flicker_split
    from engine.detectors.errors import find_errors
    from engine.tests.fixtures.build import two_sided_wall

    mesh = two_sided_wall()
    errs = find_errors(mesh)
    pairs = errs["flicker_pairs"]
    assert len(pairs) == 2

    # Two-sided wall has different materials ("concrete", "prismarine") facing opposite directions
    split = flicker_split(mesh, pairs, materials={"concrete": {"look": "look1"}, "prismarine": {"look": "look2"}})
    assert sum(split.values()) == len(pairs)
    assert split["diff_look_opposite"] == len(pairs)
    assert split["same_look_opposite"] == 0
    assert split["same_look_same"] == 0
    assert split["diff_look_same"] == 0


def test_flicker_split_two_materials_share_one_look():
    """Two material names that share one look produce same_look (E4), no diff_look (E5)."""
    from engine.campus.census import flicker_split
    from engine.detectors.errors import find_errors
    from engine.tests.fixtures.build import two_sided_wall

    mesh = two_sided_wall()
    errs = find_errors(mesh)
    pairs = errs["flicker_pairs"]
    assert len(pairs) == 2

    # concrete and prismarine share the SAME look -> E4, not E5
    split = flicker_split(mesh, pairs, materials={"concrete": {"look": "shared_look"}, "prismarine": {"look": "shared_look"}})
    assert split["same_look_opposite"] == 2
    assert split["diff_look_opposite"] == 0
    assert split["same_look"] == 2
    assert split["diff_look"] == 0


def test_flicker_split_missing_map_or_material_raises():
    """A missing materials map or a material name not in the map raises."""
    from engine.campus.census import flicker_split
    from engine.detectors.errors import find_errors
    from engine.tests.fixtures.build import two_sided_wall

    mesh = two_sided_wall()
    errs = find_errors(mesh)
    pairs = errs["flicker_pairs"]

    # Missing file path must raise FileNotFoundError
    with pytest.raises(FileNotFoundError):
        flicker_split(mesh, pairs, materials=Path("nonexistent_materials.json"))

    # Material name missing from map must raise KeyError
    with pytest.raises(KeyError):
        flicker_split(mesh, pairs, materials={"concrete": {"look": "look1"}})  # missing "prismarine"


def test_census_two_fixture_units_and_timeout(tmp_path: Path):
    """`census` on two fixture units writes both rows with `seconds` and `peak_mb`, and a `timeout_s` of 0.001 marks a unit as timeout."""
    from engine.campus.census import census
    from engine.io.obj_writer import write_obj
    from engine.tests.fixtures.build import two_sided_wall, cube

    mat_file = tmp_path / "materials.json"
    mat_file.write_text(json.dumps({
        "materials": {
            "concrete": {"look": "l1"},
            "prismarine": {"look": "l2"},
            "default": {"look": "l3"},
        }
    }), encoding="utf-8")

    snap1 = tmp_path / "unit_1"
    snap1.mkdir()
    write_obj(two_sided_wall(), snap1 / "CHTM_unit1.obj")

    snap2 = tmp_path / "unit_2"
    snap2.mkdir()
    write_obj(cube(), snap2 / "CHTM_unit2.obj")

    out_json = tmp_path / "census.json"
    result = census([snap1, snap2], out_json=out_json, jobs=2, materials_path=mat_file)

    assert out_json.is_file()
    assert len(result["rows"]) == 2
    for row in result["rows"]:
        assert row["status"] == "ok"
        assert "seconds" in row
        assert isinstance(row["seconds"], float)
        assert "peak_mb" in row
        assert isinstance(row["peak_mb"], (int, float))

    # Test timeout with very small timeout_s
    out_timeout_json = tmp_path / "census_timeout.json"
    timeout_res = census([snap1], out_json=out_timeout_json, jobs=1, timeout_s=0.0001, materials_path=mat_file)
    timeout_rows = timeout_res["rows"]
    assert len(timeout_rows) == 1
    assert timeout_rows[0]["status"] == "timeout"


def test_errors_json_equal_to_find_errors(tmp_path: Path):
    """Each unit's `errors/<unit>.json` loads equal to `find_errors` run directly on that unit."""
    from engine.campus.census import census
    from engine.detectors.errors import find_errors
    from engine.io.obj_writer import write_obj
    from engine.tests.fixtures.build import two_sided_wall

    mat_file = tmp_path / "materials.json"
    mat_file.write_text(json.dumps({
        "materials": {
            "concrete": {"look": "l1"},
            "prismarine": {"look": "l2"},
        }
    }), encoding="utf-8")

    snap = tmp_path / "unit_a"
    snap.mkdir()
    mesh = two_sided_wall()
    write_obj(mesh, snap / "unit_a.obj")

    out_json = tmp_path / "census.json"
    census([snap], out_json=out_json, jobs=1, materials_path=mat_file)

    errors_file = tmp_path / "errors" / "unit_a.json"
    assert errors_file.is_file()

    expected_errors = find_errors(mesh)
    saved_errors = json.loads(errors_file.read_text(encoding="utf-8"))
    assert saved_errors == expected_errors


def test_fix_plan_hidden_and_diff_look_flicker():
    """The fix plan of a unit whose only errors are `hidden` faces and different-look flicker pairs is `E3, E5, E7`, in that order, with their counts (E7's count null)."""
    from engine.campus.census import compute_fix_plan

    counts = {
        "open_edges": 0,
        "hidden": 12,
        "loose": 0,
        "reversed": 0,
        "flicker_diff": 4,
        "flicker_same": 0,
        "cracks": 0,
    }
    flicker_split_data = {
        "same_look_opposite": 0,
        "same_look_same": 0,
        "diff_look_opposite": 3,
        "diff_look_same": 1,
    }
    n_faces = 50

    plan = compute_fix_plan(counts, flicker_split_data, n_faces=n_faces)

    engines = [step["engine"] for step in plan]
    assert engines == ["E3", "E5", "E7"]

    assert plan[0] == {"engine": "E3", "kinds": ["hidden"], "count": 12}
    assert plan[1] == {"engine": "E5", "kinds": ["diff_look"], "count": 4}
    assert plan[2] == {"engine": "E7", "kinds": ["gridlines"], "count": None}


def test_fix_plan_full_order_all_engines():
    """All 8 engines follow order E8 -> E3 -> E1 -> E2 -> E4 -> E5 -> E6 -> E7 when all errors present."""
    from engine.campus.census import compute_fix_plan

    counts = {
        "open_edges": 5,
        "hidden": 10,
        "loose": 3,
        "reversed": 2,
        "flicker_diff": 4,
        "flicker_same": 1,
        "cracks": 7,
    }
    flicker_split_data = {
        "same_look_opposite": 1,
        "same_look_same": 0,
        "diff_look_opposite": 2,
        "diff_look_same": 2,
    }
    plan = compute_fix_plan(counts, flicker_split_data, n_faces=100)
    engines = [step["engine"] for step in plan]
    assert engines == ["E8", "E3", "E1", "E2", "E4", "E5", "E6", "E7"]


def test_unit_building_classifier():
    from engine.campus.census import unit_building

    assert unit_building("CHTM_SIDE_WALK_2nd_floor") == "CHTM"
    assert unit_building("Eds_2nd_Floor_obj") == "EDS"
    assert unit_building("BRS_3rd_floor") == "BRS"
    assert unit_building("Gymnasium_5th_floor_and_roof") == "GYMNASIUM"
    assert unit_building("Main_Infrustructure_Building") == "MAIN_INFRA"
    assert unit_building("MAIN_BUILDING") == "MAIN"
    assert unit_building("PE_BUILDING") == "PE"
    assert unit_building("Science_A_1st_Floor") == "SCIENCE_A"
    assert unit_building("Architecture_1st_floor") == "ARCHITECTURE"
    assert unit_building("something_else") == "SITE"


def test_format_census_md():
    from engine.campus.census import format_census_md

    rows = [
        {
            "unit": "CHTM_unit1",
            "building": "CHTM",
            "status": "ok",
            "triangles": 100,
            "counts": {"open_edges": 2, "hidden": 1, "loose": 0, "reversed": 0, "flicker_diff": 0, "flicker_same": 0, "cracks": 0},
            "seconds": 1.23,
            "peak_mb": 45.6,
        },
        {
            "unit": "EDS_unit1",
            "building": "EDS",
            "status": "timeout",
        }
    ]
    totals = {
        "units": 2,
        "triangles": 100,
        "counts": {"open_edges": 2, "hidden": 1, "loose": 0, "reversed": 0, "flicker_diff": 0, "flicker_same": 0, "cracks": 0},
        "seconds": 1.23,
    }
    md = format_census_md(rows, totals)
    assert "# Campus Error Census" in md
    assert "CHTM_unit1" in md
    assert "TIMEOUT" in md
    assert "## Totals by Building" in md
    assert "**Total**" in md


def test_cli_census_subcommand(tmp_path: Path):
    from engine.cli import main
    from engine.io.obj_writer import write_obj
    from engine.tests.fixtures.build import two_sided_wall

    mat_file = tmp_path / "materials.json"
    mat_file.write_text(json.dumps({
        "materials": {
            "concrete": {"look": "l1"},
            "prismarine": {"look": "l2"},
        }
    }), encoding="utf-8")

    snap = tmp_path / "unit_cli"
    snap.mkdir()
    write_obj(two_sided_wall(), snap / "CHTM_unit_cli.obj")

    out_json = tmp_path / "out_census.json"
    ret = main(["census", str(snap), "--out", str(out_json), "--jobs", "1", "--materials", str(mat_file)])
    assert ret == 0
    assert out_json.is_file()
    data = json.loads(out_json.read_text(encoding="utf-8"))
    assert len(data["rows"]) == 1
    assert data["rows"][0]["unit"] == "CHTM_unit_cli"

