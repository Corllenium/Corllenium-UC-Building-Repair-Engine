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


#: Three layers: the glass panel's 4 slivers (0-3), an identical copy A (4-7), an identical copy B (8-11), the far
#: facade (12). E3 removes B's second sliver (9) and the facade; E5 then drops copy A's slivers as same-look twins.
RAW3 = '''mtllib source.mtl
v 0 0 0
v 2 0 0
v 2 0 1
v 0 0 1
v 0.6666666666666666 0 0.3333333333333333
v 1.3333333333333333 0 0.6666666666666666
v 10 0 0
v 11 0 0
v 10 0 1
vt 0 0
vt 1 0
vt 1 0.5
vt 0 0.5
vt 0.3333333333333333 0.16666666666666666
vt 0.6666666666666666 0.3333333333333333
vn 0 1 0
o panel
g glass_panel
usemtl glass
f 1/1/1 2/2/1 3/3/1
f 1/1/1 5/5/1 4/4/1
f 5/5/1 6/6/1 4/4/1
f 6/6/1 3/3/1 4/4/1
o panel_copy_a
g glass_a
usemtl glass
f 1/1/1 2/2/1 3/3/1
f 1/1/1 5/5/1 4/4/1
f 5/5/1 6/6/1 4/4/1
f 6/6/1 3/3/1 4/4/1
o panel_copy_b
g glass_b
usemtl glass
f 1/1/1 2/2/1 3/3/1
f 1/1/1 5/5/1 4/4/1
f 5/5/1 6/6/1 4/4/1
f 6/6/1 3/3/1 4/4/1
o far
g facade_bit
usemtl facade
f 7/1/1 8/2/1 9/4/1
'''
E3_REMOVED_B, FACADE3 = 9, 12


def triple_chain(tmp_path, *, e4=True):
    """RAW3 root + an E3 fixture that removed faces 9 and 12 + real E5 (`--from-e3`) [+ real E4]: `(root, inputs)`."""
    from tools.main_infra_e3 import save_survivor_pair
    from tools.run_checked_e4_floor import main as e4_main
    from tools.run_checked_e5_floor import main as e5_main
    from tools.tests.test_main_infra_e5 import FRAME, _common_audit, _source
    root = tmp_path / 'run'
    inputs = run_root(root, RAW3)
    source = _source(inputs)
    e3_dir = root / 'e3' / '7F'
    survivors = [f for f in range(13) if f not in (E3_REMOVED_B, FACADE3)]
    save_survivor_pair(source.in_frame(FRAME), source, survivors, e3_dir)
    records = [dict(stage='E3', engine='E3', kind='remove', site=0, faces=[E3_REMOVED_B, FACADE3], n_removed=2,
                    removed=['k1', 'k2'], added=[], n_added=0, n_new_points=0, material=None),
               {'check': dict(stage='E3', engine='E3', legacy=False, rollback=True, final='PASS',
                              runs=[{'status': 'PASS', 'failing': 0}])}]
    log = e3_dir / 'edit-log.jsonl'
    log.write_text(''.join(json.dumps(row) + '\n' for row in records))
    audit = dict(_common_audit(inputs, e3_dir), cleanup_mode='e3_remove_only', executed_stages=['E3'],
                 source_faces_sha256=sha256_file(e3_dir / 'source-faces.json'), edit_log_sha256=sha256_file(log),
                 checks=[records[-1]['check']])
    (e3_dir / 'stage-audit.json').write_text(json.dumps(audit))
    assert e5_main(['--root', str(root)] + COMMON + ['--from-e3']) == 0
    if e4:
        assert e4_main(['--root', str(root)] + COMMON + ['--from-e5', '--allow-growth']) == 0
    return root, inputs


def _e5_site_of(e5_dir, e3_dir, baseline_face):
    """The E5 site (kept) that removed `baseline_face`, through the E3 survivor list."""
    e3_faces = json.loads((e3_dir / 'source-faces.json').read_text())['source_faces']
    local = e3_faces.index(baseline_face)
    rows = [json.loads(l) for l in (e5_dir / 'edit-log.jsonl').read_text().splitlines() if l.strip()]
    (site,) = [r['site'] for r in rows if 'check' not in r and local in r['faces'] and not r.get('rolled_back')]
    return site


def test_e5_attribution_names_the_site_that_removed_a_face_or_that_was_its_cover(tmp_path):
    from tools.main_infra_e4_replay import explain_failures
    root, inputs = triple_chain(tmp_path)
    e4_dir, e5_dir, e3_dir = root / 'e4' / '7F', root / 'e5' / '7F', root / 'e3' / '7F'
    receipt = receipt_for(inputs, e4_dir)
    e5_audit = json.loads((e5_dir / 'stage-audit.json').read_text())
    assert e5_audit['engine_report']['dropped'] == 4, 'copy A (faces 4-7) went as same-look twins'
    site_5 = _e5_site_of(e5_dir, e3_dir, 5)
    failing = [_entry(E3_REMOVED_B, 'covered', 85.0),            # E3 removed it; copy A's sliver 5 was its cover
               _entry(5, 'removed', 7.0),                         # E5 removed it
               _entry(FACADE3, 'covered', 61.0)]                  # E3 removed it; nothing of E5 lay on it
    validation = fake_validation(tmp_path / 'v' / 'validation.json', receipt, failing)
    got = explain_failures(candidate=e4_dir, validation=validation)
    assert got['e5_sites'] == [site_5] and got['e4_regions'] == got['regions']
    rows = got['reasons']['e5_sites'][str(site_5)]
    assert [(r['face'], r['how']) for r in rows] == [(E3_REMOVED_B, 'e5_removed_its_cover'), (5, 'e5_removed')]
    assert [u['face'] for u in got['unexplained']] == [FACADE3]
    assert got['e5_candidate'] == str(e5_dir) and got['e3_candidate'] == str(e3_dir)


def test_the_e5_runner_excludes_sites_and_writes_where_it_is_told(tmp_path):
    from tools.main_infra_physical_validation import load_physical_pair
    from tools.run_checked_e5_floor import main as e5_main
    root, inputs = triple_chain(tmp_path, e4=False)
    e5_dir, e3_dir = root / 'e5' / '7F', root / 'e3' / '7F'
    site_5 = _e5_site_of(e5_dir, e3_dir, 5)
    exclude = root / 'e5' / 'exclude.json'
    exclude.write_text(json.dumps({'e5_sites': [site_5], 'reasons': {}}))
    out = root / 'e5' / '7F-round2'
    assert e5_main(['--root', str(root)] + COMMON + ['--from-e3', '--exclude-sites', str(exclude), '--out', str(out)]) == 0
    audit = json.loads((out / 'stage-audit.json').read_text())
    assert audit['excluded_sites'] == [site_5] and audit['exclude_sites_sha256'] == sha256_file(exclude)
    assert audit['engine_report']['excluded_sites'] == [site_5]
    assert (out / 'exclude-sites.json').exists()
    survivors = json.loads((out / 'source-faces.json').read_text())['source_faces']
    e3_faces = json.loads((e3_dir / 'source-faces.json').read_text())['source_faces']
    assert e3_faces.index(5) in survivors, 'the excluded site kept its face'
    assert audit['output_triangles'] == json.loads((e5_dir / 'stage-audit.json').read_text())['output_triangles'] + len(
        [r for r in (json.loads(l) for l in (e5_dir / 'edit-log.jsonl').read_text().splitlines() if l.strip())
         if 'check' not in r and r['site'] == site_5][0]['faces'])
    audit['guard'] = {'passed': True}
    (out / 'stage-audit.json').write_text(json.dumps(audit))
    _b, after, receipt = load_physical_pair(**dict(inputs, candidate=out))
    assert receipt['candidate_contract'] == 'e3_then_e5_cull' and after.n_faces == audit['output_triangles']


def test_the_e4_runner_can_read_a_named_e5_candidate_and_write_where_it_is_told(tmp_path):
    from tools.run_checked_e4_floor import main as e4_main
    root, inputs = triple_chain(tmp_path, e4=False)
    shutil.copytree(root / 'e5' / '7F', root / 'e5' / '7F-round2')
    out = root / 'e4' / '7F-round2'
    assert e4_main(['--root', str(root)] + COMMON + ['--from-e5', '--e5-candidate', str(root / 'e5' / '7F-round2'),
                    '--out', str(out)]) == 0
    audit = json.loads((out / 'stage-audit.json').read_text())
    assert audit['e5_candidate']['candidate'] == str(root / 'e5' / '7F-round2')
    assert not (root / 'e4' / '7F').exists()


def test_the_loop_reruns_e5_without_the_covering_site_and_passes(tmp_path):
    from tools.run_e4_replay_loop import run_loop
    root, inputs = triple_chain(tmp_path, e4=False)
    e5_dir, e3_dir = root / 'e5' / '7F', root / 'e3' / '7F'
    site_5 = _e5_site_of(e5_dir, e3_dir, 5)
    validator = _validator_script([[_entry(E3_REMOVED_B, 'covered', 85.0)], []])
    summary = run_loop(root=root, floor='7F', raw_name='source.obj', rounds=3, allow=(CBR,), allow_growth=True,
                       run_guard=_fake_guard(root), run_validator=validator, inputs=inputs)
    assert summary['status'] == 'pass' and summary['rounds_run'] == 2
    r1, r2 = summary['rounds']
    assert r1['explained_e5_sites'] == [site_5] and r1['e5_candidate'] == str(e5_dir)
    assert r2['e5_candidate'] == str(root / 'e5' / '7F-round2') and r2['excluded_sites'] == [site_5]
    e5_audit2 = json.loads((root / 'e5' / '7F-round2' / 'stage-audit.json').read_text())
    assert e5_audit2['excluded_sites'] == [site_5] and e5_audit2['cleanup_mode'] == 'e3_then_e5_cull'
    e4_audit2 = json.loads((root / 'e4' / '7F-round2' / 'stage-audit.json').read_text())
    assert e4_audit2['e5_candidate']['candidate'] == str(root / 'e5' / '7F-round2')
    assert summary['excluded_sites'] == [site_5] and summary['final_e5_candidate'] == str(root / 'e5' / '7F-round2')


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
    assert got['regions'] == [rid] and got['e4_regions'] == [rid] and got['e5_sites'] == []
    assert got['unexplained'] == [] and got['failing'] == 3
    reasons = got['reasons']['e4_regions'][str(rid)]
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
