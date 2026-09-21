"""Does removing 'inside' mesh also remove facade? Compare two deletion rules, double-sided renders, 6 views.

  naive : delete every face whose FRONT cannot be seen from outside   (what simple interior tests do)
  safe  : delete only faces where NEITHER side can be seen from outside
Facade damage = pixels that showed the model before and show background after.
"""
from pathlib import Path

import numpy as np
from PIL import Image

from _common import FILES, OUT, SNAP, load_obj, save, tri_geometry, weld

here = Path(__file__).parent


def load_funcs(filename, stop):
    src = (here / filename).read_text(encoding="utf-8").split(stop)[0]
    ns = {"__file__": str(here / filename)}
    exec(compile(src, filename, "exec"), ns)
    return ns


S = load_funcs("07_three_classes.py", "\ndef run(name, render=True):")
render = S["RND"]["render"]
VIEWS = {"top_oblique": (0.45, 0.55, -0.70), "under_oblique": (0.45, 0.55, 0.70),
         "side_a": (1.0, 0.2, -0.15), "side_b": (-0.2, 1.0, -0.15),
         "side_c": (-1.0, -0.2, -0.15), "side_d": (0.2, -1.0, -0.15)}


def run(name, save_images):
    m = load_obj(SNAP / name)
    P, fw = weld(m)
    area, normals, _, deg = tri_geometry(P, fw)
    ok = ~deg
    Pc = P - (P.min(axis=0) + P.max(axis=0)) / 2
    front, back = S["both_side_counts"](Pc, fw, normals, ok)
    naive_del = ok & (front == 0)
    safe_del = ok & (front == 0) & (back == 0)
    grey = np.tile(np.array([200.0, 200.0, 205.0]), (len(fw), 1))
    res = {"naive_deletes_tris": int(naive_del.sum()), "safe_deletes_tris": int(safe_del.sum()),
           "facade_tris_saved_by_safe_rule": int((naive_del & ~safe_del).sum()), "views": {}}
    stem = name[:-4]
    for tag, view in VIEWS.items():
        imgs, masks = {}, {}
        for label, keep in (("original", ok), ("naive", ok & ~naive_del), ("safe", ok & ~safe_del)):
            imgs[label], masks[label] = render(Pc, fw[keep], normals[keep], grey[keep], view, cull=False)
        lost_naive = masks["original"] & ~masks["naive"]
        lost_safe = masks["original"] & ~masks["safe"]
        res["views"][tag] = {"model_pixels": int(masks["original"].sum()),
                             "facade_pixels_lost_naive": int(lost_naive.sum()),
                             "facade_pixels_lost_safe": int(lost_safe.sum())}
        if save_images and tag == "top_oblique":
            for label in ("naive", "safe"):
                out = imgs[label].copy()
                out[lost_naive if label == "naive" else lost_safe] = (230, 30, 30)
                Image.fromarray(out).save(OUT / f"{stem}__facade_{label}_lost_pixels_in_red.png")
    return res


out = {name: run(name, i == 0) for i, name in enumerate(FILES)}
save("facade_proof", out)
for name, r in out.items():
    print("==", name)
    print("  naive deletes:", r["naive_deletes_tris"], "| safe deletes:", r["safe_deletes_tris"],
          "| facade tris saved:", r["facade_tris_saved_by_safe_rule"])
    for tag, v in r["views"].items():
        print(f"  {tag:14s} model px {v['model_pixels']:7d} | lost naive {v['facade_pixels_lost_naive']:6d}"
              f" | lost safe {v['facade_pixels_lost_safe']:4d}")
