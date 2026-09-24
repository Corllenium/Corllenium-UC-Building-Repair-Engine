"""The fixed mesh as a SketchUp model (`.skp`), written and read back through SketchUp's own C API
(`SketchUpAPI.dll`, bound with ctypes -- the only module in `engine/` that imports ctypes).

WHY. After every fix run the owner opens the latest SketchUp file of each model in SketchUp 2026 to
check it. An OBJ cannot carry a hole and SketchUp's OBJ importer shows every triangle edge, so the
model is written natively: polygons with inner loops, only the outline edges visible.

WHAT IS WRITTEN (`write_skp`).

* One SketchUp face per merged region: every row of `rings` that shares one ring OBJECT is one
  polygon, grouped by identity exactly as `engine.io.obj_writer.write_obj_polygons` groups them,
  with `outer` as its outer loop and each of `inners` as an inner loop. Every other row is its own
  triangle. A region is written as its triangles instead, and listed in `fallback_regions` with
  the reason, when this DLL has no inner-loop call and the region has holes
  (`no_inner_loop_api`), when a loop keeps fewer than 3 distinct vertices (`degenerate_loop`),
  when its loop vertices are more than `plane_tol` off their least-squares plane (`nonplanar`),
  when SketchUp refuses or drops the polygon at the fill (`rejected_by_sketchup`), or when
  SketchUp's save still splits it (`split_by_sketchup`). The last two are found by matching
  SketchUp's own faces against the plan after the fill and again after the save, and the model is
  then rebuilt from scratch with that region as triangles. The save matters because
  `SUModelSaveToFile` applies SketchUp's validity fix to what it writes and splits a polygon it
  finds non-planar into triangles joined by HARD edges -- visible lines on a flat surface
  (measured: from about 1.2e-3 in off the plane; the export's 0.1 in print step leaves sloped
  and diagonal surfaces far off that).
* Coordinates pass through unchanged. SketchUp's internal unit is the inch, like the OBJ's, so
  the object drops back into the campus model where it came from. Vertices are welded exactly as
  the rest of the engine welds them (`weld_exact` at the mesh's printed precision), each welded
  vertex taking its lowest original row's position, and `SUEntitiesFill` welds as well.
* A triangle SketchUp cannot represent -- zero area by `engine.topo.adjacency.degenerate_mask`,
  or fewer than 3 distinct vertices -- is skipped and counted (`degenerate_faces_skipped`):
  SketchUp would drop the face and keep its edges as stray lines.
* After the fill each face's normal is compared with the area-weighted normal of the triangles it
  was built from, and a face that came out backwards is reversed (`reversed_faces`). Reversing
  mirrors a positioned texture (measured), so the texture is positioned again on both sides.
* Hidden edges. Every EDGE_SOFT crease and every EDGE_REMOVABLE gridline (two coplanar faces of
  one material, e.g. two triangles copied through) that exists in the SketchUp model -- every
  such edge that is not a diagonal inside one polygon face -- is set soft AND smooth, found by
  matching its two end points (within `EDGE_MATCH_TOL`) to the edges `SUEntitiesGetEdges`
  returns: `soft_edges`, `gridline_edges_softened`, `unmatched_edges`. Only outline edges stay
  visible.
* Materials. One SketchUp material per OBJ material (`mesh.materials`, in order), textured from
  `<tex_dir>/<file name of its map_Kd>` when that file exists, else coloured with its `Kd` (grey
  when it has neither). It is applied to the FRONT and the BACK of every face through
  `SUGeometryInputFaceSetFront/BackMaterial` (`material_path: "geometry_input"` -- measured
  reliable on this DLL through the UV helper), positioned with `SUMaterialInput` from 3
  non-collinear loop vertices and their UVs, each ring vertex's UV taken from any of the region's
  triangles. `uv_residual_regions` lists the polygon faces whose triangles' UVs are not one affine
  map to within `UV_RESIDUAL_TOL`: their texture cannot be reproduced exactly by one face.

READING BACK (`read_skp`, `read_skp_summary`, `check_skp_validity`) opens a file through
`SUModelCreateFromFile` and only queries it; `check_skp_validity` runs SketchUp's own
`SUModelFixErrors` on the IN-MEMORY model and reports whether it changed anything, and never
saves.

The DLL comes from the `dll_path` argument, else the `FIXER_SKETCHUP_DLL` environment variable,
else SketchUp 2026's default install path; every symbol is checked with ctypes before it is bound,
and anything missing raises `SketchUpUnavailable`, naming what is missing.
"""
from __future__ import annotations

import ctypes
import hashlib
import os
from contextlib import contextmanager
from ctypes import (POINTER, Structure, byref, c_bool, c_char_p, c_double, c_int, c_size_t,
                    c_ubyte, c_void_p)
from dataclasses import dataclass, field
from pathlib import Path, PurePosixPath
from typing import TYPE_CHECKING

import numpy as np

from engine.io.mtl import MtlMaterial
from engine.model import MeshData
from engine.topo.adjacency import edge_face_lists
from engine.topo.edges import EDGE_REMOVABLE, EDGE_SOFT
from engine.topo.weld import weld_exact

if TYPE_CHECKING:
    from engine.pipeline import Topology

#: Where SketchUp 2026 installs its C API.
DEFAULT_DLL = Path(r"C:\Program Files\SketchUp\SketchUp 2026\SketchUp\SketchUpAPI.dll")
#: Environment variable naming the DLL when `dll_path` is not given.
DLL_ENV = "FIXER_SKETCHUP_DLL"
#: Largest distance, in inches, of a polygon's loop vertices from their least-squares plane that
#: is still written as ONE face. SketchUp's own validity fixer splits a face from about 1.2e-3 in
#: (measured on this DLL: a quad's lifted corner splits it from 5.0e-3 in, which is 1.25e-3 off
#: the best fit; a 12-gon's single lifted vertex from 1.6e-3 in).
PLANE_TOL = 1e-3
#: An edge end point must lie this close, in inches, to the vertex it is matched to.
EDGE_MATCH_TOL = 1e-6
#: Largest residual of one affine UV map over a polygon face's triangles that is not reported.
UV_RESIDUAL_TOL = 1e-3
#: RGB for a material with neither a texture file nor a `Kd` line.
DEFAULT_RGB = (204, 204, 204)

_RESULT_NAMES = ("NONE", "NULL_POINTER_INPUT", "INVALID_INPUT", "NULL_POINTER_OUTPUT",
                 "INVALID_OUTPUT", "OVERWRITE_VALID", "GENERIC", "SERIALIZATION", "OUT_OF_RANGE",
                 "NO_DATA", "INSUFFICIENT_SIZE", "UNKNOWN_EXCEPTION", "MODEL_INVALID",
                 "MODEL_VERSION", "LAYER_LOCKED", "DUPLICATE", "PARTIAL_SUCCESS", "UNSUPPORTED",
                 "INVALID_ARGUMENT", "ENTITY_LOCKED", "INVALID_OPERATION")
_NO_DATA = 9


class SketchUpError(RuntimeError):
    """A SketchUp C API call failed."""


class SketchUpUnavailable(SketchUpError):
    """The SketchUp C API cannot be used here: there is no DLL at the resolved path, it would not
    load, or it lacks a symbol this module needs."""


# ------------------------------------------------------------------------------ C structures


class _Ref(Structure):
    """Every SketchUp `SU...Ref` is a struct holding one pointer, passed by value."""
    _fields_ = [("ptr", c_void_p)]


class _Point3D(Structure):
    _fields_ = [("x", c_double), ("y", c_double), ("z", c_double)]


class _Point2D(Structure):
    _fields_ = [("x", c_double), ("y", c_double)]


class _UVQ(Structure):
    _fields_ = [("u", c_double), ("v", c_double), ("q", c_double)]


class _Color(Structure):
    _fields_ = [("red", c_ubyte), ("green", c_ubyte), ("blue", c_ubyte), ("alpha", c_ubyte)]


class _MaterialInput(Structure):
    _fields_ = [("num_uv_coords", c_size_t), ("uv_coords", _Point2D * 4),
                ("vertex_indices", c_size_t * 4), ("material", _Ref)]


class _MaterialPositionInput(Structure):
    _fields_ = [("num_uv_coords", c_size_t), ("uv_coords", _Point2D * 4),
                ("points", _Point3D * 4), ("material", _Ref), ("projection", _Point3D)]


_RP = POINTER(_Ref)
_SP = POINTER(c_size_t)
_BP = POINTER(c_bool)

#: name -> (argtypes, restype). `SUResult` is a C enum, returned as an int.
_REQUIRED = {
    "SUInitialize": ([], None),
    "SUTerminate": ([], None),
    "SUGetAPIVersion": ([_SP, _SP], None),
    "SUModelCreate": ([_RP], c_int),
    "SUModelCreateFromFile": ([_RP, c_char_p], c_int),
    "SUModelRelease": ([_RP], c_int),
    "SUModelGetEntities": ([_Ref, _RP], c_int),
    "SUModelSaveToFile": ([_Ref, c_char_p], c_int),
    "SUModelAddMaterials": ([_Ref, c_size_t, _RP], c_int),
    "SUModelGetNumMaterials": ([_Ref, _SP], c_int),
    "SUModelGetMaterials": ([_Ref, c_size_t, _RP, _SP], c_int),
    "SUMaterialCreate": ([_RP], c_int),
    "SUMaterialRelease": ([_RP], c_int),
    "SUMaterialSetName": ([_Ref, c_char_p], c_int),
    "SUMaterialGetName": ([_Ref, _RP], c_int),
    "SUMaterialSetColor": ([_Ref, POINTER(_Color)], c_int),
    "SUMaterialGetColor": ([_Ref, POINTER(_Color)], c_int),
    "SUMaterialSetTexture": ([_Ref, _Ref], c_int),
    "SUMaterialGetTexture": ([_Ref, _RP], c_int),
    "SUTextureCreateFromFile": ([_RP, c_char_p, c_double, c_double], c_int),
    "SUTextureRelease": ([_RP], c_int),
    "SUStringCreate": ([_RP], c_int),
    "SUStringRelease": ([_RP], c_int),
    "SUStringGetUTF8Length": ([_Ref, _SP], c_int),
    "SUStringGetUTF8": ([_Ref, c_size_t, c_char_p, _SP], c_int),
    "SUGeometryInputCreate": ([_RP], c_int),
    "SUGeometryInputRelease": ([_RP], c_int),
    "SUGeometryInputSetVertices": ([_Ref, c_size_t, POINTER(_Point3D)], c_int),
    "SUGeometryInputAddFace": ([_Ref, _RP, _SP], c_int),
    "SUGeometryInputFaceSetFrontMaterial": ([_Ref, c_size_t, POINTER(_MaterialInput)], c_int),
    "SUGeometryInputFaceSetBackMaterial": ([_Ref, c_size_t, POINTER(_MaterialInput)], c_int),
    "SULoopInputCreate": ([_RP], c_int),
    "SULoopInputRelease": ([_RP], c_int),
    "SULoopInputAddVertexIndex": ([_Ref, c_size_t], c_int),
    "SUEntitiesFill": ([_Ref, _Ref, c_bool], c_int),
    "SUEntitiesGetNumFaces": ([_Ref, _SP], c_int),
    "SUEntitiesGetFaces": ([_Ref, c_size_t, _RP, _SP], c_int),
    "SUEntitiesGetNumEdges": ([_Ref, c_bool, _SP], c_int),
    "SUEntitiesGetEdges": ([_Ref, c_bool, c_size_t, _RP, _SP], c_int),
    "SUEdgeGetStartVertex": ([_Ref, _RP], c_int),
    "SUEdgeGetEndVertex": ([_Ref, _RP], c_int),
    "SUEdgeGetNumFaces": ([_Ref, _SP], c_int),
    "SUEdgeGetSoft": ([_Ref, _BP], c_int),
    "SUEdgeGetSmooth": ([_Ref, _BP], c_int),
    "SUEdgeSetSoft": ([_Ref, c_bool], c_int),
    "SUEdgeSetSmooth": ([_Ref, c_bool], c_int),
    "SUVertexGetPosition": ([_Ref, POINTER(_Point3D)], c_int),
    "SUFaceGetNormal": ([_Ref, POINTER(_Point3D)], c_int),
    "SUFaceReverse": ([_Ref], c_int),
    "SUFaceGetOuterLoop": ([_Ref, _RP], c_int),
    "SUFaceGetNumInnerLoops": ([_Ref, _SP], c_int),
    "SUFaceGetInnerLoops": ([_Ref, c_size_t, _RP, _SP], c_int),
    "SUFaceGetFrontMaterial": ([_Ref, _RP], c_int),
    "SUFaceGetBackMaterial": ([_Ref, _RP], c_int),
    "SUFaceGetUVHelper": ([_Ref, c_bool, c_bool, _Ref, _RP], c_int),
    "SUUVHelperGetFrontUVQ": ([_Ref, POINTER(_Point3D), POINTER(_UVQ)], c_int),
    "SUUVHelperGetBackUVQ": ([_Ref, POINTER(_Point3D), POINTER(_UVQ)], c_int),
    "SUUVHelperRelease": ([_RP], c_int),
    "SULoopGetNumVertices": ([_Ref, _SP], c_int),
    "SULoopGetVertices": ([_Ref, c_size_t, _RP, _SP], c_int),
    "SUMeshHelperCreate": ([_RP, _Ref], c_int),
    "SUMeshHelperRelease": ([_RP], c_int),
    "SUMeshHelperGetNumTriangles": ([_Ref, _SP], c_int),
    "SUMeshHelperGetNumVertices": ([_Ref, _SP], c_int),
    "SUMeshHelperGetVertexIndices": ([_Ref, c_size_t, _SP, _SP], c_int),
    "SUMeshHelperGetVertices": ([_Ref, c_size_t, POINTER(_Point3D), _SP], c_int),
}
#: Bound when present; each has a documented fallback when it is not.
_OPTIONAL = {
    "SUGeometryInputFaceAddInnerLoop": ([_Ref, c_size_t, _RP], c_int),
    "SUFacePositionMaterial": ([_Ref, c_bool, POINTER(_MaterialPositionInput)], c_int),
    "SUModelFixErrors": ([_Ref], c_int),
    "SUModelSetName": ([_Ref, c_char_p], c_int),
}


def _result_name(code: int) -> str:
    return f"SU_ERROR_{_RESULT_NAMES[code]}" if 0 <= code < len(_RESULT_NAMES) else f"SUResult {code}"


class _Api:
    """The bound DLL. `has_inner_loops`, `has_position_material` and `has_fix_errors` say which
    optional calls it offers."""

    def __init__(self, path: Path):
        self.path = path
        if not path.is_file():
            raise SketchUpUnavailable(
                f"SketchUp C API not found at {path} (pass dll_path or set {DLL_ENV})")
        try:
            # SketchUpAPI.dll loads companions from its own folder
            self._dll_dir = (os.add_dll_directory(str(path.parent))
                             if hasattr(os, "add_dll_directory") else None)
            self._dll = ctypes.CDLL(str(path))
        except OSError as exc:
            raise SketchUpUnavailable(f"SketchUp C API at {path} could not be loaded: {exc}") from exc
        missing = [name for name in _REQUIRED if not hasattr(self._dll, name)]
        if missing:
            raise SketchUpUnavailable(
                f"{path} lacks SketchUp C API symbol(s): {', '.join(missing)}")
        self._fn = {}
        for name, (argtypes, restype) in {**_REQUIRED, **_OPTIONAL}.items():
            if hasattr(self._dll, name):
                fn = getattr(self._dll, name)
                fn.argtypes, fn.restype = argtypes, restype
                self._fn[name] = fn
        self.has_inner_loops = "SUGeometryInputFaceAddInnerLoop" in self._fn
        self.has_position_material = "SUFacePositionMaterial" in self._fn
        self.has_fix_errors = "SUModelFixErrors" in self._fn

    def raw(self, name: str, *args) -> int:
        return self._fn[name](*args)

    def ok(self, name: str, *args) -> None:
        code = self._fn[name](*args)
        if code != 0:
            raise SketchUpError(f"{name} failed: {_result_name(code)}")

    @contextmanager
    def session(self):
        """`SUInitialize` ... `SUTerminate` around one read or write (measured: cycling them
        repeatedly in one process is fine)."""
        self._fn["SUInitialize"]()
        try:
            yield self
        finally:
            self._fn["SUTerminate"]()

    def version(self) -> str:
        major, minor = c_size_t(), c_size_t()
        self._fn["SUGetAPIVersion"](byref(major), byref(minor))
        return f"{major.value}.{minor.value}"


_LOADED: dict[Path, _Api] = {}


def resolve_dll_path(dll_path=None) -> Path:
    """`dll_path`, else `$FIXER_SKETCHUP_DLL`, else `DEFAULT_DLL`."""
    if dll_path:
        return Path(dll_path)
    env = os.environ.get(DLL_ENV)
    return Path(env) if env else DEFAULT_DLL


def load_api(dll_path=None) -> _Api:
    """The bound SketchUp C API for the resolved DLL, loaded once per path. Raises
    `SketchUpUnavailable` when the DLL is missing, will not load, or lacks a required symbol --
    a failure is not cached, so installing SketchUp later works without a restart."""
    path = resolve_dll_path(dll_path)
    api = _LOADED.get(path)
    if api is None:
        api = _LOADED[path] = _Api(path)
    return api


# --------------------------------------------------------------------------------- planning


@dataclass
class _Unit:
    """One entry of the write plan, in mesh row order: a merged region (its ring object) or one
    row copied through. `loops` are welded ids, `loops[0]` the outer loop; `None` for a region
    that is written as its triangles from the start."""
    region: int
    rows: list[int]
    loops: list[list[int]] | None


@dataclass
class _Face:
    """One face handed to `SUEntitiesFill`."""
    unit: int
    polygon: bool
    loops: list[list[int]]
    rows: list[int]
    material: int
    normal: np.ndarray
    uv: dict[int, np.ndarray]
    uv_pick: list[int] | None


@dataclass
class _Context:
    positions: np.ndarray        # per welded id: its lowest original row's position, unchanged
    positions_w: np.ndarray      # per welded id: the weld's own rounded key
    face_w: np.ndarray           # mesh rows as welded ids
    tri_normal: np.ndarray       # per row, cross product of its edges (not normalised)
    ok: np.ndarray               # per row, not degenerate
    decimals: int
    units: list[_Unit]
    fallback_regions: list[dict] = field(default_factory=list)


def _clean_loop(ids) -> list[int]:
    """`ids` with consecutive repeats (cyclically) folded: SketchUp refuses a loop that repeats
    a vertex in a row (`SULoopInputAddVertexIndex`: SU_ERROR_INVALID_ARGUMENT, measured)."""
    out: list[int] = []
    for v in (int(i) for i in ids):
        if not out or out[-1] != v:
            out.append(v)
    while len(out) > 1 and out[-1] == out[0]:
        out.pop()
    return out


def _plane_deviation(points: np.ndarray) -> float:
    centred = points - points.mean(axis=0)
    _, _, vt = np.linalg.svd(centred, full_matrices=False)
    return float(np.abs(centred @ vt[-1]).max())


def _unit_vector(v: np.ndarray) -> np.ndarray:
    n = float(np.linalg.norm(v))
    return v / n if n > 0.0 else v


def _plane_basis(normal: np.ndarray) -> tuple[np.ndarray, np.ndarray]:
    axis = np.eye(3)[int(np.argmin(np.abs(normal)))]
    e1 = _unit_vector(np.cross(normal, axis))
    return e1, np.cross(normal, e1)


def _plan(mesh: MeshData, rings: dict, face_region: np.ndarray, topo: "Topology",
          plane_tol: float, inner_loops: bool) -> _Context:
    positions_w, remap = weld_exact(mesh.positions, mesh.coord_decimals)
    if len(positions_w) != len(topo.positions_w) or len(topo.ok) != mesh.n_faces:
        raise ValueError("topo was not computed on this mesh: analyse_topology(mesh) first")
    lowest = np.full(len(positions_w), np.iinfo(np.int64).max, np.int64)
    np.minimum.at(lowest, remap, np.arange(len(mesh.positions), dtype=np.int64))
    positions = mesh.positions[lowest]
    face_w = remap[mesh.face_v]
    p = positions[face_w]
    ctx = _Context(positions=positions, positions_w=positions_w, face_w=face_w,
                   tri_normal=np.cross(p[:, 1] - p[:, 0], p[:, 2] - p[:, 0]),
                   ok=np.asarray(topo.ok, bool), decimals=mesh.coord_decimals, units=[])

    rows_of: dict[int, list[int]] = {}
    for row, loops in rings.items():
        rows_of.setdefault(id(loops), []).append(int(row))
    done: set[int] = set()
    for f in range(mesh.n_faces):
        loops = rings.get(f)
        if loops is None:
            ctx.units.append(_Unit(int(face_region[f]), [f], None))
            continue
        if id(loops) in done:
            continue
        done.add(id(loops))
        rows = sorted(rows_of[id(loops)])
        region = int(face_region[rows[0]])
        polygon = [_clean_loop(remap[np.asarray(loop, np.int64)])
                   for loop in [loops["outer"], *loops["inners"]]]
        reason, extra = None, {}
        if any(len(loop) < 3 for loop in polygon):
            reason = "degenerate_loop"
        elif len(polygon) > 1 and not inner_loops:
            reason = "no_inner_loop_api"
        else:
            deviation = _plane_deviation(positions[np.concatenate(polygon)])
            if deviation > plane_tol:
                reason, extra = "nonplanar", {"deviation": round(deviation, 6)}
        if reason is not None:
            ctx.fallback_regions.append({"region": region, "reason": reason, **extra})
            polygon = None
        ctx.units.append(_Unit(region, rows, polygon))
    return ctx


def _uv_of(mesh: MeshData, ctx: _Context, rows: list[int]) -> dict[int, np.ndarray]:
    """Welded id -> UV, from the first of `rows`' triangle corners that carries one."""
    out: dict[int, np.ndarray] = {}
    for r in rows:
        for w, t in zip(ctx.face_w[r], mesh.face_vt[r]):
            if t >= 0:
                out.setdefault(int(w), mesh.uvs[int(t)])
    return out


def _uv_pick(loop: list[int], uv: dict[int, np.ndarray], positions: np.ndarray):
    """Three loop vertices with UVs spanning the face as widely as possible (the first, the one
    farthest from it, the one farthest from their line), or `None` when no such non-collinear
    triple with a non-degenerate UV triangle exists."""
    cand = [w for w in loop if w in uv]
    if len(cand) < 3:
        return None
    pts = positions[cand]
    b = int(np.argmax(np.linalg.norm(pts - pts[0], axis=1)))
    cross = np.linalg.norm(np.cross(pts[b] - pts[0], pts - pts[0]), axis=1)
    c = int(np.argmax(cross))
    if cross[c] <= 1e-9 * max(float(np.linalg.norm(pts[b] - pts[0])) ** 2, 1e-300):
        return None
    ua, ub, uc = uv[cand[0]], uv[cand[b]], uv[cand[c]]
    if abs((ub[0] - ua[0]) * (uc[1] - ua[1]) - (ub[1] - ua[1]) * (uc[0] - ua[0])) <= 1e-12:
        return None
    return [cand[0], cand[b], cand[c]]


def _uv_residual(mesh: MeshData, ctx: _Context, rows: list[int], normal: np.ndarray):
    """Largest residual of ONE affine map (plane coordinates -> UV) fitted by least squares to
    every UV-carrying triangle corner of `rows`; `None` without 3 such corners."""
    corners = [(w, t) for r in rows for w, t in zip(ctx.face_w[r], mesh.face_vt[r]) if t >= 0]
    if len(corners) < 3:
        return None
    pts = ctx.positions[[w for w, _ in corners]]
    uv = mesh.uvs[[t for _, t in corners]]
    e1, e2 = _plane_basis(normal)
    centred = pts - pts.mean(axis=0)
    a = np.column_stack([centred @ e1, centred @ e2, np.ones(len(centred))])
    coef, *_ = np.linalg.lstsq(a, uv, rcond=None)
    return float(np.abs(a @ coef - uv).max())


def _expand(mesh: MeshData, ctx: _Context, rejected: dict[int, str]) -> tuple[list[_Face], int]:
    """The faces to write: each polygon unit as one face unless it is in `rejected`, every other
    row as its own triangle. Returns `(faces, degenerate triangles skipped)`."""
    faces: list[_Face] = []
    skipped = 0

    def face(unit, polygon, loops, rows):
        uv = _uv_of(mesh, ctx, rows)
        normal = _unit_vector(ctx.tri_normal[rows].sum(axis=0))
        faces.append(_Face(unit, polygon, loops, rows, int(mesh.face_material[rows[0]]), normal,
                           uv, _uv_pick(loops[0], uv, ctx.positions)))

    for u, unit in enumerate(ctx.units):
        if unit.loops is not None and u not in rejected:
            face(u, True, unit.loops, unit.rows)
            continue
        for r in unit.rows:
            loop = _clean_loop(ctx.face_w[r])
            if len(loop) < 3 or not ctx.ok[r]:
                skipped += 1
                continue
            face(u, False, [loop], [r])
    return faces, skipped


# ---------------------------------------------------------------------------------- materials


def _kd(mat: MtlMaterial | None):
    if mat is None:
        return None
    for line in mat.lines:
        parts = line.split()
        if parts[:1] == ["Kd"] and len(parts) >= 4:
            try:
                rgb = [min(max(float(x), 0.0), 1.0) for x in parts[1:4]]
            except ValueError:
                return None
            return tuple(int(round(c * 255.0)) for c in rgb)
    return None


def _texture_file(mat: MtlMaterial | None, tex_dir) -> Path | None:
    if mat is None or not mat.map_kd or tex_dir is None:
        return None
    candidate = Path(tex_dir) / PurePosixPath(mat.map_kd.replace("\\", "/")).name
    return candidate if candidate.is_file() else None


def _add_materials(api: _Api, model: _Ref, mesh: MeshData, mtl_materials: dict,
                   tex_dir) -> tuple[list[_Ref], list[bool], list[dict]]:
    refs: list[_Ref] = []
    try:
        textured, report = [], []
        for name in mesh.materials:
            mat = _Ref()
            api.ok("SUMaterialCreate", byref(mat))
            refs.append(mat)
            api.ok("SUMaterialSetName", mat, name.encode("utf-8"))
            src = mtl_materials.get(name)
            entry = {"name": name, "texture": None, "color": None}
            tex_file = _texture_file(src, tex_dir)
            if tex_file is not None:
                tex = _Ref()
                if api.raw("SUTextureCreateFromFile", byref(tex), str(tex_file).encode("utf-8"),
                           1.0, 1.0) == 0:
                    if api.raw("SUMaterialSetTexture", mat, tex) == 0:
                        entry["texture"] = tex_file.name
                    else:
                        api.raw("SUTextureRelease", byref(tex))
            if entry["texture"] is None:
                rgb = _kd(src) or DEFAULT_RGB
                api.ok("SUMaterialSetColor", mat, byref(_Color(*rgb, 255)))
                entry["color"] = list(rgb)
            textured.append(entry["texture"] is not None)
            report.append(entry)
        if refs:
            api.ok("SUModelAddMaterials", model, len(refs), (_Ref * len(refs))(*refs))
    except Exception:
        for mat in refs:
            api.raw("SUMaterialRelease", byref(mat))
        raise
    return refs, textured, report


# ------------------------------------------------------------------------------------ writing


def _loop_input(api: _Api, ids: list[int]) -> _Ref | None:
    loop = _Ref()
    api.ok("SULoopInputCreate", byref(loop))
    for i in ids:
        if api.raw("SULoopInputAddVertexIndex", loop, i) != 0:
            api.raw("SULoopInputRelease", byref(loop))
            return None
    return loop


def _material_input(face: _Face, material: _Ref, textured: bool,
                    index_of: dict[int, int]) -> _MaterialInput:
    mi = _MaterialInput()
    mi.material = material
    if textured and face.uv_pick is not None:
        mi.num_uv_coords = 3
        for k, w in enumerate(face.uv_pick):
            mi.vertex_indices[k] = index_of[w]
            mi.uv_coords[k] = _Point2D(*(float(c) for c in face.uv[w]))
    return mi


def _fill(api: _Api, entities: _Ref, faces: list[_Face], ctx: _Context,
          materials: list[_Ref], textured: list[bool]):
    """Hand `faces` to one `SUEntitiesFill`. Returns `(index_of, rejected, rejected_triangles)`:
    `rejected` maps the unit of every polygon SketchUp refused to take to a reason (the caller
    rebuilds without it), `rejected_triangles` counts triangles it refused."""
    used = sorted({v for face in faces for loop in face.loops for v in loop})
    index_of = {w: k for k, w in enumerate(used)}
    rejected: dict[int, str] = {}
    rejected_triangles = 0
    geom = _Ref()
    api.ok("SUGeometryInputCreate", byref(geom))
    try:
        if used:
            points = np.ascontiguousarray(ctx.positions[used], dtype=np.float64)
            api.ok("SUGeometryInputSetVertices", geom, len(used),
                   (_Point3D * len(used)).from_buffer_copy(points.tobytes()))
        for face in faces:
            outer = _loop_input(api, [index_of[w] for w in face.loops[0]])
            index = c_size_t()
            code = -1 if outer is None else api.raw("SUGeometryInputAddFace", geom, byref(outer),
                                                    byref(index))
            if code != 0:
                if outer is not None:
                    api.raw("SULoopInputRelease", byref(outer))
                if face.polygon:
                    rejected[face.unit] = "rejected_by_sketchup"
                    return index_of, rejected, rejected_triangles
                rejected_triangles += 1
                continue
            for inner_ids in face.loops[1:]:
                inner = _loop_input(api, [index_of[w] for w in inner_ids])
                if inner is None or api.raw("SUGeometryInputFaceAddInnerLoop", geom, index.value,
                                            byref(inner)) != 0:
                    if inner is not None:
                        api.raw("SULoopInputRelease", byref(inner))
                    rejected[face.unit] = "rejected_by_sketchup"
                    return index_of, rejected, rejected_triangles
            if face.material >= 0:
                mi = _material_input(face, materials[face.material], textured[face.material],
                                     index_of)
                for side in ("SUGeometryInputFaceSetFrontMaterial",
                             "SUGeometryInputFaceSetBackMaterial"):
                    code = api.raw(side, geom, index.value, byref(mi))
                    if code == 0:
                        continue
                    if not mi.num_uv_coords:
                        raise SketchUpError(f"{side} failed: {_result_name(code)}")
                    mi.num_uv_coords = 0                # a UV map SketchUp will not take
                    face.uv_pick = None
                    api.ok(side, geom, index.value, byref(mi))
        api.ok("SUEntitiesFill", entities, geom, True)
    finally:
        api.raw("SUGeometryInputRelease", byref(geom))
    return index_of, rejected, rejected_triangles


def _refs(api: _Api, count_fn: str, get_fn: str, owner: _Ref, *flag) -> list[_Ref]:
    n = c_size_t()
    api.ok(count_fn, owner, *flag, byref(n))
    if n.value == 0:
        return []
    arr = (_Ref * n.value)()
    got = c_size_t()
    api.ok(get_fn, owner, *flag, n.value, arr, byref(got))
    return list(arr[:got.value])


def _position(api: _Api, vertex: _Ref) -> tuple[float, float, float]:
    p = _Point3D()
    api.ok("SUVertexGetPosition", vertex, byref(p))
    return (p.x, p.y, p.z)


def _loop_positions(api: _Api, loop: _Ref) -> list[tuple[float, float, float]]:
    return [_position(api, v) for v in _refs(api, "SULoopGetNumVertices", "SULoopGetVertices", loop)]


def _outer_loop(api: _Api, face: _Ref) -> list[tuple[float, float, float]]:
    loop = _Ref()
    api.ok("SUFaceGetOuterLoop", face, byref(loop))
    return _loop_positions(api, loop)


def _normal(api: _Api, face: _Ref) -> np.ndarray:
    n = _Point3D()
    api.ok("SUFaceGetNormal", face, byref(n))
    return np.array([n.x, n.y, n.z])


class _Welded:
    """SketchUp position -> welded id, via the weld's own rounded key, confirmed within
    `EDGE_MATCH_TOL` of the position this writer handed SketchUp."""

    def __init__(self, ctx: _Context):
        self.ctx = ctx
        self.key = {tuple(row): w for w, row in enumerate(ctx.positions_w.tolist())}

    def __call__(self, p) -> int | None:
        w = self.key.get(tuple((np.round(np.asarray(p, float), self.ctx.decimals) + 0.0).tolist()))
        if w is None or np.linalg.norm(self.ctx.positions[w] - np.asarray(p)) > EDGE_MATCH_TOL:
            return None
        return w


def _position_material(api: _Api, sk_face: _Ref, face: _Face, material: _Ref,
                       ctx: _Context) -> None:
    mp = _MaterialPositionInput()
    mp.material = material
    mp.num_uv_coords = 3
    for k, w in enumerate(face.uv_pick):
        mp.points[k] = _Point3D(*(float(c) for c in ctx.positions[w]))
        mp.uv_coords[k] = _Point2D(*(float(c) for c in face.uv[w]))
    for front in (True, False):
        api.ok("SUFacePositionMaterial", sk_face, front, byref(mp))


@dataclass
class _Built:
    rejected: dict[int, str]
    report: dict


@dataclass
class _Matched:
    sk_faces: list[_Ref]
    pairs: list[tuple[_Ref, int]]      # SketchUp face, index of the planned face it is
    missing: list[int]                 # planned faces SketchUp does not have
    unexpected: int                    # SketchUp faces no planned face explains
    merged: int                        # planned faces sharing another's SketchUp face


def _match(api: _Api, entities: _Ref, faces: list[_Face], welded: _Welded) -> _Matched:
    """Pair every SketchUp face with the planned face whose outer loop has the same vertices."""
    by_outer: dict[frozenset, list[int]] = {}
    for i, face in enumerate(faces):
        by_outer.setdefault(frozenset(face.loops[0]), []).append(i)
    sk_faces = _refs(api, "SUEntitiesGetNumFaces", "SUEntitiesGetFaces", entities)
    pairs, matched = [], set()
    unexpected = merged = 0
    for sk_face in sk_faces:
        ids = [welded(p) for p in _outer_loop(api, sk_face)]
        planned = by_outer.get(frozenset(ids)) if None not in ids else None
        if not planned:
            unexpected += 1
            continue
        matched.update(planned)
        merged += len(planned) - 1
        pairs.append((sk_face, planned[0]))
    return _Matched(sk_faces, pairs, [i for i in range(len(faces)) if i not in matched],
                    unexpected, merged)


def _build(api: _Api, mesh: MeshData, faces: list[_Face], ctx: _Context, topo: "Topology",
           mtl_materials: dict, tex_dir, path: Path) -> _Built:
    """One attempt: a new model, filled, checked, fixed up and saved -- or, when SketchUp refused,
    dropped or split a polygon, the units to write as triangles instead.

    The check runs twice, after the fill and again after the SAVE: `SUModelSaveToFile` applies
    SketchUp's own validity fix to the model it writes, and splits a polygon it finds non-planar
    into triangles joined by HARD edges (measured: a 5-vertex ring 0.042 in off its plane is 1
    face after the fill and 3 after the save). So every count reported is taken after the save,
    from the model as written."""
    model = _Ref()
    api.ok("SUModelCreate", byref(model))
    try:
        if "SUModelSetName" in api._fn:
            api.raw("SUModelSetName", model, mesh.name.encode("utf-8"))
        entities = _Ref()
        api.ok("SUModelGetEntities", model, byref(entities))
        materials, textured, material_report = _add_materials(api, model, mesh, mtl_materials,
                                                              tex_dir)
        _, rejected, rejected_triangles = _fill(api, entities, faces, ctx, materials, textured)
        if rejected:
            return _Built(rejected, {})

        welded = _Welded(ctx)
        filled = _match(api, entities, faces, welded)
        dropped = {faces[i].unit: "rejected_by_sketchup" for i in filled.missing
                   if faces[i].polygon}
        if dropped:
            return _Built(dropped, {})
        reversed_faces = unpositioned = 0
        for sk_face, i in filled.pairs:
            face = faces[i]
            if float(_normal(api, sk_face) @ face.normal) >= 0.0:
                continue
            api.ok("SUFaceReverse", sk_face)
            reversed_faces += 1
            if face.material >= 0 and textured[face.material] and face.uv_pick is not None:
                # reversing mirrors a positioned texture (measured): position it again
                if api.has_position_material:
                    _position_material(api, sk_face, face, materials[face.material], ctx)
                else:
                    unpositioned += 1

        edge_report = _soften_edges(api, entities, faces, topo, welded)
        api.ok("SUModelSaveToFile", model, str(path).encode("utf-8"))

        saved = _match(api, entities, faces, welded)
        split = {faces[i].unit: "split_by_sketchup" for i in saved.missing if faces[i].polygon}
        if split:
            return _Built(split, {})
        sk_edges = _refs(api, "SUEntitiesGetNumEdges", "SUEntitiesGetEdges", entities, False)
        report = {
            "faces": len(saved.sk_faces),
            "faces_input": len(faces),
            "polygon_faces": sum(1 for f in faces if f.polygon),
            "triangle_faces": sum(1 for f in faces if not f.polygon),
            "inner_loops": sum(len(f.loops) - 1 for f in faces),
            "faces_missing": len(saved.missing) + rejected_triangles,
            "faces_unexpected": saved.unexpected,
            "coincident_faces_merged": saved.merged,
            "reversed_faces": reversed_faces,
            "reversed_faces_unpositioned": unpositioned,
            "uv_unpositioned_faces": sum(1 for f in faces if f.material >= 0
                                         and textured[f.material] and f.uv_pick is None),
            **edge_report,
            "edges": len(sk_edges),
            "edges_without_face": sum(1 for e in sk_edges if _edge_face_count(api, e) == 0),
            "materials": material_report,
        }
        return _Built({}, report)
    finally:
        api.raw("SUModelRelease", byref(model))


def _edge_face_count(api: _Api, edge: _Ref) -> int:
    n = c_size_t()
    api.ok("SUEdgeGetNumFaces", edge, byref(n))
    return int(n.value)


def _soften_edges(api: _Api, entities: _Ref, faces: list[_Face], topo: "Topology",
                  welded: _Welded) -> dict:
    """Set soft AND smooth every EDGE_SOFT / EDGE_REMOVABLE edge SketchUp has: all of them but
    the diagonals inside one polygon face, which SketchUp does not have at all."""
    sk_edges = _refs(api, "SUEntitiesGetNumEdges", "SUEntitiesGetEdges", entities, False)
    by_key: dict[tuple[int, int], _Ref] = {}
    for edge in sk_edges:
        ends = []
        for getter in ("SUEdgeGetStartVertex", "SUEdgeGetEndVertex"):
            v = _Ref()
            api.ok(getter, edge, byref(v))
            ends.append(welded(_position(api, v)))
        if None not in ends:
            by_key[(min(ends), max(ends))] = edge

    face_of_row = {r: i for i, f in enumerate(faces) for r in f.rows}
    polygon = {i for i, f in enumerate(faces) if f.polygon}
    counts = {"soft_edges": 0, "gridline_edges_softened": 0, "unmatched_edges": 0}
    for e, faces_of_edge in enumerate(edge_face_lists(topo.table)):
        cls = int(topo.edge_class[e])
        if cls not in (EDGE_SOFT, EDGE_REMOVABLE):
            continue
        written = {face_of_row.get(int(r), -1) for r in faces_of_edge}
        if len(written) == 1 and next(iter(written)) in polygon:
            continue                      # a diagonal inside one polygon face: not a SketchUp edge
        a, b = (int(v) for v in topo.table.edges[e])
        edge = by_key.get((min(a, b), max(a, b)))
        if edge is None:
            counts["unmatched_edges"] += 1
            continue
        api.ok("SUEdgeSetSoft", edge, True)
        api.ok("SUEdgeSetSmooth", edge, True)
        counts["soft_edges" if cls == EDGE_SOFT else "gridline_edges_softened"] += 1
    return counts


def write_skp(mesh: MeshData, rings: dict, face_region: np.ndarray, topo: "Topology",
              mtl_materials: dict[str, MtlMaterial], path, *, tex_dir=None, dll_path=None,
              plane_tol: float = PLANE_TOL) -> dict:
    """Write `mesh` to `path` as a SketchUp model and return what was written (see the module
    docstring for what and why).

    `rings` and `face_region` are `FixResult.rings` / `FixResult.face_region_final` (or
    `MergeResult.rings` / `.face_region`) for this `mesh`; `topo` is
    `engine.pipeline.analyse_topology(mesh, ...)` of THIS mesh, whose edge classes decide which
    edges are hidden; `mtl_materials` is `engine.io.mtl.parse_mtl` of the run's `materials.mtl`
    and `tex_dir` the run directory's `tex/`. Raises `SketchUpUnavailable` before touching
    `path` when the SketchUp C API cannot be used, `SketchUpError` when a call fails."""
    api = load_api(dll_path)
    path = Path(path)
    ctx = _plan(mesh, rings, face_region, topo, plane_tol, api.has_inner_loops)
    path.parent.mkdir(parents=True, exist_ok=True)
    rejected: dict[int, str] = {}
    with api.session():
        version = api.version()
        # each round moves at least one more region to its triangles, so this ends
        for _ in range(len(ctx.units) + 1):
            faces, skipped = _expand(mesh, ctx, rejected)
            built = _build(api, mesh, faces, ctx, topo, mtl_materials, tex_dir, path)
            if not built.rejected:
                break
            if set(built.rejected) <= set(rejected):
                raise SketchUpError("SketchUp refused faces the writer had already rebuilt")
            rejected.update(built.rejected)
        else:  # pragma: no cover - the loop above always breaks or raises
            raise SketchUpError("SketchUp model could not be built")

    fallback = list(ctx.fallback_regions) + [
        {"region": ctx.units[u].region, "reason": reason} for u, reason in sorted(rejected.items())]
    residuals = []
    for face in faces:
        if face.polygon:
            residual = _uv_residual(mesh, ctx, face.rows, face.normal)
            if residual is not None and residual > UV_RESIDUAL_TOL:
                residuals.append({"region": ctx.units[face.unit].region,
                                  "residual": round(residual, 6)})
    report = built.report
    return {"path": str(path), "api_version": version, "material_path": "geometry_input",
            **{k: report[k] for k in ("faces", "faces_input", "polygon_faces", "triangle_faces",
                                      "inner_loops", "faces_missing", "faces_unexpected",
                                      "coincident_faces_merged")},
            "degenerate_faces_skipped": skipped,
            **{k: report[k] for k in ("edges", "edges_without_face", "soft_edges",
                                      "gridline_edges_softened", "unmatched_edges",
                                      "reversed_faces", "reversed_faces_unpositioned",
                                      "uv_unpositioned_faces")},
            "fallback_regions": fallback, "uv_residual_regions": residuals,
            "materials": report["materials"]}


# ------------------------------------------------------------------------------------ reading


@dataclass
class SkpFace:
    """One face read back: loops as `(n, 3)` positions in loop order, its normal, the names of
    its front/back materials (`None` without one), the UV SketchUp maps each OUTER loop vertex to
    on each side (`None` unless that side's material is textured and UVs were asked for), and
    SketchUp's own triangulation of it (`(t, 3, 3)`, empty unless asked for)."""
    outer: np.ndarray
    inners: list[np.ndarray]
    normal: np.ndarray
    front_material: str | None
    back_material: str | None
    front_uv: np.ndarray | None
    back_uv: np.ndarray | None
    triangles: np.ndarray


@dataclass
class SkpEdge:
    start: np.ndarray
    end: np.ndarray
    soft: bool
    smooth: bool
    faces: int


@dataclass
class SkpMaterial:
    name: str
    textured: bool
    color: tuple[int, int, int, int] | None


@dataclass
class SkpModel:
    faces: list[SkpFace]
    edges: list[SkpEdge]
    materials: list[SkpMaterial]


def _string(api: _Api, getter: str, owner: _Ref) -> str:
    s = _Ref()
    api.ok("SUStringCreate", byref(s))
    try:
        api.ok(getter, owner, byref(s))
        n = c_size_t()
        api.ok("SUStringGetUTF8Length", s, byref(n))
        buf = ctypes.create_string_buffer(n.value + 1)
        got = c_size_t()
        api.ok("SUStringGetUTF8", s, n.value + 1, buf, byref(got))
        return buf.value.decode("utf-8")
    finally:
        api.raw("SUStringRelease", byref(s))


def _read_material(api: _Api, mat: _Ref) -> SkpMaterial:
    tex = _Ref()
    textured = api.raw("SUMaterialGetTexture", mat, byref(tex)) == 0
    color = _Color()
    has_color = api.raw("SUMaterialGetColor", mat, byref(color)) == 0
    return SkpMaterial(_string(api, "SUMaterialGetName", mat), textured,
                       (color.red, color.green, color.blue, color.alpha) if has_color else None)


def _face_uv(api: _Api, face: _Ref, outer: np.ndarray, front: bool, back: bool):
    uvh = _Ref()
    api.ok("SUFaceGetUVHelper", face, front, back, _Ref(), byref(uvh))
    try:
        out = []
        for getter, wanted in (("SUUVHelperGetFrontUVQ", front), ("SUUVHelperGetBackUVQ", back)):
            if not wanted:
                out.append(None)
                continue
            uv = np.empty((len(outer), 2))
            for k, p in enumerate(outer):
                q = _UVQ()
                api.ok(getter, uvh, byref(_Point3D(*(float(c) for c in p))), byref(q))
                uv[k] = (q.u / q.q, q.v / q.q)
            out.append(uv)
        return out
    finally:
        api.raw("SUUVHelperRelease", byref(uvh))


def _face_triangles(api: _Api, face: _Ref) -> np.ndarray:
    helper = _Ref()
    api.ok("SUMeshHelperCreate", byref(helper), face)
    try:
        nt, nv, got = c_size_t(), c_size_t(), c_size_t()
        api.ok("SUMeshHelperGetNumTriangles", helper, byref(nt))
        api.ok("SUMeshHelperGetNumVertices", helper, byref(nv))
        idx = (c_size_t * (3 * nt.value))()
        api.ok("SUMeshHelperGetVertexIndices", helper, 3 * nt.value, idx, byref(got))
        pts = (_Point3D * nv.value)()
        api.ok("SUMeshHelperGetVertices", helper, nv.value, pts, byref(got))
        verts = np.frombuffer(pts, dtype=np.float64).reshape(-1, 3)
        return verts[np.frombuffer(idx, dtype=np.uint64).astype(np.int64)].reshape(-1, 3, 3).copy()
    finally:
        api.raw("SUMeshHelperRelease", byref(helper))


@contextmanager
def _open(api: _Api, path: Path):
    if not path.is_file():
        raise FileNotFoundError(path)
    model = _Ref()
    api.ok("SUModelCreateFromFile", byref(model), str(path).encode("utf-8"))
    try:
        yield model
    finally:
        api.raw("SUModelRelease", byref(model))


def _read_model(api: _Api, model: _Ref, uvs: bool, triangles: bool) -> SkpModel:
    materials: dict[int, SkpMaterial] = {}
    for mat in _refs(api, "SUModelGetNumMaterials", "SUModelGetMaterials", model):
        materials[mat.ptr] = _read_material(api, mat)

    def face_material(getter: str, face: _Ref):
        mat = _Ref()
        if api.raw(getter, face, byref(mat)) != 0 or not mat.ptr:
            return None
        if mat.ptr not in materials:
            materials[mat.ptr] = _read_material(api, mat)
        return materials[mat.ptr]

    entities = _Ref()
    api.ok("SUModelGetEntities", model, byref(entities))
    faces = []
    for face in _refs(api, "SUEntitiesGetNumFaces", "SUEntitiesGetFaces", entities):
        outer = np.array(_outer_loop(api, face), dtype=np.float64).reshape(-1, 3)
        inners = [np.array(_loop_positions(api, loop), dtype=np.float64).reshape(-1, 3)
                  for loop in _refs(api, "SUFaceGetNumInnerLoops", "SUFaceGetInnerLoops", face)]
        front = face_material("SUFaceGetFrontMaterial", face)
        back = face_material("SUFaceGetBackMaterial", face)
        front_uv = back_uv = None
        want_front = uvs and front is not None and front.textured
        want_back = uvs and back is not None and back.textured
        if want_front or want_back:
            front_uv, back_uv = _face_uv(api, face, outer, want_front, want_back)
        faces.append(SkpFace(outer, inners, _normal(api, face),
                             None if front is None else front.name,
                             None if back is None else back.name, front_uv, back_uv,
                             _face_triangles(api, face) if triangles else np.zeros((0, 3, 3))))
    edges = []
    for edge in _refs(api, "SUEntitiesGetNumEdges", "SUEntitiesGetEdges", entities, False):
        ends = []
        for getter in ("SUEdgeGetStartVertex", "SUEdgeGetEndVertex"):
            v = _Ref()
            api.ok(getter, edge, byref(v))
            ends.append(np.array(_position(api, v)))
        soft, smooth, n = c_bool(), c_bool(), c_size_t()
        api.ok("SUEdgeGetSoft", edge, byref(soft))
        api.ok("SUEdgeGetSmooth", edge, byref(smooth))
        api.ok("SUEdgeGetNumFaces", edge, byref(n))
        edges.append(SkpEdge(ends[0], ends[1], bool(soft.value), bool(smooth.value), int(n.value)))
    model_materials = [materials[m.ptr] for m in
                       _refs(api, "SUModelGetNumMaterials", "SUModelGetMaterials", model)]
    return SkpModel(faces, edges, model_materials)


def read_skp(path, *, dll_path=None, uvs: bool = True, triangles: bool = True) -> SkpModel:
    """Every face, edge and material of the SketchUp file at `path`, read through
    `SUModelCreateFromFile` -- the file is only queried, never written."""
    api = load_api(dll_path)
    with api.session(), _open(api, Path(path)) as model:
        return _read_model(api, model, uvs, triangles)


def _summary(model: SkpModel) -> dict:
    ends = np.array([p for e in model.edges for p in (e.start, e.end)]).reshape(-1, 3)
    bbox = [ends.min(axis=0).tolist(), ends.max(axis=0).tolist()] if len(ends) else None
    return {"faces": len(model.faces), "edges": len(model.edges),
            "soft_edges": sum(e.soft for e in model.edges),
            "smooth_edges": sum(e.smooth for e in model.edges),
            "edges_without_face": sum(e.faces == 0 for e in model.edges),
            "materials": len(model.materials),
            "material_names": [m.name for m in model.materials],
            "textured_materials": sum(m.textured for m in model.materials),
            "loops_with_inners": sum(1 for f in model.faces if f.inners),
            "inner_loops": sum(len(f.inners) for f in model.faces),
            "bbox": bbox}


def read_skp_summary(path, *, dll_path=None) -> dict:
    """`faces`, `edges`, `soft_edges`, `smooth_edges`, `edges_without_face`, `materials`,
    `material_names`, `textured_materials`, `loops_with_inners`, `inner_loops` and `bbox`
    (`[[min x, y, z], [max x, y, z]]` over every edge end point, in the file's own inches) of
    the SketchUp file at `path`. Read only."""
    return _summary(read_skp(path, dll_path=dll_path, uvs=False, triangles=False))


def _fingerprint(api: _Api, model: _Ref) -> dict:
    m = _read_model(api, model, uvs=False, triangles=False)
    digest = hashlib.sha256()
    for face in sorted(m.faces, key=lambda f: (np.round(f.outer, 6).tolist(),
                                               np.round(f.normal, 6).tolist())):
        digest.update(repr((sorted(np.round(face.outer, 6).tolist()),
                            np.round(face.normal, 6).tolist(),
                            [sorted(np.round(i, 6).tolist()) for i in face.inners])).encode())
    summary = _summary(m)
    return {k: summary[k] for k in ("faces", "edges", "soft_edges", "inner_loops")} | {
        "geometry_sha256": digest.hexdigest()}


def check_skp_validity(path, *, dll_path=None) -> dict:
    """Would SketchUp's own validity check change the file at `path`? Loads it, runs
    `SUModelFixErrors` on the IN-MEMORY model (the check SketchUp runs when it opens a file) and
    compares faces, edges, soft edges, inner loops and a digest of every face's loops and normal
    before and after: `{"changed": bool, "before": {...}, "after": {...}}`. Never saves."""
    api = load_api(dll_path)
    if not api.has_fix_errors:
        raise SketchUpUnavailable(f"{api.path} lacks SUModelFixErrors")
    with api.session(), _open(api, Path(path)) as model:
        before = _fingerprint(api, model)
        api.ok("SUModelFixErrors", model)
        after = _fingerprint(api, model)
    return {"changed": before != after, "before": before, "after": after}
