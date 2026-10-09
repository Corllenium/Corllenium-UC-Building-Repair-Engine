"""Job P2-K0 item 4: a face before any `usemtl` (material index -1) is its own look, `material:<none>` in `face_keys`
and `<none>` in `material_name`, and no longer resolves to the LAST material.
"""
from __future__ import annotations

import dataclasses

import numpy as np

from engine.campus.materials import material_name
from engine.repair.types import face_keys
from engine.tests.fixtures.build import cube


def _before_usemtl():
    """Two identical triangles: the first sits before any `usemtl` (index -1), the second uses material 1, the LAST."""
    base = cube()
    face = base.face_v[:1]
    return dataclasses.replace(base, materials=["wall", "roof"], face_v=np.vstack([face, face]),
                               face_vt=np.vstack([base.face_vt[:1]] * 2), face_vn=np.vstack([base.face_vn[:1]] * 2),
                               face_material=np.array([-1, 1], np.int64), face_line=np.array([1, 2], np.int64))


def test_a_face_before_any_usemtl_has_its_own_look_in_face_keys():
    mesh = _before_usemtl()
    none_key, wall_key = face_keys(mesh, {})
    assert none_key != wall_key
    assert none_key == face_keys(dataclasses.replace(mesh, face_material=np.array([-1, -1], np.int64)), {})[0]
    as_last = face_keys(dataclasses.replace(mesh, face_material=np.array([1, 1], np.int64)), {})[0]
    assert none_key != as_last, "index -1 must not resolve to the last material"
    assert none_key == face_keys(mesh, {0: "tex:a"})[0], "a look of material 0 does not reach the unnamed face"


def test_the_material_name_of_a_face_before_any_usemtl_is_none():
    mesh = _before_usemtl()
    assert material_name(mesh, 0) == "<none>" and material_name(mesh, 1) == "roof"
