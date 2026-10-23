import copy
import json

import pytest

from tools.main_infra_progress import heartbeat_progress, load_progress, write_progress


def progress():
    return {
        'schema_version': 1, 'building_id': 'MAIN_INFRA', 'source_revision': None,
        'run_id': 'fresh-run', 'source_label': 'Fresh Minecraft export',
        'source_state': 'inventoried_not_frozen', 'scale_metres_per_block': 1,
        'state': 'running', 'step': 'Reading original polygons',
        'updated_at': '2026-10-23T05:00:00Z',
        'last_work_event_at': '2026-10-23T05:00:00Z', 'heartbeat_at': None,
        'floors': {f'{n}F': {
            'floor_id': f'MAIN_INFRA_{n}F', 'state': 'queued', 'step': 'Waiting for pilots',
            'blocker': None, 'source_preview': None, 'candidate_preview': None,
            'accepted_preview': None, 'evidence_refs': [], 'validator_ref': None,
            'owner_decision_ref': None,
        } for n in range(1, 8)},
    }


def test_publishes_real_floor_states_without_changing_other_buildings(tmp_path):
    canonical = tmp_path / 'current.json'
    published = tmp_path / 'building-repair-status.json'
    published.write_text(json.dumps({'state': 'completed', 'completedUnits': {'CHTM': {'trisAfter': 90}}}))
    doc = progress()
    doc['floors']['1F'].update(state='blocked', blocker='Source polygon line 10224')
    write_progress(canonical, doc, published_path=published)
    assert load_progress(canonical)['floors']['1F']['blocker'] == 'Source polygon line 10224'
    displayed = json.loads(published.read_text())
    assert displayed['completedUnits'] == {'CHTM': {'trisAfter': 90}}
    assert displayed['freshMainInfra']['floors']['1F']['state'] == 'blocked'


def test_invalid_write_keeps_the_previous_valid_snapshot(tmp_path):
    path = tmp_path / 'current.json'
    write_progress(path, progress())
    original = path.read_bytes()
    malformed = progress()
    malformed['floors'] = {}
    with pytest.raises(ValueError):
        write_progress(path, malformed)
    assert path.read_bytes() == original
    assert list(tmp_path.glob('*.tmp')) == []


def test_refuses_accepted_state_without_independent_validation_and_owner_proof(tmp_path):
    doc = progress()
    doc['floors']['1F']['state'] = 'accepted'
    with pytest.raises(ValueError):
        write_progress(tmp_path / 'current.json', doc)


def test_cancelled_run_cannot_be_resurrected_by_late_events(tmp_path):
    path = tmp_path / 'current.json'
    doc = progress()
    doc['state'] = 'cancelled'
    write_progress(path, doc)
    late = progress()
    late['updated_at'] = '2026-10-23T05:01:00Z'
    with pytest.raises(ValueError):
        write_progress(path, late)
    assert load_progress(path)['state'] == 'cancelled'


def test_another_run_requires_explicit_replacement(tmp_path):
    path = tmp_path / 'current.json'
    write_progress(path, progress())
    other = progress()
    other['run_id'] = 'another-run'
    with pytest.raises(ValueError):
        write_progress(path, other)
    other['replaces_run_id'] = 'fresh-run'
    write_progress(path, other)
    assert load_progress(path)['run_id'] == 'another-run'


def test_frozen_source_cannot_change_under_the_same_run(tmp_path):
    path = tmp_path / 'current.json'
    doc = progress()
    doc['source_revision'] = 'a' * 64
    write_progress(path, doc)
    changed = copy.deepcopy(doc)
    changed['source_revision'] = 'b' * 64
    with pytest.raises(ValueError):
        write_progress(path, changed)


def test_heartbeat_is_not_a_work_event(tmp_path):
    path = tmp_path / 'current.json'
    write_progress(path, progress())
    heartbeat_progress(path, now='2026-10-23T05:01:00Z')
    doc = load_progress(path)
    assert doc['heartbeat_at'] == '2026-10-23T05:01:00Z'
    assert doc['last_work_event_at'] == '2026-10-23T05:00:00Z'


def test_partial_json_is_not_a_valid_progress_document(tmp_path):
    path = tmp_path / 'current.json'
    path.write_text('{"schema_version":')
    with pytest.raises(ValueError):
        load_progress(path)
