"""S1: close each slab so its interior becomes hidden.

Measured on file A (spikes 14-16): the sidewalk is a top sheet with partial skirts and almost no
bottom -- 657 open edges, and only 21 of its 182 open TOP edges have a bottom outline below. The
interior rib walls are therefore visible through the side openings and from underneath, so the
strict hidden-face removal keeps every one of them. Closing the sides alone hides 105 more faces;
sides plus bottom hide 182. A single uniform thickness leaks: a real skirt varies from 1.3 to
49 in.

This is the ONLY step in the engine allowed to invent a vertex, and every face it invents is
guarded.
"""
import numpy as np
import pytest

from engine.fixes.pipeline import FixProfile, fix_object
from engine.fixes.solidify import solidify
from engine.pipeline import analyse_topology
from engine.tests.fixtures.build import (box_with_partition, open_box_with_cells,
                                         slab_with_three_skirts, two_level_slab)

_FAST = FixProfile(guard_size=(120, 80), n_dirs=32)


def _fast(**overrides):
    return FixProfile(guard_size=(120, 80), n_dirs=32, **overrides)


def _solidified(mesh, profile=None):
    profile = profile or _FAST
    return solidify(mesh, analyse_topology(mesh), profile)


def _face_normals(mesh):
    tri = mesh.positions[mesh.face_v]
    n = np.cross(tri[:, 1] - tri[:, 0], tri[:, 2] - tri[:, 0])
    return n / np.maximum(np.linalg.norm(n, axis=1), 1e-30)[:, None]


# ------------------------------------------------------------------- (b) skirt, and then bottom


def test_a_slab_open_on_one_side_gets_that_skirt_and_a_bottom():
    m = slab_with_three_skirts(size=40.0, height=8.0)
    r = _solidified(m)

    assert r.report["regions_processed"] == 1
    assert r.report["skirts_added"] == 1          # one open outline edge, one skirt quad
    assert r.report["bottoms_added"] == 1
    assert r.report["bottom_exists"] == 0
    assert r.report["outline_unmappable"] == 0
    assert list(r.report["thickness_per_region"].values()) == [8.0]
    assert r.report["skirt_length_total"] == pytest.approx(40.0)

    assert int(r.new_faces.sum()) == 4            # 2 skirt triangles + 2 bottom triangles
    assert r.mesh.n_faces == m.n_faces + 4
    # the skirt and the bottom land on corners the fixture already has
    assert r.report["invented_vertices"] == 0
    assert len(r.mesh.positions) == len(m.positions)

    new = np.nonzero(r.new_faces)[0]
    z = r.mesh.positions[r.mesh.face_v[new]][:, :, 2]
    assert z.min() == -8.0
    bottom = [f for f in new if np.allclose(r.mesh.positions[r.mesh.face_v[f]][:, 2], -8.0)]
    assert len(bottom) == 2
    assert (_face_normals(r.mesh)[bottom][:, 2] < -0.99).all()    # the bottom faces DOWN


def test_the_added_skirt_closes_the_slab():
    """Every edge of the result is shared by exactly two faces: a closed solid."""
    r = _solidified(slab_with_three_skirts())
    topo = analyse_topology(r.mesh)
    assert set(topo.table.counts.tolist()) == {2}


def test_the_skirt_is_wound_outward():
    """Away from the region centroid: a skirt wound inward would be back-facing from outside and
    a one-sided renderer would draw the hole it was added to close."""
    m = slab_with_three_skirts()
    r = _solidified(m)
    skirt = [f for f in np.nonzero(r.new_faces)[0]
             if abs(_face_normals(r.mesh)[f][2]) < 0.5]
    assert len(skirt) == 2
    # the open side is x = 0 and the slab lies at x > 0, so outward is -x
    assert all(_face_normals(r.mesh)[f][0] < -0.99 for f in skirt)


# ------------------------------------------------------------------ (c) an existing bottom


def test_a_region_that_already_has_a_bottom_gets_no_new_one():
    m = slab_with_three_skirts(with_bottom=True)
    r = _solidified(m)
    assert r.report["bottoms_added"] == 0
    assert r.report["bottom_exists"] == 1
    assert r.report["skirts_added"] == 1
    assert int(r.new_faces.sum()) == 2            # the skirt only


# -------------------------------------------------------------------- (a) the open box


def test_the_open_box_gets_its_missing_side_and_becomes_closed():
    m = open_box_with_cells()
    r = _solidified(m)

    assert r.report["skirts_added"] == 1 and r.report["bottoms_added"] == 0
    assert r.report["bottom_exists"] == 1         # the box floor is already there
    assert list(r.report["thickness_per_region"].values()) == [10.0]
    assert r.report["cap_guard_removed"] == 0

    # the BOX is closed: every edge still open belongs to one of the two floating partitions,
    # which is what makes them hidden -- 4 faces that had escape routes before and have none now
    topo = analyse_topology(r.mesh)
    partition_z = {2.0, 8.0}
    for edge in np.nonzero(topo.table.counts == 1)[0]:
        corners = topo.positions_w[topo.table.edges[edge]]
        assert set(np.round(corners[:, 1], 6).tolist()) <= {3.0, 7.0}, corners
        assert set(np.round(corners[:, 2], 6).tolist()) <= partition_z, corners
    assert r.report["faces_newly_hidden"] == 4


def test_a_top_sheet_wound_downwards_is_still_a_top_sheet():
    """`open_box_with_cells` is wound INWARD throughout: its z = 10 lid has `n_z = -1` and its
    z = 0 floor `n_z = +1`. A signed `n_z > 0.7` test would take the floor for the top surface
    and hang a skirt below the box. The sky test is what tells them apart -- and it matters on
    the real file, where 809 faces are wound backwards."""
    m = open_box_with_cells()
    normals = _face_normals(m)
    assert normals[2][2] == pytest.approx(-1.0)   # the lid, pointing down
    assert normals[0][2] == pytest.approx(1.0)    # the floor, pointing up

    r = _solidified(m)
    new = np.nonzero(r.new_faces)[0]
    z = r.mesh.positions[r.mesh.face_v[new]][:, :, 2]
    assert z.min() == 0.0 and z.max() == 10.0     # the skirt closes the SIDE, nothing hangs below


def test_fix_object_closes_the_open_box_and_then_removes_both_partitions():
    m = open_box_with_cells()
    r = fix_object(m, {}, _FAST)

    assert r.solidify_report["skirts_added"] == 1
    assert r.n_hidden_candidates >= 4 and r.n_removed_hidden >= 4
    assert r.n_restored_by_guard == 0
    topo = analyse_topology(r.mesh)
    assert set(topo.table.counts.tolist()) == {2}     # a closed box
    assert r.passed is True


# --------------------------------------------------------------------- (d) the cap guard


def test_a_skirt_that_reaches_past_the_slab_is_removed_by_the_cap_guard():
    """`two_level_slab`'s deep fin makes the open edge measure 200 in on an 8 in slab; with the
    ceiling raised the skirt hangs 192 in below the slab's own underside, covers that underside
    from every grazing view from below, and covers the panel as well. Neither is allowed: the
    underside is seen on its FRONT side and is still exposed, and so is the panel."""
    m = two_level_slab()
    r = _solidified(m, _fast(max_thickness=1000.0))

    assert list(r.report["thickness_per_region"].values()) == [200.0]   # the deep fin was measured
    assert r.report["cap_guard_rounds"] >= 2
    assert r.report["cap_guard_removed"] == 2       # the whole skirt quad goes
    assert int(r.new_faces.sum()) == 0
    assert r.mesh.n_faces == m.n_faces              # nothing else was touched


def test_the_same_fixture_is_fine_once_the_measurement_is_right():
    """Same fixture with a fin only as deep as the slab, so the open edge measures the 8 in the
    slab really is: the skirt lands exactly on the underside's plane, overhangs nothing, and the
    cap guard keeps it."""
    r = _solidified(two_level_slab(deep=8.0))
    assert list(r.report["thickness_per_region"].values()) == [8.0]
    assert r.report["cap_guard_removed"] == 0
    assert int(r.new_faces.sum()) == 2


def test_an_over_long_skirt_is_refused_at_the_default_ceiling_too():
    """The clamp is a bound, not a measurement: 200 in clamped to 36 is still 28 in of skirt
    hanging below an 8 in slab, and the cap guard refuses that as well. The ceiling limits how
    wrong a measurement can get; only the guard decides whether the result is acceptable."""
    r = _solidified(two_level_slab())
    assert list(r.report["thickness_per_region"].values()) == [36.0]
    assert r.report["cap_guard_removed"] == 2


# ------------------------------------------------------------------------ (e) determinism


def test_solidify_is_deterministic():
    m = slab_with_three_skirts()
    a, b = _solidified(m), _solidified(m)
    assert np.array_equal(a.mesh.face_v, b.mesh.face_v)
    assert np.array_equal(a.mesh.positions, b.mesh.positions)
    assert a.new_faces.tolist() == b.new_faces.tolist()
    assert a.report["thickness_per_region"] == b.report["thickness_per_region"]


# ----------------------------------------------------------------------- (f) --no-solidify


def test_no_solidify_reproduces_the_previous_result_on_box_with_partition():
    m = box_with_partition()
    off = fix_object(m, {}, _fast(solidify=False))
    assert off.solidify_report == {}
    assert off.mesh.n_faces == 12
    assert off.n_hidden_candidates == 2 and off.n_removed_hidden == 2
    assert len(off.mesh.positions) == len(m.positions)   # nothing invented
    assert off.passed is True


def test_a_closed_box_has_nothing_to_solidify():
    """`box_with_partition`'s cube has no open edge at all, so the default profile invents
    nothing either and the two runs agree face for face."""
    m = box_with_partition()
    on, off = fix_object(m, {}, _FAST), fix_object(m, {}, _fast(solidify=False))
    assert on.solidify_report["skirts_added"] == 0
    assert on.solidify_report["bottoms_added"] == 0
    assert on.solidify_report["invented_vertices"] == 0
    assert np.array_equal(on.mesh.face_v, off.mesh.face_v)
