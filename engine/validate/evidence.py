"""The evidence for a verdict: two orthographic crops of each of the worst failing sites.

A site is a group of failing samples (`checks.validate` groups them on a 6 in grid). For each of the 20
worst (most area), the BEFORE and the AFTER are drawn from the SAME camera: the viewpoint that judged the
site's best-conditioned sample (a direction, or the very camera or probe), looking at the site's centre
through a square window, 256 x 256 px. So the two crops are pixel for pixel the same place, and what
differs is what the floor lost, covered or changed there.

Colours: every face is its look's mean texture colour, shaded by how squarely it faces the camera
(`0.55 + 0.45 |cos|`). A face seen from BEHIND (its winding says it faces away) is mixed half and half with
purple, so a flipped face shows. A ray that meets nothing is pale grey. A yellow tick on the top and the
left edge, at the site's centre, marks where to look. No text is drawn in the picture; the report names it.

Written for the Validator and independent of the code it judges (see `engine.validate`).
"""
from __future__ import annotations

from pathlib import Path

import numpy as np
from PIL import Image

from engine.validate.checks import BACK_TINT, Validation
from engine.validate.sampling import face_normals, used_bbox
from engine.validate.visibility import build_caster

PX = 256
WORST = 20
#: A crop's window is `3 x` the site's size across, never narrower than this nor wider than the cap, in inches.
MIN_WINDOW = 36.0
MAX_WINDOW = 400.0
BACKGROUND = (236, 238, 241)
MARK = (255, 220, 0)
_TICK = 8


def _basis(u: np.ndarray) -> tuple[np.ndarray, np.ndarray]:
    """`(right, up)`, unit vectors that with the viewing direction `u` make a right-handed frame, `up`
    as near the world's +z as the view allows (+y when looking nearly straight up or down)."""
    ref = np.array([0.0, 0.0, 1.0]) if abs(u[2]) < 0.99 else np.array([0.0, 1.0, 0.0])
    right = np.cross(u, ref)
    right /= np.linalg.norm(right)
    return right, np.cross(right, u)


def _face_colours(look_ids: np.ndarray, v: Validation) -> np.ndarray:
    """(F, 3) float64: the colour of every face's look."""
    per_look = np.array([v.looks.colour_of(key) for key in v.look_keys], dtype=np.float64).reshape(-1, 3)
    return per_look[look_ids] if len(look_ids) else np.zeros((0, 3))


def render_crop(caster, normals: np.ndarray, colours: np.ndarray, origin: np.ndarray, u: np.ndarray,
                right: np.ndarray, up: np.ndarray, window: float, px: int = PX) -> np.ndarray:
    """(px, px, 3) uint8: parallel rays along `u` from a `window` x `window` inch square centred on
    `origin` (spanned by `right` and `up`), each pixel the first face it meets, coloured as described
    in the module docstring. `caster` may be None (a mesh with no faces): all background."""
    step = (np.arange(px) + 0.5) / px - 0.5
    x = step[None, :] * window                                 # columns, left to right
    y = -step[:, None] * window                                # rows, top to bottom
    origins = (origin[None, None, :] + x[:, :, None] * right + y[:, :, None] * up).reshape(-1, 3)
    image = np.empty((px * px, 3))
    image[:] = BACKGROUND
    if caster is not None:
        tri, _ = caster.first_hit(origins, np.tile(u, (len(origins), 1)))
        hit = np.flatnonzero(tri >= 0)
        face = tri[hit]
        facing = normals[face] @ u                              # < 0: the ray runs against the normal: a front
        shade = 0.55 + 0.45 * np.abs(facing)
        colour = colours[face] * shade[:, None]
        back = facing > 0.0
        colour[back] = 0.5 * colour[back] + 0.5 * np.array(BACK_TINT)
        image[hit] = colour
    image = np.clip(np.round(image), 0, 255).astype(np.uint8).reshape(px, px, 3)
    mid = px // 2
    image[0:_TICK, mid] = MARK
    image[mid, 0:_TICK] = MARK
    return image


def _viewers(v: Validation, idx: np.ndarray, point_set: np.ndarray) -> tuple[np.ndarray, np.ndarray]:
    """`(toward, position)` for the viewpoints that judged the samples `idx`: the unit vectors from each sample
    to its viewer, and where the viewer stood (NaN for a direction, a viewer at infinity). `point_set` is
    the cameras then the probes."""
    vp = v.viewpoints
    col, extra = v.wit_col[idx].astype(np.int64), v.wit_extra[idx]
    n_dir = len(vp["dirs"])
    toward = np.empty((len(idx), 3))
    position = np.full((len(idx), 3), np.nan)
    toward[extra] = -vp["extra_dirs"][col[extra]]
    standard = ~extra & (col < n_dir)
    toward[standard] = -vp["dirs"][col[standard]]
    pointed = ~extra & (col >= n_dir)
    where = point_set[col[pointed] - n_dir]
    to = where - v.samples.points[idx[pointed]]
    toward[pointed] = to / np.linalg.norm(to, axis=1, keepdims=True)
    position[pointed] = where
    return toward, position


def write_evidence(v: Validation, out_dir, *, limit: int = WORST, px: int = PX) -> list[dict]:
    """Write `evidence/site-NN-before.png` and `-after.png` under `out_dir` for each of the `limit` worst
    sites of `v`, and set that site's `evidence` in the report to their paths (relative to `out_dir`).
    Returns the list of those entries. A floor with no failing site writes nothing."""
    out_dir = Path(out_dir)
    sites = v.report["sites"][:limit]
    if not sites:
        return []
    (out_dir / "evidence").mkdir(parents=True, exist_ok=True)
    caster_b = build_caster(v.before)
    caster_a = build_caster(v.after) if v.after.n_faces else None
    normals_b = face_normals(v.before)
    normals_a = face_normals(v.after)
    colours_b = _face_colours(v.look_before, v)
    colours_a = _face_colours(v.look_after, v)
    lo_b, hi_b = used_bbox(v.before)
    lo_a, hi_a = used_bbox(v.after) if v.after.n_faces else (lo_b, hi_b)
    lo, hi = np.minimum(lo_b, lo_a), np.maximum(hi_b, hi_a)
    point_set = np.vstack([v.viewpoints["cams"], v.viewpoints["probes"]])
    entries = []
    for site, members in zip(sites, v.members):
        pts = v.samples.points[members]
        centre = (pts.min(axis=0) + pts.max(axis=0)) / 2.0
        # the sample whose line of sight is the most square to its face speaks for the site
        toward_all, position_all = _viewers(v, members, point_set)
        squareness = np.abs(np.einsum("ij,ij->i", normals_b[v.samples.face[members]], toward_all))
        best = int(np.argmax(squareness))
        toward, position = toward_all[best], position_all[best]
        anchor = v.samples.points[members[best]]
        u = -toward
        if np.isnan(position[0]):                               # a direction: start outside the whole model
            with np.errstate(divide="ignore", invalid="ignore"):
                far = np.where(toward > 0, (hi - centre) / toward, np.where(toward < 0, (lo - centre) / toward, np.inf))
            origin = centre + toward * (float(far.min()) + 1.0)
        else:                                                   # the camera or probe itself, shifted over the site
            shift = centre - anchor
            origin = position + (shift - (shift @ u) * u)
        right, up = _basis(u)
        window = float(np.clip(3.0 * site["size"], MIN_WINDOW, MAX_WINDOW))
        stem = f"site-{site['id']:02d}"
        for name, caster, normals, colours in (("before", caster_b, normals_b, colours_b),
                                               ("after", caster_a, normals_a, colours_a)):
            image = render_crop(caster, normals, colours, origin, u, right, up, window, px)
            Image.fromarray(image, "RGB").save(out_dir / "evidence" / f"{stem}-{name}.png")
        site["evidence"] = {"before": f"evidence/{stem}-before.png", "after": f"evidence/{stem}-after.png"}
        entries.append(site["evidence"])
    return entries
