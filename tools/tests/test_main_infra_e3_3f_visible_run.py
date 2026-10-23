import copy,json
from pathlib import Path
import pytest
from engine.io.snapshot import sha256_file

POLICY=Path(__file__).resolve().parents[2]/'docs/superpowers/records/MAIN-INFRA-E3-3F-RETAIN-VISIBLE-20261024/policy.json'
def api():
    from tools import main_infra_e3_3f_visible_run
    return main_infra_e3_3f_visible_run

def pin(path=POLICY):return dict(path=str(path),sha256=sha256_file(path))

def test_actual_report_cohort_restores_native258_and_five_nonfailing_sites():
    p,e,retained=api().read_policy(pin())
    assert len(p['restore_sites'])==263 and len(p['native_sites'])==258
    assert p['subthreshold_extra_sites']==[190,265,267,358,984]
    assert e['signed_preservation_failure_sites']==[] and e['subthreshold_extras_are_failures'] is False
    assert len(e['original_records'])==1821 and len(e['native_changed_pixels'])==119
    assert len(retained)==p['original_counts']['site_faces'] and len(set(retained))==len(retained)
    assert set(p['required_faces'])<=set(retained)

@pytest.mark.parametrize('change',['missing','duplicate','unknown','native','subthreshold','faces','counts','audit','evidence','extra_field'])
def test_rehashed_policy_cannot_change_measured_cohort(tmp_path,change):
    p=json.loads(POLICY.read_text())
    if change=='missing':p['restore_sites'].pop()
    if change=='duplicate':p['restore_sites'].append(p['restore_sites'][0])
    if change=='unknown':p['restore_sites'][-1]=999999
    if change=='native':p['native_sites']=p['native_sites'][1:]
    if change=='subthreshold':p['subthreshold_extra_sites']=[]
    if change=='faces':p['required_faces']=p['required_faces'][1:]
    if change=='counts':p['original_counts']['rolled_back']=144
    if change=='audit':p['original_audit']['sha256']='0'*64
    if change=='evidence':p['evidence']['footprint']['sha256']='0'*64
    if change=='extra_field':p['claim_preservation_pass']=True
    path=tmp_path/'policy.json';path.write_text(json.dumps(p))
    with pytest.raises(ValueError):api().read_policy(pin(path))

def test_namespace_is_new_3f_only(tmp_path):
    base=tmp_path/'run-20261024-3F-retain-visible';api().check_namespace(base/'preparation-3F.json',base/'3F')
    for name in ['run-20261023-attempt2','run-20261024-1F-retain-visible']:
        with pytest.raises(ValueError):api().check_namespace(tmp_path/name/'preparation-3F.json',tmp_path/name/'3F')
    with pytest.raises(ValueError):api().check_namespace(base/'preparation-1F.json',base/'1F')

def test_original1820_verification_precedes_exact1412_ordered_selection(monkeypatch):
    from tools.main_infra_e3_replay import _original_edit
    from tools.main_infra_e7_checkpoint import typed_plan_digest
    m=api();p,e,retained=m.read_policy(pin());rows=e['original_records'][:-1]
    selected=[_original_edit(r,53602) for r in rows if not r.get('rolled_back',False) and r['site'] not in p['restore_sites']]
    seen={}
    def load(before,looks,candidate,**kwargs):
        seen.update(kwargs)
        return selected,dict(original_kept_sites=1675,restored_sites=p['restore_sites'],remaining_sites=1412,remaining_removed_triangles=sum(len(x.faces) for x in selected),fresh_site_check_required=True)
    monkeypatch.setattr(m,'load_replay_plan',load,raising=False)
    result=m.select_plan(None,None,p,e,retained)
    assert seen['restore_sites']==tuple(p['restore_sites'])
    assert result['selected']==1412 and result['selected_sites']==[x.site for x in selected]
    assert result['typed_plan_digest']==typed_plan_digest(selected)
    assert len(result['original_rolled_sites'])==145
    assert set(result['selected_sites']).isdisjoint(set(p['restore_sites'])|set(result['original_rolled_sites']))
    assert result['retained_source_faces']==retained and result['old_verdict_is_not_reused'] is True

@pytest.fixture
def profile_runner(tmp_path,monkeypatch):
    from tools.tests.test_main_infra_e3_visible_run import runner_case
    common,paths,_plan,_out,_pin,proof,old_run=runner_case.__wrapped__(tmp_path,monkeypatch)
    m=api();policy,evidence,retained=m.read_policy(pin())
    proof=dict(proof,replay=dict(proof['replay'],restored_sites=policy['restore_sites']))
    source,engine,before,looks,facts=common.load_inputs(paths)
    monkeypatch.setattr(m,'components',lambda:{'HEAD':'tiny-profile'},raising=False)
    monkeypatch.setattr(m,'load_inputs',lambda _paths:(source,engine,before,looks,facts),raising=False)
    monkeypatch.setattr(m,'select_plan',lambda *args:proof)
    # Existing fixture supplies an explicitly synthetic typed rollback, never an admission pass.
    def run(*args,**kwargs):
        assert kwargs['restore_sites']==tuple(policy['restore_sites'])
        result,indices,_receipt=old_run(*args,**dict(kwargs,restore_sites=(5,)))
        return result,indices,proof['replay']
    monkeypatch.setattr(common,'run_checked_replay',run)
    plan=tmp_path/'run-20261024-3F-retain-visible/preparation-3F.json';out=plan.parent/'3F'
    return common,m,paths,plan,out,proof,run


def test_shared_driver_profile_saves_actual_tiny_checkpoint_and_exact_pair(profile_runner):
    common,m,paths,plan,out,proof,_run=profile_runner
    common.prepare(paths,plan,out,policy_pin=pin(),profile=m)
    result=common.execute(plan,sha256_file(plan),policy_pin=pin(),profile=m)
    assert result['floor']=='3F' and result['run_id']==m.RUN_ID and result['state']=='candidate_saved'
    assert result['checkpoint_status']=='verified' and result['kept_edits']==0 and result['rolled_back_edits']==1
    assert json.loads((out/'source-faces.json').read_text())['source_faces']==[0,1]
    assert json.loads((out/'retention-receipt.json').read_text())['run_id']==m.RUN_ID
    assert json.loads((out/'stage-audit.json').read_text())['guard']['passed'] is False
    assert not (plan.parent/'execution-1F').exists()


def test_shared_profile_serializer_failure_preserves_verified_checkpoint(profile_runner,monkeypatch):
    common,m,paths,plan,out,proof,_run=profile_runner
    common.prepare(paths,plan,out,policy_pin=pin(),profile=m)
    def fail(*a,**k):
        assert (plan.parent/'execution-3F/checked-outcome/checkpoint-receipt.json').is_file()
        raise RuntimeError('tiny serializer failure')
    monkeypatch.setattr(common,'serialize_result',fail)
    with pytest.raises(RuntimeError,match='serializer'):common.execute(plan,sha256_file(plan),policy_pin=pin(),profile=m)
    worker=json.loads((plan.parent/'execution-3F/worker.json').read_text())
    assert worker['state']=='failed' and worker['checkpoint_status']=='verified' and not out.exists()


@pytest.mark.parametrize('drift',['preparation','components'])
def test_profile_post_kernel_drift_cannot_serialize(profile_runner,monkeypatch,drift):
    common,m,paths,plan,out,proof,run=profile_runner
    common.prepare(paths,plan,out,policy_pin=pin(),profile=m)
    def changed(*a,**k):
        value=run(*a,**k)
        if drift=='preparation':plan.write_text(plan.read_text()+' ')
        else:monkeypatch.setattr(m,'components',lambda:{'HEAD':'drift'})
        return value
    monkeypatch.setattr(common,'run_checked_replay',changed)
    monkeypatch.setattr(common,'serialize_result',lambda *a,**k:pytest.fail('drift reached serializer'))
    with pytest.raises(ValueError):common.execute(plan,sha256_file(plan),policy_pin=pin(),profile=m)
    worker=json.loads((plan.parent/'execution-3F/worker.json').read_text())
    assert worker['state']=='failed' and worker['checkpoint_status']=='diagnostic_unverified' and not out.exists()


@pytest.fixture
def tiny_qualified_paths(tmp_path,monkeypatch):
    from tools.tests.test_main_infra_e3_replay import fixture
    _before,_looks,candidate,_audit=fixture(tmp_path)
    qpath=tmp_path/'qualification.json';q=json.loads(qpath.read_text());q.update(floor_id='3F',source_revision=api().REVISION,job_id='MAIN-INFRA-CLEAN-20261023');qpath.write_text(json.dumps(q))
    apath=candidate/'stage-audit.json';a=json.loads(apath.read_text());a.update(qualification_sha256=sha256_file(qpath),input_triangles=2,output_triangles=1,guard={'passed':False});apath.write_text(json.dumps(a))
    materials=tmp_path/'materials.json';materials.write_text(json.dumps({'materials':{'wall':{'look':'wall','map_kd':'wall.png','kd':[1,1,1]}}}))
    prior=tmp_path/'prior-validation.json';prior.write_text(json.dumps({'checks':{'problems':{'kinds':{}}}}))
    paths=dict(raw=str(tmp_path/'source.obj'),reference=str(tmp_path/'reference.json'),qualification=str(qpath),provenance=str(tmp_path/'baseline/geometry-provenance.json'),baseline_source=str(tmp_path/'baseline/before.source.obj'),baseline_engine=str(tmp_path/'baseline/before.engine.obj'),source_input=str(candidate/'candidate.source.obj'),engine_input=str(candidate/'candidate.engine.obj'),lineage=str(candidate/'source-faces.json'),e3_audit=str(apath),e3_edit_log=str(candidate/'edit-log.jsonl'),materials=str(materials),targets=str(api().ROOT/'engine/validate/targets.json'),prior_validation=str(prior))
    monkeypatch.setattr(api(),'ANCHORS',{key:sha256_file(path) for key,path in paths.items()},raising=False)
    monkeypatch.setattr(api(),'SOURCE_TRIANGLES',2,raising=False);monkeypatch.setattr(api(),'RETIRED_TRIANGLES',1,raising=False)
    return paths


def test_genuine_qualified_loader_accepts_pending_prior_guard_without_inheriting_pass(tiny_qualified_paths):
    source,engine,before,looks,facts=api().load_inputs(tiny_qualified_paths)
    assert source.mesh.n_faces==engine.mesh.n_faces==before.n_faces==2
    assert facts['retired_stage_triangles']==1 and facts['prior_preservation_is_not_reused'] is True
    assert facts['unknown_materials']==[] and facts['no_texel']==[] and looks.unknown(before)==[]


@pytest.mark.parametrize('target',['raw','qualification','lineage','source_input','materials'])
def test_qualified_loader_rejects_changed_source_or_proof(tiny_qualified_paths,target):
    path=Path(tiny_qualified_paths[target]);path.write_bytes(path.read_bytes()+b'\n')
    with pytest.raises(ValueError,match='hash'):api().load_inputs(tiny_qualified_paths)


def test_profile_cli_help_never_loads_model(monkeypatch,capsys):
    monkeypatch.setattr(api(),'load_inputs',lambda *a:pytest.fail('help loaded model'),raising=False)
    with pytest.raises(SystemExit) as exc:api().main(['--help'])
    assert exc.value.code==0
    help_text=capsys.readouterr().out
    assert '3F' in help_text and 'original 1F' not in help_text


def test_actual_3f_paths_include_every_consumed_snapshot_and_asset_pin():
    paths=api().real_paths()
    assert 'before' in paths and any(k.startswith('snapshot_') for k in paths)
    for label in ('raw','baseline','candidate'):
        assert any(k.startswith('asset_'+label+'_') for k in paths)
