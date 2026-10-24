"""The owner's flag -> site -> replay loop (after real 7F chain run #3): failing floor faces of a validation are mapped
to the E4 regions responsible (`tools/main_infra_e4_replay.py`), the E4 runner reruns without them
(`--exclude-regions`), and `tools/run_e4_replay_loop.py` repeats E4 -> guard -> Validator until check 3 passes or a
failure has no explanation. Fixture chain only; the Validator and the guard are injected."""
import json
import shutil
from pathlib import Path

import pytest

from engine.io.snapshot import sha256_file
from tools.tests.test_e4_independent_guard import HELPER, ORACLE, REVISION
from tools.tests.test_main_infra_e5 import FACADE, PANEL, e3_fixture, run_root

COMMON = ['--floor', '7F', '--raw-name', 'source.obj']
CBR = 'coincident_backface_removed'


def chain(tmp_path):
    """run root + E3 fixture + real E5 (--from-e3) + real E4 (--from-e5 --allow-growth): `(root, inputs)`."""
    from tools.run_checked_e4_floor import main as e4_main
    from tools.run_checked_e5_floor import main as e5_main
    root = tmp_path / 'run'
    inputs = run_root(root)
    e3_fixture(inputs, root / 'e3' / '7F')
    assert e5_main(['--root', str(root)] + COMMON + ['--from-e3']) == 0
    assert e4_main(['--root', str(root)] + COMMON + ['--from-e5', '--allow-growth']) == 0
    return root, inputs


def receipt_for(inputs, e4_dir):
    """The Validator's physical-precision receipt for `e4_dir` (its audit marked guard passed, as the loop does)."""
    from tools.main_infra_physical_validation import load_physical_pair
    audit_path = e4_dir / 'stage-audit.json'
    audit = json.loads(audit_path.read_text())
    if audit.get('guard', {}).get('passed') is not True:        # the loop may already have recorded the guard receipt
        audit['guard'] = {'passed': True}
        audit_path.write_text(json.dumps(audit, indent=2))
    _before, _after, receipt = load_physical_pair(**dict(inputs, candidate=e4_dir))
    return receipt


def fake_validation(path, receipt, failing):
    """A validation.json whose check 3 fails by the floor alone with `failing` entries (baseline face ids)."""
    status = 'FAIL' if failing else 'PASS'
    report = {'version': 1, 'verdict': status, 'depth_tolerance_in': 0.05,
              'checks': {'textures': {'status': 'PASS', 'reasons': {}},
                         'problems': {'status': 'REPORT_ONLY'},
                         'nothing_deleted': {'status': status, 'deleted': 0, 'replaced': 0, 'covered': 0, 'overlaid': 0,
                                             'failed_by': {'samples': False, 'floor': bool(failing),
                                                           'floor_faces_failed': len(failing), 'samples_failed': 0},
                                             'floor': {'status': status, 'faces_failed': len(failing),
                                                       'failing': failing, 'measured': failing}}},
              'physical_precision': receipt}
    Path(path).parent.mkdir(parents=True, exist_ok=True)
    Path(path).write_text(json.dumps(report, indent=2))
    return path


def _region(e4_dir):
    (region,) = json.loads((e4_dir / 'region-map.json').read_text())['regions']
    return region


def _entry(face, kind, pixels, covering=(), viewpoint=None):
    return dict(face=face, kind=kind, pixels=pixels, at_least=False, visible_px=pixels,
                reasons={'covered' if kind == 'covered' else 'deleted': pixels},
                viewpoint=viewpoint or {'kind': 'direction', 'index': 15, 'at': [-0.6, -0.7, -0.2]},
                covering_faces=list(covering))


# ------------------------------------------------------------------------------------- failures -> regions

def test_failing_floor_faces_are_mapped_to_the_regions_that_cover_or_replaced_them(tmp_path):
    from tools.main_infra_e4_replay import explain_failures, main
    root, inputs = chain(tmp_path)
    e4_dir = root / 'e4' / '7F'
    receipt = receipt_for(inputs, e4_dir)
    region = _region(e4_dir)
    rid = region['region']
    failing = [_entry(PANEL[0], 'covered', 85.0, covering=region['new_triangles'][:1]),   # the covering face names it
               _entry(PANEL[1], 'covered', 27.1),                                           # geometry alone names it
               _entry(PANEL[2], 'removed', 7.0)]                                            # a source face of the region
    validation = fake_validation(tmp_path / 'v1' / 'validation.json', receipt, failing)
    got = explain_failures(candidate=e4_dir, validation=validation)
    assert got['regions'] == [rid] and got['unexplained'] == [] and got['failing'] == 3
    reasons = got['reasons'][str(rid)]
    assert [(r['face'], r['kind'], r['pixels']) for r in reasons] == [(PANEL[0], 'covered', 85.0), (PANEL[1], 'covered', 27.1),
                                                                        (PANEL[2], 'removed', 7.0)]
    assert {r['how'] for r in reasons} == {'covering_face', 'coplanar_overlap', 'source_face'}
    out = tmp_path / 'exclude.json'
    assert main(['--candidate', str(e4_dir), '--validation', str(validation), '--out', str(out)]) == 0
    written = json.loads(out.read_text())
    assert written['regions'] == [rid] and written['depth_tolerance_in'] == 0.05
    assert written['validation_sha256'] == sha256_file(validation)


def test_a_failure_no_region_explains_is_refused_and_listed(tmp_path):
    from tools.main_infra_e4_replay import main
    root, inputs = chain(tmp_path)
    e4_dir = root / 'e4' / '7F'
    receipt = receipt_for(inputs, e4_dir)
    region = _region(e4_dir)
    failing = [_entry(FACADE, 'covered', 61.0),                                            # far from every region
               _entry(PANEL[0], 'covered', 14.0, covering=region['new_triangles'][:1])]
    validation = fake_validation(tmp_path / 'v' / 'validation.json', receipt, failing)
    out = tmp_path / 'exclude.json'
    assert main(['--candidate', str(e4_dir), '--validation', str(validation), '--out', str(out)]) == 2
    written = json.loads(out.read_text())
    assert written['regions'] == [region['region']]
    assert [u['face'] for u in written['unexplained']] == [FACADE]


# -------------------------------------------------------------------------------- the runner's exclusion

def test_the_e4_runner_excludes_the_listed_regions_and_the_candidate_still_binds(tmp_path):
    from tools.main_infra_physical_validation import load_physical_pair
    from tools.run_checked_e4_floor import main as e4_main
    root, inputs = chain(tmp_path)
    first = root / 'e4' / '7F'
    rid = _region(first)['region']
    shutil.move(str(first), str(root / 'e4' / '7F-round1'))
    exclude = root / 'e4' / 'exclude.json'
    exclude.write_text(json.dumps({'regions': [rid], 'reasons': {str(rid): [{'face': PANEL[0], 'kind': 'covered'}]}}))
    assert e4_main(['--root', str(root)] + COMMON + ['--from-e5', '--allow-growth', '--exclude-regions', str(exclude)]) == 0
    second = root / 'e4' / '7F'
    audit = json.loads((second / 'stage-audit.json').read_text())
    assert audit['excluded_regions'] == [rid] and audit['exclude_regions_sha256'] == sha256_file(exclude)
    assert audit['input_triangles'] == 4 and audit['output_triangles'] == 4, 'the one region was excluded: no merge'
    assert audit['engine_report']['skipped']['not_allowed'] == 1 and audit['engine_report']['allowed_regions'] == []
    assert (second / 'exclude-regions.json').exists()
    audit['guard'] = {'passed': True}
    (second / 'stage-audit.json').write_text(json.dumps(audit))
    before, after, receipt = load_physical_pair(**dict(inputs, candidate=second))
    assert receipt['e4_merged_regions'] == 0 and after.n_faces == 4 and receipt['e3_removed_triangles'] == 1


# ------------------------------------------------------------------------------------------ the loop

def _fake_guard(out_root):
    def guard(*, root, floor, raw_name, candidate, out, **_kw):
        out.mkdir(parents=True)
        (out / 'independent-guard.json').write_text(json.dumps({'guard': {'passed': True, 'totals': {}}, 'acceptance': False}))
        return 0
    return guard


def _validator_script(script):
    """A Validator stand-in that answers each round from `script`: a list of lists of failing entries (baseline
    ids; a callable gets the round's E4 dir and returns the entries)."""
    calls = []

    def validator(*, candidate, out, inputs, **_kw):
        failing = script[len(calls)]
        failing = failing(candidate) if callable(failing) else failing
        calls.append(candidate)
        receipt = receipt_for(inputs, candidate)
        fake_validation(out / 'validation.json', receipt, failing)
        return 0 if not failing else 2
    validator.calls = calls
    return validator


def test_the_loop_excludes_the_covering_region_and_passes_on_round_two(tmp_path):
    from tools.run_e4_replay_loop import run_loop
    root = tmp_path / 'run'
    inputs = run_root(root)
    e3_fixture(inputs, root / 'e3' / '7F')
    from tools.run_checked_e5_floor import main as e5_main
    assert e5_main(['--root', str(root)] + COMMON + ['--from-e3']) == 0
    round1_failure = lambda e4_dir: [_entry(PANEL[0], 'covered', 196.8, covering=_region(e4_dir)['new_triangles'][:1],
                                            viewpoint={'kind': 'probe', 'index': 924, 'at': [925.2, -1358.3, 402.6]})]
    validator = _validator_script([round1_failure, []])
    summary = run_loop(root=root, floor='7F', raw_name='source.obj', rounds=3, allow=(CBR,), allow_growth=True,
                       run_guard=_fake_guard(root), run_validator=validator, inputs=inputs)
    assert summary['status'] == 'pass' and summary['rounds_run'] == 2 and len(validator.calls) == 2
    r1, r2 = summary['rounds']
    assert r1['nothing_deleted'] == 'FAIL' and r1['explained_regions'] and r1['unexplained'] == []
    assert r2['nothing_deleted'] == 'PASS' and r2['excluded_regions'] == r1['explained_regions']
    assert Path(r1['candidate']).name == '7F-round1' and Path(r2['candidate']).name == '7F-round2'
    assert (root / 'e4' / '7F-round1' / 'region-map.json').exists() and (root / 'e4' / '7F-round2' / 'exclude-regions.json').exists()
    audit2 = json.loads((root / 'e4' / '7F-round2' / 'stage-audit.json').read_text())
    assert audit2['excluded_regions'] == r1['explained_regions'] and audit2['output_triangles'] == 4
    assert audit2['guard']['passed'] is True and 'receipt_sha256' in audit2['guard'], 'the loop records the guard receipt'
    written = json.loads((root / 'e4' / '7F-replay-summary.json').read_text())
    assert written['status'] == 'pass' and written['final_candidate'] == str(root / 'e4' / '7F-round2')
    assert (root / 'e4' / '7F').is_dir() and json.loads((root / 'e4' / '7F' / 'stage-audit.json').read_text()) == audit2, \
        'the final passing round is also left at e4/<F> for the chain'


def test_an_unexplained_failure_stops_the_loop(tmp_path):
    from tools.run_e4_replay_loop import run_loop
    root = tmp_path / 'run'
    inputs = run_root(root)
    e3_fixture(inputs, root / 'e3' / '7F')
    from tools.run_checked_e5_floor import main as e5_main
    assert e5_main(['--root', str(root)] + COMMON + ['--from-e3']) == 0
    validator = _validator_script([[_entry(FACADE, 'covered', 61.0)], []])
    summary = run_loop(root=root, floor='7F', raw_name='source.obj', rounds=3, allow=(CBR,), allow_growth=True,
                       run_guard=_fake_guard(root), run_validator=validator, inputs=inputs)
    assert summary['status'] == 'unexplained' and summary['rounds_run'] == 1 and len(validator.calls) == 1
    assert [u['face'] for u in summary['rounds'][0]['unexplained']] == [FACADE]
    assert not (root / 'e4' / '7F-round2').exists()


def test_interior_poses_without_a_renderer_stop_the_loop_with_that_reason(tmp_path):
    from tools.run_e4_replay_loop import run_loop
    root = tmp_path / 'run'
    inputs = run_root(root)
    e3_fixture(inputs, root / 'e3' / '7F')
    from tools.run_checked_e5_floor import main as e5_main
    assert e5_main(['--root', str(root)] + COMMON + ['--from-e3']) == 0
    poses = tmp_path / 'poses.json'
    poses.write_text(json.dumps({'poses': [{'name': 'eye_2_qualified_3_probe_119', 'camera_position': [0, 0, 60],
                                            'target': [40, 0, 60], 'lens': 22}]}))
    validator = _validator_script([[], []])
    summary = run_loop(root=root, floor='7F', raw_name='source.obj', rounds=2, allow=(CBR,), allow_growth=True,
                       run_guard=_fake_guard(root), run_validator=validator, inputs=inputs, interior_poses=poses,
                       interior_px_max=60)
    assert summary['status'] == 'interior_unavailable' and summary['rounds_run'] == 1
    assert summary['interior']['status'] == 'unavailable' and 'renderer' in summary['interior']['reason']


def test_the_loop_cli_parses_its_arguments():
    from tools.run_e4_replay_loop import build_parser
    args = build_parser().parse_args(['--root', 'r', '--floor', '7F', '--raw-name', 'x.obj', '--rounds', '4',
                                      '--helper', 'h.py', '--job-id', 'J', '--reviewer', 'me', '--allow', CBR,
                                      '--interior-px-max', '40'])
    assert args.rounds == 4 and args.allow == [CBR] and args.interior_px_max == 40 and args.interior_poses is None
