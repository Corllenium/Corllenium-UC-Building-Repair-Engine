import copy,json
from pathlib import Path
import pytest
from engine.io.snapshot import sha256_file

POLICY=Path(__file__).resolve().parents[2]/'docs/superpowers/records/MAIN-INFRA-E3-1F-RETAIN-VISIBLE-20261024/policy.json'


def api():
    from tools import main_infra_e3_visible_run
    return main_infra_e3_visible_run


def write(tmp_path,value):
    path=tmp_path/'policy.json';path.write_text(json.dumps(value))
    return dict(path=str(path),sha256=sha256_file(path))


def test_actual_visible_site_policy_binds_all14_missing_lines_without_claiming_clearance():
    policy,evidence,retained=api().read_policy(dict(path=str(POLICY),sha256=sha256_file(POLICY)))
    assert policy['restore_sites']==[5] and policy['required_faces']==[9809,10366]
    assert len(retained)==274 and set(policy['required_faces'])<=set(retained)
    assert len(evidence['lost_lines'])==14 and evidence['attribution']['unresolved_lines']==14
    assert evidence['provenance']['acceptance'] is False


@pytest.mark.parametrize('change',['wrong_site','duplicate_site','wrong_faces','counts','unknown_field','wrong_audit','evidence_hash'])
def test_rehashed_policy_cannot_change_actual_retention_scope(tmp_path,change):
    p=json.loads(POLICY.read_text())
    if change=='wrong_site':p['restore_sites']=[0]
    if change=='duplicate_site':p['restore_sites']=[5,5]
    if change=='wrong_faces':p['required_faces']=[9809,10367]
    if change=='counts':p['original_counts']['kept']=279
    if change=='unknown_field':p['ignore_loss']=True
    if change=='wrong_audit':p['original_audit']['sha256']='0'*64
    if change=='evidence_hash':p['evidence']['lost_lines']['sha256']='0'*64
    with pytest.raises(ValueError):api().read_policy(write(tmp_path,p))


def test_visible_replay_namespace_is_new_and_exclusive(tmp_path):
    base=tmp_path/'run-20261024-1F-retain-visible'
    api().check_namespace(base/'preparation-1F.json',base/'1F')
    for bad in ('run-20261023','run-20261024-attempt4','run-20261024-attempt5'):
        with pytest.raises(ValueError):api().check_namespace(tmp_path/bad/'preparation-1F.json',tmp_path/bad/'1F')
    with pytest.raises(ValueError):api().check_namespace(base/'preparation-1F.json',base/'2F')


def test_selection_reuses_all_original_records_with_explicit_restore5(monkeypatch):
    from tools.main_infra_e3_replay import _original_edit
    from tools.main_infra_e7_checkpoint import typed_plan_digest
    m=api();pin=dict(path=str(POLICY),sha256=sha256_file(POLICY));p,e,retained=m.read_policy(pin)
    rows=e['original_records'][:-1];selected=[_original_edit(r,15856) for r in rows if not r.get('rolled_back',False) and r['site']!=5]
    seen={}
    def load(before,looks,candidate,**kwargs):
        seen.update(kwargs)
        return selected,dict(original_kept_sites=280,restored_sites=[5],remaining_sites=279,remaining_removed_triangles=5446,fresh_site_check_required=True)
    monkeypatch.setattr(m,'load_replay_plan',load,raising=False)
    got=m.select_plan(None,None,p,e,retained)
    assert seen['restore_sites']==(5,) and seen['expected_audit_sha256']==p['original_audit']['sha256']
    assert got['selected']==279 and got['retained_source_faces']==retained
    assert got['typed_plan_digest']==typed_plan_digest(selected)
    assert set(got['original_rolled_sites'])=={r['site'] for r in rows if r.get('rolled_back',False)}
    assert set(got['selected_sites']).isdisjoint({5,*got['original_rolled_sites']})


@pytest.fixture
def runner_case(tmp_path,monkeypatch):
    from tools.tests.test_main_infra_e3_checkpoint import captured
    from tools.main_infra_e7_checkpoint import typed_plan_digest
    from tools.main_infra_e7_serialization import _encode
    from engine.io.minecraft_floor import Frame,parse_floor
    from tools.main_infra_e3 import _source_digest
    m=api();before,outcome,looks,binding=captured.__wrapped__(tmp_path)
    source=parse_floor((tmp_path/'source.obj').read_text());provenance=json.loads((tmp_path/'baseline/geometry-provenance.json').read_text())
    engine=source.in_frame(Frame(1000/25.4,provenance['frame_evidence']))
    audit=json.loads(Path(binding['paths']['audit']).read_text())
    paths=dict(binding['paths'],raw=str(tmp_path/'source.obj'),reference=str(tmp_path/'reference.json'),
        provenance=str(tmp_path/'baseline/geometry-provenance.json'),qualification=str(tmp_path/'qualification.json'))
    facts=dict(original_source_triangles=2,stage_input_triangles=2,before_digest=_source_digest(before).hex(),assets=provenance['assets'],
        physical=audit['input_receipt'],prior_failed_targets={})
    proof=dict(selected=1,selected_sites=[0],retained_source_faces=[0],original_rolled_sites=[],
        typed_plan_digest=typed_plan_digest(outcome.edits),selected_edits=[dict(_encode(e),decision=e.decision) for e in outcome.edits],
        replay=dict(original_kept_sites=1,restored_sites=[5],remaining_sites=1,remaining_removed_triangles=1,fresh_site_check_required=True))
    components={'HEAD':'fixture'};monkeypatch.setattr(m,'components',lambda:components,raising=False)
    monkeypatch.setattr(m,'load_inputs',lambda paths:(source,engine,before,looks,facts),raising=False)
    monkeypatch.setattr(m,'select_plan',lambda *args:proof,raising=False)
    def run(*args,**kwargs):
        assert kwargs['restore_sites']==(5,)
        return outcome,__import__('numpy').arange(2),proof['replay']
    monkeypatch.setattr(m,'run_checked_replay',run,raising=False)
    plan=tmp_path/'run-20261024-1F-retain-visible/preparation-1F.json';out=plan.parent/'1F'
    pin=dict(path=str(POLICY),sha256=sha256_file(POLICY))
    return m,paths,plan,out,pin,proof,run


def test_runner_saves_new_exact_pair_only_after_checkpoint_and_fresh_result(runner_case):
    m,paths,plan,out,pin,proof,_run=runner_case
    m.prepare(paths,plan,out,policy_pin=pin)
    result=m.execute(plan,sha256_file(plan),policy_pin=pin)
    assert result['state']=='candidate_saved' and result['checkpoint_status']=='verified'
    assert result['kept_edits']==0 and result['rolled_back_edits']==1
    mapping=json.loads((out/'source-faces.json').read_text());assert mapping['source_faces']==[0,1]
    audit=json.loads((out/'stage-audit.json').read_text())
    assert audit['guard']['passed'] is False and audit['accepted'] is False
    receipt=json.loads((out/'retention-receipt.json').read_text())
    assert receipt['selection']==proof and receipt['all_retained_faces_survive'] is True
    assert receipt['checkpoint_receipt_sha256']==result['checkpoint_receipt_sha256']


def test_serializer_failure_keeps_actual_checkpoint_and_no_final_candidate(runner_case,monkeypatch):
    m,paths,plan,out,pin,_proof,_run=runner_case;m.prepare(paths,plan,out,policy_pin=pin)
    def fail(*args,**kwargs):
        assert (plan.parent/'execution-1F/checked-outcome/checkpoint-receipt.json').is_file()
        raise RuntimeError('forced serializer failure')
    monkeypatch.setattr(m,'serialize_result',fail,raising=False)
    with pytest.raises(RuntimeError,match='serializer'):m.execute(plan,sha256_file(plan),policy_pin=pin)
    worker=json.loads((plan.parent/'execution-1F/worker.json').read_text())
    assert worker['state']=='failed' and worker['checkpoint_status']=='verified' and not out.exists()


@pytest.mark.parametrize('drift',['preparation','components','typed_plan'])
def test_kernel_drift_preserves_diagnostic_capture_without_serializing(runner_case,monkeypatch,drift):
    from dataclasses import replace
    m,paths,plan,out,pin,_proof,run=runner_case;m.prepare(paths,plan,out,policy_pin=pin)
    def changed(*args,**kwargs):
        outcome,survivors,replay=run(*args,**kwargs)
        if drift=='preparation':plan.write_text(plan.read_text()+' ')
        if drift=='components':monkeypatch.setattr(m,'components',lambda:{'HEAD':'drift'})
        if drift=='typed_plan':
            edit=replace(outcome.edits[0],reason='different typed proposal')
            from engine.repair.kernel import stage_records
            records=stage_records(args[0],[edit],{i:args[1].key_of(n) for i,n in enumerate(args[0].materials)},'E3')
            records[0]['rolled_back']=True
            outcome=replace(outcome,edits=[edit],rolled_back=[edit],records=records+[{'check':outcome.checks[0]}])
        return outcome,survivors,replay
    monkeypatch.setattr(m,'run_checked_replay',changed)
    monkeypatch.setattr(m,'serialize_result',lambda *a,**k:pytest.fail('drift may not reach serializer'),raising=False)
    with pytest.raises(ValueError):m.execute(plan,sha256_file(plan),policy_pin=pin)
    worker=json.loads((plan.parent/'execution-1F/worker.json').read_text())
    assert worker['state']=='failed' and worker['checkpoint_status']=='diagnostic_unverified'
    assert (plan.parent/'execution-1F/checked-outcome/checkpoint-receipt.json').is_file() and not out.exists()


def test_serialization_refuses_loss_of_any_required_whole_site_face(runner_case):
    from dataclasses import replace
    from engine.repair.types import Edit,apply_edits
    from engine.repair.kernel import KernelResult,stage_records
    m,paths,plan,out,pin,proof,_run=runner_case
    prepared=m.prepare(paths,plan,out,policy_pin=pin)
    source,engine,before,looks,facts=m.load_inputs(paths)
    e=Edit('E3','remove',(0,),None,None,0,'synthetic bad retention',{})
    mesh,_=apply_edits(before,[e]);check=dict(stage='E3',engine='E3',legacy=False,rollback=True,final='PASS',
        runs=[dict(status='PASS',failing=0,unknown=0)])
    records=stage_records(before,[e],{i:looks.key_of(n) for i,n in enumerate(before.materials)},'E3')
    outcome=KernelResult(mesh,None,[e],[],None,[e],[],[check],records+[{'check':check}])
    with pytest.raises(ValueError,match='retained'):
        m.serialize_result(source,engine,before,outcome,looks,facts,prepared,{},dict(receipt_sha256='a'*64),out)
    assert not out.exists()


def test_cli_help_never_loads_model_or_runs_engine(monkeypatch):
    m=api();monkeypatch.setattr(m,'load_inputs',lambda *_:pytest.fail('help may not load model'))
    with pytest.raises(SystemExit) as exc:m.main(['--help'])
    assert exc.value.code==0
