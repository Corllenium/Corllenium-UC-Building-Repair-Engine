import pytest

from tools.main_infra_drop_markers import split_markers


def test_drops_exactly_the_approved_faces():
    e3_map = [100, 101, 102, 103]  # E3 index -> original id
    kept, dropped = split_markers([0, 1, 3], e3_map, [101, 103])
    assert kept == [0]
    assert dropped == [1, 3]


def test_refuses_when_an_approved_face_is_not_in_the_candidate():
    with pytest.raises(ValueError, match='not in the candidate'):
        split_markers([0, 1], [100, 101, 102], [101, 102])
