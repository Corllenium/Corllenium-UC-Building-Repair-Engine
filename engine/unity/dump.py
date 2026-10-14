"""Read what Unity made of a floor: the dump written by the mirror project (route A) or a live-scene read (route B).

The dump is `<name>.obj` + `<name>.mtl` + `<name>.unity.json`. The sidecar is written LAST and must say
`"complete": true`, so a run that died half way never reads as a valid dump.
"""
from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path

import numpy as np

from engine.io.obj_reader import read_obj
from engine.model import MeshData

SCHEMA = 1


class DumpError(ValueError):
    """A Unity dump that cannot be trusted."""


@dataclass(frozen=True)
class UnityDump:
    mesh: MeshData                # Unity's geometry, in Unity's own frame and units
    corner_normals: np.ndarray    # (F, 3, 3): each corner's normal as Unity shades it
    sidecar: dict


def read_unity_dump(obj_path: Path) -> UnityDump:
    obj_path = Path(obj_path)
    side = obj_path.with_name(obj_path.stem + ".unity.json")
    if not side.is_file():
        raise DumpError(f"no sidecar {side.name} next to {obj_path.name}")
    sidecar = json.loads(side.read_text(encoding="utf-8"))
    if sidecar.get("schema") != SCHEMA:
        raise DumpError(f"unknown schema {sidecar.get('schema')!r} (expected {SCHEMA})")
    if sidecar.get("complete") is not True:
        raise DumpError("dump not complete: the Unity run did not finish")
    mesh = read_obj(obj_path)
    if mesh.face_vn.size and (mesh.face_vn < 0).any() or len(mesh.normals) == 0:
        raise DumpError("every face corner must carry a normal (vn); Unity always has one")
    return UnityDump(mesh=mesh, corner_normals=mesh.normals[mesh.face_vn], sidecar=sidecar)
