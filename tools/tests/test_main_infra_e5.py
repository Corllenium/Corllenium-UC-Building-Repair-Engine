"""The checked E5 run, its survivor proof, the saved pair and its binding (MAIN-INFRA-E4-MERGE-20261023, E5): both
cleanup modes through `load_physical_pair`, the floor runner, and the E3 -> E5 -> E4 chain on a fixture run root."""
import json
from pathlib import Path
from shutil import copyfile

import numpy as np
import pytest
from PIL import Image

from engine.io.minecraft_floor import Frame, parse_floor
from engine.io.obj_reader import read_obj
from engine.io.snapshot import sha256_file, snapshot_object
from engine.repair.kernel import write_records
from engine.tests.test_validate_checks import _looks

FRAME = Frame(1000 / 25.4, 'owner: 1 block = 1 metre; Y-up')
FLATNESS = {'glass': 50.0}
#: A 2 x 1 (source units) glass panel in the y = 0 plane cut into 4 slivers (faces 0-3), an IDENTICAL copy of the four
#: slivers (faces 4-7: same vertices, UVs and winding -- the fresh export's flicker_same twin), and a far facade
#: triangle (face 8).
RAW = '''mtllib source.mtl
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
o panel_twin
g glass_twin
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
PANEL, TWIN, FACADE = [0, 1, 2, 3], [4, 5, 6, 7], 8


def floor():
    return parse_floor(RAW, name='fixture')


def looks():
    return _looks('glass', 'facade')


def run_root(root):
    """A qualified fresh-floor run root in the layout the floor runners read (raw/, reference/, normalized/7F/,
    independent-validator/{import-audit,preflight}/, candidates/7F/), around RAW. Returns `load_physical_pair`'s
    inputs for the duplicate-only candidate."""
    from tools.repair_fresh_main_infra import normalize_reference
    root = Path(root)
    (root / 'raw').mkdir(parents=True)
    raw = root / 'raw' / 'source.obj'
    raw.write_text(RAW, encoding='utf-8')
    (root / 'raw' / 'source.mtl').write_text('newmtl glass\nKd 1 1 1\nmap_Kd glass.png\nnewmtl facade\nKd 0.5 0.5 0.5\n')
    Image.new('RGB', (2, 2), (20, 80, 30)).save(root / 'raw' / 'glass.png')
    polygons = {str(i): [[0, 1, 2]] for i, line in enumerate(RAW.splitlines(), 1) if line.startswith('f ')}
    (root / 'reference').mkdir()
    reference = root / 'reference' / '7F.json'
    reference.write_text(json.dumps(dict(schema_version=1, source_sha256=sha256_file(raw), unmatched_polygons=0,
                                         blender_version='fixture', raw_polygon_count=9, imported_polygon_count=9,
                                         triangle_count=9, polygons=polygons)))
    base = root / 'normalized' / '7F'
    normalize_reference(raw, reference, base, FRAME)
    (root / 'independent-validator' / 'import-audit').mkdir(parents=True)
    qualification = root / 'independent-validator' / 'import-audit' / 'qualification-7F.json'
    qualification.write_text(json.dumps(dict(qualified=True, floor_id='7F', source_revision='a' * 64,
                                             source_obj_sha256=sha256_file(raw),
                                             native_reference_sha256=sha256_file(reference),
                                             engine_obj_sha256=sha256_file(base / 'before.engine.obj'),
                                             source_triangles_sha256=sha256_file(base / 'before.source.obj'))))
    (root / 'independent-validator' / 'preflight').mkdir()
    (root / 'independent-validator' / 'preflight' / 'materials-7F.json').write_text(json.dumps({'materials': {
        'glass': {'look': 'look-glass', 'map_kd': 'glass.png'}, 'facade': {'look': 'look-facade'}}}))
    candidate = root / 'candidates' / '7F'
    candidate.mkdir(parents=True)
    snapshot = snapshot_object(base / 'before.engine.obj', candidate / 'snapshots', interval_s=0).dir
    copyfile(base / 'before.engine.obj', candidate / 'candidate.engine.obj')
    copyfile(base / 'before.source.obj', candidate / 'candidate.source.obj')
    assets = json.loads((base / 'geometry-provenance.json').read_text())['assets']
    for row in assets:
        copyfile(base / row['path'], candidate / row['path'])
    (candidate / 'stage-audit.json').write_text(json.dumps(dict(
        before_snapshot=str(snapshot), qualification_sha256=sha256_file(qualification), guard={'passed': True},
        engine_candidate_sha256=sha256_file(candidate / 'candidate.engine.obj'),
        source_candidate_sha256=sha256_file(candidate / 'candidate.source.obj'), assets=assets)))
    return dict(raw=raw, reference=reference, baseline=base, qualification=qualification, candidate=candidate)


def _source(inputs):
    native = json.loads(inputs['reference'].read_text())
    return parse_floor(inputs['raw'].read_text(encoding='utf-8'),
                       triangulations={int(k): v for k, v in native['polygons'].items()})


def _common_audit(inputs, candidate):
    original = json.loads((inputs['candidate'] / 'stage-audit.json').read_text())
    for row in original['assets']:
        copyfile(inputs['baseline'] / row['path'], candidate / row['path'])
    return dict(before_snapshot=original['before_snapshot'], qualification_sha256=original['qualification_sha256'],
                assets=original['assets'], guard={'passed': True},
                engine_candidate_sha256=sha256_file(candidate / 'candidate.engine.obj'),
                source_candidate_sha256=sha256_file(candidate / 'candidate.source.obj'))


def e3_fixture(inputs, candidate):
    """An E3 candidate at `candidate` that removed the facade triangle (face 8), with its log and audit."""
    from tools.main_infra_e3 import save_survivor_pair
    source = _source(inputs)
    save_survivor_pair(source.in_frame(FRAME), source, PANEL + TWIN, candidate)
    records = [dict(stage='E3', engine='E3', kind='remove', site=0, faces=[FACADE], n_removed=1, removed=['fixture-key'],
                    added=[], n_added=0, n_new_points=0, material=None),
               {'check': dict(stage='E3', engine='E3', legacy=False, rollback=True, final='PASS',
                              runs=[{'status': 'PASS', 'failing': 0}])}]
    log = candidate / 'edit-log.jsonl'
    log.write_text(''.join(json.dumps(row) + '\n' for row in records))
    audit = dict(_common_audit(inputs, candidate), cleanup_mode='e3_remove_only', executed_stages=['E3'],
                 source_faces_sha256=sha256_file(candidate / 'source-faces.json'), edit_log_sha256=sha256_file(log),
                 checks=[records[-1]['check']])
    (candidate / 'stage-audit.json').write_text(json.dumps(audit))
    return candidate


def e5_fixture(tmp_path, *, chained=False):
    """The run root plus an E5 candidate over the baseline (`e5_cull_only`) or over an E3 candidate that removed the
    facade (`e3_then_e5_cull`); `inputs['candidate']` points at the E5 candidate."""
    from tools.main_infra_e3 import save_survivor_pair
    from tools.main_infra_e4 import floor_from_candidate
    from tools.main_infra_e5 import run_checked_e5
    inputs = run_root(tmp_path / 'run')
    e3_binding = None
    if chained:
        e3_dir = e3_fixture(inputs, tmp_path / 'run' / 'e3' / '7F')
        e3_audit = json.loads((e3_dir / 'stage-audit.json').read_text())
        source_floor = floor_from_candidate(e3_dir / 'candidate.source.obj')
        e3_binding = dict(candidate=str(e3_dir), engine_candidate_sha256=e3_audit['engine_candidate_sha256'],
                          source_candidate_sha256=e3_audit['source_candidate_sha256'],
                          source_faces_sha256=e3_audit['source_faces_sha256'],
                          stage_audit_sha256=sha256_file(e3_dir / 'stage-audit.json'))
    else:
        source_floor = _source(inputs)
    engine_floor = source_floor.in_frame(FRAME)
    outcome, indices = run_checked_e5(engine_floor.mesh, looks(), FLATNESS)
    candidate = tmp_path / 'run' / 'e5' / '7F'
    save_survivor_pair(engine_floor, source_floor, indices, candidate)
    write_records(candidate / 'edit-log.jsonl', outcome.records)
    audit = dict(_common_audit(inputs, candidate), cleanup_mode='e3_then_e5_cull' if chained else 'e5_cull_only',
                 executed_stages=['E3', 'E5'] if chained else ['E5'], e3_candidate=e3_binding,
                 source_faces_sha256=sha256_file(candidate / 'source-faces.json'),
                 edit_log_sha256=sha256_file(candidate / 'edit-log.jsonl'), checks=outcome.checks)
    (candidate / 'stage-audit.json').write_text(json.dumps(audit))
    inputs['candidate'] = candidate
    return inputs


def _rehash(candidate, **extra):
    audit_path = candidate / 'stage-audit.json'
    audit = json.loads(audit_path.read_text())
    audit.update(source_faces_sha256=sha256_file(candidate / 'source-faces.json'),
                 edit_log_sha256=sha256_file(candidate / 'edit-log.jsonl'), **extra)
    audit_path.write_text(json.dumps(audit))
    return audit


# ------------------------------------------------------------------------------------------------- run

def test_checked_e5_drops_the_identical_twin_slivers_and_keeps_the_panel_and_the_facade():
    from tools.main_infra_e5 import run_checked_e5
    before = floor().in_frame(FRAME).mesh
    outcome, indices = run_checked_e5(before, looks(), FLATNESS)
    (check,) = outcome.checks
    assert check['stage'] == 'E5' and check['engine'] == 'E5' and check['legacy'] is False and check['final'] == 'PASS'
    # the twin's A-B-C triangle meets its fan only at T-junctions, so the drops form two edge-connected sites
    assert [sorted(e.faces) for e in outcome.kept] == [[4], [5, 6, 7]] and outcome.rolled_back == []
    np.testing.assert_array_equal(indices, PANEL + [FACADE])
    assert outcome.mesh.n_faces == 5
    np.testing.assert_array_equal(outcome.mesh.positions, before.positions)
    np.testing.assert_array_equal(outcome.mesh.face_v, before.face_v[PANEL + [FACADE]])
    rows = [row for e in outcome.kept for row in e.evidence['pairs']]
    assert [r['rule'] for r in rows] == ['same_look'] * 4 and all(r['overlap_fraction'] == 1.0 for r in rows)


def test_the_survivor_proof_refuses_an_e3_labelled_or_unconfirmed_e5_outcome():
    from dataclasses import replace
    from engine.fixes.remove import remove_faces
    from engine.repair.kernel import KernelResult
    from engine.repair.types import Edit
    from tools.main_infra_e3 import source_survivors
    before = floor().in_frame(FRAME).mesh

    def outcome(edit, final='PASS', engine='E5'):
        drop = np.zeros(before.n_faces, bool)
        drop[list(edit.faces)] = True
        after, _ = remove_faces(before, drop)
        return KernelResult(mesh=after, result=None, edits=[edit], stages=[], report=None, kept=[edit], rolled_back=[],
                            checks=[dict(stage=engine, engine=engine, legacy=False, rollback=True, final=final)],
                            records=[])

    e5 = Edit('E5', 'remove', tuple(TWIN), None, None, 0, 'twin', {})
    np.testing.assert_array_equal(source_survivors(before, outcome(e5), engine='E5'), PANEL + [FACADE])
    with pytest.raises(ValueError, match='E5'):
        source_survivors(before, outcome(replace(e5, engine='E3'), engine='E3'), engine='E5')
    with pytest.raises(ValueError, match='E3'):
        source_survivors(before, outcome(e5))
    with pytest.raises(ValueError, match='unconfirmed'):
        source_survivors(before, outcome(e5, final='FAIL'), engine='E5')


def test_save_survivor_pair_round_trips_the_e5_survivors_in_both_frames_and_refuses_existing_output(tmp_path):
    from tools.main_infra_e3 import save_survivor_pair, verify_survivor_mesh
    from tools.main_infra_e5 import run_checked_e5
    source = floor()
    engine = source.in_frame(FRAME)
    _outcome, indices = run_checked_e5(engine.mesh, looks(), FLATNESS)
    out = tmp_path / 'e5' / '7F'
    eng_path, src_path, map_path = save_survivor_pair(engine, source, indices, out)
    verify_survivor_mesh(engine.mesh, read_obj(eng_path), indices)
    verify_survivor_mesh(source.mesh, read_obj(src_path), indices)
    mapping = json.loads(map_path.read_text())
    assert mapping['mode'] == 'original_source_survivors' and mapping['source_faces'] == PANEL + [FACADE]
    assert mapping['input_triangles'] == 9 and mapping['output_triangles'] == 5
    text = src_path.read_text()
    assert 'g glass_panel' in text and 'g glass_twin' not in text and 'g facade_bit' in text
    with pytest.raises(ValueError, match='exists'):
        save_survivor_pair(engine, source, indices, out)


# --------------------------------------------------------------------------------------------- binding

def test_an_e5_cull_only_candidate_binds_to_the_baseline(tmp_path):
    from tools.main_infra_physical_validation import load_physical_pair
    inputs = e5_fixture(tmp_path)
    before, after, receipt = load_physical_pair(**inputs)
    assert before.n_faces == 9 and after.n_faces == 5
    np.testing.assert_array_equal(after.positions, before.positions)
    np.testing.assert_array_equal(after.face_v, before.face_v[PANEL + [FACADE]])
    assert after.physical_quanta == before.physical_quanta
    assert receipt['candidate_contract'] == 'e5_cull_only'
    assert receipt['source_faces_sha256'] == sha256_file(inputs['candidate'] / 'source-faces.json')
    assert receipt['e5_removed_triangles'] == 4 and receipt['e3_removed_triangles'] == 0
    assert receipt['baseline_kept_source_faces'] == PANEL + [FACADE] and receipt['e3_contract'] is None


def test_an_e3_then_e5_candidate_binds_through_the_e3_candidate_to_the_baseline(tmp_path):
    from tools.main_infra_physical_validation import load_physical_pair
    inputs = e5_fixture(tmp_path, chained=True)
    before, after, receipt = load_physical_pair(**inputs)
    assert before.n_faces == 9 and after.n_faces == 4, 'E3 removed the facade, E5 the twin slivers'
    np.testing.assert_array_equal(after.face_v, before.face_v[PANEL])
    assert receipt['candidate_contract'] == 'e3_then_e5_cull'
    assert receipt['e3_removed_triangles'] == 1 and receipt['e5_removed_triangles'] == 4
    assert receipt['baseline_kept_source_faces'] == PANEL
    assert receipt['e3_contract']['candidate_contract'] == 'e3_remove_only'


@pytest.mark.parametrize('file', ['source-faces.json', 'edit-log.jsonl'])
def test_a_changed_e5_map_or_log_hash_is_refused(tmp_path, file):
    from tools.main_infra_physical_validation import load_physical_pair
    inputs = e5_fixture(tmp_path)
    path = inputs['candidate'] / file
    path.write_bytes(path.read_bytes() + b'\n')
    with pytest.raises(ValueError, match='hash'):
        load_physical_pair(**inputs)


@pytest.mark.parametrize('change', ['engine', 'kind', 'legacy', 'final', 'stages', 'mode'])
def test_a_rehashed_e5_log_or_audit_cannot_hide_another_contract(tmp_path, change):
    from tools.main_infra_physical_validation import load_physical_pair
    inputs = e5_fixture(tmp_path)
    candidate = inputs['candidate']
    log = candidate / 'edit-log.jsonl'
    records = [json.loads(line) for line in log.read_text().splitlines()]
    extra = {}
    if change == 'engine': records[0]['engine'] = 'E3'
    elif change == 'kind': records[0]['kind'] = 'cut'
    elif change == 'legacy': records[0]['legacy'] = True
    elif change == 'final': records[-1]['check']['final'] = 'FAIL'
    elif change == 'stages': extra = dict(executed_stages=['E3'])
    elif change == 'mode': extra = dict(cleanup_mode='e3_remove_only')
    log.write_text(''.join(json.dumps(row) + '\n' for row in records))
    _rehash(candidate, checks=[records[-1]['check']], **extra)
    with pytest.raises(ValueError, match='E5|E3|contract|check'):
        load_physical_pair(**inputs)


def test_the_guard_itself_may_bind_a_pending_e5_candidate_but_the_validator_path_may_not(tmp_path):
    from tools.main_infra_e5_binding import bind_saved_e5
    inputs = e5_fixture(tmp_path)
    audit = _rehash(inputs['candidate'], guard={'passed': False, 'state': 'pending'})
    args = dict(candidate=inputs['candidate'], audit=audit, before_engine=_source(inputs).in_frame(FRAME).mesh,
                after_engine=read_obj(inputs['candidate'] / 'candidate.engine.obj'),
                before_source=_source(inputs).mesh, after_source=read_obj(inputs['candidate'] / 'candidate.source.obj'))
    contract = bind_saved_e5(**args, require_guard=False)
    assert contract['candidate_contract'] == 'e5_cull_only' and contract['e5_removed_triangles'] == 4
    with pytest.raises(ValueError, match='guard'):
        bind_saved_e5(**args)


# ------------------------------------------------------------------------------------------ the runners

def test_the_e5_floor_runner_refuses_an_existing_output_before_reading_anything(tmp_path):
    from tools.run_checked_e5_floor import main
    (tmp_path / 'e5' / '7F').mkdir(parents=True)
    with pytest.raises(ValueError, match='existing'):
        main(['--root', str(tmp_path), '--floor', '7F', '--raw-name', 'source.obj'])


def test_the_e4_runner_from_e5_needs_an_e3_then_e5_candidate(tmp_path):
    from tools.run_checked_e4_floor import main
    inputs = e5_fixture(tmp_path)                       # e5_cull_only, not chained through E3
    with pytest.raises(ValueError, match='e3_then_e5_cull'):
        main(['--root', str(tmp_path / 'run'), '--floor', '7F', '--raw-name', 'source.obj', '--from-e5'])
    assert not (tmp_path / 'run' / 'e4' / '7F').exists()


def test_the_chain_e3_then_e5_then_e4_runs_on_the_fixture_root_and_binds_to_the_baseline(tmp_path):
    from tools.main_infra_physical_validation import load_physical_pair
    from tools.run_checked_e4_floor import main as e4_main
    from tools.run_checked_e5_floor import main as e5_main
    root = tmp_path / 'run'
    inputs = run_root(root)
    e3_fixture(inputs, root / 'e3' / '7F')
    common = ['--root', str(root), '--floor', '7F', '--raw-name', 'source.obj']

    assert e5_main(common + ['--from-e3']) == 0
    e5_dir = root / 'e5' / '7F'
    e5_audit = json.loads((e5_dir / 'stage-audit.json').read_text())
    assert e5_audit['cleanup_mode'] == 'e3_then_e5_cull' and e5_audit['executed_stages'] == ['E3', 'E5']
    assert e5_audit['input_triangles'] == 8 and e5_audit['output_triangles'] == 4
    assert e5_audit['guard'] == {'passed': False, 'state': 'pending'} and e5_audit['e3_candidate']['candidate'] == str(root / 'e3' / '7F')
    assert json.loads((e5_dir / 'source-faces.json').read_text())['source_faces'] == PANEL
    assert e5_audit['engine_report']['dropped'] == 4 and e5_audit['engine_report']['by_rule']['same_look'] == 4
    assert (e5_dir / 'edit-log.jsonl').exists() and (e5_dir / 'source.mtl').exists()

    assert e4_main(common + ['--from-e5']) == 0
    e4_dir = root / 'e4' / '7F'
    e4_audit = json.loads((e4_dir / 'stage-audit.json').read_text())
    assert e4_audit['cleanup_mode'] == 'e3_then_e5_then_e4_merge' and e4_audit['executed_stages'] == ['E3', 'E5', 'E4']
    assert e4_audit['input_triangles'] == 4 and e4_audit['output_triangles'] == 2
    assert e4_audit['e5_candidate']['candidate'] == str(e5_dir)
    assert e4_audit['e3_candidate'] == e5_audit['e3_candidate']

    # the Validator path: the chained candidate binds to the qualified baseline once the guard is recorded
    e4_audit['guard'] = {'passed': True}
    (e4_dir / 'stage-audit.json').write_text(json.dumps(e4_audit, indent=2))
    before, after, receipt = load_physical_pair(**dict(inputs, candidate=e4_dir))
    assert before.n_faces == 9 and after.n_faces == 2
    np.testing.assert_array_equal(after.positions, before.positions)
    assert receipt['candidate_contract'] == 'e3_then_e5_then_e4_merge'
    assert receipt['e3_removed_triangles'] == 1 and receipt['e5_removed_triangles'] == 4
    assert receipt['e4_replaced_triangles'] == 4 and receipt['e4_new_triangles'] == 2
    assert receipt['baseline_kept_source_faces'] == [] and receipt['e4_region_source_faces'] == [PANEL]
    assert receipt['e5_contract']['candidate_contract'] == 'e3_then_e5_cull'
    assert receipt['e3_contract']['candidate_contract'] == 'e3_remove_only'
    # a changed E5 proof breaks the chain
    (e5_dir / 'source-faces.json').write_bytes((e5_dir / 'source-faces.json').read_bytes() + b'\n')
    with pytest.raises(ValueError, match='hash'):
        load_physical_pair(**dict(inputs, candidate=e4_dir))
