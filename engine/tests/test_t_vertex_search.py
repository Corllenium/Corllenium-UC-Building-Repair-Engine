"""P1-S1: the T-junction search, made near-linear, must give exactly the old answer.

Claude wrote and committed these tests before the job was queued (the P1-P2 plan's rolling-brief
rule); the job makes them pass without changing them.

- `find_t_vertices_reference` is the old edge x vertex loop, kept verbatim as the oracle.
- `find_t_vertices` is the new search: the same signature plus an optional `stats` dict. When one is
  given it sets `stats["pairs_tested"]`: how many (edge, candidate vertex) pairs the geometric search
  computed a distance for. The zero-area hints are not counted.

"Exactly" means: the same keys (Python ints, edge indices into `table.edges`), and for each key an
int64 array with the same vertex ids in the same order.
"""
import numpy as np
import pytest

from engine.tests.fixtures.build import (box_with_partition_and_stitch, frame_with_crossed_seam,
                                         gridded_box, grid_slab, t_junction_lattice_region,
                                         t_junction_seam_strip, t_junction_shared_strip,
                                         t_junction_strip)
from engine.topo.adjacency import (EdgeTable, build_edge_table, degenerate_mask, find_t_vertices,
                                    find_t_vertices_reference)
from engine.topo.weld import axis_quanta, weld_exact

TOL = 0.015  # 1.5 print steps at 2 decimals, as analyse_topology uses on such files


def _same(old: dict, new: dict) -> bool:
    return (old.keys() == new.keys()
            and all(type(k) is int for k in new)
            and all(new[k].dtype == np.int64 and np.array_equal(old[k], new[k]) for k in old))


def _triples(table, found: dict) -> set:
    """An answer as (edge end, edge end, T-vertex) id triples, comparable across edge tables."""
    return {(int(table.edges[e][0]), int(table.edges[e][1]), int(v)) for e, vs in found.items() for v in vs}


# ----------------------------------------------------------------------------- synthetic scenes

def _quadtree_rects(rng, size, depth, p_split):
    rects, stack = [], [(0.0, 0.0, size, size, 0)]
    while stack:
        x0, y0, x1, y1, d = stack.pop()
        if d < depth and (d < 2 or rng.random() < p_split):
            xm, ym = (x0 + x1) / 2, (y0 + y1) / 2
            stack += [(x0, y0, xm, ym, d + 1), (xm, y0, x1, ym, d + 1),
                      (x0, ym, xm, y1, d + 1), (xm, ym, x1, y1, d + 1)]
        else:
            rects.append((x0, y0, x1, y1))
    return rects


def _wall(rng, size=400.0, depth=6, p_split=0.55):
    """A flat z = 0 wall of axis-aligned rectangles from a random quadtree split, two triangles
    each. Where a leaf meets smaller neighbours, their corners sit on its edge: T-junctions. Big
    leaves next to small ones give long edges beside short ones."""
    P, F = [], []
    for x0, y0, x1, y1 in _quadtree_rects(rng, size, depth, p_split):
        b = len(P)
        P += [[x0, y0, 0.0], [x1, y0, 0.0], [x1, y1, 0.0], [x0, y1, 0.0]]
        F += [[b, b + 1, b + 2], [b, b + 2, b + 3]]
    return np.array(P), np.array(F, np.int64)


def _rotation(rng):
    q, _ = np.linalg.qr(rng.normal(size=(3, 3)))
    return q * np.sign(np.linalg.det(q))


def _scene_raw(seed, n_walls, depth):
    """Walls in the three axis planes and in skew planes, spread along x so they do not touch, in
    print coordinates (2 decimals) like an OBJ export. Rounding a skew wall moves its T-vertices up
    to 0.009 off their edges, inside TOL."""
    rng = np.random.default_rng(seed)
    parts, faces, base = [], [], 0
    for w in range(n_walls):
        P, F = _wall(rng, depth=depth)
        kind = w % 4
        if kind == 1:
            P = P[:, [2, 0, 1]]           # an x = const wall
        elif kind == 2:
            P = P[:, [0, 2, 1]]           # a y = const wall
        elif kind == 3:
            P = P @ _rotation(rng).T      # a skew wall
        P = P + w * np.array([1500.0, 37.0, 11.0])
        parts.append(P)
        faces.append(F + base)
        base += len(P)
    return np.round(np.concatenate(parts), 2), np.concatenate(faces)


def _prepared(P, F, decimals=2, drop=None):
    """Weld and build the edge table the way analyse_topology does; `drop` leaves faces out."""
    Pw, remap = weld_exact(P, decimals)
    fw = remap[F]
    ok = ~degenerate_mask(Pw, fw)
    include = ok if drop is None else ok & ~drop
    return Pw, fw, ok, build_edge_table(fw, include)


def _scene(seed, n_walls, depth):
    return _prepared(*_scene_raw(seed, n_walls, depth))


def _edge_index(Pw, table, p, q):
    ends = Pw[table.edges]
    want = np.array([p, q], float)
    for e in range(len(table.edges)):
        if np.array_equal(ends[e], want) or np.array_equal(ends[e], want[::-1]):
            return e
    raise AssertionError(f"no edge {p} - {q}")


# ------------------------------------------------------------------------------ same answer

@pytest.mark.parametrize("seed", [0, 1, 2, 3])
def test_same_answer_as_the_reference_on_random_walls(seed):
    Pw, fw, ok, table = _scene(seed, n_walls=4, depth=5)
    old = find_t_vertices_reference(Pw, table, TOL)
    new = find_t_vertices(Pw, table, TOL)
    assert len(old) > 250  # the scene really has T-junctions, on every kind of wall
    assert _same(old, new)


@pytest.mark.parametrize("build", [t_junction_strip, t_junction_shared_strip, grid_slab, gridded_box,
                                   frame_with_crossed_seam, t_junction_seam_strip,
                                   t_junction_lattice_region, box_with_partition_and_stitch])
def test_same_answer_on_the_engine_fixtures(build):
    m = build()
    Pw, remap = weld_exact(m.positions, m.coord_decimals)
    fw = remap[m.face_v]
    ok = ~degenerate_mask(Pw, fw)
    table = build_edge_table(fw, ok)
    tol = 1.5 * float(axis_quanta(Pw, m.sig_digits).max())  # analyse_topology's tolerance
    assert _same(find_t_vertices_reference(Pw, table, tol, face_w=fw, degenerate=~ok),
                 find_t_vertices(Pw, table, tol, face_w=fw, degenerate=~ok))


def test_same_answer_with_zero_area_hints_on_vertices_no_face_shares():
    """Zero-area stitches (a, m, b) with a fresh mid vertex that no kept face uses: only the hints
    can report it, and the new search must merge them exactly as the old one does."""
    P, F = _scene_raw(4, n_walls=2, depth=5)  # two axis-aligned walls: midpoints stay exact
    rng = np.random.default_rng(14)
    extra_p, extra_f = [], []
    for i in rng.choice(len(F), size=60, replace=False):
        a, b = F[i, 0], F[i, 1]  # a leaf's side or its diagonal
        extra_f.append([a, len(P) + len(extra_p), b])
        extra_p.append((P[a] + P[b]) / 2)
    P2 = np.concatenate([P, np.array(extra_p)])
    F2 = np.concatenate([F, np.array(extra_f, np.int64)])
    Pw, fw, ok, table = _prepared(P2, F2)
    assert (~ok).sum() == 60  # the stitches are zero-area, so the table leaves them out
    old = find_t_vertices_reference(Pw, table, TOL, face_w=fw, degenerate=~ok)
    new = find_t_vertices(Pw, table, TOL, face_w=fw, degenerate=~ok)
    assert _triples(table, old) > _triples(table, find_t_vertices_reference(Pw, table, TOL))
    assert _same(old, new)


def test_same_answer_at_the_tolerance_and_end_limits():
    """Probes just inside and just outside the reference's limits: distance <= tol and
    1e-9 < t < 1 - 1e-9. The margins (1e-6 of tol, 1e-9 of t) are far above rounding noise, so
    any search that applies the same test to the same pairs agrees."""
    L, tol = 100.0, 0.25
    P = [[0.0, 0.0, 0.0], [L, 0.0, 0.0], [L / 2, 40.0, 0.0]]
    F = [[0, 1, 2]]
    probes = [(L / 2, tol * (1 - 1e-6)), (L / 2, tol * (1 + 1e-6)),   # distance
              (L * 2e-9, 0.0), (L * 0.5e-9, 0.0),                     # t just above / below 1e-9
              (L * (1 - 2e-9), 0.0), (L * (1 - 0.5e-9), 0.0),         # t just below / above 1 - 1e-9
              (-tol / 2, 0.0), (L + tol / 2, 0.0)]                    # beyond the ends
    for x, y in probes:  # each probe is the corner of a small triangle hanging below the edge
        b = len(P)
        P += [[x, y, 0.0], [x, y - 5.0, 3.0], [x + 1.0, y - 5.0, 3.0]]
        F.append([b, b + 1, b + 2])
    Pw, fw, ok, table = _prepared(np.array(P), np.array(F, np.int64), decimals=12)
    old = find_t_vertices_reference(Pw, table, tol)
    e = _edge_index(Pw, table, [0.0, 0.0, 0.0], [L, 0.0, 0.0])
    # on the long edge: the probes at t = 2e-9, at distance tol * (1 - 1e-6), and at t = 1 - 2e-9
    assert np.allclose(np.sort(Pw[old[e], 0]), [L * 2e-9, L / 2, L * (1 - 2e-9)], rtol=0, atol=1e-9)
    assert _same(old, find_t_vertices(Pw, table, tol))


def test_same_answer_when_the_tolerance_reaches_another_surface():
    """Two floors 1 in apart with different subdivisions: at tol 1.5 the corners of each floor are
    within reach of the other floor's edges, so every edge's reach must be padded by tol."""
    rng = np.random.default_rng(5)
    P1, F1 = _wall(rng, depth=5)
    P2, F2 = _wall(rng, depth=5)
    P = np.round(np.concatenate([P1, P2 + [0.0, 0.0, 1.0]]), 2)
    F = np.concatenate([F1, F2 + len(P1)])
    Pw, fw, ok, table = _prepared(P, F)
    near = find_t_vertices_reference(Pw, table, TOL)
    old = find_t_vertices_reference(Pw, table, 1.5)
    assert sum(map(len, old.values())) > 2 * sum(map(len, near.values()))
    assert _same(old, find_t_vertices(Pw, table, 1.5))


def test_same_answer_when_vertices_sit_just_off_flat_edges_at_many_heights():
    """Flat edges at 600 heights 0.37 in apart, each with a vertex 0.9 in above its middle. At
    tol 1.0 each vertex reaches several edges, but it lies outside every one of those edges' own
    (flat) bounding boxes. Over 222 in of height, any grid puts a cell border between some vertex
    and an edge it reaches, so each edge's reach must be padded by tol in every direction."""
    P, F = [], []
    for k in range(600):
        z = round(0.37 * k, 2)
        b = len(P)
        P += [[0.0, 0.0, z], [10.0, 0.0, z], [5.0, 3.0, z],                  # the flat edge's triangle
              [5.0, 0.0, z + 0.9], [5.0, -2.0, z + 2.9], [6.0, -2.0, z + 2.9]]  # the vertex's triangle
        F += [[b, b + 1, b + 2], [b + 3, b + 4, b + 5]]
    Pw, fw, ok, table = _prepared(np.array(P), np.array(F, np.int64))
    old = find_t_vertices_reference(Pw, table, 1.0)
    assert sum(map(len, old.values())) > 2000
    assert _same(old, find_t_vertices(Pw, table, 1.0))


def test_same_answer_when_the_table_leaves_faces_out():
    """Only vertices of faces in the table are candidates (`np.unique(table.edges)`); a corner
    used only by left-out faces must stay unreported."""
    P, F = _scene_raw(3, n_walls=3, depth=5)
    drop = np.random.default_rng(9).random(len(F)) < 0.15
    Pw, fw, ok, table = _prepared(P, F, drop=drop)
    old = find_t_vertices_reference(Pw, table, TOL)
    _, _, _, full = _prepared(P, F)
    assert _triples(table, old) != _triples(full, find_t_vertices_reference(Pw, full, TOL))
    assert _same(old, find_t_vertices(Pw, table, TOL))


def test_an_empty_table_gives_nothing():
    empty = EdgeTable(np.zeros((0, 2), np.int64), np.zeros(0, np.int64), np.zeros((0, 3), np.int64))
    stats = {}
    assert find_t_vertices(np.zeros((0, 3)), empty, TOL, stats=stats) == {}
    assert stats.get("pairs_tested", 0) == 0


def test_two_runs_give_the_same_answer_and_count():
    Pw, fw, ok, table = _scene(6, n_walls=4, depth=5)
    s1, s2 = {}, {}
    assert _same(find_t_vertices(Pw, table, TOL, stats=s1), find_t_vertices(Pw, table, TOL, stats=s2))
    assert s1 == s2 and s1["pairs_tested"] > 0


# ------------------------------------------------------------------------------- near-linear

def test_pairs_tested_stays_near_linear_on_a_large_scene():
    """About 17 k triangles, 32 k edges and 12 k candidate vertices: the reference tests every
    (edge, vertex) pair, about 377 million; a spatial search tests a few dozen per edge."""
    Pw, fw, ok, table = _scene(11, n_walls=8, depth=7)
    E, V = len(table.edges), len(np.unique(table.edges))
    assert E > 25_000
    stats = {}
    find_t_vertices(Pw, table, TOL, stats=stats)
    assert 0 < stats["pairs_tested"] <= 100 * (E + V)
    assert stats["pairs_tested"] < E * V // 50


def test_pairs_tested_doubles_not_quadruples_when_the_scene_doubles():
    """The 8-wall scene is the 4-wall scene plus 4 more walls (the same random stream), so a
    linear search tests about twice the pairs, and an edge x vertex search about four times."""
    counts = []
    for n_walls in (4, 8):
        Pw, fw, ok, table = _scene(11, n_walls=n_walls, depth=7)
        stats = {}
        find_t_vertices(Pw, table, TOL, stats=stats)
        counts.append(stats["pairs_tested"])
    assert counts[1] <= 3 * counts[0]


def test_bounded_pairs_peak_matches_oracle():
    """stats['pairs_peak'] must be at most chunk_pairs, and chunk_pairs=1000 gives
    identical results to default and oracle on a dense synthetic scene."""
    Pw, fw, ok, table = _scene(0, n_walls=4, depth=5)
    stats_chunked = {}
    stats_default = {}
    ref = find_t_vertices_reference(Pw, table, TOL)
    res_chunked = find_t_vertices(Pw, table, TOL, stats=stats_chunked, chunk_pairs=1000)
    res_default = find_t_vertices(Pw, table, TOL, stats=stats_default)
    assert _same(ref, res_default)
    assert _same(ref, res_chunked)
    assert stats_chunked["pairs_tested"] == stats_default["pairs_tested"]
    assert stats_chunked["pairs_tested"] > 1000
    assert 0 < stats_chunked["pairs_peak"] <= 1000
    assert stats_default["pairs_peak"] <= 1_000_000


def test_long_diagonal_edge_uses_full_scan_fallback():
    """An edge whose bounding box would visit more cells than candidate vertices
    falls back to testing all candidates directly, matching the reference oracle."""
    P, F = _scene_raw(0, n_walls=4, depth=5)
    min_p = P.min(axis=0)
    max_p = P.max(axis=0)
    b = len(P)
    diag_triangle = np.array([
        [min_p[0], min_p[1], min_p[2]],
        [max_p[0], max_p[1], max_p[2]],
        [min_p[0], max_p[1], min_p[2] + 10.0],
    ])
    P_diag = np.vstack([P, diag_triangle])
    F_diag = np.vstack([F, [[b, b + 1, b + 2]]])
    Pw, fw, ok, table = _prepared(P_diag, F_diag)

    stats = {}
    ref = find_t_vertices_reference(Pw, table, TOL)
    res = find_t_vertices(Pw, table, TOL, stats=stats)

    assert _same(ref, res)
    assert "full_scan_edges" in stats
    assert stats["full_scan_edges"] >= 1


