"""A SketchUp model read through SketchUp's own C API (`SketchUpAPI.dll`, bound with ctypes), and
only read: this module binds no call that saves, so a model it opens cannot be written back.

WHY. The owner's CHECKPOINT-17 backup is the source of truth. This is how the engine looks inside
it without ever opening SketchUp: `walk_skp` returns, for the model's top level and for every
group and component instance below it, what a person looking at that model would see there --
face count, triangle count, face area and bounding box in WORLD coordinates (every transform
from the model down is composed) -- so the OBJ export can be checked against it
(`engine.campus.skp_check`).

THE WALK (`walk_skp`). A tree of plain dicts, JSON-ready:

* `root`: the model's top level, `kind` `"model"`. Every other node is a `"group"` or an
  `"instance"` (a component instance: `name` is the instance's own name, `definition` the name
  of its component definition). A node's numbers are for ITS OWN faces only, in world
  coordinates; `children` are the groups and instances inside it, `skipped` the ones that were
  not walked and why.
* `faces`, `tris`, `area`, `bbox` (`[[x, y, z], [x, y, z]]`, `None` without faces),
  `hidden_faces`, `layer_hidden_faces`. A face counts as `tris` triangles: the number a
  triangulation that uses every vertex and adds none needs -- its vertices over all loops, plus
  two for each hole, minus two. Measured against SketchUp's own OBJ export of CHECKPOINT-17 this
  is exact wherever the export has every face of a group (many material groups agree to the
  triangle), and larger by the triangles the export lacks where it does not.
* `area` scales each face's own area by the world transform: for a linear part `A` and a face
  with unit normal `n`, the area is multiplied by `|det A| * |A^-T n|`, which is `s^2` for a
  uniform scale `s` and depends on the face's plane for any other transform.
* Hidden things are not part of the model a viewer sees, and the OBJ exporter leaves them out:
  a group, instance or face that `SUDrawingElementGetHidden` reports hidden, or whose tag
  (layer) `SULayerGetVisibility` reports off, is skipped -- with everything inside it -- and
  counted (`hidden_faces`, `layer_hidden_faces`, `skipped`, `totals`).

SDK OBJECTS. Only the model and the strings it creates are owned: both are released on every
path out (`SUModelRelease`, `SUStringRelease`). Every group, instance, definition, face, vertex
and layer reference belongs to the model and dies with it.

The DLL comes from the `dll_path` argument, else the `FIXER_SKETCHUP_DLL` environment variable,
else SketchUp 2026's default install path, exactly as in `engine.io.skp_writer`; every symbol is
checked with ctypes before it is bound, and anything missing raises `SketchUpUnavailable`.
"""
from __future__ import annotations

import argparse
import ctypes
import json
import os
import sys
import tempfile
import time
from contextlib import contextmanager
from ctypes import (POINTER, Structure, byref, c_bool, c_char_p, c_double, c_int, c_size_t,
                    c_ulonglong, c_void_p)
from pathlib import Path

import numpy as np

from engine.io.skp_writer import SketchUpError, SketchUpUnavailable, resolve_dll_path

_RESULT_NAMES = ("NONE", "NULL_POINTER_INPUT", "INVALID_INPUT", "NULL_POINTER_OUTPUT",
                 "INVALID_OUTPUT", "OVERWRITE_VALID", "GENERIC", "SERIALIZATION", "OUT_OF_RANGE",
                 "NO_DATA", "INSUFFICIENT_SIZE", "UNKNOWN_EXCEPTION", "MODEL_INVALID",
                 "MODEL_VERSION", "LAYER_LOCKED", "DUPLICATE", "PARTIAL_SUCCESS", "UNSUPPORTED",
                 "INVALID_ARGUMENT", "ENTITY_LOCKED", "INVALID_OPERATION")


# ------------------------------------------------------------------------------ C structures


class _Ref(Structure):
    """Every SketchUp `SU...Ref` is a struct holding one pointer, passed by value."""
    _fields_ = [("ptr", c_void_p)]


class _Point3D(Structure):
    _fields_ = [("x", c_double), ("y", c_double), ("z", c_double)]


class _Transformation(Structure):
    """`SUTransformation`: a 4 x 4 matrix, 16 doubles in column-major order."""
    _fields_ = [("values", c_double * 16)]


_RP = POINTER(_Ref)
_SP = POINTER(c_size_t)
_BP = POINTER(c_bool)
_DP = POINTER(c_double)

#: name -> (argtypes, restype). `SUResult` is a C enum, returned as an int. Nothing here writes.
_REQUIRED = {
    "SUInitialize": ([], None),
    "SUTerminate": ([], None),
    "SUGetAPIVersion": ([_SP, _SP], None),
    "SUModelCreateFromFile": ([_RP, c_char_p], c_int),
    "SUModelRelease": ([_RP], c_int),
    "SUModelGetEntities": ([_Ref, _RP], c_int),
    "SUEntitiesGetNumGroups": ([_Ref, _SP], c_int),
    "SUEntitiesGetGroups": ([_Ref, c_size_t, _RP, _SP], c_int),
    "SUEntitiesGetNumInstances": ([_Ref, _SP], c_int),
    "SUEntitiesGetInstances": ([_Ref, c_size_t, _RP, _SP], c_int),
    "SUGroupGetName": ([_Ref, _RP], c_int),
    "SUGroupGetTransform": ([_Ref, POINTER(_Transformation)], c_int),
    "SUGroupGetEntities": ([_Ref, _RP], c_int),
    "SUComponentInstanceGetName": ([_Ref, _RP], c_int),
    "SUComponentInstanceGetTransform": ([_Ref, POINTER(_Transformation)], c_int),
    "SUComponentInstanceGetDefinition": ([_Ref, _RP], c_int),
    "SUComponentDefinitionGetName": ([_Ref, _RP], c_int),
    "SUComponentDefinitionGetEntities": ([_Ref, _RP], c_int),
    "SUEntitiesGetNumFaces": ([_Ref, _SP], c_int),
    "SUEntitiesGetFaces": ([_Ref, c_size_t, _RP, _SP], c_int),
    "SUFaceGetArea": ([_Ref, _DP], c_int),
    "SUFaceGetNormal": ([_Ref, POINTER(_Point3D)], c_int),
    "SUFaceGetNumVertices": ([_Ref, _SP], c_int),
    "SUFaceGetVertices": ([_Ref, c_size_t, _RP, _SP], c_int),
    "SUFaceGetNumInnerLoops": ([_Ref, _SP], c_int),
    "SUFaceToDrawingElement": ([_Ref], _Ref),
    "SUGroupToDrawingElement": ([_Ref], _Ref),
    "SUComponentInstanceToDrawingElement": ([_Ref], _Ref),
    "SUVertexGetPosition": ([_Ref, POINTER(_Point3D)], c_int),
    "SUDrawingElementGetHidden": ([_Ref, _BP], c_int),
    "SUStringCreate": ([_RP], c_int),
    "SUStringRelease": ([_RP], c_int),
    "SUStringGetUTF8Length": ([_Ref, _SP], c_int),
    "SUStringGetUTF8": ([_Ref, c_size_t, c_char_p, _SP], c_int),
}
#: Bound when present; each has a documented fallback when it is not: without the two tag calls
#: a tag that is switched off cannot be told, and `walk_skp` says so (`layers_bound`).
_OPTIONAL = {
    "SUDrawingElementGetLayer": ([_Ref, _RP], c_int),
    "SULayerGetVisibility": ([_Ref, _BP], c_int),
}


def _result_name(code: int) -> str:
    return f"SU_ERROR_{_RESULT_NAMES[code]}" if 0 <= code < len(_RESULT_NAMES) else f"SUResult {code}"


class _Api:
    """The bound DLL: the read-only calls of `_REQUIRED` and `_OPTIONAL`, and nothing else."""

    def __init__(self, path: Path):
        self.path = path
        if not path.is_file():
            raise SketchUpUnavailable(
                f"SketchUp C API not found at {path} (pass dll_path or set FIXER_SKETCHUP_DLL)")
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

    def raw(self, name: str, *args):
        return self._fn[name](*args)

    def ok(self, name: str, *args) -> None:
        code = self._fn[name](*args)
        if code != 0:
            raise SketchUpError(f"{name} failed: {_result_name(code)}")

    @contextmanager
    def session(self):
        """`SUInitialize` ... `SUTerminate` around one read."""
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


def load_api(dll_path=None) -> _Api:
    """The bound read-only SketchUp C API for the resolved DLL, loaded once per path. Raises
    `SketchUpUnavailable` when the DLL is missing, will not load, or lacks a required symbol --
    a failure is not cached."""
    path = resolve_dll_path(dll_path)
    api = _LOADED.get(path)
    if api is None:
        api = _LOADED[path] = _Api(path)
    return api


# -------------------------------------------------------------------------------- reading


def _refs(api: _Api, count_fn: str, get_fn: str, owner: _Ref) -> list[_Ref]:
    n = c_size_t()
    api.ok(count_fn, owner, byref(n))
    if n.value == 0:
        return []
    arr = (_Ref * n.value)()
    got = c_size_t()
    api.ok(get_fn, owner, n.value, arr, byref(got))
    return list(arr[:got.value])


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


class _Visibility:
    """Would a viewer see this entity? `reason` says why not: `"hidden"` (the entity itself is
    hidden) or `"layer"` (its tag is switched off -- only when this DLL has the two tag calls,
    `tags`)."""

    def __init__(self, api: _Api):
        self.api = api
        self.tags = "SUDrawingElementGetLayer" in api._fn and "SULayerGetVisibility" in api._fn
        self._visible: dict[int, bool] = {}

    def reason(self, element: _Ref) -> str | None:
        api = self.api
        flag = c_bool()
        api.ok("SUDrawingElementGetHidden", element, byref(flag))
        if flag.value:
            return "hidden"
        if self.tags:
            layer = _Ref()
            if api.raw("SUDrawingElementGetLayer", element, byref(layer)) == 0 and layer.ptr:
                if layer.ptr not in self._visible:
                    api.ok("SULayerGetVisibility", layer, byref(flag))
                    self._visible[layer.ptr] = bool(flag.value)
                if not self._visible[layer.ptr]:
                    return "layer"
        return None


class _Faces:
    """The faces directly in one entities collection that a viewer sees, in the collection's own
    coordinates: per face its area and unit normal, plus the distinct vertex positions."""

    def __init__(self, api: _Api, entities: _Ref, visibility: _Visibility):
        self.hidden = 0
        self.layer_hidden = 0
        areas, normals = [], []
        positions: dict[int, tuple[float, float, float]] = {}
        self.tris = 0
        area, normal, point = c_double(), _Point3D(), _Point3D()
        count, got = c_size_t(), c_size_t()
        for face in _refs(api, "SUEntitiesGetNumFaces", "SUEntitiesGetFaces", entities):
            reason = visibility.reason(api.raw("SUFaceToDrawingElement", face))
            if reason is not None:
                if reason == "hidden":
                    self.hidden += 1
                else:
                    self.layer_hidden += 1
                continue
            api.ok("SUFaceGetArea", face, byref(area))
            api.ok("SUFaceGetNormal", face, byref(normal))
            api.ok("SUFaceGetNumVertices", face, byref(count))
            vertices = (_Ref * count.value)()
            api.ok("SUFaceGetVertices", face, count.value, vertices, byref(got))
            holes = c_size_t()
            api.ok("SUFaceGetNumInnerLoops", face, byref(holes))
            self.tris += got.value + 2 * holes.value - 2
            for vertex in vertices[:got.value]:
                if vertex.ptr not in positions:
                    api.ok("SUVertexGetPosition", vertex, byref(point))
                    positions[vertex.ptr] = (point.x, point.y, point.z)
            areas.append(area.value)
            normals.append((normal.x, normal.y, normal.z))
        self.count = len(areas)
        self.areas = np.array(areas, float)
        self.normals = np.array(normals, float).reshape(-1, 3)
        self.points = np.array(list(positions.values()), float).reshape(-1, 3)

    def in_world(self, world: np.ndarray) -> tuple[float, list | None]:
        """`(area, bbox)` of these faces under the 4 x 4 transform `world`."""
        if not self.count:
            return 0.0, None
        linear = world[:3, :3]
        det = abs(float(np.linalg.det(linear)))
        if det == 0.0:
            scale = np.zeros(self.count)
        else:
            scale = det * np.linalg.norm(self.normals @ np.linalg.inv(linear), axis=1)
        moved = self.points @ linear.T + world[:3, 3]
        return float(self.areas @ scale), [moved.min(axis=0).tolist(), moved.max(axis=0).tolist()]


def _string(api: _Api, getter: str, owner: _Ref) -> str:
    """A SketchUp string property (`getter` is the SDK call) as text; the string is released."""
    string = _Ref()
    api.ok("SUStringCreate", byref(string))
    try:
        api.ok(getter, owner, byref(string))
        n = c_size_t()
        api.ok("SUStringGetUTF8Length", string, byref(n))
        buf = ctypes.create_string_buffer(n.value + 1)
        got = c_size_t()
        api.ok("SUStringGetUTF8", string, n.value + 1, buf, byref(got))
        return buf.value.decode("utf-8", errors="replace")
    finally:
        api.raw("SUStringRelease", byref(string))


def _matrix(transformation: _Transformation) -> np.ndarray:
    """`SUTransformation` (column-major) as a 4 x 4 matrix acting on column vectors.

    SketchUp keeps a uniform scale `s` in the last element, as `w = 1 / s`, and divides the whole map
    by it (measured: with `w = 0.5` and a move of 10 a group is twice as big and moved 20). So the
    matrix is divided by `w`, which leaves the last row `0 0 0 1`. Anything else in that row is not an
    affine transformation, and is refused rather than misread."""
    m = np.array(transformation.values, float).reshape(4, 4, order="F")
    w = m[3, 3]
    if np.any(m[3, :3] != 0.0) or w == 0.0 or not np.isfinite(w):
        raise SketchUpError(f"not an affine transformation: its last row is {m[3].tolist()}")
    m = m / w
    m[3] = (0.0, 0.0, 0.0, 1.0)
    return m


class _Walker:
    def __init__(self, api: _Api):
        self.api = api
        self.visibility = _Visibility(api)
        self._faces: dict[int, _Faces] = {}
        self.totals = dict.fromkeys(("groups", "instances", "faces", "tris", "hidden_nodes",
                                     "layer_hidden_nodes", "hidden_faces", "layer_hidden_faces"), 0)

    def faces(self, entities: _Ref) -> _Faces:
        """The faces of `entities`, read once however many instances share them."""
        if entities.ptr not in self._faces:
            self._faces[entities.ptr] = _Faces(self.api, entities, self.visibility)
        return self._faces[entities.ptr]

    def children(self, entities: _Ref):
        """`(kind, name, definition, reason, local transform, entities)` of each group, then each
        component instance, directly in `entities`; `reason` is why a viewer does not see it
        (`None` when it does)."""
        api = self.api
        for group in _refs(api, "SUEntitiesGetNumGroups", "SUEntitiesGetGroups", entities):
            inner, local = _Ref(), _Transformation()
            api.ok("SUGroupGetEntities", group, byref(inner))
            api.ok("SUGroupGetTransform", group, byref(local))
            reason = self.visibility.reason(api.raw("SUGroupToDrawingElement", group))
            yield ("group", _string(api, "SUGroupGetName", group), None, reason, _matrix(local),
                   inner)
        for instance in _refs(api, "SUEntitiesGetNumInstances", "SUEntitiesGetInstances", entities):
            definition, inner, local = _Ref(), _Ref(), _Transformation()
            api.ok("SUComponentInstanceGetDefinition", instance, byref(definition))
            api.ok("SUComponentDefinitionGetEntities", definition, byref(inner))
            api.ok("SUComponentInstanceGetTransform", instance, byref(local))
            reason = self.visibility.reason(
                api.raw("SUComponentInstanceToDrawingElement", instance))
            yield ("instance", _string(api, "SUComponentInstanceGetName", instance),
                   _string(api, "SUComponentDefinitionGetName", definition), reason,
                   _matrix(local), inner)

    def walk(self, kind: str, name: str, definition: str | None, entities: _Ref,
             world: np.ndarray) -> dict:
        faces = self.faces(entities)
        area, bbox = faces.in_world(world)
        node = {"kind": kind, "name": name, "definition": definition, "faces": faces.count,
                "tris": faces.tris, "area": area, "bbox": bbox, "hidden_faces": faces.hidden,
                "layer_hidden_faces": faces.layer_hidden, "children": [], "skipped": []}
        totals = self.totals
        totals["faces"] += faces.count
        totals["tris"] += faces.tris
        totals["hidden_faces"] += faces.hidden
        totals["layer_hidden_faces"] += faces.layer_hidden
        for child_kind, child_name, child_definition, reason, local, inner in self.children(entities):
            if reason is not None:
                node["skipped"].append({"kind": child_kind, "name": child_name,
                                        "definition": child_definition, "reason": reason})
                totals["hidden_nodes" if reason == "hidden" else "layer_hidden_nodes"] += 1
                continue
            totals["groups" if child_kind == "group" else "instances"] += 1
            node["children"].append(
                self.walk(child_kind, child_name, child_definition, inner, world @ local))
        return node


def walk_skp(path, *, dll_path=None) -> dict:
    """The model at `path` as the tree described in the module docstring:
    `{"path", "api_version", "elapsed_s", "layers_bound", "totals", "root"}`. `totals` counts what
    was walked (a component definition shared by several instances counts once for each) and
    what was left out; `layers_bound` says whether this DLL has the tag calls, without which a
    tag that is switched off cannot be told. The file is only read."""
    api = load_api(dll_path)
    path = Path(path)
    started = time.perf_counter()
    with api.session(), _open(api, path) as model:
        entities = _Ref()
        api.ok("SUModelGetEntities", model, byref(entities))
        walker = _Walker(api)
        root = walker.walk("model", "", None, entities, np.eye(4))
        version = api.version()
    return {"path": str(path), "api_version": version,
            "elapsed_s": round(time.perf_counter() - started, 3),
            "layers_bound": walker.visibility.tags, "totals": walker.totals, "root": root}


# -------------------------------------------------------------------- the command, in a child


def _peak_memory_mb() -> tuple[float | None, float | None]:
    """`(peak working set, peak commit)` of this process in MB; `(None, None)` off Windows. The probe is
    `engine.campus.winprobe.peak_memory_mb`, shared with the census and the Validator's command."""
    from engine.campus.winprobe import peak_memory_mb
    return peak_memory_mb()


def available_commit_mb() -> float | None:
    """How many MB the machine can still promise to a process: the commit limit minus what is
    already committed (`ullAvailPageFile` of `GlobalMemoryStatusEx`) -- what decides whether the
    next big allocation succeeds, however much RAM looks free. `None` off Windows."""
    if os.name != "nt":
        return None
    from ctypes import wintypes

    class Status(Structure):
        _fields_ = [("dwLength", wintypes.DWORD), ("dwMemoryLoad", wintypes.DWORD),
                    ("ullTotalPhys", c_ulonglong), ("ullAvailPhys", c_ulonglong),
                    ("ullTotalPageFile", c_ulonglong), ("ullAvailPageFile", c_ulonglong),
                    ("ullTotalVirtual", c_ulonglong), ("ullAvailVirtual", c_ulonglong),
                    ("ullAvailExtendedVirtual", c_ulonglong)]

    kernel32 = ctypes.WinDLL("kernel32")
    kernel32.GlobalMemoryStatusEx.argtypes = [POINTER(Status)]
    kernel32.GlobalMemoryStatusEx.restype = wintypes.BOOL
    status = Status()
    status.dwLength = ctypes.sizeof(Status)
    if not kernel32.GlobalMemoryStatusEx(byref(status)):
        return None
    return round(status.ullAvailPageFile / 2 ** 20, 1)


def main(argv: list[str] | None = None) -> int:
    """`python -m engine.io.skp_reader <model.skp> --out <walk.json> [--dll <SketchUpAPI.dll>]`:
    walk the model (`walk_skp`) and write the tree, plus this process's peak memory, as JSON.
    This is how `engine.campus.skp_check` reads the 150 MB backup: in a child process that a
    timeout can kill. Exit code 0, or 2 with the reason on stderr when the model cannot be read."""
    parser = argparse.ArgumentParser(prog="python -m engine.io.skp_reader", description=main.__doc__)
    parser.add_argument("skp", type=Path)
    parser.add_argument("--out", type=Path, required=True)
    parser.add_argument("--dll", type=Path, default=None)
    args = parser.parse_args(argv)
    try:
        walk = walk_skp(args.skp, dll_path=args.dll)
    except (SketchUpError, FileNotFoundError) as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 2
    walk["peak_working_set_mb"], walk["peak_commit_mb"] = _peak_memory_mb()
    args.out.parent.mkdir(parents=True, exist_ok=True)
    fd, tmp = tempfile.mkstemp(prefix=".walk-", suffix=".json.tmp", dir=args.out.parent)
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as fh:
            json.dump(walk, fh)
        os.replace(tmp, args.out)
    finally:
        if os.path.exists(tmp):
            os.unlink(tmp)
    return 0


if __name__ == "__main__":
    sys.exit(main())
