"""Pure helpers of tools/main_infra_external_validate.py: face membership and owner-authorized face drops."""
import numpy as np
import pytest

from engine.tests.fixtures.build import _mesh
from tools.main_infra_external_validate import drop_faces, face_rows, membership, orange_face_ids


def _quad_pair():
    positions = [[0, 0, 0], [1, 0, 0], [1, 1, 0], [0, 1, 0], [2, 0, 0], [2, 1, 0]]
    uvs = [[0, 0], [1, 0], [1, 1], [0, 1], [2, 0], [2, 1]]
    face_v = [[0, 1, 2], [0, 2, 3], [1, 4, 5], [1, 5, 2]]
    return _mesh('before', positions, uvs, face_v, face_v, materials=('a', 'b'), face_material=[0, 0, 1, 1])


def test_membership_counts_retained_removed_added():
    before = _quad_pair()
    after = drop_faces(before, [1])
    stats, removed, added = membership(before, after)
    assert stats == dict(before_faces=4, after_faces=3, retained=3, removed=1, added=0)
    assert removed.tolist() == [False, True, False, False]
    assert not added.any()


def test_membership_sees_a_cut_face_as_added():
    before = _quad_pair()
    cut = drop_faces(before, [0])
    cut.face_v[0] = [0, 1, 3]  # a face with the same corners' pool but a different triangle: new geometry
    stats, _, added = membership(before, cut)
    assert stats['added'] == 1 and stats['retained'] == 2 and stats['removed'] == 2
    assert added.tolist() == [True, False, False]


def test_face_rows_include_material_so_a_relook_is_not_retained():
    before = _quad_pair()
    relook = drop_faces(before, [])
    relook.face_material[0] = 1
    assert not np.array_equal(face_rows(before)[0], face_rows(relook)[0])
    assert membership(before, relook)[0]['retained'] == 3


def test_drop_faces_keeps_order_and_refuses_bad_ids():
    before = _quad_pair()
    after = drop_faces(before, [3, 0])
    assert after.face_v.tolist() == [[0, 2, 3], [1, 4, 5]]
    assert after.face_material.tolist() == [0, 1]
    assert after.face_line.tolist() == [2, 3]
    with pytest.raises(ValueError):
        drop_faces(before, [4])
    with pytest.raises(ValueError):
        drop_faces(before, [1, 1])


def test_orange_face_ids_reads_the_floor_entry(tmp_path):
    selection = tmp_path / 'approved-selection.json'
    selection.write_text('{"floors": [{"floor": "4F", "original_face_ids": [10, 11]}, {"floor": "5F", "original_face_ids": [3]}]}',
                         encoding='utf-8')
    assert orange_face_ids(selection, '5F') == [3]
    with pytest.raises(ValueError):
        orange_face_ids(selection, '6F')
