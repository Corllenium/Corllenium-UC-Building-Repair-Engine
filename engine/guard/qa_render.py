"""The visual QA sheet every `python -m engine.cli fix` run writes under `<run dir>/qa/`.

WHY. Every number the pipeline reports is a claim about pictures -- the guards compare renders
pixel by pixel -- yet none of those pictures is one a person would look at: the triptychs are
diagnostic, one image per axis. This sheet is what a person checks before trusting a run: the
fixed mesh shaded, with the EDGES SKETCHUP WILL DRAW, hidden lines removed, from 12 directions and
9 close-ups. A missing face, a stray triangle, a gridline a merge failed to dissolve or a skirt
hanging where it should not are all visible here at a glance, and none of them is visible in
report.json.

WHICH EDGES. `polygon_edges` builds them from the merge's own rings: a merged region is drawn as
its outer loop AND its inner loops (the SketchUp export carries holes, even though the ngon OBJ
cannot), never its triangulation diagonals; a face copied through unmerged is drawn as its three
triangle edges, because that is what it is. So the sheet shows the polygons the export will
contain, not the triangles Unity will.

Ported from `spike/17_visual_qa.py` with two changes: the edge pass is vectorised (every sample of
every edge is projected and depth-tested at once, and an edge is drawn by marking the pixel of
each visible sample, sampled finely enough that consecutive samples are under a pixel apart, with
a per-pixel depth tolerance taken from the visible surface's own slope -- see `_render`), and
a close-up whose slice of the model holds fewer than 3 vertices falls back to the whole-model
frame instead of being skipped -- so a run always writes exactly 21 files, which a test can
count. Deterministic: fixed views, no randomness, PNG written from the same array every time.

`trimesh`/`embreex` are never imported here -- ray casting goes through
`engine.rays.caster.EmbreeCaster`, as everywhere else in `engine/`.
"""
from __future__ import annotations

from pathlib import Path

import numpy as np
from PIL import Image

from engine.model import MeshData
from engine.rays.caster import EmbreeCaster

#: The 12 whole-model views, as VIEW DIRECTIONS (the way the camera looks). Taken verbatim from
#: `spike/17_visual_qa.py`, where they were chosen: the two poles, four near-horizontal sides seen
#: slightly from above, four obliques and two low grazing sides that catch a skirt's underside.
QA_VIEWS: dict[str, tuple[float, float, float]] = {
    "top": (0.01, 0.01, -1.0), "bottom": (0.01, 0.01, 1.0),
    "px": (-1.0, 0.01, -0.15), "nx": (1.0, 0.01, -0.15),
    "py": (0.01, -1.0, -0.15), "ny": (0.01, 1.0, -0.15),
    "obl_top_a": (0.45, 0.55, -0.70), "obl_top_b": (-0.6, 0.4, -0.6),
    "obl_bot_a": (0.45, 0.55, 0.70), "obl_bot_b": (-0.6, -0.4, 0.6),
    "side_low_a": (0.9, 0.3, -0.05), "side_low_b": (-0.3, -0.9, -0.05),
}

#: Each of the 3 close-up slices is rendered from these three directions.
QA_CLOSE_UP_VIEWS: tuple[tuple[str, tuple[float, float, float]], ...] = (
    ("top", (0.45, 0.55, -0.70)), ("bottom", (0.45, 0.55, 0.70)), ("side", (0.9, 0.3, -0.05)))

#: How many slices the close-ups cut the model into, along its longer horizontal axis.
QA_SLICES = 3

_BACKGROUND = 246
_FACE_RGB = np.array([205.0, 205.0, 210.0])
_EDGE_RGB = np.array([40, 40, 46], dtype=np.uint8)
_LIGHT = np.array([0.35, -0.45, 0.82]) / np.linalg.norm([0.35, -0.45, 0.82])
#: Frame margin: the view is 6 % wider than the model's projected extent.
_MARGIN = 1.06
#: Cap on the per-pixel depth slope the edge test allows for (about 87 degrees off the view):
#: a surface seen almost edge-on would otherwise excuse anything behind it.
_MAX_SLOPE = 20.0


def qa_file_names() -> list[str]:
    """The 21 file names `write_qa_sheet` writes, in the order it writes them."""
    return ([f"{name}.png" for name in QA_VIEWS]
            + [f"chunk{i}_{tag}.png" for i in range(QA_SLICES) for tag, _ in QA_CLOSE_UP_VIEWS])


def polygon_edges(mesh: MeshData, rings: dict[int, dict]) -> np.ndarray:
    """`(E, 2)` int64 vertex-index pairs into `mesh.positions`, each undirected edge once, sorted:
    the edges SketchUp will draw for `mesh`.

    `rings` is `engine.fixes.merge.MergeResult.rings` (as carried by `FixResult.rings`): every row
    of one merged region maps to the SAME dict, deduplicated here by identity, and contributes its
    outer loop and every inner loop -- but never the diagonals its triangulation needed. A row
    with no entry (copied through, a multi-piece region, or every row when the merge was rolled
    back and `rings` is empty) contributes its three triangle edges."""
    pairs: list[tuple[int, int]] = []
    seen: set[int] = set()
    for f in range(mesh.n_faces):
        loops = rings.get(f)
        if loops is None:
            a, b, c = (int(v) for v in mesh.face_v[f])
            pairs += [(a, b), (b, c), (c, a)]
            continue
        if id(loops) in seen:
            continue
        seen.add(id(loops))
        for loop in [loops["outer"], *loops["inners"]]:
            ids = [int(v) for v in loop]
            pairs += list(zip(ids, ids[1:] + ids[:1]))
    if not pairs:
        return np.zeros((0, 2), np.int64)
    out = np.sort(np.asarray(pairs, dtype=np.int64), axis=1)
    out = out[out[:, 0] != out[:, 1]]
    return np.unique(out, axis=0)


def _camera(view, frame: np.ndarray, size: tuple[int, int]):
    width, height = size
    d = np.asarray(view, dtype=np.float64)
    d = d / np.linalg.norm(d)
    up_hint = np.array([0.0, 1.0, 0.0]) if abs(d[2]) > 0.99 else np.array([0.0, 0.0, 1.0])
    right = np.cross(d, up_hint)
    right /= np.linalg.norm(right)
    up = np.cross(right, d)
    er, eu = frame @ right, frame @ up
    pixel = max((er.max() - er.min()) / width, (eu.max() - eu.min()) / height) * _MARGIN
    pixel = max(pixel, 1e-9)
    return d, right, up, (er.max() + er.min()) / 2.0, (eu.max() + eu.min()) / 2.0, pixel


def _render(caster, positions_c: np.ndarray, normals: np.ndarray, edges: np.ndarray, view,
            frame: np.ndarray, size: tuple[int, int], diag: float) -> Image.Image:
    """One shaded image with hidden-line-removed edges. Faces are shaded double-sided
    (`|n . light|`), the way SketchUp and the project's Unity materials draw them.

    An edge sample is drawn when it is no further along the view ray than the surface its pixel
    shows, plus a tolerance PER PIXEL: the depth change that surface's own slope makes over
    three quarters of a pixel (a sample is at most half a pixel diagonal from its pixel's ray),
    capped at a slope of `_MAX_SLOPE`, plus `max(diag * 2e-4, 0.05 in)` of numeric slack. An edge
    lying ON the visible surface meets that bound -- at a crease it lies on both faces' planes --
    and one behind it does not, however close. A single flat tolerance cannot do both: three
    pixels drew about 6,000 hidden edge samples through file A's top view (0.5 to 3.3 in under
    the surface they were drawn over), and the spike's 0.5 in drops edges on steep faces."""
    width, height = size
    d, right, up, cx, cy, pixel = _camera(view, frame, size)
    standoff = -d * diag * 2.0
    xs = cx + (np.arange(width) - width / 2.0 + 0.5) * pixel
    ys = cy - (np.arange(height) - height / 2.0 + 0.5) * pixel
    gx, gy = np.meshgrid(xs, ys)
    origins = (gx[..., None] * right + gy[..., None] * up + standoff).reshape(-1, 3)
    tri, t = caster.first_hit(origins, np.tile(d, (len(origins), 1)))

    img = np.full((height * width, 3), _BACKGROUND, dtype=np.uint8)
    hit = tri >= 0
    hit_normal = normals[tri[hit]]
    shade = 0.55 + 0.45 * np.abs(hit_normal @ _LIGHT)
    img[hit] = np.clip(_FACE_RGB * shade[:, None], 0, 255).astype(np.uint8)
    depth = np.full(height * width, np.inf)
    depth[hit] = t[hit]
    # depth change per unit of image-plane offset, on the surface each pixel shows
    slope = np.zeros(height * width)
    slope[hit] = np.minimum(np.hypot(hit_normal @ right, hit_normal @ up)
                            / np.maximum(np.abs(hit_normal @ d), 1e-6), _MAX_SLOPE)
    img = img.reshape(height, width, 3)
    depth = depth.reshape(height, width)
    slope = slope.reshape(height, width)

    if len(edges):
        pa, pb = positions_c[edges[:, 0]], positions_c[edges[:, 1]]
        span = np.hypot((pb - pa) @ right, (pb - pa) @ up) / pixel
        count = np.minimum(np.ceil(span * 1.5).astype(np.int64) + 2, 4 * max(width, height))
        edge_of = np.repeat(np.arange(len(edges)), count)
        k = np.arange(int(count.sum())) - np.repeat(np.cumsum(count) - count, count)
        s = k / np.repeat(count - 1, count)
        pts = pa[edge_of] + (pb - pa)[edge_of] * s[:, None]
        px = np.floor((pts @ right - cx) / pixel + width / 2.0).astype(np.int64)
        py = np.floor(height / 2.0 - (pts @ up - cy) / pixel).astype(np.int64)
        along = (pts - standoff) @ d
        inside = (px >= 0) & (px < width) & (py >= 0) & (py < height)
        slack = max(diag * 2e-4, 0.05)
        iy, ix = py[inside], px[inside]
        visible = np.zeros(len(pts), dtype=bool)
        visible[inside] = along[inside] <= depth[iy, ix] + 0.75 * pixel * slope[iy, ix] + slack
        img[py[visible], px[visible]] = _EDGE_RGB
    return Image.fromarray(img)


def write_qa_sheet(mesh: MeshData, polygon_edges: np.ndarray | None, out_dir: Path,
                   size: tuple[int, int] = (1600, 1000)) -> list[Path]:
    """Render `mesh` from the 12 `QA_VIEWS` and 9 close-ups and write them as PNGs into `out_dir`
    (created if needed), named by `qa_file_names()`. Returns the written paths, in that order.

    `polygon_edges` is `(E, 2)` vertex-index pairs into `mesh.positions` -- build it with
    `polygon_edges(mesh, rings)` -- or `None` for every triangle edge. Rays are cast against
    every face of `mesh`, so a close-up still shows whatever of the REST of the model stands in
    front of its slice.

    Only the vertices faces actually use decide the frame and the recentring: `mesh.positions`
    may carry rows no face references any more (a removed face's corners), and framing on those
    could zoom the picture out onto nothing."""
    out_dir = Path(out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)

    used = np.unique(mesh.face_v.reshape(-1))
    frame_w = mesh.positions[used]
    centre = (frame_w.min(axis=0) + frame_w.max(axis=0)) / 2.0
    positions_c = mesh.positions - centre
    frame = positions_c[used]
    diag = float(np.linalg.norm(frame.max(axis=0) - frame.min(axis=0))) or 1.0

    tri = positions_c[mesh.face_v]
    normals = np.cross(tri[:, 1] - tri[:, 0], tri[:, 2] - tri[:, 0])
    length = np.linalg.norm(normals, axis=1)
    normals = np.where(length[:, None] > 0.0, normals / np.maximum(length, 1e-300)[:, None], 0.0)
    caster = EmbreeCaster(positions_c, mesh.face_v)

    if polygon_edges is None:
        f = mesh.face_v
        polygon_edges = np.unique(np.sort(np.concatenate([f[:, [0, 1]], f[:, [1, 2]], f[:, [2, 0]]]),
                                          axis=1), axis=0)
    edges = np.asarray(polygon_edges, dtype=np.int64).reshape(-1, 2)

    written: list[Path] = []
    for name, view in QA_VIEWS.items():
        path = out_dir / f"{name}.png"
        _render(caster, positions_c, normals, edges, view, frame, size, diag).save(path)
        written.append(path)

    extent = frame.max(axis=0) - frame.min(axis=0)
    axis = int(np.argmax(extent[:2]))
    lo = float(frame[:, axis].min())
    step = float(extent[axis]) / QA_SLICES
    for i in range(QA_SLICES):
        in_slice = (frame[:, axis] >= lo + i * step) & (frame[:, axis] <= lo + (i + 1) * step)
        slice_frame = frame[in_slice] if int(in_slice.sum()) >= 3 else frame
        for tag, view in QA_CLOSE_UP_VIEWS:
            path = out_dir / f"chunk{i}_{tag}.png"
            _render(caster, positions_c, normals, edges, view, slice_frame, size, diag).save(path)
            written.append(path)
    return written
