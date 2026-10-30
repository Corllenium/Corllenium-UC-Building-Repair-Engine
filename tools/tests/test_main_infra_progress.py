import copy
import json

import pytest

from tools.main_infra_progress import heartbeat_progress, load_progress, set_stage, write_progress


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


def test_unity_ready_state_is_distinct_from_review_and_acceptance(tmp_path):
    # Owner instruction 2026-10-30: a floor whose fixed OBJ is saved in repo 03 reads "Ready for Unity import";
    # the signed flicker/crack targets are reported, not blocking, and nothing is accepted by the owner yet.
    doc = progress()
    doc['source_revision'] = 'a' * 64
    row = doc['floors']['4F']
    prefix = '/models/main-infra/' + 'a' * 64 + '/4F/fresh-run/'
    row.update(state='unity_ready', candidate_preview=prefix + 'candidate/preview.json',
               validator_ref=prefix + 'evidence/validation.json')
    write_progress(tmp_path / 'current.json', doc)
    assert load_progress(tmp_path / 'current.json')['floors']['4F']['state'] == 'unity_ready'
    row['accepted_preview'] = prefix + 'accepted/preview.json'
    with pytest.raises(ValueError, match='Unaccepted floor'):
        write_progress(tmp_path / 'current.json', doc)


def test_review_state_requires_matching_independent_proof(tmp_path):
    doc = progress()
    doc['source_revision'] = 'a' * 64
    row = doc['floors']['1F']
    prefix = '/models/main-infra/' + 'a' * 64 + '/1F/fresh-run/'
    row.update(state='needs_review', candidate_preview=prefix + 'candidate/preview.json',
               validator_ref=prefix + 'evidence/validation.json', evidence_refs=[prefix + 'evidence/independent-review.json'])
    with pytest.raises(ValueError, match='review proof'):
        write_progress(tmp_path / 'current.json', doc)
    row['validation_proof'] = dict(source_revision=doc['source_revision'], run_id=doc['run_id'], floor_id=row['floor_id'],
        candidate_preview=row['candidate_preview'], validator_ref=row['validator_ref'], validator_passed=True, independent=True,
        independent_review_ref=row['evidence_refs'][0], **{key: 'b' * 64 for key in ('before_sha256', 'engine_candidate_sha256',
        'source_candidate_sha256', 'validation_sha256', 'independent_review_sha256', 'qualification_sha256')})
    write_progress(tmp_path / 'current.json', doc)
    for key in ('run_id', 'source_revision', 'candidate_preview', 'before_sha256'):
        broken = copy.deepcopy(doc)
        broken['floors']['1F']['validation_proof'][key] = 'wrong'
        with pytest.raises(ValueError, match='review proof'):
            write_progress(tmp_path / 'current.json', broken)
    row['evidence_refs'] = [None]
    row['validation_proof']['independent_review_ref'] = None
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


def test_real_floor_time_stays_distinct_from_other_floors_and_heartbeat(tmp_path):
    from tools.main_infra_progress import update_floor
    path = tmp_path / 'current.json'
    write_progress(path, progress())
    update_floor(path, '1F', 'validating', 'Independent checks', now='2026-10-23T05:01:00Z')
    heartbeat_progress(path, now='2026-10-23T05:02:00Z')
    doc = load_progress(path)
    assert doc['floors']['1F']['last_work_event_at'] == '2026-10-23T05:01:00Z'
    assert 'last_work_event_at' not in doc['floors']['2F']


def test_stage_bars_and_floor_percent_are_optional_but_validated(tmp_path):
    # Owner instruction 2026-10-30: per-stage bars and a floor completion percent, absent fields render nothing new.
    path = tmp_path / 'current.json'
    doc = progress()
    write_progress(path, doc)
    row = doc['floors']['4F']
    row['stages'] = [{'id': 'e3', 'label': 'Hidden faces', 'status': 'done', 'percent': 100, 'note': None}]
    row['percent_complete'] = 20
    write_progress(path, doc)
    for broken_stage in ({'id': 'e3', 'label': 'Hidden faces', 'status': 'later', 'percent': 100, 'note': None},
                         {'id': 'e3', 'label': 'Hidden faces', 'status': 'done', 'percent': 101, 'note': None},
                         {'id': 'e3', 'label': '', 'status': 'done', 'percent': 100, 'note': None},
                         {'id': 'e3', 'label': 'Hidden faces', 'status': 'done', 'percent': 100, 'note': 3},
                         {'id': 'e3', 'label': 'Hidden faces', 'status': 'done', 'percent': 'all', 'note': None},
                         'e3'):
        broken = copy.deepcopy(doc)
        broken['floors']['4F']['stages'] = [broken_stage]
        with pytest.raises(ValueError, match='stage'):
            write_progress(path, broken)
    for broken_percent in (-1, 100.5, 'half', float('nan'), None):
        broken = copy.deepcopy(doc)
        broken['floors']['4F']['percent_complete'] = broken_percent
        with pytest.raises(ValueError, match='percent'):
            write_progress(path, broken)
    broken = copy.deepcopy(doc)
    broken['floors']['4F']['stages'] = {'e3': 1}
    with pytest.raises(ValueError, match='stages'):
        write_progress(path, broken)


def test_set_stage_keeps_pipeline_order_and_recomputes_the_floor_percent(tmp_path):
    path = tmp_path / 'current.json'
    write_progress(path, progress())
    set_stage(path, '4F', 'measure', 'running', 50, note='Guard 26 views', now='2026-10-30T01:00:00Z')
    set_stage(path, '4F', 'e3', 'done', 100, now='2026-10-30T01:01:00Z')
    set_stage(path, '4F', 'e4', 'skipped', 0, now='2026-10-30T01:02:00Z')
    set_stage(path, '4F', 'custom', 'pending', 0, label='Owner check', now='2026-10-30T01:03:00Z')
    set_stage(path, '4F', 'e5', 'failed', 40, note='Layer 3 unresolved', now='2026-10-30T01:04:00Z')
    doc = load_progress(path)
    row = doc['floors']['4F']
    assert [stage['id'] for stage in row['stages']] == ['e3', 'e5', 'e4', 'measure', 'custom']
    assert [stage['label'] for stage in row['stages']] == ['Hidden faces', 'Coincident layers', 'Coplanar merge',
                                                           'Guard + textures + coverage + Validator', 'Owner check']
    assert row['stages'][3] == {'id': 'measure', 'label': 'Guard + textures + coverage + Validator', 'status': 'running', 'percent': 50, 'note': 'Guard 26 views'}
    # done=100, failed e5=40, running measure=50, pending custom=0; skipped e4 is left out: (100+40+50+0)/4
    assert row['percent_complete'] == 47.5
    assert row['last_work_event_at'] == doc['last_work_event_at'] == '2026-10-30T01:04:00Z'
    assert 'stages' not in doc['floors']['5F']
    set_stage(path, '4F', 'measure', 'done', 100, label='Validator', now='2026-10-30T01:05:00Z')
    row = load_progress(path)['floors']['4F']
    assert row['stages'][3]['label'] == 'Validator' and row['stages'][3]['note'] is None
    assert row['percent_complete'] == 60
    with pytest.raises(ValueError):
        set_stage(path, '4F', 'publish', 'done', 120)
    with pytest.raises(ValueError):
        set_stage(path, '9F', 'publish', 'done', 100)
