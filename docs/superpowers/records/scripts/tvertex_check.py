"""P1-S1 acceptance: the new T-junction search against the old one, on real snapshots.

Loads each snapshot's OBJ, welds it and builds the edge table exactly as
`engine.pipeline.analyse_topology` does, then runs `find_t_vertices_reference` (the old search,
once) and `find_t_vertices` (the new one, best of 3) with the same tolerance and zero-area hints.
Prints, per snapshot: the size, whether the answers are identical, both times and the speed-up.
Exits 1 if any answer differs.

    PY="D:/PROJECTS/UC MODEL FIXER/.venv/Scripts/python.exe"
    ( cd <worktree> && PYTHONPATH="$PWD" "$PY" docs/superpowers/records/scripts/tvertex_check.py <snapshot dir>... )
"""
import sys
import time
from pathlib import Path

import numpy as np

from engine.io.obj_reader import read_obj
from engine.topo.adjacency import (build_edge_table, degenerate_mask, find_t_vertices,
                                    find_t_vertices_reference)
from engine.topo.weld import axis_quanta, weld_exact


def check(snapshot: Path) -> bool:
    objs = sorted(Path(snapshot).glob("*.obj"))
    if len(objs) != 1:
        raise SystemExit(f"{snapshot}: expected one .obj, found {len(objs)}")
    mesh = read_obj(objs[0])
    positions_w, remap = weld_exact(mesh.positions, mesh.coord_decimals)
    face_w = remap[mesh.face_v]
    ok = ~degenerate_mask(positions_w, face_w)
    table = build_edge_table(face_w, ok)
    tol = 1.5 * float(axis_quanta(positions_w, mesh.sig_digits).max())

    t0 = time.perf_counter()
    old = find_t_vertices_reference(positions_w, table, tol, face_w=face_w, degenerate=~ok)
    t_old = time.perf_counter() - t0
    t_new, new, stats = float("inf"), None, {}
    for _ in range(3):
        stats = {}
        t0 = time.perf_counter()
        new = find_t_vertices(positions_w, table, tol, face_w=face_w, degenerate=~ok, stats=stats)
        t_new = min(t_new, time.perf_counter() - t0)

    same = (old.keys() == new.keys() and all(type(k) is int for k in new)
            and all(new[k].dtype == np.int64 and np.array_equal(old[k], new[k]) for k in old))
    E, V = len(table.edges), len(np.unique(table.edges))
    print(f"{mesh.name}: tris {len(face_w)} edges {E} vertices {V} tol {tol:g} "
          f"t-junction edges {len(old)} identical {same} pairs_tested {stats.get('pairs_tested')} "
          f"(reference {E * V}) old {t_old:.2f} s new {t_new:.3f} s speed-up {t_old / t_new:.1f}x")
    return same


if __name__ == "__main__":
    results = [check(Path(p)) for p in sys.argv[1:]]
    sys.exit(0 if results and all(results) else 1)
