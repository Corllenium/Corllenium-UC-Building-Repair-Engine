from __future__ import annotations

from pathlib import Path
import pytest

from engine.campus.groups import (
    build_group_index,
    index_by_split,
    parse_group_paths,
    split_name,
)

FIXTURE_PATH = Path(__file__).parent / "fixtures" / "campus" / "clean_sample.obj"


def test_parse_group_paths_clean_sample():
    paths = parse_group_paths(FIXTURE_PATH)
    assert len(paths) == 4
    # Face 0: before any g line gets ()
    assert paths[0] == ()
    # Face 1: nested 3 deep gives a 3-tuple
    assert paths[1] == ("SubGroup", "MiddleGroup", "Outer_Level")
    assert len(paths[1]) == 3
    # Face 2: automatic name
    assert paths[2] == ("Group124",)
    # Face 3: floor name with space and dot
    assert paths[3] == ("Eds 2nd Floor.obj",)


def test_split_name_rules():
    # Face before any g line gets the path () and the split name unnamed
    assert split_name(()) == "unnamed"

    # Automatic name is skipped, Eds 2nd Floor.obj becomes Eds_2nd_Floor_obj
    assert split_name(("Group124", "Eds 2nd Floor.obj")) == "Eds_2nd_Floor_obj"
    assert split_name(("Mesh1", "minecraft_stone", "Eds 2nd Floor.obj")) == "Eds_2nd_Floor_obj"

    # Only automatic name -> falls back to the automatic name
    assert split_name(("Group124",)) == "Group124"

    # Eds 2nd Floor.obj with space and dot becomes Eds_2nd_Floor_obj
    assert split_name(("Eds 2nd Floor.obj",)) == "Eds_2nd_Floor_obj"

    # Outermost keyword group takes precedence
    assert split_name(("OtherGroup", "Main_3RD_Floor_obj1")) == "Main_3RD_Floor_obj1"
    assert split_name(("Lower_stair", "Upper_stair")) == "Upper_stair"


def test_index_by_split():
    paths = parse_group_paths(FIXTURE_PATH)
    counts = index_by_split(paths)

    # Face before any g line gets unnamed
    assert counts["unnamed"] == 1
    assert counts["Outer_Level"] == 1
    assert counts["Group124"] == 1
    assert counts["Eds_2nd_Floor_obj"] == 1
    assert sum(counts.values()) == 4


def test_build_group_index_structure():
    idx = build_group_index(FIXTURE_PATH)
    assert "paths" in idx
    assert "faces" in idx
    assert "split" in idx

    # Check paths list
    assert () in [tuple(p) for p in idx["paths"]]
    assert ("SubGroup", "MiddleGroup", "Outer_Level") in [tuple(p) for p in idx["paths"]]

    # Check faces run-length encoding
    total_faces = sum(r[2] for r in idx["faces"])
    assert total_faces == 4

    # Check split dictionary
    assert "unnamed" in idx["split"]
    assert idx["split"]["unnamed"]["tris"] == 1
    assert "Eds_2nd_Floor_obj" in idx["split"]
    assert idx["split"]["Eds_2nd_Floor_obj"]["tris"] == 1
