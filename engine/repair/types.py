"""The typed foundation of the repair engines (phase P1): `Edit`, `FaceKey`, `face_keys`, `apply_edits`.

Every repair engine (E1..E8) PLANS: it reads a `UnitState` and returns a list of `Edit`s. Nothing
here decides what is safe to change; `apply_edits` only performs edits that were already approved,
and refuses a plan that contradicts itself.

Rules that live in this file (AGENTS.md section 3-4):
- Only the E5 cut and the E8 flat fill may bring `new_points`; an `Edit` from any other engine that
  carries some raises `ValueError` at construction. E5 may bring them only in a "cut", E8 only in an
  "add" or "cut", never in a "remove" or "flip"; they must be finite. `new_faces` / `new_points` are
  copied on construction and read-only afterwards.
- This package computes its own print step from the OBJ's printed precision
  (`10 ** -mesh.coord_decimals`) and never imports `engine/validate`: the validator is the
  independent judge and does not import this package either.

Conventions for `apply_edits`
- Output face order: the surviving input faces in their original order, then the faces of every
  "add"/"cut" edit in edit order. The returned `new_to_old` map holds the input face id of each
  surviving face and -1 for every appended face (a cut's pieces count as appended).
- `flip` reverses `face_v` and `face_vt`; `face_vn` becomes -1 for all three corners, exactly as
  `engine.fixes.orient.flip_faces` does (reordering a normal INDEX does not turn a normal VECTOR).
- `new_faces` of an edit index the vertices of the INPUT mesh; ids `n .. n + m - 1` (n = rows of
  `mesh.positions`, m = rows of that edit's own `new_points`) name the edit's own new points, so
  every edit counts its points from n. `apply_edits` appends the points in edit order and renumbers.
- Appended faces have no UVs and no normals (`face_vt` / `face_vn` = -1; no vertex or UV is ever
  invented here). A "cut" inherits the material (and the lowest source line) of the faces it
  replaces, and raises if those faces do not all have one material; an "add" has no source face and must say its material: `evidence["material"]` (int
  index into `mesh.materials`).
"""
from __future__ import annotations

import hashlib
from dataclasses import dataclass, field, replace
from typing import TYPE_CHECKING, Any, Protocol

import numpy as np

from engine.model import MeshData

if TYPE_CHECKING:  # annotations only; keeps the heavy pipeline module out of this import
    from engine.fixes.pipeline import FixProfile

FaceKey = str  # sha256 hex of the 3 snapped vertices (winding kept, start vertex canonical) + look key

ENGINES = tuple(f"E{i}" for i in range(1, 9))
KINDS = ("remove", "flip", "add", "cut")
POINT_ENGINES = ("E5", "E8")  # the E5 cut (points on the winner's border) and E8 solidify only
POINT_KINDS = {"E5": ("cut",), "E8": ("add", "cut")}  # the kinds in which those engines may bring points


@dataclass(frozen=True, eq=False)  # ndarray fields: equality is never used (controller ruling K1-R1)
class Edit:
    engine: str                    # "E1" .. "E8"
    kind: str                      # "remove" | "flip" | "add" | "cut"
    faces: tuple[int, ...]         # input face ids it removes, flips or replaces
    new_faces: np.ndarray | None   # (k, 3) vertex ids for "add" / "cut"
    new_points: np.ndarray | None  # (m, 3) new positions: only E8 solidify and the E5 cut
    site: int
    reason: str
    evidence: dict                 # the numbers behind it: exposure, coverage, areas, look keys
    decision: dict | None = None   # {"question", "provider", "answer", "confidence"} when the Decider was asked

    def __post_init__(self) -> None:
        if self.engine not in ENGINES:
            raise ValueError(f"unknown engine {self.engine!r}; expected one of {ENGINES}")
        if self.kind not in KINDS:
            raise ValueError(f"unknown edit kind {self.kind!r}; expected one of {KINDS}")
        object.__setattr__(self, "faces", tuple(int(f) for f in self.faces))
        if self.kind in ("remove", "flip", "cut") and not self.faces:
            raise ValueError(f"a {self.kind!r} edit needs input faces")
        if self.kind == "add" and self.faces:
            raise ValueError("an 'add' edit replaces no input faces")

        if self.new_faces is not None:
            new_faces = np.array(self.new_faces, np.int64, copy=True)
            if new_faces.ndim != 2 or new_faces.shape[1] != 3:
                raise ValueError(f"new_faces must be (k, 3), got {new_faces.shape}")
            new_faces.flags.writeable = False
            object.__setattr__(self, "new_faces", new_faces)
        if self.kind in ("add", "cut") and (self.new_faces is None or not len(self.new_faces)):
            raise ValueError(f"a {self.kind!r} edit needs new_faces")
        if self.kind in ("remove", "flip") and self.new_faces is not None and len(self.new_faces):
            raise ValueError(f"a {self.kind!r} edit takes no new_faces")

        if self.new_points is not None:
            new_points = np.array(self.new_points, np.float64, copy=True)
            if new_points.ndim != 2 or new_points.shape[1] != 3:
                raise ValueError(f"new_points must be (m, 3), got {new_points.shape}")
            if len(new_points):
                if self.engine not in POINT_ENGINES:
                    raise ValueError(
                        f"engine {self.engine} may not add new_points; only {POINT_ENGINES} may "
                        f"(AGENTS.md: only solidify and the E5 cut invent vertices)")
                if self.kind not in POINT_KINDS[self.engine]:
                    raise ValueError(
                        f"engine {self.engine} may bring new_points only in a {POINT_KINDS[self.engine]} "
                        f"edit, not {self.kind!r} (E5: points on the winner's border; E8: solidify)")
                if not np.isfinite(new_points).all():
                    raise ValueError("new_points must be finite (no NaN or inf)")
            new_points.flags.writeable = False
            object.__setattr__(self, "new_points", new_points)


@dataclass
class UnitState:
    mesh: MeshData
    topo: Any                      # engine.pipeline topology of `mesh`
    looks: dict[int, str]          # material index -> look key (texture + colour)
    viewpoints: Any                # the unit's outside and eye-height viewpoints
    neighbours: list[MeshData] = field(default_factory=list)  # read-only context (floors above and below)


@dataclass
class RepairContext:
    profile: FixProfile
    decider: Any
    validator: Any
    log: list = field(default_factory=list)


class RepairEngine(Protocol):
    name: str

    def plan(self, unit: UnitState, ctx: RepairContext) -> list[Edit]: ...


def print_step(mesh: MeshData) -> float:
    """The OBJ's printed precision as a length: 10 ** -coord_decimals (K1-R2; never the validator's)."""
    return 10.0 ** -int(mesh.coord_decimals)


def _lex_less(a: np.ndarray, b: np.ndarray) -> np.ndarray:
    """Row-wise lexicographic `a < b` for (F, k) integer arrays."""
    differ = a != b
    first = differ.argmax(axis=1)
    rows = np.arange(len(a))
    return differ.any(axis=1) & (a[rows, first] < b[rows, first])


def face_keys(mesh: MeshData, looks: dict[int, str]) -> list[FaceKey]:
    """One `FaceKey` per face: sha256 over the face's 3 vertices snapped to the print step, with the
    winding kept but the starting vertex canonical (the lexicographically smallest rotation), plus the
    face's look key (`looks[material index]`, else `"material:<name>"`).

    Stable when faces are reordered or the vertex array is reordered or duplicated (it hashes
    positions, never ids); different for another look and for a flipped winding."""
    n = mesh.n_faces
    if n == 0:
        return []
    snapped = np.rint(np.asarray(mesh.positions, np.float64)[mesh.face_v] / print_step(mesh)).astype(np.int64)
    best = snapped.reshape(n, 9)
    for shift in (1, 2):
        candidate = np.roll(snapped, -shift, axis=1).reshape(n, 9)
        better = _lex_less(candidate, best)
        best = np.where(better[:, None], candidate, best)
    best = np.ascontiguousarray(best.astype("<i8"))

    look_of: dict[int, bytes] = {}
    out: list[FaceKey] = []
    for i in range(n):
        material = int(mesh.face_material[i])
        look = look_of.get(material)
        if look is None:
            name = looks.get(material)
            if name is None:
                name = f"material:{mesh.materials[material]}"
            look = look_of[material] = name.encode("utf-8")
        out.append(hashlib.sha256(best[i].tobytes() + b"|" + look).hexdigest())
    return out


def apply_edits(mesh: MeshData, edits: list[Edit]) -> tuple[MeshData, np.ndarray]:
    """Perform approved `edits` on `mesh`: returns the new mesh and the new->old face map (see the
    module docstring for the conventions). `mesh` is never modified; no edits gives an equal copy and
    the identity map. Edits that touch the same input face raise `ValueError` ("conflicting edits")."""
    n_faces, n_points = mesh.n_faces, len(mesh.positions)

    touched: dict[int, int] = {}
    for index, edit in enumerate(edits):
        if len(set(edit.faces)) != len(edit.faces):
            raise ValueError(f"conflicting edits: edit {index} ({edit.engine} {edit.kind}) names a face twice")
        for face in edit.faces:
            if not 0 <= face < n_faces:
                raise ValueError(f"edit {index} ({edit.engine} {edit.kind}) names face {face}, "
                                 f"but the mesh has {n_faces} faces")
            if face in touched:
                raise ValueError(f"conflicting edits: face {face} is touched by edit {touched[face]} "
                                 f"and edit {index}")
            touched[face] = index

    drop = np.zeros(n_faces, bool)
    flip = np.zeros(n_faces, bool)
    for edit in edits:
        if edit.kind == "flip":
            flip[list(edit.faces)] = True
        elif edit.kind in ("remove", "cut"):
            drop[list(edit.faces)] = True

    added_v: list[np.ndarray] = []
    added_material: list[np.ndarray] = []
    added_line: list[np.ndarray] = []
    added_points: list[np.ndarray] = []
    next_point = n_points
    for index, edit in enumerate(edits):
        if edit.kind not in ("add", "cut"):
            continue
        local = np.zeros((0, 3)) if edit.new_points is None else edit.new_points
        new_faces = edit.new_faces
        if (new_faces < 0).any() or (new_faces >= n_points + len(local)).any():
            raise ValueError(f"edit {index} ({edit.engine} {edit.kind}) uses a vertex id outside "
                             f"0..{n_points + len(local) - 1}")
        added_v.append(np.where(new_faces >= n_points, new_faces - n_points + next_point, new_faces))
        added_points.append(local)
        next_point += len(local)

        if edit.kind == "cut":
            materials = np.unique(mesh.face_material[list(edit.faces)])
            if len(materials) != 1:
                raise ValueError(f"edit {index} ({edit.engine} cut) replaces faces of different "
                                 f"materials {materials.tolist()}; a cut covers one material only")
            material = int(materials[0])
            line = int(mesh.face_line[list(edit.faces)].min())
        else:
            material = edit.evidence.get("material")
            if material is None:
                raise ValueError(f"edit {index} ({edit.engine} add) must name its material "
                                 f"in evidence['material']")
            material, line = int(material), -1
            if not 0 <= material < len(mesh.materials):
                raise ValueError(f"edit {index} ({edit.engine} add) names material {material}, "
                                 f"but the mesh has {len(mesh.materials)}")
        added_material.append(np.full(len(new_faces), material, np.int64))
        added_line.append(np.full(len(new_faces), line, np.int64))

    keep = np.flatnonzero(~drop)
    face_v = mesh.face_v[keep].copy()
    face_vt = mesh.face_vt[keep].copy()
    face_vn = mesh.face_vn[keep].copy()
    flipped = flip[keep]
    face_v[flipped] = face_v[flipped][:, ::-1]
    face_vt[flipped] = face_vt[flipped][:, ::-1]
    face_vn[flipped] = -1
    face_material = mesh.face_material[keep].copy()
    face_line = mesh.face_line[keep].copy()
    new_to_old = keep.astype(np.int64)

    if added_v:
        extra = sum(len(a) for a in added_v)
        face_v = np.vstack([face_v, *added_v]).astype(mesh.face_v.dtype)
        face_vt = np.vstack([face_vt, np.full((extra, 3), -1, mesh.face_vt.dtype)])
        face_vn = np.vstack([face_vn, np.full((extra, 3), -1, mesh.face_vn.dtype)])
        face_material = np.concatenate([face_material, *added_material]).astype(mesh.face_material.dtype)
        face_line = np.concatenate([face_line, *added_line]).astype(mesh.face_line.dtype)
        new_to_old = np.concatenate([new_to_old, np.full(extra, -1, np.int64)])

    positions = mesh.positions.copy()
    if next_point > n_points:
        positions = np.vstack([positions, *added_points])

    out = replace(mesh, positions=positions, uvs=mesh.uvs.copy(), normals=mesh.normals.copy(),
                  face_v=face_v, face_vt=face_vt, face_vn=face_vn, face_material=face_material,
                  face_line=face_line, materials=list(mesh.materials))
    return out, new_to_old
