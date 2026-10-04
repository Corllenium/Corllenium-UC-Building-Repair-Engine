"""P1-S3 acceptance: the new double_layers against the old one, on real snapshots.

Prepares each snapshot exactly as `engine.detectors.errors.find_errors` does (analyse_topology,
centred positions, the guard's depth tolerance, the 26 views at the profile's guard size), then
runs `double_layers_reference` (the old function) and `double_layers` (the new one). Prints, per
snapshot: the size, whether the two results are equal, both times and the speed-up, the new
search's counters, and the peak memory numpy allocated in each call (tracemalloc, measured in a
second run so the timings are clean). Exits 1 if any result differs.

    PY="D:/PROJECTS/UC MODEL FIXER/.venv/Scripts/python.exe"
    ( cd <worktree> && PYTHONPATH="$PWD" "$PY" docs/superpowers/records/scripts/double_layers_check.py <snapshot dir>... )
"""
import sys
import time
import tracemalloc
from pathlib import Path

from engine.cli import _load_snapshot
from engine.fixes.overlap import double_layers, double_layers_reference
from engine.fixes.pipeline import FixProfile, guard_depth_tol
from engine.guard.views import VIEWS_26
from engine.pipeline import analyse_topology


def _peak_mb(fn, *args, **kw) -> float:
    tracemalloc.start()
    try:
        fn(*args, **kw)
        return tracemalloc.get_traced_memory()[1] / 2 ** 20
    finally:
        tracemalloc.stop()


def check(snapshot: Path) -> bool:
    _obj, mesh, _flatness, _mtl = _load_snapshot(Path(snapshot))
    profile = FixProfile()
    topo = analyse_topology(mesh, frozenset(), coplanar_angle=profile.coplanar_angle,
                            soft_angle=profile.soft_angle)
    pos, faces = topo.positions_w, topo.face_w
    centre = (pos.min(axis=0) + pos.max(axis=0)) / 2.0
    args = (pos - centre, faces, guard_depth_tol(topo.quanta, profile), VIEWS_26, profile.guard_size)

    t0 = time.perf_counter()
    old = double_layers_reference(*args, centre=centre)
    t_old = time.perf_counter() - t0
    stats = {}
    t0 = time.perf_counter()
    new = double_layers(*args, centre=centre, stats=stats)
    t_new = time.perf_counter() - t0
    mb_old = _peak_mb(double_layers_reference, *args, centre=centre)
    mb_new = _peak_mb(double_layers, *args, centre=centre)

    n = len(faces)
    same = new == old
    print(f"{mesh.name}: faces {n} pairs {old['count']} planes {len(old['planes'])} px {old['px']} "
          f"equal {same} old {t_old:.1f} s new {t_new:.1f} s speed-up {t_old / t_new:.1f}x "
          f"bbox_pairs {stats.get('bbox_pairs')} (all pairs {n * (n - 1) // 2}) "
          f"pairs_tested {stats.get('pairs_tested')} pixel_rows_max {stats.get('pixel_rows_max')} "
          f"peak MB old {mb_old:.0f} new {mb_new:.0f}")
    return same


if __name__ == "__main__":
    results = [check(Path(p)) for p in sys.argv[1:]]
    sys.exit(0 if results and all(results) else 1)
