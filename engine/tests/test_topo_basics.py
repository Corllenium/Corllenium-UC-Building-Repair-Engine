import numpy as np

from engine.tests.fixtures.build import cube, grid_slab, t_junction_shared_strip, t_junction_strip
from engine.topo.adjacency import (build_edge_table, degenerate_mask, edge_face_lists, find_t_vertices,
                                    t_junction_sub_edges)
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


def test_t_junction_sub_edges_walks_chain_to_real_sub_edge_indices():
    m = t_junction_strip()
    P, remap = weld_exact(m.positions, 2)
    fw = remap[m.face_v]
    ok = ~degenerate_mask(P, fw)
    t = build_edge_table(fw, ok)
    tv = find_t_vertices(P, t, tol=0.015)
    subs = t_junction_sub_edges(t, tv)
    assert len(subs) == 1
    (e, sub_idx), = subs.items()
    assert len(sub_idx) == 2 and all(s is not None for s in sub_idx)
    a, b = t.edges[e]
    chain = [int(a), *[int(v) for v in tv[e]], int(b)]
    expected_pairs = [sorted(P[[p, q]][:, 0].tolist()) for p, q in zip(chain, chain[1:])]
    assert expected_pairs == [[0.0, 10.0], [10.0, 20.0]]  # chain order starting from edges[e][0]
    for s, pair in zip(sub_idx, expected_pairs):
        assert sorted(P[t.edges[s]][:, 0].tolist()) == pair
        assert P[t.edges[s]][:, 1].tolist() == [10.0, 10.0]


def test_t_junction_sub_edges_yields_none_for_missing_sub_edge():
    m = t_junction_strip()
    P, remap = weld_exact(m.positions, 2)
    fw = remap[m.face_v]
    ok = ~degenerate_mask(P, fw)
    t = build_edge_table(fw, ok)
    tv = find_t_vertices(P, t, tol=0.015)
    (e, _verts), = tv.items()
    # Hand-made t_vertices: name the welded vertex at (0, 20, 0) as the chain's mid-vertex.
    # It IS connected to edges[e][0] == (0, 10, 0) by a real diagonal edge, so the first
    # sub-edge resolves -- but nothing in the table connects it to edges[e][1] == (20, 10, 0),
    # so the second leg of the chain has no matching row in table.edges and must be None.
    far_vertex = int(np.nonzero((P[:, 0] == 0.0) & (P[:, 1] == 20.0))[0][0])
    fake_tv = {e: np.array([far_vertex])}
    subs = t_junction_sub_edges(t, fake_tv)
    assert subs[e][0] is not None and subs[e][1] is None


def _find_long_top_edge(P, t):
    """The long edge (0,10,0)-(20,10,0) shared by the big quad and (in the shared fixture) the wall."""
    for e, (a, b) in enumerate(t.edges):
        pair = P[[a, b]]
        if sorted(pair[:, 0].tolist()) == [0.0, 20.0] and (pair[:, 1] == 10.0).all() and (pair[:, 2] == 0.0).all():
            return e
    raise AssertionError("long top edge not found in table")


def test_shared_edge_t_vertex_found_via_hint_when_zero_area_face_present():
    m = t_junction_shared_strip()
    P, remap = weld_exact(m.positions, 2)
    fw = remap[m.face_v]
    deg = degenerate_mask(P, fw)
    t = build_edge_table(fw, ~deg)
    e = _find_long_top_edge(P, t)
    assert t.counts[e] == 2  # shared by the quad top and the new wall triangle, not open
    tv = find_t_vertices(P, t, tol=0.015, face_w=fw, degenerate=deg)
    assert e in tv and len(tv[e]) == 1 and P[tv[e][0]].tolist() == [10.0, 10.0, 0.0]


def test_shared_edge_t_vertex_found_via_geometry_alone_when_zero_area_face_absent():
    m = t_junction_shared_strip(drop_zero_area=True)
    P, remap = weld_exact(m.positions, 2)
    fw = remap[m.face_v]
    deg = degenerate_mask(P, fw)
    assert not deg.any()  # no zero-area face left, so no hint is even possible
    t = build_edge_table(fw, ~deg)
    e = _find_long_top_edge(P, t)
    assert t.counts[e] == 2
    tv = find_t_vertices(P, t, tol=0.015)  # face_w/degenerate omitted: geometry only, no hints
    assert e in tv and len(tv[e]) == 1 and P[tv[e][0]].tolist() == [10.0, 10.0, 0.0]


def test_degenerate_face_with_repeated_vertex_id_yields_no_hint_and_no_crash():
    m = t_junction_strip()
    P, remap = weld_exact(m.positions, 2)
    fw = remap[m.face_v].copy()
    fw[6] = [fw[6][0], fw[6][0], fw[6][0]]  # corrupt the zero-area stitching face
    deg = degenerate_mask(P, fw)
    assert deg[6]  # still degenerate: collapsed to a single point
    t = build_edge_table(fw, ~deg)
    tv = find_t_vertices(P, t, tol=0.015, face_w=fw, degenerate=deg)  # must not raise
    assert len(tv) == 1  # the real T-vertex is still found geometrically; no spurious hint added
