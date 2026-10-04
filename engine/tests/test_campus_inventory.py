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
    """A GroupData for the inventory from boxes (default material "m0", look "look0")."""
    material = kw.pop("material", "m0")
    looks = kw.pop("looks", {"m0": "look0"})
    return inv.load_group(name, mesh_of(name, pieces, material=material, decimals=kw.pop("decimals", 2)),
                          looks=looks, paths=kw.pop("paths", [0]), sha256=kw.pop("sha256", "sha-" + name), **kw)


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


# ------------------------------------------------------------------------------------------ misnamed levels

def stack(prefix, names, step=200):
    """One single-slab group per name, bottom to top: `{prefix}_{name}_floor` at z = 0, step, 2 step, ..."""
    return [group(f"{prefix}_{n}_floor", slab(i * step)) for i, n in enumerate(names)]


def flags_of(result, kind):
    return [f for f in result["flags"] if f["kind"] == kind]


def test_a_group_named_ninth_that_sits_in_the_eighth_band_is_flagged_misnamed():
    # the eighth band holds the group named 9th (BRS_9th_floor_obj1 in CHECKPOINT-17)
    result = inv.build_inventory(stack("BRS", ["1st", "2nd", "3rd", "4th", "5th", "6th", "7th", "9th"]))
    (flag,) = flags_of(result, "misnamed")
    assert flag["group"] == "BRS_9th_floor"
    assert (flag["named"], flag["assigned"], flag["units"]) == (9, "L08", ["BRS-L08"])
    assert flag["band"] == pytest.approx([1400, 1410], abs=0.5)          # the level's base and top
    assert result["buildings"]["BRS"]["anchor"]["offset"] == 0           # one odd name does not move the numbering


def test_names_that_all_agree_on_an_offset_number_the_levels_from_it_instead_of_flagging_every_group():
    # Science A: the floors are named 2..6 and the first floor is not in these groups
    result = inv.build_inventory([group(f"Sciene_A_Floor_plan_{n}_obj", slab(i * 200)) for i, n in enumerate((2, 3, 4))])
    assert [lv["level"] for lv in result["buildings"]["SCIENCE_A"]["levels"]] == ["L02", "L03", "L04"]
    assert result["buildings"]["SCIENCE_A"]["anchor"] == {"offset": 1, "votes": 3, "agree": 3}
    assert flags_of(result, "misnamed") == []
    assert [u["unit"] for u in result["units"]] == ["SCIENCE_A-L02", "SCIENCE_A-L03", "SCIENCE_A-L04"]


def test_a_tie_between_offsets_keeps_the_numbering_from_the_lowest_band():
    result = inv.build_inventory(stack("CHTM", ["1st", "2nd", "4th", "5th"]))
    assert result["buildings"]["CHTM"]["anchor"]["offset"] == 0
    assert sorted(f["group"] for f in flags_of(result, "misnamed")) == ["CHTM_4th_floor", "CHTM_5th_floor"]


# ------------------------------------------------------------------------------------------ missing levels

def test_a_missing_middle_level_is_flagged_missing():
    result = inv.build_inventory(stack("CHTM", ["1st", "2nd", "4th", "5th"]))      # nobody is named 3rd
    (flag,) = flags_of(result, "missing")
    assert (flag["building"], flag["level"]) == ("CHTM", "L03")
    assert flag["occupied_by"] == ["CHTM_4th_floor"]      # the geometry has a band there, under another name


def test_a_building_whose_floors_start_above_the_first_has_its_first_level_missing():
    result = inv.build_inventory([group(f"Sciene_A_Floor_plan_{n}_obj", slab(i * 200)) for i, n in enumerate((2, 3, 4))])
    (flag,) = flags_of(result, "missing")
    assert (flag["building"], flag["level"], flag["occupied_by"]) == ("SCIENCE_A", "L01", [])


def test_a_complete_stack_has_nothing_missing():
    assert flags_of(inv.build_inventory(stack("CHTM", ["1st", "2nd", "3rd"])), "missing") == []


# ------------------------------------------------------------------------------------------ levels, footprints, coverage

def test_a_group_below_the_first_slab_is_the_ground_level_and_the_first_slab_starts_the_second():
    columns = group("BRS_1st_floor", box(0, 0, 0, 5, 5, 190), box(50, 50, 0, 55, 55, 190))   # no slab: just columns
    groups = [columns] + [group(f"BRS_{n}_floor", slab(200 * (i + 1))) for i, n in enumerate(("2nd", "3rd"))]
    levels = inv.build_inventory(groups)["buildings"]["BRS"]["levels"]
    assert [lv["level"] for lv in levels] == ["L01", "L02", "L03"]
    assert [lv["base"] for lv in levels] == pytest.approx([0, 200, 400], abs=0.5)
    assert levels[0]["slab"] is None and levels[1]["slab"]["bottom"] == pytest.approx(200, abs=0.5)


def test_a_slab_whose_band_no_group_occupies_is_not_a_level():
    # a mezzanine plate inside the 2nd-floor group: 12 of its 144 triangles, so the band above it holds none
    walls = [box(0, 0, 410 + 2 * i, 3, 3, 411 + 2 * i) for i in range(10)]
    second = group("BRS_2nd_floor", slab(400), slab(600), *walls)
    groups = [group("BRS_1st_floor", slab(0)), second, group("BRS_3rd_floor", slab(800))]
    levels = inv.build_inventory(groups)["buildings"]["BRS"]["levels"]
    assert [lv["base"] for lv in levels] == pytest.approx([0, 400, 800], abs=0.5)      # no level at 600


def test_a_group_lying_mostly_inside_another_building_is_flagged():
    # Science A's floors sit inside the big box of the infrastructure group; the infrastructure's "1st floor"
    # lies exactly in Science A (CHECKPOINT-17: Main_Infrustructure_1st_floor)
    sci = [group(f"Sciene_A_Floor_plan_{n}_obj", slab(200 * i, size=300)) for i, n in enumerate((1, 2))]
    infra = group("Main_Infrustructure_Building", slab(0, size=880, x=-600, y=-600))     # box -600..280 covers 87 %
    wrong = group("Main_Infrustructure_1st_floor", slab(0, size=300))
    (flag,) = flags_of(inv.build_inventory(sci + [infra, wrong]), "footprint")
    assert (flag["group"], flag["building"], flag["other"]) == ("Main_Infrustructure_1st_floor", "MAIN_INFRA", "SCIENCE_A")
    assert flag["fraction_other"] == pytest.approx(1.0) and flag["fraction_own"] == pytest.approx((280 / 300) ** 2, abs=0.01)


def test_every_group_lands_in_exactly_one_unit_or_proposal():
    groups = (stack("CHTM", ["1st", "2nd"]) + [group("CHTM_two_floors", slab(0), slab(200)),
                                               group("CHTM_main_stairs", box(0, 0, 10, 5, 5, 60), box(0, 0, 210, 5, 5, 260)),
                                               group("Group124", slab(0))])
    cov = inv.build_inventory(groups)["coverage"]
    assert cov["groups"] == 5 and cov["whole"] == 4 and cov["split"] == 1
    assert cov["tris"] == cov["unit_tris"] == sum(g.tris for g in groups) and cov["ok"] is True


# ------------------------------------------------------------------------------------------ files and the CLI

def write_obj(path, *pieces):
    verts, faces = [], []
    for v, f in pieces:
        base = len(verts)
        verts += list(v)
        faces += [tuple(base + i + 1 for i in tri) for tri in f]
    lines = ["mtllib x.mtl", "o piece"] + [f"v {x:.2f} {y:.2f} {z:.2f}" for x, y, z in verts] + ["usemtl m0"]
    lines += [f"f {a} {b} {c}" for a, b, c in faces]
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")


def tiny_campus(tmp_path, tris_in_index=None):
    """Three CHTM floors named 2nd, 3rd, 4th (so L01 is missing) as split snapshots plus the three JSON inputs."""
    import json
    snaps, split = [], {}
    for k, (name, z) in enumerate((("CHTM_2nd_floor", 0), ("CHTM_3rd_floor", 200), ("CHTM_4th_floor", 400))):
        d = tmp_path / "snaps" / f"s{k}"
        d.mkdir(parents=True)
        write_obj(d / f"{name}.obj", slab(z))
        snaps.append({"file": f"{name}.obj", "group": name, "tris": 12, "dir": str(d), "sha256": f"sha{k}"})
        split[name] = {"tris": (tris_in_index or {}).get(name, 12), "paths": [k, k + 10]}
    src = tmp_path / "source.json"
    src.write_text(json.dumps({"created": "t", "snapshots": snaps, "clean_obj": {"sha256": "abc"}}), encoding="utf-8")
    idx = tmp_path / "group_index.json"
    idx.write_text(json.dumps({"paths": [], "faces": [], "split": split}), encoding="utf-8")
    mat = tmp_path / "materials.json"
    mat.write_text(json.dumps({"materials": {"m0": {"look": "look0"}}, "looks": {"look0": ["m0"]}, "stats": {}}),
                   encoding="utf-8")
    return src, idx, mat


def test_the_cli_writes_the_draft_json_and_the_owner_readable_table(tmp_path, capsys):
    import json
    from engine.cli import main
    src, idx, mat = tiny_campus(tmp_path)
    out, md = tmp_path / "out" / "campus_map.draft.json", tmp_path / "rec" / "campus-map-draft.md"
    assert main(["campus-inventory", "--source", str(src), "--index", str(idx), "--materials", str(mat),
                 "--out", str(out), "--md", str(md)]) == 0
    data = json.loads(out.read_text(encoding="utf-8"))
    assert [u["unit"] for u in data["units"]] == ["CHTM-L02", "CHTM-L03", "CHTM-L04"]
    u = data["units"][1]
    assert u["members"] == [{"group": "CHTM_3rd_floor", "paths": [1, 11], "sha256": "sha1", "file": "CHTM_3rd_floor.obj",
                             "tris": 12, "faces": "all"}]
    assert (u["tris"], u["type"], u["level"], u["confirmed_by_owner"]) == (12, "floor", "L03", False)
    assert u["base"] == pytest.approx(200, abs=0.5) and u["slab"]["top"] == pytest.approx(210, abs=0.5)
    assert data["coverage"]["ok"] is True and data["source"]["splits"] == 3 and data["source"]["clean_obj_sha256"] == "abc"
    text = md.read_text(encoding="utf-8")
    assert "# Campus map draft" in text and "CHTM-L03" in text and "confirmed_by_owner" in text
    assert "| CHTM | L01 | nothing: no group, no band |" in text             # the missing level is in the flag tables
    printed = capsys.readouterr().out
    assert "3 splits" in printed and "missing 1" in printed


def test_the_cli_refuses_a_snapshot_whose_triangle_count_differs_from_the_index(tmp_path):
    from engine.cli import main
    src, idx, mat = tiny_campus(tmp_path, tris_in_index={"CHTM_3rd_floor": 99})
    with pytest.raises(ValueError, match="CHTM_3rd_floor"):
        main(["campus-inventory", "--source", str(src), "--index", str(idx), "--materials", str(mat),
              "--out", str(tmp_path / "o.json"), "--md", str(tmp_path / "o.md")])
    assert not (tmp_path / "o.json").exists()


def test_the_lowest_base_and_the_highest_top_are_the_lowest_and_highest_vertex_not_a_face_centre():
    tips = ([(0, 0, 0), (10, 0, 100), (0, 10, 100)], [(0, 1, 2)])          # a slanted piece: lowest vertex z 0, centre 66.7
    spire = ([(0, 0, 400), (10, 0, 500), (0, 10, 500)], [(0, 1, 2)])       # highest vertex z 500, centre 466.7
    groups = [group("BRS_1st_floor", tips), group("BRS_2nd_floor", slab(200)), group("BRS_3rd_floor", slab(400), spire)]
    levels = inv.build_inventory(groups)["buildings"]["BRS"]["levels"]
    assert [lv["level"] for lv in levels] == ["L01", "L02", "L03"]
    assert levels[0]["base"] == pytest.approx(0.0, abs=0.01)
    assert levels[2]["top"] == pytest.approx(500.0, abs=0.01)


def test_a_level_holding_floor_groups_with_different_numbers_is_flagged_as_shared():
    # the 4th floor has no slab the table can see (columns only), so it falls into the 3rd floor's band:
    # CHECKPOINT-17's CHTM_12th_floor_obj sits in the same level as CHTM_11th_floor_obj
    columns = group("CHTM_4th_floor", box(0, 0, 410, 5, 5, 590), box(50, 50, 410, 55, 55, 590))
    result = inv.build_inventory(stack("CHTM", ["1st", "2nd", "3rd"]) + [columns])
    (flag,) = flags_of(result, "shared")
    assert (flag["building"], flag["level"], flag["numbers"]) == ("CHTM", "L03", [3, 4])
    assert flag["groups"] == ["CHTM_3rd_floor", "CHTM_4th_floor"] and flag["units"] == ["CHTM-L03"]
    assert [f["group"] for f in flags_of(result, "misnamed")] == ["CHTM_4th_floor"]      # the same fact, seen from the group


def test_groups_with_the_same_floor_number_in_one_level_are_not_shared():
    result = inv.build_inventory(stack("BRS", ["1st", "2nd"]) + [group("BRS_2nd_floor_obj1", slab(200))])
    assert flags_of(result, "shared") == []


def test_the_table_lists_shared_levels_next_to_the_other_flags():
    columns = group("CHTM_4th_floor", box(0, 0, 410, 5, 5, 590), box(50, 50, 410, 55, 55, 590))
    text = inv.render_markdown(inv.build_inventory(stack("CHTM", ["1st", "2nd", "3rd"]) + [columns]))
    assert "### Levels shared by groups named for different floors" in text
    assert "| CHTM | L03 | 3, 4 | CHTM_3rd_floor, CHTM_4th_floor |" in text


# ------------------------------------------------------------------------------------------ the rules the real tables depend on
# Each of these four was changed from the brief because the real CHECKPOINT-17 data needed it (the review of
# P0-10 found that undoing any one of them left the suite green).

def stack_of(thickness, bottoms=(0, 200, 400), prefix="CHTM"):
    return [group(f"{prefix}_{n}_floor", slab(z, thickness=thickness))
            for n, z in zip(("1st", "2nd", "3rd", "4th"), bottoms)]


@pytest.mark.parametrize("thickness", [19.7, 39.4, 54.0])
def test_slabs_as_thick_as_ckpt17_has_them_make_levels(thickness):
    # half a block (19.7 in), a block (39.4 in: BRS, CHTM, EDS ...) and Science A plan_4's 54 in
    levels = inv.build_inventory(stack_of(thickness))["buildings"]["CHTM"]["levels"]
    assert [lv["base"] for lv in levels] == pytest.approx([0, 200, 400], abs=0.5)
    assert [lv["slab"]["top"] for lv in levels] == pytest.approx([thickness, 200 + thickness, 400 + thickness], abs=0.5)


def test_the_briefs_24_in_window_finds_no_slab_in_a_stack_of_block_thick_slabs():
    # why the default is 60: a slab bottom must be found up to a slab's thickness below its top
    assert len(inv.build_inventory(stack_of(39.4), inv.BRIEF_PARAMS)["buildings"]["CHTM"]["levels"]) == 1
    assert len(inv.build_inventory(stack_of(39.4))["buildings"]["CHTM"]["levels"]) == 3


def test_a_slab_with_a_second_underside_30_in_up_takes_the_lowest_underside_as_its_base():
    # BRS 5th floor and EDS 3rd floor: part of the slab's underside sits 30 in above the real bottom, with more
    # area than the real bottom has; the groups start at the lower one
    stepped = group("CHTM_2nd_floor", slab(200, thickness=39.4), box(200, 0, 230, 300, 150, 239.4))
    groups = [group("CHTM_1st_floor", slab(0, thickness=39.4)), stepped, group("CHTM_3rd_floor", slab(400, thickness=39.4))]
    levels = inv.build_inventory(groups)["buildings"]["CHTM"]["levels"]
    assert [lv["base"] for lv in levels] == pytest.approx([0, 200, 400], abs=0.5)
    assert levels[1]["slab"]["top"] == pytest.approx(239.4, abs=0.5)


def test_slab_pairs_39_in_apart_collapse_into_one_level_but_a_157_in_storey_stays_two():
    # Architecture's terraces step up every 39 in; the shortest real storey in CKPT17 is 157.5 in
    terraces = group("CHTM_1st_floor", box(0, 0, 0, 100, 100, 39), box(200, 0, 39, 300, 100, 78),
                     box(400, 0, 78, 500, 100, 117))
    groups = [terraces, group("CHTM_2nd_floor", slab(200)), group("CHTM_3rd_floor", slab(357.5))]
    result = inv.build_inventory(groups)
    levels = result["buildings"]["CHTM"]["levels"]
    assert [lv["level"] for lv in levels] == ["L01", "L02", "L03"]
    assert [lv["base"] for lv in levels] == pytest.approx([0, 200, 357.5], abs=0.5)
    assert result["proposals"] == []                       # the terraces are one floor group, not a split


def test_the_same_geometry_in_two_different_looks_is_not_a_duplicate():
    a = group("PE_1st_floor", strip(100), material="m0", looks={"m0": "look0"})
    b = group("PE_1st_floor_obj1", strip(100), material="m1", looks={"m1": "look1"})
    assert duplicates(a, b) == []


def test_two_material_names_with_one_look_key_are_one_look():
    # the fingerprint uses the look key from materials.json, never the material name or number
    a = group("PE_1st_floor", strip(100), material="m0", looks={"m0": "look0"})
    b = group("PE_1st_floor_obj1", strip(100), material="m7", looks={"m7": "look0"})
    (flag,) = duplicates(a, b)
    assert flag["jaccard"] == 1.0 and flag["match"] == "exact"
