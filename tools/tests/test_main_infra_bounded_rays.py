"""Opt-in real-floor timing and independent exhaustive-oracle readback."""
import json
import os
from pathlib import Path
import time

import numpy as np
import pytest

from engine.guard.views import VIEWS_26, ortho_first_hit
from engine.io.minecraft_floor import parse_floor
from engine.io.snapshot import sha256_file
from engine.rays.bounded_brute import BoundedBruteCaster
from engine.rays.caster import BruteCaster


@pytest.mark.skipif(not os.environ.get('MAIN_INFRA_RAY_BASELINE'), reason='Explicit frozen real pilot path required')
def test_real_floor_bounded_oracle_timing_and_readback():
    source = Path(os.environ['MAIN_INFRA_RAY_BASELINE'])
    mesh = parse_floor(source.read_text(encoding='utf-8')).mesh
    positions = mesh.positions - (mesh.positions.min(axis=0) + mesh.positions.max(axis=0)) / 2
    caster = BoundedBruteCaster(positions, mesh.face_v)
    started = time.perf_counter()
    buf = ortho_first_hit(positions, mesh.face_v, np.arange(mesh.n_faces), VIEWS_26[0], positions,
                          (160, 120), lambda *_: caster)
    seconds = time.perf_counter() - started
    leaf_pairs = caster.search_stats['leaf_pairs']
    origins = buf.origins.reshape(-1, 3)[::1600]
    directions = np.tile(buf.direction, (len(origins), 1))
    oracle = BruteCaster(positions, mesh.face_v)
    for actual, expected in zip(caster.first_hit(origins, directions), oracle.first_hit(origins, directions)):
        np.testing.assert_array_equal(actual, expected)
    actual = np.array(caster.all_hits(origins, directions)).T
    expected = np.array(oracle.all_hits(origins, directions)).T
    if len(actual):
        actual = actual[np.lexsort((actual[:, 1], actual[:, 0]))]
    np.testing.assert_array_equal(actual, expected)
    result = dict(source_sha256=sha256_file(source), triangles=mesh.n_faces, pixels=19200,
        seconds=seconds, leaf_pairs=leaf_pairs, exhaustive_pairs=19200 * mesh.n_faces,
        sampled_rays=len(origins), sample_first_and_all_match=True)
    print(json.dumps(result))
    if os.environ.get('MAIN_INFRA_RAY_REPORT'):
        Path(os.environ['MAIN_INFRA_RAY_REPORT']).write_text(json.dumps(result, indent=2), encoding='utf-8')
