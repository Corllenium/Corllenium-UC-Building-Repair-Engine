"""The Validator's three checks, on a BEFORE and an AFTER of one floor (AGENTS.md section 6).

Written for the Validator and independent of the code it judges (see `engine.validate`). The one
exception is check 2, which has to run `engine.detectors.errors.find_errors` on both meshes, and that
module imports `engine.fixes`, `engine.guard` and `engine.vis`: so it is imported LAZILY, inside
`validate` when it is not handed the errors, and nowhere else. Loading this module loads none of them.

A look key (`data/campus/materials.json`: texture sha256 + Kd + d) is the identity of what a face
looks like, never a `usemtl` number. A face's look is `looks.key[mesh.materials[face_material]]`.

HOW A FLOOR IS JUDGED. Two layers, and a floor passes check 3 only when both pass (job P2-V2; the owner's floor of
2026-10-10, AGENTS.md section 5).

* SAMPLES. The BEFORE is sampled (`sampling.face_samples`, at least 4 a face and one per 36 sq in) and every sample
  is looked at from the directions at or above the horizon (64 of a 128-point sphere), a ring of cameras and the
  eye-height probes (`visibility.visible_samples`). The
  sample's surface is asked of AFTER from its witness, the best-conditioned viewpoint (the one least edge-on to its
  face; one that sees its front, when any does). COVERED is asked on EVERY line of sight that saw the sample, from
  either side (`_covered_on_every_line`): blocked in AFTER by new geometry more than the depth tolerance in front of
  it (only AFTER's new geometry can block: `changed_faces`, which also ends the float32 corner artefact).
* THE FLOOR (`_Floor`). The samples are too sparse to be the whole judge (P2-E3: a face with 0 of 9 samples seen
  showed through an opening between them). Every removed face (its fingerprint gone from AFTER) gets a dense lattice
  (`floor.floor_lattice`: 36 points plus one per sq in, at most 4,096), every new face of AFTER gets one too, to find
  what it stands in front of, and the covered samples name their faces and lines. Each (face, viewpoint) so found
  is MEASURED in pixels at 0.02 in/px (`floor.face_pixels`), and a face fails when one viewpoint shows more than
  `floor.VISIBLE_FLOOR_PX` of its pixels lost (removed, replaced by another look, or covered). The floor never
  excuses a sample's failure: the samples still fail what they find.

What the samples are asked:

* check 1, textures there: AFTER shows, at that depth (within `max(2 print steps, 0.05 in)`), a
  surface with the same look key, the same UV (mod 1, within one texel of that texture), seen from its
  front where BEFORE's front was seen; nothing covers it; and no NEW face lies on it or in front of it
  within the tolerance in a look or UV that place did not have (`overlaid`: it hides the texture, or
  z-fights with it; a layer up to 0.02 in behind z-fights too);
* check 3, nothing deleted or covered: a surface of the same look is at that depth, nothing is in
  front of it, and nothing new lies on it. Faces whose fingerprint (snapped corners, winding, look, UV
  mod 1) AFTER does not have are looked at from 1,024 extra directions too; what only those see counts
  for check 3 alone;
* check 2, problems solved: `find_errors` on both, against the targets the owner signs (until then it
  only reports).

v0 has NO allowed-change classes. Removing one copy of a back-to-back pair fails, which is expected until the
E4 and E5 engines name their classes: in ANOTHER look it fails both checks (the look is gone from that place:
check 1 `look`, check 3 `replaced`); in the SAME look it fails check 1 only (`side`: whoever saw the removed
copy's front now sees the other copy's back) and passes check 3. Cutting a flicker loser along a winner's border
fails check 3 the same way. Deleting or adding an identical coplanar copy (same look, UV and winding) is no change
and passes.
"""
from __future__ import annotations

import colorsys
import dataclasses
import hashlib
import json
import struct
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Sequence

import numpy as np

from engine.model import MeshData
from engine.validate.sampling import (Samples, face_areas, face_normals, face_samples, recentred, used_bbox,
                                      uv_at)
from engine.validate.viewpoints import above_horizon_directions, interior_probes, pedestrian_ring
from engine.validate.floor import (FLOOR_IN_PER_PX, LATTICE_CAP, LATTICE_MIN, LATTICE_PER_SQ_IN, PIXEL_BUDGET,
                                   VISIBLE_FLOOR_PX, Viewpoint, face_pixels, floor_lattice)
from engine.validate.visibility import EPS_ORIGIN, MIN_COS, VisibleSet, _side, build_caster, visible_samples

#: The look of a face with no `usemtl` (material -1), which is never "the last material" by accident.
NO_MATERIAL = "<no material>"
_PNG_SIGNATURE = b"\x89PNG\r\n\x1a\n"

#: The depth tolerance is `max(DEPTH_STEPS print steps, MIN_DEPTH_TOL)`.
DEPTH_STEPS = 2.0
MIN_DEPTH_TOL = 0.05

#: What a face seen from BEHIND is mixed with in the evidence crops (`engine.validate.evidence`): purple. The
#: stand-in colour of a look nobody knows keeps this far (in hue, as a fraction of a turn) away from it, so a
#: front face in such a look is never mistaken for a back face.
BACK_TINT = (150, 60, 160)
_TINT_HUE = colorsys.rgb_to_hsv(*(c / 255.0 for c in BACK_TINT))[0]
_TINT_ARC = 0.15


# ---------------------------------------------------------------------------------------------
# What the checks measure with
# ---------------------------------------------------------------------------------------------

def png_size(path) -> tuple[int, int] | None:
    """`(width, height)` in pixels of the image at `path`, read from the PNG header (the IHDR chunk,
    bytes 16 to 24) without decoding it. Another image format is sized by Pillow's own header read.
    None when the file is missing or is no image."""
    try:
        with open(path, "rb") as fh:
            head = fh.read(24)
    except OSError:
        return None
    if len(head) == 24 and head[:8] == _PNG_SIGNATURE and head[12:16] == b"IHDR":
        width, height = struct.unpack(">II", head[16:24])
        return (width, height) if width > 0 and height > 0 else None
    try:
        from PIL import Image
        with Image.open(path) as image:
            return (int(image.size[0]), int(image.size[1]))
    except Exception:                       # not an image: Pillow raises its own, and OSError, and others
        return None


def print_step(mesh: MeshData) -> float:
    """The export's own precision in inches: a coordinate is printed to `sig_digits` significant
    digits, so on an axis whose largest |coordinate| is `a` the print step is
    `10 ** (ceil(log10(a)) - sig_digits)`; the largest of the three axes. A model near y = 24,000
    printed to 6 digits has 0.1 in. Only vertices some face uses count. 0.0 for a mesh with no faces."""
    used = np.zeros(len(mesh.positions), dtype=bool)
    used[mesh.face_v.reshape(-1)] = True
    if not used.any():
        return 0.0
    biggest = np.abs(mesh.positions[used]).max(axis=0)
    exponent = np.ceil(np.log10(np.maximum(biggest, 1e-9)))
    return float((10.0 ** (exponent - mesh.sig_digits)).max())


def depth_tolerance(step: float) -> float:
    """How far two surfaces may be apart along a view ray and still be the same one: `max(2 * print
    step, 0.05 in)`. On CHTM's floors that is 0.2 in; on anything printed finer, 0.05 in."""
    return max(DEPTH_STEPS * float(step), MIN_DEPTH_TOL)


@dataclass(frozen=True)
class Looks:
    """Look keys of materials, and what the UV test and the evidence need to know about each look.

    `key`: material name -> look key (`materials.json`); `texel`: look key -> (width, height) in
    pixels of its texture, only for a look whose texture file was found; `colour`: look key -> mean
    RGB (texture mean times Kd), for the evidence crops; `flat`: the look keys known to have no texture
    at all, which have no UV to compare (a look in neither `texel` nor `flat` is one whose texture file
    was not found: `validate` lists it in the report's notes, it never goes unmentioned)."""
    key: dict
    texel: dict = field(default_factory=dict)
    colour: dict = field(default_factory=dict)
    flat: frozenset = field(default_factory=frozenset)

    def key_of(self, material: str) -> str:
        """The look key of a material; one `materials.json` does not know keeps its own name, so two
        such names stay two looks and never equal a real key."""
        return self.key.get(material) or f"unknown:{material}"

    def unknown(self, mesh: MeshData) -> list[str]:
        """The materials of `mesh` that `materials.json` does not list, sorted."""
        return sorted({m for m in mesh.materials if m not in self.key})

    def colour_of(self, look_key: str) -> tuple[int, int, int]:
        """The evidence colour of a look: its mean texture colour when known, else a stable colour made
        from the key, so different looks differ in the crops even when nothing is known about them. That
        colour is bright and fairly saturated, and its hue runs round the whole circle except the arc of
        `BACK_TINT`'s purple (`_TINT_ARC` of a turn each side), which a back face is mixed with."""
        known = self.colour.get(look_key)
        if known is not None:
            return tuple(int(c) for c in known)
        digest = hashlib.sha256(look_key.encode("utf-8")).digest()
        turn = int.from_bytes(digest[:4], "big") / 2.0 ** 32                      # [0, 1)
        hue = (_TINT_HUE + _TINT_ARC + turn * (1.0 - 2.0 * _TINT_ARC)) % 1.0
        sat, val = 0.45 + 0.45 * digest[4] / 255.0, 0.55 + 0.40 * digest[5] / 255.0
        r, g, b = colorsys.hsv_to_rgb(hue, sat, val)
        return (int(round(r * 255)), int(round(g * 255)), int(round(b * 255)))


class LookTable:
    """Look keys as small integers, shared by BEFORE and AFTER so that their look ids compare."""

    def __init__(self) -> None:
        self._ids: dict[str, int] = {}

    def id(self, look_key: str) -> int:
        return self._ids.setdefault(look_key, len(self._ids))

    @property
    def keys(self) -> list[str]:
        """The look key of each id, in id order."""
        return list(self._ids)


def face_look_ids(mesh: MeshData, looks: Looks, table: LookTable) -> np.ndarray:
    """(F,) int64: the look id of every face of `mesh`."""
    per_material = np.array([table.id(looks.key_of(name)) for name in mesh.materials], dtype=np.int64)
    fm = mesh.face_material
    ok = (fm >= 0) & (fm < len(per_material))
    ids = np.zeros(mesh.n_faces, dtype=np.int64)
    ids[ok] = per_material[fm[ok]]
    if not ok.all():
        ids[~ok] = table.id(NO_MATERIAL)
    return ids


def _mean_rgb(path: Path) -> np.ndarray | None:
    try:
        from PIL import Image
        with Image.open(path) as image:
            return np.asarray(image.convert("RGB"), dtype=np.float64).reshape(-1, 3).mean(axis=0)
    except Exception:
        return None


def _mtl_kd(mat) -> np.ndarray:
    """The `Kd` of an MTL material as 3 floats; white when it has none."""
    for line in mat.lines:
        parts = line.split()
        if len(parts) >= 4 and parts[0] == "Kd":
            try:
                return np.array([float(v) for v in parts[1:4]], dtype=np.float64)
            except ValueError:
                break
    return np.ones(3)


def load_looks(materials_json, sources: Sequence[tuple[dict, Path]]) -> Looks:
    """`Looks` from `data/campus/materials.json` and the MTLs the textures are found through.

    `sources` is a list of `(parse_mtl(...) result, directory its map_Kd paths are relative to)`: the
    BEFORE snapshot, and the AFTER output when it has its own. A look's texel size and mean colour
    come from the first source that has its texture on disk; a look with no texture file is
    coloured by its Kd, and has no texel size (`validate` then says in its notes that the UV is not
    compared: nothing shows it, or the file is missing).

    A material the MTL has but materials.json does not list (sidewalk A's only one) is NOT left out: it
    gets the look key `unknown:<name>` (`Looks.key_of`), and its texture size and mean colour are read
    from the MTL and PNG it came with, so its UV is compared like any other."""
    materials = json.loads(Path(materials_json).read_text(encoding="utf-8"))["materials"]
    key = {name: entry["look"] for name, entry in materials.items()}
    flat = {entry["look"] for entry in materials.values() if not entry.get("map_kd")}
    texel: dict = {}
    colour: dict = {}
    for mtl, base in sources:
        for name, mat in mtl.items():
            entry = materials.get(name)
            if entry is None:
                look, kd = f"unknown:{name}", _mtl_kd(mat)
                if not mat.map_kd:
                    flat.add(look)
            else:
                look = entry["look"]
                kd = np.asarray(entry.get("kd") or (1.0, 1.0, 1.0), dtype=np.float64)
            texture = None
            if mat.map_kd:
                candidate = Path(base) / mat.map_kd.replace("\\", "/")
                texture = candidate if candidate.is_file() else None
            if texture is not None:
                size = png_size(texture)
                if size is not None:
                    texel.setdefault(look, size)
                mean = _mean_rgb(texture)
                if mean is not None and look not in colour:
                    colour[look] = tuple(int(round(min(255.0, c))) for c in mean * kd)
            if look not in colour:
                colour[look] = tuple(int(round(min(255.0, c * 255.0))) for c in kd)
    return Looks(key=key, texel=texel, colour=colour, flat=frozenset(flat))


#: The UVs in a fingerprint are taken mod 1 (a whole-tile shift is no change) in steps of this much.
_UV_QUANTUM = 1e-3


def face_fingerprints(mesh: MeshData, step: float, look_ids: np.ndarray) -> np.ndarray:
    """(F, 16) int64, one row per face: its three corners snapped to the print grid (`round(x / step)`), written
    from the smallest corner on and in winding order; its look id; and the UV of each of those corners mod 1 in
    steps of `_UV_QUANTUM` (-1 for a face without UVs). Two faces with the same row are the same face for the
    Validator: the same place, wound the same way, the same look, the same texture position. The opposite
    winding is another row, so a flipped face is looked at again, and so is a copy with another UV."""
    q = step if step > 0.0 else 1e-6
    corners = np.round(mesh.positions[mesh.face_v] / q).astype(np.int64)          # (F, 3, 3)
    first = np.lexsort((corners[:, :, 2], corners[:, :, 1], corners[:, :, 0]), axis=-1)[:, 0]
    order = (first[:, None] + np.arange(3)[None, :]) % 3
    rolled = np.take_along_axis(corners, order[:, :, None], axis=1).reshape(mesh.n_faces, 9)
    vt = mesh.face_vt
    has_uv = (vt >= 0).all(axis=1) & (vt < len(mesh.uvs)).all(axis=1)
    uv = np.full((mesh.n_faces, 3, 2), np.nan)
    if has_uv.any():
        uv[has_uv] = mesh.uvs[vt[has_uv]]
    uv = np.take_along_axis(uv, order[:, :, None], axis=1)
    frac = uv - np.floor(uv)
    turn = int(round(1.0 / _UV_QUANTUM))                          # a step count of a whole tile is the tile edge: 0
    marks = np.where(np.isnan(frac), -1, np.round(frac / _UV_QUANTUM) % turn).astype(np.int64).reshape(mesh.n_faces, 6)
    return np.concatenate([rolled, np.asarray(look_ids, dtype=np.int64)[:, None], marks], axis=1)


# ---------------------------------------------------------------------------------------------
# Settings, and what each sample ends up as
# ---------------------------------------------------------------------------------------------

@dataclass(frozen=True)
class Settings:
    """How much the Validator looks at. The defaults are the owner's (spec section 3): at least 4
    samples on every face and one per 36 sq in, 128 directions (the 64 whose viewer is at or above the horizon are
    used: `viewpoints.above_horizon_directions`), a ring of 24 cameras, 1,024 extra (512 used, the same way)
    directions for faces that are gone, probes 1.6 m up. `chunk` is how many samples are cast at a
    time, which bounds memory (the dense `seen` and `front` matrices are chunk x viewpoints)."""
    n_directions: int = 128
    n_cameras: int = 24
    camera_margin: float = 240.0
    n_extra_directions: int = 1024
    min_per_face: int = 4
    area_per_sample: float = 36.0
    eye: float = 63.0
    chunk: int = 1024
    cluster_cell: float = 6.0
    max_sites: int = 200

    def as_dict(self) -> dict:
        return dataclasses.asdict(self)


#: What the surface at a sample's place is in AFTER, as the first of these it fails (0 = it is there).
OK, DELETED, LOOK, UV, SIDE = 0, 1, 2, 3, 4
_PRESENT_NAMES = {DELETED: "deleted", LOOK: "look", UV: "uv", SIDE: "side"}

#: A viewpoint ray that meets a layer this far (along the view) in front of a sample, or less, is on the
#: sample's own surface (`depth_tolerance`); after one it is covered. Rays that meet a layer INSIDE the
#: tolerance look beyond it, at most `_PEEL_MAX` times, a hair past each layer.
_PEEL_MAX = 4
_PEEL_STEP = 1e-3
#: The short cast that asks what is at a sample's depth starts this far outside the tolerance window.
_PRESENT_BACK = 0.02
#: Barycentric slack for "the line passes through this triangle": a hit exactly on an edge counts.
_INSIDE = 1e-9
#: A texel of slack on top of the 1-texel UV tolerance, for float noise in a shift of exactly one.
_TEXEL_SLACK = 1e-9
#: The face grid that finds the faces near a sample's short segment reaches this much beyond the tolerance, in
#: inches: more than the box test's own 1e-6, so a face that test keeps is always offered.
_PRESENT_GRID_SLACK = 1e-5


def _barycentric(positions: np.ndarray, face_v: np.ndarray, q: np.ndarray) -> np.ndarray:
    """(m, 3) float64 barycentric weights of the points `q` (m, 3) in the triangles `face_v` (m, 3)
    of `positions`, taken on the triangle's plane (a point off it is projected). Written with cross
    products, as ratios of areas: the usual dot-product form subtracts two products of squared edge
    lengths and loses all it has on a long thin face (a sliver 1,190 in long and 0.0008 in wide gave
    weights wrong by 3e-4, which is 0.4 in along it and 2.5 texels of a 30 UV unit span)."""
    a, b, c = positions[face_v[:, 0]], positions[face_v[:, 1]], positions[face_v[:, 2]]
    n = np.cross(b - a, c - a)
    nn = (n * n).sum(1)
    ok = nn > 0.0
    safe = np.where(ok, nn, 1.0)
    wb = np.where(ok, (np.cross(q - a, c - a) * n).sum(1) / safe, np.nan)
    wc = np.where(ok, (np.cross(b - a, q - a) * n).sum(1) / safe, np.nan)
    return np.stack([1.0 - wb - wc, wb, wc], axis=1)


def _uv_equal(uv_a: np.ndarray, uv_b: np.ndarray, texel_w: np.ndarray, texel_h: np.ndarray) -> np.ndarray:
    """(m,) bool: the two texture coordinates are the same mod 1, within one texel of the texture
    (`texel_w` x `texel_h` pixels; 0 means no texture, and then nothing shows the UV, so it passes).
    A face without UVs (NaN) matches only another face without."""
    d = uv_a - uv_b
    d = d - np.round(d)                                              # mod 1, into [-0.5, 0.5]
    nan_a, nan_b = np.isnan(uv_a[:, 0]), np.isnan(uv_b[:, 0])
    with np.errstate(invalid="ignore"):
        close = (np.abs(d[:, 0]) * texel_w <= 1.0 + _TEXEL_SLACK) & (np.abs(d[:, 1]) * texel_h <= 1.0 + _TEXEL_SLACK)
    return (texel_w <= 0) | np.where(nan_a | nan_b, nan_a == nan_b, close)


@dataclass
class _Witnesses:
    """One viewpoint per tested sample, and the rays to and from it. `toward` is the unit vector from
    the sample to the viewpoint; `origin` and `dirn` replay the very ray `visibility` used to see the
    sample (stepped off its face toward the viewer), `reach` how far the viewpoint is along it (inf for
    a direction), `col` the column of the viewpoint, `need_front` whether BEFORE saw its front."""
    col: np.ndarray
    need_front: np.ndarray
    toward: np.ndarray
    origin: np.ndarray
    dirn: np.ndarray
    reach: np.ndarray
    is_dir: np.ndarray

    def take(self, which) -> "_Witnesses":
        """The witnesses of some of the samples (`which`: a mask or an index array)."""
        return _Witnesses(self.col[which], self.need_front[which], self.toward[which], self.origin[which],
                          self.dirn[which], self.reach[which], self.is_dir[which])


def _scores(vs: VisibleSet, rows: np.ndarray, points: np.ndarray, normals: np.ndarray) -> np.ndarray:
    """(len(rows), V) |cos| between each sample's normal and its line to every viewpoint: how square the view is."""
    p, n = points[rows], normals[rows]
    n_dir = len(vs.dirs)
    viewpoints = np.vstack([vs.cams, vs.probes])
    abs_cos = np.zeros((len(rows), vs.seen.shape[1]))
    if n_dir:
        abs_cos[:, :n_dir] = np.abs(n @ (-vs.dirs).T)
    if len(viewpoints):
        v = viewpoints[None, :, :] - p[:, None, :]
        dist = np.linalg.norm(v, axis=2)
        with np.errstate(divide="ignore", invalid="ignore"):
            abs_cos[:, n_dir:] = np.abs(np.einsum("nk,nqk->nq", n, v)) / dist
    return abs_cos


def _witnesses(vs: VisibleSet, rows: np.ndarray, points: np.ndarray, normals: np.ndarray,
               scores: np.ndarray | None = None, columns: np.ndarray | None = None):
    """For each sample `rows` of the chunk `vs` was cast for: the best-conditioned viewpoint that sees it
    (the largest |cos| between the line of sight and the face's normal, so the one least edge-on),
    among those that see its FRONT when any does, else among those that see it at all. `columns`, a bool
    mask over the viewpoints, limits who may speak (the probes, say). Returns `(witnesses, sel)`: the
    witnesses of the samples `sel` (indices into `rows`) that an allowed viewpoint sees, and which they are."""
    if scores is None:
        scores = _scores(vs, rows, points, normals)
    seen, front = vs.seen[rows], vs.front[rows]
    if columns is not None:
        seen, front = seen & columns, front & columns
    sel = np.flatnonzero(seen.any(axis=1))
    seen, front, abs_cos = seen[sel], front[sel], scores[sel]
    p, n = points[rows][sel], normals[rows][sel]
    need_front = front.any(axis=1)
    score = np.where(need_front[:, None], np.where(front, abs_cos, -1.0), np.where(seen, abs_cos, -1.0))
    col = score.argmax(axis=1)
    return _witness_rays(vs, p, n, col, need_front), sel


def _witness_rays(vs: VisibleSet, p: np.ndarray, n: np.ndarray, col: np.ndarray, need_front: np.ndarray) -> _Witnesses:
    """The rays from the samples at `p` (normals `n`) to the viewpoints `col` (columns of `vs`), exactly as
    `visibility` cast them in BEFORE: stepped off the face toward the viewer (see `_Witnesses`)."""
    n_dir = len(vs.dirs)
    viewpoints = np.vstack([vs.cams, vs.probes])
    is_dir = col < n_dir
    toward, origin = np.empty_like(p), np.empty_like(p)
    dirn, reach = np.empty_like(p), np.full(len(p), np.inf)
    di = np.flatnonzero(is_dir)
    if len(di):
        t = -vs.dirs[col[di]]
        cos = np.einsum("ij,ij->i", n[di], t)
        origin[di] = p[di] + _side(cos)[:, None] * n[di]
        dirn[di] = toward[di] = t
    pi = np.flatnonzero(~is_dir)
    if len(pi):
        target = viewpoints[col[pi] - n_dir]
        v = target - p[pi]
        dist = np.linalg.norm(v, axis=1)
        cos = np.einsum("ij,ij->i", n[pi], v) / dist
        o = p[pi] + _side(cos)[:, None] * n[pi]
        to = target - o
        r = np.linalg.norm(to, axis=1)
        origin[pi], reach[pi] = o, r
        dirn[pi] = to / np.maximum(r, 1e-9)[:, None]
        toward[pi] = v / dist[:, None]
    return _Witnesses(col=col, need_front=need_front, toward=toward, origin=origin, dirn=dirn, reach=reach,
                      is_dir=is_dir)


#: (sample, viewpoint) lines of sight replayed into AFTER at once by the every-line cover test.
_LINE_PAIRS = 1 << 20


def _covered_on_every_line(judge: "_Judge", vs: VisibleSet, rows: np.ndarray, points: np.ndarray,
                           normals: np.ndarray, scores: np.ndarray, witness: np.ndarray,
                           fills: "_FillSites | None" = None):
    """Job P2-V2 item 3. `(cover, col, blocked_rows, blocked_cols, by_fill, which)` for the samples `rows` of the chunk
    `vs` was cast for: a sample is covered when ANY line of sight that saw it in BEFORE -- every viewpoint, from either
    side -- is blocked in AFTER (`_Judge.blocker`: new geometry more than the depth tolerance in front of it, before
    the viewpoint) and no honest fill takes that line inside its own loop (`_FillSites.excused`, the `fill_site`
    class, E8b-R6); `col` is its best-conditioned such line (the largest `scores`), -1 for the others; then every such
    pair, as indices into `rows` and columns of `vs`. `by_fill`: some line is blocked and every blocked line is taken
    by a fill (`covered_by_fill`); `which`: for those, the fill of the first blocked line a fill face blocks.

    `witness` (len(rows), k): per sample the columns of the lines the Validator asked before every line was (its
    witness and its best probe; -1 for none). Those keep the test along the line alone; every other line also needs
    the blocker beyond the tolerance square to the sample's face (`_Judge.blocker`'s `square`), so that a layer within
    the tolerance of the surface, met by a grazing line, stays an overlay and never becomes a cover."""
    n = len(rows)
    cover, col, best = np.zeros(n, dtype=bool), np.full(n, -1, dtype=np.int64), np.full(n, -np.inf)
    blocked_any, which = np.zeros(n, dtype=bool), np.full(n, -1, dtype=np.int64)
    empty = np.zeros(0, dtype=np.int64)
    if not n or not judge.can_block:
        return cover, col, empty, empty, blocked_any, which
    r_all, c_all = np.nonzero(vs.seen[rows])
    p_rows, n_rows = points[rows], normals[rows]
    out_r, out_c = [], []
    for start in range(0, len(r_all), _LINE_PAIRS):
        r, c = r_all[start:start + _LINE_PAIRS], c_all[start:start + _LINE_PAIRS]
        p = p_rows[r]
        square = ~(witness[r] == c[:, None]).any(axis=1)
        blocked, face, hit = judge.blocker(p, _witness_rays(vs, p, n_rows[r], c, np.zeros(len(r), dtype=bool)), square)
        if not blocked.any():
            continue
        blocked_any[r[blocked]] = True
        if fills is not None:
            bi = np.flatnonzero(blocked)
            by_a_fill = bi[fills.fill_of[face[bi]] >= 0]
            for i in by_a_fill.tolist():                          # the first line a fill face blocks names the fill
                if which[r[i]] < 0:
                    which[r[i]] = fills.fill_of[face[i]]
            blocked[bi[fills.excused(face[bi], hit[bi])]] = False
            if not blocked.any():
                continue
        rb, cb = r[blocked], c[blocked]
        out_r.append(rb)
        out_c.append(cb)
        s = scores[rb, cb]
        order = np.lexsort((cb, -s, rb))
        first = order[np.unique(rb[order], return_index=True)[1]]
        better = s[first] > best[rb[first]]
        best[rb[first][better]], col[rb[first][better]] = s[first][better], cb[first][better]
        cover[rb] = True
    by_fill = blocked_any & ~cover
    which[~by_fill] = -1
    if not out_r:
        return cover, col, empty, empty, by_fill, which
    return cover, col, np.concatenate(out_r), np.concatenate(out_c), by_fill, which


class _Judge:
    """What AFTER shows along a sample's line of sight, asked of the viewpoint that saw the sample in BEFORE.

    Two casts, both short, both started where float32 noise cannot matter:

    * COVERED. The same ray `visibility` cast in BEFORE (same origin, same direction), into AFTER's NEW
      GEOMETRY only (`blockable`: `changed_faces`). A first hit more than the tolerance in front of the sample,
      before the viewpoint, covers it (on the lines beyond the witness's, also more than the tolerance square to
      the sample's face: see `blocker`); a layer within the tolerance is the sample's own depth (or an overlay),
      and the ray looks beyond it. A face AFTER kept from BEFORE lies where it lay and met none of the line BEFORE saw clear,
      so only new geometry can block it. Casting into the whole of AFTER let the float32 caster newly block a line
      through a shared vertex or edge that BEFORE's caster let through: its verdict on such a line depends on the
      whole mesh it was built from (measured both ways: trimesh scales each mesh by its own size before rounding to
      float32; and on CHTM 5th, with the very same frame, the two Embree trees still disagreed on face 10553's
      corner -- job P2-V2 item 4, P2-E3 concern 3). So an AFTER that is a subset of BEFORE's faces covers nothing,
      by construction.
    * PRESENT. A ray from just outside the tolerance window, on the viewer's side, toward the sample.
      The first hit, if it is in the window, is judged; when it is not the whole story (another look,
      a coincident layer, nothing there), every face the short segment crosses is looked up by hand
      in float64, and the sample is met if ANY of them has its look, its UV and (when BEFORE saw its
      front) shows its front. Two layers in one place are both drawn in Unity, so either may answer.
    """

    def __init__(self, after: MeshData, caster, look_after: np.ndarray, tol: float, blockable=None):
        self.after, self.caster, self.look_a, self.tol = after, caster, look_after, tol
        self.n_faces = after.n_faces
        # the faces that may block a line: AFTER's new geometry (all of AFTER when not said)
        self.block_ids = (np.arange(after.n_faces, dtype=np.int64) if blockable is None
                          else np.flatnonzero(np.asarray(blockable, dtype=bool)).astype(np.int64))
        self.block_caster = None
        if len(self.block_ids):
            self.block_caster = (caster if len(self.block_ids) == after.n_faces else
                                 build_caster(dataclasses.replace(after, face_v=after.face_v[self.block_ids])))
        if self.n_faces:
            pos, fv = after.positions, after.face_v
            self.a0 = pos[fv[:, 0]]
            self.raw = np.cross(pos[fv[:, 1]] - self.a0, pos[fv[:, 2]] - self.a0)
            tri = pos[fv]
            self.face_lo, self.face_hi = tri.min(axis=1), tri.max(axis=1)
        self._grid = None                                  # `_by_hand`'s face grid, built when first asked

    # -- covered ---------------------------------------------------------------------------------
    @property
    def can_block(self) -> bool:
        """Some face of AFTER could block a line of sight: AFTER has new geometry."""
        return self.block_caster is not None

    def covered(self, p, w: _Witnesses) -> np.ndarray:
        return self.blocker(p, w)[0]

    def blocker(self, p, w: _Witnesses, square=None):
        """`(covered, face, point)`: `covered` as `covered` gives it, and for each covered sample the AFTER face that
        covers it and where the line of sight meets it (-1 and zeros for the others).

        `square` (bool per line, job P2-V2): for those lines a face covers only when it lies beyond the tolerance BOTH
        along the line and square to the sample's own face. A layer within the tolerance of the sample's surface is its
        own depth (or an overlay, `_Overlay`), however grazing the line that meets it. The witness lines -- the ones the
        Validator asked before every line was asked -- keep the test along the line alone, so nothing they found
        covered is excused."""
        n = len(p)
        covered = np.zeros(n, dtype=bool)
        face = np.full(n, -1, dtype=np.int64)
        point = np.zeros((n, 3))
        if self.block_caster is None or not n:
            return covered, face, point
        cur, travelled = w.origin.copy(), np.zeros(n)
        active = np.arange(n)
        for _ in range(_PEEL_MAX + 1):
            if not len(active):
                break
            tri, t = self.block_caster.first_hit(cur[active], w.dirn[active])
            hit = tri >= 0
            tri = np.where(hit, self.block_ids[np.maximum(tri, 0)], -1)
            total = travelled[active] + np.where(hit, t, 0.0)
            blocks = hit & (w.is_dir[active] | (total < w.reach[active] - EPS_ORIGIN))
            q = cur[active] + np.where(hit, t, 0.0)[:, None] * w.dirn[active]
            in_front = np.einsum("ij,ij->i", q - p[active], w.toward[active])
            beyond = blocks & (in_front > self.tol)
            if square is not None:
                off = (w.origin[active] - p[active]) / EPS_ORIGIN           # the sample's normal, toward the viewer
                deep = np.einsum("ij,ij->i", q - p[active], off) > self.tol
                beyond &= ~square[active] | deep
            covered[active[beyond]] = True
            face[active[beyond]] = tri[beyond]
            point[active[beyond]] = q[beyond]
            within = blocks & ~beyond                     # a layer inside the tolerance: look past it
            nxt = active[within]
            cur[nxt] = q[within] + w.dirn[nxt] * _PEEL_STEP
            travelled[nxt] = total[within] + _PEEL_STEP
            active = nxt
        return covered, face, point

    # -- present ---------------------------------------------------------------------------------
    def _flags(self, start, u, t_b, tri, rows, look_b, uv_b, tex_w, tex_h, need_front, inside):
        """For the candidate faces `tri` met by the rays `rows` (`start`, `u`): is the face's plane within the
        tolerance of the sample's depth `t_b` along the ray, has it the sample's look, its UV, and does
        the ray see its front. `inside` demands that the point lies in the triangle (a hand-made
        candidate); a face Embree returned was hit by construction."""
        s, d = start[rows], u[rows]
        n = self.raw[tri]
        den = np.einsum("ij,ij->i", d, n)
        num = np.einsum("ij,ij->i", self.a0[tri] - s, n)
        ok = den != 0.0
        t = np.where(ok, num / np.where(ok, den, 1.0), np.inf)
        window = ok & (np.abs(t - t_b) <= self.tol)
        q = s + np.where(np.isfinite(t), t, 0.0)[:, None] * d
        bary = _barycentric(self.after.positions, self.after.face_v[tri], q)
        if inside:
            window &= (bary >= -_INSIDE).all(axis=1)
        look_ok = window & (self.look_a[tri] == look_b[rows])
        uv_ok = _uv_equal(uv_at(self.after, tri, bary), uv_b[rows], tex_w[rows], tex_h[rows])
        side_ok = ~need_front[rows] | (den < 0.0)
        return window, look_ok, uv_ok, side_ok

    def _by_hand(self, start, u, t_b, rows, look_b, uv_b, tex_w, tex_h, need_front):
        """The same flags for EVERY face the short segment of each of `rows` crosses, found with a
        bounding-box prefilter and an exact float64 test, and reduced to a status per row.

        The segment lies within the tolerance of its middle, so every face whose box it meets is registered, in a
        `_FaceGrid` with that reach, in the middle's own cell: the grid offers those faces (and some others), and the
        box test then keeps exactly the pairs a test against every face would keep (job P2-V2: the floor asks this
        of every pixel of a removed face, where a test against every face cost pixels x faces)."""
        m = len(rows)
        status = np.full(m, DELETED, dtype=np.int8)
        s0 = start[rows] + u[rows] * (t_b - self.tol)
        s1 = start[rows] + u[rows] * (t_b + self.tol)
        lo, hi = np.minimum(s0, s1) - 1e-6, np.maximum(s0, s1) + 1e-6
        if self._grid is None:
            self._grid = _FaceGrid(self.after.positions, self.after.face_v, np.arange(self.n_faces),
                                   self.tol + _PRESENT_GRID_SLACK)
        r, f = self._grid.lookup(start[rows] + u[rows] * t_b)
        near = ((lo[r] <= self.face_hi[f]) & (hi[r] >= self.face_lo[f])).all(axis=1)
        r, f = r[near], f[near]
        if not len(r):
            return status
        window, look_ok, uv_ok, side_ok = self._flags(start, u, t_b, f, rows[r], look_b, uv_b, tex_w, tex_h,
                                                      need_front, inside=True)
        count = lambda flag: np.bincount(r, weights=flag, minlength=m) > 0
        status[count(window)] = LOOK
        status[count(look_ok)] = UV
        status[count(look_ok & uv_ok)] = SIDE
        status[count(look_ok & uv_ok & side_ok)] = OK
        return status

    def present(self, p, w: _Witnesses, look_b, uv_b, tex_w, tex_h) -> np.ndarray:
        n = len(p)
        status = np.full(n, DELETED, dtype=np.int8)
        if not self.n_faces or not n:
            return status
        t_b = self.tol + _PRESENT_BACK
        start, u = p + w.toward * t_b, -w.toward
        tri, _ = self.caster.first_hit(start, u)
        hit = np.flatnonzero(tri >= 0)
        done = np.zeros(n, dtype=bool)
        if len(hit):
            window, look_ok, uv_ok, side_ok = self._flags(start, u, t_b, tri[hit], hit, look_b, uv_b, tex_w, tex_h,
                                                          w.need_front, inside=False)
            fine = window & look_ok & uv_ok & side_ok
            status[hit[fine]] = OK
            done[hit[fine]] = True
        todo = np.flatnonzero(~done)
        if len(todo):
            status[todo] = self._by_hand(start, u, t_b, todo, look_b, uv_b, tex_w, tex_h, w.need_front)
        return status


# ---------------------------------------------------------------------------------------------
# New faces over a sample: a face of a look (or a UV) that the place did not have, on it or in front of it
# ---------------------------------------------------------------------------------------------

#: Cells of the grid over faces, in inches. A face is registered in every cell its box, grown by the reach, touches.
_GRID_CELL = 6.0
#: A face whose grown box would fill more cells than this is not registered: it is offered to every point.
_GRID_CAP = 2000
#: How far BEHIND a sample's own surface another layer still z-fights with it, in inches: the very number
#: `visibility` uses for "two layers this close are both drawn".
_ZFIGHT = EPS_ORIGIN
#: Tested samples looked at in one numpy block by the overlay pass.
_OVERLAY_BLOCK = 16384


class _FaceGrid:
    """A uniform grid over some faces of a mesh, to ask "which faces could cross a short segment near this
    point?" without testing every face. Each face (`faces`, indices into `face_v`) is registered in every
    `cell`-inch cell its bounding box, grown by `reach` on every side, touches; so every face that passes within
    `reach` of a point is registered in the point's own cell, and `lookup` reads one cell per point. A face whose
    box would fill more than `cap` cells (a floor slab a thousand inches wide) is kept apart and offered to every
    point instead. `lookup` gives candidates, a superset of the faces within reach: the caller tests them."""

    def __init__(self, positions: np.ndarray, face_v: np.ndarray, faces: np.ndarray, reach: float,
                 cell: float = _GRID_CELL, cap: int = _GRID_CAP):
        faces = np.asarray(faces, dtype=np.int64)
        self.cell = float(cell)
        self.origin = np.zeros(3)
        self.dims = np.ones(3, dtype=np.int64)
        self.keys = self.first = self.count = self.face_sorted = np.zeros(0, dtype=np.int64)
        self.big, self.big_lo, self.big_hi = np.zeros(0, dtype=np.int64), np.zeros((0, 3)), np.zeros((0, 3))
        if not len(faces):
            return
        tri = positions[face_v[faces]]
        lo, hi = tri.min(axis=1) - reach, tri.max(axis=1) + reach
        self.origin = lo.min(axis=0)
        a = np.floor((lo - self.origin) / self.cell).astype(np.int64)
        b = np.floor((hi - self.origin) / self.cell).astype(np.int64)
        n = b - a + 1
        count = n.prod(axis=1)
        small = count <= cap
        self.big, self.big_lo, self.big_hi = faces[~small], lo[~small], hi[~small]
        faces, a, n, count = faces[small], a[small], n[small], count[small]
        if not len(faces):
            return
        self.dims = b[small].max(axis=0) + 1
        owner = np.repeat(np.arange(len(faces)), count)
        local = np.arange(int(count.sum())) - np.repeat(np.cumsum(count) - count, count)
        nx, ny = n[owner, 0], n[owner, 1]
        cx = a[owner, 0] + local % nx
        cy = a[owner, 1] + (local // nx) % ny
        cz = a[owner, 2] + local // (nx * ny)
        keys = (cx * self.dims[1] + cy) * self.dims[2] + cz
        order = np.argsort(keys, kind="stable")
        self.keys, self.first, self.count = np.unique(keys[order], return_index=True, return_counts=True)
        self.face_sorted = faces[owner[order]]

    def lookup(self, points: np.ndarray) -> tuple[np.ndarray, np.ndarray]:
        """`(rows, faces)`: for each point (`rows` indexes `points`) the candidate faces, each pair once."""
        points = np.asarray(points, dtype=np.float64).reshape(-1, 3)
        rows_out, faces_out = [np.zeros(0, dtype=np.int64)], [np.zeros(0, dtype=np.int64)]
        if len(self.keys) and len(points):
            cell = np.floor((points - self.origin) / self.cell).astype(np.int64)
            inside = np.flatnonzero(((cell >= 0) & (cell < self.dims)).all(axis=1))
            key = (cell[inside, 0] * self.dims[1] + cell[inside, 1]) * self.dims[2] + cell[inside, 2]
            at = np.minimum(np.searchsorted(self.keys, key), len(self.keys) - 1)
            hit = self.keys[at] == key
            inside, at = inside[hit], at[hit]
            cnt = self.count[at]
            offset = (np.arange(int(cnt.sum())) - np.repeat(np.cumsum(cnt) - cnt, cnt)
                      + np.repeat(self.first[at], cnt))
            rows_out.append(np.repeat(inside, cnt))
            faces_out.append(self.face_sorted[offset])
        if len(self.big) and len(points):
            block = max(1, 4_000_000 // len(self.big))
            for k in range(0, len(points), block):
                near = ((points[k:k + block, None, :] >= self.big_lo[None])
                        & (points[k:k + block, None, :] <= self.big_hi[None])).all(axis=2)
                r, f = np.nonzero(near)
                rows_out.append(r + k)
                faces_out.append(self.big[f])
        return np.concatenate(rows_out), np.concatenate(faces_out)


def _crossings(positions: np.ndarray, face_v: np.ndarray, points: np.ndarray, toward: np.ndarray,
               rows: np.ndarray, faces: np.ndarray, x_lo: float, x_hi: float):
    """Of the pairs (point `rows[i]`, face `faces[i]`): which have the face crossing the segment
    `point + x toward[row]` for x from `x_lo` to `x_hi` (x > 0 is toward the viewer), in float64, with the
    crossing inside the triangle. Returns `(inside, x, bary)` for every pair."""
    face_rows = face_v[faces]
    a = positions[face_rows[:, 0]]
    n = np.cross(positions[face_rows[:, 1]] - a, positions[face_rows[:, 2]] - a)
    p, w = points[rows], toward[rows]
    den = (w * n).sum(1)
    ok = den != 0.0
    x = np.where(ok, ((a - p) * n).sum(1) / np.where(ok, den, 1.0), np.inf)
    hit = ok & (x >= x_lo) & (x <= x_hi)
    bary = _barycentric(positions, face_rows, p + np.where(hit, x, 0.0)[:, None] * w)
    return hit & (bary >= -_INSIDE).all(axis=1), x, bary


class _Overlay:
    """Which samples have a NEW face of AFTER lying on them or in front of them, within the depth tolerance, that the
    place did not already have.

    Only a new face can be one: a face of AFTER that BEFORE has too (the same fingerprint: place, winding, look, UV)
    lies where it lay, so it is in BEFORE's window along the same line of sight. So the new faces (`new_faces`)
    are put in a grid, and for each sample the ones that cross its line of sight from `_ZFIGHT` behind it to the
    tolerance in front of it are found, exactly, in float64. Such a face is EXPLAINED when the sample's own face has
    its look and UV there, or else when some face of BEFORE's window along that line has them (a flicker pair's
    other layer, an identical copy). A face nothing explains is a layer the place did not have: it hides the
    sample's texture or z-fights with it. A sample no new face crosses costs one grid lookup; an identity run has
    no new face at all and never gets here."""

    def __init__(self, before: MeshData, after: MeshData, new_faces: np.ndarray, look_before: np.ndarray,
                 look_after: np.ndarray, tex_w: np.ndarray, tex_h: np.ndarray, tol: float):
        self.before, self.after, self.look_b, self.look_a = before, after, look_before, look_after
        self.tex_w, self.tex_h, self.tol = tex_w, tex_h, tol
        self.reach = tol + 1e-6
        self.grid_new = _FaceGrid(after.positions, after.face_v, np.flatnonzero(new_faces), self.reach)
        self._grid_before = None

    def _explained_by_before(self, points, toward, rows, look, uv, tw, th) -> np.ndarray:
        """For each pair (sample `rows[i]`, new face with `look[i]`, `uv[i]`): does a face of BEFORE's window along
        that sample's line of sight have that look and a UV within a texel?"""
        if self._grid_before is None:
            self._grid_before = _FaceGrid(self.before.positions, self.before.face_v,
                                          np.arange(self.before.n_faces), self.reach)
        sample_rows = np.unique(rows)
        r, f = self._grid_before.lookup(points[sample_rows])
        r = sample_rows[r]
        inside, _, bary = _crossings(self.before.positions, self.before.face_v, points, toward, r, f,
                                     -_ZFIGHT, self.tol)
        r, f, bary = r[inside], f[inside], bary[inside]
        look_f, uv_f = self.look_b[f], uv_at(self.before, f, bary)
        order = np.argsort(r, kind="stable")
        r, look_f, uv_f = r[order], look_f[order], uv_f[order]
        lo, hi = np.searchsorted(r, rows, side="left"), np.searchsorted(r, rows, side="right")
        cnt = hi - lo
        pair = np.repeat(np.arange(len(rows)), cnt)
        other = np.arange(int(cnt.sum())) - np.repeat(np.cumsum(cnt) - cnt, cnt) + np.repeat(lo, cnt)
        same = (look_f[other] == look[pair]) & _uv_equal(uv_f[other], uv[pair], tw[pair], th[pair])
        return np.bincount(pair, weights=same, minlength=len(rows)) > 0

    def overlaid(self, points: np.ndarray, toward: np.ndarray, own_look: np.ndarray, own_uv: np.ndarray) -> np.ndarray:
        """(len(points),) bool for samples at `points` seen along `-toward`, whose own face has `own_look` and `own_uv`."""
        result = np.zeros(len(points), dtype=bool)
        rows, faces = self.grid_new.lookup(points)
        if not len(rows):
            return result
        inside, _, bary = _crossings(self.after.positions, self.after.face_v, points, toward, rows, faces,
                                     -_ZFIGHT, self.tol)
        rows, faces, bary = rows[inside], faces[inside], bary[inside]
        if not len(rows):
            return result
        look = self.look_a[faces]
        uv = uv_at(self.after, faces, bary)
        tw, th = self.tex_w[look], self.tex_h[look]
        left = np.flatnonzero(~((look == own_look[rows]) & _uv_equal(uv, own_uv[rows], tw, th)))
        if len(left):
            explained = self._explained_by_before(points, toward, rows[left], look[left], uv[left], tw[left], th[left])
            result[rows[left][~explained]] = True
        return result


# ---------------------------------------------------------------------------------------------
# The one named class of allowed change: fill_site (job P2-E8b, ruling E8b-R6)
# ---------------------------------------------------------------------------------------------

@dataclass(frozen=True, eq=False)
class FillSite:
    """One flat fill the edit log marks as E8's (AGENTS.md section 4, the owner's narrow flat fill exception):
    `faces`, its face ids in AFTER; `loop`, the (n, 3) points of the hole's border it fills, in the model's own
    coordinates and in loop order."""
    faces: np.ndarray
    loop: np.ndarray


#: (sample, viewpoint) lines of sight replayed at once by the fill_site class.
_FILL_PAIRS = 200_000
#: The owner's narrow flat fill, re-measured here and never taken from the engine (AGENTS.md section 6): the hole's
#: largest inscribed circle is at most this many inches across (E8b-R3, one block), and every face round it is
#: within this many degrees of the loop's plane, up to sign (E8b-R2).
FILL_MAX_DIAMETER = 39.37
FILL_NORMAL_TOL_DEG = 1.0
#: How close `polylabel` gets to the inscribed circle's centre (in); counted AGAINST the hole: the diameter it finds
#: plus twice this must stay within the cap.
_FILL_POLYLABEL_TOL = 0.005


def _fill_shape_refusal(before: MeshData, neighbours, loop: np.ndarray, c: np.ndarray, n: np.ndarray,
                        poly: np.ndarray, tol: float) -> str | None:
    """Why a marked fill is not the owner's narrow FLAT fill, re-measured on BEFORE (None when it is): a neighbour
    more than `FILL_NORMAL_TOL_DEG` off the loop's plane, or with a corner more than `tol` out of it (E8b-R2); a loop
    that crosses itself; or a hole whose largest inscribed circle, plus polylabel's own tolerance on both sides, is
    wider than `FILL_MAX_DIAMETER` (E8b-R3)."""
    from shapely import Polygon
    from shapely.ops import polylabel

    tri = before.positions[before.face_v[np.asarray(neighbours, dtype=np.int64)]]
    normal = np.cross(tri[:, 1] - tri[:, 0], tri[:, 2] - tri[:, 0])
    length = np.linalg.norm(normal, axis=1)
    if (length <= 0.0).any():
        return "a face round the hole has no area, so no normal to compare (E8b-R2)"
    angle = float(np.degrees(np.arccos(np.clip(np.abs((normal / length[:, None]) @ n), 0.0, 1.0))).max())
    offset = float(np.abs((tri - c) @ n).max())
    if angle > FILL_NORMAL_TOL_DEG or offset > tol:
        return (f"the faces round the hole are not coplanar with it: {angle:.3f} deg and {offset:.4f} in off its "
                f"plane (at most {FILL_NORMAL_TOL_DEG} deg and {tol:.4f} in; E8b-R2)")
    polygon = Polygon(poly)
    if not polygon.is_valid:
        return "the loop crosses itself in its plane (E8b-R1)"
    diameter = 2.0 * float(polygon.exterior.distance(polylabel(polygon, tolerance=_FILL_POLYLABEL_TOL)))
    if diameter + 2.0 * _FILL_POLYLABEL_TOL > FILL_MAX_DIAMETER:
        return (f"the hole's largest inscribed circle is {diameter:.2f} in across (with polylabel's tolerance at most "
                f"{FILL_MAX_DIAMETER} in; E8b-R3)")
    return None


def _in_polygon(poly: np.ndarray, xy: np.ndarray, tol: float) -> np.ndarray:
    """(k,) bool: the points `xy` lie inside the polygon `poly` (m, 2) (even-odd), or within `tol` of its border."""
    if not len(xy):
        return np.zeros(0, dtype=bool)
    a, b = poly, np.roll(poly, -1, axis=0)
    x, y = xy[:, 0:1], xy[:, 1:2]
    straddle = (a[None, :, 1] > y) != (b[None, :, 1] > y)
    dy = np.where(b[:, 1] == a[:, 1], 1.0, b[:, 1] - a[:, 1])
    x_cross = a[None, :, 0] + (y - a[None, :, 1]) * (b[:, 0] - a[:, 0])[None] / dy[None]
    inside = (straddle & (x < x_cross)).sum(axis=1) % 2 == 1
    ab = b - a
    ab2 = np.maximum((ab * ab).sum(axis=1), 1e-300)
    t = np.clip(((xy[:, None, :] - a[None]) * ab[None]).sum(axis=2) / ab2[None], 0.0, 1.0)
    near = np.linalg.norm(a[None] + t[..., None] * ab[None] - xy[:, None, :], axis=2).min(axis=1) <= tol
    return inside | near


class _FillSites:
    """The `fill_site` class (ruling E8b-R6). A BEFORE sample the cover test found covered counts as
    `covered_by_fill` instead only when EVERY line of sight that saw it in BEFORE and is blocked in AFTER ends on a
    face of a marked fill, at a point inside that fill's own loop (in the loop's plane, within the depth tolerance,
    and inside its polygon or within the tolerance of its border); a line that still reaches the sample is no loss.

    The mark is checked, never trusted: a fill is HONEST only when every edge of its loop is an edge of exactly one
    face of BEFORE (a hole's border, open in BEFORE), those faces have one look, every face of the fill has that
    look, and the fill is the owner's narrow FLAT fill, re-measured here (`_fill_shape_refusal`): every face round the
    hole coplanar with it within 1 degree (E8b-R2), and the hole at most 39.37 in across its inscribed circle
    (E8b-R3). A dishonest fill explains nothing: what it covers stays `covered`."""

    def __init__(self, fills, before: MeshData, after: MeshData, centre: np.ndarray, look_b: np.ndarray,
                 look_a: np.ndarray, step: float, tol: float):
        self.tol = tol
        self.fill_of = np.full(after.n_faces, -1, dtype=np.int64)
        self.sites = []
        q = step if step > 0.0 else 1e-6
        tri_b = before.positions[before.face_v] if before.n_faces else np.zeros((0, 3, 3))
        lo_b, hi_b = tri_b.min(axis=1), tri_b.max(axis=1)
        for k, fill in enumerate(fills):
            faces = np.unique(np.asarray(fill.faces, dtype=np.int64).reshape(-1))
            loop = np.asarray(fill.loop, dtype=np.float64).reshape(-1, 3)
            if not len(faces) or faces.min() < 0 or faces.max() >= after.n_faces:
                raise ValueError(f"fill {k}: its faces must be AFTER face ids in 0..{after.n_faces - 1}")
            if len(loop) < 3 or not np.isfinite(loop).all():
                raise ValueError(f"fill {k}: its loop needs at least 3 finite points")
            if (self.fill_of[faces] >= 0).any():
                raise ValueError(f"fill {k}: a face belongs to two fills")
            self.fill_of[faces] = k
            loop = loop - centre
            c = loop.mean(axis=0)
            _u, _s, vt = np.linalg.svd(loop - c, full_matrices=False)
            n = vt[2] / np.linalg.norm(vt[2])
            e1 = np.cross(n, [1.0, 0.0, 0.0] if abs(n[0]) < 0.9 else [0.0, 1.0, 0.0])
            e1 /= np.linalg.norm(e1)
            e2 = np.cross(n, e1)
            site = {"faces": faces, "c": c, "n": n, "e": np.stack([e1, e2]),
                    "poly": (loop - c) @ np.stack([e1, e2]).T, "honest": True, "why": None, "neighbours": []}
            # honest? every loop edge an edge of exactly one BEFORE face; one look round the hole; the fill in it
            near = np.flatnonzero(((lo_b <= loop.max(axis=0) + q) & (hi_b >= loop.min(axis=0) - q)).all(axis=1))
            snap = lambda p: tuple(np.round(p / q).astype(np.int64).tolist())
            edge_faces: dict = {}
            for f in near.tolist():
                corners = [snap(p) for p in before.positions[before.face_v[f]]]
                for i in range(3):
                    key = tuple(sorted((corners[i], corners[(i + 1) % 3])))
                    edge_faces.setdefault(key, []).append(f)
            neighbours = []
            for i in range(len(loop)):
                key = tuple(sorted((snap(loop[i]), snap(loop[(i + 1) % len(loop)]))))
                owners = edge_faces.get(key, [])
                if len(owners) != 1:
                    site["honest"], site["why"] = False, (f"loop edge {i} is an edge of {len(owners)} BEFORE faces, "
                                                          f"not of exactly one: not an open border of BEFORE")
                    break
                neighbours.append(owners[0])
            if site["honest"]:
                site["neighbours"] = sorted(set(neighbours))
                around = np.unique(look_b[neighbours])
                if len(around) != 1:
                    site["honest"], site["why"] = False, f"the hole's border faces have {len(around)} looks"
                elif (look_a[faces] != around[0]).any():
                    site["honest"], site["why"] = False, "the fill is in another look than its neighbours"
            if site["honest"]:
                site["why"] = _fill_shape_refusal(before, site["neighbours"], loop, c, n, site["poly"], tol)
                site["honest"] = site["why"] is None
            self.sites.append(site)

    def excused(self, face: np.ndarray, hit: np.ndarray) -> np.ndarray:
        """(k,) bool, for k blocked lines of sight: the AFTER face `face` that blocks each belongs to an HONEST fill,
        and the line meets it at `hit` inside that fill's own loop (in the loop's plane within the depth tolerance, and
        inside its polygon or within the tolerance of its border). The one test the class makes of a line."""
        face = np.asarray(face, dtype=np.int64)
        ok = np.zeros(len(face), dtype=bool)
        if not len(face):
            return ok
        fill = self.fill_of[face]
        for k in np.unique(fill[fill >= 0]).tolist():
            site = self.sites[k]
            if not site["honest"]:
                continue
            mine = np.flatnonzero(fill == k)
            d = hit[mine] - site["c"]
            ok[mine] = (np.abs(d @ site["n"]) <= self.tol) & _in_polygon(site["poly"], d @ site["e"].T, self.tol)
        return ok


# ---------------------------------------------------------------------------------------------
# The owner's floor (job P2-V2): removed and covered faces, measured in pixels
# ---------------------------------------------------------------------------------------------

#: What a pixel of a removed or covered face can have become in AFTER (V2-R2, V2-R3): the `present` codes that lose
#: it, as check 3 has always read them -- nothing at that depth, or another look there. A UV moved under the same look
#: is check 1's (`uv`): the surface is neither removed nor covered.
_GONE = (DELETED, LOOK)
_GONE_NAMES = {DELETED: "deleted", LOOK: "replaced"}


def floor_views(dirs: np.ndarray, extra_dirs: np.ndarray, cams: np.ndarray, probes: np.ndarray, centre: np.ndarray):
    """`(views, labels)`: every Validator viewpoint as a `floor.Viewpoint` in the Validator's frame, in the order the
    floor numbers them -- the standard directions, the extra directions, the cameras, the probes -- and for each a
    JSON-able label (`kind`, `index` within its kind, `at`: the look direction, or the position in the model's own
    coordinates)."""
    views, labels = [], []
    for kind, block, shift in (("direction", dirs, None), ("extra direction", extra_dirs, None),
                               ("camera", cams, centre), ("probe", probes, centre)):
        for k, at in enumerate(np.asarray(block, dtype=np.float64).reshape(-1, 3)):
            if shift is None:
                views.append(Viewpoint.direction(at))
                where = views[-1].at
            else:
                views.append(Viewpoint.point(at))
                where = at + shift
            labels.append({"kind": kind, "index": k, "at": [round(float(x), 4) for x in where]})
    return views, labels


class _Floor:
    """The owner's floor (AGENTS.md section 5, 2026-10-10), judged on the faces a lattice finds (job P2-V2).

    A CANDIDATE is a (BEFORE face, viewpoint) pair: a removed face (its fingerprint is gone from AFTER) and every
    viewpoint that sees a point of its area-scaled lattice (`floor.floor_lattice`), from either side; a covered face and
    every viewpoint whose line is blocked (see `validate`). Each pair is MEASURED (`measure`): the face's pixels from that
    viewpoint at 0.02 in/px (`floor.face_pixels`, nearest-visible in BEFORE), and of those the LOST ones, each judged
    along its own line of sight exactly as a sample is:

    * COVERED: the line from the pixel's point (stepped off the face toward the viewer) is blocked in AFTER by a face
      more than the depth tolerance in front (`_Judge.blocker`), unless an honest fill takes it inside its own loop
      (the `fill_site` class, `_FillSites.excused`);
    * GONE: AFTER no longer shows, at that depth, a surface in the pixel's look (`_Judge.present` says deleted or
      replaced). Where AFTER still shows the same look there, nothing was removed or covered (ruling V2-R3); a UV that
      moved is check 1's `uv`, as it always was.

    A face FAILS when one viewpoint shows more than `VISIBLE_FLOOR_PX` lost pixels; counts are never summed over
    viewpoints (V2-R1). A face's viewpoints are measured in order of how many lattice points (or sample lines) each
    saw, and the first above the floor ends the face's measure."""

    def __init__(self, before: MeshData, judge: "_Judge", fills, look_b: np.ndarray, tex_w: np.ndarray,
                 tex_h: np.ndarray, caster_b, views: list, labels: list, normals_b: np.ndarray, centre: np.ndarray):
        self.b, self.judge, self.fills = before, judge, fills
        self.look_b, self.tex_w, self.tex_h = look_b, tex_w, tex_h
        self.caster_b, self.views, self.labels, self.normals = caster_b, views, labels, normals_b
        self.centre = centre

    def lattice_seen(self, faces: np.ndarray, dirs: np.ndarray, cams: np.ndarray, probes: np.ndarray):
        """`(lost, seen_faces, lattice size)` for `faces`, cast against every viewpoint (`dirs` here are the standard
        then the extra directions, so the columns are the floor's own): `lost` is `{face: {view column: lattice points
        it sees that are lost in AFTER}}` (each seen line judged as a pixel is, `_lost_lines`), `seen_faces` how many
        faces some viewpoint sees a point of at all. A face whose seen points AFTER all still shows in their look
        (re-wound, re-cut, a copy dropped) lost nothing there (V2-R3) and is not measured from that viewpoint."""
        lattice = floor_lattice(self.b, faces)
        seen: dict = {}
        seen_faces: set = set()
        n_views = len(dirs) + len(cams) + len(probes)
        step = max(1, 4_000_000 // max(n_views, 1))
        for start in range(0, len(lattice), step):
            part = slice(start, min(start + step, len(lattice)))
            sub = Samples(points=lattice.points[part], face=lattice.face[part], bary=lattice.bary[part])
            vs = visible_samples(self.b, sub, dirs, cams, probes, self.caster_b)
            r, col = np.nonzero(vs.seen)
            if not len(r):
                continue
            seen_faces.update(np.unique(sub.face[r]).tolist())
            p, faces_r = sub.points[r], sub.face[r]
            w = _witness_rays(vs, p, self.normals[faces_r], col, vs.front[r, col])
            lost = self._lost_lines(faces_r, p, w, sub.bary[r])[0]
            r, col = r[lost], col[lost]
            if not len(r):
                continue
            keys, counts = np.unique(sub.face[r] * n_views + col, return_counts=True)
            for key, count in zip(keys.tolist(), counts.tolist()):
                per = seen.setdefault(key // n_views, {})
                per[key % n_views] = per.get(key % n_views, 0) + count
        return seen, len(seen_faces), len(lattice)

    def cover_seen(self, after: MeshData, new_faces: np.ndarray, dirs: np.ndarray, cams: np.ndarray,
                   probes: np.ndarray, tol: float, n_extra: int = 0) -> tuple[dict, int]:
        """`({BEFORE face: {view column: lattice points}}, lattice size)`: the BEFORE faces the NEW faces of AFTER
        (`new_faces`, ids of `after`) could cover, found by the new faces' own lattice (`floor.floor_lattice`). For
        every lattice point `q` and every viewpoint, BEFORE is cast along the viewpoint's line through `q`, from the
        viewer: when the first face it meets lies more than `tol` beyond `q`, along the line and square to itself, that
        face was nearest-visible there in BEFORE and a new face now stands in front of it. A line within `MIN_COS` of
        a new face's plane is skipped. The viewpoints are the standard ones, as for every cover (`dirs`: the standard
        directions; the camera and probe columns follow the `n_extra` extra directions, as the floor numbers them):
        the extra directions are cast only for faces that are gone."""
        lattice = floor_lattice(after, new_faces)
        seen: dict = {}
        if not len(lattice):
            return seen, 0
        normals_a = face_normals(after)
        lo_b, hi_b = used_bbox(self.b)
        lo_a, hi_a = used_bbox(after)
        far = float(np.linalg.norm(np.maximum(hi_b, hi_a) - np.minimum(lo_b, lo_a))) + 1.0
        eyes = np.vstack([np.asarray(cams, float).reshape(-1, 3), np.asarray(probes, float).reshape(-1, 3)])
        n_dirs = len(dirs)
        n_views = n_dirs + n_extra + len(eyes)
        step = max(1, (1 << 21) // max(n_dirs + len(eyes), 1))
        for start in range(0, len(lattice), step):
            q = lattice.points[start:start + step]
            nq = normals_a[lattice.face[start:start + step]]
            m = len(q)
            parts = []
            if n_dirs:
                d = np.broadcast_to(dirs[None], (m, n_dirs, 3)).reshape(-1, 3)
                origin = (q[:, None, :] - far * dirs[None]).reshape(-1, 3)
                parts.append((origin, d, np.full(m * n_dirs, far), np.tile(np.arange(n_dirs), m),
                              np.repeat(np.arange(m), n_dirs)))
            if len(eyes):
                v = (q[:, None, :] - eyes[None]).reshape(-1, 3)
                dist = np.linalg.norm(v, axis=1)
                parts.append((np.tile(eyes, (m, 1)), v / np.maximum(dist, 1e-12)[:, None], dist,
                              np.tile(np.arange(n_dirs + n_extra, n_views), m), np.repeat(np.arange(m), len(eyes))))
            for origin, d, t_q, col, row in parts:
                ok = (np.abs(np.einsum("ij,ij->i", d, nq[row])) > MIN_COS) & (t_q > 1e-9)
                origin, d, t_q, col, row = origin[ok], d[ok], t_q[ok], col[ok], row[ok]
                if not len(origin):
                    continue
                tri, t = self.caster_b.first_hit(np.ascontiguousarray(origin), np.ascontiguousarray(d))
                # beyond the tolerance along the line AND square to the face behind, as `_Judge.blocker` asks
                hit = tri >= 0
                gap = np.where(hit, np.abs(np.einsum("ij,ij->i", d, self.normals[np.maximum(tri, 0)]))
                               * np.where(hit, t - t_q, 0.0), 0.0)
                behind = hit & (t > t_q + tol) & (gap > tol)
                if not behind.any():
                    continue
                keys, counts = np.unique(tri[behind] * n_views + col[behind], return_counts=True)
                for key, count in zip(keys.tolist(), counts.tolist()):
                    per = seen.setdefault(key // n_views, {})
                    per[key % n_views] = per.get(key % n_views, 0) + count
        return seen, len(lattice)

    def _lost(self, face: int, col: int, vp: Viewpoint, blk):
        """For the pixels of one block: `(lost, reason, cover_face)`, the lost pixels, the reason code of each pixel
        (COVERED or a `present` code) and the AFTER face that covers it (-1 when none)."""
        p, toward = blk.points, blk.toward
        n = self.normals[face]
        cos = toward @ n
        origin = p + _side(cos)[:, None] * n
        if vp.kind == "direction":
            dirn, reach, is_dir = toward, np.full(len(p), np.inf), np.ones(len(p), dtype=bool)
        else:
            to = vp.at - origin
            reach = np.linalg.norm(to, axis=1)
            dirn, is_dir = to / np.maximum(reach, 1e-9)[:, None], np.zeros(len(p), dtype=bool)
        w = _Witnesses(col=np.full(len(p), col), need_front=cos > 0.0, toward=toward, origin=origin, dirn=dirn,
                       reach=reach, is_dir=is_dir)
        return self._lost_lines(np.full(len(p), face, dtype=np.int64), p, w, blk.bary)

    def _lost_lines(self, faces: np.ndarray, p: np.ndarray, w: _Witnesses, bary: np.ndarray):
        """`(lost, reason, cover_face)` for points `p` on BEFORE faces `faces` (weights `bary`) seen along the lines
        `w`: COVERED when the line is blocked in AFTER (`_Judge.blocker`, new geometry only) and no honest fill takes
        it inside its own loop; else gone when AFTER shows no surface in the point's look at its place, asked square
        to its face (`_Judge.present`: deleted, replaced). `reason` is COVERED or the `present` code; `cover_face` the AFTER
        face that covers (-1 when none)."""
        covered, cover_face, hit = self.judge.blocker(p, w, square=np.ones(len(p), dtype=bool))
        if self.fills is not None and covered.any():
            c = np.flatnonzero(covered)
            covered[c[self.fills.excused(cover_face[c], hit[c])]] = False
        cover_face = np.where(covered, cover_face, -1)
        status = np.full(len(p), OK, dtype=np.int8)
        rest = np.flatnonzero(~covered)
        if len(rest):
            # whether the place still holds its surface is the place's question, not the line's: it is asked square to
            # the face, from the viewer's side, as the squarest witness would ask it (along a grazing line a surface
            # 0.015 in off lies more than the tolerance away)
            n = self.normals[faces[rest]]
            toward = n * np.where(np.einsum("ij,ij->i", w.toward[rest], n) > 0.0, 1.0, -1.0)[:, None]
            place = _Witnesses(col=w.col[rest], need_front=w.need_front[rest], toward=toward,
                               origin=p[rest] + EPS_ORIGIN * toward, dirn=toward, reach=np.full(len(rest), np.inf),
                               is_dir=np.ones(len(rest), dtype=bool))
            lb = self.look_b[faces[rest]]
            status[rest] = self.judge.present(p[rest], place, lb, uv_at(self.b, faces[rest], bary[rest]),
                                              self.tex_w[lb], self.tex_h[lb])
        gone = np.isin(status, _GONE)
        reason = np.where(covered, COVERED, status).astype(np.int8)
        return covered | gone, reason, cover_face

    def measure(self, face: int, col: int) -> dict:
        """The face's pixels from view column `col`: `visible` (nearest-visible in BEFORE), `lost` and its `reasons`,
        `covering` (AFTER face -> pixels), `at_least` (the measure stopped early, above the floor, past
        `floor.PIXEL_BUDGET` rays), and for the crops and the site judge the lost pixels' `ij`, `plane` and `point`."""
        vp = self.views[col]
        visible, lost, rays, of_rays, at_least = 0, 0, 0, 0, False
        reasons: dict = {}
        covering: dict = {}
        ij, plane, point, toward = [], [], None, None
        for blk in face_pixels(self.b, face, vp, self.caster_b):
            rays += blk.rays
            of_rays = blk.of_rays
            if len(blk):
                visible += len(blk)
                mask, reason, cover_face = self._lost(face, col, vp, blk)
                if mask.any():
                    lost += int(mask.sum())
                    for code, count in zip(*np.unique(reason[mask], return_counts=True)):
                        name = "covered" if code == COVERED else _GONE_NAMES[int(code)]
                        reasons[name] = reasons.get(name, 0) + int(count)
                    for g, count in zip(*np.unique(cover_face[mask & (cover_face >= 0)], return_counts=True)):
                        covering[int(g)] = covering.get(int(g), 0) + int(count)
                    ij.append(blk.ij[mask])
                    plane.append(blk.plane[mask])
                    if point is None:
                        first = int(np.flatnonzero(mask)[0])
                        point, toward = blk.points[first], blk.toward[first]
            if rays >= PIXEL_BUDGET and lost > VISIBLE_FLOOR_PX and rays < of_rays:
                at_least = True
                break
        estimate = int(round(lost * of_rays / rays)) if at_least else lost
        return {"visible": visible, "lost": lost, "estimate": estimate, "reasons": reasons, "covering": covering,
                "at_least": at_least,
                "ij": np.vstack(ij) if ij else np.zeros((0, 2), np.int64),
                "plane": np.concatenate(plane) if plane else np.zeros(0, np.int64), "point": point, "toward": toward}

    def run(self, candidates: dict) -> tuple[list, list]:
        """`(entries, cases)`: one report entry per candidate face, worst first, and alongside each the measure's own
        data (`face`, `col`, and `measure`'s arrays) for the crops and the site judge. `candidates`:
        `{face: (kind, {view column: evidence count})}`."""
        entries, cases = [], []
        for face in sorted(candidates):
            kind, cols = candidates[face]
            order = sorted(cols, key=lambda c: (-cols[c], c))
            worst, worst_col, measured = None, None, 0
            for col in order:
                m = self.measure(face, col)
                measured += 1
                if worst is None or m["lost"] > worst["lost"]:
                    worst, worst_col = m, col
                if m["lost"] > VISIBLE_FLOOR_PX:
                    break
            entries.append({"face": int(face), "kind": kind, "pixels": int(worst["lost"]),
                            "visible_px": int(worst["visible"]), "reasons": dict(sorted(worst["reasons"].items())),
                            "at_least": bool(worst["at_least"]), "pixels_estimate": int(worst["estimate"]),
                            "viewpoint": dict(self.labels[worst_col]),
                            "viewpoints_seen": len(cols), "viewpoints_measured": measured,
                            "covering_faces": [g for g, _ in sorted(worst["covering"].items(),
                                                                     key=lambda kv: (-kv[1], kv[0]))[:10]],
                            "fails": bool(worst["lost"] > VISIBLE_FLOOR_PX), "crop": None})
            cases.append({"face": int(face), "col": int(worst_col), **worst})
        order = sorted(range(len(entries)), key=lambda k: (-entries[k]["pixels"], entries[k]["face"]))
        return [entries[k] for k in order], [cases[k] for k in order]


# ---------------------------------------------------------------------------------------------
# Check 2: problems solved
# ---------------------------------------------------------------------------------------------

def default_targets_path() -> Path:
    """Where the owner's signed targets live: `engine/validate/targets.json` (written when the owner signs)."""
    return Path(__file__).with_name("targets.json")


def load_targets(path=None) -> dict | None:
    """The targets file, parsed; None when there is none (the owner has not signed yet). `path` defaults
    to `default_targets_path()`. A file that is not JSON, whose JSON is not an object, or whose "kinds" is not an
    object is a `ValueError`: an unreadable target must not quietly turn into "unsigned".

    The shape: `{"signed": true, "kinds": {"flicker_diff": 0, "hidden": {"max": 5, "note": "..."},
    "open_edges": null, ...}}`. A kind's target is the most `find_errors` may count of it after the fix
    (a number, or `{"max": n}`); null or absent means the kind is only listed."""
    path = default_targets_path() if path is None else Path(path)
    if not path.is_file():
        return None
    try:
        targets = json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as exc:
        raise ValueError(f"targets file {path} is not valid JSON: {exc}") from exc
    if not isinstance(targets, dict):
        raise ValueError(f"targets file {path} must hold a JSON object, not {type(targets).__name__}")
    if "kinds" in targets and not isinstance(targets["kinds"], dict):
        raise ValueError(f"targets file {path}: \"kinds\" must be a JSON object, not {type(targets['kinds']).__name__}")
    from engine.detectors.errors import KINDS        # lazy: check 2 is the only use of find_errors here
    unknown = sorted(set(targets.get("kinds") or {}) - set(KINDS))
    if unknown:
        raise ValueError(f"targets file {path} names unknown kinds {unknown}: a misspelled kind would never gate")
    return targets


def _target_of(targets, kind: str):
    """`(number or None, label)` for one kind: ("unsigned") while the owner has not signed the targets,
    ("listed") for a signed file that gives the kind no number, else the number itself."""
    if not targets or not targets.get("signed"):
        return None, "unsigned"
    value = (targets.get("kinds") or {}).get(kind)
    if isinstance(value, dict):
        value = value.get("max")
    if value is None:
        return None, "listed"
    return int(value), int(value)


def check_problems(before_errors: dict, after_errors: dict, targets=None) -> dict:
    """Check 2, problems solved: the `find_errors` counts of BEFORE and AFTER, kind by kind, against the
    targets the owner signed. Until they are signed (or for a kind they give no number) a kind reports
    its counts and, in `residual`, the places `find_errors` still marks in AFTER (its `spots`, each with
    a `centre` in the model's coordinates); the check is then REPORT_ONLY. With a number it passes
    when AFTER has no more than that. The check fails if any numeric target is missed, passes if every
    numeric one is met, and only reports when there is none."""
    kinds = {}
    for kind, after in after_errors["counts"].items():
        number, label = _target_of(targets, kind)
        status = "REPORT_ONLY" if number is None else ("PASS" if after <= number else "FAIL")
        kinds[kind] = {"before": int(before_errors["counts"].get(kind, 0)), "after": int(after), "target": label,
                       "status": status, "residual": list((after_errors.get("spots") or {}).get(kind, []))}
    statuses = {k["status"] for k in kinds.values()}
    status = "FAIL" if "FAIL" in statuses else ("PASS" if "PASS" in statuses else "REPORT_ONLY")
    return {"status": status, "kinds": kinds, "signed": bool(targets and targets.get("signed"))}


# ---------------------------------------------------------------------------------------------
# The run
# ---------------------------------------------------------------------------------------------

#: A sample covered by a face in front of it, and one with a new face of another look on it or just in front of it
#: (reasons beside the `OK .. SIDE` codes of `_Judge.present`).
COVERED, OVERLAID = 5, 6
_REASON_NAMES = {COVERED: "covered", OVERLAID: "overlaid", **_PRESENT_NAMES}


@dataclass(frozen=True, eq=False)       # eq=False: `==` on array fields would be ambiguous, not a bool
class Focus:
    """The faces a FOCUS run looks at (job P1-K3: the repair kernel asks "did these sites break anything?").

    `before_faces`: the BEFORE faces sampled for checks 1 and 3, instead of every face. `after_faces`: the AFTER
    faces the overlay pass may lay over those samples, instead of every new face (a face of AFTER that BEFORE has
    too is never one, focus or not). Each is an array of face ids (a set: order and repeats do not matter) or a
    boolean mask over the mesh's faces. Everything else -- the viewpoints, the tolerances, the casts into the WHOLE
    of AFTER -- is the full run's, so a focus on every face is the full run's checks 1 and 3, and its sites."""
    before_faces: np.ndarray
    after_faces: np.ndarray


def _focus_ids(faces, n_faces: int, what: str) -> np.ndarray:
    """Sorted unique int64 face ids from an id array or a boolean mask; a `ValueError` for one outside 0..n-1."""
    faces = np.asarray(faces)
    if faces.dtype == np.bool_:
        if faces.shape != (n_faces,):
            raise ValueError(f"a boolean focus.{what} mask needs one entry per face ({n_faces})")
        return np.flatnonzero(faces).astype(np.int64)
    faces = faces.reshape(-1)
    if faces.size and faces.dtype.kind not in "iu":
        raise ValueError(f"focus.{what} must be integer face ids, got dtype {faces.dtype}")
    if faces.size and (faces.min() < 0 or faces.max() >= n_faces):
        raise ValueError(f"focus.{what} must lie in 0..{n_faces - 1}, got {faces.min()}..{faces.max()}")
    return np.unique(faces.astype(np.int64))


@dataclass
class Validation:
    """What `validate` found. `report` is the JSON-able `validation.json`; the rest is what the evidence crops
    need: both meshes in the Validator's frame (`centre` is what was subtracted), the samples and, for each
    reported site, which of them failed and which viewpoint judged them."""
    report: dict
    before: MeshData
    after: MeshData
    centre: np.ndarray
    looks: Looks
    look_keys: list
    look_before: np.ndarray
    look_after: np.ndarray
    samples: Samples
    members: list
    wit_col: np.ndarray
    wit_extra: np.ndarray
    viewpoints: dict
    #: the floor's measures (job P2-V2), one per entry of `checks.nothing_deleted.floor.measured`, in its order
    floor_cases: list = field(default_factory=list)

    @property
    def passed(self) -> bool:
        return self.report["verdict"] == "PASS"


def _rows_in(a: np.ndarray, b: np.ndarray) -> np.ndarray:
    """(len(a),) bool: row i of `a` is also a row of `b`."""
    keys = {row.tobytes() for row in np.ascontiguousarray(b)}
    return np.fromiter((row.tobytes() in keys for row in np.ascontiguousarray(a)), dtype=bool, count=len(a))


def changed_faces(before: MeshData, after: MeshData) -> np.ndarray:
    """(after.n_faces,) bool: the AFTER faces whose three corners, as a set and exactly in float64, are not the corners
    of any BEFORE face -- NEW GEOMETRY. A face kept, re-wound or given another look or UV lies where it lay, so it
    meets exactly the lines it met in BEFORE and can block nothing new; only these can (job P2-V2, items 3 and 4). Both
    meshes in one frame (the same shift keeps equal coordinates equal)."""
    def keys(mesh: MeshData) -> np.ndarray:
        tri = np.ascontiguousarray(mesh.positions[mesh.face_v] + 0.0)          # + 0.0: -0.0 is 0.0
        rows = tri.view(np.dtype((np.void, 24))).reshape(mesh.n_faces, 3)
        return np.ascontiguousarray(np.sort(rows, axis=1)).view(np.dtype((np.void, 72))).reshape(-1)
    if not after.n_faces:
        return np.zeros(0, dtype=bool)
    if not before.n_faces:
        return np.ones(after.n_faces, dtype=bool)
    return ~np.isin(keys(after), keys(before))


def _points(a) -> np.ndarray:
    return np.asarray(a, dtype=np.float64).reshape(-1, 3)


#: Cells joined into one site reach at most this many cells (of `Settings.cluster_cell`) away.
_MAX_LINK = 4


def _half_neighbours(link: int) -> np.ndarray:
    """The offsets within `link` cells in every axis that come after (0, 0, 0) in lexicographic order:
    with their opposites, every other cell of the (2 link + 1) cube round a cell."""
    span = range(-link, link + 1)
    return np.array([(dx, dy, dz) for dx in span for dy in span for dz in span if (dx, dy, dz) > (0, 0, 0)],
                    dtype=np.int64)


def _components(cells: np.ndarray, link: int = 1) -> np.ndarray:
    """(k,) int64: the connected group (0 .. c-1) of each occupied grid cell of `cells` (k, 3), two cells
    being connected when they are within `link` cells of each other in every axis (1: they touch, 26
    neighbours). Labels are propagated along the connected pairs, each round followed by pointer
    jumping, until nothing changes."""
    k = len(cells)
    if not k:
        return np.zeros(0, dtype=np.int64)
    shifted = cells - cells.min(axis=0) + link
    shape = shifted.max(axis=0) + link + 1
    pack = lambda c: (c[:, 0] * shape[1] + c[:, 1]) * shape[2] + c[:, 2]
    packed = pack(shifted)
    order = np.argsort(packed)
    ordered = packed[order]
    ends_a, ends_b = [], []
    for offset in _half_neighbours(link):
        wanted = pack(shifted + offset)
        at = np.minimum(np.searchsorted(ordered, wanted), k - 1)
        hit = ordered[at] == wanted
        ends_a.append(np.flatnonzero(hit))
        ends_b.append(order[at[hit]])
    a, b = np.concatenate(ends_a), np.concatenate(ends_b)
    label = np.arange(k, dtype=np.int64)
    while True:
        low = np.minimum(label[a], label[b])
        new = label.copy()
        np.minimum.at(new, a, low)
        np.minimum.at(new, b, low)
        new = new[new]
        if np.array_equal(new, label):
            break
        label = new
    return np.unique(label, return_inverse=True)[1].reshape(-1).astype(np.int64)


def _cluster_sites(validation_points: np.ndarray, centre: np.ndarray, failing: np.ndarray, area: np.ndarray,
                   face: np.ndarray, reason: np.ndarray, fail1: np.ndarray, fail3: np.ndarray, spacing: np.ndarray,
                   cell: float, limit: int):
    """The failing samples (`failing`, their indices) in groups: the `cell`-inch grid cells (in the
    model's own coordinates) they fall in, with neighbouring cells joined, so one defect is one site
    however it straddles the grid. Neighbouring means touching, or further when the samples are
    further apart than a cell: the lattice of a long thin face has gaps of `spacing` (the face's
    longest edge over the samples along it), and cells within the 90th percentile of the failing
    samples' spacing (at most `_MAX_LINK` cells) are joined. Worst first (most area, then most
    samples). Returns `(sites, members, total)`: the first `limit` sites as dicts, the sample indices
    of each, and how many clusters there were."""
    if not len(failing):
        return [], [], 0
    pts = validation_points[failing] + centre
    keys = np.floor(pts / cell).astype(np.int64)
    link = int(np.clip(np.ceil(np.percentile(spacing[failing], 90) / cell), 1, _MAX_LINK))
    cells, which = np.unique(keys, axis=0, return_inverse=True)
    inverse = _components(cells, link)[which.reshape(-1)]
    n_clusters = int(inverse.max()) + 1
    cluster_area = np.bincount(inverse, weights=area[failing], minlength=n_clusters)
    cluster_count = np.bincount(inverse, minlength=n_clusters)
    order = np.lexsort((np.arange(n_clusters), -cluster_count, -np.round(cluster_area, 9)))
    sites, members = [], []
    for rank, c in enumerate(order[:limit], start=1):
        sel = failing[np.flatnonzero(inverse == c)]
        p = validation_points[sel] + centre
        reasons = {}
        for code, count in zip(*np.unique(reason[sel], return_counts=True)):
            reasons[_REASON_NAMES[int(code)]] = int(count)
        checks = [name for name, mask in (("textures", fail1), ("nothing_deleted", fail3)) if mask[sel].any()]
        sites.append({"id": rank, "centre": [round(float(v), 2) for v in (p.min(axis=0) + p.max(axis=0)) / 2.0],
                      "size": round(float(np.linalg.norm(p.max(axis=0) - p.min(axis=0))), 2),
                      "samples": int(len(sel)), "area_in2": round(float(area[sel].sum()), 2), "checks": checks,
                      "reasons": reasons, "faces": [int(f) for f in np.unique(face[sel])[:50]], "evidence": None})
        members.append(sel)
    return sites, members, n_clusters


def validate(before: MeshData, after: MeshData, looks: Looks, *, errors=None, targets=None,
             settings: Settings = Settings(), dirs=None, cams=None, probes=None, extra_dirs=None,
             progress=None, focus: Focus | None = None, fills=None) -> Validation:
    """Judge `after` against `before` by the owner's three checks.

    Both meshes are in the model's own coordinates; they are shifted into the Validator's frame here, by
    BEFORE's bounding-box centre for both. The viewpoints (`dirs`, `cams`, `probes`, `extra_dirs`) are
    BEFORE's and are made once, here, unless given (the cameras and probes a caller gives are positions in the
    model's own coordinates, like the meshes; directions need no frame); the probes are never recomputed for AFTER.
    `errors` is the `(before, after)` pair of `find_errors` results for check 2, run here when None.
    `progress(done, total)` is called after each chunk of samples.

    The report (`Validation.report`, which the `validate` command writes as `validation.json`):

    * `verdict`: "FAIL" if any check is FAIL, else "PASS". A check 2 that is REPORT_ONLY (the targets
      are unsigned) does not fail the verdict; `checks.problems.signed` says whether it could have.
    * `checks.textures` (check 1): `status`, `samples` (the ones some standard viewpoint sees),
      `samples_failed`, `faces`, `faces_failed`, `area_failed_in2` and `reasons`, how many failed first
      by `covered` (a face in front of it by more than the tolerance), `overlaid` (a new face on it or in
      front of it within the tolerance, in a look or UV the place did not have), `deleted` (nothing at that
      depth), `look`, `uv` or `side` (BEFORE's front seen, AFTER's back).
    * `checks.nothing_deleted` (check 3): `status`, `samples` (the above plus `samples_extra`, which only
      the extra directions of a face that is gone saw), `suspect_faces`, `deleted`, `replaced` (something
      is there, in another look), `covered` (on any line of sight that saw it, from either side), `overlaid`,
      `faces_unmet` (every tested sample of the face), `faces_partly_unmet`, `faces_covered`, `faces_overlaid`
      and the areas; and `floor` (job P2-V2, `_Floor`): its `status`, the floor (`floor_px`, `in_per_px`), the
      `lattice` on the removed faces and the one on AFTER's `new_faces`, the `candidates`, and per measured face
      (`measured`, worst first; `failing`, those above the floor) its `kind` (removed or covered), `pixels` lost
      from its worst viewpoint (`at_least` and `pixels_estimate` when the measure stopped early), `visible_px`,
      `reasons`, the `viewpoint`, the `covering_faces` and the `crop` (`evidence.write_floor_crops`). Check 3
      fails when the samples fail or the floor does.
    * `checks.problems` (check 2): per `find_errors` kind `before`, `after`, `target` ("unsigned",
      "listed" or the number), `status` and `residual` (AFTER's spots with their `centre`).
    * `sites`: the failing samples grouped (`id` 1 is the worst), each with `centre` and `size` in the
      model's coordinates, `samples`, `area_in2`, `checks` it failed, `reasons`, `faces` (BEFORE's face
      numbers) and `evidence` (paths, once `evidence.write_evidence` has run); `sites_total` counts all.
    * the rest: `viewpoints`, `settings`, `frame.centre`, `print_step_in`, `depth_tolerance_in`, `before` and
      `after` sizes (`after.new_faces`: faces BEFORE did not have), `timings_s`; `materials`: those unknown
      to `materials.json` and, in `no_texel`, every look whose UV could not be compared (flat or no texture
      file); and `notes`, which say so in words, with any non-default settings.

    FOCUS (`focus`, a `Focus`; job P1-K3). Checks 1 and 3 sample only `focus.before_faces`, and the overlay pass
    lays only the new faces among `focus.after_faces` over them; nothing else changes. Check 2 is not run
    (`checks.problems` is `{"status": "skipped (focus)"}`, `errors` is ignored) and there is NO floor verdict:
    `verdict` is None (so `Validation.passed` is False). `focus` says `before_faces`, `after_faces` (how many) and
    `status`, "FAIL" when check 1 or check 3 failed on those faces, else "PASS": whether these sites broke
    anything, never whether the floor is good.

    FILLS (`fills`, a list of `FillSite`: the faces the edit log marks as E8 flat fills; job P2-E8b, ruling E8b-R6).
    The one named class of allowed change, `fill_site` (see `_FillSites`): a sample covered only by honest fills,
    each line of sight ending inside the fill's own loop, is `covered_by_fill` instead of `covered`, and fails neither
    check. `checks.textures.covered_by_fill` and `checks.nothing_deleted.covered_by_fill` count them (they are in
    neither `reasons` nor `covered`), and `fill_sites` (at the report's end) lists, per fill: `honest`, `why` not,
    its AFTER `faces`, the `samples` it covers and the BEFORE faces those lie on (`before_faces`, at most 50).
    Without fills (None or an empty list) nothing differs: those three keys are left out and `validation.json` is
    byte for byte the Validator's of before the class."""
    clock = {"start": time.perf_counter()}
    if focus is not None:
        focus_before = _focus_ids(focus.before_faces, before.n_faces, "before_faces")
        focus_after = _focus_ids(focus.after_faces, after.n_faces, "after_faces")
    step = print_step(before)
    tol = depth_tolerance(step)
    b, centre = recentred(before)
    a, _ = recentred(after, centre)
    caster_b = build_caster(b) if b.n_faces else None
    caster_a = build_caster(a) if a.n_faces else None

    lo, hi = used_bbox(b)
    # outside views come only from directions at or above the horizon (owner, 2026-10-10): d_z <= 0, the viewer at -d
    dirs = _points(above_horizon_directions(settings.n_directions) if dirs is None else dirs)
    # made here, they are already in the Validator's frame; given, they are positions in the model's own
    # coordinates (like the meshes) and are shifted into it
    cams = (_points(pedestrian_ring((lo, hi), eye_z=lo[2] + settings.eye, n=settings.n_cameras,
                                    margin=settings.camera_margin)) if cams is None else _points(cams) - centre)
    if probes is None:
        probes = _points(interior_probes(b, eye=settings.eye, caster=caster_b)) if b.n_faces else np.zeros((0, 3))
    else:
        probes = _points(probes) - centre
    extra_dirs = _points(above_horizon_directions(settings.n_extra_directions) if extra_dirs is None else extra_dirs)
    nothing = np.zeros((0, 3))

    samples = face_samples(b, faces=None if focus is None else focus_before, min_per_face=settings.min_per_face,
                           area_per_sample=settings.area_per_sample)
    n = len(samples)
    per_face_samples = np.bincount(samples.face, minlength=b.n_faces)
    sample_area = face_areas(b)[samples.face] / np.maximum(per_face_samples[samples.face], 1)

    table = LookTable()
    look_b = face_look_ids(before, looks, table)
    look_a = face_look_ids(after, looks, table)
    sizes = [looks.texel.get(k) or (0, 0) for k in table.keys]
    tex_w = np.array([s[0] for s in sizes], dtype=np.float64)
    tex_h = np.array([s[1] for s in sizes], dtype=np.float64)
    fp_before, fp_after = face_fingerprints(before, step, look_b), face_fingerprints(after, step, look_a)
    suspect = ~_rows_in(fp_before, fp_after)                  # faces of BEFORE that AFTER no longer has
    new_after = ~_rows_in(fp_after, fp_before)                # faces of AFTER that BEFORE did not have
    overlay_new = new_after                                   # ...that the overlay pass lays over the samples
    if focus is not None:
        overlay_new = np.zeros(after.n_faces, dtype=bool)
        overlay_new[focus_after] = True
        overlay_new &= new_after
    fill_sites = _FillSites(fills, b, a, centre, look_b, look_a, step, tol) if fills else None
    clock["prepared"] = time.perf_counter()

    tested = np.zeros(n, dtype=bool)
    extra = np.zeros(n, dtype=bool)
    covered = np.zeros(n, dtype=bool)
    by_fill = np.zeros(n, dtype=bool)
    fill_of_sample = np.full(n, -1, dtype=np.int64)
    present = np.zeros(n, dtype=np.int8)
    wit_col = np.full(n, -1, dtype=np.int32)
    wit_extra = np.zeros(n, dtype=bool)
    toward_all = np.zeros((n, 3))
    normals_b = face_normals(b)
    changed_a = changed_faces(b, a)           # AFTER's new geometry, the only faces that can block (job P2-V2)
    judge = _Judge(a, caster_a, look_a, tol, blockable=changed_a)
    n_dirs, n_extra = len(dirs), len(extra_dirs)
    n_views = n_dirs + n_extra + len(cams) + len(probes)
    covered_pairs: dict = {}                  # BEFORE face -> {floor view column: blocked lines} (job P2-V2 item 3)

    def run(idx: np.ndarray, d: np.ndarray, c: np.ndarray, pr: np.ndarray, is_extra: bool) -> None:
        sub = Samples(points=samples.points[idx], face=samples.face[idx], bary=samples.bary[idx])
        vs = visible_samples(b, sub, d, c, pr, caster_b)
        rows = np.flatnonzero(vs.visible)
        if not len(rows):
            return
        face_normal = normals_b[sub.face]
        scores = _scores(vs, rows, sub.points, face_normal)
        w, _ = _witnesses(vs, rows, sub.points, face_normal, scores)          # every row is seen by some viewpoint
        p, face = sub.points[rows], sub.face[rows]
        lb = look_b[face]
        g = idx[rows]
        # job P2-V2 item 3: covered on EVERY line of sight that saw the sample, from either side, not the witness's
        # alone; the crop of a covered sample is drawn from its best-conditioned blocked line
        witness = np.stack([w.col, np.full(len(rows), -1, dtype=np.int64)], axis=1)
        if len(vs.probes) and not is_extra:
            # the best eye-height probe, which the Validator asked as well before every line was asked (AGENTS.md 5)
            probes_only = np.zeros(vs.seen.shape[1], dtype=bool)
            probes_only[len(vs.dirs) + len(vs.cams):] = True
            w2, sel = _witnesses(vs, rows, sub.points, face_normal, scores, probes_only)
            witness[sel, 1] = w2.col
        cover, col, blocked_r, blocked_c, explained, which = _covered_on_every_line(
            judge, vs, rows, sub.points, face_normal, scores, witness, fill_sites)
        col = np.where(cover, col, w.col)
        if len(blocked_r):
            # the floor measures each covered face from each viewpoint that saw it covered (its columns are the
            # floor's: the standard directions, the extra ones, the cameras, the probes)
            floor_col = blocked_c + np.where(is_extra, n_dirs, np.where(blocked_c < n_dirs, 0, n_extra))
            keys, counts = np.unique(sub.face[rows[blocked_r]] * n_views + floor_col, return_counts=True)
            for key, count in zip(keys.tolist(), counts.tolist()):
                per = covered_pairs.setdefault(key // n_views, {})
                per[key % n_views] = per.get(key % n_views, 0) + count
        if fill_sites is not None:
            # the fill_site class (E8b-R6): covered only by marked, honest fills, inside their own loops
            by_fill[g], fill_of_sample[g] = explained, which
        covered[g] = cover
        present[g] = judge.present(p, w, lb, uv_at(b, face, sub.bary[rows]), tex_w[lb], tex_h[lb])
        tested[g], extra[g], wit_col[g], wit_extra[g], toward_all[g] = True, is_extra, col, is_extra, w.toward

    chunk = max(1, int(settings.chunk))
    for start in range(0, n, chunk):
        run(np.arange(start, min(start + chunk, n)), dirs, cams, probes, False)
        if progress is not None:
            progress(min(start + chunk, n), n)
    clock["cast"] = time.perf_counter()
    # faces whose fingerprint AFTER does not have: their samples nobody saw get the extra directions
    left = np.flatnonzero(suspect[samples.face] & ~tested)
    for start in range(0, len(left), chunk):
        run(left[start:start + chunk], extra_dirs, nothing, nothing, True)
    clock["extra"] = time.perf_counter()

    # new faces of AFTER on a sample or just in front of it, in a look or UV the place did not have. Only a sample
    # whose own surface is met can have one laid over it: the others already fail as deleted, look, uv or side.
    overlaid = np.zeros(n, dtype=bool)
    if overlay_new.any():
        overlay = _Overlay(b, a, overlay_new, look_b, look_a, tex_w, tex_h, tol)
        met = np.flatnonzero(tested & (present == OK))
        for start in range(0, len(met), _OVERLAY_BLOCK):
            blk = met[start:start + _OVERLAY_BLOCK]
            face = samples.face[blk]
            overlaid[blk] = overlay.overlaid(samples.points[blk], toward_all[blk], look_b[face],
                                             uv_at(b, face, samples.bary[blk]))
    clock["overlay"] = time.perf_counter()

    # ---- the owner's floor (job P2-V2): removed faces a dense lattice sees, measured in pixels ----
    floor_report = {"status": "PASS", "floor_px": VISIBLE_FLOOR_PX, "in_per_px": FLOOR_IN_PER_PX,
                    "lattice": {"min": LATTICE_MIN, "per_sq_in": LATTICE_PER_SQ_IN, "cap": LATTICE_CAP, "faces": 0,
                                "points": 0},
                    "new_faces": {"faces": 0, "points": 0},
                    "pixel_budget": PIXEL_BUDGET, "candidates": {"removed": 0, "covered": 0}, "faces_measured": 0,
                    "faces_failed": 0, "failing": [], "measured": []}
    floor_cases: list = []
    if b.n_faces:
        views, labels = floor_views(dirs, extra_dirs, cams, probes, centre)
        floor = _Floor(b, judge, fill_sites, look_b, tex_w, tex_h, caster_b, views, labels, normals_b, centre)
        removed = suspect & (np.abs(normals_b).sum(axis=1) > 0.0)
        in_focus = np.ones(b.n_faces, dtype=bool)
        if focus is not None:
            in_focus[:] = False
            in_focus[focus_before] = True
            removed &= in_focus
        removed_ids = np.flatnonzero(removed)
        all_dirs = np.vstack([dirs, extra_dirs])
        seen, n_seen, n_points = floor.lattice_seen(removed_ids, all_dirs, cams, probes)
        floor_report["lattice"].update(faces=int(len(removed_ids)), points=int(n_points))
        candidates = {f: ("removed", dict(cols)) for f, cols in seen.items()}
        floor_report["candidates"].update(removed_seen=int(n_seen), removed=len(seen))
        # covered faces: those a sample line found covered, and those a new face's own lattice finds behind it
        new_ids = np.flatnonzero(changed_a if focus is None else changed_a & np.isin(np.arange(a.n_faces), focus_after))
        behind, n_new_points = floor.cover_seen(a, new_ids, dirs, cams, probes, tol, n_extra=len(extra_dirs))
        floor_report["new_faces"] = {"faces": int(len(new_ids)), "points": int(n_new_points)}
        covered_faces = set()
        for source in (covered_pairs, behind):
            for f, cols in source.items():
                if focus is not None and not in_focus[f]:
                    continue
                covered_faces.add(f)
                kind, have = candidates.setdefault(f, ("covered", {}))
                for c, k in cols.items():
                    have[c] = have.get(c, 0) + k
        floor_report["candidates"]["covered"] = len(covered_faces)
        entries, floor_cases = floor.run(candidates)
        failing = [e for e in entries if e["fails"]]
        floor_report.update(status="FAIL" if failing else "PASS", faces_measured=len(entries),
                            faces_failed=len(failing), failing=failing, measured=entries)
    clock["floor"] = time.perf_counter()

    # ---- check 1 and check 3 from what every tested sample turned out to be ----
    standard = tested & ~extra
    reason1 = present.astype(np.int8)
    reason1[overlaid] = OVERLAID
    reason1[covered] = COVERED
    fail1 = standard & (reason1 != OK)
    unmet = tested & ((present == DELETED) | (present == LOOK))
    fail3 = tested & (covered | overlaid | unmet)
    n_faces = b.n_faces
    per_face = lambda mask: np.bincount(samples.face[mask], minlength=n_faces)
    tested_per_face, unmet_per_face = per_face(tested), per_face(unmet)

    textures = {
        "status": "FAIL" if fail1.any() else "PASS", "samples": int(standard.sum()),
        "samples_failed": int(fail1.sum()), "faces": int((per_face(standard) > 0).sum()),
        "faces_failed": int((per_face(fail1) > 0).sum()), "area_failed_in2": round(float(sample_area[fail1].sum()), 2),
        "reasons": {name: int((fail1 & (reason1 == code)).sum()) for code, name in
                    ((COVERED, "covered"), (OVERLAID, "overlaid"), (DELETED, "deleted"), (LOOK, "look"),
                     (UV, "uv"), (SIDE, "side"))},
        "depth_tolerance_in": round(tol, 4)}
    nothing_deleted = {
        "status": "FAIL" if fail3.any() or floor_report["status"] == "FAIL" else "PASS", "samples": int(tested.sum()), "samples_extra": int(extra.sum()),
        "suspect_faces": int(suspect.sum()), "deleted": int((tested & ~covered & (present == DELETED)).sum()),
        "replaced": int((tested & ~covered & (present == LOOK)).sum()), "covered": int((tested & covered).sum()),
        "overlaid": int((tested & ~covered & overlaid).sum()), "faces": int((tested_per_face > 0).sum()),
        "faces_unmet": int(((tested_per_face > 0) & (unmet_per_face == tested_per_face)).sum()),
        "faces_partly_unmet": int(((unmet_per_face > 0) & (unmet_per_face < tested_per_face)).sum()),
        "faces_covered": int((per_face(tested & covered) > 0).sum()),
        "faces_overlaid": int((per_face(tested & overlaid) > 0).sum()),
        "area_lost_in2": round(float(sample_area[unmet].sum()), 2),
        "area_covered_in2": round(float(sample_area[tested & covered].sum()), 2),
        "area_overlaid_in2": round(float(sample_area[tested & overlaid].sum()), 2),
        "depth_tolerance_in": round(tol, 4), "floor": floor_report}
    fill_report = []
    if fill_sites is not None:
        # only with fills: without them `validation.json` is exactly what it was before the fill_site class
        textures["covered_by_fill"] = int((standard & by_fill).sum())
        nothing_deleted["covered_by_fill"] = int((tested & by_fill).sum())
    for k, site in enumerate([] if fill_sites is None else fill_sites.sites):
        mine = tested & by_fill & (fill_of_sample == k)
        fill_report.append({"fill": k, "honest": site["honest"], "why": site["why"], "faces": int(len(site["faces"])),
                            "samples": int(mine.sum()), "area_in2": round(float(sample_area[mine].sum()), 2),
                            "before_faces": [int(f) for f in np.unique(samples.face[mine])[:50]]})

    # ---- check 2 (never in a focus run: it judges the floor, and a focus run judges sites) ----
    if focus is not None:
        problems = {"status": "skipped (focus)"}
    else:
        if errors is None:
            from engine.detectors.errors import find_errors    # lazy: it imports engine.fixes, .guard and .vis
            errors = (find_errors(before), find_errors(after))
        problems = check_problems(errors[0], errors[1], targets)
    clock["problems"] = time.perf_counter()

    # ---- the sites: failing samples, clustered ----
    failing = np.flatnonzero(fail1 | fail3)
    corners = b.positions[b.face_v]
    longest = np.max([np.linalg.norm(corners[:, i] - corners[:, (i + 1) % 3], axis=1) for i in range(3)], axis=0)
    spacing = (longest / np.sqrt(np.maximum(per_face_samples, 1)))[samples.face]       # n x n samples on a face
    sites, members, n_sites = _cluster_sites(samples.points, centre, failing, sample_area, samples.face, reason1,
                                             fail1, fail3, spacing, settings.cluster_cell, settings.max_sites)
    clock["end"] = time.perf_counter()

    statuses = (textures["status"], problems["status"], nothing_deleted["status"])
    default = Settings()
    density = ("n_directions", "n_cameras", "camera_margin", "n_extra_directions", "min_per_face",
               "area_per_sample", "eye")
    changed = {k: getattr(settings, k) for k in density if getattr(settings, k) != getattr(default, k)}
    notes = ([f"NON-DEFAULT SETTINGS {changed}: a development run, NOT AN OWNER VERDICT"] if changed else [])
    if focus is not None:
        notes.append(f"FOCUS RUN on {len(focus_before)}/{before.n_faces} faces: NOT A FLOOR VERDICT")
    # what BEFORE's looks leave unsaid: materials.json does not know a material, or a look has no texture size
    used = {before.materials[i] for i in np.unique(before.face_material) if 0 <= i < len(before.materials)}
    no_texel = []
    for i in np.unique(look_b):
        k = table.keys[int(i)]
        if looks.texel.get(k) is None:
            no_texel.append({"look": k, "materials": sorted(m for m in used if looks.key_of(m) == k),
                             "flat": k in looks.flat or k == NO_MATERIAL})
    no_texel.sort(key=lambda e: e["look"])
    listed = lambda entries: ", ".join(f"{e['look']} ({', '.join(e['materials']) or 'no material'})" for e in entries)
    unknown = [m for m in looks.unknown(before) if m in used]
    if unknown:
        notes.append(f"{len(unknown)} material(s) of BEFORE are not in materials.json and are compared by name "
                     f"(their texture size and colour come from the snapshot's own MTL where it has them): "
                     + ", ".join(unknown))
    if any(not e["flat"] for e in no_texel):
        missing = [e for e in no_texel if not e["flat"]]
        notes.append(f"UV NOT COMPARED for {len(missing)} look(s) whose texture size is unknown (no texture file "
                     f"was found): {listed(missing)}")
    if any(e["flat"] for e in no_texel):
        flats = [e for e in no_texel if e["flat"]]
        notes.append(f"UV not compared for {len(flats)} flat look(s) (no texture, so there is no UV to see): "
                     f"{listed(flats)}")
    verdict = "FAIL" if "FAIL" in statuses else "PASS"
    report = {
        "version": 1, "verdict": verdict if focus is None else None, "notes": notes,
        "checks": {"textures": textures, "problems": problems, "nothing_deleted": nothing_deleted},
        "sites": sites, "sites_total": n_sites,
        "viewpoints": {"directions": len(dirs), "cameras": len(cams), "probes": len(probes),
                       "extra_directions": len(extra_dirs)},
        "settings": settings.as_dict(), "frame": {"centre": [round(float(v), 4) for v in centre]},
        "print_step_in": step, "depth_tolerance_in": tol,
        "before": {"faces": before.n_faces, "samples": n},
        "after": {"faces": after.n_faces, "new_faces": int(new_after.sum())},
        "materials": {"unknown_before": looks.unknown(before), "unknown_after": looks.unknown(after),
                      "no_texel": no_texel},
        "timings_s": {"prepare": round(clock["prepared"] - clock["start"], 2),
                      "visibility_and_casts": round(clock["cast"] - clock["prepared"], 2),
                      "extra_directions": round(clock["extra"] - clock["cast"], 2),
                      "overlay": round(clock["overlay"] - clock["extra"], 2),
                      "floor": round(clock["floor"] - clock["overlay"], 2),
                      "problems": round(clock["problems"] - clock["floor"], 2),
                      "sites": round(clock["end"] - clock["problems"], 2),
                      "total": round(clock["end"] - clock["start"], 2)}}
    if fill_sites is not None:
        report["fill_sites"] = fill_report
    if focus is not None:
        report["focus"] = {"before_faces": int(len(focus_before)), "after_faces": int(len(focus_after)),
                           "status": "FAIL" if (fail1 | fail3).any() or floor_report["status"] == "FAIL" else "PASS"}
    return Validation(report=report, before=b, after=a, centre=centre, looks=looks, look_keys=table.keys,
                      look_before=look_b, look_after=look_a, samples=samples, members=members, wit_col=wit_col,
                      wit_extra=wit_extra, viewpoints={"dirs": dirs, "cams": cams, "probes": probes,
                                                       "extra_dirs": extra_dirs}, floor_cases=floor_cases)
