import json
from shutil import copyfile

import numpy as np
import pytest

from engine.io.minecraft_floor import Frame, parse_floor
from engine.io.snapshot import sha256_file
from tools.tests.test_main_infra_physical_validation import fixture as original_fixture


def fixture(tmp_path):
    from tools.main_infra_e3 import save_survivor_pair
    inputs = original_fixture(tmp_path)
    original = inputs['candidate']
    audit = json.loads((original / 'stage-audit.json').read_text())
    native = json.loads(inputs['reference'].read_text())
    source = parse_floor(inputs['raw'].read_text(),
        triangulations={int(key): value for key, value in native['polygons'].items()})
    candidate = tmp_path / 'e3-candidate'
    save_survivor_pair(source.in_frame(Frame(1000 / 25.4, 'metres; Y-up')), source, [0], candidate)
    for row in audit['assets']:
        copyfile(inputs['baseline'] / row['path'], candidate / row['path'])
    records = [dict(stage='E3', engine='E3', kind='remove', site=0, faces=[1],
        n_removed=1, removed=['fixture-key'], added=[], n_added=0, n_new_points=0, material=None),
        {'check': dict(stage='E3', engine='E3', legacy=False, rollback=True, final='PASS',
                       runs=[{'status': 'PASS', 'failing': 0}])}]
    log = candidate / 'edit-log.jsonl'
    log.write_text(''.join(json.dumps(row) + '\n' for row in records))
    audit.update(cleanup_mode='e3_remove_only', executed_stages=['E3'],
        engine_candidate_sha256=sha256_file(candidate / 'candidate.engine.obj'),
        source_candidate_sha256=sha256_file(candidate / 'candidate.source.obj'),
        source_faces_sha256=sha256_file(candidate / 'source-faces.json'),
        edit_log_sha256=sha256_file(log), checks=[records[-1]['check']])
    (candidate / 'stage-audit.json').write_text(json.dumps(audit))
    inputs['candidate'] = candidate
    return inputs


def test_saved_e3_pair_has_exact_source_survivors_without_claiming_full_coverage(tmp_path):
    from tools.main_infra_physical_validation import load_physical_pair
    inputs = fixture(tmp_path)
    before, after, receipt = load_physical_pair(**inputs)
    assert before.n_faces == 2 and after.n_faces == 1
    np.testing.assert_array_equal(after.face_v, before.face_v[[0]])
    assert after.physical_quanta == before.physical_quanta
    assert receipt['candidate_contract'] == 'e3_remove_only'
    assert receipt['source_faces_sha256'] == sha256_file(inputs['candidate'] / 'source-faces.json')


@pytest.mark.parametrize('file', ['source-faces.json', 'edit-log.jsonl'])
def test_changed_survivor_proof_hash_is_refused(tmp_path, file):
    from tools.main_infra_physical_validation import load_physical_pair
    inputs = fixture(tmp_path)
    path = inputs['candidate'] / file
    path.write_bytes(path.read_bytes() + b'\n')
    with pytest.raises(ValueError, match='hash'):
        load_physical_pair(**inputs)


@pytest.mark.parametrize('change', ['flip', 'other_engine', 'unchecked', 'failed', 'rolled_back', 'new_point'])
def test_updated_log_hash_cannot_hide_unconfirmed_or_unsupported_removal(tmp_path, change):
    from tools.main_infra_physical_validation import load_physical_pair
    inputs = fixture(tmp_path)
    candidate = inputs['candidate']
    log = candidate / 'edit-log.jsonl'
    records = [json.loads(line) for line in log.read_text().splitlines()]
    if change == 'flip': records[0]['kind'] = 'flip'
    elif change == 'other_engine': records[0]['engine'] = 'E1'
    elif change == 'unchecked': records[-1]['check']['rollback'] = False
    elif change == 'failed': records[-1]['check']['final'] = 'FAIL'
    elif change == 'rolled_back': records[0]['rolled_back'] = True
    elif change == 'new_point': records[0]['n_new_points'] = 1
    log.write_text(''.join(json.dumps(row) + '\n' for row in records))
    audit_path = candidate / 'stage-audit.json'
    audit = json.loads(audit_path.read_text())
    audit.update(edit_log_sha256=sha256_file(log), checks=[records[-1]['check']])
    audit_path.write_text(json.dumps(audit))
    with pytest.raises(ValueError, match='E3|survivor|check|contract'):
        load_physical_pair(**inputs)


def test_unknown_cleanup_contract_is_refused(tmp_path):
    from tools.main_infra_physical_validation import load_physical_pair
    inputs = original_fixture(tmp_path)
    path = inputs['candidate'] / 'stage-audit.json'
    audit = json.loads(path.read_text())
    audit['cleanup_mode'] = 'arbitrary-remesh'
    path.write_text(json.dumps(audit))
    with pytest.raises(ValueError, match='contract'):
        load_physical_pair(**inputs)


@pytest.mark.parametrize('change', ['wrong_face', 'duplicate_face', 'boolean_face', 'input_count',
                                   'output_count', 'unchecked_stage', 'check_mismatch', 'added_face'])
def test_rehashed_proof_cannot_change_the_survivor_contract(tmp_path, change):
    from tools.main_infra_physical_validation import load_physical_pair
    inputs = fixture(tmp_path)
    candidate = inputs['candidate']
    mapping_path, log_path = candidate / 'source-faces.json', candidate / 'edit-log.jsonl'
    mapping = json.loads(mapping_path.read_text())
    records = [json.loads(line) for line in log_path.read_text().splitlines()]
    audit_path = candidate / 'stage-audit.json'
    audit = json.loads(audit_path.read_text())
    if change == 'wrong_face': mapping['source_faces'] = [1]
    elif change == 'duplicate_face': mapping['source_faces'] = [0, 0]
    elif change == 'boolean_face': mapping['source_faces'] = [False]
    elif change == 'input_count': mapping['input_triangles'] = 3
    elif change == 'output_count': mapping['output_triangles'] = 2
    elif change == 'unchecked_stage': audit['executed_stages'] = ['E3', 'E1']
    elif change == 'check_mismatch': audit['checks'][0]['final'] = 'FAIL'
    elif change == 'added_face': records[0].update(added=['new-key'], n_added=1)
    mapping_path.write_text(json.dumps(mapping))
    log_path.write_text(''.join(json.dumps(row) + '\n' for row in records))
    audit.update(source_faces_sha256=sha256_file(mapping_path), edit_log_sha256=sha256_file(log_path))
    audit_path.write_text(json.dumps(audit))
    with pytest.raises(ValueError, match='E3|survivor|check|contract'):
        load_physical_pair(**inputs)


def test_rolled_back_edit_keeps_its_original_source_face(tmp_path):
    from tools.main_infra_physical_validation import load_physical_pair
    inputs = fixture(tmp_path)
    candidate = inputs['candidate']
    log_path = candidate / 'edit-log.jsonl'
    records = [json.loads(line) for line in log_path.read_text().splitlines()]
    rolled = dict(records[0], site=1, faces=[0], rolled_back=True)
    records.insert(1, rolled)
    records[-1]['check']['rolled_back'] = [{'site': 1}]
    log_path.write_text(''.join(json.dumps(row) + '\n' for row in records))
    audit_path = candidate / 'stage-audit.json'
    audit = json.loads(audit_path.read_text())
    audit.update(edit_log_sha256=sha256_file(log_path), checks=[records[-1]['check']])
    audit_path.write_text(json.dumps(audit))
    before, after, receipt = load_physical_pair(**inputs)
    np.testing.assert_array_equal(after.face_v, before.face_v[[0]])
    assert receipt['e3_removed_triangles'] == 1


def test_default_contract_still_refuses_unique_triangle_loss(tmp_path):
    from tools.main_infra_physical_validation import load_physical_pair
    inputs = fixture(tmp_path)
    audit_path = inputs['candidate'] / 'stage-audit.json'
    audit = json.loads(audit_path.read_text())
    audit.pop('cleanup_mode')
    audit_path.write_text(json.dumps(audit))
    with pytest.raises(ValueError, match='missing 1 oriented appearance'):
        load_physical_pair(**inputs)
