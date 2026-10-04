"""The Validator's three checks, on a BEFORE and an AFTER of one floor (AGENTS.md section 6).

Written for the Validator and independent of the code it judges (see `engine.validate`). The one
exception is check 2, which has to run `engine.detectors.errors.find_errors` on both meshes, and that
module imports `engine.fixes`, `engine.guard` and `engine.vis`: so it is imported LAZILY, inside
`check_problems`'s caller, and nowhere else. Loading this module loads none of them.

A look key (`data/campus/materials.json`: texture sha256 + Kd + d) is the identity of what a face
looks like, never a `usemtl` number. A face's look is `looks.key[mesh.materials[face_material]]`.
"""
from __future__ import annotations

import hashlib
import json
import struct
from dataclasses import dataclass, field
from pathlib import Path
from typing import Sequence

import numpy as np

from engine.model import MeshData

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
