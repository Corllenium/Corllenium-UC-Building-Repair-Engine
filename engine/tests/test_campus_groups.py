from __future__ import annotations

from pathlib import Path
import pytest

from engine.campus.groups import (
    build_group_index,
    index_by_split,
    parse_group_line,
    parse_group_paths,
    split_name,
)

FIXTURE_PATH = Path(__file__).parent / "fixtures" / "campus" / "clean_sample.obj"


def test_parse_group_paths_clean_sample():
    paths = parse_group_paths(FIXTURE_PATH)
    assert len(paths) == 6
    # Face 0: before any g line gets ()
    assert paths[0] == ()
    # Faces 1-2: 2 faces under one g (Mesh7587), stores tokens[1:-1]
    assert paths[1] == ("minecraft_quartz_block_side__1_29", "Eds_2nd_Floor_obj")
    assert paths[2] == ("minecraft_quartz_block_side__1_29", "Eds_2nd_Floor_obj")
    # Face 3: automatic name Group124
    assert paths[3] == ("minecraft_quartz_block_side__1_29", "Group124")
    # Face 4: nested 3 deep
    assert paths[4] == ("minecraft_quartz_block_side__1_29", "SubGroup", "MiddleGroup", "Outer_Level")
    # Face 5: return to earlier path (Mesh7587)
    assert paths[5] == ("minecraft_quartz_block_side__1_29", "Eds_2nd_Floor_obj")


def test_parse_group_line_fuller_path():
    # Slot after Mesh# is preserved in stored path (tokens[1:-1])
    assert parse_group_line("g Mesh8296 BRIDGE BRIDGE_ZONE Model") == ("BRIDGE", "BRIDGE_ZONE")
    assert parse_group_line(
        "g Mesh7587 minecraft_quartz_block_side__1_29 Eds_2nd_Floor_obj Model"
    ) == ("minecraft_quartz_block_side__1_29", "Eds_2nd_Floor_obj")


def test_parse_group_paths_missing_file_raises():
    # parse_group_paths must raise FileNotFoundError for missing path (str or Path)
    with pytest.raises(FileNotFoundError):
        parse_group_paths("missing_sample_file_12345.obj")
    with pytest.raises(FileNotFoundError):
        parse_group_paths(Path("missing_sample_file_12345.obj"))


def test_split_name_rules():
    # Face before any g line gets the path () and the split name unnamed
    assert split_name(()) == "unnamed"

    # Note 1: assert the naming rule exactly
    # 1. Outermost keyword group wins over non-keyword group
    assert split_name(("Foo_floor", "Bar")) == "Foo_floor"
    # 2. Outermost named group wins over automatic name
    assert split_name(("Lobby", "Group5")) == "Lobby"
    # 3. Fallback when all are automatic: outermost wins
    assert split_name(("Group5", "Group7")) == "Group7"

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

    # Owner skip behavior on SketchUp export paths with slot after Mesh#:
    assert split_name(("BRIDGE", "BRIDGE_ZONE"), skip_owner_slot=True) == "BRIDGE_ZONE"
    assert split_name(("Architecture_1st_floor", "ARCHITECTURE_BUILDING"), skip_owner_slot=True) == "ARCHITECTURE_BUILDING"
    assert split_name(("CHTM_12th_floor_obj",), skip_owner_slot=True) == "unnamed"


def test_index_by_split():
    paths = parse_group_paths(FIXTURE_PATH)
    counts = index_by_split(paths)

    # Note 5: index_by_split returns dict[str, int]
    assert isinstance(counts, dict)
    assert all(type(v) is int for v in counts.values())

    # Face before any g line gets unnamed
    assert counts["unnamed"] == 1
    assert counts["Outer_Level"] == 1
    assert counts["Group124"] == 1
    # 2 faces from initial g line + 1 face from return to earlier path
    assert counts["Eds_2nd_Floor_obj"] == 3
    assert sum(counts.values()) == 6


def test_build_group_index_structure():
    idx = build_group_index(FIXTURE_PATH)
    assert "paths" in idx
    assert "faces" in idx
    assert "split" in idx

    # Check paths list
    assert () in [tuple(p) for p in idx["paths"]]
    assert ("minecraft_quartz_block_side__1_29", "Eds_2nd_Floor_obj") in [tuple(p) for p in idx["paths"]]

    # Note 2: assert faces runs and split[..]["paths"] exactly
    # Runs: [path_id, first_face, count]
    # Run 0: [0, 0, 1] (unnamed)
    # Run 1: [1, 1, 2] (Eds_2nd_Floor_obj, 2 faces)
    # Run 2: [2, 3, 1] (Group124, 1 face)
    # Run 3: [3, 4, 1] (Outer_Level, 1 face)
    # Run 4: [1, 5, 1] (Eds_2nd_Floor_obj return to earlier path, 1 face)
    assert idx["faces"] == [[0, 0, 1], [1, 1, 2], [2, 3, 1], [3, 4, 1], [1, 5, 1]]

    total_faces = sum(r[2] for r in idx["faces"])
    assert total_faces == 6

    # Check split dictionary
    assert idx["split"]["unnamed"]["paths"] == [0]
    assert idx["split"]["unnamed"]["tris"] == 1
    assert idx["split"]["Eds_2nd_Floor_obj"]["paths"] == [1]
    assert idx["split"]["Eds_2nd_Floor_obj"]["tris"] == 3
    assert idx["split"]["Group124"]["paths"] == [2]
    assert idx["split"]["Group124"]["tris"] == 1
    assert idx["split"]["Outer_Level"]["paths"] == [3]
    assert idx["split"]["Outer_Level"]["tris"] == 1
