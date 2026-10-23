import json

import pytest

from tools.tests.test_main_infra_e3_binding import fixture


def test_preview_packages_checked_original_survivors_without_full_coverage_claim(tmp_path):
    from tools.main_infra_preview import package_preview
    inputs = fixture(tmp_path)
    proof = json.loads(inputs['qualification'].read_text())
    result = package_preview(baseline=inputs['baseline'], qualification=inputs['qualification'],
        public=tmp_path / 'public', revision=proof['source_revision'], run_id='checked-e3',
        floor=proof['floor_id'], kind='candidate', candidate=inputs['candidate'])
    manifest = json.loads(result['manifest_path'].read_text())
    assert manifest['kind'] == 'candidate'
    assert manifest['run_id'] == 'checked-e3'
    assert (result['manifest_path'].parent / 'model.obj').read_bytes() == (inputs['candidate'] / 'candidate.source.obj').read_bytes()
    assert not json.loads((inputs['candidate'] / 'stage-audit.json').read_text()).get('source_coverage', {}).get('exact_coverage', False)


def test_preview_refuses_rehashed_unsupported_e3_edit_before_any_public_write(tmp_path):
    from tools.main_infra_preview import package_preview
    from engine.io.snapshot import sha256_file
    inputs = fixture(tmp_path)
    candidate = inputs['candidate']
    log = candidate / 'edit-log.jsonl'
    rows = [json.loads(line) for line in log.read_text().splitlines()]
    rows[0]['kind'] = 'flip'
    log.write_text(''.join(json.dumps(row) + '\n' for row in rows))
    audit_path = candidate / 'stage-audit.json'
    audit = json.loads(audit_path.read_text())
    audit['edit_log_sha256'] = sha256_file(log)
    audit_path.write_text(json.dumps(audit))
    proof = json.loads(inputs['qualification'].read_text())
    with pytest.raises(ValueError, match='E3|contract|survivor'):
        package_preview(baseline=inputs['baseline'], qualification=inputs['qualification'],
            public=tmp_path / 'public', revision=proof['source_revision'], run_id='checked-e3',
            floor=proof['floor_id'], kind='candidate', candidate=candidate)
    assert not (tmp_path / 'public').exists()
