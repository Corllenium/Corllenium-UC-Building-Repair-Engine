"""`engine.campus.skp_check`: does the CHECKPOINT-17 OBJ export match the owner's CHECKPOINT-17
backup? Everything here runs without SketchUp: the walk of the backup is a plain dict (what
`engine.io.skp_reader.walk_skp` returns), and the export is a handful of tiny OBJ files. The two
tests that really open a model with the SketchUp C API are at the end and skip without it.

The numbers are made up so that every verdict can be worked out by eye: a floor is a rectangle
`w x h` at one height, so its area is `w * h` and its box is its corners."""
from __future__ import annotations

import hashlib
import json
import subprocess
import sys
from pathlib import Path

import pytest

from engine.campus import skp_check
from engine.io import skp_reader
from engine.io.skp_writer import SketchUpUnavailable
from engine.tests.skp_scene import build_scene, square, translation

# ------------------------------------------------------------------------------- the walk


def node(name="", kind="group", definition=None, faces=0, area=0.0, bbox=None, children=(),
         skipped=()):
    """One node of a walk (see `engine.io.skp_reader`): the numbers are for its own faces."""
    return {"kind": kind, "name": name, "definition": definition, "faces": faces,
            "tris": 2 * faces, "area": float(area), "bbox": bbox, "hidden_faces": 0,
            "layer_hidden_faces": 0, "children": list(children), "skipped": list(skipped)}


def holder(*path, **own):
    """Nested groups named `path` (outermost first), the last one holding the faces in `own`."""
    *outer, last = path
    inner = node(last, **own)
    for name in reversed(outer):
        inner = node(name, children=[inner])
    return inner


def walk_of(*top, **root_own):
    totals = {"groups": 0, "instances": 0, "faces": 0, "tris": 0, "hidden_nodes": 0,
              "layer_hidden_nodes": 0, "hidden_faces": 0, "layer_hidden_faces": 0}
    return {"path": "backup.skp", "api_version": "14.2", "elapsed_s": 1.0, "layers_bound": True,
            "totals": totals, "root": node(kind="model", children=top, **root_own)}


def box(x0, y0, x1, y1, z=0.0):
    return [[x0, y0, z], [x1, y1, z]]


# ---------------------------------------------------------------- the name the exporter writes


def test_the_exporter_writes_every_character_that_is_not_a_letter_digit_or_underscore_as_underscore():
    assert skp_check.exporter_name("Eds 2nd Floor.obj") == "Eds_2nd_Floor_obj"
    assert skp_check.exporter_name("minecraft_concrete_white_-1") == "minecraft_concrete_white__1"
    assert skp_check.exporter_name("BRS tower body (reimport)") == "BRS_tower_body__reimport_"
    assert skp_check.exporter_name("Étage") == "_tage"
    assert skp_check.exporter_name("") == ""


# ------------------------------------------------------------------ which file a face goes to


def key(*path):
    """The split key of a face in the last group of `path` (names as SketchUp has them)."""
    chain = None
    for name in reversed(path):
        chain = node(name, children=[] if chain is None else [chain])
    flat, current = [], chain
    while current is not None:
        flat.append(current)
        current = current["children"][0] if current["children"] else None
    return skp_check.split_key(flat)[0]


def test_the_outermost_group_with_a_floor_like_name_gives_the_file():
    assert key("EDS 2nd Floor.obj", "minecraft_concrete_white_-1", "") == "EDS_2nd_Floor_obj"
    # a floor group inside another floor group: the outer one wins
    assert key("Gymnasium roof", "floor 2", "minecraft_x_-1", "") == "Gymnasium_roof"
    # a floor inside a building: the floor, not the building
    assert key("MAIN BUILDING", "Main 6ft Floor.obj", "minecraft_x_-1", "") == "Main_6ft_Floor_obj"


def test_the_words_that_make_a_group_a_floor():
    for word in ("floor", "side walk", "sidewalk", "stairs", "bridge", "roof", "pathway", "ground"):
        assert key("Block A", f"North {word}", "minecraft_x_-1", "") == f"North_{word.replace(' ', '_')}"
    assert key("Block A", "North FLOOR", "minecraft_x_-1", "") == "North_FLOOR"      # any case
    assert key("Block A", "North wall", "minecraft_x_-1", "") == "Block_A"           # not one


def test_without_a_floor_like_name_the_outermost_named_group_gives_the_file():
    assert key("MAIN BUILDING", "Tower", "minecraft_x_-1", "") == "MAIN_BUILDING"
    assert key("ARCHITECTURE BUILDING", "minecraft_x_-1", "") == "ARCHITECTURE_BUILDING"


def test_names_the_import_made_are_not_names_a_person_gave():
    # Group12, Mesh3, Component1 and the material groups of the Minecraft import are skipped
    assert key("ROAD harrison front", "Group12", "minecraft_stone_-1", "") == "ROAD_harrison_front"
    assert key("Wall", "littletiles_ltcolored6_-1", "") == "Wall"
    assert key("kirosblocks_colored_metal_block_-1", "Tower", "minecraft_x_-1", "") == "Tower"
    # but a component instance that was never named is a name, as the export writes it
    assert key("Component#6", "x", "") == "Component_6"


def test_when_every_ancestor_is_an_import_name_the_outermost_one_gives_the_file():
    assert key("", "", "minecraft_x_-1", "") == "Group"       # an unnamed group: Group<N> in the export


def test_faces_directly_in_a_top_level_group_or_in_the_model_go_to_unnamed():
    """The group that holds the faces is not looked at (the exporter's own mesh name stands in
    its place), so a face directly in a top-level group has no ancestor left to name it."""
    assert key("EDS 2nd Floor.obj") == "unnamed"
    assert skp_check.split_key([]) == ("unnamed", None)


def test_the_selected_group_is_returned_with_the_key():
    floor = node("Eds 2nd Floor.obj", children=[node("minecraft_x_-1", children=[node("", faces=1)])])
    chain = [floor, floor["children"][0], floor["children"][0]["children"][0]]
    assert skp_check.split_key(chain) == ("Eds_2nd_Floor_obj", floor)


def test_a_component_instance_is_named_by_its_own_name_else_by_its_definition():
    named = node("CHTM 12th floor.obj", kind="instance", definition="Group207")
    bare = node("", kind="instance", definition="Component#6")
    assert skp_check.token(named) == "CHTM_12th_floor_obj"
    assert skp_check.token(bare) == "Component_6"
    assert skp_check.token(node("")) == "Group"                 # an unnamed group


# --------------------------------------------------------------- units: what each file holds


def test_units_collect_every_face_a_file_gets_and_leave_out_the_floors_split_off_above():
    floor = holder("MAIN BUILDING", "Main 6ft Floor.obj", "minecraft_a_-1", "",
                   faces=3, area=300, bbox=box(0, 0, 30, 10))
    own = holder("MAIN BUILDING", "Tower", "minecraft_a_-1", "", faces=2, area=40,
                 bbox=box(100, 0, 104, 10))
    building = node("MAIN BUILDING", children=[floor["children"][0], own["children"][0]])
    units = skp_check.sdk_units(walk_of(building))
    by_key = {u["key"]: u for u in units}
    assert set(by_key) == {"Main_6ft_Floor_obj", "MAIN_BUILDING"}
    assert (by_key["Main_6ft_Floor_obj"]["faces"], by_key["Main_6ft_Floor_obj"]["area"]) == (3, 300.0)
    assert (by_key["MAIN_BUILDING"]["faces"], by_key["MAIN_BUILDING"]["area"]) == (2, 40.0)
    assert by_key["MAIN_BUILDING"]["bbox"] == box(100, 0, 104, 10)
    assert by_key["MAIN_BUILDING"]["path"] == "MAIN BUILDING"


def test_two_groups_with_one_name_are_two_units_with_one_key():
    one = holder("BRS 4th floor.obj", "minecraft_a_-1", "", faces=1, area=10, bbox=box(0, 0, 1, 10))
    two = holder("BRS 4th floor.obj", "minecraft_a_-1", "", faces=2, area=30, bbox=box(5, 0, 8, 10))
    units = skp_check.sdk_units(walk_of(one, two))
    assert [u["key"] for u in units] == ["BRS_4th_floor_obj", "BRS_4th_floor_obj"]
    assert [(u["faces"], u["area"]) for u in units] == [(1, 10.0), (2, 30.0)]


def test_a_unit_adds_up_its_nested_groups_and_takes_the_union_of_their_boxes():
    floor = node("Eds 2nd Floor.obj", children=[
        node("minecraft_a_-1", children=[node("", faces=2, area=20, bbox=box(0, 0, 4, 5))]),
        node("minecraft_b_-1", children=[node("", faces=1, area=7, bbox=box(10, -2, 12, 3))])])
    [unit] = skp_check.sdk_units(walk_of(floor))
    assert (unit["faces"], unit["area"], unit["bbox"]) == (3, 27.0, [[0, -2, 0], [12, 5, 0]])


def test_the_model_s_own_faces_and_faces_in_top_level_groups_are_the_unnamed_unit():
    loose = node("Group#12", faces=4, area=50, bbox=box(0, 0, 5, 10))      # directly in a top-level group
    units = skp_check.sdk_units(walk_of(loose, faces=1, area=5, bbox=box(-3, -3, 0, 0)))
    [unit] = [u for u in units if u["key"] == "unnamed"]
    assert (unit["faces"], unit["area"]) == (5, 55.0)
    assert unit["bbox"] == [[-3, -3, 0], [5, 10, 0]]
    assert unit["path"] == "(the model's own faces and those directly in its top-level groups)"


def test_a_group_with_no_faces_makes_no_unit():
    assert skp_check.sdk_units(walk_of(node("Empty floor", children=[node("minecraft_a_-1")]))) == []


# ------------------------------------------------------------------ comparing a file with a unit


def row(name, area, bbox, tris=2):
    """One file of the export: what `export_stats` says about it."""
    return {"name": name, "file": f"{name}.obj", "tris": tris, "area": float(area), "bbox": bbox}


def unit(key, area, bbox, path=None, faces=1):
    """What the backup holds for a file."""
    return {"key": key, "path": path or key, "faces": faces, "tris": 2 * faces,
            "area": float(area), "bbox": bbox}


TOL = {"bbox_tol": 0.2, "area_tol": 0.005}


def compared(rows, units, **tol):
    return skp_check.compare(rows, units, **{**TOL, **tol})


def test_a_unit_that_agrees_with_its_file_is_a_match():
    result = compared([row("EDS_2nd_Floor_obj", 1000.0, box(0, 0, 10, 100))],
                      [unit("EDS_2nd_Floor_obj", 1000.4, box(0.05, 0, 10, 100.1))])
    [m] = result["matches"]
    assert (m["name"], m["paired_by"], m["reasons"]) == ("EDS_2nd_Floor_obj", "name", [])
    assert m["bbox_max_dev"] == pytest.approx(0.1)
    assert m["area_rel"] == pytest.approx(0.0004)
    assert m["export"] == {"tris": 2, "area": 1000.0, "bbox": box(0, 0, 10, 100)}
    assert m["unit"]["path"] == "EDS_2nd_Floor_obj" and m["unit"]["area"] == 1000.4
    assert (result["mismatches"], result["ambiguities"], result["misses"], result["sdk_only"]) == (
        [], [], [], [])


def test_the_triangles_the_export_lacks_are_counted_beside_the_verdict_and_do_not_decide_it():
    """A face of `v` corners (and `h` holes) is `v + 2h - 2` triangles when nothing is dropped, so
    the backup's count minus the export's is how many triangles the export does not have."""
    [m] = compared([row("A_Floor", 1000.0, box(0, 0, 10, 100), tris=2)],
                   [unit("A_Floor", 1000.0, box(0, 0, 10, 100), faces=3)])["matches"]
    assert m["unit"]["tris"] == 6 and m["export"]["tris"] == 2 and m["tris_diff"] == 4


def test_a_bounding_box_off_by_more_than_the_tolerance_is_a_mismatch_that_says_where():
    [m] = compared([row("A_Floor", 1000.0, box(0, 0, 10, 100))],
                   [unit("A_Floor", 1000.0, box(0, 0, 10.5, 100))])["mismatches"]
    assert m["bbox_dev"] == [0, 0, 0, 0.5, 0, 0]
    assert m["bbox_max_dev"] == pytest.approx(0.5)
    [reason] = m["reasons"]
    assert reason == ("bounding box: max x is 10.5 in the backup and 10 in the export, "
                      "0.5 in apart (tolerance 0.2 in)")


def test_the_tolerance_is_per_bound_and_inclusive_of_the_limit():
    [m] = compared([row("A_Floor", 1000.0, box(0, 0, 10, 100))],
                   [unit("A_Floor", 1000.0, box(0, 0, 10.19, 100))])["matches"]
    assert m["bbox_max_dev"] == pytest.approx(0.19)
    [n] = compared([row("A_Floor", 1000.0, box(0, 0, 10, 100))],
                   [unit("A_Floor", 1000.0, box(0, 0, 10.21, 100))])["mismatches"]
    assert n["bbox_max_dev"] == pytest.approx(0.21)
    [low] = compared([row("A_Floor", 1000.0, box(0, 0, 10, 100))],
                     [unit("A_Floor", 1000.0, box(-0.3, 0, 10, 100))])["mismatches"]
    assert low["bbox_dev"][0] == pytest.approx(-0.3) and "min x" in low["reasons"][0]


def test_an_area_off_by_more_than_half_a_percent_is_a_mismatch_with_the_sign_and_the_numbers():
    low = compared([row("A_Floor", 1000.0, box(0, 0, 10, 100))],
                   [unit("A_Floor", 1004.9, box(0, 0, 10, 100))])
    assert low["mismatches"] == []
    [m] = compared([row("A_Floor", 1000.0, box(0, 0, 10, 100))],
                   [unit("A_Floor", 1005.1, box(0, 0, 10, 100))])["mismatches"]
    assert m["area_rel"] == pytest.approx(0.0051)
    [reason] = m["reasons"]
    assert reason == ("area: the backup has 1,005.1 sq in and the export 1,000.0, "
                      "+0.510% (tolerance 0.5%)")
    [n] = compared([row("A_Floor", 1000.0, box(0, 0, 10, 100))],
                   [unit("A_Floor", 990.0, box(0, 0, 10, 100))])["mismatches"]
    assert n["area_rel"] == pytest.approx(-0.01) and "-1.000%" in n["reasons"][0]


def test_both_reasons_are_listed_and_the_worst_mismatch_comes_first():
    rows = [row("Small_Floor", 1000.0, box(0, 0, 10, 100)), row("Big_Floor", 1000.0, box(0, 0, 10, 100)),
            row("Mid_Floor", 1000.0, box(0, 0, 10, 100))]
    units = [unit("Small_Floor", 1006.0, box(0, 0, 10, 100)), unit("Big_Floor", 1100.0, box(0, 0, 12, 100)),
             unit("Mid_Floor", 1010.0, box(0, 0, 10, 100))]
    result = compared(rows, units)
    assert [m["name"] for m in result["mismatches"]] == ["Big_Floor", "Mid_Floor", "Small_Floor"]
    assert [r.split(":")[0] for r in result["mismatches"][0]["reasons"]] == ["bounding box", "area"]


def test_a_file_with_no_group_of_that_name_in_the_backup_is_a_miss():
    result = compared([row("Lost_Floor", 1000.0, box(0, 0, 10, 100))], [])
    [miss] = result["misses"]
    assert miss["name"] == "Lost_Floor" and miss["file"] == "Lost_Floor.obj"
    assert miss["reason"] == "the backup has no group called Lost_Floor (nor one numbered like it)"
    assert miss["export"]["area"] == 1000.0
    assert result["matches"] == result["mismatches"] == []


def test_faces_in_the_backup_that_no_file_holds_are_listed_as_sdk_only():
    result = compared([], [unit("Orphan_Floor", 55.0, box(0, 0, 5, 11), faces=3)])
    [orphan] = result["sdk_only"]
    assert (orphan["key"], orphan["faces"], orphan["area"]) == ("Orphan_Floor", 3, 55.0)
    assert orphan["reason"] == "the backup has faces here and the export has no file for them"


# ---------------------------------------------------- one name, several groups or several files


def twin_rows():
    return [row("BRS_4th_floor_obj", 27850.0, box(0, 0, 50, 90)),
            row("BRS_4th_floor_obj1", 16329.0, box(100, 0, 140, 60))]


def twin_units():
    big = unit("BRS_4th_floor_obj", 27800.0, box(0, 0, 50, 90), path="BRS BUILDING > BRS 4th floor.obj")
    small = unit("BRS_4th_floor_obj", 16300.0, box(100, 0, 140, 60), path="BRS 4th floor.obj")
    return big, small


def test_two_groups_with_one_name_are_told_apart_by_their_shape_and_still_reported_as_ambiguous():
    big, small = twin_units()
    for units in ([big, small], [small, big]):                 # whichever order the walk met them in
        result = compared(twin_rows(), units)
        paired = {m["name"]: (m["paired_by"], m["unit"]["path"]) for m in result["matches"]}
        assert paired == {"BRS_4th_floor_obj": ("geometry", "BRS BUILDING > BRS 4th floor.obj"),
                          "BRS_4th_floor_obj1": ("geometry", "BRS 4th floor.obj")}
        [amb] = result["ambiguities"]
        assert amb["family"] == "BRS_4th_floor_obj" and amb["resolved"] is True
        assert amb["rows"] == ["BRS_4th_floor_obj", "BRS_4th_floor_obj1"]
        assert sorted(u["path"] for u in amb["units"]) == ["BRS 4th floor.obj",
                                                           "BRS BUILDING > BRS 4th floor.obj"]
        assert "2 groups" in amb["reason"] and "2 files" in amb["reason"]


def test_a_pairing_by_shape_can_still_be_a_mismatch():
    rows = twin_rows()
    big, small = twin_units()
    small["area"] = 16900.0                         # 3.5 % over: close enough to pair, too far to match
    result = compared(rows, [small, big])
    assert [m["name"] for m in result["matches"]] == ["BRS_4th_floor_obj"]
    [m] = result["mismatches"]
    assert (m["name"], m["paired_by"]) == ("BRS_4th_floor_obj1", "geometry")


def test_twins_that_look_alike_cannot_be_told_apart_and_are_left_as_ambiguous():
    rows = [row("Sciene_A_Floor_plan_2_obj", 5000.0, box(0, 0, 50, 100)),
            row("Sciene_A_Floor_plan_2_obj1", 5010.0, box(0, 0, 50, 100))]
    units = [unit("Sciene_A_Floor_plan_2_obj", 5005.0, box(0, 0, 50, 100)),
             unit("Sciene_A_Floor_plan_2_obj", 5006.0, box(0, 0, 50, 100))]
    result = compared(rows, units)
    assert result["matches"] == result["mismatches"] == result["misses"] == []
    [amb] = result["ambiguities"]
    assert amb["resolved"] is False and amb["rows"] == [r["name"] for r in rows]
    assert "alike" in amb["reason"]
    # what a person needs to see why: the files' own numbers beside the groups'
    assert [(f["name"], f["tris"], f["area"]) for f in amb["files"]] == [
        ("Sciene_A_Floor_plan_2_obj", 2, 5000.0), ("Sciene_A_Floor_plan_2_obj1", 2, 5010.0)]
    assert [u["area"] for u in amb["units"]] == [5005.0, 5006.0]


def test_a_pairing_that_is_nowhere_close_is_not_made():
    rows = [row("X_floor", 1000.0, box(0, 0, 10, 100)), row("X_floor1", 4000.0, box(0, 0, 20, 200))]
    units = [unit("X_floor", 1000.0, box(0, 0, 10, 100)), unit("X_floor", 9000.0, box(0, 0, 90, 100))]
    [amb] = compared(rows, units)["ambiguities"]
    assert amb["resolved"] is False and "close enough" in amb["reason"]


def test_more_groups_than_files_or_the_other_way_round_is_an_ambiguity_with_every_candidate():
    result = compared([row("Y_floor", 100.0, box(0, 0, 10, 10))],
                      [unit("Y_floor", 100.0, box(0, 0, 10, 10)),
                       unit("Y_floor", 50.0, box(20, 0, 25, 10))])
    [amb] = result["ambiguities"]
    assert amb["resolved"] is False and len(amb["units"]) == 2
    assert "2 groups" in amb["reason"] and "1 file" in amb["reason"]
    assert result["matches"] == []


def test_a_nameless_group_has_no_name_to_match_so_the_nameless_files_are_paired_by_shape():
    rows = [row("Group124", 196047.0, box(0, 0, 10, 100)), row("Group137", 9231981.0, box(50, 0, 200, 600)),
            row("Group220", 1207179.0, box(300, 0, 340, 400))]
    units = [unit("Group", 1207382.0, box(300, 0, 340, 400), path="Group#162"),
             unit("Group", 9232609.0, box(50, 0, 200, 600), path="Group#46"),
             unit("Group", 195997.0, box(0, 0, 10, 100), path="Group#502")]
    result = compared(rows, units)
    assert {m["name"]: m["unit"]["path"] for m in result["matches"]} == {
        "Group124": "Group#502", "Group137": "Group#46", "Group220": "Group#162"}
    assert result["misses"] == result["sdk_only"] == []
    assert result["ambiguities"][0]["family"] == "Group"


def test_one_unit_and_one_file_with_a_number_on_the_name_are_paired_by_the_family():
    [m] = compared([row("Eds_9th_Floor_obj1", 1000.0, box(0, 0, 10, 100))],
                   [unit("Eds_9th_Floor_obj", 1000.0, box(0, 0, 10, 100))])["matches"]
    assert m["paired_by"] == "name_family"


def test_every_row_ends_up_in_exactly_one_place():
    rows = [row("A_floor", 100.0, box(0, 0, 1, 100)), row("B_floor", 100.0, box(0, 0, 1, 100)),
            row("C_floor", 100.0, box(0, 0, 1, 100)), row("D_floor", 100.0, box(0, 0, 1, 100)),
            row("T_floor", 100.0, box(0, 0, 1, 100)), row("T_floor1", 100.0, box(0, 0, 1, 100))]
    units = [unit("A_floor", 100.0, box(0, 0, 1, 100)), unit("B_floor", 150.0, box(0, 0, 1, 100)),
             unit("D_floor", 100.0, box(0, 0, 1, 100)), unit("T_floor", 100.0, box(0, 0, 1, 100)),
             unit("T_floor", 100.0, box(0, 0, 1, 100)), unit("Z_floor", 1.0, box(0, 0, 1, 1))]
    result = compared(rows, units)
    names = ([m["name"] for m in result["matches"]] + [m["name"] for m in result["mismatches"]]
             + [m["name"] for m in result["misses"]]
             + [n for a in result["ambiguities"] if not a["resolved"] for n in a["rows"]])
    assert sorted(names) == sorted(r["name"] for r in rows)
    assert [m["name"] for m in result["misses"]] == ["C_floor"]
    assert [u["key"] for u in result["sdk_only"]] == ["Z_floor"]


# ------------------------------------------------------------------- the export's own numbers


def write_obj(folder: Path, name: str, x0, y0, x1, y1, z=0.0, extra=""):
    """A snapshot folder holding one OBJ: a flat rectangle of two triangles."""
    folder.mkdir(parents=True, exist_ok=True)
    (folder / f"{name}.obj").write_text(
        f"o {name}\nv {x0} {y0} {z}\nv {x1} {y0} {z}\nv {x1} {y1} {z}\nv {x0} {y1} {z}\n{extra}"
        "f 1 2 3\nf 1 3 4\n", encoding="utf-8")
    return folder


def test_print_step_is_what_six_significant_digits_leave_at_that_size():
    assert skp_check.print_step(24244.2) == pytest.approx(0.1)
    assert skp_check.print_step(99999.9) == pytest.approx(0.1)
    assert skp_check.print_step(9999.99) == pytest.approx(0.01)
    assert skp_check.print_step(100000.0) == pytest.approx(1.0)
    assert skp_check.print_step(0.0) == 0.0


def test_export_stats_are_the_boxes_areas_and_triangles_of_the_files_own_triangles(tmp_path):
    folder = write_obj(tmp_path / "snap", "Floor", 0, 0, 30, 10, z=5.0)
    stats = skp_check.export_stats(folder)
    assert stats["tris"] == 2 and stats["area"] == pytest.approx(300.0)
    assert stats["bbox"] == [[0.0, 0.0, 5.0], [30.0, 10.0, 5.0]]
    assert stats["max_abs_coordinate"] == 30.0 and stats["zero_area_tris"] == 0


def test_export_stats_count_the_triangles_the_print_step_collapsed(tmp_path):
    folder = write_obj(tmp_path / "snap", "Floor", 0, 0, 30, 10, extra="v 5 5 0\nv 6 5 0\nv 7 5 0\n")
    obj = folder / "Floor.obj"
    obj.write_text(obj.read_text() + "f 5 6 7\n")          # three points on a line
    stats = skp_check.export_stats(folder)
    assert (stats["tris"], stats["zero_area_tris"]) == (3, 1)
    assert stats["area"] == pytest.approx(300.0)


def test_a_snapshot_folder_needs_exactly_one_obj(tmp_path):
    folder = write_obj(tmp_path / "snap", "A", 0, 0, 1, 1)
    write_obj(folder, "B", 0, 0, 1, 1)
    with pytest.raises(ValueError, match="exactly one .obj"):
        skp_check.export_stats(folder)


# ---------------------------------------------------------------------- the verified copy


def sha(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def backup_folder(tmp_path, skp=b"skp-bytes", skb=b"skb-bytes"):
    folder = tmp_path / "BACKUP"
    folder.mkdir(parents=True)
    (folder / "M - CHECKPOINT-17.skp").write_bytes(skp)
    (folder / "M - CHECKPOINT-17.skb").write_bytes(skb)
    return folder


def frozen(skp=b"skp-bytes", skb=b"skb-bytes"):
    """The `backup` part of source.json, as `engine.campus.source` writes it."""
    return {"backup": {"M - CHECKPOINT-17.skb": {"sha256": sha(skb), "size": len(skb), "mtime": "x"},
                       "M - CHECKPOINT-17.skp": {"sha256": sha(skp), "size": len(skp), "mtime": "x"}}}


NO_SLEEP = {"interval_s": 0, "sleep": lambda s: None}


def listing(folder: Path):
    return sorted((str(p.relative_to(folder)), p.stat().st_size, p.stat().st_mtime_ns)
                  for p in folder.rglob("*"))


def test_the_copy_is_made_with_copy_verified_and_its_hash_checked(tmp_path):
    backup = backup_folder(tmp_path)
    before = listing(backup)
    copy = skp_check.verified_copy(frozen(), backup, tmp_path / "campus" / "skp_copy", **NO_SLEEP)
    assert copy == tmp_path / "campus" / "skp_copy" / "M - CHECKPOINT-17.skp"
    assert copy.read_bytes() == b"skp-bytes"                       # the .skp, not the .skb
    assert listing(backup) == before                               # nothing written beside the backup
    assert sorted(p.name for p in copy.parent.iterdir()) == [copy.name]


def test_a_copy_whose_hash_is_not_the_frozen_one_is_refused_and_leaves_nothing(tmp_path):
    backup = backup_folder(tmp_path, skp=b"changed since the freeze")
    dest = tmp_path / "campus" / "skp_copy"
    with pytest.raises(skp_check.BackupMismatch) as raised:
        skp_check.verified_copy(frozen(), backup, dest, **NO_SLEEP)
    assert sha(b"skp-bytes") in str(raised.value) and sha(b"changed since the freeze") in str(raised.value)
    assert list(dest.iterdir()) == []                              # not even a partial file


def test_a_wrong_copy_left_in_the_folder_is_deleted_even_when_the_backup_fails_too(tmp_path):
    backup = backup_folder(tmp_path, skp=b"changed since the freeze")
    dest = tmp_path / "skp_copy"
    dest.mkdir()
    (dest / "M - CHECKPOINT-17.skp").write_bytes(b"an old copy")
    with pytest.raises(skp_check.BackupMismatch):
        skp_check.verified_copy(frozen(), backup, dest, **NO_SLEEP)
    assert list(dest.iterdir()) == []                              # nothing unverified left to be opened


def test_a_good_copy_is_reused_without_touching_the_backup(tmp_path):
    backup = backup_folder(tmp_path)
    dest = tmp_path / "skp_copy"
    first = skp_check.verified_copy(frozen(), backup, dest, **NO_SLEEP)
    (backup / "M - CHECKPOINT-17.skp").unlink()                    # the backup is out of reach now
    assert skp_check.verified_copy(frozen(), backup, dest, **NO_SLEEP) == first


def test_a_copy_that_does_not_match_is_made_again(tmp_path):
    backup = backup_folder(tmp_path)
    dest = tmp_path / "skp_copy"
    dest.mkdir()
    (dest / "M - CHECKPOINT-17.skp").write_bytes(b"half a file")
    copy = skp_check.verified_copy(frozen(), backup, dest, **NO_SLEEP)
    assert copy.read_bytes() == b"skp-bytes"


def test_the_backup_file_is_found_by_the_name_in_source_json(tmp_path):
    backup = backup_folder(tmp_path)
    (backup / "Other.skp").write_bytes(b"other")
    source = frozen()
    source["backup"]["Other.skp"] = {"sha256": sha(b"other")}
    with pytest.raises(ValueError, match="more than one .skp"):
        skp_check.verified_copy(source, backup, tmp_path / "d", **NO_SLEEP)
    copy = skp_check.verified_copy(source, backup, tmp_path / "d", name="Other.skp", **NO_SLEEP)
    assert copy.read_bytes() == b"other"
    with pytest.raises(ValueError, match="no .skp"):
        skp_check.verified_copy({"backup": {"x.skb": {"sha256": "0"}}}, backup, tmp_path / "e", **NO_SLEEP)


def test_a_backup_file_that_is_not_there_is_an_error_not_a_guess(tmp_path):
    backup = backup_folder(tmp_path)
    (backup / "M - CHECKPOINT-17.skp").unlink()
    with pytest.raises(FileNotFoundError):
        skp_check.verified_copy(frozen(), backup, tmp_path / "skp_copy", **NO_SLEEP)


def test_the_master_model_is_never_opened_and_no_output_goes_beside_the_backup(tmp_path):
    master = tmp_path / "UC" / "02-SKETCHUP" / "current"
    master.mkdir(parents=True)
    (master / "M - CHECKPOINT-17.skp").write_bytes(b"skp-bytes")
    with pytest.raises(ValueError, match="master"):
        skp_check.verified_copy(frozen(), master, tmp_path / "skp_copy", **NO_SLEEP)
    backup = backup_folder(tmp_path)
    with pytest.raises(ValueError, match="inside the backup"):
        skp_check.verified_copy(frozen(), backup, backup / "skp_copy", **NO_SLEEP)
    assert not (backup / "skp_copy").exists()


# ----------------------------------------------------------------- the walk in a child process

FAKE_WALK = ("import json, sys; skp, flag, out = sys.argv[1:4]; "
             "json.dump({'path': skp, 'flag': flag, 'root': {}}, open(out, 'w'))")


def child(code: str):
    return [sys.executable, "-c", code]


def test_the_walk_runs_in_a_child_process_that_is_given_the_copy_and_an_output_path(tmp_path):
    walk = skp_check.run_walk(tmp_path / "m.skp", tmp_path / "walk.json", argv=child(FAKE_WALK),
                              min_free_commit_mb=0)
    assert (walk["path"], walk["flag"]) == (str(tmp_path / "m.skp"), "--out")
    assert json.loads((tmp_path / "walk.json").read_text(encoding="utf-8")) == walk | {}


def test_a_child_that_fails_is_reported_with_what_it_said(tmp_path):
    code = "import sys; print('SketchUp could not open it', file=sys.stderr); sys.exit(2)"
    with pytest.raises(skp_check.WalkFailed, match=r"exit code 2.*SketchUp could not open it"):
        skp_check.run_walk(tmp_path / "m.skp", tmp_path / "walk.json", argv=child(code),
                           min_free_commit_mb=0)


def test_a_child_that_writes_nothing_is_a_failure_too(tmp_path):
    with pytest.raises(skp_check.WalkFailed, match="wrote no walk"):
        skp_check.run_walk(tmp_path / "m.skp", tmp_path / "walk.json", argv=child("pass"),
                           min_free_commit_mb=0)


def test_a_stale_walk_file_is_not_mistaken_for_a_new_one(tmp_path):
    (tmp_path / "walk.json").write_text('{"stale": true}', encoding="utf-8")
    with pytest.raises(skp_check.WalkFailed, match="wrote no walk"):
        skp_check.run_walk(tmp_path / "m.skp", tmp_path / "walk.json", argv=child("pass"),
                           min_free_commit_mb=0)


def test_a_child_that_runs_too_long_is_killed(tmp_path):
    pid_file = tmp_path / "pid"
    code = (f"import os, time; open({str(pid_file)!r}, 'w').write(str(os.getpid())); time.sleep(60)")
    with pytest.raises(skp_check.WalkFailed, match="timed out after 1 s"):
        skp_check.run_walk(tmp_path / "m.skp", tmp_path / "walk.json", argv=child(code),
                           timeout_s=1, min_free_commit_mb=0)
    pid = pid_file.read_text()
    if sys.platform == "win32":
        listed = subprocess.run(["tasklist", "/FI", f"PID eq {pid}", "/NH"], capture_output=True,
                                text=True).stdout
        assert pid not in listed


@pytest.mark.skipif(skp_reader.available_commit_mb() is None, reason="needs Windows' commit figures")
def test_the_walk_is_not_started_when_the_machine_has_too_little_memory_to_give(tmp_path):
    with pytest.raises(skp_check.NotEnoughMemory, match="commit"):
        skp_check.run_walk(tmp_path / "m.skp", tmp_path / "walk.json", argv=child(FAKE_WALK),
                           min_free_commit_mb=10 ** 9)
    assert not (tmp_path / "walk.json").exists()


def test_the_default_child_is_the_readers_own_command_line():
    argv = skp_check.walk_argv()
    assert argv[:3] == [sys.executable, "-m", "engine.io.skp_reader"]


# ----------------------------------------------------------------- the whole check, no SketchUp


def floor_walk(*floors):
    """A walk with one top-level floor group per `(name, faces, area, bbox)`, its faces two levels down."""
    return walk_of(*(node(name, children=[node("minecraft_a_-1", children=[
        node("", faces=faces, area=area, bbox=bbox)])]) for name, faces, area, bbox in floors))


def freeze(tmp_path, rows, backup=None):
    """A `source.json` for `rows` -- `(group, x0, y0, x1, y1)` -- with the snapshots it points to."""
    backup = backup or backup_folder(tmp_path)
    manifest, snapshots = [], []
    for group, x0, y0, x1, y1 in rows:
        folder = write_obj(tmp_path / "snapshots" / group, group, x0, y0, x1, y1)
        manifest.append({"file": f"{group}.obj", "tris": 2, "group": group})
        snapshots.append({"file": f"{group}.obj", "group": group, "tris": 2, "dir": str(folder),
                          "sha256": "0" * 64})
    source = {"created": "2026-10-03T19:12:52+08:00", "manifest": manifest, "snapshots": snapshots,
              **frozen(), "totals": {"files": len(rows), "tris": 2 * len(rows)}}
    path = tmp_path / "campus" / "source.json"
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(source), encoding="utf-8")
    return path, backup


class Walker:
    """A stand-in for the child process: remembers which model it was given, returns `walk`."""

    def __init__(self, walk):
        self.walk, self.models = walk, []

    def __call__(self, skp, out_json):
        self.models.append(Path(skp))
        return self.walk


def run_check(tmp_path, rows, walk, **kw):
    source, backup = freeze(tmp_path, rows)
    walker = Walker(walk)
    report = skp_check.check_source(source, backup, tmp_path / "campus", walker=walker,
                                    interval_s=0, sleep=lambda s: None, **kw)
    return report, walker, backup


def test_the_check_opens_only_the_verified_copy_and_writes_the_report(tmp_path):
    rows = [("A_Floor", 0, 0, 30, 10), ("B_Floor", 100, 0, 120, 10)]
    walk = floor_walk(("A Floor", 5, 300.0, box(0, 0, 30, 10)), ("B Floor", 3, 200.4, box(100, 0, 120, 10)))
    backup = backup_folder(tmp_path)
    source, _ = freeze(tmp_path, rows, backup)
    before = listing(backup)
    walker = Walker(walk)
    report = skp_check.check_source(source, backup, tmp_path / "campus", walker=walker, interval_s=0,
                                    sleep=lambda s: None)
    copy = tmp_path / "campus" / "skp_copy" / "M - CHECKPOINT-17.skp"
    assert walker.models == [copy]                                  # never the backup itself
    assert listing(backup) == before
    assert report["counts"] == {"files": 2, "matches": 2, "mismatches": 0, "ambiguous_files": 0,
                                "misses": 0, "sdk_only_units": 0, "paired_by_geometry": 0}
    on_disk = json.loads((tmp_path / "campus" / "skp_check.json").read_text(encoding="utf-8"))
    assert on_disk == json.loads(json.dumps(report))                # what was returned is what was written
    assert report["source"]["backup"] == "M - CHECKPOINT-17.skp"
    assert report["source"]["backup_sha256"] == sha(b"skp-bytes")
    assert report["source"]["created"] == "2026-10-03T19:12:52+08:00"
    assert report["source"]["copy"] == str(copy)
    assert [m["name"] for m in report["matches"]] == ["A_Floor", "B_Floor"]


def test_mismatches_missing_files_and_extra_groups_are_all_in_the_report(tmp_path):
    rows = [("A_Floor", 0, 0, 30, 10), ("B_Floor", 100, 0, 120, 10), ("C_Floor", 200, 0, 210, 10)]
    walk = floor_walk(("A Floor", 5, 300.0, box(0, 0, 30, 10)),
                      ("B Floor", 3, 215.0, box(100, 0, 120, 10)),          # 7.5 % too big
                      ("D Floor", 1, 9.0, box(0, 0, 3, 3)))
    report, _, _ = run_check(tmp_path, rows, walk)
    assert [m["name"] for m in report["matches"]] == ["A_Floor"]
    assert [m["name"] for m in report["mismatches"]] == ["B_Floor"]
    assert "area" in report["mismatches"][0]["reasons"][0]
    assert [m["name"] for m in report["misses"]] == ["C_Floor"]
    assert [u["key"] for u in report["sdk_only"]] == ["D_Floor"]
    assert (report["counts"]["matches"], report["counts"]["mismatches"], report["counts"]["misses"],
            report["counts"]["sdk_only_units"]) == (1, 1, 1, 1)


def test_the_bounding_box_tolerance_is_twice_the_print_step_measured_in_the_export(tmp_path):
    rows = [("A_Floor", 0, 24000, 30, 24244.2)]
    walk = floor_walk(("A Floor", 5, 30 * 244.2, box(0, 24000, 30, 24244.2)))
    report, _, _ = run_check(tmp_path, rows, walk)
    tolerance = report["tolerance"]
    assert tolerance["print_step_in"] == pytest.approx(0.1)
    assert tolerance["bbox_in"] == pytest.approx(0.2) and tolerance["area_fraction"] == 0.005
    assert tolerance["max_abs_coordinate"] == 24244.2
    small, _, _ = run_check(tmp_path / "small", [("A_Floor", 0, 0, 12.3456, 10)],
                            floor_walk(("A Floor", 5, 123.456, box(0, 0, 12.3456, 10))))
    assert small["tolerance"]["bbox_in"] == pytest.approx(0.0002)       # 12.3456: six digits, 0.0001
    pinned, _, _ = run_check(tmp_path / "pinned", [("A_Floor", 0, 0, 30, 10)],
                             floor_walk(("A Floor", 5, 300.0, box(0, 0, 30, 10))), bbox_tol=0.5)
    assert pinned["tolerance"]["bbox_in"] == 0.5


def test_the_export_s_precision_is_the_best_any_of_its_files_shows(tmp_path):
    """A file whose numbers happen to be round (`0`, `30`) says nothing about the exporter's digits:
    the precision is the most significant digits any file shows, not the first file's."""
    rows = [("A_Floor", 0, 0, 30, 10), ("B_Floor", 100, 24000, 130, 24244.2)]
    walk = floor_walk(("A Floor", 5, 300.0, box(0, 0, 30, 10)),
                      ("B Floor", 5, 30 * 244.2, box(100, 24000, 130, 24244.2)))
    report, _, _ = run_check(tmp_path, rows, walk)
    assert report["tolerance"]["sig_digits"] == 6
    assert report["tolerance"]["bbox_in"] == pytest.approx(0.2)


def test_what_the_sdk_left_out_as_hidden_is_counted_in_the_report(tmp_path):
    rows = [("A_Floor", 0, 0, 30, 10)]
    walk = floor_walk(("A Floor", 5, 300.0, box(0, 0, 30, 10)))
    walk["totals"].update(hidden_nodes=2, layer_hidden_nodes=1, hidden_faces=7, layer_hidden_faces=3)
    walk["root"]["skipped"] = [{"kind": "group", "name": "Old", "definition": None, "reason": "hidden"}]
    walk["root"]["children"][0]["skipped"] = [
        {"kind": "instance", "name": "Tree", "definition": "Tree#1", "reason": "layer"}]
    report, _, _ = run_check(tmp_path, rows, walk)
    hidden = report["hidden"]
    assert (hidden["hidden_nodes"], hidden["layer_hidden_nodes"], hidden["hidden_faces"],
            hidden["layer_hidden_faces"]) == (2, 1, 7, 3)
    assert hidden["layers_bound"] is True
    assert hidden["skipped"] == [
        {"path": "", "kind": "group", "name": "Old", "reason": "hidden"},
        {"path": "A Floor", "kind": "instance", "name": "Tree", "reason": "layer"}]


def test_the_report_says_how_far_apart_the_paired_files_are(tmp_path):
    rows = [("A_Floor", 0, 0, 30, 10), ("B_Floor", 100, 0, 120, 10)]
    walk = floor_walk(("A Floor", 5, 301.5, box(0, 0, 30.1, 10)), ("B Floor", 3, 200.0, box(100, 0, 120, 10)))
    report, _, _ = run_check(tmp_path, rows, walk)
    measured = report["measured"]
    assert measured["paired"] == 2
    assert measured["bbox_max_dev"]["max"] == pytest.approx(0.1)
    assert measured["area_rel"]["max"] == pytest.approx(0.005) and measured["area_rel"]["min"] == 0.0
    assert measured["area_more_in_backup"] == 1
    assert (measured["tris_backup"], measured["tris_export"], measured["tris_diff"]) == (16, 4, 12)


def test_the_sdk_facts_are_carried_into_the_report(tmp_path):
    rows = [("A_Floor", 0, 0, 30, 10)]
    walk = floor_walk(("A Floor", 5, 300.0, box(0, 0, 30, 10)))
    walk.update(peak_working_set_mb=1949.3, peak_commit_mb=2525.8)
    walk["totals"].update(groups=3, instances=1, faces=5)
    report, _, _ = run_check(tmp_path, rows, walk)
    sdk = report["sdk"]
    assert (sdk["api_version"], sdk["elapsed_s"], sdk["peak_working_set_mb"], sdk["peak_commit_mb"]) == (
        "14.2", 1.0, 1949.3, 2525.8)
    assert (sdk["totals"]["groups"], sdk["totals"]["faces"], sdk["units"]) == (3, 5, 1)


def test_the_check_refuses_the_master_and_an_output_folder_beside_the_backup(tmp_path):
    rows = [("A_Floor", 0, 0, 30, 10)]
    master = tmp_path / "UC" / "02-SKETCHUP" / "current"
    master.mkdir(parents=True)
    (master / "M - CHECKPOINT-17.skp").write_bytes(b"skp-bytes")
    source, backup = freeze(tmp_path, rows)
    walker = Walker(floor_walk(("A Floor", 5, 300.0, box(0, 0, 30, 10))))
    with pytest.raises(ValueError, match="master"):
        skp_check.check_source(source, master, tmp_path / "campus", walker=walker, interval_s=0,
                               sleep=lambda s: None)
    with pytest.raises(ValueError, match="inside the backup"):
        skp_check.check_source(source, backup, backup / "out", walker=walker, interval_s=0,
                               sleep=lambda s: None)
    assert walker.models == [] and not (backup / "out").exists()


def test_a_backup_that_changed_since_the_freeze_stops_the_check_before_anything_is_opened(tmp_path):
    rows = [("A_Floor", 0, 0, 30, 10)]
    source, backup = freeze(tmp_path, rows, backup_folder(tmp_path, skp=b"changed"))
    walker = Walker(floor_walk(("A Floor", 5, 300.0, box(0, 0, 30, 10))))
    with pytest.raises(skp_check.BackupMismatch):
        skp_check.check_source(source, backup, tmp_path / "campus", walker=walker, interval_s=0,
                               sleep=lambda s: None)
    assert walker.models == [] and not (tmp_path / "campus" / "skp_check.json").exists()


def test_an_old_report_is_not_left_behind_when_the_check_fails(tmp_path):
    rows = [("A_Floor", 0, 0, 30, 10)]
    source, backup = freeze(tmp_path, rows, backup_folder(tmp_path, skp=b"changed"))
    (tmp_path / "campus" / "skp_check.json").write_text('{"old": true}', encoding="utf-8")
    with pytest.raises(skp_check.BackupMismatch):
        skp_check.check_source(source, backup, tmp_path / "campus", walker=Walker({}), interval_s=0,
                               sleep=lambda s: None)
    assert not (tmp_path / "campus" / "skp_check.json").exists()


# --------------------------------------------------------------------------- the summary page


def test_the_summary_gives_the_counts_and_the_five_worst_mismatches_worst_first(tmp_path):
    rows = [(f"F{i}_Floor", 100 * i, 0, 100 * i + 20, 10) for i in range(8)] + [("Lost_Floor", 0, 50, 5, 55)]
    walk = floor_walk(*[(f"F{i} Floor", 3, 200.0 * (1 + 0.01 * i), box(100 * i, 0, 100 * i + 20, 10))
                        for i in range(8)])
    report, _, _ = run_check(tmp_path, rows, walk)
    text = skp_check.render_markdown(report)
    assert "| match | 1 |" in text and "| mismatch | 7 |" in text and "| miss | 1 |" in text
    table = [line for line in text.splitlines() if line.startswith("| F")]
    assert [line.split("|")[1].strip() for line in table] == [f"F{i}_Floor" for i in (7, 6, 5, 4, 3)]
    assert "Lost_Floor" in text and "M - CHECKPOINT-17.skp" in text and sha(b"skp-bytes")[:12] in text
    assert "In every mismatch the backup has MORE area than the export (+1.00 % to +7.00 %)." in text
    assert "the export has 32 triangles fewer" in text             # 8 paired floors x 4 more in the backup
    assert ("bounding boxes of the 8 paired files differ by at most 0 in "
            "(median 0 in; the tolerance is 2 in)") in text
    assert len(text.splitlines()) < 80                              # short, as asked


# ------------------------------------------------------------------------------ the command


def fake_report(**counts):
    base = {"files": 85, "matches": 56, "mismatches": 20, "ambiguous_files": 3, "misses": 1,
            "sdk_only_units": 0, "paired_by_geometry": 0}
    return {"counts": {**base, **counts}, "source": {"backup": "M.skp"}}


def test_campus_skp_check_hands_its_arguments_to_the_check_and_prints_the_counts(tmp_path, monkeypatch, capsys):
    from engine import cli
    seen = {}

    def check(source, backup, out, **kw):
        seen.update(source=source, backup=backup, out=out, **kw)
        return fake_report()

    monkeypatch.setattr(skp_check, "check_source", check)
    code = cli.main(["campus-skp-check", "--source", str(tmp_path / "s.json"), "--backup", str(tmp_path / "B"),
                     "--out", str(tmp_path / "out"), "--summary", str(tmp_path / "s.md"),
                     "--timeout-min", "5", "--min-free-commit-mb", "1000", "--name", "M.skp"])
    assert code == 0
    assert (seen["source"], seen["backup"], seen["out"]) == (
        tmp_path / "s.json", tmp_path / "B", tmp_path / "out")
    assert (seen["summary"], seen["name"], seen["timeout_s"], seen["min_free_commit_mb"]) == (
        tmp_path / "s.md", "M.skp", 300.0, 1000.0)
    printed = capsys.readouterr().out
    assert "85 files" in printed and "56 match" in printed and "20 mismatch" in printed
    assert "3 ambiguous" in printed and "1 miss" in printed and str(tmp_path / "out" / "skp_check.json") in printed


def test_campus_skp_check_defaults_follow_campus_freeze(monkeypatch):
    from engine import cli
    seen = {}
    monkeypatch.setattr(skp_check, "check_source", lambda source, backup, out, **kw: (
        seen.update(source=source, out=out, kw=kw), fake_report())[1])
    assert cli.main(["campus-skp-check", "--backup", "B"]) == 0
    assert (seen["source"], seen["out"]) == (Path("data/campus/source.json"), Path("data/campus"))
    assert seen["kw"].get("summary") is None and "timeout_s" not in seen["kw"]


@pytest.mark.parametrize("error", [skp_check.BackupMismatch("the copy changed"),
                                   skp_check.WalkFailed("it timed out"),
                                   skp_check.NotEnoughMemory("no commit left"),
                                   ValueError("refusing to open the master"),
                                   FileNotFoundError("no such backup")])
def test_campus_skp_check_reports_a_refusal_in_a_line_and_exits_2(monkeypatch, capsys, error):
    from engine import cli

    def check(*args, **kw):
        raise error

    monkeypatch.setattr(skp_check, "check_source", check)
    assert cli.main(["campus-skp-check", "--backup", "B"]) == 2
    err = capsys.readouterr().err
    assert err.startswith("error: ") and str(error) in err and "Traceback" not in err


def test_campus_skp_check_needs_the_backup_folder(capsys):
    from engine import cli
    with pytest.raises(SystemExit) as raised:
        cli.main(["campus-skp-check"])
    assert raised.value.code == 2 and "--backup" in capsys.readouterr().err


def test_the_summary_is_written_where_it_was_asked_for(tmp_path):
    rows = [("A_Floor", 0, 0, 30, 10)]
    walk = floor_walk(("A Floor", 5, 300.0, box(0, 0, 30, 10)))
    out = tmp_path / "records" / "campus" / "skp-check.md"
    run_check(tmp_path, rows, walk, summary=out)
    assert out.read_text(encoding="utf-8").startswith("# SDK cross-check")


# ------------------------------------------------- a real model, a real child process (needs SketchUp)


@pytest.fixture
def sketchup():
    """Skip, saying why, when this machine has no usable SketchUp C API."""
    try:
        skp_reader.load_api()
    except SketchUpUnavailable as exc:
        pytest.skip(f"SketchUp C API unavailable: {exc}")


def floor_group(name, x, size, **extra):
    """A top-level group `name` with a `size` x `size` floor at `x`, two groups down like the real ones."""
    return {"name": name, "transform": translation(x, 0, 0), **extra, "groups": [
        {"name": "minecraft_concrete_white_-1", "groups": [{"faces": [square(0, 0, 0, size)]}]}]}


def freeze_real(tmp_path, scene, rows):
    """A backup folder holding a real `.skp` built from `scene`, and the freeze that describes it."""
    backup = tmp_path / "BACKUP"
    backup.mkdir()
    skp = backup / "M - CHECKPOINT-17.skp"
    build_scene(skp, scene)
    source, _ = freeze(tmp_path, rows, backup)
    data = json.loads(source.read_text(encoding="utf-8"))
    data["backup"] = {skp.name: {"sha256": sha(skp.read_bytes()), "size": skp.stat().st_size, "mtime": "x"}}
    source.write_text(json.dumps(data), encoding="utf-8")
    return source, backup


def test_a_real_model_is_walked_in_a_child_process_and_compared_with_the_export(tmp_path, sketchup):
    scene = {"groups": [floor_group("EDS 2nd Floor.obj", 100, 10),
                        floor_group("Main 3RD Floor.obj", 200, 40),
                        floor_group("Main 3RD Floor.obj", 300, 5)]}
    rows = [("EDS_2nd_Floor_obj", 100, 0, 110, 10), ("Main_3RD_Floor_obj", 200, 0, 240, 40),
            ("Main_3RD_Floor_obj1", 300, 0, 305, 5)]
    source, backup = freeze_real(tmp_path, scene, rows)
    before = listing(backup)
    report = skp_check.check_source(source, backup, tmp_path / "campus", min_free_commit_mb=0,
                                    interval_s=0, sleep=lambda s: None)
    assert listing(backup) == before
    assert report["counts"] == {"files": 3, "matches": 3, "mismatches": 0, "ambiguous_files": 0,
                                "misses": 0, "sdk_only_units": 0, "paired_by_geometry": 2}
    paired = {m["name"]: m["paired_by"] for m in report["matches"]}
    assert paired == {"EDS_2nd_Floor_obj": "name", "Main_3RD_Floor_obj": "geometry",
                      "Main_3RD_Floor_obj1": "geometry"}
    assert report["ambiguities"][0]["family"] == "Main_3RD_Floor_obj" and report["ambiguities"][0]["resolved"]
    assert report["sdk"]["totals"]["groups"] == 9 and report["sdk"]["peak_commit_mb"] > 1
    assert (tmp_path / "campus" / "skp_walk.json").is_file()


def test_what_is_hidden_in_a_real_model_is_left_out_and_counted(tmp_path, sketchup):
    scene = {"layers": {"Off": False}, "groups": [
        floor_group("EDS 2nd Floor.obj", 100, 10),
        floor_group("Old Floor.obj", 500, 99, hidden=True),
        floor_group("Tagged Floor.obj", 600, 99, layer="Off")]}
    rows = [("EDS_2nd_Floor_obj", 100, 0, 110, 10)]
    source, backup = freeze_real(tmp_path, scene, rows)
    report = skp_check.check_source(source, backup, tmp_path / "campus", min_free_commit_mb=0,
                                    interval_s=0, sleep=lambda s: None)
    assert report["counts"]["matches"] == 1 and report["counts"]["sdk_only_units"] == 0
    hidden = report["hidden"]
    assert (hidden["hidden_nodes"], hidden["layer_hidden_nodes"], hidden["layers_bound"]) == (1, 1, True)
    assert sorted((s["name"], s["reason"]) for s in hidden["skipped"]) == [
        ("Old Floor.obj", "hidden"), ("Tagged Floor.obj", "layer")]
