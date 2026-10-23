import json
from pathlib import Path

import pytest

from engine.io.snapshot import sha256_file


def runner():
    from tools import main_infra_e7_1f_run
    return main_infra_e7_1f_run


def test_prepare_never_reaches_kernel(tmp_path, monkeypatch):
    run = runner()
    monkeypatch.setattr(run, '_load', lambda paths: ('source', 'engine', 'before', 'ancestry', 'looks', {'original_source_triangles': 3, 'stage_input_triangles': 2}))
    monkeypatch.setattr(run, '_components', lambda: {'HEAD': 'fixture'})
    monkeypatch.setattr(run, 'run_checked_e7', lambda *_: pytest.fail('prepare called kernel'))
    raw = tmp_path/'raw.obj'; raw.write_text('raw')
    value = run.prepare({'raw': str(raw)}, tmp_path/'planned.json', tmp_path/'result')
    assert value['state'] == 'prepared'
    assert value['original_source_triangles'] == 3 and value['stage_input_triangles'] == 2
    assert not (tmp_path/'result').exists()


def test_execute_refuses_changed_plan_before_loading_or_kernel(tmp_path, monkeypatch):
    run = runner()
    plan = tmp_path/'plan.json'; plan.write_text('{}')
    monkeypatch.setattr(run, '_load', lambda *_: pytest.fail('loaded changed plan'))
    with pytest.raises(ValueError, match='hash'):
        run.execute(plan, '0'*64)


def test_execute_refuses_changed_component_before_kernel(tmp_path, monkeypatch):
    run = runner()
    plan = tmp_path/'plan.json'; plan.write_text(json.dumps({'components': {'HEAD': 'old'}, 'paths': {}, 'sha256': {}}))
    monkeypatch.setattr(run, '_components', lambda: {'HEAD': 'new'})
    monkeypatch.setattr(run, 'run_checked_e7', lambda *_: pytest.fail('changed code reached kernel'))
    with pytest.raises(ValueError, match='component'):
        run.execute(plan, sha256_file(plan))


def test_execute_refuses_changed_input_before_kernel(tmp_path, monkeypatch):
    run = runner()
    raw = tmp_path/'raw'; raw.write_text('changed')
    plan = tmp_path/'plan.json'; plan.write_text(json.dumps({'components': {}, 'paths': {'raw': str(raw)}, 'sha256': {'raw': '0'*64}}))
    monkeypatch.setattr(run, '_components', lambda: {})
    monkeypatch.setattr(run, 'run_checked_e7', lambda *_: pytest.fail('changed input reached kernel'))
    with pytest.raises(ValueError, match='hash'):
        run.execute(plan, sha256_file(plan))


def test_new_asset_copies_are_verified(tmp_path):
    run = runner()
    source = tmp_path/'original'; source.mkdir()
    (source/'tex').mkdir(); (source/'tex/a.png').write_bytes(b'original texture')
    out = tmp_path/'candidate'; out.mkdir()
    assets = [{'path': 'tex/a.png', 'sha256': sha256_file(source/'tex/a.png')}]
    rows = run.copy_assets(source, out, assets)
    assert (out/'tex/a.png').read_bytes() == b'original texture'
    assert rows == [{'path': 'tex/a.png', 'sha256': assets[0]['sha256'], 'bytes': 16}]


def test_bad_new_asset_copy_fails_closed(tmp_path, monkeypatch):
    run = runner()
    source = tmp_path/'original'; source.mkdir(); (source/'a.png').write_bytes(b'original')
    out = tmp_path/'candidate'; out.mkdir()
    monkeypatch.setattr(run, 'copy_verified', lambda src, dst: dst.write_bytes(b'bad copy'))
    with pytest.raises(ValueError, match='hash'):
        run.copy_assets(source, out, [{'path': 'a.png', 'sha256': sha256_file(source/'a.png')}])


@pytest.mark.parametrize('path', ['../escape.png', '/absolute.png', 'C:/absolute.png', 'candidate.source.obj'])
def test_asset_paths_cannot_escape_or_replace_geometry(tmp_path, path):
    run = runner()
    source = tmp_path/'original'; source.mkdir()
    out = tmp_path/'candidate'; out.mkdir()
    with pytest.raises(ValueError, match='asset'):
        run.copy_assets(source, out, [{'path': path, 'sha256': '0'*64}])


def test_existing_asset_copy_is_never_overwritten(tmp_path):
    run = runner()
    source = tmp_path/'original'; source.mkdir(); (source/'a.png').write_bytes(b'original')
    out = tmp_path/'candidate'; out.mkdir(); (out/'a.png').write_bytes(b'keep')
    with pytest.raises(ValueError, match='exists'):
        run.copy_assets(source, out, [{'path': 'a.png', 'sha256': sha256_file(source/'a.png')}])
    assert (out/'a.png').read_bytes() == b'keep'


def test_execute_saves_actual_checked_fixture_with_new_assets(tmp_path, monkeypatch):
    from tools.tests.test_main_infra_e7_serialization import fixture
    run = runner()
    source, engine, before, ancestry, _outcome, looks, binding = fixture(tmp_path)
    texture = tmp_path/'fixture.png'; texture.write_bytes(b'fixture asset')
    facts = dict(original_source_triangles=source.mesh.n_faces, stage_input_triangles=before.n_faces,
        before_digest=binding['before_digest'], assets=[{'path': texture.name, 'sha256': sha256_file(texture)}],
        prior_failed_targets={'cracks': {'after': 1, 'target': 0, 'status': 'FAIL'}})
    monkeypatch.setattr(run, '_load', lambda _: (source, engine, before, ancestry, looks, facts))
    monkeypatch.setattr(run, '_components', lambda: {'HEAD': 'fixture'})
    plan, out = tmp_path/'plan.json', tmp_path/'saved'
    run.prepare(binding['paths'], plan, out)
    saved_states = []
    original_write = run._write
    def observe_write(path, value):
        if Path(path).name == 'worker.json.tmp' and value.get('state') == 'candidate_saved':
            saved_states.append(out.exists())
        original_write(path, value)
    monkeypatch.setattr(run, '_write', observe_write)
    worker = run.execute(plan, sha256_file(plan))
    assert saved_states and all(saved_states)
    assert worker['state'] == 'candidate_saved' and worker['kept_cuts'] == 1
    assert worker['floor_accepted'] is False and worker['independent_validation'] == 'pending'
    assert worker['post_e7_signed_targets'] == 'not independently measured'
    assert (out/'fixture.png').read_bytes() == b'fixture asset'
    receipt = json.loads((out/'cut-receipt.json').read_text())
    assert receipt['original_source_triangles'] == 3
    assert receipt['stage_input_triangles'] == 2 and receipt['output_triangles'] == 3
    assert json.loads((out/'cut-lineage.json').read_text())['faces'][1]['original_source_triangle'] == 1
    assert not (tmp_path/'execution-1F/candidate').exists()
    assert json.loads((tmp_path/'execution-1F/worker.json').read_text())['final_package'] == str(out.resolve())
    with pytest.raises(ValueError, match='exists'):
        run.execute(plan, sha256_file(plan))


def test_duplicate_asset_inventory_is_refused_without_overwriting(tmp_path, monkeypatch):
    run = runner()
    source = tmp_path/'source'; source.mkdir(); (source/'a.png').write_bytes(b'a')
    out = tmp_path/'candidate'; out.mkdir()
    monkeypatch.setattr(run, 'copy_verified', lambda src, dst: dst.write_bytes(src.read_bytes()))
    row = {'path': 'a.png', 'sha256': sha256_file(source/'a.png')}
    with pytest.raises(ValueError, match='duplicate'):
        run.copy_assets(source, out, [row, {**row, 'path': 'A.PNG'}])
