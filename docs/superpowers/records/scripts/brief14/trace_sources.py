"""Brief 14 items 2 and 3: why the duplicate-layer pass keeps a stacked copy, what a wider rule
would remove, and where each z-fight source comes from in the export.

On the stage `remove_overlaps` is handed (rebuilt by `zfight_sources.overlap_stage` and checked
against the run's own removals):
- for the reference faces named on the command line, the region, the plane cluster, whether any
  welded edge joins them to the faces they lie on, the duplicate pairs the pass found for them and
  the part their own region covers;
- the WIDER rule measured, not adopted: a same-wound face is covered by the other faces of its
  PLANE GROUP with the same material and the same winding (whatever their region), >= 0.99, the
  candidates walked like `plan_overlap_removal` (each re-measured against what is still kept), and
  the strict guard asked -- what it would remove, and what the guard confirms;
- per z-fight source of `zfight_sources.py`'s JSON: the export's own windings, OBJ lines and
  whether the two already overlap in the INPUT.

Usage (repo root as cwd and PYTHONPATH):
  trace_sources.py <result.pkl> <zfight json> [reference face ids to explain ...]"""
from __future__ import annotations

import json
import pickle
import sys
from pathlib import Path

import numpy as np
import shapely

sys.path.insert(0, str(Path(__file__).resolve().parent))
from zfight_sources import overlap_stage  # noqa: E402

from engine.fixes.overlap import (COVERED_FRACTION, covered_fractions, plan_overlap_removal,  # noqa: E402
                                  plane_groups)
from engine.fixes.pipeline import guard_depth_tol  # noqa: E402
from engine.guard.compare import guard_feedback  # noqa: E402
from engine.topo.adjacency import edge_face_lists  # noqa: E402
from engine.topo.planes import cluster_planes, face_normals, plane_basis  # noqa: E402


def wider_candidates(mesh, topo, already: np.ndarray):
    """Faces the wider rule proposes: covered >= COVERED_FRACTION by the union of the OTHER
    faces of their plane group with the same material and the same winding, walked in
    (-face id) order and re-measured against what is still kept."""
    tri = topo.positions_w[topo.face_w]
    normal = face_normals(topo.positions_w, topo.face_w, topo.ok)
    kept = ~already.copy()
    out = np.zeros(mesh.n_faces, dtype=bool)
    cover = {}
    for faces, n, origin in plane_groups(topo, 1.5 * float(topo.quanta.max())):
        e1, e2 = plane_basis(n)
        basis = np.stack([e1, e2], axis=1)
        polys = {int(f): shapely.Polygon((tri[f] - origin) @ basis) for f in faces}
        tree_ids = np.asarray(faces)
        tree = shapely.STRtree([polys[int(f)] for f in faces])
        for f in sorted((int(x) for x in faces), reverse=True):
            if not kept[f] or polys[f].area <= 0.0:
                continue
            near = [int(tree_ids[k]) for k in tree.query(polys[f], predicate="intersects")]
            others = [g for g in near if g != f and kept[g]
                      and mesh.face_material[g] == mesh.face_material[f]
                      and float(normal[g] @ normal[f]) > 0.0]
            if not others:
                continue
            frac = polys[f].intersection(shapely.union_all([polys[g] for g in others])).area / polys[f].area
            if frac >= COVERED_FRACTION:
                out[f] = True
                kept[f] = False
                cover[f] = round(frac, 4)
    return out, cover


def main(path, zjson, explain):
    with open(path, "rb") as fh:
        cap = pickle.load(fh)
    r, profile = cap["result"], cap["profile"]
    mesh, topo2, survivors, flat, topo = overlap_stage(cap)
    local_of = {int(g): k for k, g in enumerate(survivors.tolist())}
    depth_tol = guard_depth_tol(topo.quanta, profile)
    centre = (topo.positions_w.min(axis=0) + topo.positions_w.max(axis=0)) / 2.0
    positions_c = topo.positions_w - centre
    plan = plan_overlap_removal(mesh, topo2)

    # ---- item 2: why a named copy stays -------------------------------------------------------
    if explain:
        tri = topo2.positions_w[topo2.face_w]
        area = 0.5 * np.linalg.norm(np.cross(tri[:, 1] - tri[:, 0], tri[:, 2] - tri[:, 0]), axis=1)
        plabel, _planes = cluster_planes(tri, face_normals(topo2.positions_w, topo2.face_w, topo2.ok),
                                         area, mesh.face_material, topo2.ok, topo2.quanta)
        locals_ = [local_of[g] for g in explain]
        partners = sorted({j if i in locals_ else i for i, j, _a, s in plan.pairs_same
                           if (i in locals_ or j in locals_)})
        print(f"explain ref {explain} = stage faces {locals_}: regions "
              f"{[int(topo2.face_region[k]) for k in locals_]}, plane clusters "
              f"{[int(plabel[k]) for k in locals_]}, own region covers "
              f"{covered_fractions(topo2, locals_)}")
        print(f"  same-material overlap partners: {len(partners)} faces, regions "
              f"{sorted({int(topo2.face_region[k]) for k in partners})}, plane clusters "
              f"{sorted({int(plabel[k]) for k in partners})}, own region covers "
              f"{sorted(set(covered_fractions(topo2, partners).values()))}")
        mine, theirs = set(locals_), set(partners)
        shared = [e for e, group in enumerate(edge_face_lists(topo2.table))
                  if mine & set(int(f) for f in group) and theirs & set(int(f) for f in group)]
        print(f"  welded edges shared between them: {len(shared)}")

    # ---- item 2: the wider rule, measured --------------------------------------------------------
    wider, cover = wider_candidates(mesh, topo2, plan.remove)
    print(f"wider rule: {int(wider.sum())} faces proposed beyond the {int(plan.remove.sum())} the "
          f"pass proposes: ref {sorted(int(survivors[k]) for k in np.nonzero(wider)[0])}, area "
          f"{round(float(sum(0.5 * np.linalg.norm(np.cross(*(topo2.positions_w[topo2.face_w[k]][1:] - topo2.positions_w[topo2.face_w[k]][0]))) for k in np.nonzero(wider)[0])), 2)} sq in")
    if wider.any():
        removed, history = guard_feedback(plan.remove | wider, positions_c, topo2.face_w,
                                          mesh.face_material, flat, depth_tol, strict=True,
                                          size=profile.guard_size,
                                          crack_closed_cap=profile.crack_closed_cap)
        confirmed = np.asarray(removed, dtype=bool) & wider
        print(f"  strict guard confirms {int(confirmed.sum())} of them, puts back "
              f"{int((wider & ~np.asarray(removed, dtype=bool)).sum())}; the pass's own "
              f"{int(plan.remove.sum())} still confirmed: "
              f"{bool((np.asarray(removed, dtype=bool) & plan.remove).sum() == plan.remove.sum())}; "
              f"rounds {[h.get('failing_pixels') for h in history]}")
        for k in np.nonzero(wider)[0]:
            c = topo2.positions_w[topo2.face_w[k]].mean(axis=0)
            print(f"    ref {int(survivors[k])} (input "
                  f"{int(np.nonzero(~r.replaced_input)[0][survivors[k]])}), covered {cover[int(k)]}, "
                  f"at {np.round(c, 2).tolist()}, confirmed {bool(removed[k])}")

    # ---- item 3: every source in the export ---------------------------------------------------
    data = json.load(open(zjson, encoding="utf-8"))
    inp = cap["input"]
    tri_in = np.asarray(inp.positions, dtype=np.float64)[inp.face_v]
    n_in = np.cross(tri_in[:, 1] - tri_in[:, 0], tri_in[:, 2] - tri_in[:, 0])
    print(f"{data['name']}: the export's own view of each source")
    for e in data["sources"]:
        ins = [[s["input"] for s in side] for side in e["sources"]]
        if any(x is None for side in ins for x in side):
            origin = "solidify made one side"
        else:
            e1, e2 = plane_basis(np.asarray(e["normal"]))
            basis = np.stack([e1, e2], axis=1)
            o = tri_in[ins[0][0]][0]
            polys = [shapely.union_all([shapely.Polygon((tri_in[f] - o) @ basis) for f in side])
                     for side in ins]
            dots = [float(n_in[a] @ n_in[b]) for a in ins[0] for b in ins[1]]
            wind = ("opposite" if all(d < 0 for d in dots) else "same" if all(d > 0 for d in dots)
                    else "mixed")
            origin = (f"export: overlap {polys[0].intersection(polys[1]).area:.1f} sq in in the "
                      f"input, {wind}-wound there; OBJ lines "
                      f"{[[int(inp.face_line[f]) for f in side] for side in ins]}")
        flips = [[s["flipped"] for s in side] for side in e["sources"]]
        print(f"  {e['faces']} {'OPP' if e['opposite'] else 'same'} {e['area']} sq in at "
              f"{e['centroid']}: {origin}; flipped {flips}")


if __name__ == "__main__":
    main(sys.argv[1], sys.argv[2], [int(x) for x in sys.argv[3:]])
