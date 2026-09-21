"""Guard feedback: remove double-sided-hidden faces, then put back any face whose removal changes a pixel.

Run as-is on 2026-09-21: A 1853 -> 1819 (34 put back), B 2411 -> 2381 (30 put back), 0 damaged px over 26 views.
"""
import itertools
from pathlib import Path

import numpy as np
import trimesh
from PIL import Image
from trimesh.ray.ray_pyembree import RayMeshIntersector

from _common import FILES, OUT, SNAP, load_obj, save, tri_geometry, weld

here = Path(__file__).parent
ns = {"__file__": str(here / "10_ds_visibility.py")}
exec(compile((here / "10_ds_visibility.py").read_text(encoding="utf-8").split("\ndef run(name, images):")[0],
             "10", "exec"), ns)
W, H, TOL = ns["W"], ns["H"], ns["TOL"]


def first_hit(Pc, faces, ids, view, frame):
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
    diag = np.linalg.norm(frame.max(0) - frame.min(0))
    o = (gx[..., None] * right + gy[..., None] * up - d * diag * 2).reshape(-1, 3)
    rmi = RayMeshIntersector(trimesh.Trimesh(vertices=Pc.astype(np.float32), faces=faces, process=False))
    loc, iray, itri = rmi.intersects_location(o, np.tile(d, (len(o), 1)), multiple_hits=False)
    depth = np.full(W * H, np.inf)
    tid = np.full(W * H, -1)
    depth[iray] = (loc - o[iray]) @ d
    tid[iray] = ids[itri]
    return depth, tid


# 26 views, nudged off-axis so no view is exactly edge-on to axis-aligned faces
VIEWS = [tuple(np.array(v, float) + np.array([0.013, 0.007, 0.011]))
         for v in itertools.product((-1, 0, 1), repeat=3) if any(v)]

out = {}
for name in FILES:
    m = load_obj(SNAP / name)
    P, fw = weld(m)
    area, normals, _, deg = tri_geometry(P, fw)
    ok = ~deg
    Pc = P - (P.min(0) + P.max(0)) / 2
    hidden = ok & (ns["escapes_double_sided"](Pc, fw, normals, ok) == 0)
    start = int(hidden.sum())
    ids_ok = np.nonzero(ok)[0]
    before = [first_hit(Pc, fw[ids_ok], ids_ok, v, Pc) for v in VIEWS]
    history = []
    for rnd in range(8):
        keep = np.nonzero(ok & ~hidden)[0]
        dmg_total, restore = 0, set()
        for (bd, bt), v in zip(before, VIEWS):
            ad, _ = first_hit(Pc, fw[keep], keep, v, Pc)
            fb, fa = np.isfinite(bd), np.isfinite(ad)
            with np.errstate(invalid="ignore"):
                dmg = (fb & ~fa) | (fb & fa & (np.abs(bd - ad) > TOL))
            dmg_total += int(dmg.sum())
            t = bt[dmg]
            restore.update(t[hidden[t]].tolist())
        history.append({"round": rnd, "hidden": int(hidden.sum()), "damaged_px_26_views": dmg_total,
                        "restored": len(restore)})
        if dmg_total == 0 or not restore:
            break
        hidden[list(restore)] = False
    out[name] = {"hidden_by_sampling": start, "hidden_after_guard_feedback": int(hidden.sum()),
                 "faces_put_back": start - int(hidden.sum()),
                 "final_hidden_pct_tris": round(100 * hidden.sum() / ok.sum(), 2),
                 "final_hidden_pct_area": round(100 * area[hidden].sum() / area[ok].sum(), 2),
                 "history": history}
    if name == FILES[0]:
        v = (0.45, 0.55, -0.70)
        bd, _ = first_hit(Pc, fw[ids_ok], ids_ok, v, Pc)
        hid = np.nonzero(hidden)[0]
        xd, _ = first_hit(Pc, fw[hid], hid, v, Pc)
        img = np.full((H * W, 3), 255, np.uint8)
        img[np.isfinite(bd)] = (225, 225, 229)
        img[np.isfinite(xd)] = (220, 40, 40)
        Image.fromarray(img.reshape(H, W, 3)).save(OUT / "A__xray_final_hidden_red.png")

save("guard_feedback", out)
for k, v in out.items():
    print("==", k)
    for kk, vv in v.items():
        print("  ", kk, ":", vv)
