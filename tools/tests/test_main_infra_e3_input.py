import json

import numpy as np
import pytest

from tools.tests.test_main_infra_physical_validation import fixture


def test_loads_qualified_before_without_running_or_requiring_a_cleanup_candidate(tmp_path):
    from tools.main_infra_e3 import load_qualified_floor
    inputs = fixture(tmp_path)
    source, engine, before, receipt = load_qualified_floor(**{k: v for k, v in inputs.items() if k != 'candidate'})
    assert before.n_faces == source.mesh.n_faces == 2
    np.testing.assert_array_equal(before.positions, engine.mesh.positions)
    np.testing.assert_array_equal(before.face_v, engine.mesh.face_v)
    assert before.physical_quanta == engine.mesh.physical_quanta
    assert receipt['source_revision'] == 'a' * 64
    assert source.frame is None and engine.frame is not None


@pytest.mark.parametrize('changed', ['raw', 'reference', 'qualification', 'before.engine.obj', 'before.source.obj', 'source.mtl', 'wall.png'])
def test_changed_before_or_assets_cannot_start_a_repair(tmp_path, changed):
    from tools.main_infra_e3 import load_qualified_floor
    inputs = fixture(tmp_path)
    if changed in ('raw', 'reference'):
        path = inputs[changed]
        path.write_bytes(path.read_bytes() + b'\n')
    elif changed == 'qualification':
        path = inputs['qualification']
        doc = json.loads(path.read_text())
        doc['qualified'] = False
        path.write_text(json.dumps(doc))
    else:
        path = inputs['baseline'] / changed
        if not path.exists():
            path = next(inputs['baseline'].rglob(changed))
        path.write_bytes(path.read_bytes() + b'changed')
    with pytest.raises(ValueError):
        load_qualified_floor(**{k: v for k, v in inputs.items() if k != 'candidate'})
