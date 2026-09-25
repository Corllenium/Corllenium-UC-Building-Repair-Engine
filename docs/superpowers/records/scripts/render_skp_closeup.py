"""Scratch: a CLOSE-UP of one box of a written .skp, drawn the way `render_skp.py` draws the whole
model (SketchUp's own triangulation read back through the C API, shaded double-sided, every edge
SketchUp shows) -- and a second time coloured the way SketchUp colours a face's two sides: the
front grey, the BACK purple. A back face seen from outside is the purple patch the owner looks
for in SketchUp; the double-sided picture cannot show one.

The rest of the model is still cast against, so whatever stands in front of the box is drawn in
front of it. Each picture is framed on the part of the model inside the box.

Usage: render_skp_closeup.py <file.skp> <out dir> <xmin> <xmax> <ymin> <ymax> <zmin> <zmax>
Writes <view>.png and <view>_sides.png for each view below, and prints per view how many pixels
show a front and how many a back."""
import sys
from pathlib import Path

import numpy as np
from PIL import Image

from engine.guard.qa_render import _EDGE_RGB, _camera, _render
from engine.io.skp_writer import read_skp
from engine.rays.caster import EmbreeCaster

#: View DIRECTIONS (the way the camera looks), as in `engine.guard.qa_render`.
VIEWS = {"top": (0.01, 0.01, -1.0), "bottom": (0.01, 0.01, 1.0),
         "obl_top_a": (0.45, 0.55, -0.70), "obl_top_b": (-0.6, 0.4, -0.6),
         "obl_bot_a": (0.45, 0.55, 0.70), "side_px": (-1.0, 0.01, -0.15),
         "side_nx": (1.0, 0.01, -0.15)}
SIZE = (1600, 1000)
_FRONT = np.array([205.0, 205.0, 210.0])
_BACK = np.array([150.0, 110.0, 205.0])      # purple, as SketchUp shows a back face
_LIGHT = np.array([0.35, -0.45, 0.82]) / np.linalg.norm([0.35, -0.45, 0.82])


def main(skp: str, out_dir: str, box: list[float]) -> None:
    model = read_skp(skp, uvs=False, triangles=True)
    tris, normals = [], []
    for face in model.faces:
        if not len(face.triangles):
            continue
        t = np.asarray(face.triangles, dtype=np.float64)
        cross = np.cross(t[:, 1] - t[:, 0], t[:, 2] - t[:, 0])
        # SketchUp's triangles, wound like the face they belong to
        t = np.where(((cross @ face.normal) < 0.0)[:, None, None], t[:, [0, 2, 1]], t)
        tris.append(t)
        normals.append(np.repeat(np.asarray(face.normal, dtype=np.float64)[None], len(t), axis=0))
    tris = np.concatenate(tris)
    normals = np.concatenate(normals)
    visible = [(e.start, e.end) for e in model.edges if not (e.soft or e.smooth)]
    pts = np.concatenate([tris.reshape(-1, 3), np.array(visible).reshape(-1, 3)])
    uniq, inverse = np.unique(pts, axis=0, return_inverse=True)
    inverse = inverse.reshape(-1)
    face_v = inverse[:len(tris) * 3].reshape(-1, 3)
    edges = inverse[len(tris) * 3:].reshape(-1, 2)

    lo, hi = np.array(box[0::2]), np.array(box[1::2])
    inside = ((uniq >= lo) & (uniq <= hi)).all(axis=1)
    if int(inside.sum()) < 3:
        raise SystemExit(f"fewer than 3 vertices inside {box}")
    centre = (uniq[inside].min(axis=0) + uniq[inside].max(axis=0)) / 2.0
    positions_c = uniq - centre
    frame = positions_c[inside]
    diag = float(np.linalg.norm(positions_c.max(axis=0) - positions_c.min(axis=0))) or 1.0
    caster = EmbreeCaster(positions_c, face_v)
    shade_normals = normals          # per triangle, like `write_qa_sheet`'s

    out = Path(out_dir)
    out.mkdir(parents=True, exist_ok=True)
    width, height = SIZE
    for name, view in VIEWS.items():
        image = _render(caster, positions_c, shade_normals, edges, view, frame, SIZE, diag)
        image.save(out / f"{name}.png")
        # the same camera, cast again, to tell front from back
        d, right, up, cx, cy, pixel = _camera(view, frame, SIZE)
        standoff = -d * diag * 2.0
        xs = cx + (np.arange(width) - width / 2.0 + 0.5) * pixel
        ys = cy - (np.arange(height) - height / 2.0 + 0.5) * pixel
        gx, gy = np.meshgrid(xs, ys)
        origins = (gx[..., None] * right + gy[..., None] * up + standoff).reshape(-1, 3)
        tri, _t = caster.first_hit(origins, np.tile(d, (len(origins), 1)))
        hit = tri >= 0
        back = np.zeros(len(tri), dtype=bool)
        back[hit] = (normals[tri[hit]] @ d) > 0.0
        img = np.asarray(image).reshape(-1, 3).copy()
        edge = (img == _EDGE_RGB).all(axis=1)
        shade = 0.55 + 0.45 * np.abs(normals[tri[hit]] @ _LIGHT)
        colour = np.where(back[hit][:, None], _BACK, _FRONT) * shade[:, None]
        paint = np.zeros(len(tri), dtype=bool)
        paint[hit] = True
        paint &= ~edge
        img[paint] = np.clip(colour[paint[hit]], 0, 255).astype(np.uint8)
        Image.fromarray(img.reshape(height, width, 3)).save(out / f"{name}_sides.png")
        print(f"{name}: {int((hit & ~back).sum())} front px, {int(back.sum())} BACK px")
    print(f"{skp}: {len(model.faces)} faces, {len(tris)} SketchUp triangles, {len(visible)} "
          f"visible edges; close-up of {box} written to {out_dir}")


if __name__ == "__main__":
    main(sys.argv[1], sys.argv[2], [float(v) for v in sys.argv[3:9]])
