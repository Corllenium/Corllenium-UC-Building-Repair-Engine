from dataclasses import replace

import numpy as np
import pytest

from engine.fixes.remove import remove_faces
from engine.io.minecraft_floor import Frame, parse_floor
from engine.repair.kernel import KernelResult
from engine.repair.types import Edit


def mesh():
    return parse_floor('''v 0 0 0
v 1 0 0
v 0 1 0
v 0 0 1
vt 0.123456789 0.25
vt 0.75 0.25
vt 0.25 0.75
vn 0 0 1
usemtl facade
f 1/1/1 2/2/1 3/3/1
usemtl inner
f 1/1/1 4/2/1 2/3/1
f 1/1/1 3/2/1 4/3/1
''').in_frame(Frame(1000 / 25.4, 'owner metre/block; Y-up')).mesh


def edit(face, site=0, **changes):
    return replace(Edit('E3', 'remove', (face,), None, None, site, 'hidden', {}), **changes)


def result(before, kept, rolled=(), *, final='PASS'):
    drop = np.zeros(before.n_faces, bool)
    for item in kept:
        drop[list(item.faces)] = True
    after, _ = remove_faces(before, drop)
    return KernelResult(mesh=after, result=None, edits=list(kept) + list(rolled), stages=[], report=None,
        kept=list(kept), rolled_back=list(rolled), checks=[dict(stage='E3', engine='E3', legacy=False,
        rollback=True, final=final)], records=[])


def test_kept_survivors_use_original_indices_and_exclude_only_kept_edits():
    from tools.main_infra_e3 import source_survivors
    before = mesh()
    outcome = result(before, [edit(1)], [edit(2, site=1)])
    indices = source_survivors(before, outcome)
    np.testing.assert_array_equal(indices, [0, 2])
    np.testing.assert_array_equal(outcome.mesh.positions, before.positions)
    np.testing.assert_array_equal(outcome.mesh.uvs, before.uvs)
    assert outcome.mesh.physical_quanta == before.physical_quanta


@pytest.mark.parametrize('field', ['positions', 'uvs', 'normals', 'face_v', 'face_vt', 'face_vn', 'face_material'])
def test_survivor_contract_refuses_changed_corner_or_attribute(field):
    from tools.main_infra_e3 import source_survivors
    before = mesh()
    outcome = result(before, [edit(1)])
    values = getattr(outcome.mesh, field).copy()
    values.flat[0] += 1
    outcome.mesh = replace(outcome.mesh, **{field: values})
    with pytest.raises(ValueError):
        source_survivors(before, outcome)


@pytest.mark.parametrize('changes', [dict(engine='E1'), dict(kind='flip'), dict(legacy=True)])
def test_survivor_contract_refuses_any_other_engine_or_edit(changes):
    from tools.main_infra_e3 import source_survivors
    before = mesh()
    with pytest.raises(ValueError):
        source_survivors(before, result(before, [edit(1, **changes)]))


def test_unchecked_or_unconfirmed_removal_cannot_ship():
    from tools.main_infra_e3 import source_survivors
    before = mesh()
    outcome = result(before, [edit(1)], final='FAIL')
    with pytest.raises(ValueError):
        source_survivors(before, outcome)
    outcome.checks = []
    with pytest.raises(ValueError):
        source_survivors(before, outcome)


def test_duplicate_source_indices_in_one_edit_cannot_ship():
    from tools.main_infra_e3 import source_survivors
    before = mesh()
    with pytest.raises(ValueError):
        source_survivors(before, result(before, [edit(1, faces=(1, 1))]))


@pytest.mark.parametrize('field,value', [('coord_decimals', 2), ('sig_digits', 3)])
def test_source_storage_precision_metadata_remains_bound(field, value):
    from tools.main_infra_e3 import source_survivors
    before = mesh()
    outcome = result(before, [edit(1)])
    outcome.mesh = replace(outcome.mesh, **{field: value})
    with pytest.raises(ValueError):
        source_survivors(before, outcome)


def test_kernel_mutation_of_source_input_is_refused(monkeypatch):
    from tools import main_infra_e3 as module
    from engine.tests.test_validate_checks import _looks
    before = mesh()
    def unsafe(unit, *args, **kwargs):
        outcome = result(unit.mesh, [])
        unit.mesh.positions[0, 0] += 1
        return outcome
    monkeypatch.setattr(module, 'repair_unit', unsafe)
    with pytest.raises(ValueError, match='source|input'):
        module.run_checked_e3(before, _looks(*before.materials), {})


def test_unknown_failure_with_every_site_rolled_back_retains_original_mesh():
    from tools.main_infra_e3 import source_survivors
    before = mesh()
    outcome = result(before, [], [edit(1)], final='NOTHING KEPT')
    np.testing.assert_array_equal(source_survivors(before, outcome), [0, 1, 2])


def test_checked_e3_executes_real_engine_and_retains_visible_facade():
    from tools.main_infra_e3 import run_checked_e3
    from engine.tests.test_validate_checks import _looks
    before = mesh()
    outcome, indices = run_checked_e3(before, _looks(*before.materials), {})
    assert len(outcome.checks) == 1
    assert outcome.checks[0]['engine'] == 'E3'
    assert outcome.checks[0]['legacy'] is False
    assert outcome.checks[0]['rollback'] is True
    np.testing.assert_array_equal(indices, [0, 1, 2])
    assert outcome.mesh.physical_quanta == before.physical_quanta
