"""Test support: SketchUp models with groups, component instances, transforms, hidden things and
tags, built through SketchUp's own C API and saved to a file, for `engine.io.skp_reader`'s tests.

The writer (`engine.io.skp_writer`) only makes flat meshes, so the reader's handling of groups
and transforms needs a builder of its own. It needs `SketchUpAPI.dll` and, for the
`SUModelSaveToFile` call that makes a test file, binds a save call -- which the reader under test
must not (this module is not part of the engine).

A scene is a dict, every key optional:

    {"faces": [face, ...], "groups": [group, ...], "instances": [instance, ...],
     "layers": {"Tag name": visible, ...}, "definitions": {"Def name": {"faces": [...], ...}}}

* a face is a list of 3-D points, or `{"points": [...], "hidden": True, "layer": "Tag name"}`;
* a group is `{"name", "transform", "hidden", "layer", "faces", "groups", "instances"}`;
* an instance is `{"definition", "name", "transform", "hidden", "layer"}`;
* a transform is a 4 x 4 numpy matrix in the usual column-vector convention (`translation`,
  `rotation_z`, `scaling`, multiplied with `@`).

`build_scene` returns SketchUp's OWN answers for the top-level groups and instances, by name --
`bounds` (`SUDrawingElementGetBoundingBox`, in model coordinates) and `areas` (the sum of
`SUFaceGetAreaWithTransform` over the faces directly in it, under its transform) -- the oracle the
reader's composed transforms are checked against.
"""
from __future__ import annotations

import ctypes
import os
from ctypes import POINTER, Structure, byref, c_bool, c_char_p, c_double, c_int, c_size_t, c_void_p
from pathlib import Path

import numpy as np

from engine.io.skp_writer import resolve_dll_path


class _Ref(Structure):
    _fields_ = [("ptr", c_void_p)]


class _Point3D(Structure):
    _fields_ = [("x", c_double), ("y", c_double), ("z", c_double)]


class _Transformation(Structure):
    _fields_ = [("values", c_double * 16)]


class _BoundingBox3D(Structure):
    _fields_ = [("min_point", _Point3D), ("max_point", _Point3D)]


_RP = POINTER(_Ref)
_FUNCTIONS = {
    "SUInitialize": ([], None),
    "SUTerminate": ([], None),
    "SUModelCreate": ([_RP], c_int),
    "SUModelRelease": ([_RP], c_int),
    "SUModelGetEntities": ([_Ref, _RP], c_int),
    "SUModelSaveToFile": ([_Ref, c_char_p], c_int),
    "SUModelAddLayers": ([_Ref, c_size_t, _RP], c_int),
    "SUModelAddComponentDefinitions": ([_Ref, c_size_t, _RP], c_int),
    "SULayerCreate": ([_RP], c_int),
    "SULayerSetName": ([_Ref, c_char_p], c_int),
    "SULayerSetVisibility": ([_Ref, c_bool], c_int),
    "SUFaceCreateSimple": ([_RP, POINTER(_Point3D), c_size_t], c_int),
    "SUEntitiesAddFaces": ([_Ref, c_size_t, _RP], c_int),
    "SUGroupCreate": ([_RP], c_int),
    "SUGroupSetName": ([_Ref, c_char_p], c_int),
    "SUGroupSetTransform": ([_Ref, POINTER(_Transformation)], c_int),
    "SUGroupGetEntities": ([_Ref, _RP], c_int),
    "SUEntitiesAddGroup": ([_Ref, _Ref], c_int),
    "SUComponentDefinitionCreate": ([_RP], c_int),
    "SUComponentDefinitionSetName": ([_Ref, c_char_p], c_int),
    "SUComponentDefinitionGetEntities": ([_Ref, _RP], c_int),
    "SUComponentDefinitionCreateInstance": ([_Ref, _RP], c_int),
    "SUEntitiesAddInstance": ([_Ref, _Ref, c_void_p], c_int),
    "SUComponentInstanceSetName": ([_Ref, c_char_p], c_int),
    "SUComponentInstanceSetTransform": ([_Ref, POINTER(_Transformation)], c_int),
    "SUDrawingElementSetHidden": ([_Ref, c_bool], c_int),
    "SUDrawingElementSetLayer": ([_Ref, _Ref], c_int),
    "SUGroupToDrawingElement": ([_Ref], _Ref),
    "SUComponentInstanceToDrawingElement": ([_Ref], _Ref),
    "SUFaceToDrawingElement": ([_Ref], _Ref),
    "SUDrawingElementGetBoundingBox": ([_Ref, POINTER(_BoundingBox3D)], c_int),
    "SUFaceGetAreaWithTransform": ([_Ref, POINTER(_Transformation), POINTER(c_double)], c_int),
}


def translation(x: float, y: float, z: float) -> np.ndarray:
    m = np.eye(4)
    m[:3, 3] = (x, y, z)
    return m


def rotation_z(degrees: float) -> np.ndarray:
    c, s = np.cos(np.radians(degrees)), np.sin(np.radians(degrees))
    m = np.eye(4)
    m[:2, :2] = [[c, -s], [s, c]]
    return m


def scaling(sx: float, sy: float | None = None, sz: float | None = None) -> np.ndarray:
    return np.diag([sx, sx if sy is None else sy, sx if sz is None else sz, 1.0])


def square(x: float, y: float, z: float, size: float, plane: str = "xy") -> list[tuple]:
    """A `size` x `size` square with its lowest corner at `(x, y, z)` in the `xy`, `xz` or `yz`
    plane."""
    a, b = {"xy": ((1, 0, 0), (0, 1, 0)), "xz": ((1, 0, 0), (0, 0, 1)),
            "yz": ((0, 1, 0), (0, 0, 1))}[plane]
    o = np.array([x, y, z], float)
    u, v = np.array(a, float) * size, np.array(b, float) * size
    return [tuple(p) for p in (o, o + u, o + u + v, o + v)]


class _Builder:
    def __init__(self, dll):
        self.dll = dll
        self.fn = {}
        for name, (argtypes, restype) in _FUNCTIONS.items():
            f = getattr(dll, name)
            f.argtypes, f.restype = argtypes, restype
            self.fn[name] = f
        self.layers: dict[str, _Ref] = {}
        self.definitions: dict[str, _Ref] = {}
        self.bounds: dict[str, tuple] = {}
        self.areas: dict[str, float] = {}

    def ok(self, name: str, *args):
        code = self.fn[name](*args)
        assert code == 0, f"{name} failed with SUResult {code}"

    def matrix(self, m: np.ndarray) -> _Transformation:
        t = _Transformation()
        t.values[:] = np.asarray(m, float).flatten(order="F").tolist()      # column-major
        return t

    def faces(self, entities: _Ref, faces: list) -> list[_Ref]:
        made = []
        for spec in faces:
            spec = {"points": spec} if not isinstance(spec, dict) else spec
            pts = (_Point3D * len(spec["points"]))(*[_Point3D(*p) for p in spec["points"]])
            face = _Ref()
            self.ok("SUFaceCreateSimple", byref(face), pts, len(pts))
            self.ok("SUEntitiesAddFaces", entities, 1, byref(face))
            element = self.fn["SUFaceToDrawingElement"](face)
            if spec.get("hidden"):
                self.ok("SUDrawingElementSetHidden", element, True)
            if spec.get("layer"):
                self.ok("SUDrawingElementSetLayer", element, self.layers[spec["layer"]])
            made.append(face)
        return made

    def element_flags(self, element: _Ref, spec: dict) -> None:
        if spec.get("hidden"):
            self.ok("SUDrawingElementSetHidden", element, True)
        if spec.get("layer"):
            self.ok("SUDrawingElementSetLayer", element, self.layers[spec["layer"]])

    def contents(self, entities: _Ref, spec: dict, top: bool = False) -> list[_Ref]:
        made = self.faces(entities, spec.get("faces", []))
        for group in spec.get("groups", []):
            self.group(entities, group, top)
        for instance in spec.get("instances", []):
            self.instance(entities, instance, top)
        return made

    def group(self, parent: _Ref, spec: dict, top: bool) -> None:
        group = _Ref()
        self.ok("SUGroupCreate", byref(group))
        self.ok("SUEntitiesAddGroup", parent, group)                    # before it is filled
        inner = _Ref()
        self.ok("SUGroupGetEntities", group, byref(inner))
        faces = self.contents(inner, spec)
        if "name" in spec:
            self.ok("SUGroupSetName", group, spec["name"].encode("utf-8"))
        transform = spec.get("transform")
        if transform is not None:
            self.ok("SUGroupSetTransform", group, byref(self.matrix(transform)))
        element = self.fn["SUGroupToDrawingElement"](group)
        self.element_flags(element, spec)
        if top:
            self.measure(element, spec, faces, transform)

    def instance(self, parent: _Ref, spec: dict, top: bool) -> None:
        instance = _Ref()
        self.ok("SUComponentDefinitionCreateInstance", self.definitions[spec["definition"]],
                byref(instance))
        self.ok("SUEntitiesAddInstance", parent, instance, None)
        if spec.get("name"):
            self.ok("SUComponentInstanceSetName", instance, spec["name"].encode("utf-8"))
        transform = spec.get("transform")
        if transform is not None:
            self.ok("SUComponentInstanceSetTransform", instance, byref(self.matrix(transform)))
        element = self.fn["SUComponentInstanceToDrawingElement"](instance)
        self.element_flags(element, spec)
        if top:
            self.measure(element, spec, [], transform)

    def measure(self, element: _Ref, spec: dict, faces: list[_Ref], transform) -> None:
        """SketchUp's own bounds (and area of the faces directly inside) for a top-level item."""
        if spec.get("name") is None:
            return
        box = _BoundingBox3D()
        self.ok("SUDrawingElementGetBoundingBox", element, byref(box))
        self.bounds[spec["name"]] = ([box.min_point.x, box.min_point.y, box.min_point.z],
                                     [box.max_point.x, box.max_point.y, box.max_point.z])
        matrix = self.matrix(np.eye(4) if transform is None else transform)
        total = 0.0
        for face in faces:
            area = c_double()
            self.ok("SUFaceGetAreaWithTransform", face, byref(matrix), byref(area))
            total += area.value
        self.areas[spec["name"]] = total

    def build(self, model: _Ref, scene: dict) -> None:
        entities = _Ref()
        self.ok("SUModelGetEntities", model, byref(entities))
        for name, visible in scene.get("layers", {}).items():
            layer = _Ref()
            self.ok("SULayerCreate", byref(layer))
            self.ok("SULayerSetName", layer, name.encode("utf-8"))
            self.ok("SULayerSetVisibility", layer, visible)
            self.ok("SUModelAddLayers", model, 1, byref(layer))
            self.layers[name] = layer
        for name, definition in scene.get("definitions", {}).items():
            ref = _Ref()
            self.ok("SUComponentDefinitionCreate", byref(ref))
            self.ok("SUComponentDefinitionSetName", ref, name.encode("utf-8"))
            self.ok("SUModelAddComponentDefinitions", model, 1, byref(ref))   # before it is filled
            inner = _Ref()
            self.ok("SUComponentDefinitionGetEntities", ref, byref(inner))
            self.contents(inner, definition)
            self.definitions[name] = ref
        self.contents(entities, scene, top=True)


def build_scene(path, scene: dict, dll_path=None) -> dict:
    """Save `scene` to `path` as a SketchUp model; return SketchUp's own `{"bounds", "areas"}` for
    the top-level groups and instances (see the module docstring)."""
    dll_path = resolve_dll_path(dll_path)
    os.add_dll_directory(str(dll_path.parent))
    dll = ctypes.CDLL(str(dll_path))
    builder = _Builder(dll)
    builder.fn["SUInitialize"]()
    model = _Ref()
    try:
        builder.ok("SUModelCreate", byref(model))
        try:
            builder.build(model, scene)
            Path(path).parent.mkdir(parents=True, exist_ok=True)
            builder.ok("SUModelSaveToFile", model, str(path).encode("utf-8"))
        finally:
            builder.fn["SUModelRelease"](byref(model))
    finally:
        builder.fn["SUTerminate"]()
    return {"bounds": builder.bounds, "areas": builder.areas}
