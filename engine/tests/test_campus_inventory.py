"""Tests for the campus inventory (P0 task 10), on synthetic meshes.

"X" in the brief's test names stands for a real building prefix here: `building_of` sends every other
prefix to SITE, and SITE groups have no level table.
"""
from __future__ import annotations

import numpy as np
import pytest

from engine.campus import inventory as inv


@pytest.mark.parametrize("name, building", [
    ("CHTM_5th_floor", "CHTM"), ("Chtm_2nd_floor", "CHTM"), ("chtm_5ft_floor", "CHTM"),
    ("EDS_1st_Floor", "EDS"), ("Eds_10th_Floor_obj", "EDS"),
    ("BRS_9th_floor_obj1", "BRS"), ("BRS_ZONE", "BRS"),
    ("Gymnasium_5th_floor_and_roof", "GYMNASIUM"),
    ("Main_Infrustructure_1st_floor", "MAIN_INFRA"),      # the longer prefix wins over `Main`
    ("Main_Infrustructure_Building", "MAIN_INFRA"),
    ("MAIN_BUILDING", "MAIN"), ("Main_3RD_Floor_obj1", "MAIN"),
    ("PE_GROUND_landscaping", "PE"),
    ("Sciene_A_Floor_plan_2_obj", "SCIENCE_A"),
    ("Architecture_dep_2nd_Floor_obj", "ARCHITECTURE"), ("ARCHITECTURE_BUILDING", "ARCHITECTURE"),
    ("BRIDGE_ZONE", "SITE"), ("ROAD_harrison_front", "SITE"), ("Group124", "SITE"), ("unnamed", "SITE"),
    ("Side_walk_harrision_Main_building_2", "SITE"),
    ("PEOPLE_walkway", "SITE"),                              # a prefix must end at an underscore
])
def test_building_prefix_table(name, building):
    assert inv.building_of(name) == building


@pytest.mark.parametrize("name, number", [
    ("BRS_9th_floor_obj1", 9), ("EDS_1st_Floor", 1), ("Eds_5ft_Floor_obj", 5), ("chtm_5ft_floor", 5),
    ("Main_3RD_Floor_obj1", 3), ("Sciene_A_Floor_plan_2_obj1", 2), ("X_Floor 4", 4), ("X_plan 2", 2),
    ("Gymnasium_5th_floor_and_roof", 5), ("CHTM_1st_floor_zone", 1), ("Architecture_dep_7th_Floor_obj", 7),
    ("BRS_ZONE", None), ("BRS_GROUND_FLOOR_PATHWAY_obj", None), ("Group124", None), ("MAIN_BUILDING", None),
])
def test_floor_number_from_the_name(name, number):
    assert inv.floor_number(name) == number
