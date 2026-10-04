"""Tests for the campus inventory (P0 task 10), on synthetic meshes.

"X" in the brief's test names stands for a real building prefix here: `building_of` sends every other
prefix to SITE, and SITE groups have no level table.
"""
from __future__ import annotations

import numpy as np
import pytest

from engine.campus import inventory as inv
from engine.model import MeshData

# ------------------------------------------------------------------------------------------ helpers

# the 12 triangles of an axis-aligned box, outward normals (vertex order: 4 bottom, 4 top)
_BOX_FACES = [(0, 2, 1), (0, 3, 2), (4, 5, 6), (4, 6, 7), (0, 1, 5), (0, 5, 4),
              (1, 2, 6), (1, 6, 5), (2, 3, 7), (2, 7, 6), (3, 0, 4), (3, 4, 7)]


def box(x0, y0, z0, x1, y1, z1):
    verts = [(x0, y0, z0), (x1, y0, z0), (x1, y1, z0), (x0, y1, z0),
             (x0, y0, z1), (x1, y0, z1), (x1, y1, z1), (x0, y1, z1)]
    return verts, list(_BOX_FACES)


def slab(z, thickness=10.0, size=100.0, x=0.0, y=0.0):
    """A floor plate: bottom face at z, top face at z + thickness."""
    return box(x, y, z, x + size, y + size, z + thickness)


def mesh_of(name, pieces, material="m0", decimals=2):
    """One MeshData from (verts, faces) pieces."""
    verts, faces = [], []
    for v, f in pieces:
        base = len(verts)
        verts += list(v)
        faces += [tuple(base + i for i in tri) for tri in f]
    n = len(faces)
    return MeshData(
        name=name, positions=np.array(verts, float).reshape(-1, 3), uvs=np.zeros((0, 2)), normals=np.zeros((0, 3)),
        face_v=np.array(faces, np.int64).reshape(-1, 3), face_vt=np.full((n, 3), -1, np.int64),
        face_vn=np.full((n, 3), -1, np.int64), face_material=np.zeros(n, np.int64),
        face_line=np.arange(1, n + 1, dtype=np.int64), materials=[material], mtllib=None,
        coord_decimals=decimals, sig_digits=6)


def group(name, *pieces, **kw):
    """A GroupData for the inventory from boxes (default look "look0")."""
    looks = kw.pop("looks", {"m0": "look0"})
    return inv.load_group(name, mesh_of(name, pieces, decimals=kw.pop("decimals", 2)), looks=looks,
                          paths=kw.pop("paths", [0]), sha256=kw.pop("sha256", "sha-" + name), **kw)


# ------------------------------------------------------------------------------------------ the brief's tests

def test_three_stacked_slabs_make_three_levels_with_the_right_bases():
    groups = [group(f"CHTM_{n}_floor", slab(z)) for n, z in (("1st", 0), ("2nd", 200), ("3rd", 400))]
    levels = inv.build_inventory(groups)["buildings"]["CHTM"]["levels"]
    assert [lv["level"] for lv in levels] == ["L01", "L02", "L03"]
    assert [lv["base"] for lv in levels] == pytest.approx([0, 200, 400], abs=0.5)
    assert [lv["slab"]["top"] for lv in levels] == pytest.approx([10, 210, 410], abs=0.5)
    assert [lv["top"] for lv in levels] == pytest.approx([200, 400, 410], abs=0.5)   # next base; the roof's highest face
    assert [lv["tris"] for lv in levels] == [12, 12, 12]


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


def test_a_group_holding_two_slabs_gets_a_split_proposal_with_face_counts_per_band():
    both = group("CHTM_two_floors", slab(0), slab(200))
    result = inv.build_inventory([both])
    (proposal,) = result["proposals"]
    assert proposal["group"] == "CHTM_two_floors"
    assert [(part["level"], part["tris"]) for part in proposal["parts"]] == [("L01", 12), ("L02", 12)]
    assert sum(part["tris"] for part in proposal["parts"]) == both.tris          # no triangle is cut
    units = {u["unit"]: u for u in result["units"]}
    assert [m["faces"] for m in units["CHTM-L01"]["members"]] == ["band 1"]       # "band k" is the level number
    assert [m["faces"] for m in units["CHTM-L02"]["members"]] == ["band 2"]
    assert units["CHTM-L02"]["members"][0]["tris"] == 12
    assert units["CHTM-L02"]["members"][0]["z_range"][0] == pytest.approx(199, abs=1.5)   # faces with lo <= z < hi
    assert units["CHTM-L02"]["members"][0]["z_range"][1] is None
    assert any(f["kind"] == "split" and f["group"] == "CHTM_two_floors" and f["parts"] == 2
               for f in result["flags"])


def test_a_stairs_group_spanning_two_levels_is_an_element_unit_not_a_split():
    floors = [group(f"CHTM_{n}_floor", slab(z)) for n, z in (("1st", 0), ("2nd", 200))]
    stairs = group("CHTM_main_stairs", box(0, 0, 10, 5, 5, 60), box(0, 0, 210, 5, 5, 260))   # one flight per floor
    result = inv.build_inventory(floors + [stairs])
    unit = next(u for u in result["units"] if u["unit"] == "CHTM-E-CHTM_main_stairs")
    assert (unit["type"], unit["level"], unit["spans"]) == ("element", None, ["L01", "L02"])
    assert unit["members"][0]["faces"] == "all" and unit["tris"] == 24
    assert result["proposals"] == []
    assert [u["tris"] for u in result["units"] if u["type"] == "floor"] == [12, 12]   # the stairs add no floor tris


def test_a_group_with_no_building_prefix_is_a_site_unit():
    result = inv.build_inventory([group("ROAD_harrison_front", slab(0)), group("Group124", slab(0))])
    assert {u["unit"]: u["type"] for u in result["units"]} == {"SITE-Group124": "site", "SITE-ROAD_harrison_front": "site"}
    assert result["buildings"] == {}


def test_floor_units_know_their_neighbours_and_start_unconfirmed():
    groups = [group(f"CHTM_{n}_floor", slab(z)) for n, z in (("1st", 0), ("2nd", 200), ("3rd", 400))]
    units = {u["unit"]: u for u in inv.build_inventory(groups)["units"]}
    assert units["CHTM-L02"]["neighbours"] == {"below": "CHTM-L01", "above": "CHTM-L03"}
    assert units["CHTM-L01"]["neighbours"]["below"] is None and units["CHTM-L03"]["neighbours"]["above"] is None
    assert all(u["confirmed_by_owner"] is False for u in units.values())
    m = units["CHTM-L01"]["members"][0]
    assert (m["group"], m["paths"], m["sha256"], m["faces"]) == ("CHTM_1st_floor", [0], "sha-CHTM_1st_floor", "all")


# ------------------------------------------------------------------------------------------ duplicates

def strip(n, z=0.0, dx=0.0, flip=False, start=0):
    """n distinct flat triangles side by side (up-facing unless flipped); `start` skips the first triangles."""
    verts, faces = [], []
    for i in range(start, start + n):
        a, b, c = (i * 10 + dx, 0.0, z), (i * 10 + 10 + dx, 0.0, z), (i * 10 + dx, 10.0, z)
        k = len(verts)
        verts += [a, b, c]
        faces.append((k, k + 2, k + 1) if flip else (k, k + 1, k + 2))
    return verts, faces


def duplicates(*groups, **kw):
    return [f for f in inv.build_inventory(list(groups), **kw)["flags"] if f["kind"] == "duplicate"]


def test_two_groups_sharing_ninety_percent_of_their_faces_flag_a_duplicate_of_about_point_nine():
    a = group("PE_1st_floor", strip(100))
    b = group("PE_1st_floor_obj1", strip(90))                  # the same first 90 triangles, same look
    (flag,) = duplicates(a, b)
    assert set(flag["groups"]) == {"PE_1st_floor", "PE_1st_floor_obj1"}
    assert flag["jaccard"] == pytest.approx(0.9, abs=0.01)
    assert flag["percent"] == pytest.approx(90, abs=1)
    assert flag["shared"] == 90 and sorted(flag["faces"]) == [90, 100]
    assert flag["match"] == "exact" and flag["exact_jaccard"] == pytest.approx(0.9, abs=0.01)
    assert flag["decision"] is None                            # the owner's call, later


def test_the_flag_also_gives_the_share_of_the_smaller_group():
    a = group("PE_1st_floor", strip(100))                      # 90 shared + 10 of its own
    b = group("PE_1st_floor_obj1", strip(90), strip(10, start=500))
    (flag,) = duplicates(a, b)
    assert flag["jaccard"] == pytest.approx(90 / 110, abs=0.001)
    assert flag["of_smaller"] == pytest.approx(0.9, abs=0.001)


def test_a_copy_shifted_by_a_few_hundredths_of_an_inch_is_a_shifted_duplicate():
    a = group("Sciene_A_Floor_plan_2_obj", strip(100))
    b = group("Sciene_A_Floor_plan_2_obj1", strip(100, dx=0.03))   # Science A's obj1 copies sit 0.03 in off
    (flag,) = duplicates(a, b)
    assert flag["match"] == "shifted"
    assert flag["exact_jaccard"] == 0.0                        # nothing coincides at the print step
    assert flag["jaccard"] > 0.95


def test_a_flipped_copy_is_not_a_duplicate():
    # opposite-normal coincident faces are never duplicates (AGENTS.md section 4)
    assert duplicates(group("PE_1st_floor", strip(100)), group("PE_1st_floor_obj1", strip(100, flip=True))) == []


def test_groups_that_share_little_or_sit_in_different_buildings_are_not_flagged():
    a = group("PE_1st_floor", strip(100))
    assert duplicates(a, group("PE_1st_floor_obj1", strip(20), strip(80, start=500))) == []   # 20 / 180 = 0.11
    assert duplicates(a, group("BRS_1st_floor", strip(100))) == []                              # other building
