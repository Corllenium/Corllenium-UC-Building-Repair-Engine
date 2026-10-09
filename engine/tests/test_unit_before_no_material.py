"""Job P2-E8a item 4 (carried from P2-K0): a face with no material (index -1, a face before any `usemtl`) in a
campus unit's BEFORE keeps the look "material:<none>", as `face_keys` and `material_name` give it.

`write_obj` writes no `usemtl` for index -1, so a later member's face of no material, written after an earlier
member's `usemtl`, used to read back as that earlier member's material.
"""
from __future__ import annotations

import dataclasses

import numpy as np

from engine.campus.materials import material_name
from engine.campus.unit_before import build_unit_before
from engine.io.obj_reader import read_obj
from engine.io.snapshot import sha256_file
from engine.repair.types import NO_MATERIAL_LOOK, face_keys


def _snapshot(root, name, body: list[str], mtl: str) -> dict:
    d = root / name
    d.mkdir(parents=True)
    obj = d / f"{name}.obj"
    obj.write_text("\n".join(["mtllib materials.mtl", f"o {name}", *body]) + "\n", encoding="utf-8")
    (d / "materials.mtl").write_text(mtl, encoding="utf-8")
    return {"file": obj.name, "group": name, "dir": str(d), "sha256": sha256_file(obj)}


def _unit(tmp_path):
    a = _snapshot(tmp_path / "snaps", "Floor_A", ["v 0 0 0", "v 10 0 0", "v 0 10 0", "usemtl brick", "f 1 2 3"],
                  "newmtl brick\nKd 0.5 0.5 0.5\n")
    # B: its first face comes before any `usemtl` (no material), its second uses paint
    b = _snapshot(tmp_path / "snaps", "Floor_B", ["v 0 0 5", "v 10 0 5", "v 0 10 5", "v 0 0 9", "v 10 0 9",
                                                  "v 0 10 9", "f 1 2 3", "usemtl paint", "f 4 5 6"],
                  "newmtl paint\nKd 0.9 0.9 0.9\n")
    cmap = {"units": [{"unit": "X-L01", "members": [
        {"group": "Floor_A", "file": a["file"], "sha256": a["sha256"], "tris": 1, "faces": "all"},
        {"group": "Floor_B", "file": b["file"], "sha256": b["sha256"], "tris": 2, "faces": "all"}]}]}
    return cmap, {"snapshots": [a, b]}


def test_a_member_face_with_no_material_keeps_the_look_none_in_the_unit_before(tmp_path):
    cmap, source = _unit(tmp_path)
    report = build_unit_before(cmap, source, "X-L01", tmp_path / "out")
    mesh = read_obj(report["obj"])
    assert mesh.n_faces == 3
    z = mesh.positions[mesh.face_v][:, :, 2].mean(axis=1)
    none_face = int(np.flatnonzero(np.isclose(z, 5.0))[0])

    assert material_name(mesh, none_face) == "<none>", "not the earlier member's last material"
    as_none = dataclasses.replace(mesh, face_material=np.where(np.arange(mesh.n_faces) == none_face, -1,
                                                               mesh.face_material))
    assert face_keys(mesh, {})[none_face] == face_keys(as_none, {})[none_face], f"the look is {NO_MATERIAL_LOOK}"
    names = [material_name(mesh, f) for f in range(mesh.n_faces)]
    assert sorted(names) == ["<none>", "brick", "paint"]
