"""Triptych PNG output for the facade guard: BEFORE | AFTER | DIFF, side by side.

BEFORE/AFTER are shaded by the normal of the face each pixel hit (simple Lambert against one
fixed light, plus an ambient floor), so a person can actually see surface detail instead of a flat
silhouette -- pass `normals_before`/`normals_after` (a `(F, 3)` unit normal per possible `tri` id,
built from the same geometry the render was cast against) to get it; omitted, a panel falls back
to the old flat "hit" grey. DIFF stays a flat, light-grey model with failures in red and tolerated
depth changes in amber, unshaded, so the overlay colours read unambiguously regardless of the
underlying surface's orientation."""
from __future__ import annotations

from pathlib import Path

import numpy as np
from PIL import Image

from engine.guard.compare import (PX_EDGE_FLICKER, PX_HOLE, PX_MATERIAL_CHANGED, PX_MOVED_OTHER,
                                   PX_MOVED_SAME_FLAT)

_BG = (255, 255, 255)
_MODEL = (222, 222, 226)
_FAIL = (220, 40, 40)
_AMBER = (235, 165, 35)

#: One fixed directional light (arbitrary but stable), matching the preview page's own sun.
_LIGHT = np.array([0.4, -0.5, 0.9])
_LIGHT = _LIGHT / np.linalg.norm(_LIGHT)
#: Floor of a hit pixel's shade, so a face edge-on to the light is still visible, not pure black.
_AMBIENT = 0.35


def _shade(tri: np.ndarray, normals: np.ndarray) -> np.ndarray:
    """Per-pixel Lambert factor in `[_AMBIENT, 1.0]`, `_AMBIENT` where `tri` missed."""
    shade = np.full(tri.shape, _AMBIENT, dtype=np.float64)
    hit = tri >= 0
    if hit.any():
        lambert = np.clip(np.asarray(normals)[tri[hit]] @ _LIGHT, 0.0, None)
        shade[hit] = _AMBIENT + (1.0 - _AMBIENT) * lambert
    return shade


def _panel(depth: np.ndarray, tri: np.ndarray | None = None, normals: np.ndarray | None = None) -> np.ndarray:
    depth = np.asarray(depth)
    hit = np.isfinite(depth)
    img = np.full(depth.shape + (3,), _BG, dtype=np.uint8)
    if tri is not None and normals is not None:
        shade = _shade(np.asarray(tri), normals)
        model = np.asarray(_MODEL, dtype=np.float64)
        shaded = np.clip(model[None, None, :] * shade[..., None], 0, 255).astype(np.uint8)
        img[hit] = shaded[hit]
    else:
        img[hit] = _MODEL
    return img


def save_triptych(path, before: tuple[np.ndarray, np.ndarray], after: tuple[np.ndarray, np.ndarray],
                   verdict_mask: np.ndarray, normals_before: np.ndarray | None = None,
                   normals_after: np.ndarray | None = None) -> None:
    """Write `path` as one PNG: three `(H, W)` panels side by side -- BEFORE model (shaded when
    `normals_before` is given), AFTER model (shaded when `normals_after` is given), and DIFF (the
    flat, unshaded BEFORE silhouette with `verdict_mask` overlaid: `PX_HOLE` / `PX_MATERIAL_CHANGED`
    / `PX_MOVED_OTHER` in red, `PX_MOVED_SAME_FLAT` and `PX_EDGE_FLICKER` in amber -- amber is
    "reported, tolerated by some caller", and whether a flicker pixel actually failed depends on
    that view's `edge_flicker_cap`, which this module is not given).

    `before`/`after` are `(depth, tri)` pairs for ONE view, as returned by `ortho_first_hit`
    (a `HitBuffers` unpacks as that pair); `tri` values index `normals_before`/`normals_after`
    exactly as they index the `face_ids` that render was cast with.
    `verdict_mask` is the `classify_pixels` code array for that same view (same `(H, W)` shape)."""
    before_depth, before_tri = before
    after_depth, after_tri = after
    verdict_mask = np.asarray(verdict_mask)

    panel_before = _panel(before_depth, before_tri, normals_before)
    panel_after = _panel(after_depth, after_tri, normals_after)
    panel_diff = _panel(before_depth)
    panel_diff[np.isin(verdict_mask, (PX_MOVED_SAME_FLAT, PX_EDGE_FLICKER))] = _AMBER
    fail = np.isin(verdict_mask, (PX_HOLE, PX_MATERIAL_CHANGED, PX_MOVED_OTHER))
    panel_diff[fail] = _FAIL

    combo = np.concatenate([panel_before, panel_after, panel_diff], axis=1)
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    Image.fromarray(combo).save(path)
