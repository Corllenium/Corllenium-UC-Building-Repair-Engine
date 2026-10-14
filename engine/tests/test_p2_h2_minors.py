"""Job P2-H2: small fixes the P2-E3 and P2-E8c reviews parked."""
from __future__ import annotations

import numpy as np
import pytest

from engine.campus.needs_modelling import build_needs_modelling
from engine.repair.engines.e3_hidden import MAX_SITE_FACES, E3Hidden, split_group
from engine.repair.types import RepairContext, UnitState
from engine.site_judge import SiteJudge
from engine.tests.fixtures import build as B
from engine.tests.test_e3_hidden import _FAST
from engine.tests.test_validate_checks import _looks


def _grid_centroids(nx: int = 32, ny: int = 32, span_xy: float = 100.0, z_jitter: float = 0.0) -> np.ndarray:
    """Centroids of a flat `nx` x `ny` grid of `2 * nx * ny` triangles over `span_xy` x `span_xy` in, with z jittered
    deterministically within `[-z_jitter, +z_jitter]`."""
    xs = np.linspace(0.0, span_xy, nx + 1)
    ys = np.linspace(0.0, span_xy, ny + 1)
    centroids = []
    for i in range(nx):
        for j in range(ny):
            x0, x1 = xs[i], xs[i + 1]
            y0, y1 = ys[j], ys[j + 1]
            centroids.append([(2 * x0 + x1) / 3.0, (2 * y0 + y1) / 3.0, 0.0])
            centroids.append([(x0 + 2 * x1) / 3.0, (y0 + 2 * y1) / 3.0, 0.0])
    pts = np.asarray(centroids, dtype=np.float64)
    if z_jitter > 0.0:
        rng = np.random.default_rng(42)
        pts[:, 2] = rng.uniform(-z_jitter, z_jitter, size=len(pts))
    return pts


def test_item1_near_flat_groups_are_not_over_split():
    flat = _grid_centroids(32, 32, 100.0, z_jitter=0.0)
    jittered = _grid_centroids(32, 32, 100.0, z_jitter=0.0005)
    ids = np.arange(len(flat), dtype=np.int64)
    assert len(ids) == 2048

    sites_flat = split_group(ids, flat)
    sites_jittered = split_group(ids, jittered)

    assert len(sites_jittered) == len(sites_flat)
    assert all(len(s) <= MAX_SITE_FACES for s in sites_jittered)
    assert sorted(int(f) for s in sites_jittered for f in s) == list(range(2048))


def test_item2_every_e3_edit_rule_is_hidden_on_box_with_partition():
    mesh = B.box_with_partition()
    engine = E3Hidden()
    unit = UnitState(mesh=mesh, topo=None, looks={}, viewpoints=None)
    judge = SiteJudge(_looks(*mesh.materials), margin=2.0)
    edits = engine.plan(unit, RepairContext(profile=_FAST, decider=None, validator=judge))
    assert edits
    for edit in edits:
        assert edit.evidence["rules"] == ["hidden"] * len(edit.faces)


def test_item3_needs_modelling_cross_check_reads_only_e8_lines():
    report = {
        "unit": "ARCH-L03",
        "pieces": [{
            "site": 5,
            "piece": "wall",
            "kept": False,
            "reasons": {"covered": 10},
            "border": [[0.0, 0.0, 0.0], [10.0, 0.0, 0.0], [10.0, 0.0, 10.0], [0.0, 0.0, 10.0]],
            "border_ordered": True,
            "area_in2": 100.0,
            "normal": [0.0, -1.0, 0.0],
        }],
    }
    e3_only_log = [{"stage": "E3", "engine": "E3", "site": 5, "rolled_back": True}]
    with pytest.raises(ValueError, match="site 5"):
        build_needs_modelling(report, e3_only_log, None)

    e8_log = e3_only_log + [{"stage": "E8", "engine": "E8", "site": 5, "rolled_back": True}]
    doc = build_needs_modelling(report, e8_log, None)
    assert doc["counts"]["entries"] == 1 and doc["entries"][0]["site"] == 5


