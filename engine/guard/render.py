"""Triptych PNG output for the facade guard: BEFORE | AFTER | DIFF, side by side.

Shading here is intentionally simple (flat "hit" grey vs white background), matching the
ghost/xray images in `spike/11_guard_feedback.py` and `spike/10_ds_visibility.py` --
`ortho_first_hit` only gives `save_triptych` depth and face-id buffers, not normals, so there is
no per-face lighting here (see `spike/06_render_classes.py` for that; it needs the mesh's normals
directly, which this module never receives)."""
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


def _panel(depth: np.ndarray) -> np.ndarray:
    depth = np.asarray(depth)
    img = np.full(depth.shape + (3,), _BG, dtype=np.uint8)
    img[np.isfinite(depth)] = _MODEL
    return img


def save_triptych(path, before: tuple[np.ndarray, np.ndarray], after: tuple[np.ndarray, np.ndarray],
                   verdict_mask: np.ndarray) -> None:
    """Write `path` as one PNG: three `(H, W)` panels side by side -- BEFORE model silhouette,
    AFTER model silhouette, and DIFF (the BEFORE silhouette with `verdict_mask` overlaid:
    `PX_HOLE` / `PX_MATERIAL_CHANGED` / `PX_MOVED_OTHER` in red, `PX_MOVED_SAME_FLAT` and
    `PX_EDGE_FLICKER` in amber -- amber is "reported, tolerated by some caller", and whether a
    flicker pixel actually failed depends on that view's `edge_flicker_cap`, which this module is
    not given).

    `before`/`after` are `(depth, tri)` pairs for ONE view, as returned by `ortho_first_hit`
    (a `HitBuffers` unpacks as that pair).
    `verdict_mask` is the `classify_pixels` code array for that same view (same `(H, W)` shape)."""
    before_depth, _ = before
    after_depth, _ = after
    verdict_mask = np.asarray(verdict_mask)

    panel_before = _panel(before_depth)
    panel_after = _panel(after_depth)
    panel_diff = _panel(before_depth)
    panel_diff[np.isin(verdict_mask, (PX_MOVED_SAME_FLAT, PX_EDGE_FLICKER))] = _AMBER
    fail = np.isin(verdict_mask, (PX_HOLE, PX_MATERIAL_CHANGED, PX_MOVED_OTHER))
    panel_diff[fail] = _FAIL

    combo = np.concatenate([panel_before, panel_after, panel_diff], axis=1)
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    Image.fromarray(combo).save(path)
