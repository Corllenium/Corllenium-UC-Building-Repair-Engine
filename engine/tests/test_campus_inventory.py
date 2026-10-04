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
