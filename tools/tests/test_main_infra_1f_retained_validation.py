"""Corrected1F profile fixtures; actual heavy phases are not executed."""
import json
from pathlib import Path
import pytest
from tools import main_infra_2f_validation as shared

PROFILE='e3_1f_retain_visible_20261024'
NATIVE=Path('D:/LLM_BACKUP/Codex session/main-infra-1f-validation-attempt4-20261024/05-Corllenium-UC-Building-Repair-Engine/data/main-infra-1f-validation/run-20261024-attempt4/1F/native-poses.json')
QUAL=Path('D:/PROJECTS/UC MODEL FIXER/.claude/worktrees/MAIN-INFRA-CLEAN-20261023/data/main-infra-fresh/run-20261023/independent-validator/import-audit/qualification-1F.json')

def test_explicit_corrected_profile_preserves_original_triangle_count():
    assert shared.floor_size('1F',profile=PROFILE)==15856
    assert shared.floor_size('2F')==56828 and shared.floor_size('3F')==53602

@pytest.mark.parametrize('floor,profile',[('1F',None),('1F','old'),('2F',PROFILE),('4F',PROFILE)])
def test_profile_cannot_relabel_other_floor(floor,profile):
    with pytest.raises(ValueError,match='profile'):shared.floor_size(floor,profile=profile)

def test_actual_historical_1f_qualification_without_job_id_remains_bound():
    proof=json.loads(QUAL.read_bytes())
    assert 'job_id' not in proof
    shared.require_qualification(proof,'1F',profile=PROFILE)
    for key in ['qualified','floor_id','source_revision']:
        wrong=dict(proof);wrong[key]=None
        with pytest.raises(ValueError):shared.require_qualification(wrong,'1F',profile=PROFILE)

@pytest.mark.parametrize('job',[None,'','foreign'])
def test_present_wrong_historical_qualification_job_is_rejected(job):
    proof=json.loads(QUAL.read_bytes());proof['job_id']=job
    with pytest.raises(ValueError):shared.require_qualification(proof,'1F',profile=PROFILE)

def test_actual_1f_native_cohort_has_33qualified_and13diagnostic():
    poses=json.loads(NATIVE.read_bytes())['poses']
    assert shared.native_pose_inventory(poses,'1F',profile=PROFILE)==dict(qualified_walking=16,qualified_outside=17,diagnostic=13)

@pytest.mark.parametrize('change',['missing','duplicate','eye_height','headroom','outside_projection'])
def test_retained_1f_native_cohort_rejects_drift(change):
    poses=json.loads(NATIVE.read_bytes())['poses']
    walking=next(p for p in poses if p['name'].startswith('eye_0_qualified'))
    if change=='missing':poses.pop()
    elif change=='duplicate':poses[-1]['name']=poses[0]['name']
    elif change=='eye_height':walking['eye_height_above_floor_metres']=.6
    elif change=='headroom':walking['headroom_clear']=False
    elif change=='outside_projection':next(p for p in poses if p.get('viewpoint_class')=='qualified_outside')['projection']='PERSP'
    with pytest.raises(ValueError):shared.native_pose_inventory(poses,'1F',profile=PROFILE)

