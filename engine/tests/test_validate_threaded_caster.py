"""Job P2-V2: the Validator's caster casts big batches on several threads, with the very answers of one thread.

The floor measure (`engine.validate.floor`) and the dense lattice cast many more rays than the 4-9 samples a face
had; Embree answers each ray on its own, so a batch split over threads gives the same `tri` and `t`, faster.
"""
import numpy as np

from engine.rays.caster import EmbreeCaster
from engine.tests.fixtures.build import closed_room
from engine.validate.sampling import recentred
from engine.validate.visibility import THREAD_MIN_RAYS, build_caster


def test_a_big_batch_is_cast_on_threads_with_the_answers_of_one_thread():
    m, _ = recentred(closed_room())
    serial = EmbreeCaster(m.positions, m.face_v)
    threaded = build_caster(m)
    assert threaded.threads > 1, "build_caster casts a big batch on more than one thread"
    rng = np.random.default_rng(7)
    n = 4 * THREAD_MIN_RAYS + 13
    o = rng.uniform(-150.0, 150.0, (n, 3))
    d = rng.normal(size=(n, 3))
    d /= np.linalg.norm(d, axis=1, keepdims=True)
    tri_s, t_s = serial.first_hit(o, d)
    tri_t, t_t = threaded.first_hit(o, d)
    assert np.array_equal(tri_s, tri_t) and np.array_equal(t_s, t_t)
    assert np.array_equal(serial.any_hit(o, d), threaded.any_hit(o, d))
    assert (tri_s >= 0).any() and (tri_s < 0).any(), "the batch both hits and misses"
    assert np.array_equal(threaded.faces, m.face_v)
