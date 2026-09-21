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
