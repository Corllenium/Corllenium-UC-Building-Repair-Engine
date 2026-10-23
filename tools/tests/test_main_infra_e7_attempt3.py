import json
from pathlib import Path

import pytest

from engine.io.minecraft_floor import Frame,parse_floor
from engine.io.snapshot import sha256_file
from tools.main_infra_e7_checkpoint import restore_e7_checkpoint
from tools.main_infra_e7_subset import verify_donor_subset
from tools.tests.test_main_infra_e7_subset import donor


def api():
    from tools import main_infra_e7_attempt3
    return main_infra_e7_attempt3


@pytest.fixture
def prepared(tmp_path,donor,monkeypatch):
    run = api()
    before,looks,donor_paths,donor_hashes,component_root,_ = donor
    original = json.loads(Path(donor_paths['preparation']).read_text())
    paths = original['paths']
    source = parse_floor(Path(paths['raw']).read_text())
    engine = source.in_frame(Frame(1000/25.4,'fixture'))
    ancestry = json.loads(Path(paths['lineage']).read_text())['source_faces']
    asset = Path(paths['raw']).parent/'fixture.png'; asset.write_bytes(b'new original asset')
    facts = dict(original_source_triangles=source.mesh.n_faces,stage_input_triangles=before.n_faces,
        before_digest=original['inputs']['before_digest'],assets=[{'path':asset.name,'sha256':sha256_file(asset)}],
        prior_failed_targets={'cracks':{'after':1,'target':0,'status':'FAIL'}})
    monkeypatch.setattr(run,'_load',lambda _:(source,engine,before,ancestry,looks,facts))
    monkeypatch.setattr(run,'_components',lambda:{'HEAD':'fixture'})
    monkeypatch.setattr(run,'_select',lambda b,l,p,h:verify_donor_subset(b,l,paths=p,expected_sha256=h,
        component_root=component_root,expected_counts=(2,1)))
    plan,out = tmp_path/'attempt3-preparation.json',tmp_path/'attempt3/1F'
    run.prepare(paths,donor_paths,donor_hashes,plan,out)
    return run,plan,out,before,looks


def test_prepare_is_pure_admission_and_never_runs_kernel(prepared,monkeypatch,tmp_path,donor):
    run,plan,out,*_ = prepared
    monkeypatch.setattr(run,'run_checked_subset',lambda *_:pytest.fail('prepare reached kernel'))
    value = json.loads(plan.read_text())
    assert value['selection']['selected'] == 1
    assert value['preflight']['exact_source_passed'] == 1
    assert value['preflight']['rejected_sites'] == []
    assert not out.exists() and not (out.parent/'execution-1F').exists()


def test_wrong_preparation_or_component_rejects_before_kernel(prepared,monkeypatch):
    run,plan,*_ = prepared
    monkeypatch.setattr(run,'run_checked_subset',lambda *_:pytest.fail('wrong preparation reached kernel'))
    with pytest.raises(ValueError,match='hash'):
        run.execute(plan,'0'*64)
    monkeypatch.setattr(run,'_components',lambda:{'HEAD':'changed'})
    with pytest.raises(ValueError,match='component'):
        run.execute(plan,sha256_file(plan))


def test_checkpoint_is_saved_before_downstream_serializer_error(prepared,monkeypatch):
    run,plan,out,before,looks = prepared
    def fail_after_actual_checkpoint(*args,**kwargs):
        work = out.parent/'execution-1F'
        receipt = work/'checked-outcome/checkpoint-receipt.json'
        assert receipt.exists()
        checkpoint = json.loads(receipt.read_text())
        actual = restore_e7_checkpoint(before,looks,receipt.parent,binding=checkpoint['binding'],
            expected_receipt_sha256=sha256_file(receipt))
        assert actual.checks[0]['sites'] == 1 and actual.checks[0]['first'] == 'PASS'
        raise RuntimeError('downstream serializer fixture failure')
    monkeypatch.setattr(run,'prepare_cut_pair',fail_after_actual_checkpoint)
    with pytest.raises(RuntimeError,match='downstream'):
        run.execute(plan,sha256_file(plan))
    worker = json.loads((out.parent/'execution-1F/worker.json').read_text())
    checkpoint = out.parent/'execution-1F/checked-outcome/checkpoint-receipt.json'
    assert worker['state'] == 'failed'
    assert worker['checkpoint_receipt_sha256'] == sha256_file(checkpoint)
    assert not out.exists() and not (out.parent/'execution-1F/candidate').exists()


def test_actual_new_subset_candidate_has_new_assets_and_bound_checkpoint(prepared):
    run,plan,out,before,looks = prepared
    worker = run.execute(plan,sha256_file(plan))
    assert worker['state'] == 'candidate_saved' and worker['planned_cuts'] == worker['kept_cuts'] == 1
    assert worker['floor_accepted'] is False and worker['independent_validation'] == 'pending'
    assert worker['run_id'] == 'MAIN-INFRA-E7-1F-attempt3-20261023'
    assert worker['checks'][0]['sites'] == 1
    assert (out/'fixture.png').read_bytes() == b'new original asset'
    cut = json.loads((out/'cut-receipt.json').read_text())
    checkpoint = out.parent/'execution-1F/checked-outcome/checkpoint-receipt.json'
    assert cut['binding']['sha256']['checked_outcome_receipt'] == sha256_file(checkpoint)
    assert cut['original_source_triangles'] == 5 and cut['stage_input_triangles'] == 4
    assert cut['output_triangles'] == 5 and worker['post_e7_signed_targets'] == 'not independently measured'
    with pytest.raises(ValueError,match='exists'):
        run.execute(plan,sha256_file(plan))


@pytest.mark.parametrize('drift',['preparation','component'])
def test_drift_during_kernel_keeps_diagnostic_capture_and_refuses_candidate(prepared,monkeypatch,drift):
    run,plan,out,before,looks = prepared
    pinned = sha256_file(plan)
    actual_kernel = run.run_checked_subset
    def checked_then_drift(*args):
        result = actual_kernel(*args)
        if drift == 'preparation':
            value = json.loads(plan.read_text()); value['changed_during_kernel'] = True
            plan.write_text(json.dumps(value))
        return result
    monkeypatch.setattr(run,'run_checked_subset',checked_then_drift)
    if drift == 'component':
        calls = iter([{'HEAD':'fixture'},{'HEAD':'changed-during-kernel'}])
        monkeypatch.setattr(run,'_components',lambda:next(calls))
    monkeypatch.setattr(run,'prepare_cut_pair',lambda *a,**kw:pytest.fail('drift reached serializer'))
    with pytest.raises(ValueError,match='hash|component'):
        run.execute(plan,pinned)
    work = out.parent/'execution-1F'
    receipt_path = work/'checked-outcome/checkpoint-receipt.json'
    receipt = json.loads(receipt_path.read_text())
    worker = json.loads((work/'worker.json').read_text())
    assert worker['state'] == 'failed' and worker['checkpoint_status'] == 'diagnostic_unverified'
    assert worker['checkpoint_receipt_sha256'] == sha256_file(receipt_path)
    assert receipt['binding']['sha256']['preparation'] == pinned
    assert receipt['binding']['preparation_sha256'] == pinned
    assert not out.exists() and not (work/'candidate').exists()
