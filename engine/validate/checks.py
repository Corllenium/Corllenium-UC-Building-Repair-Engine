"""The Validator's three checks, on a BEFORE and an AFTER of one floor (AGENTS.md section 6).

Written for the Validator and independent of the code it judges (see `engine.validate`). The one
exception is check 2, which has to run `engine.detectors.errors.find_errors` on both meshes, and that
module imports `engine.fixes`, `engine.guard` and `engine.vis`: so it is imported LAZILY, inside
`validate` when it is not handed the errors, and nowhere else. Loading this module loads none of them.

A look key (`data/campus/materials.json`: texture sha256 + Kd + d) is the identity of what a face
looks like, never a `usemtl` number. A face's look is `looks.key[mesh.materials[face_material]]`.

HOW A FLOOR IS JUDGED. The BEFORE is sampled (`sampling.face_samples`) and every sample is looked at
from 128 directions, a ring of cameras and the eye-height probes (`visibility.visible_samples`). Each
sample some viewpoint sees is then asked of AFTER from ONE viewpoint, the best conditioned (the one
least edge-on to its face; one that sees its front, when any does):

* check 1, textures there: AFTER shows, at that depth (within `max(2 print steps, 0.05 in)`), a
  surface with the same look key, the same UV (mod 1, within one texel of that texture), seen from its
  front where BEFORE's front was seen; and nothing covers it;
* check 3, nothing deleted or covered: a surface of the same look is at that depth, and nothing is in
  front of it. Faces whose fingerprint (snapped corners, winding, look) AFTER does not have are looked
  at from 1,024 extra directions too; what only those see counts for check 3 alone;
* check 2, problems solved: `find_errors` on both, against the targets the owner signs (until then it
  only reports).

v0 has NO allowed-change classes: removing an inward copy of a back-to-back pair, or cutting a loser
along a winner's border, fails check 3, which is expected until those engines name their classes.
"""
from __future__ import annotations

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
from engine.validate.viewpoints import interior_probes, outside_directions, pedestrian_ring
from engine.validate.visibility import EPS_ORIGIN, VisibleSet, _side, build_caster, visible_samples

#: The look of a face with no `usemtl` (material -1), which is never "the last material" by accident.
NO_MATERIAL = "<no material>"
_PNG_SIGNATURE = b"\x89PNG\r\n\x1a\n"

#: The depth tolerance is `max(DEPTH_STEPS print steps, MIN_DEPTH_TOL)`.
DEPTH_STEPS = 2.0
MIN_DEPTH_TOL = 0.05


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
    RGB (texture mean times Kd), for the evidence crops."""
    key: dict
    texel: dict = field(default_factory=dict)
    colour: dict = field(default_factory=dict)

    def key_of(self, material: str) -> str:
        """The look key of a material; one `materials.json` does not know keeps its own name, so two
        such names stay two looks and never equal a real key."""
        return self.key.get(material) or f"unknown:{material}"

    def unknown(self, mesh: MeshData) -> list[str]:
        """The materials of `mesh` that `materials.json` does not list, sorted."""
        return sorted({m for m in mesh.materials if m not in self.key})

    def colour_of(self, look_key: str) -> tuple[int, int, int]:
        """The evidence colour of a look: its mean texture colour when known, else a stable colour made
        from the key, so different looks differ in the crops even when nothing is known about them."""
        known = self.colour.get(look_key)
        if known is not None:
            return tuple(int(c) for c in known)
        digest = hashlib.sha256(look_key.encode("utf-8")).digest()
        return (64 + digest[0] % 160, 64 + digest[1] % 160, 64 + digest[2] % 160)


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


def load_looks(materials_json, sources: Sequence[tuple[dict, Path]]) -> Looks:
    """`Looks` from `data/campus/materials.json` and the MTLs the textures are found through.

    `sources` is a list of `(parse_mtl(...) result, directory its map_Kd paths are relative to)`: the
    BEFORE snapshot, and the AFTER output when it has its own. A look's texel size and mean colour
    come from the first source that has its texture on disk; a look with no texture file is
    coloured by its Kd, and has no texel size (its UV is then not compared: nothing shows it)."""
    materials = json.loads(Path(materials_json).read_text(encoding="utf-8"))["materials"]
    key = {name: entry["look"] for name, entry in materials.items()}
    texel: dict = {}
    colour: dict = {}
    for mtl, base in sources:
        for name, mat in mtl.items():
            entry = materials.get(name)
            if entry is None:
                continue
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
    return Looks(key=key, texel=texel, colour=colour)


def face_fingerprints(mesh: MeshData, step: float, look_ids: np.ndarray) -> np.ndarray:
    """(F, 10) int64, one row per face: its three corners snapped to the print grid (`round(x /
    step)`), written from the smallest corner on and in winding order, then its look id. Two faces
    with the same row are the same face for the Validator: the same place, wound the same way, the
    same look. The opposite winding is another row, so a flipped face is looked at again."""
    q = step if step > 0.0 else 1e-6
    corners = np.round(mesh.positions[mesh.face_v] / q).astype(np.int64)          # (F, 3, 3)
    first = np.lexsort((corners[:, :, 2], corners[:, :, 1], corners[:, :, 0]), axis=-1)[:, 0]
    order = (first[:, None] + np.arange(3)[None, :]) % 3
    rolled = np.take_along_axis(corners, order[:, :, None], axis=1).reshape(mesh.n_faces, 9)
    return np.concatenate([rolled, np.asarray(look_ids, dtype=np.int64)[:, None]], axis=1)


# ---------------------------------------------------------------------------------------------
# Settings, and what each sample ends up as
# ---------------------------------------------------------------------------------------------

@dataclass(frozen=True)
class Settings:
    """How much the Validator looks at. The defaults are the owner's (spec section 3): at least 4
    samples on every face and one per 36 sq in, 128 directions, a ring of 24 cameras, 1,024 extra
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
#: Pairs (ray x face) tested in one numpy block when the surface at a sample is looked up by hand.
_FALLBACK_PAIRS = 4_000_000


def _barycentric(positions: np.ndarray, face_v: np.ndarray, q: np.ndarray) -> np.ndarray:
    """(m, 3) float64 barycentric weights of the points `q` (m, 3) in the triangles `face_v` (m, 3)
    of `positions`, taken on the triangle's plane (a point off it is projected)."""
    a, b, c = positions[face_v[:, 0]], positions[face_v[:, 1]], positions[face_v[:, 2]]
    v0, v1, v2 = b - a, c - a, q - a
    d00, d01, d11 = (v0 * v0).sum(1), (v0 * v1).sum(1), (v1 * v1).sum(1)
    d20, d21 = (v2 * v0).sum(1), (v2 * v1).sum(1)
    den = d00 * d11 - d01 * d01
    ok = den != 0.0
    safe = np.where(ok, den, 1.0)
    wb = np.where(ok, (d11 * d20 - d01 * d21) / safe, np.nan)
    wc = np.where(ok, (d00 * d21 - d01 * d20) / safe, np.nan)
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


def _witnesses(vs: VisibleSet, rows: np.ndarray, points: np.ndarray, normals: np.ndarray) -> _Witnesses:
    """For each sample `rows` of the chunk `vs` was cast for: the best-conditioned viewpoint that sees it
    (the largest |cos| between the line of sight and the face's normal, so the one least edge-on),
    among those that see its FRONT when any does, else among those that see it at all."""
    p, n = points[rows], normals[rows]
    seen, front = vs.seen[rows], vs.front[rows]
    n_dir = len(vs.dirs)
    viewpoints = np.vstack([vs.cams, vs.probes])
    abs_cos = np.zeros(seen.shape)
    if n_dir:
        abs_cos[:, :n_dir] = np.abs(n @ (-vs.dirs).T)
    if len(viewpoints):
        v = viewpoints[None, :, :] - p[:, None, :]
        dist = np.linalg.norm(v, axis=2)
        with np.errstate(divide="ignore", invalid="ignore"):
            abs_cos[:, n_dir:] = np.abs(np.einsum("nk,nqk->nq", n, v)) / dist
    need_front = front.any(axis=1)
    score = np.where(need_front[:, None], np.where(front, abs_cos, -1.0), np.where(seen, abs_cos, -1.0))
    col = score.argmax(axis=1)

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


class _Judge:
    """What AFTER shows along a sample's line of sight, asked of the viewpoint that saw the sample in BEFORE.

    Two casts, both short, both started where float32 noise cannot matter:

    * COVERED. The same ray `visibility` cast in BEFORE (same origin, same direction), into AFTER. A
      first hit more than the tolerance in front of the sample, and before the viewpoint, covers it;
      a layer within the tolerance is the sample's own depth, and the ray looks beyond it. For AFTER =
      BEFORE this is BEFORE's own ray, so nothing can be reported that BEFORE did not see.
    * PRESENT. A ray from just outside the tolerance window, on the viewer's side, toward the sample.
      The first hit, if it is in the window, is judged; when it is not the whole story (another look,
      a coincident layer, nothing there), every face the short segment crosses is looked up by hand
      in float64, and the sample is met if ANY of them has its look, its UV and (when BEFORE saw its
      front) shows its front. Two layers in one place are both drawn in Unity, so either may answer.
    """

    def __init__(self, after: MeshData, caster, look_after: np.ndarray, tol: float):
        self.after, self.caster, self.look_a, self.tol = after, caster, look_after, tol
        self.n_faces = after.n_faces
        if self.n_faces:
            pos, fv = after.positions, after.face_v
            self.a0 = pos[fv[:, 0]]
            self.raw = np.cross(pos[fv[:, 1]] - self.a0, pos[fv[:, 2]] - self.a0)
            tri = pos[fv]
            self.face_lo, self.face_hi = tri.min(axis=1), tri.max(axis=1)

    # -- covered ---------------------------------------------------------------------------------
    def covered(self, p, w: _Witnesses) -> np.ndarray:
        n = len(p)
        covered = np.zeros(n, dtype=bool)
        if not self.n_faces or not n:
            return covered
        cur, travelled = w.origin.copy(), np.zeros(n)
        active = np.arange(n)
        for _ in range(_PEEL_MAX + 1):
            if not len(active):
                break
            tri, t = self.caster.first_hit(cur[active], w.dirn[active])
            hit = tri >= 0
            total = travelled[active] + np.where(hit, t, 0.0)
            blocks = hit & (w.is_dir[active] | (total < w.reach[active] - EPS_ORIGIN))
            q = cur[active] + np.where(hit, t, 0.0)[:, None] * w.dirn[active]
            in_front = np.einsum("ij,ij->i", q - p[active], w.toward[active])
            beyond = blocks & (in_front > self.tol)
            covered[active[beyond]] = True
            within = blocks & ~beyond                     # a layer inside the tolerance: look past it
            nxt = active[within]
            cur[nxt] = q[within] + w.dirn[nxt] * _PEEL_STEP
            travelled[nxt] = total[within] + _PEEL_STEP
            active = nxt
        return covered

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
        bounding-box prefilter and an exact float64 test, and reduced to a status per row."""
        m = len(rows)
        status = np.full(m, DELETED, dtype=np.int8)
        s0 = start[rows] + u[rows] * (t_b - self.tol)
        s1 = start[rows] + u[rows] * (t_b + self.tol)
        lo, hi = np.minimum(s0, s1) - 1e-6, np.maximum(s0, s1) + 1e-6
        block = max(1, _FALLBACK_PAIRS // max(self.n_faces, 1))
        pair_r, pair_f = [], []
        for k in range(0, m, block):
            near = ((lo[k:k + block, None, :] <= self.face_hi[None]) &
                    (hi[k:k + block, None, :] >= self.face_lo[None])).all(axis=2)
            r, f = np.nonzero(near)
            pair_r.append(r + k)
            pair_f.append(f)
        r, f = np.concatenate(pair_r), np.concatenate(pair_f)
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
# Check 2: problems solved
# ---------------------------------------------------------------------------------------------

def default_targets_path() -> Path:
    """Where the owner's signed targets live: `engine/validate/targets.json` (written when the owner signs)."""
    return Path(__file__).with_name("targets.json")


def load_targets(path=None) -> dict | None:
    """The targets file, parsed; None when there is none (the owner has not signed yet). `path` defaults
    to `default_targets_path()`. A file that is not JSON is a `ValueError`: an unreadable target must
    not quietly turn into "unsigned".

    The shape: `{"signed": true, "kinds": {"flicker_diff": 0, "hidden": {"max": 5, "note": "..."},
    "open_edges": null, ...}}`. A kind's target is the most `find_errors` may count of it after the fix
    (a number, or `{"max": n}`); null or absent means the kind is only listed."""
    path = default_targets_path() if path is None else Path(path)
    if not path.is_file():
        return None
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as exc:
        raise ValueError(f"targets file {path} is not valid JSON: {exc}") from exc


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

#: A sample covered by a face in front of it (a reason beside the `OK .. SIDE` codes of `_Judge.present`).
COVERED = 5
_REASON_NAMES = {COVERED: "covered", **_PRESENT_NAMES}


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

    @property
    def passed(self) -> bool:
        return self.report["verdict"] == "PASS"


def _rows_in(a: np.ndarray, b: np.ndarray) -> np.ndarray:
    """(len(a),) bool: row i of `a` is also a row of `b`."""
    keys = {row.tobytes() for row in np.ascontiguousarray(b)}
    return np.fromiter((row.tobytes() in keys for row in np.ascontiguousarray(a)), dtype=bool, count=len(a))


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
             progress=None) -> Validation:
    """Judge `after` against `before` by the owner's three checks.

    Both meshes are in the model's own coordinates; they are shifted into the Validator's frame here, by
    BEFORE's bounding-box centre for both. The viewpoints (`dirs`, `cams`, `probes`, `extra_dirs`) are
    BEFORE's and are made once, here, unless given; the probes are never recomputed for AFTER.
    `errors` is the `(before, after)` pair of `find_errors` results for check 2, run here when None.
    `progress(done, total)` is called after each chunk of samples."""
    clock = {"start": time.perf_counter()}
    step = print_step(before)
    tol = depth_tolerance(step)
    b, centre = recentred(before)
    a, _ = recentred(after, centre)
    caster_b = build_caster(b) if b.n_faces else None
    caster_a = build_caster(a) if a.n_faces else None

    lo, hi = used_bbox(b)
    dirs = _points(outside_directions(settings.n_directions) if dirs is None else dirs)
    cams = _points(pedestrian_ring((lo, hi), eye_z=lo[2] + settings.eye, n=settings.n_cameras,
                                   margin=settings.camera_margin) if cams is None else cams)
    if probes is None:
        probes = interior_probes(b, eye=settings.eye, caster=caster_b) if b.n_faces else np.zeros((0, 3))
    probes = _points(probes)
    extra_dirs = _points(outside_directions(settings.n_extra_directions) if extra_dirs is None else extra_dirs)
    nothing = np.zeros((0, 3))

    samples = face_samples(b, min_per_face=settings.min_per_face, area_per_sample=settings.area_per_sample)
    n = len(samples)
    per_face_samples = np.bincount(samples.face, minlength=b.n_faces)
    sample_area = face_areas(b)[samples.face] / np.maximum(per_face_samples[samples.face], 1)

    table = LookTable()
    look_b = face_look_ids(before, looks, table)
    look_a = face_look_ids(after, looks, table)
    sizes = [looks.texel.get(k) or (0, 0) for k in table.keys]
    tex_w = np.array([s[0] for s in sizes], dtype=np.float64)
    tex_h = np.array([s[1] for s in sizes], dtype=np.float64)
    suspect = ~_rows_in(face_fingerprints(before, step, look_b), face_fingerprints(after, step, look_a))
    clock["prepared"] = time.perf_counter()

    tested = np.zeros(n, dtype=bool)
    extra = np.zeros(n, dtype=bool)
    covered = np.zeros(n, dtype=bool)
    present = np.zeros(n, dtype=np.int8)
    wit_col = np.full(n, -1, dtype=np.int32)
    wit_extra = np.zeros(n, dtype=bool)
    normals_b = face_normals(b)
    judge = _Judge(a, caster_a, look_a, tol)

    def run(idx: np.ndarray, d: np.ndarray, c: np.ndarray, pr: np.ndarray, is_extra: bool) -> None:
        sub = Samples(points=samples.points[idx], face=samples.face[idx], bary=samples.bary[idx])
        vs = visible_samples(b, sub, d, c, pr, caster_b)
        rows = np.flatnonzero(vs.visible)
        if not len(rows):
            return
        w = _witnesses(vs, rows, sub.points, normals_b[sub.face])
        p, face = sub.points[rows], sub.face[rows]
        lb = look_b[face]
        g = idx[rows]
        covered[g] = judge.covered(p, w)
        present[g] = judge.present(p, w, lb, uv_at(b, face, sub.bary[rows]), tex_w[lb], tex_h[lb])
        tested[g], extra[g], wit_col[g], wit_extra[g] = True, is_extra, w.col, is_extra

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

    # ---- check 1 and check 3 from what every tested sample turned out to be ----
    standard = tested & ~extra
    reason1 = np.where(covered, COVERED, present).astype(np.int8)
    fail1 = standard & (reason1 != OK)
    unmet = tested & ((present == DELETED) | (present == LOOK))
    fail3 = tested & (covered | unmet)
    n_faces = b.n_faces
    per_face = lambda mask: np.bincount(samples.face[mask], minlength=n_faces)
    tested_per_face, unmet_per_face = per_face(tested), per_face(unmet)

    textures = {
        "status": "FAIL" if fail1.any() else "PASS", "samples": int(standard.sum()),
        "samples_failed": int(fail1.sum()), "faces": int((per_face(standard) > 0).sum()),
        "faces_failed": int((per_face(fail1) > 0).sum()), "area_failed_in2": round(float(sample_area[fail1].sum()), 2),
        "reasons": {name: int((fail1 & (reason1 == code)).sum()) for code, name in
                    ((COVERED, "covered"), (DELETED, "deleted"), (LOOK, "look"), (UV, "uv"), (SIDE, "side"))},
        "depth_tolerance_in": round(tol, 4)}
    nothing_deleted = {
        "status": "FAIL" if fail3.any() else "PASS", "samples": int(tested.sum()), "samples_extra": int(extra.sum()),
        "suspect_faces": int(suspect.sum()), "deleted": int((tested & ~covered & (present == DELETED)).sum()),
        "replaced": int((tested & ~covered & (present == LOOK)).sum()), "covered": int((tested & covered).sum()),
        "faces": int((tested_per_face > 0).sum()),
        "faces_unmet": int(((tested_per_face > 0) & (unmet_per_face == tested_per_face)).sum()),
        "faces_partly_unmet": int(((unmet_per_face > 0) & (unmet_per_face < tested_per_face)).sum()),
        "faces_covered": int((per_face(tested & covered) > 0).sum()),
        "area_lost_in2": round(float(sample_area[unmet].sum()), 2),
        "area_covered_in2": round(float(sample_area[tested & covered].sum()), 2),
        "depth_tolerance_in": round(tol, 4)}

    # ---- check 2 ----
    if errors is None:
        from engine.detectors.errors import find_errors    # lazy: it imports engine.fixes, .guard and .vis
        errors = (find_errors(before), find_errors(after))
    problems = check_problems(errors[0], errors[1], targets)
    clock["problems"] = time.perf_counter()

    # ---- the sites: failing samples, clustered ----
    failing = np.flatnonzero(fail1 | fail3)
    reason_all = np.where(extra, np.where(covered, COVERED, present), reason1).astype(np.int8)
    corners = b.positions[b.face_v]
    longest = np.max([np.linalg.norm(corners[:, i] - corners[:, (i + 1) % 3], axis=1) for i in range(3)], axis=0)
    spacing = (longest / np.sqrt(np.maximum(per_face_samples, 1)))[samples.face]       # n x n samples on a face
    sites, members, n_sites = _cluster_sites(samples.points, centre, failing, sample_area, samples.face, reason_all,
                                             fail1, fail3, spacing, settings.cluster_cell, settings.max_sites)
    clock["end"] = time.perf_counter()

    statuses = (textures["status"], problems["status"], nothing_deleted["status"])
    report = {
        "version": 1, "verdict": "FAIL" if "FAIL" in statuses else "PASS",
        "checks": {"textures": textures, "problems": problems, "nothing_deleted": nothing_deleted},
        "sites": sites, "sites_total": n_sites,
        "viewpoints": {"directions": len(dirs), "cameras": len(cams), "probes": len(probes),
                       "extra_directions": len(extra_dirs)},
        "settings": settings.as_dict(), "frame": {"centre": [round(float(v), 4) for v in centre]},
        "print_step_in": step, "depth_tolerance_in": tol,
        "before": {"faces": before.n_faces, "samples": n}, "after": {"faces": after.n_faces},
        "materials": {"unknown_before": looks.unknown(before), "unknown_after": looks.unknown(after)},
        "timings_s": {"prepare": round(clock["prepared"] - clock["start"], 2),
                      "visibility_and_casts": round(clock["cast"] - clock["prepared"], 2),
                      "extra_directions": round(clock["extra"] - clock["cast"], 2),
                      "problems": round(clock["problems"] - clock["extra"], 2),
                      "sites": round(clock["end"] - clock["problems"], 2),
                      "total": round(clock["end"] - clock["start"], 2)}}
    return Validation(report=report, before=b, after=a, centre=centre, looks=looks, look_keys=table.keys,
                      look_before=look_b, look_after=look_a, samples=samples, members=members, wit_col=wit_col,
                      wit_extra=wit_extra, viewpoints={"dirs": dirs, "cams": cams, "probes": probes,
                                                       "extra_dirs": extra_dirs})
