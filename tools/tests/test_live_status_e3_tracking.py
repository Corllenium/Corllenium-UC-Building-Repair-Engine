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


def execute_updater(tmp_path,monkeypatch,*,state='checking',engine='E3',alive=True,change=None):
    source=RUNTIME.read_text(encoding='utf-8-sig')
    code=re.search(r"(?ms)\$taskPython=@'\r?\n(.*?)\r?\n'@",source).group(1)
    original_path=Path
    def mapped(value):
        text=str(value).replace('\\','/')
        for external,local in [('D:/PROJECTS/UC MODEL FIXER',tmp_path/'main'),(E3_ROOT,tmp_path/'e3')]:
            if text==external or text.startswith(external+'/'):
                return local/text[len(external):].lstrip('/')
        return original_path(value)
    row=dict(pid=40476,floor='1F',run_id=E3_RUN,state=state,output_triangles=42)
    worker=E3_WORKER if engine=='E3' else str(tmp_path/'e7-worker.json')
    if change=='run':row['run_id']='wrong'
    if change=='floor':row['floor']='2F'
    if change=='path':worker=E3_ROOT+'/data/wrong-worker.json'
    path=mapped(worker);path.parent.mkdir(parents=True,exist_ok=True);path.write_text(json.dumps(row))
    process=dict(alive=alive,worker_path=worker,cpu=1,start='actual-start')
    if engine is not None:process['engine']=engine
    doc=dict(source_revision='fresh',floors={f:dict(state='queued',accepted_preview=None) for f in ['1F','2F','3F','4F','5F','6F','7F']})
    upper=mapped('D:/PROJECTS/UC MODEL FIXER/.claude/worktrees/MAIN-INFRA-CLAUDE-4F-7F-20261023/data/main-infra-fresh/current-upper.json')
    upper.parent.mkdir(parents=True);upper.write_text(json.dumps(dict(source_revision='fresh',job_id='MAIN-INFRA-CLAUDE-4F-7F-20261023',run_id='upper',updated_at='now',floors={f:dict(state='queued',step='waiting') for f in ['4F','5F','6F','7F']})))
    written=[]
    progress=SimpleNamespace(load_progress=lambda _:doc,write_progress=lambda _,value:written.append(value),utc_now=lambda:'now')
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


@pytest.mark.parametrize('change',['run','floor','path'])
def test_e3_registration_rejects_wrong_run_or_worker_binding(tmp_path,monkeypatch,change):
    with pytest.raises(ValueError,match='E3.*(identity|binding)'):
        execute_updater(tmp_path,monkeypatch,change=change)


def test_unknown_registered_engine_is_rejected(tmp_path,monkeypatch):
    with pytest.raises(ValueError,match='engine'):
        execute_updater(tmp_path,monkeypatch,engine='unknown')
