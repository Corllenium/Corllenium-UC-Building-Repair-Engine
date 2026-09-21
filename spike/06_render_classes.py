"""LOOK AT IT. Ray-cast renders (no GPU) of visibility classes, Unity-style backface culling.

  *_exterior.png  what Unity would show. grey = front-visible, orange = barely visible (1-2 rays)
  *_xray.png      ONLY the never-visible faces (red), same camera, ghost outline of the rest
"""
import importlib.util
import sys
from pathlib import Path

import numpy as np
import trimesh
from PIL import Image
from trimesh.ray.ray_pyembree import RayMeshIntersector

from _common import FILES, OUT, SNAP, load_obj, tri_geometry, weld

spec = importlib.util.spec_from_file_location("v", Path(__file__).with_name("05_visibility_then_merge.py"))
W, H = 1200, 800


def camera(view_dir, up_hint=(0, 0, 1)):
    d = np.asarray(view_dir, float)
    d /= np.linalg.norm(d)
    right = np.cross(d, up_hint)
    right /= np.linalg.norm(right)
    return d, right, np.cross(right, d)


def render(Pc, faces, normals, colours, view_dir, cull=True, bg=(255, 255, 255)):
    d, right, up = camera(view_dir)
    keep = (normals @ d < -1e-6) if cull else np.ones(len(faces), bool)
    ids = np.nonzero(keep)[0]
    img = np.full((H, W, 3), bg, np.uint8)
    if len(ids) == 0:
        return img, None
    ext_r = Pc @ right
    ext_u = Pc @ up
    half = max((ext_r.max() - ext_r.min()) / W, (ext_u.max() - ext_u.min()) / H) * 0.52
    cx, cy = (ext_r.max() + ext_r.min()) / 2, (ext_u.max() + ext_u.min()) / 2
    xs = cx + (np.arange(W) - W / 2 + 0.5) * half * 2
    ys = cy - (np.arange(H) - H / 2 + 0.5) * half * 2
    gx, gy = np.meshgrid(xs, ys)
    diag = np.linalg.norm(Pc.max(axis=0) - Pc.min(axis=0))
    o = gx[..., None] * right + gy[..., None] * up - d * diag * 2
    o = o.reshape(-1, 3)
    rmi = RayMeshIntersector(trimesh.Trimesh(vertices=Pc.astype(np.float32), faces=faces[ids], process=False))
    tri = rmi.intersects_first(o, np.tile(d, (len(o), 1)))
    hit = tri >= 0
    f = ids[tri[hit]]
    light = np.array([0.35, -0.45, 0.82])
    light /= np.linalg.norm(light)
    shade = 0.45 + 0.55 * np.abs(normals[f] @ light)
    flat = img.reshape(-1, 3)
    flat[hit] = np.clip(colours[f] * shade[:, None], 0, 255).astype(np.uint8)
    return img, hit.reshape(H, W)


def main(name):
    mod = importlib.util.module_from_spec(spec)
    # reuse the visibility function without re-running that script's top-level work
    src = Path(spec.origin).read_text(encoding="utf-8").split("\nout = {name: run(name)")[0]
    exec(compile(src, spec.origin, "exec"), mod.__dict__)

    m = load_obj(SNAP / name)
    P, fw = weld(m)
    area, normals, _, degenerate = tri_geometry(P, fw)
    ok = ~degenerate
    Pc = P - (P.min(axis=0) + P.max(axis=0)) / 2
    escapes = mod.front_visible_counts(Pc, fw, normals, ok)

    colours = np.tile(np.array([200.0, 200.0, 205.0]), (len(fw), 1))
    colours[ok & (escapes > 0) & (escapes <= 2)] = (255, 150, 30)
    never = ok & (escapes == 0)
    stem = name[:-4]
    for tag, view in (("top", (0.45, 0.55, -0.70)), ("under", (0.45, 0.55, 0.70))):
        ext, _ = render(Pc, fw[ok], normals[ok], colours[ok], view, cull=True)
        Image.fromarray(ext).save(OUT / f"{stem}__{tag}_exterior.png")
        ghost, mask = render(Pc, fw[ok], normals[ok], np.full((int(ok.sum()), 3), 225.0), view, cull=True,
                             bg=(255, 255, 255))
        red = np.tile(np.array([220.0, 30.0, 30.0]), (int(never.sum()), 1))
        xr, hit = render(Pc, fw[never], normals[never], red, view, cull=False)
        out = ghost.copy()
        if hit is not None:
            out[hit] = (0.35 * ghost[hit] + 0.65 * xr[hit]).astype(np.uint8)
        Image.fromarray(out).save(OUT / f"{stem}__{tag}_xray.png")
    print(name, "never:", int(never.sum()), "images written to", OUT)


main(FILES[int(sys.argv[1])] if len(sys.argv) > 1 else FILES[0])
