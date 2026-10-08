import numpy as np
import pytest

from engine.campus import error_export as ee
from engine.campus.pixfont import GLYPHS


def test_face_kinds_takes_the_first_kind_in_priority_order():
    kinds = ee.face_kinds(6, {"hidden": [2, 3, 5], "flicker_same": [1, 2], "flicker_diff": [3], "loose": [5]})
    names = [None if k < 0 else ee.ERROR_KINDS[k] for k in kinds]
    assert names == [None, "flicker_same", "flicker_same", "flicker_diff", None, "loose"]


def test_face_kinds_ignores_out_of_range_indices_loudly():
    with pytest.raises(ValueError):
        ee.face_kinds(3, {"hidden": [3]})


def test_member_mask_follows_the_inventory_band_rule():
    cz = np.array([5.0, 10.0, 15.0])
    assert ee.member_mask({"faces": "all"}, cz).tolist() == [True, True, True]
    assert ee.member_mask({"faces": "band 1", "z_range": [None, 10.0]}, cz).tolist() == [True, False, False]
    assert ee.member_mask({"faces": "band 2", "z_range": [10.0, None]}, cz).tolist() == [False, True, True]
    assert ee.member_mask({"faces": "band 2", "z_range": [6.0, 14.0]}, cz).tolist() == [False, True, False]


def test_grid_dedup_keeps_one_point_per_cell_deterministically():
    pts = np.array([[0.1, 0.1, 0.1], [0.2, 0.3, 0.1], [7.0, 0.0, 0.0], [0.15, 0.1, 0.1]])
    out = ee.grid_dedup(pts, 6.0)
    assert out.tolist() == [[0.1, 0.1, 0.1], [7.0, 0.0, 0.0]]
    assert ee.grid_dedup(np.zeros((0, 3)), 6.0).shape == (0, 3)


FLAGS = [
    ({"kind": "split", "text": "MAIN_BUILDING spans 2 levels; proposed split by face centre: L04 34548 tris (43 %)"},
     "SPLIT: MAIN_BUILDING"),
    ({"kind": "misnamed", "text": "BRS_9th_floor_obj1: the name says floor 9, but its faces sit in L08 (z 1 to 2 in)"},
     "MISNAMED: BRS_9TH_FLOOR_OBJ1"),
    ({"kind": "missing", "text": "no group in BRS is named floor 8; L08 holds BRS_9th_floor_obj1"},
     "MISSING: NO GROUP NAMED FLOOR 8"),
    ({"kind": "duplicate", "text": "BRS_5th_floor_obj and BRS_5th_floor_obj1 share 39 % of their faces (Jaccard 0.39)"},
     "DUPLICATE: BRS_5TH_FLOOR_OBJ1 39%"),
    ({"kind": "shared", "text": "L05 of SCIENCE_A holds groups named for floors 4, 5 (A_obj, B_obj): a level may be"},
     "SHARED: FLOORS 4 5"),
    ({"kind": "footprint", "text": "Sciene_A_Floor_plan_6_obj (SCIENCE_A): 91 % of its footprint lies in MAIN_INFRA"},
     "FOOTPRINT: 91% IN MAIN_INFRA"),
    ({"kind": "owner", "text": "owner 2026-10-08: CHTM_12th is its own level (its slab is single-sided)"},
     "OWNER: CHTM_12TH IS ITS OWN LEVEL (ITS SLAB IS"),
]


@pytest.mark.parametrize("flag,label", FLAGS)
def test_flag_label_is_short_and_drawable(flag, label):
    got = ee.flag_label(flag)
    assert got == label
    assert len(got) <= ee.LABEL_MAX
    assert all(ch in GLYPHS for ch in got)


# -------------------------------------------------------------------------------------- plan_building

def _square(x, y, z, size=10.0):
    """Two triangles of a horizontal square."""
    p = np.array([[x, y, z], [x + size, y, z], [x + size, y + size, z], [x, y + size, z]], float)
    return p, np.array([[0, 1, 2], [0, 2, 3]])


def _mesh(*parts):
    pos, fv = [], []
    for p, f in parts:
        fv.append(f + sum(len(q) for q in pos))
        pos.append(p)
    return np.vstack(pos), np.vstack(fv)


def _errors(n, faces=None, open_edges=(), cracks=()):
    faces = {k: [] for k in ee.ERROR_KINDS} | (faces or {})
    return {"n_faces": n, "faces": faces, "open_edges": [list(s) for s in open_edges],
            "cracks": [list(c) for c in cracks],
            "counts": {k: len(v) for k, v in faces.items()} | {"open_edges": len(open_edges), "cracks": len(cracks)}}


@pytest.fixture
def campus():
    # A: one floor at z 100 (4 faces: 2 squares). S: spans two floors (z 100 and z 200), split by band.
    # D: an excluded duplicate of A.
    a_pos, a_fv = _mesh(_square(1000, 500, 100), _square(1020, 500, 100))
    s_pos, s_fv = _mesh(_square(1000, 500, 105), _square(1000, 500, 200))
    # a degenerate (zero-area) triangle in S's upper band, listed as loose, and one unlisted
    s_pos = np.vstack([s_pos, [[1000, 500, 210], [1001, 500, 210], [1002, 500, 210]]])
    s_fv = np.vstack([s_fv, [[8, 9, 10], [8, 9, 10]]])
    meshes = {
        "A_1st_floor": (a_pos, a_fv, _errors(4, {"flicker_diff": [0], "hidden": [0, 1]},
                                             open_edges=[(1000, 500, 100, 1010, 500, 100)],
                                             cracks=[(1000, 500, 100), (1000.5, 500.5, 100), (1030, 510, 100)])),
        "S_building": (s_pos, s_fv, _errors(6, {"reversed": [1], "loose": [4]},
                                            open_edges=[(1000, 500, 105, 1000, 510, 105),
                                                        (1000, 500, 200, 1010, 500, 200)])),
        "A_1st_floor_obj1": (a_pos, a_fv, _errors(4, {"hidden": [3]})),
    }
    units = [
        {"unit": "B-L02", "building": "B", "level": "L02", "type": "floor", "base": 195.0,
         "members": [{"group": "S_building", "file": "S_building.obj", "faces": "band 2", "z_range": [150.0, None]}],
         "flags": [{"kind": "split", "text": "S_building spans 2 levels; proposed split by face centre: L01 2 tris"},
                   {"kind": "misnamed", "text": "A_1st_floor: the name says floor 1, but its faces sit in L02 (z 1 to 2 in)"}],
         "confirmed_by_owner": False},
        {"unit": "B-L01", "building": "B", "level": "L01", "type": "floor", "base": 99.0,
         "members": [{"group": "A_1st_floor", "file": "A_1st_floor.obj", "faces": "all"},
                     {"group": "S_building", "file": "S_building.obj", "faces": "band 1", "z_range": [None, 150.0]}],
         "flags": [], "confirmed_by_owner": True},
        {"unit": "OTHER-L01", "building": "OTHER", "level": "L01", "type": "floor", "base": 0.0,
         "members": [], "flags": [], "confirmed_by_owner": True},
    ]
    cmap = {"units": units, "excluded": [{"group": "A_1st_floor_obj1", "reason": "owner: duplicate of A"}]}
    mismatches = {"A_1st_floor.obj": {"area_rel": 0.0071}}
    return cmap, meshes, mismatches


def _plan(campus):
    cmap, meshes, mismatches = campus
    return ee.plan_building("B", cmap, lambda group: meshes[group], mismatches=mismatches,
                            building_of=lambda g: "B")


def test_columns_are_floors_in_level_order_then_excluded(campus):
    plan = _plan(campus)
    assert [c.unit for c in plan.columns] == ["B-L01", "B-L02", "EXCLUDED-A_1st_floor_obj1"]
    assert [c.type for c in plan.columns] == ["floor", "floor", "excluded"]


def _label_width(col):
    from engine.campus.pixfont import text_width
    return max([text_width(col.label, ee.UNIT_CELL_IN)] + [text_width(f["label"], ee.FLAG_CELL_IN) for f in col.flags])


def test_columns_sit_side_by_side_at_the_origin_with_their_base_at_zero(campus):
    plan = _plan(campus)
    c1, c2, c3 = plan.columns
    assert c1.x0 == 0.0
    assert c2.x0 == pytest.approx(c1.x0 + max(c1.width, _label_width(c1)) + ee.GAP_IN)
    assert c3.x0 == pytest.approx(c2.x0 + max(c2.width, _label_width(c2)) + ee.GAP_IN)
    for c in plan.columns:
        pts = np.vstack([t.reshape(-1, 3) for m in c.members for t in m.tris.values() if len(t)]
                        + [m.markers[k] for m in c.members for k in m.markers if len(m.markers[k])])
        assert pts[:, 0].min() == pytest.approx(c.x0)
        assert pts[:, 1].min() == pytest.approx(0.0)
    l01 = plan.columns[0]
    a = l01.members[0]
    assert a.tris["base"].reshape(-1, 3)[:, 2].min() == pytest.approx(1.0)   # z 100 - base 99


def test_each_face_is_drawn_once_in_its_first_kind(campus):
    plan = _plan(campus)
    a, s1 = plan.columns[0].members
    assert {k: len(v) for k, v in a.tris.items() if len(v)} == {"flicker_diff": 1, "hidden": 1, "base": 2}
    assert {k: len(v) for k, v in s1.tris.items() if len(v)} == {"base": 1, "reversed": 1}
    s2 = plan.columns[1].members[0]
    assert {k: len(v) for k, v in s2.tris.items() if len(v)} == {"base": 2}
    assert len(s2.markers["loose"]) == 1            # the listed degenerate face becomes a marker
    assert s2.skipped_degenerate_base == 1          # the unlisted one is counted, not drawn


def test_counts_keep_every_listing(campus):
    plan = _plan(campus)
    l01 = plan.columns[0]
    assert l01.counts["flicker_diff"] == 1 and l01.counts["hidden"] == 2 and l01.counts["reversed"] == 1
    assert plan.counts["loose"] == 1 and plan.counts["hidden"] == 2


def test_open_edges_and_cracks_follow_the_member_band_and_are_moved(campus):
    plan = _plan(campus)
    a, s1 = plan.columns[0].members
    s2 = plan.columns[1].members[0]
    assert len(a.segments) == 1 and len(s1.segments) == 1 and len(s2.segments) == 1
    assert len(a.cracks) == 2                      # two of three crack points share a 6 in cell
    assert plan.columns[0].counts["cracks"] == 3
    assert s2.segments[:, :, 2].min() == pytest.approx(5.0)   # z 200 - base 195


def test_flags_labels_pending_and_mismatch(campus):
    plan = _plan(campus)
    l01, l02, ex = plan.columns
    assert [f["kind"] for f in l01.flags] == ["skp_mismatch"]
    assert l01.flags[0]["label"] == "BACKUP +0.71% AREA: A_1ST_FLOOR"
    # the misnamed flag names a group that is not a member any more: stale, dropped
    assert [f["kind"] for f in l02.flags] == ["split", "pending"]
    assert [f["kind"] for f in ex.flags] == ["excluded"]
    assert ex.members[0].tris.keys() == {"excluded"}
    assert len(ex.members[0].tris["excluded"]) == 4


def test_a_building_without_units_is_refused(campus):
    cmap, meshes, _ = campus
    with pytest.raises(ValueError):
        ee.plan_building("NOPE", cmap, lambda g: meshes[g])


def test_exact_duplicates_counts_triangles_repeating_an_earlier_one_in_any_vertex_order():
    t = np.array([[[0, 0, 0], [1, 0, 0], [0, 1, 0]],
                  [[1, 0, 0], [0, 1, 0], [0, 0, 0]],      # same triangle, rotated
                  [[0, 0, 0], [0, 1, 0], [1, 0, 0]],      # same, reversed winding
                  [[0, 0, 0], [1, 0, 0], [0, 2, 0]]], float)
    assert ee.exact_duplicates(t) == 2
    assert ee.exact_duplicates(np.zeros((0, 3, 3))) == 0


def test_columns_leave_room_for_their_longest_label(campus):
    from engine.campus.pixfont import text_width
    plan = _plan(campus)
    for a, b in zip(plan.columns, plan.columns[1:]):
        widest = max([text_width(a.label, ee.UNIT_CELL_IN)] +
                     [text_width(f["label"], ee.FLAG_CELL_IN) for f in a.flags])
        assert b.x0 >= a.x0 + max(a.width, widest) + ee.GAP_IN - 1e-9
    assert plan.columns[1].x0 > plan.columns[0].x0 + plan.columns[0].width + ee.GAP_IN   # labels are wider here


def test_the_longest_campus_duplicate_label_keeps_its_percent():
    flag = {"kind": "duplicate", "text": "Sciene_A_Floor_plan_2_obj and Sciene_A_Floor_plan_2_obj1 share 80 % of"}
    assert ee.flag_label(flag) == "DUPLICATE: SCIENE_A_FLOOR_PLAN_2_OBJ1 80%"


def test_tubes_are_three_quads_per_segment_around_it_and_skip_zero_length():
    seg = np.array([[[0, 0, 0], [10, 0, 0]], [[0, 0, 0], [0, 0, 10]], [[5, 5, 5], [5, 5, 5]]], float)
    q = ee._tubes(seg, r=1.0)
    assert q.shape == (6, 4, 3)
    horiz = q[[0, 2, 4]].reshape(-1, 3)                    # every corner sits r from its segment's axis
    assert np.allclose(np.hypot(horiz[:, 1], horiz[:, 2]), 1.0)
    vert = q[[1, 3, 5]].reshape(-1, 3)                     # vertical segment: the helper axis switches
    assert np.allclose(np.hypot(vert[:, 0], vert[:, 1]), 1.0)


def test_markers_are_octahedra_of_the_given_radius():
    m = ee._markers(np.array([[1.0, 2.0, 3.0]]), r=2.0)
    assert m.shape == (8, 3, 3)
    assert np.allclose(np.linalg.norm(m.reshape(-1, 3) - [1, 2, 3], axis=1), 2.0)


def test_ring_frames_the_rectangle_between_its_margins():
    r = ee._ring(0, 0, 100, 50, 10, 30, -2)
    assert r.shape == (4, 4, 3)
    pts = r.reshape(-1, 3)
    assert pts[:, 0].min() == -30 and pts[:, 0].max() == 130 and pts[:, 1].min() == -30 and pts[:, 1].max() == 80
    assert np.all(pts[:, 2] == -2)


def test_grouping_rings_stay_inside_half_the_column_gap():
    assert ee.ring_margins(len(ee.GROUPING_KINDS) - 1)[1] < ee.GAP_IN / 2


def test_mismatch_text_says_less_for_a_negative_area_difference(campus):
    cmap, meshes, _ = campus
    plan = ee.plan_building("B", cmap, lambda g: meshes[g], mismatches={"A_1st_floor.obj": {"area_rel": -0.03}},
                            building_of=lambda g: "B")
    flag = plan.columns[0].flags[0]
    assert "3.00 % less area" in flag["text"] and flag["label"] == "BACKUP -3.00% AREA: A_1ST_FLOOR"


def test_a_missing_snapshot_or_errors_file_names_the_group(campus):
    cmap, meshes, _ = campus

    def load(group):
        raise FileNotFoundError("nope")
    with pytest.raises(ValueError, match="A_1st_floor"):
        ee.plan_building("B", cmap, load, building_of=lambda g: "B")
