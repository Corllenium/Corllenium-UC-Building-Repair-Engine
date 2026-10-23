from dataclasses import replace
import json

import numpy as np
import pytest

from engine.io.snapshot import sha256_file
from engine.repair.kernel import edit_keys
from engine.repair.types import Edit
from engine.validate.checks import Looks
from tools.main_infra_physical_validation import load_physical_pair
from tools.tests.test_main_infra_e3_binding import fixture as original_fixture


def fixture(tmp_path):
    inputs = original_fixture(tmp_path)
    before, _after, receipt = load_physical_pair(**inputs)
    looks = Looks(key={'wall': 'original-wall'}, flat=frozenset({'original-wall'}))
    edit = Edit('E3', 'remove', (1,), None, None, 0, 'original hidden-site reason', {})
    log = inputs['candidate'] / 'edit-log.jsonl'
    records = [json.loads(line) for line in log.read_text().splitlines()]
    records[0].update(reason=edit.reason, **edit_keys(before, [edit], {0: looks.key_of('wall')})[0])
    log.write_text(''.join(json.dumps(row) + '\n' for row in records))
    audit_path = inputs['candidate'] / 'stage-audit.json'
    audit = json.loads(audit_path.read_text())
    audit.update(edit_log_sha256=sha256_file(log), input_receipt=receipt)
    audit_path.write_text(json.dumps(audit))
    return before, looks, inputs['candidate'], sha256_file(audit_path)


def test_replay_uses_original_kept_edit_keys_reason_and_site(tmp_path):
    from tools.main_infra_e3_replay import load_replay_plan
    before, looks, candidate, audit_hash = fixture(tmp_path)
    edits, receipt = load_replay_plan(before, looks, candidate,
        expected_audit_sha256=audit_hash, restore_sites=())
    assert len(edits) == 1
    assert (edits[0].engine, edits[0].kind, edits[0].faces, edits[0].site, edits[0].reason) == (
        'E3', 'remove', (1,), 0, 'original hidden-site reason')
    original = json.loads((candidate / 'edit-log.jsonl').read_text().splitlines()[0])
    assert edit_keys(before, edits, {0: looks.key_of('wall')})[0]['removed'] == original['removed']
    assert receipt['remaining_sites'] == 1 and receipt['remaining_removed_triangles'] == 1


def test_whole_restored_site_is_excluded_and_unknown_site_is_refused(tmp_path):
    from tools.main_infra_e3_replay import load_replay_plan
    before, looks, candidate, audit_hash = fixture(tmp_path)
    edits, receipt = load_replay_plan(before, looks, candidate,
        expected_audit_sha256=audit_hash, restore_sites=(0,))
    assert edits == [] and receipt['restored_sites'] == [0]
    assert receipt['remaining_sites'] == 0 and receipt['remaining_removed_triangles'] == 0
    with pytest.raises(ValueError, match='site'):
        load_replay_plan(before, looks, candidate, expected_audit_sha256=audit_hash, restore_sites=(99,))


@pytest.mark.parametrize('target', ['stage-audit.json', 'edit-log.jsonl', 'source-faces.json',
                                    'candidate.engine.obj', 'candidate.source.obj'])
def test_replay_refuses_changed_frozen_original_artifact(tmp_path, target):
    from tools.main_infra_e3_replay import load_replay_plan
    before, looks, candidate, audit_hash = fixture(tmp_path)
    path = candidate / target
    path.write_bytes(path.read_bytes() + b'\n')
    with pytest.raises(ValueError, match='hash'):
        load_replay_plan(before, looks, candidate, expected_audit_sha256=audit_hash, restore_sites=())


@pytest.mark.parametrize('change', ['flip', 'add', 'engine', 'new_point', 'out_of_bounds', 'forged_key'])
def test_even_rehashed_log_must_describe_original_e3_removals(tmp_path, change):
    from tools.main_infra_e3_replay import load_replay_plan
    before, looks, candidate, _audit_hash = fixture(tmp_path)
    log = candidate / 'edit-log.jsonl'
    records = [json.loads(line) for line in log.read_text().splitlines()]
    if change == 'flip': records[0]['kind'] = 'flip'
    elif change == 'add': records[0].update(kind='add', added=['new-face'], n_added=1)
    elif change == 'engine': records[0]['engine'] = 'E1'
    elif change == 'new_point': records[0]['n_new_points'] = 1
    elif change == 'out_of_bounds': records[0]['faces'] = [before.n_faces]
    elif change == 'forged_key': records[0]['removed'] = ['forged-original-key']
    log.write_text(''.join(json.dumps(row) + '\n' for row in records))
    audit_path = candidate / 'stage-audit.json'
    audit = json.loads(audit_path.read_text())
    audit['edit_log_sha256'] = sha256_file(log)
    audit_path.write_text(json.dumps(audit))
    with pytest.raises(ValueError, match='E3|source|key|face'):
        load_replay_plan(before, looks, candidate,
            expected_audit_sha256=sha256_file(audit_path), restore_sites=())


@pytest.mark.parametrize('field', ['positions', 'physical_quanta'])
def test_replay_refuses_an_unbound_before_mesh(tmp_path, field):
    from tools.main_infra_e3_replay import load_replay_plan
    before, looks, candidate, audit_hash = fixture(tmp_path)
    if field == 'positions':
        values = before.positions.copy()
        values[0, 0] += .01
    else:
        values = tuple(value * 2 for value in before.physical_quanta)
    bad = replace(before, **{field: values})
    with pytest.raises(ValueError, match='BEFORE|source'):
        load_replay_plan(bad, looks, candidate, expected_audit_sha256=audit_hash, restore_sites=())


def test_replay_refuses_changed_source_look_keys(tmp_path):
    from tools.main_infra_e3_replay import load_replay_plan
    before, _looks, candidate, audit_hash = fixture(tmp_path)
    with pytest.raises(ValueError, match='key'):
        load_replay_plan(before, Looks(key={'wall': 'different-look'}), candidate,
            expected_audit_sha256=audit_hash, restore_sites=())


def test_fresh_default_site_check_rolls_back_visible_fixture_despite_original_pass(tmp_path):
    from tools.main_infra_e3_replay import run_checked_replay
    before, looks, candidate, audit_hash = fixture(tmp_path)
    original = json.loads((candidate / 'stage-audit.json').read_text())['checks'][0]
    assert original['final'] == 'PASS'
    outcome, survivors, _receipt = run_checked_replay(before, looks, candidate,
        expected_audit_sha256=audit_hash, restore_sites=())
    assert outcome.checks[0]['first'] == 'FAIL'
    assert outcome.checks[0]['final'] == 'NOTHING KEPT'
    assert outcome.checks[0]['rollback'] is True and outcome.checks[0]['legacy'] is False
    assert not outcome.kept and len(outcome.rolled_back) == 1
    np.testing.assert_array_equal(survivors, np.arange(before.n_faces))
