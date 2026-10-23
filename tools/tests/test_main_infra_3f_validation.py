"""Identity/profile fixtures; no model or oracle is executed."""
import json
from pathlib import Path
import pytest
from tools.tests.test_main_infra_2f_validation import bound as old_bound,write,digest
from tools import main_infra_2f_validation as shared

@pytest.fixture
def three(tmp_path):
    prep,old,old_worker,audit,worker,plan=old_bound.__wrapped__(tmp_path)
    candidate=old.with_name('3F');old.rename(candidate)
    snap=Path(audit['before_snapshot']);snap.parent.rename(snap.parent.with_name('3F'))
    snapshot=snap.parent.with_name('3F')/snap.name
    target_worker=old_worker.with_name('worker-3F.json');old_worker.unlink()
    worker.update(pid=22268,floor_id='3F',input_triangles=53602,output_triangles=38691,candidate=str(candidate))
    audit.update(input_triangles=53602,output_triangles=38691,before_snapshot=str(snapshot))
    audit['input_receipt']['floor_id']='3F'
    terminal=tmp_path/'terminal.json';phase=tmp_path/'phase.json';write(phase,{'phase':'E3-3F-attempt2'})
    creation='2026-10-23T17:36:13.8205790Z'
    exit_record=dict(state='PROCESS_EXITED_ZERO',phase='E3-3F-attempt2',abort_reason=None,actual_pid=22268,
        actual_creation_utc=creation,actual_exit_code=0,launcher_exit_code=0,HEAD=shared.COMPONENT,
        phase_plan_sha256=digest(phase),all_owned_exited=True,acceptance=False)
    write(terminal,exit_record)
    plan.update(floor_id='3F',worker_pid=22268,worker=str(target_worker),candidate=str(candidate),
        before_snapshot_root=str(snapshot.parent),worker_creation_utc=creation)
    plan['paths'].update(worker_terminal=str(terminal),worker_phase_plan=str(phase))
    plan['sha256'].update(worker_terminal=digest(terminal),worker_phase_plan=digest(phase))
    write(prep,plan);write(target_worker,worker);write(candidate/'stage-audit.json',audit)
    return prep,candidate,target_worker,audit,worker,plan,terminal,exit_record

def bind(case,**kw):
    return shared.bind_identity(case[0],case[1],digest(case[1]/'stage-audit.json'),digest(case[2]),**kw)

def test_default_2f_contract_is_unchanged(tmp_path):
    case=old_bound.__wrapped__(tmp_path);receipt=bind(case)
    assert receipt['floor_id']=='2F' and receipt['input_triangles']==56828

def test_saved_3f_profile_binds_original_and_terminal(three):
    receipt=bind(three,floor_id='3F')
    assert receipt['floor_id']=='3F' and receipt['input_triangles']==53602 and receipt['output_triangles']==38691
    assert receipt['hashes']['worker_terminal']==digest(three[6]) and receipt['acceptance'] is False

@pytest.mark.parametrize('floor',['1F','4F','unknown'])
def test_only_explicit_2f3f_profiles_are_permitted(three,floor):
    with pytest.raises(ValueError,match='profile'):bind(three,floor_id=floor)

@pytest.mark.parametrize('field,value',[('floor_id','2F'),('input_triangles',56828),('output_triangles',38690)])
def test_3f_rejects_foreign_worker(three,field,value):
    three[4][field]=value;write(three[2],three[4])
    with pytest.raises(ValueError):bind(three,floor_id='3F')

@pytest.mark.parametrize('field,value',[('state','RUNNING'),('phase','E3-2F-attempt2'),('actual_pid',41648),
    ('actual_creation_utc','old'),('actual_exit_code',2),('launcher_exit_code',2),('abort_reason','failure'),
    ('HEAD','old'),('all_owned_exited',False),('acceptance',True),('phase_plan_sha256','0'*64)])
def test_3f_requires_actual_successful_owned_terminal(three,field,value):
    three[7][field]=value;write(three[6],three[7]);three[5]['sha256']['worker_terminal']=digest(three[6]);write(three[0],three[5])
    with pytest.raises(ValueError,match='terminal'):bind(three,floor_id='3F')

def test_3f_entrypoint_help_launches_nothing(capsys):
    from tools.main_infra_3f_validation import main
    with pytest.raises(SystemExit) as info:main(['--help'])
    help_text=capsys.readouterr().out
    assert info.value.code==0 and '--guard-sha256' in help_text and 'Independent 3F' in help_text


def actual_3f_poses():
    path=Path('D:/PROJECTS/UC MODEL FIXER/.claude/worktrees/MAIN-INFRA-E3-20261023/data/main-infra-e3/run-20261023/independent-validator/import-2F3F-audit/3F/native-poses.json')
    return json.loads(path.read_bytes())['poses']

def test_retained_3f_native_cohort_has33qualified_and13diagnostic():
    assert shared.native_pose_inventory(actual_3f_poses(),'3F')==dict(qualified_walking=16,qualified_outside=17,diagnostic=13)

@pytest.mark.parametrize('change',['missing','duplicate','walking_relabel','outside_projection'])
def test_3f_native_cohort_drift_is_refused(change):
    poses=actual_3f_poses()
    if change=='missing':poses.pop()
    if change=='duplicate':poses[-1]['name']=poses[0]['name']
    if change=='walking_relabel':next(p for p in poses if p.get('viewpoint_class')=='actual_unchanged_qualified_walking_probe')['viewpoint_class']='diagnostic'
    if change=='outside_projection':next(p for p in poses if p['name']=='view_0_0_1')['projection']='PERSP'
    with pytest.raises(ValueError,match='native|cohort'):shared.native_pose_inventory(poses,'3F')


def test_actual_saved_3f_manifest_is_bound_without_loading_geometry():
    prep=Path(__file__).resolve().parents[2]/'docs/superpowers/records/MAIN-INFRA-3F-VALIDATE-ATTEMPT2-20261024/preparation.json'
    plan=json.loads(prep.read_bytes());candidate=Path(plan['candidate'])
    receipt=shared.bind_identity(prep,candidate,plan['audit_sha256'],plan['worker_sha256'],floor_id='3F')
    assert receipt['worker_pid']==22268 and receipt['input_triangles']==53602 and receipt['output_triangles']==38691
    assert receipt['after_sha256']=='c3664f9e796c5c63cdcdcd1ba36be6996e07bee2727a908204ec08cbc37ed09d'
    assert receipt['source_after_sha256']=='a910864443ea698855836b9f725664d2a9e86f9b11270b503515eaacc9ad907a'
    assert receipt['hashes']['worker_terminal']=='e0cb3afbacc60e37e58c9199b57236cf2af724357b8b66d0129ce6e9cf51f363'
