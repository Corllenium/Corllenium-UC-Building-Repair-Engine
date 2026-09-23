import numpy as np

from engine.pipeline import analyse_topology, topology_stats
from engine.tests.fixtures.build import (creased_pair, cube, grid_slab, rounded_long_slab,
                                         t_junction_shared_strip, t_junction_strip)
from engine.topo.edges import EDGE_OPEN, EDGE_REAL, EDGE_REMOVABLE


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
