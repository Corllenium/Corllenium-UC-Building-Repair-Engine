import numpy as np

from engine.pipeline import analyse_topology, topology_stats
from engine.tests.fixtures.build import (creased_pair, creased_pair_with_fine_band, cube,
                                         grid_slab, rounded_long_slab,
                                         t_junction_shared_strip, t_junction_strip)
from engine.topo.edges import EDGE_OPEN, EDGE_REAL, EDGE_REMOVABLE, EDGE_SOFT


def regions(topo):
    return len(set(topo.face_region[topo.face_region >= 0].tolist()))


def test_cube_has_six_regions_and_six_removable_diagonals():
    t = analyse_topology(cube())
    assert regions(t) == 6
    assert int((t.edge_class == EDGE_REMOVABLE).sum()) == 6 and int((t.edge_class == EDGE_REAL).sum()) == 12


def test_grid_slab_is_one_region():
    t = analyse_topology(grid_slab(10, 10))
    assert regions(t) == 1
    assert int((t.edge_class == EDGE_REMOVABLE).sum()) == 280 and int((t.edge_class == EDGE_OPEN).sum()) == 40


def test_whole_tile_uv_shift_does_not_split():
    assert regions(analyse_topology(grid_slab(10, 10, shift_cols=(3, 4)))) == 1


def test_real_uv_seam_splits_patterned_texture_only():
    m = grid_slab(10, 10, break_col=5)
    assert regions(analyse_topology(m)) == 2
    assert regions(analyse_topology(m, flat_materials=frozenset({0}))) == 1


def test_material_change_splits():
    m = grid_slab(10, 10)
    m.materials, m.face_material = ["a", "b"], np.array([0] * 100 + [1] * 100)
    assert regions(analyse_topology(m)) == 2


def test_t_junction_joins_one_region_and_edges_are_removable():
    t = analyse_topology(t_junction_strip())
    assert regions(t) == 1 and t.face_region[6] == -1
    assert topology_stats(t)["t_junction_edges"] == 0
    # 3 quad diagonals + edge shared by the two upper quads + long edge + its 2 sub-edges
    assert int((t.edge_class == EDGE_REMOVABLE).sum()) == 7


def test_shared_tjunction_edge_keeps_its_count_class_when_chain_regions_differ():
    """The long top edge is now shared (count == 2) with an unrelated vertical wall triangle.
    Its T-vertex is still found (via the F3 hint/geometry fix), but since the wall's face is in
    a different region than the quads, the chain is not "whole": per spec a counts >= 2 edge
    keeps whatever class the count rules gave it (EDGE_REAL here), it must not be downgraded
    to EDGE_TJUNCTION just because a T-vertex happens to lie on it."""
    t = analyse_topology(t_junction_shared_strip())
    P, edges = t.positions_w, t.table.edges
    e = next(i for i, (a, b) in enumerate(edges)
             if sorted(P[[a, b]][:, 0].tolist()) == [0.0, 20.0]
             and (P[[a, b]][:, 1] == 10.0).all() and (P[[a, b]][:, 2] == 0.0).all())
    assert t.table.counts[e] == 2
    assert e in t.t_vertices
    assert t.edge_class[e] == EDGE_REAL


# ---------------------------------------------------------------------------------------------
# M1: plane regions grow with an iterative least-squares refit -- a region's plane is fitted to
# the faces it has COLLECTED, not to the one triangle it was seeded from, so exporter rounding
# noise on the seed no longer splits one flat face into several regions.
# ---------------------------------------------------------------------------------------------

def test_rounded_long_slab_is_one_region_despite_seed_plane_rounding_noise():
    """Seeded from its largest triangle alone (tilted by one 0.1 in print step over 300 in), the
    far end of this 1,700 in strip sits 0.47 in off the seed plane against a 0.15 in tolerance,
    so seed-only clustering splits it. Every vertex is within ONE quantum of the strip's own
    best-fit plane, so a refit plane holds all 58 faces."""
    m = rounded_long_slab()
    t = analyse_topology(m)
    assert m.n_faces == 58 and len(m.positions) == 60
    assert bool(t.ok.all())
    assert regions(t) == 1
    assert (t.face_region == 0).all()


def test_three_degree_crease_stays_two_regions():
    """cos(3 deg) = 0.9986 passes `facing_dot`, so only the plane-distance test separates these:
    refitting must not swallow a genuinely different plane."""
    m = creased_pair()
    t = analyse_topology(m)
    assert regions(t) == 2
    assert t.face_region[0] == t.face_region[1]
    assert t.face_region[2] == t.face_region[3]
    assert t.face_region[0] != t.face_region[2]


def test_region_growing_is_deterministic():
    """Two independently built copies of the same mesh give the identical labelling -- no
    iteration order, dict order or accumulated state leaks into the result."""
    a = analyse_topology(rounded_long_slab()).face_region
    b = analyse_topology(rounded_long_slab()).face_region
    assert np.array_equal(a, b)
    c = analyse_topology(creased_pair()).face_region
    d = analyse_topology(creased_pair()).face_region
    assert np.array_equal(c, d)


# ---------------------------------------------------------------------------------------------
# M2: EDGE_SOFT -- a crease between two regions of the same material that is too shallow to be a
# real shape edge and too steep to merge without moving vertices. Below it, `coplanar_region_
# borders` counts the region borders that are flat to within `coplanar_angle`: a diagnostic for
# the splits M1 was supposed to end, which should read ~0.
# ---------------------------------------------------------------------------------------------

def hinge_edge(t):
    """The `creased_pair` hinge: the only edge whose two endpoints both sit at x == 0."""
    P = t.positions_w
    return next(i for i, (a, b) in enumerate(t.table.edges) if P[a][0] == 0.0 and P[b][0] == 0.0)


def test_three_degree_crease_edge_is_soft():
    t = analyse_topology(creased_pair(angle_deg=3.0))
    e = hinge_edge(t)
    assert t.table.counts[e] == 2
    assert t.edge_class[e] == EDGE_SOFT
    s = topology_stats(t)
    assert s["soft_edges"] == 1 and s["coplanar_region_borders"] == 0


def test_a_half_degree_crease_is_a_coplanar_region_border_not_a_soft_edge():
    """Below `coplanar_angle` the two faces are flat to within the export's own precision, so the
    split is a defect to be counted, not a crease to be drawn."""
    t = analyse_topology(creased_pair(angle_deg=0.5))
    e = hinge_edge(t)
    assert t.edge_class[e] != EDGE_SOFT
    s = topology_stats(t)
    assert s["soft_edges"] == 0 and s["coplanar_region_borders"] == 1


def test_a_ten_degree_crease_stays_a_real_edge():
    t = analyse_topology(creased_pair(angle_deg=10.0))
    e = hinge_edge(t)
    assert t.edge_class[e] == EDGE_REAL
    s = topology_stats(t)
    assert s["soft_edges"] == 0 and s["coplanar_region_borders"] == 0


def test_soft_and_coplanar_thresholds_are_settable():
    """Both are keyword arguments all the way down from `FixProfile`."""
    t = analyse_topology(creased_pair(angle_deg=3.0), soft_angle=2.0)
    assert t.edge_class[hinge_edge(t)] == EDGE_REAL
    t = analyse_topology(creased_pair(angle_deg=3.0), coplanar_angle=4.0, soft_angle=5.0)
    assert t.edge_class[hinge_edge(t)] != EDGE_SOFT
    assert topology_stats(t)["coplanar_region_borders"] == 1


def test_a_cube_has_no_soft_edges_and_no_coplanar_region_borders():
    s = topology_stats(analyse_topology(cube()))
    assert s["soft_edges"] == 0 and s["coplanar_region_borders"] == 0


# ---------------------------------------------------------------------------------------------
# MQ1: EDGE_SOFT is a border between two REAL regions. Two faces that are both copied through
# (`face_region == -1`) share no region border at all, so a shallow fold between them is not a
# soft crease -- the same rule `region_border_angles` already applies.
# ---------------------------------------------------------------------------------------------

def test_two_copied_through_faces_never_make_a_soft_edge():
    """`classify_edges` with a `face_region` of all -1: the hinge of `creased_pair` is a 3 degree
    fold between two same-material faces that belong to NO region. `region_border_angles` does not
    call that a region border; neither may `classify_edges`."""
    from engine.topo.edges import classify_edges, region_border_angles
    from engine.topo.planes import face_normals

    t = analyse_topology(creased_pair(angle_deg=3.0))
    e = hinge_edge(t)
    assert t.edge_class[e] == EDGE_SOFT      # with real regions it IS a soft crease

    normals = face_normals(t.positions_w, t.face_w, t.ok)
    nowhere = np.full(len(t.face_w), -1, np.int64)
    cls = classify_edges(t.table, nowhere, t.t_vertices, normals,
                         creased_pair(angle_deg=3.0).face_material)
    assert cls[e] != EDGE_SOFT
    assert region_border_angles(t.table, nowhere, normals) == {}


# ---------------------------------------------------------------------------------------------
# MQ3: the iterative least-squares refit must not walk ACROSS a shallow crease. At y = 24,000 in
# the plane tolerance is 0.15 in while a point d inches along a 3 degree slope sits only
# `0.052 * d` off the other plane, so every vertex of a fine band within ~2.9 in of the hinge is
# inside the neighbouring plane's tolerance AND inside `facing_dot`. If the refit followed them,
# one plane would tilt, admit the next band column, and drift off its own surface.
# ---------------------------------------------------------------------------------------------

_TRUE_FLAT = np.array([0.0, -1.0, 0.0])
_TRUE_TILT = np.array([np.sin(np.radians(3.0)), -np.cos(np.radians(3.0)), 0.0])


def _fitted_planes(mesh):
    """`cluster_planes`' own output for `mesh`, built exactly as `analyse_topology` builds it:
    `[(members, normal), ...]` in plane order."""
    from engine.topo.adjacency import degenerate_mask
    from engine.topo.planes import cluster_planes, face_normals
    from engine.topo.weld import axis_quanta, weld_exact

    positions_w, remap = weld_exact(mesh.positions, mesh.coord_decimals)
    face_w = remap[mesh.face_v]
    ok = ~degenerate_mask(positions_w, face_w)
    tri = positions_w[face_w]
    cross = np.cross(tri[:, 1] - tri[:, 0], tri[:, 2] - tri[:, 0])
    label, planes = cluster_planes(tri, face_normals(positions_w, face_w, ok),
                                   0.5 * np.linalg.norm(cross, axis=1), mesh.face_material, ok,
                                   axis_quanta(positions_w, mesh.sig_digits))
    return [(np.nonzero(label == i)[0], n) for i, (n, _p0, _tol) in enumerate(planes)]


def _degrees_between(a, b):
    return float(np.degrees(np.arccos(np.clip(float(np.asarray(a) @ np.asarray(b)), -1.0, 1.0))))


def test_least_squares_refit_does_not_drift_across_a_shallow_crease():
    m = creased_pair_with_fine_band()
    assert regions(analyse_topology(m)) == 2

    planes = _fitted_planes(m)
    assert len(planes) == 2, [len(mem) for mem, _ in planes]
    for _members, normal in planes:
        assert min(_degrees_between(normal, _TRUE_FLAT),
                   _degrees_between(normal, _TRUE_TILT)) <= 0.5, normal
    # ... and the two planes are the two DIFFERENT surfaces, not the same one found twice.
    assert _degrees_between(planes[0][1], planes[1][1]) > 2.5


def test_the_fine_band_is_what_makes_that_fixture_dangerous():
    """Pins the geometry the test above depends on, so a later edit to the fixture cannot quietly
    make it harmless: same material both sides, both halves wound the SAME way (or no candidate of
    one could ever be considered for the other's plane), and a band of triangles whose edges are
    under 2 in -- short enough to sit inside the neighbour's 0.15 in plane tolerance."""
    m = creased_pair_with_fine_band()
    assert len(set(m.face_material.tolist())) == 1
    tri = m.positions[m.face_v]
    normals = np.cross(tri[:, 1] - tri[:, 0], tri[:, 2] - tri[:, 0])
    normals = normals / np.linalg.norm(normals, axis=1)[:, None]
    assert (normals @ _TRUE_FLAT > 0.99).all()          # every face points the same way

    edges = np.linalg.norm(tri - np.roll(tri, -1, axis=1), axis=2)
    band = edges.max(axis=1) < 2.0
    # 10 band columns x 25 rows x 2 triangles per cell x 2 sides
    assert int(band.sum()) == 2 * 2 * 10 * 25, int(band.sum())
    hinge = np.abs(tri[band][:, :, 0]).min()
    assert hinge <= 1e-9                                 # the band really does touch the crease
