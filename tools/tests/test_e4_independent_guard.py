"""`tools/e4_independent_guard.py`: the saved-E4 readback (binding, assets, looks, material ids rebound by name) and
the unchanged `strict_guard` loaded by path, with the E3 guard's evidence files and keys."""
import json
from pathlib import Path
from shutil import copyfile, copytree

import pytest

from engine.io.snapshot import sha256_file
from tools.tests.test_main_infra_e4_binding import e4_fixture

REVISION = 'a' * 64
HELPER = '''
from dataclasses import dataclass

@dataclass
class Report:
    passed: bool
    totals: dict

def strict_guard(before, after, source, provenance, *, caster_factory=None, on_view=None):
    assert before.materials == after.materials, 'material ids must be rebound by name before the guard'
    assert before.n_faces == source.n_faces
    for label in ('Before', 'After'):
        for index in (1, 26):
            if on_view:
                on_view(label, index)
    passed = provenance.get('fixture_guard_passes', True)
    return Report(passed, {'after_faces': after.n_faces, 'caster': getattr(caster_factory, '__name__', 'default'),
                           'after_material_ids': after.face_material.tolist()}), 0.15
'''
ORACLE = 'class BoundedBruteCaster:\n    pass\n'


def run_layout(tmp_path, *, chained=False):
    """The run-root layout the guard reads, filled from the binding fixture: raw/, reference/, normalized/<F>/,
    independent-validator/{import-audit,preflight}/, raw-manifest.json, plus a helper tree with strict_guard."""
    (tmp_path / 'fixture').mkdir()
    inputs = e4_fixture(tmp_path / 'fixture', chained=chained)
    run = tmp_path / 'run'
    (run / 'raw').mkdir(parents=True)
    for name in ('source.obj', 'source.mtl', 'glass.png'):
        copyfile(inputs['raw'].parent / name, run / 'raw' / name)
    (run / 'reference').mkdir()
    copyfile(inputs['reference'], run / 'reference' / '7F.json')
    copytree(inputs['baseline'], run / 'normalized' / '7F')
    (run / 'independent-validator' / 'import-audit').mkdir(parents=True)
    copyfile(inputs['qualification'], run / 'independent-validator' / 'import-audit' / 'qualification-7F.json')
    (run / 'independent-validator' / 'preflight').mkdir()
    (run / 'independent-validator' / 'preflight' / 'materials-7F.json').write_text(json.dumps({'materials': {
        'glass': {'look': 'look-glass', 'map_kd': 'glass.png'}, 'facade': {'look': 'look-facade'}}}))
    (run / 'raw-manifest.json').write_text(json.dumps(dict(
        source_revision=REVISION,
        files=[dict(path=name, sha256=sha256_file(run / 'raw' / name)) for name in ('source.obj', 'source.mtl', 'glass.png')])))
    helper = tmp_path / 'helper' / 'tools' / 'main_infra_candidate.py'
    helper.parent.mkdir(parents=True)
    helper.write_text(HELPER)
    oracle = tmp_path / 'helper' / 'engine' / 'rays' / 'bounded_brute.py'
    oracle.parent.mkdir(parents=True)
    oracle.write_text(ORACLE)
    return run, inputs['candidate'], helper


def _args(run, candidate, helper, out, *extra):
    return ['--root', str(run), '--floor', '7F', '--raw-name', 'source.obj', '--candidate', str(candidate),
            '--out', str(out), '--helper', str(helper), '--job-id', 'JOB-E4', '--reviewer', 'test',
            '--expected-revision', REVISION, *extra]


def test_the_guard_reads_back_a_merge_only_candidate_and_writes_the_e3_evidence_files(tmp_path):
    from tools.e4_independent_guard import main
    run, candidate, helper = run_layout(tmp_path)
    out = tmp_path / 'guard'
    assert main(_args(run, candidate, helper, out)) == 0
    readback = json.loads((out / 'input-readback.json').read_text())
    receipt = json.loads((out / 'independent-guard.json').read_text())
    for key in ('job_id', 'floor_id', 'reviewer', 'source_revision', 'pid', 'readback_utc', 'paths', 'hashes',
                'source_sig_digits', 'physical_axis_quanta_inches', 'input_triangles', 'output_triangles',
                'removed_triangles', 'contract', 'assets', 'precision', 'stored_physical_membership_equal',
                'material_order_equal', 'source_to_engine', 'acceptance'):
        assert key in readback, key
    for key in ('guard', 'guard_depth_tol_inches', 'resolution', 'views', 'caster', 'wall_s', 'finished_utc',
                'post_guard_input_hashes'):
        assert key in receipt, key
    assert readback['input_triangles'] == 5 and readback['output_triangles'] == 3 and readback['removed_triangles'] == 4
    assert readback['new_triangles'] == 2 and readback['contract']['candidate_contract'] == 'e4_merge_only'
    assert readback['material_order_equal'] is False and readback['material_ids_rebound_by_name'] is True
    assert readback['acceptance'] is False and receipt['guard']['passed'] is True
    assert receipt['guard']['totals']['after_material_ids'] == [1, 0, 0], 'facade, glass, glass in BEFORE ids'
    assert receipt['caster'].startswith('unchanged') and receipt['post_guard_input_hashes']['matches_receipt'] is True
    assert [p['grid'] for p in readback['precision']] == ['stored', 'physical']
    assert all(p['kept_faces_identical'] is True for p in readback['precision'])
    assert (out / 'guard-progress.json').exists()
    assert readback['manifest_files'] == 3
    with pytest.raises(ValueError, match='exists'):
        main(_args(run, candidate, helper, out))


def test_the_guard_chains_through_e3_and_can_use_the_original_oracle(tmp_path):
    from tools.e4_independent_guard import main
    run, candidate, helper = run_layout(tmp_path, chained=True)
    out = tmp_path / 'guard'
    assert main(_args(run, candidate, helper, out, '--original-oracle')) == 0
    readback = json.loads((out / 'input-readback.json').read_text())
    receipt = json.loads((out / 'independent-guard.json').read_text())
    assert readback['contract']['candidate_contract'] == 'e3_then_e4_merge'
    assert readback['input_triangles'] == 5 and readback['output_triangles'] == 2 and readback['removed_triangles'] == 5
    assert readback['contract']['e3_removed_triangles'] == 1
    assert 'e3_candidate' in readback['paths'] and 'e3_source_faces' in readback['hashes']
    assert receipt['guard']['totals']['caster'] == 'BoundedBruteCaster'
    assert receipt['caster'].startswith('BoundedBruteCaster')


def test_a_failing_guard_returns_2_and_a_changed_frozen_source_is_refused(tmp_path):
    from tools.e4_independent_guard import main
    run, candidate, helper = run_layout(tmp_path)
    provenance = run / 'normalized' / '7F' / 'geometry-provenance.json'
    data = json.loads(provenance.read_text())
    data['fixture_guard_passes'] = False
    provenance.write_text(json.dumps(data))
    assert main(_args(run, candidate, helper, tmp_path / 'g1')) == 2
    (run / 'raw' / 'source.mtl').write_bytes((run / 'raw' / 'source.mtl').read_bytes() + b'\n')
    with pytest.raises(AssertionError, match='Frozen source changed'):
        main(_args(run, candidate, helper, tmp_path / 'g2'))
    assert (tmp_path / 'g2' / 'failure.txt').exists()


def test_a_tampered_candidate_is_refused_before_the_guard_runs(tmp_path):
    from tools.e4_independent_guard import main
    run, candidate, helper = run_layout(tmp_path)
    path = candidate / 'region-map.json'
    path.write_bytes(path.read_bytes() + b'\n')
    with pytest.raises(ValueError, match='hash'):
        main(_args(run, candidate, helper, tmp_path / 'guard'))
    assert not (tmp_path / 'guard' / 'guard-progress.json').exists()
