import json
import re
import sys
from pathlib import Path
from types import SimpleNamespace

import pytest

RUNTIME=Path(__file__).resolve().parents[2]/'docs/superpowers/records/scripts/main-infra/live-worker-status-runtime.ps1'
E3_ROOT='D:/LLM_BACKUP/Codex session/main-infra-e3-1f-retain-visible-20261024/05-Corllenium-UC-Building-Repair-Engine'
E3_WORKER=E3_ROOT+'/data/main-infra-e3/run-20261024-1F-retain-visible/execution-1F/worker.json'
E3_RUN='MAIN-INFRA-E3-1F-retain-visible-20261024'


def execute_updater(tmp_path,monkeypatch,*,state='checking',engine='E3',alive=True,change=None,doc=None,now='2026-10-23T21:30:00Z',cpu=1,pid=40476,start='2026-10-23T21:15:39.9150019Z',worker_fields=None):
    source=RUNTIME.read_text(encoding='utf-8-sig')
    code=re.search(r"(?ms)\$taskPython=@'\r?\n(.*?)\r?\n'@",source).group(1)
    original_path=Path
    def mapped(value):
        text=str(value).replace('\\','/')
        for external,local in [('D:/PROJECTS/UC MODEL FIXER',tmp_path/'main'),(E3_ROOT,tmp_path/'e3')]:
            if text==external or text.startswith(external+'/'):
                return local/text[len(external):].lstrip('/')
        return original_path(value)
    row=dict(pid=pid,floor='1F',run_id=E3_RUN,state=state,output_triangles=42)
    row.update(worker_fields or {})
    worker=E3_WORKER if engine=='E3' else str(tmp_path/'e7-worker.json')
    if change=='run':row['run_id']='wrong'
    if change=='floor':row['floor']='2F'
    if change=='path':worker=E3_ROOT+'/data/wrong-worker.json'
    if change=='pid':row['pid']=999
    path=mapped(worker);path.parent.mkdir(parents=True,exist_ok=True);path.write_text(json.dumps(row))
    process=dict(alive=alive,worker_path=worker,cpu=cpu,start=start,expected_pid=pid,expected_start=start)
    if change=='start':process['start']='2026-10-23T22:15:39Z'
    if engine is not None:process['engine']=engine
    if doc is None:doc=dict(source_revision='fresh',floors={f:dict(state='queued',accepted_preview=None) for f in ['1F','2F','3F','4F','5F','6F','7F']})
    upper=mapped('D:/PROJECTS/UC MODEL FIXER/.claude/worktrees/MAIN-INFRA-CLAUDE-4F-7F-20261023/data/main-infra-fresh/current-upper.json')
    upper.parent.mkdir(parents=True,exist_ok=True);upper.write_text(json.dumps(dict(source_revision='fresh',job_id='MAIN-INFRA-CLAUDE-4F-7F-20261023',run_id='upper',updated_at='now',floors={f:dict(state='queued',step='waiting') for f in ['4F','5F','6F','7F']})))
    written=[]
    progress=SimpleNamespace(load_progress=lambda _:doc,write_progress=lambda _,value:written.append(value),utc_now=lambda:now)
    monkeypatch.setitem(sys.modules,'tools.main_infra_progress',progress)
    monkeypatch.setitem(sys.modules,'pathlib',SimpleNamespace(Path=mapped))
    monkeypatch.setattr(sys,'path',list(sys.path))
    monkeypatch.setenv('UC_MODEL_WORKER_OBSERVATIONS',json.dumps({'1F':process}))
    exec(compile(code,str(RUNTIME),'exec'),{})
    assert written==[doc]
    return doc


@pytest.mark.parametrize('state',['checking','checked_checkpoint_saved','serializing','finalizing'])
def test_registered_e3_worker_is_running_with_truthful_stage(tmp_path,monkeypatch,state):
    doc=execute_updater(tmp_path,monkeypatch,state=state)
    row=doc['floors']['1F']
    assert doc['state']=='running' and row['state']=='cleaning'
    assert row['engine_stage']=='E3' and 'E3' in row['step'] and 'E7' not in row['step']
    assert '1F' in doc['step'] and row['worker_pid']==40476 and row['accepted_preview'] is None


def test_registered_e3_saved_candidate_is_pending_review(tmp_path,monkeypatch):
    doc=execute_updater(tmp_path,monkeypatch,state='candidate_saved',alive=False)
    row=doc['floors']['1F']
    assert doc['state']=='reviewing' and row['state']=='validating'
    assert row['engine_stage']=='E3' and 'E3' in row['step'] and 'E7' not in row['step']
    assert row['pending_output_triangles']==42 and row['accepted_preview'] is None


@pytest.mark.parametrize('engine',[None,'E7'])
@pytest.mark.parametrize('state',['checking','checked_checkpoint_saved','serializing','candidate_saved'])
def test_existing_e7_registration_keeps_backward_default(tmp_path,monkeypatch,engine,state):
    doc=execute_updater(tmp_path,monkeypatch,state=state,engine=engine)
    row=doc['floors']['1F']
    assert row['engine_stage']=='E7' and 'E7' in row['step']
    assert doc['state']==('reviewing' if state=='candidate_saved' else 'running')


@pytest.mark.parametrize('change',['run','floor','path','pid','start'])
def test_e3_registration_rejects_wrong_run_or_worker_binding(tmp_path,monkeypatch,change):
    with pytest.raises(ValueError,match='E3.*(identity|binding)'):
        execute_updater(tmp_path,monkeypatch,change=change)


def test_unknown_registered_engine_is_rejected(tmp_path,monkeypatch):
    with pytest.raises(ValueError,match='engine'):
        execute_updater(tmp_path,monkeypatch,engine='unknown')


def test_heartbeats_do_not_duplicate_phase_events_or_work_timestamp(tmp_path,monkeypatch):
    doc=execute_updater(tmp_path,monkeypatch)
    first=doc['floors']['1F']['last_work_event_at']
    doc=execute_updater(tmp_path,monkeypatch,doc=doc,now='2026-10-23T21:30:10Z',cpu=2)
    doc=execute_updater(tmp_path,monkeypatch,doc=doc,now='2026-10-23T21:30:30Z',cpu=3)
    row=doc['floors']['1F']
    assert len(row['worker_events'])==1
    assert [s['cpu_seconds'] for s in row['worker_cpu_samples']]==[1,3]
    assert row['last_work_event_at']==first and doc['heartbeat_at']=='2026-10-23T21:30:30Z'
    event=row['worker_events'][0]
    assert (event['engine'],event['run_id'],event['pid'],event['start_utc'],event['phase'])==('E3',E3_RUN,40476,'2026-10-23T21:15:39.9150019Z','checking')
    assert 'percent' not in event and 'eta' not in event and 'kept_edits' not in event


def test_actual_worker_phase_changes_record_available_counts(tmp_path,monkeypatch):
    doc=execute_updater(tmp_path,monkeypatch)
    for index,state in enumerate(['checked_checkpoint_saved','serializing','candidate_saved'],1):
        doc=execute_updater(tmp_path,monkeypatch,doc=doc,state=state,alive=state!='candidate_saved',now=f'2026-10-23T21:3{index}:00Z',cpu=index+1,worker_fields={'kept_edits':2,'rolled_back_edits':1})
    row=doc['floors']['1F']
    assert [e['phase'] for e in row['worker_events']]==['checking','checked_checkpoint_saved','serializing','candidate_saved']
    assert row['worker_events'][-1]['kept_edits']==2 and row['worker_events'][-1]['rolled_back_edits']==1
    assert row['worker_events'][-1]['output_triangles']==42 and row['accepted_preview'] is None
    assert len(row['worker_cpu_samples'])==3
    assert all(doc['floors'][f].get('worker_events') is None for f in ['2F','3F','4F','5F','6F','7F'])


def test_phase_and_cpu_histories_keep_latest_hundred_only(tmp_path,monkeypatch):
    doc=execute_updater(tmp_path,monkeypatch)
    row=doc['floors']['1F'];event=row['worker_events'][0];sample=row['worker_cpu_samples'][0]
    row['worker_events']=[dict(event,phase=f'prior-{i}') for i in range(100)]
    row['worker_cpu_samples']=[dict(sample,cpu_seconds=i) for i in range(100)]
    doc=execute_updater(tmp_path,monkeypatch,doc=doc,state='serializing',now='2026-10-23T21:31:00Z',cpu=100)
    row=doc['floors']['1F']
    assert len(row['worker_events'])==len(row['worker_cpu_samples'])==100
    assert row['worker_events'][0]['phase']=='prior-1' and row['worker_events'][-1]['phase']=='serializing'
    assert row['worker_cpu_samples'][0]['cpu_seconds']==1 and row['worker_cpu_samples'][-1]['cpu_seconds']==100


def test_same_phase_new_bound_lifetime_is_separate_actual_event(tmp_path,monkeypatch):
    doc=execute_updater(tmp_path,monkeypatch)
    doc=execute_updater(tmp_path,monkeypatch,doc=doc,pid=40477,start='2026-10-23T21:30:01Z',now='2026-10-23T21:30:05Z')
    row=doc['floors']['1F']
    assert [e['pid'] for e in row['worker_events']]==[40476,40477]
    assert [e['pid'] for e in row['worker_cpu_samples']]==[40476,40477]


def test_missing_cpu_creates_no_sample_and_e7_creates_no_new_history(tmp_path,monkeypatch):
    doc=execute_updater(tmp_path,monkeypatch,cpu=None)
    assert doc['floors']['1F']['worker_cpu_samples']==[]
    e7=execute_updater(tmp_path,monkeypatch,engine=None)
    assert 'worker_events' not in e7['floors']['1F'] and 'worker_cpu_samples' not in e7['floors']['1F']
