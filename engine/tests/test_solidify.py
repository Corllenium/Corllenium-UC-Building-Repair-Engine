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


def test_a_fin_at_the_corner_no_longer_sets_the_edge_height():
    """`two_level_slab`'s fin hangs 200 in from the open edge's corner `(0, 0, 0)`. Taking an
    edge's height from the deepest side face at either endpoint measured that edge at 200 in (the
    default ceiling's 36, then), and the cap guard had to refuse the skirt. Review I1: the height
    comes only from side faces hanging from the region's own outline -- the three 8 in skirts --
    so the edge measures 8 in, the skirt meets the slab's underside, and it stays."""
    m = two_level_slab()
    r = _solidified(m, _fast(max_thickness=1000.0))

    assert list(r.report["thickness_per_region"].values()) == [8.0]
    assert r.report["cap_guard_removed"] == 0
    new = np.nonzero(r.new_faces)[0]
    assert len(new) == 2
    z = r.mesh.positions[r.mesh.face_v[new]][:, :, 2]
    assert z.min() == pytest.approx(-8.0)


def test_the_same_fixture_is_fine_once_the_measurement_is_right():
    """Same fixture with a fin only as deep as the slab, so the open edge measures the 8 in the
    slab really is: the skirt lands exactly on the underside's plane, overhangs nothing, and the
    cap guard keeps it."""
    r = _solidified(two_level_slab(deep=8.0))
    assert list(r.report["thickness_per_region"].values()) == [8.0]
    assert r.report["cap_guard_removed"] == 0
    assert int(r.new_faces.sum()) == 2


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


@pytest.mark.parametrize("reversed_underside", [False, True])
def test_a_partial_underside_is_never_boxed_in_whatever_its_winding(reversed_underside):
    """S-C1's scenario, and review C1's failure 1. The region's three sides measure 9.8 in, so a
    bottom is invented there; the slab's real underside is only 4 in down and covers a quarter
    of the footprint, too little for `_has_bottom`. From below it is plainly visible (exposure
    about 0.3 on the side facing down), so a bottom that boxed it in would change what a person
    sees -- and the hidden pass would then delete it and ship the invented one.

    SR2 briefly let the bottom cover it as an "interior" face: it lies under the top and above
    the measured 9.8 in. The review is right that it is the slab's underside where it exists, so
    a bottom may not cover a face PARALLEL to it that the original mesh shows from outside,
    unless it is a piece of that bottom or a top surface's own underside. And winding changes
    nothing: wound into the slab (+z), the underside is seen on its BACK from below, which the
    cap guard's rule 2 used to let through unmeasured -- it now reads the original exposure of
    the side the ray met, back or front."""
    m = slab_with_partial_underside()
    if reversed_underside:
        m.face_v[8:10] = m.face_v[8:10][:, ::-1].copy()
        m.face_vt[8:10] = m.face_vt[8:10][:, ::-1].copy()
    r = _solidified(m)
    assert r.report["bottoms_added"] == 1              # invented at the measured 9.8 in
    assert r.report["cap_guard_removed"] >= 1          # and refused where it boxes in the plate

    result = fix_object(m, {}, _FAST)
    assert not result.removed_hidden[8] and not result.removed_hidden[9]
    z = sorted({round(float(v), 3) for v in
                result.mesh.positions[result.mesh.face_v].reshape(-1, 3)[:, 2]})
    assert -4.0 in z                                   # the real underside ships
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


def _planned(mesh, profile, monkeypatch):
    """`solidify` with the cap guard bypassed: every face it PLANNED, none judged -- what ships
    when the guard keeps every new face, the pieces they replace included (review part 2, M5: it
    used to report none). For tests of the extrusion rule itself, which is a different question
    from what the guard keeps."""
    from dataclasses import replace as dc_replace

    import engine.fixes.solidify as S

    def keep_all(original, solid, new_faces, *args, **kwargs):
        group = kwargs.get("replaced_group")
        replaced = (np.zeros(original.n_faces, bool) if group is None
                    else np.asarray(group)[:original.n_faces] >= 0)
        keep = np.ones(solid.n_faces, bool)
        keep[:original.n_faces] = ~replaced
        out = dc_replace(solid, face_v=solid.face_v[keep], face_vt=solid.face_vt[keep],
                         face_vn=solid.face_vn[keep], face_material=solid.face_material[keep],
                         face_line=solid.face_line[keep])
        return (out, new_faces[keep], [], 0, {"replaced": replaced, "interior_faces": [],
                                              "refused_reason": {}}, keep)

    monkeypatch.setattr(S, "_cap_guard", keep_all)
    return _solidified(mesh, profile)


def test_the_plan_replaces_the_pieces_it_would_replace(monkeypatch):
    """Review part 2, M5: `_planned` -- solidify with the cap guard bypassed -- reported no
    replaced pieces at all, so no plan test could see replacement. The plan is what ships when the
    guard keeps every new face: the sawtooth side's four teeth are replaced, and gone from its
    mesh."""
    m = slab_with_sawtooth_side()
    teeth = np.arange(m.n_faces - 6, m.n_faces - 2)
    r = _planned(m, _FAST, monkeypatch)
    assert r.replaced.tolist() == [f in teeth for f in range(m.n_faces)]
    assert r.mesh.n_faces == m.n_faces - len(teeth) + int(r.new_faces.sum())
    kept_input = r.mesh.face_v[~r.new_faces]
    assert not any(np.array_equal(row, m.face_v[t]) for t in teeth for row in kept_input)


def test_each_open_edge_is_extruded_to_its_own_measured_height(monkeypatch):
    """`slab_with_two_depths` measures 1.3 in at the two open edges touching its shallow end and
    9.8 in at the two touching its deep end. The region's single statistic (its median, 5.55 in
    here) used to be applied to all four, which hangs half of them 4 in too low and half of them
    4 in too high. Asserted on the PLAN (guard bypassed): what the cap guard then keeps is the
    next test's subject."""
    m = slab_with_two_depths()
    r = _planned(m, _fast(min_thickness=1.0), monkeypatch)

    assert r.report["skirts_added"] == 4
    assert r.report["skirt_edges_fallback"] == 0
    assert r.report["thickness_per_region"] == {"0": pytest.approx(5.55)}   # the FALLBACK only

    skirt = _skirt_faces(r)
    assert len(skirt) == 8                           # four quads
    assert _skirt_lows(r) == [-9.8] * 4 + [-1.3] * 4

    # the shallow pair hangs off the shallow (x = 0) end, the deep pair off the deep one
    for f in skirt:
        x = r.mesh.positions[r.mesh.face_v[f]][:, 0]
        low = round(float(r.mesh.positions[r.mesh.face_v[f]][:, 2].min()), 6)
        assert (float(x.min()) == 0.0) if low == -1.3 else (float(x.max()) == 60.0)


def test_skirts_hanging_below_the_bottom_are_refused_where_they_cover_a_visible_inside():
    """The same slab, judged. The bottom goes at the shallowest 1.3 in; the deep skirts hang
    8.5 in below it and cover the deep end skirt's inner side there, which nothing closes and
    which is visible from outside. They used to pass because rule 2 let every back-side cover
    through unmeasured; review C1 removed rule 2, and they are refused as covering below the
    slab's bottom. The shallow skirts and the bottom stay."""
    r = _solidified(slab_with_two_depths(), _fast(min_thickness=1.0))
    assert r.report["walls_refused"]["reasons"].get("covers_below_bottom", 0) >= 1
    assert r.report["bottoms_added"] == 1
    assert -1.3 in _skirt_lows(r)


def test_a_measured_edge_height_is_still_clamped_into_the_profile_bounds(monkeypatch):
    """Per edge now, where it used to be per region: the same 1.3 in measurement comes back as
    the default `min_thickness` of 2.0 (on the plan, guard bypassed)."""
    assert (_skirt_lows(_planned(slab_with_two_depths(), _FAST, monkeypatch))
            == [-9.8] * 4 + [-2.0] * 4)


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
    solidified mesh that has never been corrected: `slab_with_partial_underside`'s bottom boxes
    in its real underside. The point of the test is that the verdict comes from a real final
    render of the mesh that would have shipped, not from the loop's own bookkeeping."""
    r = fix_object(slab_with_partial_underside(), {}, _fast(cap_guard_max_rounds=0))

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


def _through_box(origins, direction, depth, lo, hi):
    """Per pixel: does the line of sight from the camera to the hit at `depth` pass through the
    INSIDE of the box `lo`..`hi` (a stretch of positive length)?"""
    d = np.asarray(direction, dtype=np.float64)
    with np.errstate(divide="ignore", invalid="ignore"):
        t1 = (lo - origins) / d
        t2 = (hi - origins) / d
    inside = (origins >= lo) & (origins <= hi)
    t_in = np.where(d == 0.0, np.where(inside, -np.inf, np.inf), np.minimum(t1, t2)).max(axis=-1)
    t_out = np.where(d == 0.0, np.where(inside, np.inf, -np.inf), np.maximum(t1, t2)).min(axis=-1)
    return np.maximum(t_in, 0.0) + 1e-6 < np.minimum(t_out, depth)


def test_a_railing_seen_through_an_open_slab_is_hidden_only_through_the_closed_slab():
    """The same railing with the slab's bottom missing too, so from below a person sees the
    railing's inner face THROUGH the slab: in at its open bottom, out at its open side.

    SR2 asserted that not one of those pixels may change, so whatever closing face covered that
    view was refused -- which is only possible with the slab left open, bottom or side. Brief 10
    item 1 judges a slab's new shell together: the wall and the bottom are both kept, and the slab
    is a solid, so nothing is seen THROUGH it any more. The railing is still never replaced, and a
    pixel of it (or of the wall 6 in out) changes only where the line of sight to it crosses the
    slab's volume -- everywhere else it is exactly what it was."""
    m = slab_with_railing_outside(with_bottom=False)
    outside = np.arange(m.n_faces - 8, m.n_faces)
    r = _solidified(m)

    assert r.report["cap_guard_passed"] is True
    assert not r.replaced[outside].any()
    assert r.new_faces[_plane_faces(r.mesh, 0, 0.0)].all() and len(_plane_faces(r.mesh, 0, 0.0))
    assert len(_bottom_faces(r)) >= 2
    positions_w, remap = weld_exact(r.mesh.positions, r.mesh.coord_decimals)
    centre = (positions_w.min(axis=0) + positions_w.max(axis=0)) / 2.0
    pc = positions_w - centre
    lo, hi = np.array([0.0, 0.0, -8.0]) - centre, np.array([40.0, 40.0, 0.0]) - centre
    rows = _reference_row(r, np.arange(m.n_faces))
    seen = through = changed_through = changed_elsewhere = 0
    for view in VIEWS_26:
        b = ortho_first_hit(pc, remap[m.face_v], np.arange(m.n_faces), view, pc, (120, 80))
        a = ortho_first_hit(pc, remap[r.mesh.face_v], np.arange(r.mesh.n_faces), view, pc,
                            (120, 80))
        mine = np.isin(b.tri, outside)
        crosses = _through_box(b.origins, b.direction, b.depth, lo, hi) & mine
        changed = mine & (a.tri != np.where(mine, rows[np.where(mine, b.tri, 0)], -2))
        seen += int(mine.sum())
        through += int(crosses.sum())
        changed_through += int((changed & crosses).sum())
        changed_elsewhere += int((changed & ~crosses).sum())
    assert seen > through > 0
    assert changed_elsewhere == 0
    assert changed_through > 0                 # seen through the slab: hidden by the closed slab


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


def test_a_side_is_measured_at_its_own_depth_however_shallow_its_edge_measured():
    """File A, region 11: one outline edge measured 11.72 in from the side faces at its
    endpoints, while the side face lying in its plane goes 29.52 in deep. The band search stopped
    at `measured + band + 1` (15.22 in) and reported THAT as the side's depth -- the bottom was
    then placed at 15.22 in, 14.3 in above the slab's real partial bottom, and the merge's
    0.004 in border shrink exposed it. The side's depth is its own faces' depth."""
    from engine.fixes.solidify import _Faces, _wall_pieces
    m = slab_with_three_skirts(height=30.0, with_bottom=True)
    topo = analyse_topology(m)
    faces = _Faces(topo, np.array([0, 1]))
    pa, pb = np.array([40.0, 0.0, 0.0]), np.array([0.0, 0.0, 0.0])
    pieces, coverage, depth = _wall_pieces(faces, pa, pb, np.array([0.0, -1.0, 0.0]),
                                           5.0, 5.0, 2.5, set(),
                                           max_depth=FixProfile().max_thickness)
    assert depth == pytest.approx(30.0)
    assert coverage == pytest.approx(1.0)
    assert sorted(pieces) == [2, 3]            # the y = 0 skirt's two triangles


def test_a_wall_below_a_gap_is_not_part_of_the_side_above_it():
    """The side is what hangs from the top edge. A second wall in the same plane further down,
    separated from it by a gap -- the next level's side, say -- does not make this side deeper,
    and so does not make a whole side look broken."""
    from engine.fixes.solidify import _Faces, _wall_pieces
    m = slab_with_three_skirts(height=8.0, with_bottom=True)
    P = m.positions.tolist()
    uvs, fv, fvt, fm = m.uvs.tolist(), m.face_v.tolist(), m.face_vt.tolist(), m.face_material.tolist()
    r = len(P)
    P += [[0.0, 0.0, -20.0], [40.0, 0.0, -20.0], [40.0, 0.0, -30.0], [0.0, 0.0, -30.0]]
    from engine.tests.fixtures.build import _mesh, _quads
    _quads(P, uvs, fv, fvt, fm, [(r, r + 3, r + 2, r + 1)])       # a lower wall, y = 0, -y
    m2 = _mesh("slab_over_a_lower_wall", P, uvs, fv, fvt, face_material=fm)
    faces = _Faces(analyse_topology(m2), np.array([0, 1]))
    pieces, coverage, depth = _wall_pieces(
        faces, np.array([40.0, 0.0, 0.0]), np.array([0.0, 0.0, 0.0]), np.array([0.0, -1.0, 0.0]),
        8.0, 8.0, 2.5, set(), max_depth=FixProfile().max_thickness)
    assert depth == pytest.approx(8.0)
    assert coverage == pytest.approx(1.0)


def test_a_top_that_continues_under_a_landing_is_one_slab_with_it():
    """File A, region 11: the lower landing's top continues under the upper landing, where it
    sees no sky and so was never a top surface -- its volume was unknown, the rib-like wall under
    it counted as OUTSIDE, and region 11's new bottom was refused over the views of it. Once one
    of its faces went, the bottom's pieces came back and the rest of it failed against them in
    its own plane. A surface the top CONTINUES into is part of that top: it is processed as one,
    its volume is inside, and it gets its own bottom."""
    from engine.tests.fixtures.build import slab_continuing_under_a_landing
    m = slab_continuing_under_a_landing()
    r = _solidified(m)

    assert r.report["top_regions_continued"] == 1          # B, under the landing
    assert r.report["cap_guard_removed"] == 0
    assert r.report["bottoms_added"] == 2                   # under A and under B
    assert r.report["interior_faces_covered"] >= 2          # the rib
    new = r.mesh.positions[r.mesh.face_v[r.new_faces]]
    assert np.allclose(new[:, :, 2], -10.0)                 # the bottoms, and nothing else


def test_fix_object_seals_the_slab_under_the_landing_and_removes_the_rib():
    from engine.tests.fixtures.build import slab_continuing_under_a_landing
    m = slab_continuing_under_a_landing()
    r = fix_object(m, {}, _FAST)
    assert r.passed is True
    rib = (np.abs(r.mesh.positions[r.mesh.face_v][:, :, 0] - 60.0) < 1e-6).all(axis=1)
    assert not rib.any()
    assert r.backface_px["final"]["total"] == 0


def test_walls_this_run_built_do_not_measure_a_duplicate_layers_sides():
    """A top drawn twice, the second layer in another material and cut into its own regions,
    all seeing sky. The first layer's walls also close the second layer's coincident edges, so
    those sides count as whole -- but a wall this run invented is not a measurement: counted as
    one, it gave 10 of the layer's regions a bottom at the 2 in fallback depth."""
    from engine.tests.fixtures.build import stacked_duplicate_slab
    m = stacked_duplicate_slab(nx=3, ny=3, top_material=1)
    r = _solidified(m)
    assert r.report["top_regions_continued"] == 0
    # no side face anywhere, so no depth was ever measured: no bottom at a made-up depth, for
    # either layer (the walls one layer built do not measure the other's sides)
    assert r.report["bottoms_added"] == 0


def test_the_faces_one_closing_face_is_made_of_share_one_texture_map():
    """A textured material splits a plane into UV classes (`engine.topo.planes.cluster_uv`), and
    the merge only rebuilds a class as one polygon. Every invented triangle used to be projected
    from its OWN first corner, so no two of them shared a map: file A's region 11 bottom came out
    as a fan of separate triangles, every edge drawn. All the invented faces in one plane are
    projected from ONE origin now, so they are one UV class and merge."""
    from engine.topo.planes import cluster_uv, plane_basis
    r = _solidified(slab_with_sawtooth_side_wall_only())
    new = np.nonzero(r.new_faces)[0]
    tri = r.mesh.positions[r.mesh.face_v[new]]
    n = _face_normals(r.mesh)[new]
    for normal in ([-1.0, 0.0, 0.0], [0.0, 0.0, -1.0]):
        rows = np.nonzero((n @ np.array(normal)) > 0.99)[0]
        assert len(rows) >= 2
        e1, e2 = plane_basis(np.array(normal))
        xy = np.stack([tri[rows] @ e1, tri[rows] @ e2], axis=2)
        uv = r.mesh.uvs[r.mesh.face_vt[new[rows]]]
        area = 0.5 * np.linalg.norm(np.cross(tri[rows, 1] - tri[rows, 0],
                                              tri[rows, 2] - tri[rows, 0]), axis=1)
        labels, fits = cluster_uv(xy, uv, area)
        assert len(fits) == 1, normal


def test_a_closed_slab_on_a_textured_material_merges_its_new_bottom_into_one_polygon():
    m = slab_with_three_skirts()
    r = fix_object(m, {"m0": 100.0}, _FAST)          # std 100: textured, not flat
    bottom = [f for f in range(r.mesh.n_faces)
              if np.allclose(r.mesh.positions[r.mesh.face_v[f]][:, 2], -8.0)]
    assert len(bottom) == 2
    assert r.face_region_final[bottom[0]] >= 0
    assert r.face_region_final[bottom[0]] == r.face_region_final[bottom[1]]


def slab_with_sawtooth_side_wall_only():
    """`slab_with_sawtooth_side` without its bottom, so solidify builds a wall AND a bottom."""
    from engine.tests.fixtures.build import slab_with_sawtooth_side
    m = slab_with_sawtooth_side()
    tri = m.positions[m.face_v]
    keep = ~(np.abs(tri[:, :, 2] + 8.0) < 1e-9).all(axis=1)
    from dataclasses import replace
    return replace(m, face_v=m.face_v[keep], face_vt=m.face_vt[keep], face_vn=m.face_vn[keep],
                   face_material=m.face_material[keep], face_line=m.face_line[keep])


# ------------------------------------ SR4 (review C1): the cap guard measures back-side covers


def _closed_slab_with_split_side(inward: bool):
    """Review probe `probe_duplicate_skirt.py`: a closed 40 x 40 x 8 in slab whose x = 0 side
    EXISTS, split at the midpoint of its top edge, so the top's outline edge 0-3 is used by the
    top alone (edge-table count 1) -- file B's region 38 in miniature. `inward` winds that side
    into the slab. Faces 8-11 are the side."""
    from engine.tests.fixtures.build import _mesh, _quads
    s, h = 40.0, 8.0
    P = [[0, 0, 0], [s, 0, 0], [s, s, 0], [0, s, 0],
         [0, 0, -h], [s, 0, -h], [s, s, -h], [0, s, -h],
         [0, s / 2, 0], [0, s / 2, -h]]
    uvs, fv, fvt, fm = [], [], [], []
    _quads(P, uvs, fv, fvt, fm, [(0, 1, 2, 3), (0, 4, 5, 1), (1, 5, 6, 2), (2, 6, 7, 3),
                                 (0, 8, 9, 4), (8, 3, 7, 9), (4, 7, 6, 5)])
    fv = [list(f) for f in fv]
    if inward:
        for k in (8, 9, 10, 11):
            fv[k] = fv[k][::-1]
    return _mesh("closed_slab_with_split_side", P, uvs, fv, fvt, face_material=fm)


@pytest.mark.parametrize("inward", [False, True])
def test_no_skirt_is_laid_over_an_existing_side_whatever_its_winding(inward):
    """Review C1's failure 2: with the side wound inward, a skirt laid exactly over it passed
    the cap guard on rule 2 and shipped as a z-fighting double layer. The side is whole, so
    nothing is built on it, and the shipped x = 0 side is the side itself, once."""
    m = _closed_slab_with_split_side(inward)
    r = _solidified(m)
    assert not r.new_faces[_plane_faces(r.mesh, 0, 0.0)].any()
    result = fix_object(m, {}, _FAST)
    final = result.mesh.positions[result.mesh.face_v]
    on_x0 = np.all(np.isclose(final[:, :, 0], 0.0), axis=1)
    area = float(sum(0.5 * np.linalg.norm(np.cross(t[1] - t[0], t[2] - t[0]))
                     for t in final[on_x0]))
    assert area == pytest.approx(40.0 * 8.0)
    assert result.passed is True


def test_a_new_face_that_coincides_with_an_existing_face_is_refused():
    """Coincidence is decided by a coplanar-overlap test, not by pixels: the renderer resolves a
    coincident pair as a tie, so no pixel changes and no pixel rule can see it. A plate lying in
    the plane the new bottom will take, reaching in under the slab from outside (centroid
    outside the footprint, so it is not one of that bottom's pieces), would be doubled by it."""
    from engine.tests.fixtures.build import _mesh, _quads
    m = slab_with_three_skirts()
    P = m.positions.tolist()
    uvs, fv, fvt = m.uvs.tolist(), m.face_v.tolist(), m.face_vt.tolist()
    fm = m.face_material.tolist()
    b = len(P)
    P += [[-30.0, 5.0, -8.0], [10.0, 5.0, -8.0], [10.0, 35.0, -8.0], [-30.0, 35.0, -8.0]]
    _quads(P, uvs, fv, fvt, fm, [(b, b + 3, b + 2, b + 1)])            # a plate, -z
    m2 = _mesh("slab_over_a_plate", P, uvs, fv, fvt, face_material=fm)
    r = _solidified(m2)
    assert r.report["bottom_faces_refused"]["reasons"].get("coincides_with_existing_face", 0) >= 1
    # no kept new face overlaps the plate in its plane
    plate = shapely.Polygon([(-30, 5), (10, 5), (10, 35), (-30, 35)])
    new = r.mesh.positions[r.mesh.face_v[r.new_faces]]
    at_plate = [shapely.Polygon(t[:, :2]) for t in new if np.allclose(t[:, 2], -8.0)]
    assert all(p.intersection(plate).area < 1e-6 for p in at_plate)


# ------------------------ SR5 (review I1): an open edge takes its height from the slab's own sides


def _thin_slab_beside_a_deep_wall():
    """Review probe `probe_deep_corner.py`: a 2 in slab (top and three 2 in outward skirts, the
    x = 0 edge open) whose corner (0, 0, 0) is also the top corner of a 30 in retaining wall
    running outward in -x, in the plane y = 0. Faces 0-7 the slab, 8-9 the wall."""
    from engine.tests.fixtures.build import _mesh, _quads
    s, h, deep = 40.0, 2.0, 30.0
    P = [[0, 0, 0], [s, 0, 0], [s, s, 0], [0, s, 0],
         [0, 0, -h], [s, 0, -h], [s, s, -h], [0, s, -h],
         [-10, 0, 0], [-10, 0, -deep], [0, 0, -deep]]
    uvs, fv, fvt, fm = [], [], [], []
    _quads(P, uvs, fv, fvt, fm, [(0, 1, 2, 3), (0, 4, 5, 1), (1, 5, 6, 2), (2, 6, 7, 3),
                                 (8, 9, 10, 0)])
    return _mesh("thin_slab_beside_a_deep_wall", P, uvs, fv, fvt, face_material=fm)


def test_a_thin_slab_touching_a_deep_wall_stays_thin():
    """Review I1: the retaining wall touches the open edge's corner, but it does not hang from
    the slab's outline -- its top edge runs away from the slab -- so it measures nothing. The
    edge measures 2 in from the slab's own skirts, the bottom goes at 2 in, and nothing is built
    below the slab. (It used to become a 30 in box, with every guard passing.)"""
    m = _thin_slab_beside_a_deep_wall()
    r = fix_object(m, {}, _FAST)
    sr = r.solidify_report
    assert sr["thickness_per_region"] == {"0": 2.0}
    assert sr["bottom_depth_per_region"] == {"0": 2.0}
    used = r.mesh.positions[r.mesh.face_v]
    over_slab = np.all(used[:, :, 0] >= -1e-9, axis=1)
    assert float(used[over_slab][:, :, 2].min()) == pytest.approx(-2.0)
    assert sr["regions_deeper_than_own_sides"] == []
    assert r.passed is True


def test_a_side_shallower_than_the_slabs_representative_depth_is_completed():
    """The x = 40 side is only 4 in deep, the y = 0 and y = 40 sides 8 in, and x = 0 is open (its
    corners measure 8 from the two long sides).

    SR5 (review I1) put the bottom no deeper than the region's shallowest existing side, closed
    sides included -- 4 in here -- and the 8 in sides and wall hung below it as fins. SR6 item 2
    replaced that rule: a band shallower than the slab's REPRESENTATIVE side depth (the depth
    reached by most of its own side length, 8 in here: 80 of its 120 in) does not cap the bottom.
    The bottom goes at 8 in; the 4 in side above it is then not a whole side of this slab but a
    band over a missing one, so it is completed to 8 in like any broken side, and the band goes
    with it. Through the cap guard (brief 10 item 1; SR6 asserted only the plan): nothing of the
    new shell is refused. The report still names the region -- a wall and a bottom deeper than its
    shallowest side."""
    from engine.tests.fixtures.build import _mesh, _quads
    s = 40.0
    P = [[0, 0, 0], [s, 0, 0], [s, s, 0], [0, s, 0],
         [0, 0, -8], [s, 0, -8], [s, s, -8], [0, s, -8], [s, 0, -4], [s, s, -4]]
    uvs, fv, fvt, fm = [], [], [], []
    _quads(P, uvs, fv, fvt, fm, [(0, 1, 2, 3),              # top, +z
                                 (0, 4, 5, 1),              # y = 0, 8 in, -y
                                 (2, 6, 7, 3),              # y = s, 8 in, +y
                                 (1, 8, 9, 2)])             # x = s, 4 in, +x
    m = _mesh("slab_with_a_shallow_side", P, uvs, fv, fvt, face_material=fm)
    r = _solidified(m, _fast(min_thickness=1.0))
    assert r.report["cap_guard_passed"] is True
    assert r.report["walls_refused"]["faces"] == 0
    assert r.report["bottom_faces_refused"]["faces"] == 0
    assert r.report["representative_side_per_region"] == {"0": pytest.approx(8.0)}
    assert r.report["bottom_depth_per_region"] == {"0": pytest.approx(8.0)}
    assert r.replaced[6] and r.replaced[7]                   # the 4 in band went with the wall
    completed = [f for f in _plane_faces(r.mesh, 0, s) if r.new_faces[f]]
    assert completed
    z = r.mesh.positions[r.mesh.face_v[completed]][:, :, 2]
    assert z.max() == pytest.approx(0.0) and z.min() == pytest.approx(-8.0)
    assert len(_bottom_faces(r)) >= 2
    deeper = r.report["regions_deeper_than_own_sides"]
    assert [d["region"] for d in deeper] == [0]
    assert deeper[0]["shallowest_side"] == pytest.approx(4.0)
    assert deeper[0]["representative_side"] == pytest.approx(8.0)
    assert deeper[0]["deepest_wall"] == pytest.approx(8.0)


# ------------------------------------------------ M1: the cap guard's cut-off path, verified


def test_a_cap_guard_cut_off_after_one_round_verifies_what_it_hands_back():
    """Review M1: at 0 rounds the returned mesh and the pre-removal mesh are the same mesh, so a
    verification rendered on a stale `keep` would still pass the S-I2 test above. At ONE round,
    round 0 removes faces and the loop runs out of rounds -- and it is the appended round 1, a
    render of the mesh actually handed back, that makes `cap_guard_passed` True."""
    r = _solidified(slab_with_partial_underside(), _fast(cap_guard_max_rounds=1))
    history = r.report["cap_guard"]
    assert len(history) == 2
    assert history[0]["round"] == 0 and history[0]["removed"] > 0
    assert history[0]["failing_pixels"] > 0
    assert history[-1]["round"] == 1
    assert history[-1]["failing_pixels"] == 0 and history[-1]["removed"] == 0
    assert r.report["cap_guard_passed"] is True


# --------------------------------------------- SR6 item 2: a thin lip never sets a slab's bottom


def test_a_lip_never_sets_the_slabs_bottom():
    """`slab_with_a_lip`: sides 12 in deep on three edges; the fourth is open but for a 2 in lip
    along 8 of its 40 in. SR5 put the bottom no deeper than the shallowest own side -- the lip --
    so a 12 in slab got a bottom 2 in down, inside itself (file B's ramp: 5.62 in; its landing,
    region 92: 0.26 in). The lip measures nothing now: the open edge takes the 12 in its corners
    measure, the lip is replaced by that wall, and the bottom goes at the slab's representative
    side depth -- 12 in, reached by 120 of its 128 in of own side."""
    from engine.tests.fixtures.build import slab_with_a_lip
    r = _solidified(slab_with_a_lip())
    assert r.report["representative_side_per_region"] == {"0": pytest.approx(12.0)}
    assert r.report["bottom_depth_per_region"] == {"0": pytest.approx(12.0)}
    assert r.report["bottoms_added"] == 1
    assert r.replaced[8] and r.replaced[9]                     # the lip went with the wall
    wall = [f for f in _plane_faces(r.mesh, 0, 0.0) if r.new_faces[f]]
    assert wall
    z = r.mesh.positions[r.mesh.face_v[wall]][:, :, 2]
    assert z.max() == pytest.approx(0.0) and z.min() == pytest.approx(-12.0)


def test_a_riser_standing_up_from_the_top_is_not_a_side():
    """A face going UP from the outline -- the step to the next landing -- was counted as an own
    side by its vertical extent, and capped the bottom at it: file A's lower landing (region 11)
    got its bottom 9.85 in down from its risers, 19.67 in above its real partial bottom. A side is
    measured by how far it reaches BELOW the edge it lies along; a riser reaches nothing."""
    from engine.tests.fixtures.build import slab_with_a_lip
    r = _solidified(slab_with_a_lip(with_lip=False, riser=5.0))
    assert r.report["representative_side_per_region"] == {"0": pytest.approx(12.0)}
    assert r.report["bottom_depth_per_region"] == {"0": pytest.approx(12.0)}


# ----------------------------------------------- SR6 item 1: a sloped top's walls follow the ground


def _new_faces_on_y0(r):
    return [f for f in _plane_faces(r.mesh, 1, 0.0) if r.new_faces[f]]


def _lowest_z_at(r, faces, x, tol=1e-6):
    """The lowest z of `faces`' corners lying on the vertical line x = `x`."""
    tri = r.mesh.positions[r.mesh.face_v[faces]].reshape(-1, 3)
    on = np.abs(tri[:, 0] - x) <= tol
    return float(tri[on, 2].min()) if on.any() else None


def test_a_ramp_side_whose_pieces_do_not_reach_the_top_is_replaced_down_to_its_underside():
    """File B's ramp, the owner's photograph: along its 85 in sloped edge the broken side's pieces
    are only its LOWER part, 28 to 39.4 in down, just above the ramp's underside (39.37 in below
    its top everywhere). Nothing hung from the top edge, so nothing was taken as a piece; the wall
    lay ON the pieces and the coincidence test (review C1) refused it -- the sawtooth stayed.

    `sloped_slab(side="low")`: the underside runs 12 in below the sloped top; the y = 0 side is
    only a strip 8 to 12 in down over the edge's upper half. The wall goes from the top edge down
    to the slab's lower surface at EACH end -- 12 in at both, the underside being parallel -- and
    the strip, inside that wall, is replaced by it."""
    from engine.tests.fixtures.build import sloped_slab
    m = sloped_slab(side="low")
    r = _solidified(m)
    assert r.replaced[10] and r.replaced[11]                  # the strip went with the wall
    wall = _new_faces_on_y0(r)
    assert wall
    assert _lowest_z_at(r, wall, 0.0) == pytest.approx(-12.0)
    assert _lowest_z_at(r, wall, 80.0) == pytest.approx(20.0 - 12.0)
    assert r.report["walls_to_lower_surface"]["walls"] == 1


def test_a_wall_under_a_sloped_edge_goes_down_to_a_flat_underside_at_each_end():
    """A sloped top over a FLAT underside -- a wedge on the ground. A wall at one constant depth is
    either too shallow at the high end (a gap under it) or too deep at the low end (a fin hanging
    below the underside, covering what lies outside the slab). It goes to the lower surface at
    EACH end: 12 in at x = 0, 32 in at x = 80 -- a trapezoid -- and the slab's volume, which the
    cap guard reads, follows the same surface, so the wall is kept."""
    from engine.tests.fixtures.build import sloped_slab
    m = sloped_slab(flat_underside=True)
    r = _solidified(m)
    wall = _new_faces_on_y0(r)
    assert wall
    assert _lowest_z_at(r, wall, 0.0) == pytest.approx(-12.0)
    assert _lowest_z_at(r, wall, 80.0) == pytest.approx(-12.0)
    z = r.mesh.positions[r.mesh.face_v[wall]][:, :, 2]
    assert z.min() == pytest.approx(-12.0)                    # nothing below the underside
    assert r.report["walls_to_lower_surface"]["trapezoids"] == 1
    assert r.report["bottoms_added"] == 0 and r.report["bottom_exists"] == 1


def test_a_block_face_inside_the_slab_does_not_tilt_its_lower_surface():
    """41 of the 196 rays file B's ramp sends down to find its lower surface meet a block face
    inside it first, some of them only 0.4 to 0.6 in above the underside. A plane fitted to every
    point met, dropping the far ones and fitting again, came out tilted: the ramp's walls were
    planned 34.8 to 37.2 in deep against its 39.37 in, their covers were refused as below the
    slab, and its whole side was judged broken. The lower surface is the one surface most of the
    rays meet (the ramp's underside takes 154 of the 196), fitted to the points met on it alone.

    Here 45 % of the slab's top has a plate 2 in above the underside: the wall still reaches the
    underside, 12 in down, at both ends."""
    from engine.tests.fixtures.build import sloped_slab
    r = _solidified(sloped_slab(inner_plate=(0.0, 36.0, 2.0)))
    wall = _new_faces_on_y0(r)
    assert wall
    assert _lowest_z_at(r, wall, 0.0) == pytest.approx(-12.0)
    assert _lowest_z_at(r, wall, 80.0) == pytest.approx(20.0 - 12.0)


def test_a_floor_below_a_thin_slab_is_not_its_lower_surface():
    """Review I1's protection, for the lower surface: a 2 in slab (three 2 in skirts, one edge
    open) 20 in above a floor. The floor is found straight below it, but the slab's own sides end
    18 in above it: it is the ground under the slab, not the slab's underside, and the open edge's
    wall is 2 in deep, not 20.

    Nor is the floor the slab's EXISTING bottom (brief 10 item 1): taken for one, no bottom was
    built, and through the slab's open underside the 2 in wall covered the floor outside the
    slab's footprint -- the cap guard refused it, and SR6 could assert only the plan. The slab
    gets its own bottom at 2 in, and through the guard the wall and the bottom are kept together:
    each covers only what was seen through the other's opening."""
    from engine.tests.fixtures.build import _mesh, _quads
    s = 40.0
    P = [[0, 0, 0], [s, 0, 0], [s, s, 0], [0, s, 0],
         [0, 0, -2], [s, 0, -2], [s, s, -2], [0, s, -2],
         [-20, -20, -20], [s + 20, -20, -20], [s + 20, s + 20, -20], [-20, s + 20, -20]]
    uvs, fv, fvt, fm = [], [], [], []
    _quads(P, uvs, fv, fvt, fm, [(0, 1, 2, 3),                  # top, +z
                                 (4, 5, 1, 0),                  # y = 0, -y
                                 (5, 6, 2, 1),                  # x = s, +x
                                 (6, 7, 3, 2),                  # y = s, +y
                                 (8, 9, 10, 11)])               # the floor, +z
    m = _mesh("thin_slab_over_a_floor", P, uvs, fv, fvt, face_material=fm)
    r = _solidified(m, _FAST)
    assert r.report["cap_guard_passed"] is True
    assert r.report["walls_to_lower_surface"]["walls"] == 0
    assert r.report["bottom_exists"] == 0 and r.report["bottoms_added"] == 1
    assert r.report["walls_refused"]["faces"] == 0
    assert r.report["bottom_faces_refused"]["faces"] == 0
    wall = [f for f in _plane_faces(r.mesh, 0, 0.0) if r.new_faces[f]]
    assert wall
    z = r.mesh.positions[r.mesh.face_v[wall]][:, :, 2]
    assert z.min() == pytest.approx(-2.0)
    bottom = _bottom_faces(r)
    assert bottom
    assert np.allclose(r.mesh.positions[r.mesh.face_v[bottom]][:, :, 2], -2.0)


# ------------------------------------------ SR6 item 3: an underside is not a top a top runs into


def test_an_underside_met_in_a_tops_plane_is_not_taken_for_a_top():
    """File A's merge was rolled back on a pixel where faces of region 57 had been deleted. Region
    57 is no top: it is a slab's UNDERSIDE (every face has the slab's own top 9.83 in above it and
    nothing below), met in its plane by a top's edge, so SR2's continuation took it for a top
    running on -- and built a bottom 2 in below it, which the cap guard allowed (it read the space
    under the "top" as the slab's inside) and which hid the real underside for the hidden pass to
    delete. 64 regions of file A and 5 of file B are such undersides: every own side of each
    stands UP from its outline, where a top that runs on under a landing (file A's regions 9 and
    784) has its sides hanging below.

    `slab_beside_a_lower_top`: the plate's x = 40 edge meets the box's underside plane. The
    underside is not processed, nothing is built under the box, and its real underside is
    neither replaced nor covered."""
    from engine.tests.fixtures.build import slab_beside_a_lower_top
    r = _solidified(slab_beside_a_lower_top())
    new = np.nonzero(r.new_faces)[0]
    tri = r.mesh.positions[r.mesh.face_v[new]]
    assert [f for f, t in zip(new, tri) if t[:, 0].mean() < 40.0 - 1e-6] == []
    assert r.report["undersides_not_tops"] == 1
    assert not r.replaced[2] and not r.replaced[3]


def test_a_top_edge_that_ran_into_an_underside_only_is_a_side():
    """The same plate with no side at the box: its x = 40 edge ran only into the box's underside,
    which is no top, so it does not continue -- it is a side, and it gets its 8 in wall, and the
    plate its bottom.

    Through the cap guard (brief 10 item 1). The guard used to judge each new face by what the
    input showed at its pixels -- a mesh without the OTHER new faces -- so the bottom was refused
    for covering the box's underside seen through the wall's opening (outside the plate), and then
    the wall for covering it through the bottom's: nothing of the plate's shell was kept. Both are
    kept now, because every such pixel is seen THROUGH the plate: in at one kept face of its shell
    and out at another."""
    from engine.tests.fixtures.build import slab_beside_a_lower_top
    r = _solidified(slab_beside_a_lower_top(), _FAST)
    assert r.report["cap_guard_passed"] is True
    assert r.report["edges_continued"] == 0
    assert r.report["walls_refused"]["faces"] == 0
    assert r.report["bottom_faces_refused"]["faces"] == 0
    assert sum(h.get("through_shell_px", 0) for h in r.report["cap_guard"]) > 0
    wall = [f for f in _plane_faces(r.mesh, 0, 40.0) if r.new_faces[f]]
    assert wall
    z = r.mesh.positions[r.mesh.face_v[wall]][:, :, 2]
    assert z.max() == pytest.approx(0.0) and z.min() == pytest.approx(-8.0)
    bottom = _plane_faces(r.mesh, 2, -8.0)
    assert len(bottom) >= 2 and r.new_faces[bottom].all()
    assert _covered_area(r.mesh, bottom, [0, 1]) == pytest.approx(40.0 * 40.0)
    new = np.nonzero(r.new_faces)[0]
    tri = r.mesh.positions[r.mesh.face_v[new]]
    assert [f for f, t in zip(new, tri) if t[:, 0].mean() < 40.0 - 1e-6] == []
    # ...and it SHIPS (review part 2, M5: the plan was pinned, never what ships): the plate is a
    # closed solid in the final mesh, and the box beside it is untouched
    m = slab_beside_a_lower_top()
    shipped = fix_object(m, {}, _FAST)
    assert shipped.passed is True
    final = shipped.mesh
    assert _covered_area(final, _plane_faces(final, 0, 40.0), [1, 2]) == pytest.approx(
        40.0 * 10.0 + 40.0 * 8.0)                              # the box's side over the plate's wall
    assert _covered_area(final, _plane_faces(final, 2, -8.0), [0, 1]) == pytest.approx(1600.0)
    assert _covered_area(final, _plane_faces(final, 2, 0.0), [0, 1]) == pytest.approx(3200.0)


def test_a_shell_is_refused_together_when_one_of_its_faces_fails(monkeypatch):
    """Brief 10 item 1, the other half: the plate's bottom may cover what it covers only because
    the wall closes the plate on the far side of every such ray. With the wall refused for a reason
    of its own (forced here), those rays leave the plate through its opening again, so the bottom
    covers the box's underside outside the plate, and is refused with it."""
    import engine.fixes.solidify as S
    from engine.tests.fixtures.build import slab_beside_a_lower_top
    real = S._coincident_new_faces

    def refuse_the_wall(solid, new_faces, new_group, replaced_group, ok_input, tol):
        out = real(solid, new_faces, new_group, replaced_group, ok_input, tol)
        tri = solid.positions[solid.face_v]
        out |= new_faces & np.isclose(tri[:, :, 0], 40.0).all(axis=1)
        return out

    monkeypatch.setattr(S, "_coincident_new_faces", refuse_the_wall)
    r = _solidified(slab_beside_a_lower_top(), _FAST)
    assert r.report["cap_guard_passed"] is True
    assert not r.new_faces.any()
    assert r.report["bottom_faces_refused"]["reasons"] == {"covers_outside_footprint": 2}


def test_a_fin_below_the_slab_is_still_refused_face_by_face():
    """Brief 10 item 1 keeps the per-face refusal for new faces OUTSIDE the slab's volume.
    `slab_with_fins_beside_a_post`: the two walls touching the deep end hang 8.5 in below the
    1.3 in bottom, fins facing each other across the slab, and a post stands beyond the far one.
    A ray from -y at the post's height enters the near fin, runs UNDER the slab -- outside it --
    and leaves through the far fin: no view through the slab. The fins are refused for what they
    cover below it, nothing is kept below the bottom, and the post looks exactly as it did."""
    from engine.tests.fixtures.build import slab_with_fins_beside_a_post
    m = slab_with_fins_beside_a_post()
    r = _solidified(m, _fast(min_thickness=1.0))
    assert r.report["cap_guard_passed"] is True
    assert r.report["walls_refused"]["reasons"].get("covers_below_bottom", 0) >= 1
    new = r.mesh.positions[r.mesh.face_v[r.new_faces]]
    assert float(new[:, :, 2].min()) == pytest.approx(-1.3)
    post = np.array([m.n_faces - 2, m.n_faces - 1])
    seen, changed = _unchanged_pixels(m, r, post)
    assert seen > 0 and changed == 0


# ------------------------------- brief 10 item 2: max_thickness from the files' own side depths


@pytest.mark.parametrize("depth", [39.37, 49.21])
def test_a_one_metre_block_is_not_clamped_to_36_in(depth):
    """These files are LittleTiles blocks in 9.84 in (25 cm) steps. File B's upper landing (region
    92) and four more of its regions are 39.37 in (1 m) deep by most of their own sides, and file
    A's region 852 is 49.21 in (1.25 m) deep by every one of its own sides -- and `max_thickness`
    was 36 in, so their walls and bottoms stopped 3.37 in and 13.21 in short of their sides' feet.
    The open edge's wall and the bottom now reach the slab's own depth."""
    r = _solidified(slab_with_three_skirts(size=40.0, height=depth))
    assert r.report["thickness_per_region"] == {"0": pytest.approx(depth)}
    assert r.report["bottom_depth_per_region"] == {"0": pytest.approx(depth)}
    wall = [f for f in _plane_faces(r.mesh, 0, 0.0) if r.new_faces[f]]
    assert wall
    assert r.mesh.positions[r.mesh.face_v[wall]][:, :, 2].min() == pytest.approx(-depth)
    bottom = _bottom_faces(r)
    assert bottom and np.allclose(r.mesh.positions[r.mesh.face_v[bottom]][:, :, 2], -depth)


def test_a_side_deeper_than_any_slab_of_the_files_is_still_clamped(monkeypatch):
    """The ceiling stays a ceiling: a 60 in skirt -- deeper than any own side either file has but
    one 39.4 in run -- measures the open edge at `max_thickness` (on the plan, guard bypassed)."""
    r = _planned(slab_with_three_skirts(size=40.0, height=60.0), _FAST, monkeypatch)
    assert r.report["thickness_per_region"] == {"0": pytest.approx(FixProfile().max_thickness)}
    assert FixProfile().max_thickness < 60.0


# ------------------ review part 2, C2 (brief 10 item 3): top or underside, by looking above and below


def test_an_underside_with_a_neighbours_side_along_it_is_not_taken_for_a_top():
    """R2-C2 (`probe_underside_with_hanging_neighbour.py`). B's underside is flush with L's top, so
    L's edge runs on into it, and L's own 8 in side hangs along the underside's x = 40 edge. SR6's
    test (an underside has no own side hanging) took it for a top: three 8 in walls and a bottom
    8 in down were built under B, the cap guard let them through, and the hidden pass deleted B's
    real underside -- 1,600 sq in of invented floor shipped 8 in low, `passed` True. On file A the
    same fired at region 33: all 16 of its faces (19,777 sq in, visible on the input) deleted.

    A side hanging along an edge the top CONTINUES across is the neighbour's; no body hangs below
    B's underside, and the slab it belongs to is above it: nothing is built under it, and it ships."""
    from engine.tests.fixtures.build import overhang_beside_a_slab
    m = overhang_beside_a_slab()
    r = fix_object(m, {}, _FAST)
    assert r.passed is True
    assert r.solidify_report["undersides_not_tops"] == 1
    assert not r.replaced_input[[12, 13]].any()
    rows = np.cumsum(~r.replaced_input) - 1
    assert not r.removed_hidden[rows[[12, 13]]].any()
    n_in = int((~r.replaced_input).sum())
    invented = r.reference_mesh.positions[r.reference_mesh.face_v[n_in:]]
    assert [t for t in invented if t[:, 0].min() >= 40.0 - 1e-9] == []
    shipped = r.mesh.positions[r.mesh.face_v]
    flat = np.ptp(shipped[:, :, 2], axis=1) <= 1e-9
    under_b = shapely.box(40.0, 0.0, 80.0, 40.0)

    def area_at(z):
        return sum(shapely.Polygon(t[:, :2]).intersection(under_b).area
                   for t in shipped[flat & np.isclose(shipped[:, 0, 2], z)])
    assert area_at(0.0) == pytest.approx(1600.0)              # B's underside ships, whole
    assert area_at(-8.0) == pytest.approx(0.0)


def test_a_floor_under_a_landing_with_its_sides_missing_is_a_top():
    """Review part 2, M2 (`probe_real_top_taken_for_underside.py`): R, the slab's top running on
    under a landing, has its two sides missing and only a riser standing up to the landing. SR6's
    test (every own side stands up) took it for an underside: nothing was built under it, and
    L's edge into it became a "side" whose wall was refused -- a missed rebuild. Looking up from
    R meets the landing's own underside, not the top of a slab R belongs to: R is a top. Its open
    sides are walled, the slab gets its bottom, and nothing is built between L and R."""
    from engine.tests.fixtures.build import real_top_under_a_landing
    m = real_top_under_a_landing()
    r = _solidified(m, FixProfile(guard_size=(240, 160), n_dirs=64))
    assert r.report["undersides_not_tops"] == 0
    assert r.report["cap_guard_passed"] is True
    new = r.mesh.positions[r.mesh.face_v[r.new_faces]]
    under_r = [t for t in new if t[:, 0].min() >= 40.0 - 1e-9]
    for y in (0.0, 40.0):
        wall = [t for t in under_r if np.allclose(t[:, 1], y)]
        assert wall and min(t[:, 2].min() for t in wall) == pytest.approx(-10.0)
    bottom = [t for t in new if np.allclose(t[:, 2], -10.0)]
    assert sum(shapely.Polygon(t[:, :2]).area for t in bottom) == pytest.approx(80.0 * 40.0)
    assert [t for t in new if np.allclose(t[:, 0], 40.0)] == []   # no wall inside the slab


# ------------------------ review part 2, C1: the side rebuild never ships a coincident double layer


def _plane_census(mesh, axis, value, tol=1e-6):
    """`(sum of face areas, area of their union, area covered by two materials)` over the faces
    of `mesh` lying in the plane `x[axis] == value`: a double layer shows as sum > union."""
    tri = mesh.positions[mesh.face_v]
    on = np.nonzero((np.abs(tri[:, :, axis] - value) <= tol).all(axis=1))[0]
    keep = [a for a in range(3) if a != axis]
    by_material: dict = {}
    total = 0.0
    for f in on:
        poly = shapely.Polygon(tri[f][:, keep])
        total += poly.area
        by_material.setdefault(int(mesh.face_material[f]), []).append(poly)
    unions = [shapely.union_all(p) for p in by_material.values()]
    union = shapely.union_all(unions).area if unions else 0.0
    both = sum(a.intersection(b).area for i, a in enumerate(unions) for b in unions[i + 1:])
    return total, union, both


@pytest.mark.parametrize("teeth_material", [1, 0])
def test_a_piece_given_back_never_keeps_a_new_face_lying_on_it(teeth_material):
    """R2-C1 (`probe_restored_piece_double_layer.py`, `..._same_material.py`): the coincidence
    rule ran once, before the cap guard, and skipped a wall's own pieces -- they were to be
    removed. But the guard gives pieces back: the deep tooth's tip, 3 in below the wall, fails
    and is restored, and a wall that loses a face gives back every piece. At the default 900 x
    600 the wall face lying on tooth 35 was kept on it: 21.33 sq in of m0 over m1 shipped (in one
    material the fold and overlap passes left it too), `passed` True. A new face lying on a piece
    present in the state being judged is refused, every round. (Solidify's own output, where the
    layer was made -- nothing after it invents a face -- at the default 900 x 600 guard, the size
    it shows at.)"""
    from engine.tests.fixtures.build import slab_with_a_deep_tooth_in_its_side
    r = _solidified(slab_with_a_deep_tooth_in_its_side(teeth_material),
                    FixProfile(guard_size=(900, 600), n_dirs=32))
    assert r.report["cap_guard_passed"] is True
    total, union, both = _plane_census(r.mesh, 0, 0.0)
    assert both == pytest.approx(0.0, abs=1e-6)
    assert total == pytest.approx(union, abs=1e-6)


@pytest.mark.parametrize("size", [40.0, 2000.0])
def test_a_tooth_given_back_at_real_scale_leaves_no_double_layer(size):
    """R2-C1 at the real files' scale (`probe_piece_below_wall.py`): at 2000 in the tooth's fin
    shows in a few guard pixels, so it is given back; one wall face was refused and the other
    kept ON the tooth -- a 14.46 sq in coincident double layer, `passed` True. No face of the
    x = 0 plane lies on another (solidify's output, at the default 900 x 600 guard)."""
    from engine.tests.fixtures.build import slab_with_one_deep_tooth
    r = _solidified(slab_with_one_deep_tooth(size), FixProfile(guard_size=(900, 600), n_dirs=32))
    assert r.report["cap_guard_passed"] is True
    total, union, _both = _plane_census(r.mesh, 0, 0.0)
    assert total == pytest.approx(union, abs=1e-3)


def test_two_coincident_tops_get_one_bottom():
    """R2-C1 failure 3 (`probe_double_bottom.py`): a slab whose top is a duplicate layer of two
    materials got a bottom under EACH top region -- 1,600 sq in of m0 exactly over 1,600 sq in of
    m1 shipped on the underside, `passed` True. Walls were deduplicated across regions; bottoms
    were not. One bottom per footprint: the second one, lying on the first, is refused."""
    from engine.tests.fixtures.build import slab_with_a_double_layer_top
    r = fix_object(slab_with_a_double_layer_top(), {}, _FAST)
    assert r.passed is True
    total, union, both = _plane_census(r.mesh, 2, -8.0)
    assert union == pytest.approx(1600.0)
    assert both == pytest.approx(0.0, abs=1e-6) and total == pytest.approx(union)
    reasons = r.solidify_report["bottom_faces_refused"]["reasons"]
    assert reasons.get("coincides_with_existing_face", 0) >= 2


# ------------------------------ review part 2, I1: a piece belongs to the slab and to the side's look


def test_a_rebuilt_side_keeps_the_material_of_the_side_it_replaces():
    """R2-I1 failure 1 (`probe_side_material.py`): the teeth of the broken x = 0 side are m1
    (concrete) under an m0 (paving) top. The wall took the TOP's material, so the side shipped as
    320 sq in of m0 where the input had 128 sq in of m1 -- every tooth pixel changed material, and
    no rule named it. A wall takes the material of the side it replaces."""
    from engine.tests.fixtures.build import slab_with_a_concrete_sawtooth_side
    r = fix_object(slab_with_a_concrete_sawtooth_side(), {}, _FAST)
    assert r.passed is True
    assert r.solidify_report["side_pieces_replaced"] == 4
    shipped = r.mesh
    side = _plane_faces(shipped, 0, 0.0)
    assert len(side)
    assert set(shipped.face_material[side].tolist()) == {1}
    assert _covered_area(shipped, side, [1, 2]) == pytest.approx(40.0 * 8.0)


@pytest.mark.parametrize("size", [40.0, 2000.0])
def test_a_sign_standing_in_front_of_a_missing_side_is_never_a_piece(size):
    """R2-I1 failure 2 (`probe_object_in_band.py`): a sign 1.2 in in front of the missing half of
    a side -- inside the 2.5 in band, below the top, another material, touching nothing of the
    slab -- was taken for a piece of that side: at 2000 in and the default 900 x 600 guard both
    its triangles were deleted with the wall's acceptance, `passed` True. A piece is attached to
    the slab: its part of the side reaches the top edge or the wall's foot; the sign reaches
    neither, and stays."""
    from engine.tests.fixtures.build import slab_with_half_side_and_a_sign
    m, sign = slab_with_half_side_and_a_sign(size)
    r = _solidified(m, FixProfile(guard_size=(900, 600), n_dirs=32))
    assert r.report["cap_guard_passed"] is True
    assert not r.replaced[sign].any()


# --------------- review part 2, I2: a lower surface is where the slab's own sides end, not a floor


def _shipped_input_faces(r):
    """Input face ids that reach the shipped mesh (through the merge's provenance)."""
    ref_rows = np.nonzero(~r.replaced_input)[0]
    n_ref_in = len(ref_rows)
    src = (np.unique(np.concatenate([np.asarray(s).reshape(-1) for s in r.source_faces]))
           if len(r.source_faces) else np.zeros(0, np.int64))
    return set(ref_rows[src[src < n_ref_in]].tolist())


def test_one_deep_side_never_makes_the_floor_under_an_open_slab_its_lower_surface():
    """R2-I2 (`probe_lower_surface_floor.py`): S, a 2 in slab with no bottom, is attached to a
    32 in wall W -- one of its own sides -- over L, a lower slab whose top is 24 in down, with a
    bench standing on it under S. "No deeper than the slab's DEEPEST own side, + band" let L's top
    pass for S's lower surface: S's three WHOLE 2 in skirts were replaced by 24 in walls, and the
    hidden pass deleted the bench and L's top, `passed` True.

    A lower surface is where the MOST of the slab's own side length ends (within the band): here
    2 in (120 in of skirts), not 24 -- W passes 8 in below L's top, a wall S hangs on, not a side
    ending on it. S keeps its skirts, gets its bottom at 2 in, and the bench and L's top ship."""
    from engine.tests.fixtures.build import slab_over_a_floor_with_a_bench
    m = slab_over_a_floor_with_a_bench()
    r = fix_object(m, {}, _FAST)
    assert r.passed is True
    sr = r.solidify_report
    assert sr["walls_to_lower_surface"]["walls"] == 0
    assert not r.replaced_input[2:8].any()                       # the whole skirts stay
    n_in = int((~r.replaced_input).sum())
    invented = r.reference_mesh.positions[r.reference_mesh.face_v[n_in:]]
    assert len(invented) and float(invented[:, :, 2].min()) == pytest.approx(-2.0)
    shipped = _shipped_input_faces(r)
    assert set(range(22, 32)) <= shipped        # the bench (its bottom, 20-21, sits on L's top)
    assert {12, 13} <= shipped                                     # L's top


# ---------------- brief 10 item 6 (triage B1): a block standing on a slab is not an underside


def test_the_slab_runs_on_beneath_a_block_standing_on_it():
    """File B's walkway: a 1 m slab whose top has no face of its own where stair blocks stand on
    it -- the blocks' bottom faces lie in its top plane. Since review part 2 C2 those count as
    undersides (a slab above, nothing hanging below), so no top's volume covered the slab under
    them: walls were built round them INSIDE the slab, and the bottom there was missing or refused
    as covering outside every footprint -- the slab read as a tray from below.

    An underside a top runs into is where a block STANDS ON that top's slab when the top has a
    measured depth, none of its own sides hangs along the edges they share (the slab does not end
    there), and the underside lies within the top's outline (its convex hull). Here: the slab gets
    its bottom under the block too, no wall is built round the block, and from below it is one
    closed underside."""
    from engine.tests.fixtures.build import slab_with_a_block_standing_on_it
    m = slab_with_a_block_standing_on_it()
    r = _solidified(m, _FAST)
    assert r.report["cap_guard_passed"] is True
    assert r.report["walls_refused"]["faces"] == 0 and r.report["bottom_faces_refused"]["faces"] == 0
    new = r.mesh.positions[r.mesh.face_v[r.new_faces]]
    walls_round_block = [t for t in new if np.ptp(t[:, 2]) > 1e-6
                         and (np.allclose(t[:, 0], 20.0) or np.allclose(t[:, 0], 40.0)
                              or np.allclose(t[:, 1], 20.0) or np.allclose(t[:, 1], 40.0))]
    assert walls_round_block == []
    bottom = [f for f in np.nonzero(r.new_faces)[0]
              if np.allclose(r.mesh.positions[r.mesh.face_v[f]][:, 2], -8.0)]
    assert _covered_area(r.mesh, bottom, [0, 1]) == pytest.approx(60.0 * 60.0)
    shipped = fix_object(m, {}, _FAST)
    assert shipped.passed is True
    assert shipped.backface_px["final"]["total"] == 0


def test_the_slabs_side_under_a_block_at_its_edge_is_built():
    """The same slab with the block standing at its y = 0 edge, and the slab's side MISSING under
    the block (file B has no -y side under its stairs): the block's edge the slab does not continue
    across is the slab's side there, walled down to the slab's own 8 in like any of its edges --
    and the slab is closed: one bottom under all of it, nothing refused."""
    from engine.tests.fixtures.build import slab_with_a_block_standing_on_it
    m = slab_with_a_block_standing_on_it(at_edge=True)
    r = _solidified(m, _FAST)
    assert r.report["blocks_standing_on_slabs"] == 1
    assert r.report["cap_guard_passed"] is True
    assert r.report["walls_refused"]["faces"] == 0 and r.report["bottom_faces_refused"]["faces"] == 0
    side = [f for f in _plane_faces(r.mesh, 1, 0.0) if r.new_faces[f]]
    assert _covered_area(r.mesh, side, [0, 2]) == pytest.approx(20.0 * 8.0)
    bottom = [f for f in np.nonzero(r.new_faces)[0]
              if np.allclose(r.mesh.positions[r.mesh.face_v[f]][:, 2], -8.0)]
    assert _covered_area(r.mesh, bottom, [0, 1]) == pytest.approx(60.0 * 60.0)
    shipped = fix_object(m, {}, _FAST)
    assert shipped.passed is True
    assert shipped.backface_px["final"]["total"] == 0


def test_a_point_on_a_slabs_top_or_bottom_plane_is_inside_it():
    """The cap guard judges the point in front of a covered hit, and for a face lying ON the new
    bottom's plane -- a real partial bottom the bottom replaces -- that point is the hit point
    itself. Measured, such points came out 3.05e-6 in below file A's lower landing bottom (every
    one of 4,395) and 3.4e-4 to 7.9e-4 in outside file B's ramp and its neighbours: the precision
    of a ray hit on quantised coordinates. Called "below the bottom", they refused half of file
    A's lower-landing bottom, and each refusal gave the bottom's pieces back, so the next round
    refused more. A point within `EPS_IN` of the top or bottom plane is on it: inside."""
    from engine.guard.compare import INTERIOR_INSIDE
    from engine.fixes.solidify import _interior_test
    from engine.vis.exposure import EPS_IN
    foot = shapely.box(0.0, 0.0, 40.0, 40.0)
    shapely.prepare(foot)
    volumes = {0: (foot, np.array([0.0, 0.0, 1.0]), np.array([0.0, 0.0, 0.0]), 12.0, None)}
    interior = _interior_test(volumes, np.array([0, 0]), np.array([0]), np.zeros(3))
    points = np.array([[10.0, 10.0, -12.0 - 3.05e-6],       # on the bottom plane
                       [20.0, 20.0, 7.9e-4],                 # on the top plane
                       [30.0, 30.0, -6.0]])                  # well inside
    codes = interior(np.array([0, 0, 0]), points)
    assert codes.tolist() == [INTERIOR_INSIDE] * 3
    outside = interior(np.array([0, 0]), np.array([[10.0, 10.0, -12.0 - 2 * EPS_IN],
                                                   [10.0, 10.0, 2 * EPS_IN]]))
    assert INTERIOR_INSIDE not in outside.tolist()


def test_a_bottom_face_refused_gives_back_only_the_pieces_it_covers(monkeypatch):
    """File A's lower-landing bottom: one of its 33 faces lies over faces of the file's lower
    level (regions 800 and 810) that straddle the landing's diagonal side, so it is refused as
    coinciding with faces that are no piece of it -- rightly. But a group's pieces were only
    replaced while EVERY face of the group was kept, so all 38 pieces of the landing's real
    partial bottom came back, and 16 more bottom faces were refused for covering them: half the
    bottom gone, 7,836 back-face pixels where it was.

    A bottom's piece now comes back only when a face that covers it is refused. Here one bottom
    face is refused by force, far from the strip: the strip is still replaced, and the faces over
    it are kept."""
    import engine.fixes.solidify as S
    from engine.tests.fixtures.build import slab_with_a_bottom_strip
    m = slab_with_a_bottom_strip()
    real = S._coincident_new_faces

    def refuse_the_far_one(solid, new_faces, new_group, replaced_group, ok_input, tol):
        out = real(solid, new_faces, new_group, replaced_group, ok_input, tol)
        tri = solid.positions[solid.face_v]
        flat = np.abs(np.cross(tri[:, 1] - tri[:, 0], tri[:, 2] - tri[:, 0])[:, 2]) > 0.0
        bottom = np.nonzero(new_faces & flat & np.isclose(tri[:, :, 2], -8.0).all(axis=1))[0]
        far = bottom[np.argmax(tri[bottom][:, :, 0].min(axis=1))]
        assert tri[far][:, 0].min() >= 20.0                 # it covers none of the strip
        out[far] = True
        return out

    monkeypatch.setattr(S, "_coincident_new_faces", refuse_the_far_one)
    r = _solidified(m)
    assert r.replaced[14] and r.replaced[15]                 # the strip is still replaced
    new = np.nonzero(r.new_faces)[0]
    tri = r.mesh.positions[r.mesh.face_v[new]]
    over_strip = [f for f, t in zip(new, tri) if np.isclose(t[:, 2], -8.0).all()
                  and t[:, 0].max() <= 20.0 + 1e-6]
    assert over_strip
