import numpy as np

from engine.pipeline import analyse_topology
from engine.tests.fixtures.build import cube
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
