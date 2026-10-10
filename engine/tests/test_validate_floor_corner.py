"""Job P2-V2 item 4: a mesh that is a subset of BEFORE's faces never newly blocks a line (the corner artefact).

P2-E3 concern 3: on CHTM 5th a probe's line through the corner of face 10553 missed everything in BEFORE and hit that
very face in AFTER, a subset of BEFORE's faces -- 4 false `covered` samples, 21 sites rolled back. The cause: the float32
caster's verdict on a line through a shared vertex or edge depends on the whole mesh it was built from. Measured both
ways: trimesh's Embree wrapper scales each mesh by its own size before rounding to float32 (this fixture: the same
origin, scale 0.26 against 5.88), and on CHTM 5th the two meshes had the very same frame and their Embree trees still
disagreed on face 10553's corner. So a line slips through one caster and not the other.

The fixture: a floor under an opaque grid of triangles, every probe placed on the line from a floor sample's ray
origin through a vertex of the grid, and a zero-area face far off. AFTER drops that face only, so it is a face subset
of BEFORE (its vertices stay) with another size.
"""
import numpy as np

from engine.tests.fixtures.build import _mesh
from engine.tests.test_validate_checks import _check, _looks, _without_faces
from engine.validate.checks import changed_faces
from engine.validate.sampling import face_samples, recentred
from engine.validate.visibility import EPS_ORIGIN, build_caster

NONE = np.zeros((0, 3))


def grid_over_floor(seed, n=12, cell=0.37):
    """`(mesh, first grid vertex, n)`: a floor (faces 0, 1) at z = 0 under an n x n grid of triangles at z ~ 1.3 with
    alternating diagonals, and last a zero-area face far off, below and to the side, which is the lowest corner."""
    rng = np.random.default_rng(seed)
    P = [[-3, -3, 0], [9, -3, 0], [9, 9, 0], [-3, 9, 0]]
    fv = [[0, 1, 2], [0, 2, 3]]
    base = len(P)
    off = rng.uniform(0, 0.1, 2)
    for j in range(n + 1):
        for i in range(n + 1):
            P.append([off[0] + i * cell + 0.0123, off[1] + j * cell + 0.0457, 1.3 + 0.001 * rng.uniform()])
    vid = lambda i, j: base + j * (n + 1) + i
    for j in range(n):
        for i in range(n):
            a, b, c, d = vid(i, j), vid(i + 1, j), vid(i + 1, j + 1), vid(i, j + 1)
            fv += [[a, b, c], [a, c, d]] if (i + j) % 2 else [[a, b, d], [b, c, d]]
    k = len(P)
    P += [[-300.7, -211.3, -57.1], [-299.7, -211.3, -57.1], [-298.7, -211.3, -57.1]]     # collinear: no area
    fv += [[k, k + 1, k + 2]]
    return _mesh("grid_over_floor", P, [[0, 0]] * len(P), fv, [[0, 0, 0]] * len(fv)), base, n


def _lines(mesh, base, n):
    """`(origins, probes)`: every floor sample's ray origin (stepped `EPS_ORIGIN` up, toward the probes) and, for
    every grid vertex, a probe 3 times as far along the line from that origin through the vertex."""
    s = face_samples(mesh, faces=[0, 1]).points + [0.0, 0.0, EPS_ORIGIN]
    verts = mesh.positions[base:base + (n + 1) ** 2]
    origins = np.repeat(s, len(verts), axis=0)
    return origins, origins + 3.0 * (np.tile(verts, (len(s), 1)) - origins)


def test_the_fixture_has_lines_one_caster_lets_through_and_the_other_blocks():
    m, base, n = grid_over_floor(0)
    b, centre = recentred(m)
    a, _ = recentred(_without_faces(m, [m.n_faces - 1]), centre)
    origins, probes = _lines(b, base, n)
    d = probes - origins
    d /= np.linalg.norm(d, axis=1, keepdims=True)
    through_b, through_a = ~build_caster(b).any_hit(origins, d), ~build_caster(a).any_hit(origins, d)
    assert (through_b & ~through_a).any(), "some line leaks through a vertex in BEFORE and is blocked in AFTER"
    assert not changed_faces(b, a).any(), "AFTER is a face subset of BEFORE: no new geometry"


def test_an_after_that_is_a_face_subset_of_before_covers_nothing_on_any_line():
    for seed in range(3):
        m, base, n = grid_over_floor(seed)
        _origins, probes = _lines(m, base, n)
        v = _check(m, _without_faces(m, [m.n_faces - 1]), _looks("m0"), dirs=NONE, cams=NONE, probes=probes,
                   extra_dirs=NONE)
        gone = v.report["checks"]["nothing_deleted"]
        assert gone["covered"] == 0 and v.report["checks"]["textures"]["reasons"]["covered"] == 0, seed
        assert gone["floor"]["candidates"]["covered"] == 0 and gone["floor"]["failing"] == [], seed
        assert gone["status"] == "PASS" and v.report["verdict"] == "PASS", seed
