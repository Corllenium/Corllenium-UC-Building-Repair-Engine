"""The per-face stage classifications for the fresh MAIN INFRA dashboard (`tools/main_infra_stage_errors.py`): the
E5 rules (`backface_twin`, `interior_seam`, `two_sided_sheet`, `e5_rolled_back`), the E4 merge (`merge_region`,
`merge_refused`, `e4_rolled_back`) and the crack judgement (`jev_merge`, `jev_keep`, `jev_unsure`), read from the saved
run directories only, in the BEFORE model's ids and mapped into the AFTER model's ids."""
import json

import numpy as np
import pytest

from engine.io.obj_reader import read_obj
from tools.tests.test_main_infra_e5 import FRAME, PANEL, e3_fixture, run_root

# ---------------------------------------------------------------------------------------- a synthetic run tree
#
# E5 input (10 faces, ids 0-9) -> E5 output (6) -> E4 input (= E5 output) -> E4 output (5).
#
# E5 edit log: site 0 drops face 2 (backface_twin); site 1 is a mixed site dropping 4 (backface_twin) and the
# coincident opposite pair 5+6 (interior_twins); site 2 (face 7) is rolled back. kept_pairs: (0,1) both_exposed,
# (3,8) no_backface_winner. Survivors: [0, 1, 3, 7, 8, 9].
#
# E4 on the survivors: site 0 merges E4-input faces [2, 3] (= before 3, 7) into one new triangle (after id 4); site 1
# (E4-input face 1) is rolled back; region 7 (E4-input face 5 = before 9) is refused (area_changed).
# kept_source_faces = [0, 1, 4, 5].

E5_INPUT = '''v 0 0 0
v 1 0 0
v 1 0 1
v 0 0 1
v 2 0 0
v 3 0 0
v 3 0 1
v 5 0 0
v 6 0 0
v 6 0 1
v 5 0 1
v 8 0 0
v 9 0 0
v 9 0 1
v 11 0 0
v 12 0 0
v 12 0 1
v 14 0 0
v 15 0 0
v 15 0 1
f 1 2 3
f 1 3 4
f 5 6 7
f 8 9 10
f 8 10 11
f 12 13 14
f 12 14 13
f 15 16 17
f 18 19 20
f 1 2 4
'''
SURVIVORS = [0, 1, 3, 7, 8, 9]


def _write_tris(path, n):
    """An OBJ of `n` disjoint triangles (face ids 0..n-1)."""
    verts, faces = [], []
    for i in range(n):
        verts += [f'v {3 * i} 0 0', f'v {3 * i + 1} 0 0', f'v {3 * i + 1} 0 1']
        faces.append(f'f {3 * i + 1} {3 * i + 2} {3 * i + 3}')
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text('\n'.join(verts + faces) + '\n', encoding='utf-8')
    return path


def _jsonl(path, rows):
    path.write_text(''.join(json.dumps(r) + '\n' for r in rows), encoding='utf-8')


def _e5_line(site, faces, by_rule, rolled_back=False):
    line = dict(stage='E5', engine='E5', kind='remove', site=site, faces=faces, removed=[], added=[], n_removed=len(faces),
                n_added=0, n_new_points=0, material=0,
                reason=f'E5 coincident layer: {len(faces)} face(s) of connected group {site} lying on the same plane as, '
                       f'facing the same way as, and covered at least 98% by larger or higher-priority faces that '
                       f'stay ({by_rule}); the Validator\'s own double-layer pairs at depth tolerance 0.0100 in')
    if rolled_back:
        line['rolled_back'] = True
    return line


def synthetic_tree(tmp_path, *, e4_refused_region_faces=(5,), e4_new_triangles=(4,)):
    root = tmp_path / 'run'
    e3_dir, e5_dir, e4_dir = root / 'e3' / '7F', root / 'e5' / '7F', root / 'e4' / '7F'
    for d in (e3_dir, e5_dir, e4_dir):
        d.mkdir(parents=True)
    (e3_dir / 'candidate.engine.obj').write_text(E5_INPUT, encoding='utf-8')
    _write_tris(e5_dir / 'candidate.engine.obj', len(SURVIVORS))
    _write_tris(e4_dir / 'candidate.engine.obj', 5)

    (e5_dir / 'source-faces.json').write_text(json.dumps(dict(
        schema_version=1, mode='original_source_survivors', input_triangles=10, output_triangles=6,
        source_faces=SURVIVORS)))
    e5_check = dict(stage='E5', engine='E5', legacy=False, rollback=True, final='PASS',
                    rolled_back=[dict(site=2, round=1, charged=3, how={'touched': 3}, reasons={'uv': 3},
                                      faces=[7], edits=1, rounds_exhausted=False)])
    _jsonl(e5_dir / 'edit-log.jsonl', [
        _e5_line(0, [2], {'backface_twin': 1}),
        _e5_line(1, [4, 5, 6], {'backface_twin': 1, 'interior_twins': 2}),
        _e5_line(2, [7], {'same_look': 1}, rolled_back=True),
        {'check': e5_check}])
    (e5_dir / 'stage-audit.json').write_text(json.dumps(dict(
        cleanup_mode='e3_then_e5_cull', executed_stages=['E3', 'E5'], input_triangles=10, output_triangles=6,
        kept_edits=2, rolled_back_edits=1, checks=[e5_check], e3_candidate=dict(candidate=str(e3_dir)),
        engine_report=dict(dropped=4, by_rule={'backface_twin': 2, 'interior_twins': 2, 'same_look': 1},
                           kept_pairs=[dict(faces=[0, 1], looks=['a', 'a'], front=[1, 1], back=[0, 0], reason='both_exposed'),
                                       dict(faces=[3, 8], looks=['a', 'a'], front=[0, 0], back=[0, 0], reason='no_backface_winner')],
                           kept_pairs_total=2, planned=[[2], [4, 5, 6], [7]], sites=3))))

    e4_check = dict(stage='E4', engine='E4', legacy=False, rollback=True, final='PASS',
                    rolled_back=[dict(site=1, round=1, charged=2, how={'touched': 2}, reasons={'cover': 2},
                                      faces=[1], edits=1, rounds_exhausted=False)])
    _jsonl(e4_dir / 'edit-log.jsonl', [
        dict(stage='E4', engine='E4', kind='cut', site=0, faces=[2, 3], reason='E4 coplanar merge: region 3', removed=[],
             added=[], n_removed=2, n_added=1, n_new_points=0, material=0),
        dict(stage='E4', engine='E4', kind='cut', site=1, faces=[1], reason='E4 coplanar merge: region 5', removed=[],
             added=[], n_removed=1, n_added=1, n_new_points=0, material=0, rolled_back=True),
        {'check': e4_check}])
    refused = [dict(region=7, material=0, look='look-a', faces_before=1, faces_after=1, area_before=0.5, area_after=0.6,
                    ring_vertices=3, plane_offset=0.0, uv_residual=None, centroid=[0, 0, 0], bbox=[[0, 0, 0], [1, 0, 1]],
                    reason='area_changed', detail='the merge changed the area')]
    (e4_dir / 'region-map.json').write_text(json.dumps(dict(
        schema_version=1, mode='e4_merge', input_triangles=6, output_triangles=5, kept_source_faces=[0, 1, 4, 5],
        appended_uvs=[], appended_normals=[],
        regions=[dict(site=0, region=3, material='a', source_faces=[2, 3], new_triangles=list(e4_new_triangles),
                      face_v=[[0, 1, 2]], face_vt=[[-1, -1, -1]], face_vn=[[-1, -1, -1]], area_before=1.0, area_after=1.0,
                      ring_vertices=4)],
        engine_report=dict(regions=4, changed=3, sites=2, skipped={}, refused=refused, allowed_regions=None,
                           max_site_faces=400, allow_growth=True, flat_materials=[0]))))
    (e4_dir / 'stage-audit.json').write_text(json.dumps(dict(
        cleanup_mode='e3_then_e5_then_e4_merge', executed_stages=['E3', 'E5', 'E4'], input_triangles=6,
        output_triangles=5, kept_edits=1, rolled_back_edits=1, checks=[e4_check],
        e3_candidate=dict(candidate=str(e3_dir)), e5_candidate=dict(candidate=str(e5_dir)), allow_growth=True,
        engine_report=dict(regions=4, changed=3, sites=2, skipped={}, refused=refused, allowed_regions=None,
                           max_site_faces=400, allow_growth=True, flat_materials=[0]))))

    judgement = tmp_path / 'crack-judgement.json'
    judgement.write_text(json.dumps(dict(
        qtype='crack.region',
        regions=[dict(region=3, material='a', crack_faces=[2], region_faces=2, decision='merge', provider='rules',
                      confidence=1.0, suggestion=None,
                      state=dict(region=3, merge_reason=None, area_preserved=True, stair_material=False,
                                 stair_open_edges=0, spot=dict(faces=[2, 3]))),
                 dict(region=7, material='a', crack_faces=[5], region_faces=1, decision='unsure', provider='queue',
                      confidence=0.0, suggestion=dict(provider='jev', answer='keep', confidence=0.9),
                      state=dict(region=7, merge_reason='area_changed', area_preserved=False, stair_material=False,
                                 stair_open_edges=0, spot=dict(faces=[5]))),
                 dict(region=9, material='stair_a', crack_faces=[0], region_faces=1, decision='keep', provider='rules',
                      confidence=1.0, suggestion=None,
                      state=dict(region=9, merge_reason=None, area_preserved=True, stair_material=True,
                                 stair_open_edges=2, spot=dict(faces=[0])))],
        merge=[3], keep=[9], unsure=[7], unassigned_faces=[], decider=dict(providers=['rules'], jev='off'))))
    # the refused region's faces come from the E4 input's coplanar regions; the synthetic tree fixes them instead
    region_faces = {7: list(e4_refused_region_faces)}
    return dict(root=root, e3=e3_dir, e5=e5_dir, e4=e4_dir, judgement=judgement, region_faces=region_faces)


@pytest.fixture
def tree(tmp_path, monkeypatch):
    import tools.main_infra_stage_errors as mod
    t = synthetic_tree(tmp_path)
    monkeypatch.setattr(mod, 'region_faces', lambda mesh, flat_materials: t['region_faces'])
    return t


def _run(tree, tmp_path, *extra, e5=True, e4=True, judgement=True):
    from tools.main_infra_stage_errors import main
    before, after = tmp_path / 'out' / 'errors_before.json', tmp_path / 'out' / 'errors_after.json'
    argv = ['--before-out', str(before), '--after-out', str(after), *extra]
    if e5:
        argv += ['--e5', str(tree['e5'])]
    if e4:
        argv += ['--e4', str(tree['e4'])]
    if judgement:
        argv += ['--judgement', str(tree['judgement'])]
    assert main(argv) == 0
    return json.loads(before.read_text()), json.loads(after.read_text())


# ---------------------------------------------------------------------------------------------- the id sets

def test_the_before_sets_classify_e5_rules_e4_regions_and_the_judgement_in_the_e5_inputs_ids(tree, tmp_path):
    before, after = _run(tree, tmp_path)
    assert before['schema_version'] == 1 and before['n_faces'] == 10
    assert before['faces']['backface_twin'] == [2, 4]
    assert before['faces']['interior_seam'] == [5, 6]
    assert before['faces']['two_sided_sheet'] == [0, 1]
    assert before['faces']['e5_rolled_back'] == [7]
    assert before['details']['e5_rolled_back']['7'] == {'site': 2, 'reasons': {'uv': 3}, 'stage_rolled_back': False}
    # E4 ids (E5-output space) are carried back through the E5 survivors: 2 -> 3, 3 -> 7, 5 -> 9, 1 -> 1
    assert before['faces']['merge_region'] == [3, 7]
    assert before['faces']['merge_refused'] == [9]
    assert before['details']['merge_refused'] == {'9': 'area_changed'}
    assert before['faces']['e4_rolled_back'] == [1]
    assert before['details']['e4_rolled_back']['1']['reasons'] == {'cover': 2}
    assert before['faces']['jev_merge'] == [3, 7] and before['faces']['jev_unsure'] == [9] and before['faces']['jev_keep'] == [0]
    assert before['details']['jev']['9'] == {'provider': 'queue', 'reason': 'rules could not say (merge_reason=area_changed); jev suggests keep (0.9)'}
    assert before['details']['jev']['0']['provider'] == 'rules'
    assert before['counts'] == {k: len(v) for k, v in before['faces'].items()}
    assert set(before['faces']) == {'backface_twin', 'interior_seam', 'two_sided_sheet', 'e5_rolled_back', 'merge_region',
                                    'merge_refused', 'e4_rolled_back', 'jev_merge', 'jev_keep', 'jev_unsure'}


def test_the_after_sets_follow_the_survivors_the_kept_faces_and_the_new_triangles(tree, tmp_path):
    before, after = _run(tree, tmp_path)
    assert after['n_faces'] == 5
    # removed faces are gone on AFTER
    assert after['faces']['backface_twin'] == [] and after['faces']['interior_seam'] == []
    # E5 survivors 0, 1 are E4 kept faces 0, 1
    assert after['faces']['two_sided_sheet'] == [0, 1]
    # the rolled-back E5 face 7 survives E5 as 3, which E4 merges into new triangle 4
    assert after['faces']['e5_rolled_back'] == [4]
    assert after['faces']['merge_region'] == [4]
    # refused and rolled-back E4 faces are kept: E4-input 5 -> after 3, E4-input 1 -> after 1
    assert after['faces']['merge_refused'] == [3] and after['details']['merge_refused'] == {'3': 'area_changed'}
    assert after['faces']['e4_rolled_back'] == [1]
    assert after['faces']['jev_merge'] == [4] and after['faces']['jev_unsure'] == [3] and after['faces']['jev_keep'] == [0]
    assert after['counts']['merge_region'] == 1


def test_e5_alone_uses_the_e5_output_as_after_and_e4_alone_uses_its_input_as_before(tree, tmp_path):
    before, after = _run(tree, tmp_path, e4=False, judgement=False)
    assert before['n_faces'] == 10 and after['n_faces'] == 6
    assert after['faces']['two_sided_sheet'] == [0, 1] and after['faces']['e5_rolled_back'] == [3]
    assert 'merge_region' not in before['faces'] and 'jev_merge' not in before['faces']
    before, after = _run(tree, tmp_path, e5=False)
    assert before['n_faces'] == 6 and after['n_faces'] == 5
    assert before['faces']['merge_region'] == [2, 3] and before['faces']['merge_refused'] == [5]
    assert before['faces']['jev_unsure'] == [5] and after['faces']['jev_unsure'] == [3]
    assert 'backface_twin' not in before['faces']


def test_merge_into_keeps_the_existing_kinds_replaces_the_stage_kinds_and_refuses_a_face_count_mismatch(tree, tmp_path):
    existing = tmp_path / 'existing_before.json'
    existing.write_text(json.dumps(dict(schema_version=1, n_faces=10, engine_obj_sha256='x',
                                        counts={'cracks': 2, 'hidden': 0, 'merge_region': 1},
                                        faces={'cracks': [8, 9], 'hidden': [], 'merge_region': [99]})))
    before, _ = _run(tree, tmp_path, '--merge-into-before', str(existing))
    assert before['faces']['cracks'] == [8, 9] and before['faces']['hidden'] == [] and before['engine_obj_sha256'] == 'x'
    assert before['faces']['merge_region'] == [3, 7], 'the stage kind replaces the stale one'
    assert before['counts']['cracks'] == 2 and before['counts']['merge_region'] == 2 and before['n_faces'] == 10
    existing.write_text(json.dumps(dict(schema_version=1, n_faces=11, counts={}, faces={})))
    with pytest.raises(ValueError, match='n_faces'):
        _run(tree, tmp_path, '--merge-into-before', str(existing))


def test_ids_outside_the_named_objs_face_counts_are_refused(tmp_path, monkeypatch):
    import tools.main_infra_stage_errors as mod
    t = synthetic_tree(tmp_path, e4_new_triangles=(99,))
    monkeypatch.setattr(mod, 'region_faces', lambda mesh, flat_materials: t['region_faces'])
    with pytest.raises(ValueError, match='out of range'):
        _run(t, tmp_path)
    t = synthetic_tree(tmp_path / 'b', e4_refused_region_faces=(6,))
    monkeypatch.setattr(mod, 'region_faces', lambda mesh, flat_materials: t['region_faces'])
    with pytest.raises(ValueError, match='out of range'):
        _run(t, tmp_path / 'b')


def test_an_e4_dir_that_does_not_name_the_given_e5_dir_as_its_input_is_refused(tree, tmp_path):
    audit_path = tree['e4'] / 'stage-audit.json'
    audit = json.loads(audit_path.read_text())
    audit['e5_candidate'] = dict(candidate=str(tmp_path / 'elsewhere'))
    audit_path.write_text(json.dumps(audit))
    with pytest.raises(ValueError, match='e5_candidate'):
        _run(tree, tmp_path)


def test_interior_twins_in_a_mixed_site_are_the_coincident_opposite_pairs_and_an_unsplittable_site_is_reported(tmp_path):
    from tools.main_infra_stage_errors import classify_e5_removals
    mesh = read_obj(_write_obj(tmp_path, E5_INPUT))
    lines = [_e5_line(0, [2], {'backface_twin': 1}), _e5_line(1, [4, 5, 6], {'backface_twin': 1, 'interior_twins': 2}),
             _e5_line(2, [3, 8], {'backface_twin': 1, 'same_look': 1})]
    out = classify_e5_removals(mesh, lines)
    assert out['backface_twin'] == [2, 4] and out['interior_seam'] == [5, 6]
    assert out['unresolved'] == [dict(site=2, faces=[3, 8], by_rule={'backface_twin': 1, 'same_look': 1})]


def _write_obj(tmp_path, text):
    path = tmp_path / 'mesh.obj'
    path.write_text(text, encoding='utf-8')
    return path


# ------------------------------------------------------------------------------- the real E3 -> E5 -> E4 chain

def test_the_tool_reads_the_real_chain_fixture_and_the_census_rides_along(tmp_path):
    from tools.main_infra_stage_errors import BASE_KINDS, main
    from tools.run_checked_e4_floor import main as e4_main
    from tools.run_checked_e5_floor import main as e5_main
    root = tmp_path / 'run'
    inputs = run_root(root)
    e3_fixture(inputs, root / 'e3' / '7F')
    common = ['--root', str(root), '--floor', '7F', '--raw-name', 'source.obj']
    assert e5_main(common + ['--from-e3']) == 0
    assert e4_main(common + ['--from-e5', '--allow-growth']) == 0
    before_out, after_out = tmp_path / 'errors_before.json', tmp_path / 'errors_after.json'
    assert main(['--e5', str(root / 'e5' / '7F'), '--e4', str(root / 'e4' / '7F'), '--before-out', str(before_out),
                 '--after-out', str(after_out), '--with-census']) == 0
    before, after = json.loads(before_out.read_text()), json.loads(after_out.read_text())
    assert before['n_faces'] == 8 and after['n_faces'] == 2
    # the fixture's E5 drops the twin by same_look (neither backface_twin nor interior_twins), keeps nothing two-sided
    assert before['faces']['backface_twin'] == [] and before['faces']['interior_seam'] == []
    assert before['faces']['two_sided_sheet'] == [] and before['faces']['e5_rolled_back'] == []
    # E4 merged the panel: its E4-input faces [0..3] are the E5 input's PANEL faces, its new triangles [0, 1]
    assert before['faces']['merge_region'] == PANEL and after['faces']['merge_region'] == [0, 1]
    assert before['faces']['merge_refused'] == [] and before['faces']['e4_rolled_back'] == []
    assert all(k in before['faces'] and k in after['faces'] for k in BASE_KINDS)
    assert before['counts'] == {k: len(v) for k, v in before['faces'].items()}
    assert all(0 <= f < before['n_faces'] for v in before['faces'].values() for f in v)
    assert all(0 <= f < after['n_faces'] for v in after['faces'].values() for f in v)
    assert np.array_equal(sorted(json.loads((root / 'e5' / '7F' / 'source-faces.json').read_text())['source_faces']), PANEL)
