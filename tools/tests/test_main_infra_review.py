import json

import pytest


def test_physical_validation_evidence_keeps_prior_report_immutable(tmp_path):
    from tools.main_infra_review import evidence_locations
    original, old_url = evidence_locations(tmp_path, 'revision', 'run', '1F')
    physical, new_url = evidence_locations(tmp_path, 'revision', 'run', '1F', 'physical-precision')
    assert original == tmp_path / 'independent-validator/1F'
    assert physical == tmp_path / 'independent-validator/physical-precision/1F'
    assert old_url == '/models/main-infra/revision/1F/run/evidence/'
    assert new_url == '/models/main-infra/revision/1F/run/evidence/physical-precision/'


@pytest.mark.parametrize('batch', ['..', '../other', '/absolute', 'a/b', 'a\\b', ''])
def test_validation_evidence_batch_cannot_escape_its_namespace(tmp_path, batch):
    from tools.main_infra_review import evidence_locations
    with pytest.raises(ValueError):
        evidence_locations(tmp_path, 'revision', 'run', '1F', batch)


def test_independent_review_cannot_promote_a_different_baseline_or_report():
    from tools.main_infra_review import bind_independent_review
    candidate = {'qualification_sha256': 'q', 'engine_candidate_sha256': 'after', 'source_candidate_sha256': 'source'}
    qualification = {'qualified': True, 'source_revision': 'revision', 'floor_id': '1F', 'engine_obj_sha256': 'before'}
    validation = {'verdict': 'PASS', 'inputs': {'before_sha256': 'before', 'after_sha256': 'after'}}
    independent = {'job_id': 'RUN', 'source_revision': 'revision', 'floor_id': '1F', 'reviewer': '/root/independent',
        'verdict': 'PASS', 'validation_json_sha256': 'v', 'post_validation_input_hashes': {'before': 'before', 'after': 'after', 'matches_report': True}}
    kwargs = dict(validation=validation, candidate=candidate, qualification=qualification, independent=independent,
        source_revision='revision', run_id='run', floor='1F', qualification_sha256='q', validation_sha256='v',
        expected_before_sha256='before')
    bind_independent_review(**kwargs)
    for field, value in [('floor_id', '7F'), ('source_revision', 'other'), ('validation_json_sha256', 'wrong'),
                         ('verdict', 'FAIL'), ('reviewer', ''), ('job_id', 'OTHER')]:
        bad = dict(independent, **{field: value})
        with pytest.raises(ValueError):
            bind_independent_review(**dict(kwargs, independent=bad))
    with pytest.raises(ValueError):
        bind_independent_review(**dict(kwargs, expected_before_sha256='unrelated'))
    with pytest.raises(ValueError):
        bind_independent_review(**dict(kwargs, qualification_sha256='changed'))


def test_floor_result_uses_real_bound_validation_and_never_accepts(tmp_path):
    from tools.main_infra_review import review_state
    candidate = {'engine_candidate_sha256': 'a' * 64}
    result = {'verdict': 'FAIL', 'inputs': {'after_sha256': 'a' * 64}, 'checks': {
        'textures': {'status': 'PASS'}, 'nothing_deleted': {'status': 'PASS'},
        'problems': {'status': 'FAIL', 'signed': True, 'kinds': {'flicker_diff': {'after': 12, 'target': 0}}}}}
    state, blocker = review_state(result, candidate)
    assert state == 'blocked' and 'flicker_diff=12' in blocker
    result['verdict'] = 'PASS'
    result['checks']['problems']['status'] = 'PASS'
    assert review_state(result, candidate) == ('needs_review', None)
    result['inputs']['after_sha256'] = 'b' * 64
    with pytest.raises(ValueError, match='candidate'):
        review_state(result, candidate)
