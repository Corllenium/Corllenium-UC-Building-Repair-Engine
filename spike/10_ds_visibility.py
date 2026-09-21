"""Visibility the way SketchUp and the Unity project actually draw: DOUBLE-SIDED. Every face renders and blocks.

hidden_ds : no ray from either side of the face escapes, with ALL faces as blockers.
Guard     : depth-aware. A pixel is damaged when it turns into background OR its first-hit depth moves > TOL.
"""
from pathlib import Path

import numpy as np
import trimesh
from PIL import Image
from trimesh.ray.ray_pyembree import RayMeshIntersector

from _common import FILES, OUT, SNAP, load_obj, save, tri_geometry, weld

here = Path(__file__).parent
ns = {"__file__": str(here / "05_visibility_then_merge.py")}
exec(compile((here / "05_visibility_then_merge.py").read_text(encoding="utf-8").split("\nout = {name: run(name)")[0],
             "05", "exec"), ns)
fib_dirs, BARY, EPS = ns["fib_dirs"], ns["BARY"], ns["EPS"]
N_DIRS, TOL, W, H = 128, 0.15, 900, 600
VIEWS = {"top_oblique": (0.45, 0.55, -0.70), "under_oblique": (0.45, 0.55, 0.70), "down": (0.001, 0.001, -1.0),
         "up": (0.001, 0.001, 1.0), "side_a": (1.0, 0.2, -0.15), "side_b": (-0.2, 1.0, -0.15),
         "side_c": (-1.0, -0.2, -0.15), "side_d": (0.2, -1.0, -0.15)}


def escapes_double_sided(Pc, fw, normals, ok):
    ids_ok = np.nonzero(ok)[0]
    rmi = RayMeshIntersector(trimesh.Trimesh(vertices=Pc.astype(np.float32), faces=fw[ids_ok], process=False))
    tri = Pc[fw]
    esc = np.zeros(len(fw), np.int64)
    for w in fib_dirs(N_DIRS):
        dot = normals @ w
        for ids, sign in ((np.nonzero(ok & (dot > 1e-6))[0], 1.0), (np.nonzero(ok & (dot < -1e-6))[0], -1.0)):
            if len(ids) == 0:
                continue
            pts = np.einsum("sb,fbk->fsk", BARY, tri[ids]) + sign * EPS * normals[ids][:, None, :]
            o = pts.reshape(-1, 3)
            hit = rmi.intersects_any(o, np.tile(w, (len(o), 1)))
            esc[ids] += (~hit).reshape(len(ids), len(BARY)).sum(axis=1)
    return esc


def depth_image(Pc, faces, view, frame):
    d = np.asarray(view, float)
    d /= np.linalg.norm(d)
    up_hint = (0, 1, 0) if abs(d[2]) > 0.99 else (0, 0, 1)
    right = np.cross(d, up_hint)
    right /= np.linalg.norm(right)
    up = np.cross(right, d)
    er, eu = frame @ right, frame @ up
    half = max((er.max() - er.min()) / W, (eu.max() - eu.min()) / H) * 0.52
    xs = (er.max() + er.min()) / 2 + (np.arange(W) - W / 2 + 0.5) * half * 2
    ys = (eu.max() + eu.min()) / 2 - (np.arange(H) - H / 2 + 0.5) * half * 2
    gx, gy = np.meshgrid(xs, ys)
    diag = np.linalg.norm(frame.max(axis=0) - frame.min(axis=0))
    o = (gx[..., None] * right + gy[..., None] * up - d * diag * 2).reshape(-1, 3)
    rmi = RayMeshIntersector(trimesh.Trimesh(vertices=Pc.astype(np.float32), faces=faces, process=False))
    loc, iray, itri = rmi.intersects_location(o, np.tile(d, (len(o), 1)), multiple_hits=False)
    depth = np.full(W * H, np.inf)
    depth[iray] = (loc - o[iray]) @ d
    return depth.reshape(H, W)


def damage(before, after):
    lost = np.isfinite(before) & ~np.isfinite(after)
    moved = np.isfinite(before) & np.isfinite(after) & (np.abs(before - after) > TOL)
    return lost | moved


def run(name, images):
    m = load_obj(SNAP / name)
    P, fw = weld(m)
    area, normals, _, deg = tri_geometry(P, fw)
    ok = ~deg
    Pc = P - (P.min(axis=0) + P.max(axis=0)) / 2
    esc = escapes_double_sided(Pc, fw, normals, ok)
    hidden = ok & (esc == 0)
    barely = ok & (esc > 0) & (esc <= 2)
    res = {"tris_nondegenerate": int(ok.sum()),
           "hidden_double_sided_tris": int(hidden.sum()),
           "hidden_pct_of_tris": round(100 * hidden.sum() / ok.sum(), 2),
           "hidden_pct_of_area": round(100 * area[hidden].sum() / area[ok].sum(), 2),
           "barely_visible_1_or_2_rays_KEPT": int(barely.sum()),
           "rays_cast": int(N_DIRS * len(BARY) * ok.sum()), "views": {}}
    total = 0
    for tag, view in VIEWS.items():
        b = depth_image(Pc, fw[ok], view, Pc)
        a = depth_image(Pc, fw[ok & ~hidden], view, Pc)
        dmg = damage(b, a)
        res["views"][tag] = {"model_pixels": int(np.isfinite(b).sum()), "damaged_pixels": int(dmg.sum())}
        total += int(dmg.sum())
        if images and tag == "top_oblique":
            ghost = np.full((H, W, 3), 255, np.uint8)
            ghost[np.isfinite(b)] = (222, 222, 226)
            x = depth_image(Pc, fw[hidden], view, Pc)
            ghost[np.isfinite(x)] = (220, 40, 40)
            Image.fromarray(ghost).save(OUT / f"{name[:-4]}__xray_hidden_faces_red.png")
    res["damaged_pixels_all_views"] = total
    return res


out = {name: run(name, True) for name in FILES}
save("ds_visibility", out)
for name, r in out.items():
    print("==", name)
    for k, v in r.items():
        if k == "views":
            for tag, vv in v.items():
                print(f"    {tag:14s} model px {vv['model_pixels']:7d} | damaged {vv['damaged_pixels']}")
        else:
            print(f"  {k}: {v}")
