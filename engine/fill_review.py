"""The floor review's picture of each kept flat fill (job P2-E8b, ruling E8b-R8): BEFORE | AFTER, side by side.

AGENTS.md section 4 lets the narrow flat fill close a hole only if each fill is shown in the floor review. For each
kept fill, `write_fill_crop` draws the unit's BEFORE and the shipped AFTER from one viewpoint that sees THROUGH the
hole: orthographic, looking straight at the hole's plane from the side its neighbours face, so BEFORE shows what lay
behind the hole and AFTER shows the fill in its neighbours' look. The two halves are the Validator's evidence crops
(`engine.validate.evidence.render_crop`: each face its look's colour, a back face mixed with purple, misses pale), with
the hole's loop outlined in yellow on both, and a 4 px white gap between them.

The needs-modelling queue (job P2-E8c) reuses the camera and the drawing for a single BEFORE picture of each spot
(`write_spot_crop`): orthographic, standing at the entry's `suggested_view` and looking at its target, the spot's
border outlined in yellow (a loop as a line, an unordered set of open-edge points as crosses).

This module sits outside both packages, like `engine.site_judge`: the repair package never imports the Validator.
"""
from __future__ import annotations

from pathlib import Path

import numpy as np
from PIL import Image, ImageDraw

from engine.model import MeshData
from engine.validate.checks import LookTable, Looks, face_look_ids
from engine.validate.evidence import PX, _basis, render_crop
from engine.validate.sampling import face_normals, recentred
from engine.validate.visibility import build_caster

#: The crop's window is this many times the loop's extent across, within [MIN_WINDOW, MAX_WINDOW] inches.
WINDOW_SCALE = 3.0
MIN_WINDOW = 36.0
MAX_WINDOW = 400.0
#: The camera stands at most this far (in) off the hole's plane, and short of anything above the hole.
MAX_STANDOFF = 240.0
GAP = 4
OUTLINE = (255, 220, 0)


def _half(mesh: MeshData, looks: Looks, table: LookTable, origin, u, right, up, window, px):
    caster = build_caster(mesh) if mesh.n_faces else None
    ids = face_look_ids(mesh, looks, table)                  # fills the table first
    per_look = np.array([looks.colour_of(k) for k in table.keys], dtype=np.float64).reshape(-1, 3)
    colours = per_look[ids] if mesh.n_faces else np.zeros((0, 3))
    return render_crop(caster, face_normals(mesh), colours, origin, u, right, up, window, px)


def write_fill_crop(before: MeshData, after: MeshData, loop: np.ndarray, normal, looks: Looks, path,
                    px: int = PX) -> Path:
    """Write the BEFORE | AFTER crop of one fill to `path` (PNG, `2 px + GAP` wide, `px` high). `loop`: the hole's
    border points in the model's own coordinates; `normal`: the fill's normal (the side its neighbours face)."""
    b, centre = recentred(before)
    a, _ = recentred(after, centre)
    loop = np.asarray(loop, dtype=np.float64).reshape(-1, 3) - centre
    n = np.asarray(normal, dtype=np.float64)
    n = n / np.linalg.norm(n)
    middle = loop.mean(axis=0)
    # stand off the plane on the neighbours' side, short of the first thing above the hole in BEFORE
    standoff = MAX_STANDOFF
    if b.n_faces:
        tri, t = build_caster(b).first_hit((middle + 0.5 * n)[None], n[None])
        if tri[0] >= 0:
            standoff = float(np.clip(0.9 * (float(t[0]) + 0.5), 1.0, MAX_STANDOFF))
    u = -n
    right, up = _basis(u)
    extent = float(np.ptp(loop, axis=0).max())
    window = float(np.clip(WINDOW_SCALE * extent, MIN_WINDOW, MAX_WINDOW))
    origin = middle + standoff * n
    table = LookTable()
    halves = [_half(m, looks, table, origin, u, right, up, window, px) for m in (b, a)]
    # the loop outline, in pixel coordinates of both halves
    rel = loop - origin
    xs = ((rel @ right) / window + 0.5) * px
    ys = (0.5 - (rel @ up) / window) * px
    canvas = Image.new("RGB", (2 * px + GAP, px), (255, 255, 255))
    for k, half in enumerate(halves):
        image = Image.fromarray(half, "RGB")
        ring = [(int(round(x)), int(round(y))) for x, y in zip(xs.tolist(), ys.tolist())]
        ImageDraw.Draw(image).line(ring + ring[:1], fill=OUTLINE, width=2)
        canvas.paste(image, (k * (px + GAP), 0))
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    canvas.save(path)
    return path


#: The half size, in px, of the cross drawn on each point of an unordered border.
_CROSS = 3


class SpotCropper:
    """Draws the BEFORE picture of each needs-modelling spot of one unit: the recentred BEFORE, its ray caster and its
    face colours are made once, so a floor with hundreds of spots builds them once. `write` draws one spot."""

    def __init__(self, before: MeshData, looks: Looks, px: int = PX):
        self.px = px
        self.mesh, self.centre = recentred(before)
        self.caster = build_caster(self.mesh) if self.mesh.n_faces else None
        table = LookTable()
        ids = face_look_ids(self.mesh, looks, table)                 # fills the table first
        per_look = np.array([looks.colour_of(k) for k in table.keys], dtype=np.float64).reshape(-1, 3)
        self.colours = per_look[ids] if self.mesh.n_faces else np.zeros((0, 3))
        self.normals = face_normals(self.mesh)

    def write(self, border, ordered: bool, view: dict, path) -> Path:
        """Write one spot to `path` (PNG, `px` x `px`). `border`: its points in the model's own coordinates;
        `ordered`: they run round a loop; `view`: its `suggested_view` (`eye`, `target`). The camera is
        orthographic: parallel rays from the plane through `eye`, along the line to `target`, so the picture is what a
        viewer standing at `eye` looks at. The window is `WINDOW_SCALE` times the border's extent, within
        [MIN_WINDOW, MAX_WINDOW] inches."""
        px = self.px
        pts = np.asarray(border, dtype=np.float64).reshape(-1, 3) - self.centre
        eye = np.asarray(view["eye"], dtype=np.float64) - self.centre
        target = np.asarray(view["target"], dtype=np.float64) - self.centre
        u = target - eye
        u = u / np.linalg.norm(u)
        right, up = _basis(u)
        window = float(np.clip(WINDOW_SCALE * float(np.ptp(pts, axis=0).max()), MIN_WINDOW, MAX_WINDOW))
        image = Image.fromarray(render_crop(self.caster, self.normals, self.colours, eye, u, right, up, window, px),
                                "RGB")
        rel = pts - eye
        xs = ((rel @ right) / window + 0.5) * px
        ys = (0.5 - (rel @ up) / window) * px
        ring = [(int(round(x)), int(round(y))) for x, y in zip(xs.tolist(), ys.tolist())]
        draw = ImageDraw.Draw(image)
        if ordered and len(ring) >= 2:
            draw.line(ring + ring[:1], fill=OUTLINE, width=2)
        else:
            for x, y in ring:
                draw.line([(x - _CROSS, y), (x + _CROSS, y)], fill=OUTLINE, width=2)
                draw.line([(x, y - _CROSS), (x, y + _CROSS)], fill=OUTLINE, width=2)
        path = Path(path)
        path.parent.mkdir(parents=True, exist_ok=True)
        image.save(path)
        return path


def write_spot_crop(before: MeshData, border, ordered: bool, view: dict, looks: Looks, path, px: int = PX) -> Path:
    """`SpotCropper(before, looks, px).write(...)` for one spot."""
    return SpotCropper(before, looks, px).write(border, ordered, view, path)
