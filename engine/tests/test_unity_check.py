# engine/tests/test_unity_check.py
from dataclasses import replace

import numpy as np

from engine.tests.fixtures.build import cube
from engine.unity.check import geometry_diff
from engine.unity.dump import UnityDump

M = np.array([[-1, 0, 0], [0, 0, 1], [0, 1, 0]], float)   # Unity mirrors x; y-up


def _dump(mesh, *, faces=None, index_format="UInt32", vertex_count=None):
    """`mesh` as Unity would hold it: mirrored (so winding reverses) and scaled."""
    f = mesh.face_v[:, ::-1] if faces is None else faces
    u = replace(mesh, positions=(mesh.positions @ M.T) * 0.0254, face_v=f,
                face_vt=mesh.face_vt[:, ::-1], face_material=mesh.face_material[: len(f)])
    n = np.zeros((len(f), 3, 3))
    side = {"importer": {"globalScale": 0.0254},
            "meshes": [{"name": "m", "vertex_count": vertex_count or len(mesh.positions),
                        "index_format": index_format, "submeshes": []}]}
    return UnityDump(mesh=u, corner_normals=n, sidecar=side)


def test_an_unchanged_import_matches_every_face():
    b = cube(100.0)
    g = geometry_diff(b, _dump(b))
    assert (g["matched"], g["missing"], g["extra"], g["flipped"]) == (12, 0, 0, 0)


def test_a_dropped_face_is_missing():
    b = cube(100.0)
    g = geometry_diff(b, _dump(b, faces=b.face_v[1:, ::-1]))
    assert g["missing"] == 1 and g["matched"] == 11


def test_a_face_unity_turned_round_is_flipped_not_missing():
    b = cube(100.0)
    f = b.face_v[:, ::-1].copy()
    f[0] = f[0, ::-1]
    g = geometry_diff(b, _dump(b, faces=f))
    assert g["flipped"] == 1 and g["missing"] == 0 and g["extra"] == 0


def test_coincident_opposite_faces_count_as_two_each_side():
    b = cube(100.0)
    both = replace(b, face_v=np.vstack([b.face_v, b.face_v[:1, ::-1]]),
                   face_vt=np.vstack([b.face_vt, b.face_vt[:1, ::-1]]),
                   face_vn=np.vstack([b.face_vn, b.face_vn[:1]]),
                   face_material=np.append(b.face_material, 0), face_line=np.arange(1, 14))
    g = geometry_diff(both, _dump(both, faces=both.face_v[:12, ::-1]))   # Unity dropped the back copy
    assert g["missing"] == 1 and g["matched"] == 12


def test_a_16_bit_mesh_over_65535_vertices_is_flagged():
    b = cube(100.0)
    g = geometry_diff(b, _dump(b, index_format="UInt16", vertex_count=70000))
    assert g["index_overflow"] is True
