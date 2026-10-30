"""Per-face visibility along the strict 26-view guard's OWN directions (MAIN-INFRA-E5-GUARDDIR-20261029).

THE MEASURED PROBLEM (4F, 2026-10-29, diagnosis-below-oblique.json): E5 rule (d) `interior_twins` removed 20 sites
(62 `minecraft_concrete_white_-1` faces) whose fronts the 128-direction / 4-sample Fibonacci census
(`engine.vis.exposure.compute_side_exposure`) reported as exposure 0, and the Validator's seam view saw nothing; the
strict guard's eight below-oblique views (`engine.guard.views.VIEWS_26`, direction z = +1.011: the camera under the
floor looking up) hit the FRONT of 21 of those faces on 328 px, 0.65-62 in in front of the next surface. Both E5 runs
(Claude, Codex) made the same call. A Fibonacci lattice of 128 directions is ~10 degrees apart, and nothing in it
is the guard's own direction; a sliver seen only through a narrow opening along that direction is missed.

THE RULE. A face the guard can see is never called hidden. Two tests, both along the guard's directions, and a face
is guard-seen if either sees it:

- `guard_front_escapes`: for each of the 52 escape directions (`guard_escape_directions`: for every view direction
  `d` of `VIEWS_26` the direction toward that camera, `-d`, and `+d` too, since the guard renders every sign of every
  axis combination and the nudge makes `-d` of one view differ slightly from the view opposite it), from
  `GUARD_BARY` sample points of the face (10: the census's 4 plus the three near-corner and three edge-mid points)
  pushed `EPS_IN` to the FRONT side, the number of rays that escape (no hit). This is the census test itself, with
  the guard's directions and more samples.
- `guard_pixel_hits`: the guard's own orthographic grid (`ortho_first_hit` at the profile's `guard_size`, framed on
  the recentred positions exactly as `tools/strict_guard_allowed.guard_frame` frames the BEFORE), each of the 26
  views rendered at `scales` (1x: the guard's pixels; 2x: a sub-pixel hedge against framing differences), counting
  per face the pixels whose first hit is that face, split by whether the view direction meets the face's FRONT
  (`normal . d < 0`) or its BACK. A face that owns a pixel in BEFORE changes that pixel when removed, whichever side
  was hit -- the guard renders double-sided.

Precondition as for `compute_side_exposure`: `positions_c` is already recentred by the caller.
"""
from __future__ import annotations

import numpy as np

from engine.guard.views import VIEWS_26, ortho_first_hit
from engine.rays.caster import EmbreeCaster
from engine.vis.exposure import BARY, EPS_IN

#: Sample points per triangle for the guard-direction test: the census's 4 (`BARY`: centroid, three corner-biased),
#: three near-corner (0.8/0.1/0.1) and three edge-mid (0.45/0.45/0.1) points -- 10, inside the triangle, never on
#: an edge (a ray from an edge point can graze the neighbour).
GUARD_BARY = np.vstack([
    BARY,
    [[0.8, 0.1, 0.1], [0.1, 0.8, 0.1], [0.1, 0.1, 0.8]],
    [[0.45, 0.45, 0.1], [0.1, 0.45, 0.45], [0.45, 0.1, 0.45]],
])


def guard_escape_directions(views=VIEWS_26, both_signs: bool = True) -> np.ndarray:
    """`(2 * len(views), 3)` unit directions (or `(len(views), 3)` without `both_signs`): for each guard view
    direction `d` (rays travel along `d`), the escape direction toward that camera `-d` first, then `+d`."""
    out = []
    for view in views:
        d = np.asarray(view, dtype=np.float64)
        d = d / np.linalg.norm(d)
        out.append(-d)
        if both_signs:
            out.append(d)
    return np.asarray(out, dtype=np.float64)


def face_normals(positions_c: np.ndarray, face_w: np.ndarray, ok: np.ndarray) -> np.ndarray:
    """`(F, 3)` unit normals from the welded geometry (winding), zero for `not ok` or zero-area faces."""
    tri = positions_c[face_w]
    cross = np.cross(tri[:, 1] - tri[:, 0], tri[:, 2] - tri[:, 0])
    lengths = np.linalg.norm(cross, axis=1)
    normals = np.zeros_like(cross)
    safe = ok & (lengths > 0)
    normals[safe] = cross[safe] / lengths[safe, None]
    return normals


def guard_front_escapes(positions_c: np.ndarray, face_w: np.ndarray, ok: np.ndarray, directions: np.ndarray, *,
                        faces: np.ndarray | None = None, bary: np.ndarray = GUARD_BARY,
                        caster_factory=EmbreeCaster, caster=None) -> np.ndarray:
    """`(F,)` int64: per face, how many `(sample point, direction)` rays cast from its FRONT side escape, over the
    `directions` whose dot with the face normal is above 1e-6 (the others cannot leave the front) and the `bary`
    sample points pushed `EPS_IN` along the normal. Only the faces in `faces` (default: all ok faces) are sampled;
    the rest read 0. The caster is built once from ALL ok faces (`caster_factory(positions_c, face_w[ok])`) unless
    `caster` is given."""
    positions_c = np.asarray(positions_c, dtype=np.float64)
    face_w = np.asarray(face_w, dtype=np.int64)
    ok = np.asarray(ok, dtype=bool)
    directions = np.asarray(directions, dtype=np.float64).reshape(-1, 3)
    bary = np.asarray(bary, dtype=np.float64)
    n_faces = len(face_w)
    subset = np.flatnonzero(ok) if faces is None else np.asarray(faces, dtype=np.int64).reshape(-1)
    subset = subset[ok[subset]]
    escapes = np.zeros(n_faces, dtype=np.int64)
    if len(subset) == 0 or len(directions) == 0:
        return escapes
    tri = positions_c[face_w]
    normals = face_normals(positions_c, face_w, ok)
    if caster is None:
        caster = caster_factory(positions_c, face_w[ok])
    for w in directions:
        dot = normals[subset] @ w
        ids = subset[dot > 1e-6]
        if len(ids) == 0:
            continue
        pts = np.einsum("sb,fbk->fsk", bary, tri[ids]) + EPS_IN * normals[ids][:, None, :]
        origins = pts.reshape(-1, 3)
        hit = caster.any_hit(origins, np.tile(w, (len(origins), 1)))
        escapes[ids] += (~hit).reshape(len(ids), len(bary)).sum(axis=1)
    return escapes


def guard_pixel_hits(positions_c: np.ndarray, face_w: np.ndarray, ok: np.ndarray, *, views=VIEWS_26,
                     size: tuple[int, int] = (900, 600), scales=(1, 2), frame_points: np.ndarray | None = None,
                     caster_factory=EmbreeCaster) -> tuple[np.ndarray, np.ndarray]:
    """`(front_px, back_px)`, each `(F,)` int64: per face, the pixels of the guard's orthographic renders whose first
    hit is that face, over every view in `views` at `size` scaled by each of `scales`, split by whether the view
    direction meets the face's front (`normal . d < 0`) or its back. `frame_points` (default `positions_c`) sets the
    camera framing, as `ortho_first_hit` takes it; the faces rendered are the ok ones, labelled by their index in
    `face_w`."""
    positions_c = np.asarray(positions_c, dtype=np.float64)
    face_w = np.asarray(face_w, dtype=np.int64)
    ok = np.asarray(ok, dtype=bool)
    n_faces = len(face_w)
    front_px = np.zeros(n_faces, dtype=np.int64)
    back_px = np.zeros(n_faces, dtype=np.int64)
    ids = np.flatnonzero(ok)
    if len(ids) == 0:
        return front_px, back_px
    frame = positions_c if frame_points is None else np.asarray(frame_points, dtype=np.float64)
    normals = face_normals(positions_c, face_w, ok)
    W, H = size
    for view in views:
        d = np.asarray(view, dtype=np.float64)
        d = d / np.linalg.norm(d)
        facing = normals @ d                                  # < 0: the view meets the face's front
        for scale in scales:
            buf = ortho_first_hit(positions_c, face_w[ids], ids, view, frame, size=(int(W * scale), int(H * scale)),
                                  caster_factory=caster_factory)
            hit = buf.tri[buf.tri >= 0]
            if len(hit) == 0:
                continue
            counts = np.bincount(hit, minlength=n_faces)
            front_mask = facing < 0
            front_px += np.where(front_mask, counts, 0)
            back_px += np.where(front_mask, 0, counts)
    return front_px, back_px


def guard_visibility(positions_c: np.ndarray, face_w: np.ndarray, ok: np.ndarray, faces: np.ndarray, *,
                     views=VIEWS_26, size: tuple[int, int] = (900, 600), scales=(1, 2), both_signs: bool = True,
                     bary: np.ndarray = GUARD_BARY, caster_factory=EmbreeCaster) -> dict:
    """Both tests over the faces `faces` (the pixel grid is rendered over all ok faces and read for every face):
    `{"front": (F,) escapes + front pixels, "back": (F,) back pixels, "escapes": (F,), "front_px": (F,),
    "back_px": (F,), "directions": n, "views": n, "samples_per_face": n, "pixel_grid": [[W, H], ...]}`.
    A face is guard-seen from the front when `front[f] > 0`, from the back when `back[f] > 0`."""
    directions = guard_escape_directions(views, both_signs=both_signs)
    escapes = guard_front_escapes(positions_c, face_w, ok, directions, faces=faces, bary=bary,
                                  caster_factory=caster_factory)
    front_px, back_px = guard_pixel_hits(positions_c, face_w, ok, views=views, size=size, scales=scales,
                                         caster_factory=caster_factory)
    W, H = size
    return {"front": escapes + front_px, "back": back_px, "escapes": escapes, "front_px": front_px,
            "back_px": back_px, "directions": int(len(directions)), "views": int(len(views)),
            "samples_per_face": int(len(bary)), "pixel_grid": [[int(W * s), int(H * s)] for s in scales]}
