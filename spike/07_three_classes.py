"""Split 'front never visible' into REVERSED (back is exposed -> flip) and INTERIOR (nothing exposed -> delete).

Unity culling: only triangles whose front faces the viewer render or occlude.
For viewer direction w (rays travel along w, away from the surface):
  blockers        = triangles with n.w > 0
  front test of f = ray from f's front side, needs n_f.w > 0
  back  test of f = ray from f's back  side, needs n_f.w < 0
"""
import importlib.util
import sys
from pathlib import Path

import numpy as np
import trimesh
from PIL import Image
from trimesh.ray.ray_pyembree import RayMeshIntersector

from _common import FILES, OUT, SNAP, load_obj, save, tri_geometry, weld

here = Path(__file__).parent


def load_funcs(filename, stop):
    src = (here / filename).read_text(encoding="utf-8").split(stop)[0]
    ns = {"__file__": str(here / filename)}
    exec(compile(src, filename, "exec"), ns)
    return ns


V = load_funcs("05_visibility_then_merge.py", "\nout = {name: run(name)")
RND = load_funcs("06_render_classes.py", "\ndef main(name):")
R = V["R"]
N_DIRS, EPS, BARY = V["N_DIRS"], V["EPS"], V["BARY"]


def both_side_counts(Pc, fw, normals, ok):
    tri = Pc[fw]
    front = np.zeros(len(fw), np.int64)
    back = np.zeros(len(fw), np.int64)
    P32 = Pc.astype(np.float32)
    for w in V["fib_dirs"](N_DIRS):
        dot = normals @ w
        blockers = np.nonzero(ok & (dot > 1e-6))[0]
        if len(blockers) == 0:
            continue
        rmi = RayMeshIntersector(trimesh.Trimesh(vertices=P32, faces=fw[blockers], process=False))
        for ids, sign, acc in ((blockers, 1.0, front), (np.nonzero(ok & (dot < -1e-6))[0], -1.0, back)):
            if len(ids) == 0:
                continue
            pts = np.einsum("sb,fbk->fsk", BARY, tri[ids]) + sign * EPS * normals[ids][:, None, :]
            o = pts.reshape(-1, 3)
            hit = rmi.intersects_any(o, np.tile(w, (len(o), 1)))
            acc[ids] += (~hit).reshape(len(ids), len(BARY)).sum(axis=1)
    return front, back


def run(name, render=True):
    path = SNAP / name
    m = load_obj(path)
    P, fw = weld(m)
    area, normals, _, degenerate = tri_geometry(P, fw)
    ok = ~degenerate
    _, quanta = R.axis_quanta(path, P)
    Pc = P - (P.min(axis=0) + P.max(axis=0)) / 2
    front, back = both_side_counts(Pc, fw, normals, ok)

    visible = ok & (front > 0)
    reversed_ = ok & (front == 0) & (back > 0)
    interior = ok & (front == 0) & (back == 0)
    two_sided = ok & (front > 0) & (back > 0)

    # after the orientation fix: flip reversed faces, drop interior ones, then merge
    fw2, n2 = fw.copy(), normals.copy()
    fw2[reversed_] = fw2[reversed_][:, ::-1]
    n2[reversed_] *= -1
    keep = visible | reversed_
    tri = P[fw2]
    after, planes, rings = V["merge_floor"](tri, fw2, n2, area, m["fm"], keep, quanta)
    n_ok = int(ok.sum())
    res = {
        "tris_nondegenerate": n_ok,
        "front_visible": int(visible.sum()),
        "of_which_both_sides_exposed": int(two_sided.sum()),
        "reversed_back_only_visible": int(reversed_.sum()),
        "reversed_area_pct": round(100 * area[reversed_].sum() / area[ok].sum(), 2),
        "interior_never_visible": int(interior.sum()),
        "interior_area_pct": round(100 * area[interior].sum() / area[ok].sum(), 2),
        "pipeline_flip_delete_merge": {"tris_after": after, "planes": planes, "rings": rings,
                                       "reduction_vs_nondegenerate_pct": round(100 * (1 - after / n_ok), 2),
                                       "reduction_vs_total_pct": round(100 * (1 - after / len(fw)), 2)},
    }
    if render:
        stem = name[:-4]
        for tag, view in (("top", (0.45, 0.55, -0.70)), ("under", (0.45, 0.55, 0.70))):
            col = np.tile(np.array([200.0, 200.0, 205.0]), (len(fw), 1))
            before, _ = RND["render"](Pc, fw[ok], normals[ok], col[ok], view, cull=True)
            Image.fromarray(before).save(OUT / f"{stem}__{tag}_1_unity_before.png")
            col[reversed_] = (40, 110, 255)
            fixed, _ = RND["render"](Pc, fw2[keep], n2[keep], col[keep], view, cull=True)
            Image.fromarray(fixed).save(OUT / f"{stem}__{tag}_2_after_flip_reversed_in_blue.png")
    return res


idx = [int(a) for a in sys.argv[1:]] or [0, 1]
out = {FILES[i]: run(FILES[i]) for i in idx}
save("three_classes", out)
for name, r in out.items():
    print("==", name)
    for k, v in r.items():
        print(f"  {k}: {v}")
