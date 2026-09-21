import numpy as np

from engine.tests.fixtures.build import cube, grid_slab, t_junction_strip
from engine.topo.adjacency import build_edge_table, degenerate_mask, edge_face_lists, find_t_vertices
from engine.topo.weld import axis_quanta, weld_exact


def test_weld_merges_printed_duplicates_and_negative_zero():
    P = np.array([[0.0, 1.0, 2.0], [-0.0, 1.0, 2.0], [0.004, 1.0, 2.0], [5.0, 5.0, 5.0]])
    uniq, remap = weld_exact(P, decimals=2)
    assert len(uniq) == 2 and remap.tolist()[:3] == [remap[0]] * 3 and remap[3] != remap[0]


def test_axis_quanta_follow_magnitude():
    P = np.array([[3293.33, 24204.9, 2114.17], [980.11, 22651.0, 1779.53]])
    assert np.allclose(axis_quanta(P, sig_digits=6), [0.01, 0.1, 0.01])


def test_cube_edges():
    m = cube()
    P, remap = weld_exact(m.positions, 2)
    fw = remap[m.face_v]
    ok = ~degenerate_mask(P, fw)
    t = build_edge_table(fw, ok)
    assert ok.all() and len(t.edges) == 18 and (t.counts == 2).all()
    assert all(len(f) == 2 for f in edge_face_lists(t))


def test_grid_slab_open_edges():
    m = grid_slab(10, 10)
    P, remap = weld_exact(m.positions, 2)
    t = build_edge_table(remap[m.face_v], np.ones(200, bool))
    assert len(t.edges) == 320 and int((t.counts == 1).sum()) == 40


def test_t_junction_found():
    m = t_junction_strip()
    P, remap = weld_exact(m.positions, 2)
    fw = remap[m.face_v]
    deg = degenerate_mask(P, fw)
    assert deg.tolist() == [False] * 6 + [True]
    t = build_edge_table(fw, ~deg)
    assert (t.face_edges[6] == -1).all()
    tv = find_t_vertices(P, t, tol=0.015)
    assert len(tv) == 1
    (e, verts), = tv.items()
    assert sorted(P[t.edges[e]][:, 0].tolist()) == [0.0, 20.0] and P[verts[0]].tolist() == [10.0, 10.0, 0.0]
