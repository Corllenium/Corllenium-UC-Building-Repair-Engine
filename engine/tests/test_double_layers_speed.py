"""P1-S3: double_layers, made sub-quadratic, must give exactly the old answer.

Claude wrote and committed these tests before the job was queued (the P1-P2 plan's rolling-brief
rule); the job makes them pass without changing them.

- `double_layers_reference` is the old function, kept verbatim as the oracle.
- `double_layers` is the new one: the same signature plus two keyword-only arguments:
  - `stats`: a dict that receives
    - `bbox_pairs`: how many distinct face pairs (i < j) the candidate search compared bounding
      boxes for;
    - `pairs_tested`: how many candidate pairs reached the separation and shared-area tests;
    - `pixel_rows_max`: the largest number of (pixel, partner) rows the pixel stage evaluated at
      once;
  - `chunk_rows` (default 1_000_000): the most (pixel, partner) rows the pixel stage evaluates at
    once, so its memory stays bounded.

"Exactly" means the two returned dicts are equal: count, area, px, every plane (in order, every
field) and pair_list.
"""
import numpy as np
import pytest

from engine.fixes.overlap import double_layers, double_layers_reference
from engine.guard.views import VIEWS_26
from engine.tests.fixtures import build as fixtures

SIZE = (90, 60)  # small renders: the pixel stage's code path is the same at any size


def _call(fn, P, F, depth_tol, **kw):
    P = np.asarray(P, float)
    centre = (P.min(axis=0) + P.max(axis=0)) / 2
    return fn(P - centre, np.asarray(F, np.int64), depth_tol, VIEWS_26, kw.pop("size", SIZE),
              centre=centre, **kw)


def _both(P, F, depth_tol, **kw):
    return (_call(double_layers_reference, P, F, depth_tol, **dict(kw)),
            _call(double_layers, P, F, depth_tol, **dict(kw)))


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


def _wall(rng, size, depth, p_split=0.5, flip=False):
    """A flat z = 0 wall of quadtree rectangles, two triangles each (wound the other way if `flip`)."""
    P, F = [], []
    for x0, y0, x1, y1 in _quadtree_rects(rng, size, depth, p_split):
        b = len(P)
        P += [[x0, y0, 0.0], [x1, y0, 0.0], [x1, y1, 0.0], [x0, y1, 0.0]]
        F += [[b, b + 2, b + 1], [b, b + 3, b + 2]] if flip else [[b, b + 1, b + 2], [b, b + 2, b + 3]]
    return np.array(P), np.array(F, np.int64)


def _rotation(axis, degrees):
    a = np.radians(degrees)
    c, s = np.cos(a), np.sin(a)
    x, y, z = np.asarray(axis, float) / np.linalg.norm(axis)
    return np.array([[c + x * x * (1 - c), x * y * (1 - c) - z * s, x * z * (1 - c) + y * s],
                     [y * x * (1 - c) + z * s, c + y * y * (1 - c), y * z * (1 - c) - x * s],
                     [z * x * (1 - c) - y * s, z * y * (1 - c) + x * s, c + z * z * (1 - c)]])


#: How the second layer of each wall sits on the first (depth_tol is 0.15 in these scenes).
LAYERS = [
    ("coplanar", {}),                      # drawn twice in one plane
    ("offset", {"dz": 0.08}),              # inside the depth band
    ("far", {"dz": 0.4}),                  # outside it: no pair
    ("flipped", {"flip": True, "dz": 0.03}),  # opposite winding
    ("tilted", {"tilt": 1.5}),             # parallel within 0.999, but only near the hinge
    ("tilted_far", {"tilt": 3.5}),         # not parallel enough: no pair
    ("shifted", {"shift": (37.5, 12.5)}),  # overlapping in part
]


def _layered(seed, n_walls=7, size=100.0, depth=4, spacing=300.0):
    """Walls of two layers each, one LAYERS case per wall in turn; every other wall turned into a
    random skew plane. Different random subdivisions in the two layers make every kind of partial
    overlap between their triangles."""
    rng = np.random.default_rng(seed)
    parts, faces, base = [], [], 0
    for w in range(n_walls):
        _name, opt = LAYERS[w % len(LAYERS)]
        P1, F1 = _wall(rng, size, depth)
        P2, F2 = _wall(rng, size, depth, flip=opt.get("flip", False))
        if "tilt" in opt:
            hinge = np.array([size / 2, size / 2, 0.0])
            P2 = (P2 - hinge) @ _rotation([1.0, 0.3, 0.0], opt["tilt"]).T + hinge
        P2 = P2 + [*opt.get("shift", (0.0, 0.0)), opt.get("dz", 0.0)]
        P = np.concatenate([P1, P2])
        F = np.concatenate([F1, F2 + len(P1)])
        if w % 2:
            P = P @ _rotation(rng.normal(size=3), rng.uniform(10.0, 80.0)).T
        parts.append(P + [w * spacing, 0.0, 0.0])
        faces.append(F + base)
        base += len(P)
    return np.round(np.concatenate(parts), 4), np.concatenate(faces)


def _three_layers(seed, dzs=(0.0, 0.1, 0.2), size=100.0, depth=4):
    """One wall drawn three times at heights `dzs`, each layer with its own subdivision; the faces
    are shuffled, so the pairs' order is not simply layer by layer. At the default heights the
    planes chain -- 0 reaches 0.1, 0.1 reaches 0.2, but 0 and 0.2 are beyond depth_tol 0.15 -- so
    which plane a pair joins depends on the order the pairs are taken in. At (0, 0.05, 0.1) a ray
    that first hits an outer layer meets partners in both other layers."""
    rng = np.random.default_rng(seed)
    parts, faces, base = [], [], 0
    for dz in dzs:
        P, F = _wall(rng, size, depth)
        parts.append(P + [0.0, 0.0, dz])
        faces.append(F + base)
        base += len(P)
    F = np.concatenate(faces)
    return np.round(np.concatenate(parts), 4), F[rng.permutation(len(F))]


# ------------------------------------------------------------------------------ same answer

@pytest.mark.parametrize("build, depth_tol", [
    ("partially_overlapping_fins", 0.15), ("back_to_back_pair", 0.01), ("split_double_layer", 0.01),
    ("two_sided_wall", 0.01), ("stacked_duplicate_slab", 0.15), ("overlapping_pair", 0.15),
    ("grid_slab", 0.15)])
def test_same_answer_on_the_engine_fixtures(build, depth_tol):
    m = getattr(fixtures, build)()
    old, new = _both(m.positions, m.face_v, depth_tol, size=(120, 80))
    assert new == old


@pytest.mark.parametrize("seed, min_area", [(0, 1.0), (1, 1.0), (2, 5.0)])
def test_same_answer_on_layered_walls(seed, min_area):
    P, F = _layered(seed)
    old, new = _both(P, F, 0.15, min_area=min_area)
    assert old["count"] > 300 and len(old["planes"]) >= 3   # pairs in axis and skew planes
    assert sum(p["opposite"] for p in old["planes"]) > 0     # and opposite-wound ones
    assert new == old


def test_same_answer_when_tilted_layers_lie_far_from_the_origin():
    """Two walls 4,000 in apart, so after centring each lies about 2,000 in from the origin. Each has
    a layer tilted 0.5 deg about a hinge through its middle: within about 17 in of the hinge the
    layers share the depth band, yet their plane offsets (n . p) differ by about 16 in. A search
    that groups faces by plane offset misses these pairs; a search by position does not."""
    rng = np.random.default_rng(21)
    parts, faces, base = [], [], 0
    for x in (0.0, 4000.0):
        P1, F1 = _wall(rng, 100.0, 4)
        P2, F2 = _wall(rng, 100.0, 4)
        hinge = np.array([50.0, 50.0, 0.0])
        P2 = (P2 - hinge) @ _rotation([0.3, 1.0, 0.0], 0.5).T + hinge
        parts += [P1 + [x, 0, 0], P2 + [x, 0, 0]]
        faces += [F1 + base, F2 + base + len(P1)]
        base += len(P1) + len(P2)
    P, F = np.round(np.concatenate(parts), 4), np.concatenate(faces)
    old, new = _both(P, F, 0.15)
    assert old["count"] > 20
    assert new == old


def test_same_answer_at_the_parallel_depth_and_area_limits():
    """Six pairs, each just inside or just outside one limit of the reference: |n . m| > 0.999,
    every corner within depth_tol of the other's plane, shared area > min_area. The margins
    (1e-5) are far above rounding noise, so any search that applies the same tests to the same
    pairs agrees. Only the three 'inside' pairs are double layers."""
    tol = 0.15
    tri = np.array([[0.0, 0.0, 0.0], [2.0, 0.0, 0.0], [0.0, 2.0, 0.0]])
    big = np.array([[0.0, 0.0, 0.0], [4.0, 0.0, 0.0], [0.0, 4.0, 0.0]])
    centroid = tri.mean(axis=0)

    def tilted(dot):
        return (tri - centroid) @ _rotation([1.0, -1.0, 0.0], np.degrees(np.arccos(dot))).T + centroid

    second = [tilted(0.999 + 1e-5), tilted(0.999 - 1e-5),                 # parallel
              tri + [0, 0, tol * (1 - 1e-5)], tri + [0, 0, tol * (1 + 1e-5)],  # depth
              big + [4.0 - np.sqrt(2 * (1 + 1e-5)), 0, 0],                 # shared area 1 + 1e-5
              big + [4.0 - np.sqrt(2 * (1 - 1e-5)), 0, 0]]                 # shared area 1 - 1e-5
    first = [tri, tri, tri, tri, big, big]
    P, F = [], []
    for k, (a, b) in enumerate(zip(first, second)):
        shift = [50.0 * k, 0.0, 0.0]
        F += [[len(P), len(P) + 1, len(P) + 2], [len(P) + 3, len(P) + 4, len(P) + 5]]
        P += (a + shift).tolist() + (b + shift).tolist()
    old, new = _both(np.array(P), np.array(F), tol)
    assert [(i, j) for i, j, _s, _o in old["pair_list"]] == [(4, 5), (0, 1), (8, 9)]
    assert new == old


@pytest.mark.parametrize("seed", [6, 7])
def test_same_answer_when_three_layers_chain_their_planes(seed):
    """The reference takes the pairs by ascending (i, j) and puts each in the first plane, in the
    order the planes were made, within depth_tol of it; the new search must keep that order."""
    P, F = _three_layers(seed)
    old, new = _both(P, F, 0.15)
    assert old["count"] > 100
    assert new == old


def test_same_answer_with_zero_area_faces_and_no_faces():
    P, F = _layered(3, n_walls=2)
    F = np.concatenate([F, [[0, 0, 1], [2, 3, 3], [0, 1, 1]]])  # collapsed faces: never a pair
    old, new = _both(P, F, 0.15)
    assert new == old
    empty = np.zeros((0, 3), np.int64)
    assert double_layers(np.zeros((0, 3)), empty, 0.15) == double_layers_reference(np.zeros((0, 3)), empty, 0.15)


def test_same_pixels_whatever_the_chunk_size():
    """The pixel stage evaluates at most `chunk_rows` (pixel, partner) rows at once, and a pixel
    whose rows fall in different chunks still counts once: with three layers 0.05 in apart a ray
    often meets two partners of its first face, and a chunk of 5 rows splits many such pixels."""
    P, F = _three_layers(8, dzs=(0.0, 0.05, 0.1))
    whole = _call(double_layers, P, F, 0.15)
    s = {}
    tiny = _call(double_layers, P, F, 0.15, chunk_rows=5, stats=s)
    assert tiny == whole and whole["px"] > 0
    assert 0 < s["pixel_rows_max"] <= 5
    assert tiny == _call(double_layers_reference, P, F, 0.15)


def test_two_runs_give_the_same_answer_and_counts():
    P, F = _layered(5, n_walls=4)
    s1, s2 = {}, {}
    assert _call(double_layers, P, F, 0.15, stats=s1) == _call(double_layers, P, F, 0.15, stats=s2)
    assert s1 == s2
    assert {"bbox_pairs", "pairs_tested", "pixel_rows_max"} <= s1.keys()
    assert 0 < s1["pairs_tested"] <= s1["bbox_pairs"]


# ------------------------------------------------------------------------------- sub-quadratic

def test_bbox_pairs_stay_far_below_all_pairs_on_a_large_scene():
    """About 22 k faces: the reference compares the boxes of every pair (about 2.4e8). A search by
    position compares a small multiple of the faces (a throwaway grid prototype: 13 per face).
    Comparing every pair within one plane is still too many here: the axis-aligned walls all lie
    in the plane z = 0 and hold some 9 k faces between them."""
    P, F = _layered(11, n_walls=14, depth=6)
    n = len(F)
    assert n > 20_000
    s = {}
    _call(double_layers, P, F, 0.15, stats=s)
    assert 0 < s["bbox_pairs"] < n * n // 20


def test_bbox_pairs_double_not_quadruple_when_the_scene_doubles():
    """The 14-wall scene is the 7-wall scene plus 7 more walls (the same random stream), so a
    search by position compares about twice the pairs, and an all-pairs search about four times."""
    counts = []
    for n_walls in (7, 14):
        P, F = _layered(11, n_walls=n_walls, depth=5)
        s = {}
        _call(double_layers, P, F, 0.15, stats=s)
        counts.append(s["bbox_pairs"])
    assert counts[1] <= 3 * counts[0]
