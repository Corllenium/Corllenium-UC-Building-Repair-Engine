"""`load_physical_pair` accepts the E4 cleanup modes through `bind_saved_e4`: the candidate is the qualified baseline
minus E3-removed faces (chained mode), with E4 regions replaced exactly as `region-map.json` says."""
import json
from pathlib import Path
from shutil import copyfile

import numpy as np
import pytest

from engine.io.minecraft_floor import Frame, parse_floor
from engine.io.obj_reader import read_obj
from engine.io.snapshot import sha256_file, snapshot_object
from engine.repair.kernel import write_records
from engine.tests.test_validate_checks import _looks

FRAME = Frame(1000 / 25.4, 'owner: 1 block = 1 metre; Y-up')
FLATNESS = {'glass': 50.0}
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
o far
g facade_bit
usemtl facade
f 7/1/1 8/2/1 9/4/1
'''


def run_root(tmp_path):
    """A qualified fresh-floor run root (raw, reference, baseline, qualification) around RAW, like the physical
    validation fixture, plus a duplicate-only candidate so `load_physical_pair` has its usual inputs."""
    from tools.repair_fresh_main_infra import normalize_reference
    raw = tmp_path / 'source.obj'
    raw.write_text(RAW, encoding='utf-8')
    (tmp_path / 'source.mtl').write_text('newmtl glass\nKd 1 1 1\nmap_Kd glass.png\nnewmtl facade\nKd 0.5 0.5 0.5\n')
    from PIL import Image
    Image.new('RGB', (2, 2), (20, 80, 30)).save(tmp_path / 'glass.png')
    polygons = {str(i): [[0, 1, 2]] for i, line in enumerate(RAW.splitlines(), 1) if line.startswith('f ')}
    reference = tmp_path / 'reference.json'
    reference.write_text(json.dumps(dict(schema_version=1, source_sha256=sha256_file(raw), unmatched_polygons=0,
                                         blender_version='fixture', raw_polygon_count=5, imported_polygon_count=5,
                                         triangle_count=5, polygons=polygons)))
    base = tmp_path / 'baseline'
    normalize_reference(raw, reference, base, FRAME)
    qualification = tmp_path / 'qualification.json'
    qualification.write_text(json.dumps(dict(qualified=True, floor_id='7F', source_revision='a' * 64,
                                             source_obj_sha256=sha256_file(raw),
                                             native_reference_sha256=sha256_file(reference),
                                             engine_obj_sha256=sha256_file(base / 'before.engine.obj'),
                                             source_triangles_sha256=sha256_file(base / 'before.source.obj'))))
    candidate = tmp_path / 'candidate'
    candidate.mkdir()
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


def e3_fixture(inputs, tmp_path):
    """An E3 candidate that removed the facade triangle (face 4), with its log and audit."""
    from tools.main_infra_e3 import save_survivor_pair
    source = _source(inputs)
    candidate = tmp_path / 'e3-candidate'
    save_survivor_pair(source.in_frame(FRAME), source, [0, 1, 2, 3], candidate)
    records = [dict(stage='E3', engine='E3', kind='remove', site=0, faces=[4], n_removed=1, removed=['fixture-key'],
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


def e4_fixture(tmp_path, *, chained=False):
    """The run root plus an E4 candidate: over the baseline (`e4_merge_only`) or over an E3 candidate that removed
    the facade (`e3_then_e4_merge`). `inputs['candidate']` points at the E4 candidate."""
    from tools.main_infra_e4 import floor_from_candidate, run_checked_e4, save_merged_pair
    inputs = run_root(tmp_path)
    e3_binding = None
    if chained:
        e3_dir = e3_fixture(inputs, tmp_path)
        e3_audit = json.loads((e3_dir / 'stage-audit.json').read_text())
        source_floor = floor_from_candidate(e3_dir / 'candidate.source.obj')
        e3_binding = dict(candidate=str(e3_dir), engine_candidate_sha256=e3_audit['engine_candidate_sha256'],
                          source_candidate_sha256=e3_audit['source_candidate_sha256'],
                          source_faces_sha256=e3_audit['source_faces_sha256'],
                          stage_audit_sha256=sha256_file(e3_dir / 'stage-audit.json'))
    else:
        source_floor = _source(inputs)
    engine_floor = source_floor.in_frame(FRAME)
    outcome, mapping = run_checked_e4(engine_floor.mesh, _looks('glass', 'facade'), FLATNESS)
    candidate = tmp_path / 'e4-candidate'
    save_merged_pair(engine_floor, source_floor, mapping, candidate)
    write_records(candidate / 'edit-log.jsonl', outcome.records)
    audit = dict(_common_audit(inputs, candidate),
                 cleanup_mode='e3_then_e4_merge' if chained else 'e4_merge_only',
                 executed_stages=['E3', 'E4'] if chained else ['E4'], e3_candidate=e3_binding,
                 region_map_sha256=sha256_file(candidate / 'region-map.json'),
                 edit_log_sha256=sha256_file(candidate / 'edit-log.jsonl'), checks=outcome.checks)
    (candidate / 'stage-audit.json').write_text(json.dumps(audit))
    inputs['candidate'] = candidate
    return inputs


def _rehash(candidate, **extra):
    audit_path = candidate / 'stage-audit.json'
    audit = json.loads(audit_path.read_text())
    audit.update(region_map_sha256=sha256_file(candidate / 'region-map.json'),
                 edit_log_sha256=sha256_file(candidate / 'edit-log.jsonl'), **extra)
    audit_path.write_text(json.dumps(audit))
    return audit


def test_e4_merge_only_candidate_binds_to_the_baseline(tmp_path):
    from tools.main_infra_physical_validation import load_physical_pair
    inputs = e4_fixture(tmp_path)
    before, after, receipt = load_physical_pair(**inputs)
    assert before.n_faces == 5 and after.n_faces == 3
    np.testing.assert_array_equal(after.face_v[0], before.face_v[4])
    np.testing.assert_array_equal(after.positions, before.positions)
    assert after.physical_quanta == before.physical_quanta
    assert receipt['candidate_contract'] == 'e4_merge_only'
    assert receipt['region_map_sha256'] == sha256_file(inputs['candidate'] / 'region-map.json')
    assert receipt['e4_merged_regions'] == 1 and receipt['e4_replaced_triangles'] == 4
    assert receipt['e4_new_triangles'] == 2 and receipt['e3_removed_triangles'] == 0
    assert receipt['baseline_kept_source_faces'] == [4]


def test_e3_then_e4_candidate_binds_through_the_e3_candidate_to_the_baseline(tmp_path):
    from tools.main_infra_physical_validation import load_physical_pair
    inputs = e4_fixture(tmp_path, chained=True)
    before, after, receipt = load_physical_pair(**inputs)
    assert before.n_faces == 5 and after.n_faces == 2, 'E3 removed the facade, E4 merged the panel'
    np.testing.assert_array_equal(after.positions, before.positions)
    assert receipt['candidate_contract'] == 'e3_then_e4_merge'
    assert receipt['e3_removed_triangles'] == 1 and receipt['e4_replaced_triangles'] == 4
    assert receipt['baseline_kept_source_faces'] == [] and receipt['e4_region_source_faces'] == [[0, 1, 2, 3]]
    assert receipt['e3_contract']['candidate_contract'] == 'e3_remove_only'


@pytest.mark.parametrize('file', ['region-map.json', 'edit-log.jsonl'])
def test_changed_region_map_or_log_hash_is_refused(tmp_path, file):
    from tools.main_infra_physical_validation import load_physical_pair
    inputs = e4_fixture(tmp_path)
    path = inputs['candidate'] / file
    path.write_bytes(path.read_bytes() + b'\n')
    with pytest.raises(ValueError, match='hash'):
        load_physical_pair(**inputs)


def test_a_chained_candidate_whose_e3_proof_changed_is_refused(tmp_path):
    from tools.main_infra_physical_validation import load_physical_pair
    inputs = e4_fixture(tmp_path, chained=True)
    audit = json.loads((inputs['candidate'] / 'stage-audit.json').read_text())
    e3_dir = Path(audit['e3_candidate']['candidate'])
    (e3_dir / 'source-faces.json').write_bytes((e3_dir / 'source-faces.json').read_bytes() + b'\n')
    with pytest.raises(ValueError, match='hash'):
        load_physical_pair(**inputs)


def test_a_chained_audit_without_its_e3_binding_is_refused(tmp_path):
    from tools.main_infra_physical_validation import load_physical_pair
    inputs = e4_fixture(tmp_path, chained=True)
    _rehash(inputs['candidate'], e3_candidate=None)
    with pytest.raises(ValueError, match='E3'):
        load_physical_pair(**inputs)


def test_a_candidate_without_a_passed_guard_is_refused(tmp_path):
    from tools.main_infra_physical_validation import load_physical_pair
    inputs = e4_fixture(tmp_path)
    _rehash(inputs['candidate'], guard={'passed': False, 'state': 'pending'})
    with pytest.raises(ValueError, match='guard'):
        load_physical_pair(**inputs)


@pytest.mark.parametrize('change', ['kind', 'engine', 'legacy', 'new_point', 'rolled_back', 'final', 'unchecked'])
def test_a_rehashed_log_cannot_hide_an_unsupported_or_unconfirmed_edit(tmp_path, change):
    from tools.main_infra_physical_validation import load_physical_pair
    inputs = e4_fixture(tmp_path)
    candidate = inputs['candidate']
    log = candidate / 'edit-log.jsonl'
    records = [json.loads(line) for line in log.read_text().splitlines()]
    if change == 'kind': records[0]['kind'] = 'add'
    elif change == 'engine': records[0]['engine'] = 'E7'
    elif change == 'legacy': records[0]['legacy'] = True
    elif change == 'new_point': records[0]['n_new_points'] = 1
    elif change == 'rolled_back': records[0]['rolled_back'] = True
    elif change == 'final': records[-1]['check']['final'] = 'FAIL'
    elif change == 'unchecked': records[-1]['check']['rollback'] = False
    log.write_text(''.join(json.dumps(row) + '\n' for row in records))
    _rehash(candidate, checks=[records[-1]['check']])
    with pytest.raises(ValueError, match='E4|region|check'):
        load_physical_pair(**inputs)


@pytest.mark.parametrize('change', ['outside_vertex', 'kept_face', 'extra_region_face', 'dropped_triangle'])
def test_a_rehashed_region_map_cannot_change_the_merge_contract(tmp_path, change):
    from tools.main_infra_physical_validation import load_physical_pair
    inputs = e4_fixture(tmp_path)
    candidate = inputs['candidate']
    path = candidate / 'region-map.json'
    mapping = json.loads(path.read_text())
    if change == 'outside_vertex': mapping['regions'][0]['face_v'][0][0] = 6
    elif change == 'kept_face': mapping['kept_source_faces'] = [3]
    elif change == 'extra_region_face': mapping['regions'][0]['source_faces'] = [0, 1, 2, 3, 4]
    elif change == 'dropped_triangle':
        for key in ('new_triangles', 'face_v', 'face_vt', 'face_vn'):
            mapping['regions'][0][key] = mapping['regions'][0][key][:1]
        mapping['output_triangles'] = 2
    path.write_text(json.dumps(mapping))
    _rehash(candidate)
    with pytest.raises(ValueError):
        load_physical_pair(**inputs)


def test_the_binding_refuses_a_log_whose_kept_sites_differ_from_the_region_map(tmp_path):
    from tools.main_infra_physical_validation import load_physical_pair
    inputs = e4_fixture(tmp_path)
    candidate = inputs['candidate']
    log = candidate / 'edit-log.jsonl'
    records = [json.loads(line) for line in log.read_text().splitlines()]
    records[0]['faces'] = [0, 1, 2]
    records[0]['removed'] = records[0]['removed'][:3]
    records[0]['n_removed'] = 3
    log.write_text(''.join(json.dumps(row) + '\n' for row in records))
    _rehash(candidate)
    with pytest.raises(ValueError, match='region map|E4'):
        load_physical_pair(**inputs)
