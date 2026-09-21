"""How much geometry is visible ONLY through the open rim (seen from very few directions)?

exposure = escaping rays / rays tested, double-sided occlusion, 128 directions x 4 samples per face.
  0        hidden inside (already removable, guard-verified)
  0 - 5 %  seen only through a slit / open rim: the compartments in the user's screenshot
  >= 5 %   real outside surface
"""
import sys
from pathlib import Path

import numpy as np
from PIL import Image

from _common import FILES, OUT, SNAP, load_obj, save, tri_geometry, weld

here = Path(__file__).parent


def funcs(filename, stop):
    nsx = {"__file__": str(here / filename)}
    exec(compile((here / filename).read_text(encoding="utf-8").split(stop)[0], filename, "exec"), nsx)
    return nsx


V10 = funcs("10_ds_visibility.py", "\ndef run(name, images):")
V11 = funcs("11_guard_feedback.py", "\n# 26 views")
first_hit, N_DIRS, BARY = V11["first_hit"], V10["N_DIRS"], V10["BARY"]


def run(name, image):
    m = load_obj(SNAP / name)
    P, fw = weld(m)
    area, normals, _, deg = tri_geometry(P, fw)
    ok = ~deg
    Pc = P - (P.min(0) + P.max(0)) / 2
    esc = V10["escapes_double_sided"](Pc, fw, normals, ok)
    exposure = esc / float(N_DIRS * len(BARY))
    vis = ok & (esc > 0)
    bands = {"hidden_0": ok & (esc == 0), "slit_under_1pct": vis & (exposure < 0.01),
             "slit_1_to_5pct": vis & (exposure >= 0.01) & (exposure < 0.05),
             "outside_5pct_plus": vis & (exposure >= 0.05)}
    res = {"tris_nondegenerate": int(ok.sum())}
    for k, mask in bands.items():
        res[k] = {"tris": int(mask.sum()), "pct_tris": round(100 * mask.sum() / ok.sum(), 2),
                  "pct_area": round(100 * area[mask].sum() / area[ok].sum(), 2)}
    slit = vis & (exposure < 0.05)
    res["slit_faces_touching_open_edge"] = None
    pairs = np.sort(np.stack([fw[:, [0, 1]], fw[:, [1, 2]], fw[:, [2, 0]]], axis=1), axis=2)
    flat = pairs[ok].reshape(-1, 2)
    uniq, inv, cnt = np.unique(flat, axis=0, return_inverse=True, return_counts=True)
    open_per_face = (cnt[inv.reshape(-1)] == 1).reshape(-1, 3).any(axis=1)
    ids_ok = np.nonzero(ok)[0]
    touches = np.zeros(len(fw), bool)
    touches[ids_ok] = open_per_face
    res["open_edges_total"] = int((cnt == 1).sum())
    res["slit_faces_touching_open_edge"] = int((slit & touches).sum())

    if image and slit.any():
        cen = Pc[fw].mean(axis=1)
        target = np.median(cen[slit], axis=0)
        near = slit & (np.linalg.norm(cen - target, axis=1) < 400)
        target = cen[near].mean(axis=0) if near.any() else target
        out_dir = np.array([target[0], target[1], 0.0])
        out_dir /= max(np.linalg.norm(out_dir), 1e-9)
        view = -out_dir + np.array([0, 0, -0.35])
        frame = Pc[np.unique(fw[ok & (np.linalg.norm(cen - target, axis=1) < 260)])]
        depth, tid = first_hit(Pc, fw[ids_ok], ids_ok, view, frame)
        W, H = V11["W"], V11["H"]
        img = np.full((H * W, 3), 255, np.uint8)
        hit = tid >= 0
        col = np.tile(np.array([205.0, 205.0, 210.0]), (len(fw), 1))
        col[bands["slit_1_to_5pct"]] = (255, 160, 40)
        col[bands["slit_under_1pct"]] = (225, 40, 40)
        light = np.array([0.35, -0.45, 0.82])
        light /= np.linalg.norm(light)
        shade = 0.5 + 0.5 * np.abs(normals[tid[hit]] @ light)
        img[hit] = np.clip(col[tid[hit]] * shade[:, None], 0, 255).astype(np.uint8)
        Image.fromarray(img.reshape(H, W, 3)).save(OUT / f"{name[:-4]}__rim_exposure.png")
    return res


out = {name: run(name, i == 0) for i, name in enumerate(FILES)}
save("rim_exposure", out)
for name, r in out.items():
    print("==", name)
    for k, v in r.items():
        print(f"  {k}: {v}")
