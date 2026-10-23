from dataclasses import replace
import json
from pathlib import Path
import zipfile

import numpy as np
import pytest

from engine.io.snapshot import sha256_file
from engine.repair.types import apply_edits
from tools.main_infra_e3 import _source_digest
from tools.tests.test_main_infra_e7_serialization import fixture


def api():
    from tools import main_infra_e7_checkpoint
    return main_infra_e7_checkpoint


@pytest.fixture
def captured(tmp_path):
    values = fixture(tmp_path)
    source, engine, before, ancestry, outcome, looks, inputs = values
    binding = dict(inputs, run_id='attempt3-fixture', preparation_sha256='a'*64,
                   selection_digest='b'*64, components={'HEAD': 'fixture'})
    return before, outcome, looks, binding


def save(tmp_path, captured):
    before, outcome, looks, binding = captured
    out = tmp_path/'checked-outcome'
    receipt = api().save_e7_checkpoint(before, outcome, looks, out, binding=binding)
    return out, receipt


def restore(captured, out, receipt):
    before, _, looks, binding = captured
    return api().restore_e7_checkpoint(before, looks, out, binding=binding,
        expected_receipt_sha256=receipt['receipt_sha256'])


def test_actual_result_survives_serialization_failure_bit_exact(tmp_path, captured):
    out, receipt = save(tmp_path, captured)
    with pytest.raises(RuntimeError):
        raise RuntimeError('downstream serializer failed')
    got = restore(captured, out, receipt)
    before, actual, _, _ = captured
    assert _source_digest(got.mesh) == _source_digest(actual.mesh)
    assert got.mesh.name == actual.mesh.name
    assert got.checks == actual.checks and got.records == actual.records
    assert got.kept[0] is got.edits[0] and got.rolled_back == []
    for name in ('new_faces', 'new_face_uv', 'new_face_normal'):
        assert getattr(got.edits[0], name).tobytes() == getattr(actual.edits[0], name).tobytes()
    assert not (tmp_path/'candidate').exists()
    assert receipt['fresh_check']['final'] == 'PASS'


@pytest.mark.parametrize('file', ['arrays.npz', 'result.json', 'edit-log.jsonl', 'checkpoint-receipt.json'])
def test_checkpoint_file_tamper_is_rejected(tmp_path, captured, file):
    out, receipt = save(tmp_path, captured)
    with (out/file).open('ab') as stream:
        stream.write(b'changed')
    with pytest.raises(ValueError, match='hash'):
        restore(captured, out, receipt)


def test_external_receipt_and_binding_are_required(tmp_path, captured):
    out, receipt = save(tmp_path, captured)
    with pytest.raises(ValueError, match='hash'):
        restore(captured, out, dict(receipt, receipt_sha256='0'*64))
    before, _, looks, binding = captured
    with pytest.raises(ValueError, match='binding'):
        api().restore_e7_checkpoint(before, looks, out, binding=dict(binding, run_id='other-attempt'),
            expected_receipt_sha256=receipt['receipt_sha256'])


def reseal(out):
    receipt = json.loads((out/'checkpoint-receipt.json').read_text())
    receipt['files'] = {name: sha256_file(out/name) for name in receipt['files']}
    (out/'checkpoint-receipt.json').write_text(json.dumps(receipt))
    return dict(receipt_sha256=sha256_file(out/'checkpoint-receipt.json'))


@pytest.mark.parametrize('entry', ['unknown.npy', 'mesh_positions.npy'])
def test_unknown_or_duplicate_archive_members_are_rejected(tmp_path, captured, entry):
    out, _ = save(tmp_path, captured)
    with zipfile.ZipFile(out/'arrays.npz', 'a') as archive:
        with pytest.warns(UserWarning) if entry == 'mesh_positions.npy' else __import__('contextlib').nullcontext():
            archive.writestr(entry, b'invalid')
    with pytest.raises(ValueError, match='archive'):
        restore(captured, out, reseal(out))


def test_array_reference_cannot_escape_checkpoint(tmp_path, captured):
    out, _ = save(tmp_path, captured)
    data = json.loads((out/'result.json').read_text())
    data['edits'][0]['new_faces'] = '../outside.npy'
    (out/'result.json').write_text(json.dumps(data))
    with pytest.raises(ValueError, match='reference'):
        restore(captured, out, reseal(out))


def test_actual_mesh_must_equal_actual_kept_edits(tmp_path, captured):
    before, outcome, looks, binding = captured
    changed = replace(outcome, mesh=replace(outcome.mesh, positions=outcome.mesh.positions.copy()))
    changed.mesh.positions[0, 0] += .25
    with pytest.raises(ValueError, match='outcome'):
        api().save_e7_checkpoint(before, changed, looks, tmp_path/'bad', binding=binding)


def test_e7_only_and_identity_partition_are_required(tmp_path, captured):
    before, outcome, looks, binding = captured
    for bad in [replace(outcome, result='legacy'), replace(outcome, stages=['legacy']),
                replace(outcome, kept=[replace(outcome.edits[0])])]:
        with pytest.raises(ValueError, match='E7|partition'):
            api().save_e7_checkpoint(before, bad, looks, tmp_path/'bad', binding=binding)


def test_cannot_overwrite_an_actual_checkpoint(tmp_path, captured):
    out, _ = save(tmp_path, captured)
    before, outcome, looks, binding = captured
    with pytest.raises(ValueError, match='exists'):
        api().save_e7_checkpoint(before, outcome, looks, out, binding=binding)


def test_complete_typed_edit_preserves_optional_nan_and_decision(tmp_path, captured):
    before, outcome, looks, binding = captured
    edit = replace(outcome.edits[0], new_face_normal=None, new_face_uv=np.full_like(outcome.edits[0].new_face_uv, np.nan),
                   decision={'question': 'fixture', 'answer': None})
    mesh, _ = apply_edits(before, [edit])
    # This fixture exercises capture of typed fields; its existing verdict is not a new repair admission.
    from engine.repair.kernel import stage_records
    records = stage_records(before, [edit], {i: looks.key_of(n) for i, n in enumerate(before.materials)}, 'E7')
    synthetic = replace(outcome, mesh=mesh, edits=[edit], kept=[edit], records=records+[{'check': outcome.checks[0]}])
    out = tmp_path/'typed-fields'
    receipt = api().save_e7_checkpoint(before, synthetic, looks, out, binding=binding)
    got = restore((before, synthetic, looks, binding), out, receipt)
    assert got.edits[0].decision == edit.decision
    assert got.edits[0].new_face_normal is None
    assert got.edits[0].new_face_uv.tobytes() == edit.new_face_uv.tobytes()
    assert np.signbit(got.mesh.normals[0, 0]) == np.signbit(mesh.normals[0, 0])


def test_input_drift_retains_diagnostic_actual_capture_without_verifying_it(tmp_path,captured):
    before,outcome,looks,binding = captured
    Path(binding['paths']['raw']).write_text('changed during kernel')
    out = tmp_path/'diagnostic-capture'
    with pytest.raises(ValueError,match='hash'):
        api().save_e7_checkpoint(before,outcome,looks,out,binding=binding)
    receipt = json.loads((out/'checkpoint-receipt.json').read_text())
    assert receipt['capture_only'] is True
    assert receipt['binding'] == json.loads(json.dumps(binding))
    with pytest.raises(ValueError,match='hash'):
        api().restore_e7_checkpoint(before,looks,out,binding=binding,
            expected_receipt_sha256=sha256_file(out/'checkpoint-receipt.json'))
