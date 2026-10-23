from dataclasses import replace
import json

import numpy as np
import pytest

from engine.io.minecraft_floor import Frame, parse_floor
from engine.io.obj_reader import read_obj


def source():
    return parse_floor('''v 0.0333333333 0 0
v 1 0 0
v 0 1 0
v 0 0 1
vt 0.12345678901234566 0.25
vt 0.75 0.25
vt 0.25 0.75
vn 0 0 1
usemtl facade
f 1/1/1 2/2/1 3/3/1
usemtl inner
f 1/1/1 4/2/1 2/3/1
f 1/1/1 3/2/1 4/3/1
''')


def test_saved_pair_retains_exact_original_survivors_and_material_names(tmp_path):
    from tools.main_infra_e3 import save_survivor_pair
    raw = source()
    engine = raw.in_frame(Frame(1000 / 25.4, 'owner metre/block; Y-up'))
    out = tmp_path / 'candidate'
    save_survivor_pair(engine, raw, [1, 2], out)
    saved_engine = read_obj(out / 'candidate.engine.obj')
    saved_source = read_obj(out / 'candidate.source.obj')
    np.testing.assert_array_equal(saved_engine.positions, engine.mesh.positions)
    np.testing.assert_array_equal(saved_source.positions, raw.mesh.positions)
    np.testing.assert_array_equal(saved_source.uvs, raw.mesh.uvs)
    np.testing.assert_array_equal(saved_source.normals, raw.mesh.normals)
    np.testing.assert_array_equal(saved_source.face_v, raw.mesh.face_v[[1, 2]])
    assert saved_source.materials == ['inner']
    assert json.loads((out / 'source-faces.json').read_text())['source_faces'] == [1, 2]
    with pytest.raises(ValueError, match='exists'):
        save_survivor_pair(engine, raw, [0], out)


@pytest.mark.parametrize('indices', [[1, 1], [2, 0], [-1], [3], [0.5], [True], [[0]],
                                     np.array([2, 0], dtype=np.uint64)])
def test_invalid_survivor_mapping_cannot_create_output(tmp_path, indices):
    from tools.main_infra_e3 import save_survivor_pair
    raw = source()
    engine = raw.in_frame(Frame(1000 / 25.4, 'metres; Y-up'))
    out = tmp_path / 'candidate'
    with pytest.raises(ValueError):
        save_survivor_pair(engine, raw, indices, out)
    assert not out.exists()


@pytest.mark.parametrize('field', ['positions', 'uvs', 'normals', 'face_v', 'face_vt', 'face_vn', 'face_material'])
def test_saved_survivor_readback_refuses_changed_original_data(tmp_path, field):
    from tools.main_infra_e3 import save_survivor_pair, verify_survivor_mesh
    raw = source()
    engine = raw.in_frame(Frame(1000 / 25.4, 'metres; Y-up'))
    out = tmp_path / 'candidate'
    save_survivor_pair(engine, raw, [1, 2], out)
    saved = read_obj(out / 'candidate.source.obj')
    values = getattr(saved, field).copy()
    values.flat[0] += 1
    bad = replace(saved, **{field: values})
    with pytest.raises(ValueError):
        verify_survivor_mesh(raw.mesh, bad, [1, 2])


def test_frame_or_source_mismatch_cannot_create_output(tmp_path):
    from tools.main_infra_e3 import save_survivor_pair
    raw = source()
    engine = raw.in_frame(Frame(1000 / 25.4, 'metres; Y-up'))
    bad = engine.mesh.positions.copy()
    bad[0, 0] += 0.01
    engine = replace(engine, mesh=replace(engine.mesh, positions=bad))
    out = tmp_path / 'candidate'
    with pytest.raises(ValueError):
        save_survivor_pair(engine, raw, [0], out)
    assert not out.exists()
