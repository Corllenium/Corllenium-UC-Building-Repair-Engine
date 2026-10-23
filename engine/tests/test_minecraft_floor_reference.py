import numpy as np
import pytest

from engine.io.minecraft_floor import FloorFormatError, parse_floor


def nonplanar_quad():
    return '\n'.join([
        'v 5.0 4.0 1.8043478', 'v 4.0 4.0 1.7173913',
        'v 4.0 3.0 1.7173913', 'v 5.0 3.0 1.8043479',
        'vt 0 0', 'vt 1 0', 'vt 1 1', 'vt 0 1',
        'usemtl facade', 'f 1/1 2/2 3/3 4/4',
    ])


def test_authoritative_tessellation_preserves_actual_nonplanar_corners_and_uvs():
    text = nonplanar_quad()
    with pytest.raises(FloorFormatError, match='nonplanar'):
        parse_floor(text)
    floor = parse_floor(text, triangulations={10: [(0, 1, 2), (0, 2, 3)]})
    np.testing.assert_array_equal(floor.mesh.positions, [[5, 4, 1.8043478], [4, 4, 1.7173913], [4, 3, 1.7173913], [5, 3, 1.8043479]])
    np.testing.assert_array_equal(floor.mesh.face_v, [[0, 1, 2], [0, 2, 3]])
    np.testing.assert_array_equal(floor.mesh.face_vt, [[0, 1, 2], [0, 2, 3]])
    np.testing.assert_array_equal(floor.triangle_polygon, [0, 0])
    assert floor.mesh.materials == ['facade']


@pytest.mark.parametrize('triangles', [
    [(0, 1, 2)], [(0, 1, 2), (0, 1, 2)], [(0, 2, 1), (0, 2, 3)],
    [(0, 1, 4), (0, 2, 3)], [(0, 0, 2), (0, 2, 3)],
])
def test_reference_cannot_drop_cover_reverse_or_invent_corners(triangles):
    with pytest.raises(FloorFormatError, match='reference'):
        parse_floor(nonplanar_quad(), triangulations={10: triangles})


def test_reference_must_cover_every_source_polygon_and_no_other_record():
    with pytest.raises(FloorFormatError, match='reference'):
        parse_floor(nonplanar_quad(), triangulations={})
    with pytest.raises(FloorFormatError, match='reference'):
        parse_floor(nonplanar_quad(), triangulations={10: [(0, 1, 2), (0, 2, 3)], 11: [(0, 1, 2)]})
