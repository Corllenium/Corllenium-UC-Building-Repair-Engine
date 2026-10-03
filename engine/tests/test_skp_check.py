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
    folder.mkdir()
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
