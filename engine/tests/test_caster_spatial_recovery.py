import numpy as np

from engine.rays.caster import EmbreeCaster


def exhaustive(caster, triangles, points, tolerance):
    lo, hi = caster._face_bounds()
    pairs = []
    for index, point in enumerate(points):
        candidates = np.flatnonzero(((point >= lo - tolerance) & (point <= hi + tolerance)).all(axis=1))
        candidates = candidates[candidates != triangles[index]]
        inside = caster._contains(candidates, np.broadcast_to(point, (len(candidates), 3)), tolerance)
        pairs.extend((index, int(face)) for face in candidates[inside])
    return pairs


def test_spatial_recovery_keeps_exact_exhaustive_results_at_boundaries_and_unshared_corners():
    rng = np.random.default_rng(29)
    triangles = rng.uniform(-100, 100, (250, 3, 3))
    triangles = np.concatenate([triangles, triangles[:40], triangles[:40, ::-1]])
    triangles = np.concatenate([triangles, np.array([[[-1000, 0, 0], [1000, 0, 0], [0, 1000, 0]]])])
    positions = triangles.reshape(-1, 3)
    caster = EmbreeCaster(positions, np.arange(len(positions)).reshape(-1, 3))
    face_ids = np.arange(len(triangles))
    points = triangles.mean(axis=1)
    for tolerance in [0.0, 1e-8, 0.001]:
        edge_points = triangles[:, 0] + np.array([tolerance, 0, 0])
        for sample in [points, edge_points]:
            got = list(zip(*[arr.tolist() for arr in caster._coincident_with(face_ids, sample, tolerance)]))
            assert got == exhaustive(caster, face_ids, sample, tolerance)


def test_sparse_floor_recovery_avoids_the_full_hit_by_face_product():
    count = 5000
    triangles = np.array([[[i * 3, 0, 0], [i * 3 + 1, 0, 0], [i * 3, 1, 0]] for i in range(count)], float)
    triangles = np.concatenate([triangles, triangles])
    points = triangles[:count].mean(axis=1)
    positions = triangles.reshape(-1, 3)
    caster = EmbreeCaster(positions, np.arange(len(positions)).reshape(-1, 3))
    hit, face = caster._coincident_with(np.arange(count), points, 1e-8)
    assert hit.tolist() == list(range(count))
    assert face.tolist() == list(range(count, 2 * count))
    assert caster.coincident_search_stats['bbox_pairs'] < count * len(triangles) // 20
