import numpy as np

from engine.fixes.remove import remove_faces
from engine.io.obj_reader import read_obj
from engine.io.obj_writer import write_obj
from engine.tests.fixtures.build import cube


def test_dropping_nothing_is_identity():
    m = cube()
    drop = np.zeros(m.n_faces, dtype=bool)

    new, source_face = remove_faces(m, drop)

    assert new.n_faces == m.n_faces
    assert np.array_equal(new.face_v, m.face_v)
    assert np.array_equal(new.face_vt, m.face_vt)
    assert np.array_equal(new.face_vn, m.face_vn)
    assert np.array_equal(new.face_material, m.face_material)
    assert np.array_equal(new.face_line, m.face_line)
    # positions/UVs/normals/materials untouched -- no re-indexing, no compaction
    assert np.array_equal(new.positions, m.positions)
    assert np.array_equal(new.uvs, m.uvs)
    assert np.array_equal(new.normals, m.normals)
    assert new.materials == m.materials
    assert source_face.dtype == np.int64
    assert source_face.tolist() == list(range(m.n_faces))


def test_dropping_faces_keeps_order_of_survivors():
    m = cube()
    drop = np.zeros(m.n_faces, dtype=bool)
    drop[[3, 7]] = True

    new, source_face = remove_faces(m, drop)

    expected_order = [i for i in range(m.n_faces) if i not in (3, 7)]
    assert source_face.tolist() == expected_order
    assert new.n_faces == m.n_faces - 2
    # positions untouched even though faces were dropped
    assert np.array_equal(new.positions, m.positions)


def test_source_face_maps_back_exactly():
    m = cube()
    drop = np.zeros(m.n_faces, dtype=bool)
    drop[[1, 5, 9]] = True

    new, source_face = remove_faces(m, drop)

    assert np.array_equal(new.face_v, m.face_v[source_face])
    assert np.array_equal(new.face_vt, m.face_vt[source_face])
    assert np.array_equal(new.face_vn, m.face_vn[source_face])
    assert np.array_equal(new.face_material, m.face_material[source_face])
    assert np.array_equal(new.face_line, m.face_line[source_face])


def test_round_trip_through_write_and_read_preserves_face_count(tmp_path):
    m = cube()
    drop = np.zeros(m.n_faces, dtype=bool)
    drop[[0, 2, 4]] = True

    new, _ = remove_faces(m, drop)

    path = tmp_path / "dropped.obj"
    write_obj(new, path)
    reloaded = read_obj(path)

    assert reloaded.n_faces == new.n_faces == m.n_faces - 3
