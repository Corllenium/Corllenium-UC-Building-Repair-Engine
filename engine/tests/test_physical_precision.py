from dataclasses import replace

import numpy as np

from engine.io.minecraft_floor import Frame, parse_floor
from engine.pipeline import analyse_topology, analyse_topology_memo, clear_topology_memo


SLIGHTLY_ROUNDED_PLANE = """v 0 0 10
v 1 0 10
v 0 1 10
v 1 1 10.0000001
f 1 2 3
f 2 4 3
"""


def test_coordinate_frame_conversion_preserves_plane_partition():
    source = parse_floor(SLIGHTLY_ROUNDED_PLANE)
    before = analyse_topology(source.mesh)
    converted = analyse_topology(source.in_frame(Frame(1000 / 25.4, "1 unit = 1 metre; Y-up")).mesh)
    assert before.face_region[0] == before.face_region[1]
    assert converted.face_region[0] == converted.face_region[1]
    np.testing.assert_allclose(converted.quanta, [1000 / 25.4 * 1e-9,
                                                1000 / 25.4 * 1e-7,
                                                1000 / 25.4 * 1e-9], rtol=1e-14)


def test_topology_memo_distinguishes_physical_precision():
    clear_topology_memo()
    mesh = parse_floor(SLIGHTLY_ROUNDED_PLANE).in_frame(Frame(1000 / 25.4, "metres; Y-up")).mesh
    physical = analyse_topology_memo(mesh)
    literal_storage = analyse_topology_memo(replace(mesh, physical_quanta=None))
    assert physical is not literal_storage
    assert physical.face_region[0] == physical.face_region[1]
    assert literal_storage.face_region[0] != literal_storage.face_region[1]
