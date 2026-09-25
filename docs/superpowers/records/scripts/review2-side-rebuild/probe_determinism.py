"""Determinism of the merged pipeline on the scenes of this review that take the side rebuild's
restore and replace paths: each is run twice through `fix_object` (default profile) and the
shipped mesh (faces, materials, positions) and the solidify / fragment / fold reports are compared
byte for byte (json with sorted keys, runtime removed).

usage: PYTHONPATH=<tree at e27eb79> .venv/Scripts/python.exe probe_determinism.py
"""
import hashlib
import json

import numpy as np

from engine.fixes.pipeline import FixProfile, fix_object

scenes = {}


def load_scene(path, fn, *args):
    src = open(path, encoding="utf-8").read()
    head = src.split("\nfor ", 1)[0]          # the definitions, not the run loop
    g = {"__name__": "scene_defs"}
    exec(compile(head, path, "exec"), g)
    return g[fn](*args)


scenes["deep tooth, 2000 in"] = load_scene("probe_piece_below_wall.py", "scene", 2000.0)[0]
scenes["sign one face, 2000 in"] = load_scene("probe_object_in_band.py", "build", True, 2000.0)[0]


def digest(r):
    def clean(d):
        return {k: v for k, v in d.items() if k != "runtime_s"}
    blob = json.dumps({"solidify": clean(r.solidify_report), "fragments": r.fragment_report,
                       "folds": r.fold_report, "passed": r.passed}, sort_keys=True, default=str)
    h = hashlib.sha256(blob.encode())
    h.update(np.ascontiguousarray(r.mesh.face_v).tobytes())
    h.update(np.ascontiguousarray(r.mesh.face_material).tobytes())
    h.update(np.ascontiguousarray(r.mesh.positions).tobytes())
    return h.hexdigest()[:16]


for name, m in scenes.items():
    d = [digest(fix_object(m, {}, FixProfile())) for _ in range(2)]
    print(f"{name}: {d[0]} {d[1]} {'identical' if d[0] == d[1] else 'DIFFERENT'}")
