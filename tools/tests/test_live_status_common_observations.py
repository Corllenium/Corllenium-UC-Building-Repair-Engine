import copy
import hashlib
import json
from pathlib import Path
import re
import sys
from types import SimpleNamespace

import pytest

RUNTIME=Path(__file__).resolve().parents[2]/'docs/superpowers/records/scripts/main-infra/live-worker-status-runtime.ps1'
E3_1F='D:/LLM_BACKUP/Codex session/main-infra-e3-1f-retain-visible-20261024/05-Corllenium-UC-Building-Repair-Engine'
RUN='MAIN-INFRA-E3-3F-retain-visible-20261024'
START='2026-10-23T22:43:56.2456960Z'


def update(tmp_path,monkeypatch,*,phase='checking',alive=True,change=None,legacy=False,validator=None,doc=None,now='2026-10-23T22:45:00Z',cpu=3,finished_1f=False,retained_schema=False):
    code=re.search(r"(?ms)\$taskPython=@'\r?\n(.*?)\r?\n'@",RUNTIME.read_text(encoding='utf-8-sig')).group(1)
    original=Path
    def mapped(value):
        text=str(value).replace('\\','/');external='D:/PROJECTS/UC MODEL FIXER'
        if text==E3_1F or text.startswith(E3_1F+'/'):return tmp_path/'e3-1f'/text[len(E3_1F):].lstrip('/')
        return tmp_path/'main'/text[len(external):].lstrip('/') if text==external or text.startswith(external+'/') else original(value)
    namespace=tmp_path/'repair';namespace.mkdir(exist_ok=True)
    plan_path=namespace/'preparation-3F.json';worker_path=namespace/'execution-3F/worker.json'
    qualification=namespace/'qualification-3F.json'
    qualification.write_text(json.dumps(dict(schema_version=1,qualified=True,floor_id='3F',source_revision='fresh')))
    plan=dict(mode='fresh_checked_e3_visible_replay',state='prepared',run_id=RUN,floor='3F',paths={'qualification':str(qualification)},sha256={'qualification':hashlib.sha256(qualification.read_bytes()).hexdigest()},components={'HEAD':'frozen'},out=str(namespace/'3F'))
    if retained_schema:
        retained=original('D:/LLM_BACKUP/Codex session/main-infra-e3-3f-retain-visible-20261024/05-Corllenium-UC-Building-Repair-Engine/data/main-infra-e3/attempt2/run-20261024-3F-retain-visible/preparation-3F.json')
        assert hashlib.sha256(retained.read_bytes()).hexdigest()=='b62f399728cd09e08cfbecc8306d61628d62d8f6aa972c8ecf26b008a4cd1f62'
        plan=json.loads(retained.read_text());assert 'source_revision' not in plan
        plan['out']=str(namespace/'3F')
    plan_path.write_text(json.dumps(plan));plan_hash=hashlib.sha256(plan_path.read_bytes()).hexdigest()
    worker=dict(pid=60376,floor='3F',run_id=RUN,state=phase,output_triangles=44972,components={'HEAD':plan['components']['HEAD']},preparation=str(plan_path),preparation_sha256=plan_hash,started_utc='2026-10-23T22:44:08Z')
    process=dict(engine='E3',run_id=RUN,component_commit=plan['components']['HEAD'],preparation=str(plan_path),preparation_sha256=plan_hash,alive=alive,worker_path=str(worker_path),expected_pid=60376,expected_start=START,start=START,cpu=cpu)
    if legacy:
        worker=dict(pid=60376,floor_id='3F',state=phase,output_triangles=38691)
        process={k:v for k,v in process.items() if k not in ('engine','run_id','component_commit','preparation','preparation_sha256')}
    revision=json.loads(original(plan['paths']['qualification']).read_text())['source_revision']
    if change=='run':worker['run_id']='wrong'
    elif change=='floor':worker['floor']='2F'
    elif change=='pid':worker['pid']=999
    elif change=='start':process['start']='2026-10-23T22:43:56.2456961Z'
    elif change=='path':process['worker_path']=str(namespace/'wrong-worker.json')
    elif change=='P_hash':process['preparation_sha256']='0'*64
    elif change=='worker_P':worker['preparation_sha256']='0'*64
    elif change=='component':worker['components']['HEAD']='wrong'
    elif change=='source':
        plan['source_revision']='wrong';plan_path.write_text(json.dumps(plan))
        process['preparation_sha256']=worker['preparation_sha256']=hashlib.sha256(plan_path.read_bytes()).hexdigest()
    elif change in ('qualification_hash','qualification_revision','qualification_floor','qualification_not_qualified'):
        if change=='qualification_hash':plan['sha256']['qualification']='0'*64
        else:
            q=json.loads(original(plan['paths']['qualification']).read_text())
            q[{'qualification_revision':'source_revision','qualification_floor':'floor_id','qualification_not_qualified':'qualified'}[change]]={'qualification_revision':'wrong','qualification_floor':'2F','qualification_not_qualified':False}[change]
            qualification.write_text(json.dumps(q));plan['paths']['qualification']=str(qualification)
            plan['sha256']['qualification']=hashlib.sha256(qualification.read_bytes()).hexdigest()
        plan_path.write_text(json.dumps(plan));process['preparation_sha256']=worker['preparation_sha256']=hashlib.sha256(plan_path.read_bytes()).hexdigest()
    path=original(process['worker_path']);path.parent.mkdir(exist_ok=True);path.write_text(json.dumps(worker))
    if doc is None:doc=dict(source_revision=revision,floors={f:dict(state='queued',accepted_preview=None,candidate_preview={'old':'inspection-only'},validation={'verdict':'FAIL'}) for f in ['1F','2F','3F','4F','5F','6F','7F']})
    upper=mapped('D:/PROJECTS/UC MODEL FIXER/.claude/worktrees/MAIN-INFRA-CLAUDE-4F-7F-20261023/data/main-infra-fresh/current-upper.json')
    upper.parent.mkdir(parents=True,exist_ok=True);upper.write_text(json.dumps(dict(source_revision=doc['source_revision'],job_id='MAIN-INFRA-CLAUDE-4F-7F-20261023',run_id='upper',updated_at='now',floors={f:dict(state='queued',step='waiting') for f in ['4F','5F','6F','7F']})))
    written=[];progress=SimpleNamespace(load_progress=lambda _:doc,write_progress=lambda _,value:written.append(value),utc_now=lambda:now)
    monkeypatch.setitem(sys.modules,'tools.main_infra_progress',progress);monkeypatch.setitem(sys.modules,'pathlib',SimpleNamespace(Path=mapped));monkeypatch.setattr(sys,'path',list(sys.path))
    observations={'3F':process}
    if finished_1f:
        old_path=E3_1F+'/data/main-infra-e3/run-20261024-1F-retain-visible/execution-1F/worker.json'
        local=mapped(old_path);local.parent.mkdir(parents=True,exist_ok=True)
        local.write_text(json.dumps(dict(pid=40476,floor='1F',run_id='MAIN-INFRA-E3-1F-retain-visible-20261024',state='candidate_saved',output_triangles=10410)))
        observations['1F']=dict(engine='E3',alive=False,worker_path=old_path,expected_pid=40476,expected_start='2026-10-23T21:15:39.9150019Z')
    monkeypatch.setenv('UC_MODEL_WORKER_OBSERVATIONS',json.dumps(observations));monkeypatch.setenv('UC_MODEL_VALIDATOR_OBSERVATIONS',json.dumps(validator or {}))
    exec(compile(code,str(RUNTIME),'exec'),{})
    assert written==[doc]
    return doc


@pytest.mark.parametrize('phase',['checking','checked_checkpoint_saved','serializing','finalizing'])
def test_actual_common3f_states_are_active_and_preserve_prior_failed_inspection(tmp_path,monkeypatch,phase):
    doc=update(tmp_path,monkeypatch,phase=phase)
    row=doc['floors']['3F']
    assert doc['state']=='running' and row['state']=='cleaning' and row['worker_alive'] is True
    assert row['engine_stage']=='E3' and phase==row['worker_events'][-1]['phase']
    assert 'displayed candidate remains inspection-only' in row['step']
    assert row['candidate_preview']=={'old':'inspection-only'} and row['validation']=={'verdict':'FAIL'} and row['accepted_preview'] is None
    assert row['worker_cpu_samples'][-1]['cpu_seconds']==3


def test_common3f_saved_is_pending_and_dead_checking_is_failure_never_pass(tmp_path,monkeypatch):
    saved=update(tmp_path,monkeypatch,phase='candidate_saved',alive=False)
    assert saved['floors']['3F']['state']=='validating' and saved['floors']['3F']['pending_output_triangles']==44972
    dead=update(tmp_path,monkeypatch,alive=False)
    assert dead['floors']['3F']['state']=='failed' and dead['floors']['3F']['accepted_preview'] is None


@pytest.mark.parametrize('change',['run','floor','pid','start','path','P_hash','worker_P','component','source'])
def test_common3f_refuses_wrong_exact_lifetime_or_proof_binding(tmp_path,monkeypatch,change):
    with pytest.raises(ValueError):update(tmp_path,monkeypatch,change=change)


@pytest.mark.parametrize('phase,want',[('loading_qualified_input','cleaning'),('running_checked_E3','cleaning'),('candidate_saved','validating'),('failed','failed')])
def test_legacy3f_worker_schema_remains_supported(tmp_path,monkeypatch,phase,want):
    assert update(tmp_path,monkeypatch,phase=phase,legacy=True)['floors']['3F']['state']==want


def test_common_history_deduplicates_heartbeat_and_keeps_hundred_samples(tmp_path,monkeypatch):
    doc=update(tmp_path,monkeypatch);row=doc['floors']['3F'];first=row['last_work_event_at']
    doc=update(tmp_path,monkeypatch,doc=doc,now='2026-10-23T22:45:10Z',cpu=4)
    doc=update(tmp_path,monkeypatch,doc=doc,now='2026-10-23T22:45:30Z',cpu=5)
    assert len(row['worker_events'])==1 and [r['cpu_seconds'] for r in row['worker_cpu_samples']]==[3,5] and row['last_work_event_at']==first
    row['worker_events']=[dict(row['worker_events'][0],phase=str(i)) for i in range(100)]
    row['worker_cpu_samples']=[dict(row['worker_cpu_samples'][-1],cpu_seconds=i) for i in range(100)]
    update(tmp_path,monkeypatch,doc=doc,phase='serializing',now='2026-10-23T22:46:00Z',cpu=101)
    assert len(row['worker_events'])==len(row['worker_cpu_samples'])==100


def validator_process(**changes):
    value=dict(alive=True,pid=25704,expected_pid=25704,start='2026-10-23T22:20:00.1234567Z',expected_start='2026-10-23T22:20:00.1234567Z',run_id='independent1F',phase='full_signed',cpu=23)
    value.update(changes);return value


def validator_doc():
    doc=dict(source_revision='fresh',floors={f:dict(state='queued',accepted_preview=None) for f in ['1F','2F','3F','4F','5F','6F','7F']})
    doc['floors']['1F'].update(state='validating',step='Actual full signed check running',worker_pid=25704,worker_start_utc='2026-10-23T22:20:00.1234567Z',validation={'verdict':'FAIL'},blocker='prior native failure')
    return doc


def test_bound_validator_observations_are_visible_without_changing_verdict_or_floor_state(tmp_path,monkeypatch):
    doc=validator_doc();before=copy.deepcopy(doc['floors']['1F'])
    result=update(tmp_path,monkeypatch,doc=doc,validator={'1F':validator_process()})['floors']['1F']
    for key in ('state','step','validation','blocker','accepted_preview'):assert result[key]==before[key]
    assert result['worker_alive'] is True and result['worker_cpu_seconds']==23
    assert result['worker_observed_at']=='2026-10-23T22:45:00Z'
    assert result['worker_events'][-1]['phase']=='independent_validation:full_signed'
    assert result['worker_cpu_samples'][-1]['cpu_seconds']==23 and 'percent' not in result['worker_events'][-1]


def test_validator_must_not_overwrite_another_active_engine_binding(tmp_path,monkeypatch):
    doc=validator_doc();doc['floors']['1F'].update(worker_pid=40476,worker_start_utc=START,worker_alive=True,worker_cpu_seconds=8)
    row=update(tmp_path,monkeypatch,doc=doc,validator={'1F':validator_process()})['floors']['1F']
    assert row['worker_pid']==40476 and row['worker_cpu_seconds']==8 and row['validator_cpu_seconds']==23
    assert 'worker_events' not in row


@pytest.mark.parametrize('change',[{'pid':999},{'start':'2026-10-23T22:20:00.1234568Z'},{'phase':''}])
def test_wrong_validator_lifetime_or_phase_refuses(tmp_path,monkeypatch,change):
    with pytest.raises(ValueError):update(tmp_path,monkeypatch,doc=validator_doc(),validator={'1F':validator_process(**change)})


def test_validator_heartbeat_deduplicates_and_dead_observation_never_marks_pass(tmp_path,monkeypatch):
    doc=validator_doc();update(tmp_path,monkeypatch,doc=doc,validator={'1F':validator_process()})
    update(tmp_path,monkeypatch,doc=doc,validator={'1F':validator_process(cpu=24)},now='2026-10-23T22:45:10Z')
    update(tmp_path,monkeypatch,doc=doc,validator={'1F':validator_process(cpu=25)},now='2026-10-23T22:45:30Z')
    row=doc['floors']['1F'];assert len(row['worker_events'])==1 and [s['cpu_seconds'] for s in row['worker_cpu_samples']]==[23,25]
    update(tmp_path,monkeypatch,doc=doc,validator={'1F':validator_process(alive=False)},now='2026-10-23T22:46:00Z')
    assert row['worker_alive'] is False and row['state']=='validating' and row['validation']=={'verdict':'FAIL'}


def test_finished_engine_cannot_hide_the_already_bound_validator(tmp_path,monkeypatch):
    doc=validator_doc();before=copy.deepcopy(doc['floors']['1F'])
    row=update(tmp_path,monkeypatch,doc=doc,validator={'1F':validator_process()},finished_1f=True)['floors']['1F']
    assert row['worker_pid']==25704 and row['worker_cpu_seconds']==23
    assert row['step']==before['step'] and row['state']==before['state'] and row['validation']==before['validation']
    assert row['worker_events'][-1]['phase']=='independent_validation:full_signed'

@pytest.mark.parametrize('start',[None,'invalid','2026-10-23T22:20:00.1234568Z'])
def test_unbound_canonical_start_keeps_validator_audit_only(tmp_path,monkeypatch,start):
    doc=validator_doc();doc['floors']['1F']['worker_start_utc']=start
    row=update(tmp_path,monkeypatch,doc=doc,validator={'1F':validator_process()})['floors']['1F']
    assert row['validator_cpu_seconds']==23 and 'worker_cpu_seconds' not in row and 'worker_events' not in row

def test_genuine_retained_preparation_schema_uses_qualified_revision_anchor(tmp_path,monkeypatch):
    row=update(tmp_path,monkeypatch,retained_schema=True)['floors']['3F']
    assert row['state']=='cleaning' and row['worker_pid']==60376


@pytest.mark.parametrize('change',['qualification_hash','qualification_revision','qualification_floor','qualification_not_qualified'])
def test_even_rehashed_preparation_cannot_change_the_qualified_source_anchor(tmp_path,monkeypatch,change):
    with pytest.raises(ValueError):update(tmp_path,monkeypatch,retained_schema=True,change=change)
