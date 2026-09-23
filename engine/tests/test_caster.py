import numpy as np

from engine.rays.caster import BruteCaster, EmbreeCaster, ReusableCaster
from engine.tests.fixtures.build import cube, grid_slab


def _stack(*meshes):
    """Combine several fixture meshes into one (positions, faces) pair, offsetting face
    indices so each mesh's own vertex block stays intact."""
    positions, faces, offset = [], [], 0
    for m in meshes:
        positions.append(m.positions)
        faces.append(m.face_v + offset)
        offset += len(m.positions)
    return np.concatenate(positions, axis=0), np.concatenate(faces, axis=0)


def test_ray_straight_down_hits_cube_top_at_t_10():
    m = cube(10.0)
    for Caster in (EmbreeCaster, BruteCaster):
        caster = Caster(m.positions, m.face_v)
        tri, t = caster.first_hit(np.array([[5.0, 5.0, 20.0]]), np.array([[0.0, 0.0, -1.0]]))
        assert tri[0] >= 0
        assert np.isclose(t[0], 10.0, atol=1e-6)


def test_ray_missing_cube_reports_miss():
    m = cube(10.0)
    for Caster in (EmbreeCaster, BruteCaster):
        caster = Caster(m.positions, m.face_v)
        tri, t = caster.first_hit(np.array([[100.0, 100.0, 100.0]]), np.array([[0.0, 0.0, -1.0]]))
        assert tri[0] == -1
        assert np.isinf(t[0])


def test_any_hit_agrees_with_first_hit_non_negative():
    m = cube(10.0)
    origins = np.array([[5.0, 5.0, 20.0], [100.0, 100.0, 100.0], [5.0, 5.0, -20.0]])
    directions = np.tile([0.0, 0.0, -1.0], (3, 1))
    for Caster in (EmbreeCaster, BruteCaster):
        caster = Caster(m.positions, m.face_v)
        tri, _ = caster.first_hit(origins, directions)
        hit = caster.any_hit(origins, directions)
        assert hit.dtype == np.bool_
        assert (hit == (tri >= 0)).all()


def test_embree_and_brute_oracle_agree_on_random_rays():
    positions, faces = _stack(grid_slab(10, 10), cube())
    embree = EmbreeCaster(positions, faces)
    brute = BruteCaster(positions, faces)

    rng = np.random.default_rng(7)  # test code only, no randomness in production code
    n_rays = 2000
    lo, hi = positions.min(axis=0), positions.max(axis=0)
    diag = float(np.linalg.norm(hi - lo))
    directions = rng.normal(size=(n_rays, 3))
    directions /= np.linalg.norm(directions, axis=1, keepdims=True)
    origins = rng.uniform(lo, hi, size=(n_rays, 3)) - directions * diag * 2

    tri_e, t_e = embree.first_hit(origins, directions)
    tri_b, t_b = brute.first_hit(origins, directions)

    hit_e, hit_b = tri_e >= 0, tri_b >= 0
    agree = hit_e == hit_b
    assert agree.mean() >= 0.999

    both = hit_e & hit_b
    assert both.any()
    assert np.abs(t_e[both] - t_b[both]).max() <= 1e-3


# ---------------------------------------------------------------------------------------------
# M4: all_hits -- every surface along the ray, not just the nearest one. The guard's z-fight tie
# test needs the whole tie set (every hit within `depth_tol` of the first) to tell "the same two
# overlapping faces, a different winner" from "one of them is gone".
# ---------------------------------------------------------------------------------------------

def _sorted_hits(caster, origins, directions):
    ray, tri, t = caster.all_hits(origins, directions)
    order = np.lexsort((tri, t, ray))
    return ray[order], tri[order], t[order]


def test_all_hits_reports_the_far_side_of_a_cube_as_well_as_the_near_one():
    m = cube(10.0)
    # off the quad's own diagonal: straight down the middle the ray grazes the shared edge of the
    # top face's two triangles and legitimately meets four surfaces, not two.
    origins = np.array([[3.0, 4.0, 20.0]])
    directions = np.array([[0.0, 0.0, -1.0]])
    for Caster in (EmbreeCaster, BruteCaster):
        ray, tri, t = _sorted_hits(Caster(m.positions, m.face_v), origins, directions)
        assert ray.tolist() == [0, 0]
        assert np.allclose(np.sort(t), [10.0, 20.0], atol=1e-4)   # top face, then the floor
        assert len(set(tri.tolist())) == 2


def test_all_hits_reports_nothing_for_a_ray_that_misses():
    m = cube(10.0)
    origins = np.array([[100.0, 100.0, 100.0]])
    directions = np.array([[0.0, 0.0, -1.0]])
    for Caster in (EmbreeCaster, BruteCaster):
        ray, tri, t = Caster(m.positions, m.face_v).all_hits(origins, directions)
        assert len(ray) == len(tri) == len(t) == 0


def _coincident_pair():
    """File B's real z-fight, in its own coordinates: two triangles in the SAME plane
    (y = 767.05) sharing an edge and overlapping, wound opposite ways -- a SketchUp double face.
    Which one a first-hit cast returns is arbitrary; both are really there."""
    P = np.array([[-408.58, 767.05, 156.96], [-369.21, 767.05, 147.64],
                   [-408.58, 767.05, 147.64], [-369.21, 767.05, 151.78]])
    F = np.array([[0, 1, 2], [2, 3, 0]], np.int64)
    d = np.array([1.013, 1.007, 0.011])
    d = d / np.linalg.norm(d)
    origins = (np.array([-400.0, 767.05, 150.0]) - d * 500.0)[None, :]
    return P, F, origins, d[None, :]


def test_all_hits_reports_both_faces_of_an_exactly_coincident_overlap():
    """Embree's own multi-hit walk advances the ray past each hit by `max(1e-8, scale * 1e-6)`,
    so it can never report two hits at the SAME depth -- on this pair it returns one triangle and
    stops. `all_hits` has to report both, or the guard's tie test can never fire on the very
    defect it was written for."""
    P, F, origins, directions = _coincident_pair()
    for Caster in (EmbreeCaster, BruteCaster):
        ray, tri, t = _sorted_hits(Caster(P, F), origins, directions)
        assert ray.tolist() == [0, 0], f"{Caster.__name__} reported {len(ray)} hit(s), not 2"
        assert sorted(tri.tolist()) == [0, 1]
        assert abs(t[0] - t[1]) < 1e-3          # the same depth: that is what makes it a tie


def test_all_hits_agrees_with_the_brute_oracle_on_random_rays():
    positions, faces = _stack(grid_slab(10, 10), cube())
    rng = np.random.default_rng(11)  # test code only, no randomness in production code
    lo, hi = positions.min(axis=0), positions.max(axis=0)
    diag = float(np.linalg.norm(hi - lo))
    directions = rng.normal(size=(500, 3))
    directions /= np.linalg.norm(directions, axis=1, keepdims=True)
    origins = rng.uniform(lo, hi, size=(500, 3)) - directions * diag * 2

    ray_e, tri_e, t_e = _sorted_hits(EmbreeCaster(positions, faces), origins, directions)
    ray_b, tri_b, t_b = _sorted_hits(BruteCaster(positions, faces), origins, directions)

    # count of hits per ray agrees for the overwhelming majority (embree's float32 vertices put a
    # few grazing rays on the other side of an edge)
    n_e = np.bincount(ray_e, minlength=500)
    n_b = np.bincount(ray_b, minlength=500)
    assert (n_e == n_b).mean() >= 0.98
    assert (n_b >= 2).sum() >= 10   # the fixture really does stack surfaces along some rays


# ---------------------------------------------------------------------------------------------
# Task 7: ReusableCaster -- build one caster per distinct geometry, reuse it across many calls
# with the SAME (positions, faces) objects, so a 26-view render loop doesn't rebuild the BVH once
# per view. Results must stay bit-identical to building fresh every call.
# ---------------------------------------------------------------------------------------------

def test_reusable_caster_returns_the_identical_instance_for_the_same_geometry_objects():
    m = cube(10.0)
    factory = ReusableCaster(EmbreeCaster)
    c1 = factory(m.positions, m.face_v)
    c2 = factory(m.positions, m.face_v)
    assert c1 is c2
    assert isinstance(c1, EmbreeCaster)


def test_reusable_caster_rebuilds_for_a_different_geometry_object():
    m1, m2 = cube(10.0), cube(20.0)
    factory = ReusableCaster(EmbreeCaster)
    c1 = factory(m1.positions, m1.face_v)
    c2 = factory(m2.positions, m2.face_v)
    c3 = factory(m1.positions, m1.face_v)  # switching back rebuilds again -- a size-1 cache
    assert c1 is not c2
    assert c3 is not c1


def test_reusable_caster_wraps_any_factory_and_only_skips_construction_not_ray_casts():
    m = cube(10.0)
    builds = []

    class CountingBrute(BruteCaster):
        def __init__(self, positions, faces):
            builds.append(1)
            super().__init__(positions, faces)

    factory = ReusableCaster(CountingBrute)
    origins = np.array([[5.0, 5.0, 20.0], [100.0, 100.0, 100.0]])
    directions = np.tile([0.0, 0.0, -1.0], (2, 1))

    tri_a, t_a = factory(m.positions, m.face_v).first_hit(origins, directions)
    tri_b, t_b = factory(m.positions, m.face_v).first_hit(origins, directions)

    assert len(builds) == 1  # one construction serves both calls
    assert np.array_equal(tri_a, tri_b) and np.array_equal(t_a, t_b)
    # bit-identical to a fresh caster built directly, not just internally consistent
    fresh_tri, fresh_t = BruteCaster(m.positions, m.face_v).first_hit(origins, directions)
    assert np.array_equal(tri_a, fresh_tri) and np.array_equal(t_a, fresh_t)


# ---------------------------------------------------------------------------------------------
# M4b: the coincident-hit recovery is GEOMETRIC. Recovering coincident faces by looking only at
# the triangles that share a vertex with the one embree returned misses a coincident face welded
# from an independently drawn loop -- which shares no vertex at all.
# ---------------------------------------------------------------------------------------------

def _coincident_pair_sharing_no_vertex():
    """The same plane and the same outline as `_coincident_pair`, but the second triangle is
    built on its OWN copies of the positions, so the two faces have disjoint vertex ids -- two
    loops drawn separately and never welded, which a SketchUp export really does produce."""
    P, F, origins, directions = _coincident_pair()
    doubled = np.vstack([P, P])
    faces = np.array([F[0], F[1] + len(P)], np.int64)
    assert not (set(faces[0].tolist()) & set(faces[1].tolist()))
    return doubled, faces, origins, directions


def test_all_hits_reports_a_coincident_face_that_shares_no_vertex():
    P, F, origins, directions = _coincident_pair_sharing_no_vertex()
    for Caster in (EmbreeCaster, BruteCaster):
        ray, tri, t = _sorted_hits(Caster(P, F), origins, directions)
        assert ray.tolist() == [0, 0], f"{Caster.__name__} reported {len(ray)} hit(s), not 2"
        assert sorted(tri.tolist()) == [0, 1]
        assert abs(t[0] - t[1]) < 1e-3


def test_all_hits_leaves_a_separated_face_to_embrees_own_walk():
    """Why the recovery tolerance is the width of the band embree SKIPS and not the guard's
    `depth_tol`: measured on this pair, the multi-hit walk reports both faces itself, at their
    own true depths, for every separation down to 0.001 in -- its step on this mesh is 4e-5 in.
    Only an exact coincidence is stepped over. A `depth_tol`-wide recovery would find nothing
    new; it would re-report a face embree had already returned, at the hit face's depth instead
    of its own, which is a depth that face does not have."""
    for nudge in (0.001, 0.01, 0.05):
        P, F, origins, directions = _coincident_pair_sharing_no_vertex()
        P = P.copy()
        P[len(P) // 2:, 1] += nudge     # along the plane normal, so the ray meets them apart
        ray, tri, t = _sorted_hits(EmbreeCaster(P, F), origins, directions)
        assert sorted(tri.tolist()) == [0, 1], f"nudge {nudge}: {tri.tolist()}"
        assert 0.0 < abs(t[0] - t[1]) < 0.15   # two depths, both inside the guard's tolerance
