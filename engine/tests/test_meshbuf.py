from pathlib import Path

import numpy as np

from engine.pipeline import analyse_topology
from engine.tests.fixtures.build import cube, t_junction_strip
from engine.transport.meshbuf import pack_meshbuf, unpack_meshbuf


def test_round_trip_and_alignment():
    m = cube(10.0)
    buf = pack_meshbuf(m, analyse_topology(m), {"m0": "tex/stone.png"})
    assert buf[:4] == b"UCMB"
    header, blocks = unpack_meshbuf(buf)
    assert header["version"] == 1 and header["counts"] == {"faces": 12, "edges": 18}
    assert header["origin_offset"] == [5.0, 5.0, 5.0] and header["unit_scale_m"] == 0.0254
    assert header["materials"] == [{"name": "m0", "texture": "tex/stone.png"}]
    assert all(b["offset"] % 4 == 0 for b in header["blocks"])
    assert blocks["positions"].shape == (36, 3) and np.abs(blocks["positions"]).max() == 5.0
    assert blocks["tri_face_id"].tolist() == list(range(12))
    assert blocks["edge_positions"].shape == (36, 3) and blocks["edge_class"].shape == (18,)
    n = blocks["normals"].reshape(12, 3, 3)[:, 0]
    assert np.allclose(np.linalg.norm(n, axis=1), 1.0)


def test_header_serializes_path_texture_value():
    m = cube(10.0)
    buf = pack_meshbuf(m, analyse_topology(m), {"m0": Path("tex/stone.png")})
    header, _ = unpack_meshbuf(buf)
    assert header["materials"] == [{"name": "m0", "texture": "tex/stone.png"}]


def test_header_serializes_backslash_string_texture_value():
    m = cube(10.0)
    buf = pack_meshbuf(m, analyse_topology(m), {"m0": "tex\\stone.png"})
    header, _ = unpack_meshbuf(buf)
    assert header["materials"] == [{"name": "m0", "texture": "tex/stone.png"}]


def test_header_keeps_missing_texture_as_null():
    m = cube(10.0)
    buf = pack_meshbuf(m, analyse_topology(m), {})
    header, _ = unpack_meshbuf(buf)
    assert header["materials"] == [{"name": "m0", "texture": None}]


def test_degenerate_face_and_missing_material_produce_correct_sentinels():
    m = t_junction_strip()
    m.face_material = m.face_material.copy()
    m.face_material[0] = -1  # face 0 (non-degenerate) gets no assigned material
    zero_area = 6  # the (3,4,2) zero-area stitching triangle
    topo = analyse_topology(m)
    assert not topo.ok[zero_area]  # sanity: this really is the degenerate face

    buf = pack_meshbuf(m, topo, {})
    header, blocks = unpack_meshbuf(buf)

    assert blocks["tri_region"][zero_area] == -1
    assert blocks["tri_material"][0] == 65535
    assert blocks["tri_face_id"].tolist() == list(range(m.n_faces))

    normals = blocks["normals"].reshape(m.n_faces, 3, 3)
    assert np.isfinite(normals).all()
    assert np.allclose(np.linalg.norm(normals[:, 0], axis=1), 1.0)
    assert normals[zero_area, 0].tolist() == [0.0, 0.0, 1.0]
