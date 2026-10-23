from dataclasses import replace
import json
from pathlib import Path

import numpy as np
import pytest

from engine.fixes.pipeline import FixProfile
from engine.io.minecraft_floor import Frame, parse_floor, write_floor
from engine.io.obj_reader import read_obj
from engine.io.snapshot import sha256_file
from engine.repair.engines.e7_thread import E7Thread
from engine.repair.kernel import repair_unit, write_records
from engine.repair.types import RepairContext, UnitState
from engine.site_judge import SiteJudge
from engine.validate.checks import Looks
from tools.main_infra_e3 import _source_digest
from tools.main_infra_e7 import run_checked_e7


def fixture(tmp_path, mixed=False):
    points = [[0, 0, 0], [.1016, 0, 0], [0, 0, -.1016], [.0508, 0, 0], [.0508, 0, .0508]]
    if mixed:
        points += [[x + 2.54, y, z] for x, y, z in points]
    text = ['o original-infra', 'g source-shell']
    text += ['v ' + ' '.join(str(value) for value in point) for point in points]
    text += ['vt .123456789012345 .234567890123456', 'vt 2.34567890123456 .234567890123456',
             'vt .123456789012345 2.45678901234567', 'vt 9.23456789012345 9.34567890123456',
             'vt 8.12345678901234 9.34567890123456', 'vt 9.23456789012345 8.45678901234567',
             'vn -0.0 1 0', 'vn 0 -1 0', 'usemtl wall', 'f 1/1/1 2/2/1 3/3/1',
             'f 1/1/1 2/2/1 3/3/1', 'g source-trim', 'usemtl trim', 'f 4/4/2 1/5/2 5/6/2']
    if mixed:
        text += ['g second-shell', 'usemtl wall', 'f 6/1/1 7/2/1 8/3/1',
                 'g second-trim', 'usemtl trim', 'f 9/4/2 6/5/2 10/6/2']
    raw = tmp_path / 'raw.obj'
    raw.write_text('\n'.join(text) + '\n', encoding='utf-8')
    source = parse_floor(raw.read_text())
    frame = Frame(1000 / 25.4, 'owner metres; independent Y-up evidence')
    engine = source.in_frame(frame)
    ancestry = list(range(1, source.mesh.n_faces))
    keep = np.ones(source.mesh.n_faces, bool); keep[0] = False
    source_input, engine_input = tmp_path / 'input.source.obj', tmp_path / 'input.engine.obj'
    write_floor(source, source_input, keep_triangles=keep)
    write_floor(engine, engine_input, keep_triangles=keep)
    before = replace(read_obj(engine_input), units=engine.mesh.units,
                     physical_quanta=engine.mesh.physical_quanta)
    looks = Looks(key={'wall': 'wall', 'trim': 'trim'}, texel={'wall': (1024, 1024)}, flat=frozenset({'trim'}))
    if mixed:
        class OneBadCut:
            name = 'E7'
            def plan(self, unit, ctx):
                edits = E7Thread().plan(unit, ctx)
                assert len(edits) == 2
                return [edits[0], replace(edits[1], new_face_uv=edits[1].new_face_uv + .25)]
        outcome = repair_unit(UnitState(before, None, {0: 'wall', 1: 'trim'}, None),
            RepairContext(FixProfile(), None, SiteJudge(looks)), engines=[OneBadCut()], validate_sites=True)
        assert len(outcome.kept) == 1 and len(outcome.rolled_back) == 1
    else:
        outcome = run_checked_e7(before, looks)
        assert len(outcome.kept) == 1
    baseline_source, baseline_engine = tmp_path/'before.source.obj', tmp_path/'before.engine.obj'
    write_floor(source, baseline_source); write_floor(engine, baseline_engine)
    paths = dict(provenance=tmp_path/'geometry-provenance.json', baseline_source=baseline_source,
                 baseline_engine=baseline_engine, raw=raw, reference=tmp_path/'reference.json', qualification=tmp_path/'qualification.json',
                 source_input=source_input, engine_input=engine_input, lineage=tmp_path/'source-faces.json',
                 edit_log=tmp_path/'edit-log.jsonl')
    paths['reference'].write_text(json.dumps({'source_sha256': sha256_file(raw),
        'polygons': {str(poly.line): [[0, 1, 2]] for poly in source.polygons}}))
    paths['qualification'].write_text(json.dumps({'qualified': True, 'source_obj_sha256': sha256_file(raw),
        'native_reference_sha256': sha256_file(paths['reference']), 'source_triangles_sha256': sha256_file(baseline_source),
        'engine_obj_sha256': sha256_file(baseline_engine), 'floor_id': '1F', 'source_revision': 'fixture-revision'}))
    paths['provenance'].write_text(json.dumps({'source_sha256': sha256_file(raw),
        'reference_sha256': sha256_file(paths['reference']), 'source_triangles_sha256': sha256_file(baseline_source),
        'engine_obj_sha256': sha256_file(baseline_engine), 'source_to_engine': frame.matrix.tolist()}))
    paths['lineage'].write_text(json.dumps({'schema_version': 1, 'mode': 'original_source_survivors',
        'input_triangles': source.mesh.n_faces, 'output_triangles': before.n_faces, 'source_faces': ancestry}))
    write_records(paths['edit_log'], outcome.records)
    binding = {'paths': {key: str(path) for key, path in paths.items()},
               'sha256': {key: sha256_file(path) for key, path in paths.items()},
               'before_digest': _source_digest(before).hex()}
    return source, engine, before, ancestry, outcome, looks, binding


def prepare(values):
    from tools.main_infra_e7_serialization import prepare_cut_pair
    return prepare_cut_pair(*values[:6], binding=values[6])


def exact(actual, expected):
    assert actual.shape == expected.shape and actual.dtype == expected.dtype
    assert actual.tobytes() == expected.tobytes()


def test_cut_pair_preserves_original_tables_and_explicit_e3_ancestry(tmp_path):
    values = fixture(tmp_path)
    pair = prepare(values)
    source, engine, before, ancestry, outcome, _looks, _binding = values
    exact(pair.source.mesh.positions, source.mesh.positions)
    exact(pair.engine.mesh.positions, engine.mesh.positions)
    exact(pair.engine.mesh.uvs, outcome.mesh.uvs)
    exact(pair.engine.mesh.normals, outcome.mesh.normals)
    exact(pair.source.mesh.uvs[:len(source.mesh.uvs)], source.mesh.uvs)
    exact(pair.source.mesh.normals[:len(source.mesh.normals)], source.mesh.normals)
    assert pair.source.mesh.face_v.tolist() == pair.engine.mesh.face_v.tolist() == [[3, 0, 4], [0, 3, 2], [3, 1, 2]]
    rows = pair.lineage['faces']
    assert [row['original_source_triangle'] for row in rows] == [2, 1, 1]
    assert [row['child'] for row in rows] == [None, 0, 1]
    assert [row['kind'] for row in rows] == ['unchanged', 'cut_child', 'cut_child']
    assert [row['group'] for row in rows] == ['source-trim', 'source-shell', 'source-shell']
    assert all(row['source_polygon_line'] == source.polygons[row['original_source_triangle']].line for row in rows)


def test_save_pair_and_saved_binding_are_exact_and_deterministic(tmp_path):
    from tools.main_infra_e7_serialization import save_cut_pair, bind_saved_cut_pair
    values = fixture(tmp_path)
    pair = prepare(values)
    receipt = save_cut_pair(pair, tmp_path/'first')
    assert receipt['original_source_triangles'] == 3
    assert receipt['stage_input_triangles'] == 2 and receipt['output_triangles'] == 3
    save_cut_pair(pair, tmp_path/'second')
    for name in ['candidate.source.obj', 'candidate.engine.obj', 'cut-lineage.json', 'checked-edits.json',
                 'cut-receipt.json', 'edit-log.jsonl']:
        assert (tmp_path/'first'/name).read_bytes() == (tmp_path/'second'/name).read_bytes()
    source_after, engine_after, saved = bind_saved_cut_pair(*values[:4], values[5], tmp_path/'first',
        binding=values[6], expected_receipt_sha256=receipt['receipt_sha256'])
    for actual, expected in [(source_after, pair.source.mesh), (engine_after, pair.engine.mesh)]:
        for field in ('positions', 'uvs', 'normals', 'face_v', 'face_vt', 'face_vn'):
            exact(getattr(actual, field), getattr(expected, field))
    assert saved['mode'] == 'e7_existing_vertex_cuts'
    assert any(len(line.split('.')[1]) > 6 for line in (tmp_path/'first'/'candidate.source.obj').read_text().splitlines()
               if line.startswith('vt ') and '.' in line)


def test_rolled_back_cut_contributes_no_children(tmp_path):
    values = fixture(tmp_path, mixed=True)
    pair = prepare(values)
    assert pair.source.mesh.n_faces == 5
    assert sum(row['kind'] == 'cut_child' for row in pair.lineage['faces']) == 2
    assert [row['original_source_triangle'] for row in pair.lineage['faces']] == [2, 3, 4, 1, 1]
    assert pair.checked['kept'] == [0] and pair.checked['rolled_back'] == [1]


@pytest.mark.parametrize('name', ['raw', 'reference', 'qualification', 'provenance', 'baseline_source', 'baseline_engine',
                                 'source_input', 'engine_input', 'lineage', 'edit_log'])
def test_changed_frozen_input_hash_is_refused(tmp_path, name):
    values = fixture(tmp_path)
    path = Path(values[6]['paths'][name]); path.write_bytes(path.read_bytes() + b'\n')
    with pytest.raises(ValueError): prepare(values)


@pytest.mark.parametrize('change', ['uv', 'positions', 'winding', 'material', 'unconfirmed', 'partition', 'ancestry'])
def test_unbound_or_forged_cut_state_is_refused(tmp_path, change):
    values = list(fixture(tmp_path))
    outcome = values[4]
    if change in ('uv', 'positions', 'winding', 'material'):
        mesh = replace(outcome.mesh)
        field = {'uv':'uvs', 'positions':'positions', 'winding':'face_v', 'material':'face_material'}[change]
        array = getattr(mesh, field).copy()
        if change == 'winding': array[-1] = array[-1, ::-1]
        else: array.flat[-1] += 1
        setattr(mesh, field, array); values[4] = replace(outcome, mesh=mesh)
    elif change == 'unconfirmed':
        values[4] = replace(outcome, checks=[{**outcome.checks[0], 'final': 'FAIL'}])
    elif change == 'partition': values[4] = replace(outcome, kept=[])
    else: values[3] = [0, 2]
    with pytest.raises(ValueError): prepare(values)


@pytest.mark.parametrize('name', ['candidate.source.obj', 'candidate.engine.obj', 'cut-lineage.json',
                                 'checked-edits.json', 'cut-receipt.json', 'edit-log.jsonl'])
def test_saved_pair_artifact_tampering_is_refused(tmp_path, name):
    from tools.main_infra_e7_serialization import save_cut_pair, bind_saved_cut_pair
    values = fixture(tmp_path); out = tmp_path/'candidate'
    receipt = save_cut_pair(prepare(values), out)
    path = out/name; path.write_bytes(path.read_bytes() + b'\n')
    with pytest.raises(ValueError):
        bind_saved_cut_pair(*values[:4], values[5], out, binding=values[6],
                            expected_receipt_sha256=receipt['receipt_sha256'])


def test_existing_output_directory_is_never_overwritten(tmp_path):
    from tools.main_infra_e7_serialization import save_cut_pair
    values = fixture(tmp_path); out = tmp_path/'candidate'; out.mkdir()
    (out/'sentinel').write_text('keep')
    with pytest.raises(ValueError): save_cut_pair(prepare(values), out)
    assert (out/'sentinel').read_text() == 'keep'


def test_failed_saved_readback_does_not_finalize_output(tmp_path, monkeypatch):
    import tools.main_infra_e7_serialization as module
    values = fixture(tmp_path); pair = prepare(values)
    original = module.write_floor
    def corrupt(floor, path, **kwargs):
        original(floor, path, **kwargs)
        text = path.read_text().replace('vt 0.123456789012345', 'vt 0.223456789012345', 1)
        path.write_text(text)
    monkeypatch.setattr(module, 'write_floor', corrupt)
    with pytest.raises(ValueError): module.save_cut_pair(pair, tmp_path/'candidate')
    assert not (tmp_path/'candidate').exists()


@pytest.mark.parametrize('attribute', ['new_face_uv', 'new_face_normal'])
def test_fake_pass_and_k1_equivalent_wrong_corner_values_are_refused(tmp_path, attribute):
    from engine.repair.types import apply_edits
    values = list(fixture(tmp_path)); outcome = values[4]
    original = outcome.edits[0]
    bad = replace(original, **{attribute: getattr(original, attribute) + .25})
    mesh, _ = apply_edits(values[2], [bad])
    values[4] = replace(outcome, mesh=mesh, edits=[bad], kept=[bad])
    with pytest.raises(ValueError): prepare(values)


@pytest.mark.parametrize('target', ['before_precision', 'original_source', 'engine_frame'])
def test_qualified_in_memory_inputs_cannot_be_replaced(tmp_path, target):
    values = list(fixture(tmp_path))
    if target == 'before_precision':
        values[2] = replace(values[2], physical_quanta=tuple(x * 2 for x in values[2].physical_quanta))
    elif target == 'original_source':
        mesh = replace(values[0].mesh, positions=values[0].mesh.positions.copy())
        mesh.positions[0, 0] += .001
        values[0] = replace(values[0], mesh=mesh)
    else:
        values[1] = replace(values[1], frame=Frame(1.0, 'wrong scale'))
    with pytest.raises(ValueError): prepare(values)
