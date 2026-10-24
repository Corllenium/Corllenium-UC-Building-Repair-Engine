"""`tools/e5_independent_guard.py`: the saved-E5 readback (binding through E3, kept faces = baseline minus E3-removed
minus E5-removed, assets, looks, material ids rebound by name) and the unchanged `strict_guard` loaded by path, with the
E3/E4 guards' receipt keys. Fixture chain (E3 fixture -> real E5 `--from-e3`), fake `strict_guard`."""
import json
from pathlib import Path

import pytest

from engine.io.snapshot import sha256_file
from tools.tests.test_e4_independent_guard import HELPER, ORACLE, REVISION
from tools.tests.test_main_infra_e5 import PANEL, e3_fixture, run_root

COMMON = ['--floor', '7F', '--raw-name', 'source.obj']


def layout(tmp_path):
    """run root + E3 fixture + real E5 (`--from-e3`), the frozen-source manifest and a helper tree with the fake
    `strict_guard`: `(root, candidate, helper)`."""
    from tools.run_checked_e5_floor import main as e5_main
    root = tmp_path / 'run'
    inputs = run_root(root)
    e3_fixture(inputs, root / 'e3' / '7F')
    assert e5_main(['--root', str(root)] + COMMON + ['--from-e3']) == 0
    (root / 'raw-manifest.json').write_text(json.dumps(dict(
        source_revision=REVISION,
        files=[dict(path=name, sha256=sha256_file(root / 'raw' / name)) for name in ('source.obj', 'source.mtl', 'glass.png')])))
    helper = tmp_path / 'helper' / 'tools' / 'main_infra_candidate.py'
    helper.parent.mkdir(parents=True)
    helper.write_text(HELPER)
    oracle = tmp_path / 'helper' / 'engine' / 'rays' / 'bounded_brute.py'
    oracle.parent.mkdir(parents=True)
    oracle.write_text(ORACLE)
    return root, root / 'e5' / '7F', helper


def _args(root, candidate, helper, out, *extra):
    return ['--root', str(root)] + COMMON + ['--candidate', str(candidate), '--out', str(out), '--helper', str(helper),
                                           '--job-id', 'JOB-E5', '--reviewer', 'test', '--expected-revision', REVISION, *extra]


def test_the_guard_reads_back_a_chained_e5_candidate_and_writes_the_e3_evidence_files(tmp_path):
    from tools.e5_independent_guard import main
    root, candidate, helper = layout(tmp_path)
    out = tmp_path / 'guard'
    assert main(_args(root, candidate, helper, out)) == 0
    readback = json.loads((out / 'input-readback.json').read_text())
    receipt = json.loads((out / 'independent-guard.json').read_text())
    for key in ('job_id', 'floor_id', 'reviewer', 'source_revision', 'pid', 'readback_utc', 'paths', 'hashes',
                'source_sig_digits', 'physical_axis_quanta_inches', 'input_triangles', 'output_triangles',
                'removed_triangles', 'contract', 'assets', 'precision', 'stored_physical_membership_equal',
                'material_order_equal', 'material_ids_rebound_by_name', 'source_to_engine', 'acceptance', 'manifest_files'):
        assert key in readback, key
    assert readback['contract']['candidate_contract'] == 'e3_then_e5_cull'
    assert readback['input_triangles'] == 9 and readback['output_triangles'] == 4
    assert readback['removed_triangles'] == 5, 'E3 removed 1, E5 removed 4'
    assert readback['contract']['e3_removed_triangles'] == 1 and readback['contract']['e5_removed_triangles'] == 4
    assert readback['contract']['baseline_kept_source_faces'] == PANEL
    assert {'e3_candidate', 'e3_source_faces', 'e3_audit', 'mapping', 'edit_log', 'after', 'source_after', 'before'} <= set(readback['hashes'])
    assert readback['acceptance'] is False and readback['manifest_files'] == 3
    assert receipt['guard']['passed'] is True and receipt['views'] == 26 and receipt['removed_triangles'] == 5
    assert receipt['post_guard_input_hashes']['matches_receipt'] is True
    assert receipt['caster'].startswith('unchanged helper')
    assert [p['grid'] for p in readback['precision']] == ['stored', 'physical']
    assert all(p['kept_faces'] == 4 and p['removed_faces'] == 5 and p['added_faces'] == 0 for p in readback['precision'])


def test_the_guard_can_use_the_original_oracle_and_runs_on_a_pending_audit(tmp_path):
    from tools.e5_independent_guard import main
    root, candidate, helper = layout(tmp_path)
    audit_path = candidate / 'stage-audit.json'
    assert json.loads(audit_path.read_text())['guard'] == {'passed': False, 'state': 'pending'}
    out = tmp_path / 'guard'
    assert main(_args(root, candidate, helper, out, '--original-oracle')) == 0
    receipt = json.loads((out / 'independent-guard.json').read_text())
    assert receipt['guard']['totals']['caster'] == 'BoundedBruteCaster' and receipt['caster'].startswith('BoundedBruteCaster')
    assert json.loads(audit_path.read_text())['guard'] == {'passed': False, 'state': 'pending'}, 'the guard never writes the audit'


def test_a_failing_guard_returns_2_and_a_changed_frozen_source_is_refused(tmp_path):
    from tools.e5_independent_guard import main
    root, candidate, helper = layout(tmp_path)
    provenance = root / 'normalized' / '7F' / 'geometry-provenance.json'
    data = json.loads(provenance.read_text())
    data['fixture_guard_passes'] = False
    provenance.write_text(json.dumps(data))
    assert main(_args(root, candidate, helper, tmp_path / 'g1')) == 2
    (root / 'raw' / 'source.mtl').write_bytes((root / 'raw' / 'source.mtl').read_bytes() + b'\n')
    with pytest.raises(AssertionError, match='Frozen source changed'):
        main(_args(root, candidate, helper, tmp_path / 'g2'))
    assert (tmp_path / 'g2' / 'failure.txt').exists()


@pytest.mark.parametrize('file', ['source-faces.json', 'edit-log.jsonl'])
def test_a_tampered_candidate_is_refused_before_the_guard_runs(tmp_path, file):
    from tools.e5_independent_guard import main
    root, candidate, helper = layout(tmp_path)
    path = candidate / file
    path.write_bytes(path.read_bytes() + b'\n')
    with pytest.raises(ValueError, match='hash'):
        main(_args(root, candidate, helper, tmp_path / 'guard'))
    assert not (tmp_path / 'guard' / 'guard-progress.json').exists()


def test_an_e5_only_candidate_without_the_e3_chain_is_also_accepted(tmp_path):
    from tools.e5_independent_guard import main
    from tools.tests.test_main_infra_e5 import e5_fixture
    inputs = e5_fixture(tmp_path)                                   # e5_cull_only over the baseline
    root = tmp_path / 'run'
    (root / 'raw-manifest.json').write_text(json.dumps(dict(
        source_revision=REVISION,
        files=[dict(path=name, sha256=sha256_file(root / 'raw' / name)) for name in ('source.obj', 'source.mtl', 'glass.png')])))
    helper = tmp_path / 'helper' / 'tools' / 'main_infra_candidate.py'
    helper.parent.mkdir(parents=True)
    helper.write_text(HELPER)
    out = tmp_path / 'guard'
    assert main(_args(root, inputs['candidate'], helper, out)) == 0
    readback = json.loads((out / 'input-readback.json').read_text())
    assert readback['contract']['candidate_contract'] == 'e5_cull_only' and readback['removed_triangles'] == 4
    assert readback['input_triangles'] == 9 and readback['output_triangles'] == 5
    assert 'e3_candidate' not in readback['paths']
