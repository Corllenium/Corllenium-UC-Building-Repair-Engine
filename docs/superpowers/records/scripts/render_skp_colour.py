"""Scratch: render a colour-coded .skp (P0-18 error export) WITHOUT the SketchUp GUI.

Walks every group of the file through the SketchUp C API, takes SketchUp's own triangulation of each face and
the colour of its front material, and paints them with a painter's algorithm (far first) from a top view and an
oblique view. Tags can be switched off with --hide (as the owner would in SketchUp).

Usage: render_skp_colour.py <file.skp> <out dir> [--hide tag ...] [--only-unit LABEL] [--only-member GROUP ...]
       [--size 2400x1400] [--prefix NAME]
"""
import argparse
from ctypes import byref
from pathlib import Path

import numpy as np
from PIL import Image, ImageDraw

from engine.campus.error_export import _bind
from engine.io.skp_writer import _face_triangles, _open, _read_material, _Ref, _refs, _string, load_api


def read_faces(path, hide=(), only_unit=None, only_member=None):
    api = load_api()
    _bind(api)
    tris, cols = [], []
    mats = {}
    with api.session(), _open(api, Path(path)) as model:
        def colour(face):
            m = _Ref()
            if api.raw("SUFaceGetFrontMaterial", face, byref(m)) != 0 or not m.ptr:
                return (128, 128, 128)
            if m.ptr not in mats:
                c = _read_material(api, m).color
                mats[m.ptr] = (128, 128, 128) if c is None else tuple(c[:3])
            return mats[m.ptr]

        def walk(ents, tag, unit, member):
            if tag not in hide and (only_unit is None or unit == only_unit) and (
                    only_member is None or member in only_member):
                for f in _refs(api, "SUEntitiesGetNumFaces", "SUEntitiesGetFaces", ents):
                    t = _face_triangles(api, f)
                    if len(t):
                        tris.append(t)
                        cols.extend([colour(f)] * len(t))
            for g in _refs(api, "SUEntitiesGetNumGroups", "SUEntitiesGetGroups", ents):
                name = _string(api, "SUGroupGetName", g)
                lay = _Ref()
                api.ok("SUDrawingElementGetLayer", api.raw("SUGroupToDrawingElement", g), byref(lay))
                lname = _string(api, "SULayerGetName", lay)
                sub = _Ref()
                api.ok("SUGroupGetEntities", g, byref(sub))
                u = name.split(" | ", 1)[1] if name.startswith("UNIT | ") else unit
                m = name.split(" | ", 1)[1] if name.startswith("MEMBER | ") else member
                walk(sub, tag if lname in ("Layer0", "Untagged") else lname, u, m)

        root = _Ref()
        api.ok("SUModelGetEntities", model, byref(root))
        walk(root, "untagged", None, None)
    return np.concatenate(tris) if tris else np.zeros((0, 3, 3)), np.array(cols, np.uint8)


def paint(tris, cols, view, size, bg=(245, 245, 245)):
    """view: 3x3 rotation; x right, y up on screen, z toward the viewer."""
    W, H = size
    p = tris.reshape(-1, 3) @ view.T
    lo, hi = p.min(axis=0), p.max(axis=0)
    scale = 0.96 * min(W / max(hi[0] - lo[0], 1e-9), H / max(hi[1] - lo[1], 1e-9))
    xy = np.empty((len(p), 2))
    xy[:, 0] = (p[:, 0] - lo[0]) * scale + 0.02 * W
    xy[:, 1] = H - ((p[:, 1] - lo[1]) * scale + 0.02 * H)
    xy = xy.reshape(-1, 3, 2)
    depth = p[:, 2].reshape(-1, 3).mean(axis=1)
    # simple shading from the face normal so slabs and walls read apart
    n = np.cross(tris[:, 1] - tris[:, 0], tris[:, 2] - tris[:, 0])
    n /= np.maximum(np.linalg.norm(n, axis=1), 1e-12)[:, None]
    light = 0.75 + 0.25 * np.abs(n @ (view.T @ np.array([0.3, 0.5, 0.8]) / np.linalg.norm([0.3, 0.5, 0.8])))
    shade = np.clip(cols * light[:, None], 0, 255).astype(np.uint8)
    img = Image.new("RGB", size, bg)
    d = ImageDraw.Draw(img)
    for i in np.argsort(depth):
        c = tuple(int(v) for v in shade[i])
        d.polygon([tuple(q) for q in xy[i]], fill=c, outline=c)
    return img


def rot(elev_deg, azim_deg):
    a, e = np.radians(azim_deg), np.radians(elev_deg)
    rz = np.array([[np.cos(a), -np.sin(a), 0], [np.sin(a), np.cos(a), 0], [0, 0, 1]])
    rx = np.array([[1, 0, 0], [0, np.cos(e), -np.sin(e)], [0, np.sin(e), np.cos(e)]])
    return rx @ rz


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("skp")
    ap.add_argument("out")
    ap.add_argument("--hide", nargs="*", default=[])
    ap.add_argument("--only-unit", default=None)
    ap.add_argument("--only-member", nargs="*", default=None)
    ap.add_argument("--size", default="2400x1400")
    ap.add_argument("--prefix", default="")
    a = ap.parse_args()
    size = tuple(int(v) for v in a.size.split("x"))
    tris, cols = read_faces(a.skp, set(a.hide), a.only_unit, set(a.only_member) if a.only_member else None)
    out = Path(a.out)
    out.mkdir(parents=True, exist_ok=True)
    stem = a.prefix or Path(a.skp).stem
    paint(tris, cols, np.eye(3), size).save(out / f"{stem}-top.png")
    paint(tris, cols, rot(-60, -30), size).save(out / f"{stem}-oblique.png")
    print(f"{a.skp}: {len(tris):,} triangles painted (hidden tags: {sorted(a.hide) or 'none'}) -> {out}")


if __name__ == "__main__":
    main()
