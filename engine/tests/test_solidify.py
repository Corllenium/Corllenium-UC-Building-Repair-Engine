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
import shapely

from engine.fixes.pipeline import FixProfile, fix_object
from engine.fixes.solidify import solidify, top_regions
from engine.rays.caster import EmbreeCaster
from engine.pipeline import analyse_topology
from engine.tests.fixtures.build import (bare_top_quad, box_with_partition,
                                         compartment_with_deep_wall, open_box_with_cells,
                                         slab_with_partial_underside, slab_with_three_skirts,
                                         slab_with_two_depths, two_level_slab)
from engine.topo.weld import weld_exact
from engine.vis.exposure import compute_side_exposure

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


def test_the_open_box_is_closed_and_the_partitions_inside_it_may_be_covered():
    """The wall this fixture needs is built -- one missing side, measured at the box's own 10 in
    -- and KEPT, because everything it covers lies inside the box's volume.

    THIS TEST HAS CHANGED SIDES TWICE. Before S-C1 the skirt was kept for a wrong reason (the
    rule read the covered face's exposure on the SOLIDIFIED mesh, which the skirt itself drove to
    0). S-C1 made the rule read the ORIGINAL mesh, where the near partition, 3 in inside the hole,
    is 25 % exposed -- far above `cover_max_exposure` -- and the skirt was refused, leaving the box
    open and its insides on show. SR2 is the owner's rule: "delete the inside, build the side
    meshes". A face lying INSIDE the slab's volume (under its top, above its measured bottom) may
    be covered whatever its exposure, and the hidden-face pass then removes it because the slab
    is closed. So the partitions' 25 % still does not authorise the cover (rule 3 still refuses
    it); their position does (`interior_faces_covered`)."""
    m = open_box_with_cells()
    r = _solidified(m)

    assert r.report["skirts_added"] == 1 and r.report["bottoms_added"] == 0
    assert r.report["bottom_exists"] == 1         # the box floor is already there
    assert list(r.report["thickness_per_region"].values()) == [10.0]

    assert r.report["cap_guard_removed"] == 0
    assert int(r.new_faces.sum()) == 2            # the one wall quad
    assert r.report["interior_faces_covered"] >= 2
    assert r.report["faces_newly_hidden"] == 4    # both partitions, sealed on both sides

    front = _front_exposure(m, n_dirs=512)
    assert front[10] > FixProfile().cover_max_exposure     # the near partition, 25 % exposed
    assert front[11] > FixProfile().cover_max_exposure


def test_a_top_sheet_wound_downwards_is_still_a_top_sheet():
    """`open_box_with_cells` is wound INWARD throughout: its z = 10 lid has `n_z = -1` and its
    z = 0 floor `n_z = +1`. A signed `n_z > 0.7` test would take the floor for the top surface
    and hang a skirt below the box. The sky test is what tells them apart -- and it matters on
    the real file, where 809 faces are wound backwards.

    Asserted on the PLAN rather than on the surviving faces: which region was chosen, and how far
    down its wall was measured, is what this test is about (what the cap guard then does with the
    wall is `test_the_open_box_is_closed_and_the_partitions_inside_it_may_be_covered`)."""
    m = open_box_with_cells()
    normals = _face_normals(m)
    assert normals[2][2] == pytest.approx(-1.0)   # the lid, pointing down
    assert normals[0][2] == pytest.approx(1.0)    # the floor, pointing up

    topo = analyse_topology(m)
    caster = EmbreeCaster(topo.positions_w, topo.face_w[topo.ok])
    regions = top_regions(topo, _FAST, caster)
    assert regions == [int(topo.face_region[2])]              # the LID, not the floor
    assert int(topo.face_region[0]) not in regions

    r = _solidified(m)
    # measured at the box's own side, so the skirt reaches z = 0 and nothing hangs below it
    assert list(r.report["thickness_per_region"].values()) == [10.0]


def test_fix_object_closes_the_open_box_and_removes_the_partitions_inside_it():
    """End to end, SR2: the wall is kept, both partitions are then sealed inside the box, and the
    strict hidden-face pass removes all four of their triangles. The shipped box is closed and
    shows no back side anywhere. (Under S-C1 this box was left open and both partitions were
    kept on show -- see the test above for why that rule changed.)"""
    m = open_box_with_cells()
    r = fix_object(m, {}, _FAST)

    assert r.solidify_report["skirts_added"] == 1
    assert r.solidify_report["cap_guard_removed"] == 0
    assert r.reference_mesh.n_faces == m.n_faces + 2
    assert r.n_removed_hidden == 4
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


# ------------------------------------------------- S-C1: the cover rule reads the ORIGINAL mesh


def _front_exposure(mesh, n_dirs=32):
    """Front-side exposure of every face of `mesh`, measured against `mesh` itself."""
    positions_w, remap = weld_exact(mesh.positions, mesh.coord_decimals)
    centre = (positions_w.min(axis=0) + positions_w.max(axis=0)) / 2.0
    face_w = remap[mesh.face_v]
    front, _back = compute_side_exposure(positions_w - centre, face_w,
                                         np.ones(len(face_w), bool), n_dirs=n_dirs)
    return front


def test_a_shelf_inside_the_slab_is_interior_and_may_be_covered_by_the_bottom():
    """The S-C1 reviewer's scenario, under SR2's rule. The region's three sides measure 9.8 in,
    so the slab is 9.8 in deep and a bottom is invented there; a 4 in deep shelf covers a
    quarter of the footprint, too little for `_has_bottom`.

    S-C1 refused the part of the bottom that covered the shelf, reading the shelf as the slab's
    "real underside" because it is plainly visible from below (front exposure about 0.5). That
    is exactly the owner's "floating thin slab visible inside": it lies under the top, above the
    slab's measured bottom, so it is INSIDE the slab's volume, and SR2 lets the bottom cover it
    (`interior_faces_covered`). What S-C1's rule still refuses is a cover of anything OUTSIDE the
    volume -- `two_level_slab`'s underside below a skirt that hangs past it, below."""
    m = slab_with_partial_underside()
    original_front = _front_exposure(m)
    assert original_front[8] > FixProfile().cover_max_exposure    # plainly visible from below

    r = _solidified(m)
    assert r.report["bottoms_added"] == 1              # invented at the measured 9.8 in
    assert r.report["cap_guard_removed"] == 0          # and kept whole
    assert r.report["interior_faces_covered"] >= 2

    result = fix_object(m, {}, _FAST)
    assert result.removed_hidden[8] and result.removed_hidden[9]  # sealed inside, then removed
    assert result.passed is True


def test_a_wall_seen_only_through_a_side_opening_may_be_covered_and_is_then_removed():
    """The case rule 3 exists for, and which the new rule must not break: a compartment whose
    far wall is visible ONLY through the side opening the skirt closes. Its exposure on the
    ORIGINAL mesh is a fraction of a percent -- well under `cover_max_exposure` -- so the skirt
    is allowed to cover it, and the hidden pass then removes it."""
    m = compartment_with_deep_wall()
    # Genuinely seen, and barely: 0.39 % of the sample budget at 512 directions, against a
    # 10 % threshold. (At the 32 directions this test's fast profile uses it rounds to 0.0 --
    # which is also below the threshold, but says less.)
    original_front = _front_exposure(m, n_dirs=512)
    assert 0.0 < original_front[10] < 0.01 < FixProfile().cover_max_exposure
    assert 0.0 < original_front[11] < 0.01

    # At the shipped 128 directions, not this file's fast 32: at 32 the wall's own exposure
    # already rounds to 0, so "newly hidden" would have nothing left to show.
    r = _solidified(m, FixProfile(guard_size=(120, 80), n_dirs=128))
    assert r.report["skirts_added"] == 1
    assert r.report["cap_guard_removed"] == 0
    assert r.report["faces_newly_hidden"] == 2


def test_fix_object_closes_the_compartment_and_removes_its_deep_wall():
    """End to end: the skirt survives the cap guard, the wall it covers becomes hidden, and the
    strict removal guard then deletes it."""
    result = fix_object(compartment_with_deep_wall(), {}, _FAST)
    assert result.solidify_report["cap_guard_removed"] == 0
    assert result.removed_hidden[10] and result.removed_hidden[11]
    assert result.passed is True


# ---------------------------------------------- S-I4: each open edge gets its OWN measured height


def _skirt_faces(result):
    """New faces that are vertical -- the skirts, as opposed to the bottom."""
    normals = _face_normals(result.mesh)
    return [f for f in np.nonzero(result.new_faces)[0] if abs(normals[f][2]) < 0.5]


def _skirt_lows(result):
    return sorted(round(float(result.mesh.positions[result.mesh.face_v[f]][:, 2].min()), 6)
                  for f in _skirt_faces(result))


def test_each_open_edge_is_extruded_to_its_own_measured_height():
    """`slab_with_two_depths` measures 1.3 in at the two open edges touching its shallow end and
    9.8 in at the two touching its deep end. The region's single statistic (its median, 5.55 in
    here) used to be applied to all four, which hangs half of them 4 in too low and half of them
    4 in too high -- and the cap guard then refuses the overhang."""
    m = slab_with_two_depths()
    r = _solidified(m, _fast(min_thickness=1.0))

    assert r.report["skirts_added"] == 4
    assert r.report["skirt_edges_fallback"] == 0
    assert r.report["cap_guard_removed"] == 0
    assert r.report["thickness_per_region"] == {"0": pytest.approx(5.55)}   # the FALLBACK only

    skirt = _skirt_faces(r)
    assert len(skirt) == 8                           # four quads
    assert _skirt_lows(r) == [-9.8] * 4 + [-1.3] * 4

    # the shallow pair hangs off the shallow (x = 0) end, the deep pair off the deep one
    for f in skirt:
        x = r.mesh.positions[r.mesh.face_v[f]][:, 0]
        low = round(float(r.mesh.positions[r.mesh.face_v[f]][:, 2].min()), 6)
        assert (float(x.min()) == 0.0) if low == -1.3 else (float(x.max()) == 60.0)


def test_a_measured_edge_height_is_still_clamped_into_the_profile_bounds():
    """Per edge now, where it used to be per region: the same 1.3 in measurement comes back as
    the default `min_thickness` of 2.0, and `two_level_slab`'s 200 in edge still clamps to
    `max_thickness`."""
    assert _skirt_lows(_solidified(slab_with_two_depths())) == [-9.8] * 4 + [-2.0] * 4


def test_an_edge_whose_height_cannot_be_measured_is_counted_as_a_fallback():
    """`bare_top_quad` has no side face anywhere in the file, so not one of its four open edges
    resolves. Each still gets a skirt -- it closes a hole a person can see, and the cap guard
    judges it -- at `min_thickness`, and all four are reported as fallbacks."""
    r = _solidified(bare_top_quad())
    assert r.report["skirts_added"] == 4
    assert r.report["skirt_edges_fallback"] == 4
    assert r.report["bottom_thickness_unresolved"] == 1      # and so no bottom is invented
    assert r.report["bottoms_added"] == 0


# ------------------------------------ S-I5: the bottom goes at the SHALLOWEST measured depth


def _bottom_faces(result):
    normals = _face_normals(result.mesh)
    return [f for f in np.nonzero(result.new_faces)[0] if normals[f][2] < -0.5]


def test_the_bottom_goes_at_the_shallowest_resolved_skirt_height():
    """`slab_with_two_depths` measures 1.3 in on two edges and 9.8 in on the other two. A bottom
    at the MEDIAN (5.55 in) sits below the shallow skirts -- so the steps between them stay open
    from underneath -- and above the deep ones, cutting them in half. The shallowest is the only
    depth at which the bottom meets a skirt rather than crossing one."""
    r = _solidified(slab_with_two_depths(), _fast(min_thickness=1.0))

    assert r.report["bottoms_added"] == 1
    bottom = _bottom_faces(r)
    assert bottom
    z = r.mesh.positions[r.mesh.face_v[bottom]][:, :, 2]
    assert z.min() == pytest.approx(-1.3) and z.max() == pytest.approx(-1.3)


def test_an_existing_underside_deeper_than_the_shallowest_skirt_counts_as_a_bottom():
    """The same slab with a real plate 11.8 in down. The shallowest skirt is 1.3 in, so a search
    that stopped at `h + tol` would not see the plate and would invent a second bottom 10.5 in
    ABOVE it -- boxing the real one in. `bottom_search_extra` reaches past `h` for exactly that
    reason."""
    m = slab_with_two_depths(with_bottom=True)
    r = _solidified(m, _fast(min_thickness=1.0))

    assert r.report["bottom_exists"] == 1
    assert r.report["bottoms_added"] == 0
    assert _bottom_faces(r) == []
    # the real plate is untouched and still the lowest thing in the mesh
    assert float(r.mesh.positions[:, 2].min()) == pytest.approx(-11.8)


def test_a_bottom_is_not_found_beyond_the_extra_search_depth():
    """The search is bounded, not unbounded: a plate further down than `h + bottom_search_extra`
    is not this region's bottom, and one is invented."""
    m = slab_with_two_depths(with_bottom=True)
    r = _solidified(m, _fast(min_thickness=1.0, bottom_search_extra=2.0))
    assert r.report["bottom_exists"] == 0
    assert r.report["bottoms_added"] == 1


# ------------------------------------- S-I3: skips are counted and a partial bottom is refused


def test_a_clean_bottom_reports_no_skips_at_all():
    r = _solidified(slab_with_three_skirts())
    assert r.report["bottoms_added"] == 1
    assert r.report["bottoms_partial_refused"] == 0
    assert set(r.report["bottom_skips"].values()) == {0}


def test_a_bottom_with_a_skipped_part_is_refused_whole(monkeypatch):
    """`shapely.constrained_delaunay_triangles` returns a GeometryCollection whose members are
    normally all Polygons; a degenerate one comes back as a LineString instead, which `_add_bottom`
    skips. No fixture in this repo produces one -- `b2134e9`, which added that guard, says the
    same -- so the branch is driven here by replacing ONE part of the real CDT's output.

    What is under test is what solidify then does: a bottom missing one of its triangles is a
    hole in the underside, which is worse than no bottom at all, so the WHOLE bottom is dropped,
    counted as `bottoms_partial_refused`, and not reported as added."""
    real = shapely.constrained_delaunay_triangles

    def one_part_degenerate(polygon):
        parts = list(getattr(real(polygon), "geoms", []))
        return shapely.GeometryCollection(
            [shapely.LineString(list(parts[0].exterior.coords)[:2])] + parts[1:])

    monkeypatch.setattr(shapely, "constrained_delaunay_triangles", one_part_degenerate)
    m = slab_with_three_skirts()
    r = _solidified(m)

    assert r.report["bottoms_added"] == 0
    assert r.report["bottoms_partial_refused"] == 1
    assert r.report["bottom_skips"]["non_polygon_part"] == 1
    assert int(r.new_faces.sum()) == 2                # the skirt only, no half a bottom
    assert r.report["invented_vertices"] == 0         # and a refused bottom invents nothing


def test_a_bottom_whose_triangulation_raises_is_counted_and_refused(monkeypatch):
    """A second skip reason, reaching the same verdict through its own counter: GEOS refuses to
    triangulate the outline at all."""
    monkeypatch.setattr(shapely, "constrained_delaunay_triangles",
                        lambda polygon: (_ for _ in ()).throw(shapely.errors.GEOSException("no")))
    r = _solidified(slab_with_three_skirts())
    assert r.report["bottoms_added"] == 0
    assert r.report["bottoms_partial_refused"] == 1
    assert r.report["bottom_skips"]["cdt_failed"] == 1


# --------------------------------------------------- S-I2: the cap guard is an INVARIANT


def test_a_converged_cap_guard_is_reported_as_passed():
    r = fix_object(slab_with_three_skirts(), {}, _FAST)
    assert r.solidify_report["cap_guard_passed"] is True
    assert r.invariants["cap_guard_passed"] is True
    assert r.passed is True
    assert r.solidify_report["cap_guard"][-1]["failing_pixels"] == 0


def test_a_run_with_nothing_to_solidify_passes_the_cap_guard_vacuously():
    on = fix_object(box_with_partition(), {}, _FAST)
    assert on.solidify_report["cap_guard"] == [] and on.solidify_report["cap_guard_passed"] is True
    off = fix_object(box_with_partition(), {}, _fast(solidify=False))
    assert off.invariants["cap_guard_passed"] is True


def test_a_cap_guard_that_never_converged_fails_the_whole_run():
    """The rounds are capped, and a round's `failing_pixels` is measured BEFORE that round's own
    removals -- so a loop cut off at the cap reported the state before its last deletion and
    `cap_guard_removed` was the only trace that anything was still wrong. The loop now always
    ends with a render-only verification of the mesh it is actually handing back.

    Forced here by giving the guard NO rounds at all, which is the cleanest way to leave a
    solidified mesh that has never been corrected: `two_level_slab`'s skirt, with the ceiling
    raised, hangs 192 in below the slab's own underside and covers it and the panel below -- both
    OUTSIDE the slab's volume. (This used `slab_with_partial_underside` until SR2 made its shelf
    an interior face the bottom may cover.) The point of the test is that the verdict comes from
    a real final render of the mesh that would have shipped, not from the loop's own
    bookkeeping."""
    r = fix_object(two_level_slab(), {}, _fast(cap_guard_max_rounds=0, max_thickness=1000.0))

    history = r.solidify_report["cap_guard"]
    assert len(history) == 1
    assert history[-1]["removed"] == 0 and history[-1]["failing_pixels"] > 0
    assert r.solidify_report["cap_guard_removed"] == 0     # nothing was corrected
    assert r.solidify_report["cap_guard_passed"] is False
    assert r.invariants["cap_guard_passed"] is False
    assert r.passed is False


# ------------------------------------------------- S-M: an invented face has no line number


def test_an_invented_face_carries_no_line_number():
    """`face_line` is the line of the OBJ the face was read from. A face this module invents was
    never in any file, and the builder used to give it `n + 1, n + 2, ...` -- line numbers that
    exist, belong to other faces, and would send anyone chasing a defect to the wrong row."""
    m = slab_with_three_skirts()
    r = _solidified(m)
    new = np.nonzero(r.new_faces)[0]
    assert len(new) == 4
    assert (r.mesh.face_line[new] == -1).all()
    # every face that DID come from the file keeps its own line
    assert np.array_equal(r.mesh.face_line[: m.n_faces], m.face_line)


# --------------------------------------------- SR2: a broken side is rebuilt instead of preserved
#
# Measured on the owner's files (SR1): the sawtooth he photographed is file B's ramp side, a row
# of triangular teeth with gaps. Solidify only walled OPEN outline edges, so the edges a tooth
# shares with the top got nothing and the gaps' walls were judged by a rule that refuses to cover
# anything visible -- and the teeth and the inside seen between them are visible by definition.
# SR2 walls every outline edge whose side is missing or broken, replaces the pieces of the side
# lying within `FixProfile.side_band` of the new wall, and lets a closing face cover what lies
# inside the slab's volume. Nothing outside the volume may be covered.

from engine.guard.views import VIEWS_26, ortho_first_hit  # noqa: E402
from engine.tests.fixtures.build import (slab_with_half_side, slab_with_railing_outside,  # noqa: E402
                                         slab_with_sawtooth_side,
                                         slab_with_side_behind_a_t_junction,
                                         two_slabs_meeting_at_a_t_junction)


def _reference_row(r, input_faces):
    """Where input face ids landed in `r.mesh` (solidify drops the pieces it replaced)."""
    rows = np.cumsum(~r.replaced) - 1
    return np.where(r.replaced[input_faces], -1, rows[input_faces])


def _plane_faces(mesh, axis, value, tol=1e-6):
    """Faces of `mesh` lying in the plane `x[axis] == value`."""
    tri = mesh.positions[mesh.face_v]
    return np.nonzero((np.abs(tri[:, :, axis] - value) <= tol).all(axis=1))[0]


def _covered_area(mesh, faces, axes):
    """Area of the union of `faces` projected on the two `axes`."""
    polys = [shapely.Polygon(mesh.positions[mesh.face_v[f]][:, axes]) for f in faces]
    return shapely.union_all(polys).area if polys else 0.0


def _unchanged_pixels(m, r, faces, size=(120, 80)):
    """For every pixel of the 26 guard views whose first hit on the INPUT is one of `faces`:
    is its first hit on the solidified mesh the same face? Both meshes framed alike."""
    positions_w, remap = weld_exact(r.mesh.positions, r.mesh.coord_decimals)
    centre = (positions_w.min(axis=0) + positions_w.max(axis=0)) / 2.0
    pc = positions_w - centre
    before_faces = remap[m.face_v]
    after_faces = remap[r.mesh.face_v]
    rows = _reference_row(r, np.arange(m.n_faces))
    seen = changed = 0
    for view in VIEWS_26:
        b = ortho_first_hit(pc, before_faces, np.arange(m.n_faces), view, pc, size)
        a = ortho_first_hit(pc, after_faces, np.arange(r.mesh.n_faces), view, pc, size)
        mine = np.isin(b.tri, faces)
        seen += int(mine.sum())
        changed += int((a.tri[mine] != rows[b.tri[mine]]).sum())
    return seen, changed


def test_a_sawtooth_side_is_rebuilt_as_one_clean_wall():
    """The teeth lie within 1 in of the `x = 0` plane, some wound inward, one missing: the side
    is broken, not missing and not whole. It is replaced by a wall wound outward, tiling the
    whole side, and the four teeth are gone. The rib seen through the gaps lies inside the slab,
    so covering it is allowed -- and it is still in the mesh here: deleting the inside is the
    hidden-face pass's job, below."""
    m = slab_with_sawtooth_side()
    teeth = np.arange(m.n_faces - 6, m.n_faces - 2)
    r = _solidified(m)

    assert r.report["cap_guard_passed"] is True
    assert r.replaced.tolist() == [f in teeth for f in range(m.n_faces)]
    assert r.report["side_pieces_replaced"] == 4
    assert r.report["sides_rebuilt"]["edges"] >= 1
    assert r.report["sides_rebuilt"]["length"] == pytest.approx(40.0)
    assert r.report["interior_faces_covered"] >= 2            # the rib
    assert r.report["walls_refused"]["faces"] == 0

    wall = _plane_faces(r.mesh, 0, 0.0)
    assert len(wall) >= 2 and r.new_faces[wall].all()          # only the new wall is at x = 0
    assert (_face_normals(r.mesh)[wall][:, 0] < -0.99).all()   # wound outward
    assert _covered_area(r.mesh, wall, [1, 2]) == pytest.approx(40.0 * 8.0)
    # the rib is untouched by solidify itself
    rib = _reference_row(r, np.array([m.n_faces - 2, m.n_faces - 1]))
    assert (rib >= 0).all()


def test_fix_object_closes_the_sawtooth_side_and_deletes_what_was_seen_through_it():
    """End to end: the rebuilt wall seals the slab, the rib becomes hidden and the strict hidden
    pass deletes it, and from outside no pixel shows a face's back side any more."""
    m = slab_with_sawtooth_side()
    r = fix_object(m, {}, _FAST)

    assert r.passed is True
    assert r.backface_px["input"]["total"] > 0
    assert r.backface_px["final"]["total"] == 0
    at_rib = (np.abs(r.mesh.positions[r.mesh.face_v][:, :, 0] - 4.0) < 1e-6).all(axis=1)
    assert not at_rib.any()
    topo = analyse_topology(r.mesh)
    assert set(topo.table.counts.tolist()) == {2}              # a closed solid


def test_a_railing_standing_outside_the_edge_is_never_replaced_or_covered():
    """A railing 2 in outside the missing side -- both its faces inside the 2.5 in side band --
    but standing from the slab's underside up to 30 in ABOVE the top: not a piece of the side.
    And a wall 6 in out. Neither is replaced, and not one of their pixels changes."""
    m = slab_with_railing_outside()
    outside = np.arange(m.n_faces - 8, m.n_faces)
    r = _solidified(m)

    assert not r.replaced.any()
    assert r.report["sides_rebuilt"]["edges"] == 1             # the missing side is built
    seen, changed = _unchanged_pixels(m, r, outside)
    assert seen > 0 and changed == 0


def test_a_railing_seen_through_an_open_slab_is_never_covered():
    """The same railing with the slab's bottom missing too, so from below a person sees the
    railing's inner face THROUGH the slab and its open side. Whatever closing face would cover that
    view is refused -- the railing lies outside the slab's volume -- and its pixels are exactly
    what they were."""
    m = slab_with_railing_outside(with_bottom=False)
    outside = np.arange(m.n_faces - 8, m.n_faces)
    r = _solidified(m)

    seen, changed = _unchanged_pixels(m, r, outside)
    assert seen > 0 and changed == 0
    assert not r.replaced[outside].any()


def test_a_half_side_gets_the_rest_built_and_nothing_outside_the_volume_changes():
    """The side covers `y` 0 to 20 of a 40 in edge. After solidify the whole `x = 0` side is
    closed by faces wound outward, and the post standing outside the missing half looks exactly
    as it did from every view."""
    m = slab_with_half_side()
    post = np.array([m.n_faces - 2, m.n_faces - 1])
    r = _solidified(m)

    assert r.report["cap_guard_passed"] is True
    side = _plane_faces(r.mesh, 0, 0.0)
    assert (_face_normals(r.mesh)[side][:, 0] < -0.99).all()
    assert _covered_area(r.mesh, side, [1, 2]) == pytest.approx(40.0 * 8.0)
    seen, changed = _unchanged_pixels(m, r, post)
    assert seen > 0 and changed == 0
    # nothing was invented outside the slab
    new = r.mesh.positions[r.mesh.face_v[r.new_faces]]
    assert new[:, :, 0].min() >= 0.0 and new[:, :, 2].min() >= -8.0


def test_an_existing_side_behind_a_t_junction_gets_nothing_laid_over_it():
    """The top edge counts as open (the side's own top edge is cut at a T-vertex), but the side
    is whole. It is not a missing side: nothing is added in its plane and nothing is replaced."""
    m = slab_with_side_behind_a_t_junction()
    r = _solidified(m)

    assert not r.replaced.any()
    assert r.report["sides_rebuilt"]["edges"] == 0
    assert not r.new_faces[_plane_faces(r.mesh, 0, 0.0)].any()
    assert r.report["sides_intact"] >= 1


def test_where_two_top_regions_meet_there_is_no_side():
    """Two tops meeting at a T-junction both count their shared border as open. The slab simply
    continues across it, so neither gets a wall there -- the old solidify hung one inside the
    slab from each side."""
    m = two_slabs_meeting_at_a_t_junction()
    r = _solidified(m)

    assert not r.new_faces[_plane_faces(r.mesh, 0, 40.0)].any()
    assert r.report["edges_continued"] >= 2
    assert r.report["sides_rebuilt"]["edges"] == 0


def test_the_side_rebuild_is_deterministic():
    m = slab_with_sawtooth_side()
    a, b = _solidified(m), _solidified(m)
    assert np.array_equal(a.mesh.face_v, b.mesh.face_v)
    assert np.array_equal(a.mesh.positions, b.mesh.positions)
    assert a.replaced.tolist() == b.replaced.tolist()
    assert a.new_faces.tolist() == b.new_faces.tolist()
    assert ({k: v for k, v in a.report.items() if k != "runtime_s"}
            == {k: v for k, v in b.report.items() if k != "runtime_s"})
