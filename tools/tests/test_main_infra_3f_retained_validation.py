"""Corrected3F proof profile controls; these tests do not cast floor rays."""
import pytest
from tools import main_infra_2f_validation as shared

PROFILE='e3_3f_retain_visible_20261024'


def test_corrected_3f_profile_uses_original53602_and_preserves_existing_profiles():
    assert shared.floor_size('3F',profile=PROFILE)==53602
    assert shared.floor_size('1F',profile=shared.RETAINED_1F)==15856
    assert shared.floor_size('2F')==56828
    assert shared.floor_size('3F')==53602


@pytest.mark.parametrize('floor',["1F","2F","4F"])
def test_corrected3f_profile_cannot_relabel_another_floor(floor):
    with pytest.raises(ValueError): shared.floor_size(floor,profile=PROFILE)

from pathlib import Path
import json

BUILDER=Path('D:/LLM_BACKUP/Codex session/main-infra-e3-3f-retain-visible-20261024/05-Corllenium-UC-Building-Repair-Engine')
ACTUAL_P=BUILDER/'data/main-infra-e3/attempt2/run-20261024-3F-retain-visible/preparation-3F.json'


def actual_cohort():
    p=json.loads(ACTUAL_P.read_bytes())
    policy=json.loads(Path(p['policy']['path']).read_bytes())
    old=Path(policy['original_audit']['path']).parent
    rows=[json.loads(row) for row in (old/'edit-log.jsonl').read_text().splitlines()][:-1]
    return p,policy,rows


def test_actual_new3f_cohort_binds_all263whole_sites_and145_old_rollbacks():
    from tools.main_infra_3f_retained_validation import require_cohort
    p,policy,rows=actual_cohort()
    result=require_cohort(p,policy,rows)
    assert result['selected']==1412 and len(result['restored_sites'])==263
    assert len(result['retained_faces'])==6281 and len(result['old_rolled_sites'])==145
    assert len(result['old_rolled_faces'])>0
    assert result['required_faces']==[897,1318,1323,4311,7760,13602,22979,26120,29747]


@pytest.mark.parametrize('change',['omitted_old_rollback','missing_restored_face','selected_restored_site','selected_order',
    'wrong_required_face','old_pass_reused','wrong_original_counts','incomplete_native_sites','incomplete_extra_sites',
    'wrong_selected_count','missing_replay_site','nonempty_signed_failures'])
def test_rehashed_cohort_metadata_cannot_change_actual3f_retention(change):
    from tools.main_infra_3f_retained_validation import require_cohort
    p,policy,rows=actual_cohort();s=p['selection']
    if change=='omitted_old_rollback':s['original_rolled_sites'].pop()
    elif change=='missing_restored_face':s['retained_source_faces'].pop()
    elif change=='selected_restored_site':s['selected_sites'][0]=policy['restore_sites'][0]
    elif change=='selected_order':s['selected_sites'][:2]=reversed(s['selected_sites'][:2])
    elif change=='wrong_required_face':s['required_faces'][0]=9809
    elif change=='old_pass_reused':s['old_verdict_is_not_reused']=False
    elif change=='wrong_original_counts':s['original_counts']['rolled_back']=144
    elif change=='incomplete_native_sites':s['native_restored_sites'].pop()
    elif change=='incomplete_extra_sites':s['nonfailing_subthreshold_restored_sites'].pop()
    elif change=='wrong_selected_count':s['selected']=1413
    elif change=='missing_replay_site':s['replay']['restored_sites'].pop()
    elif change=='nonempty_signed_failures':s['signed_preservation_failure_sites']=[5]
    with pytest.raises(ValueError):require_cohort(p,policy,rows)


def test_generic_checkpoint_helpers_are_reused_without_a_new_reader():
    from tools import main_infra_3f_retained_validation as three, main_infra_1f_retained_validation as one
    assert three.bind_package is one.bind_package
    assert three.read_checked_capture is one.read_checked_capture
    assert three.require_retained_mesh is one.require_retained_mesh


def actual_binding(tmp_path):
    p,policy,_rows=actual_cohort();candidate=Path(p['out'])
    worker=candidate.parent/'execution-3F/worker.json';w=json.loads(worker.read_bytes())
    audit=candidate/'stage-audit.json';a=json.loads(audit.read_bytes())
    ops=BUILDER/'data/main-infra-e3/3f-retain-visible-preflight-attempt2'
    terminal=ops/'monitor-e3-3F-retain-visible-execute-attempt2-20261023T224354/result.json'
    phase=ops/'phase-execute.json'
    paths={key:Path(p['paths'][name]) for key,name in [('raw','raw'),('reference','reference'),
        ('engine_baseline','baseline_engine'),('source_baseline','baseline_source'),
        ('provenance','provenance'),('qualification','qualification'),('materials','materials')]}
    paths.update(builder_preparation=ACTUAL_P,retention_policy=Path(p['policy']['path']),
        checkpoint_receipt=Path(w['checkpoint'])/'checkpoint-receipt.json',worker_terminal=terminal,worker_phase_plan=phase)
    plan=dict(schema_version=1,job_id=shared.JOB,floor_id='3F',source_revision=shared.REV,
        validation_profile=PROFILE,attempt_namespace='run-20261024-3F-retain-visible',
        builder_component_commit='c125cd8ab28fe648491676125e8bc8e67d1c5c3a',builder_root=str(BUILDER),
        worker_pid=60376,worker_started_at=w['started_utc'],worker_creation_utc='2026-10-23T22:43:56.2456960Z',
        worker_terminal_phase='e3-3F-retain-visible-execute-attempt2',worker=str(worker),candidate=str(candidate),
        before_snapshot_root=str(Path(a['before_snapshot']).parent),paths={k:str(v) for k,v in paths.items()},
        sha256={k:shared.digest(v) for k,v in paths.items()})
    prep=tmp_path/'independent-preparation.json';shared.write(prep,plan)
    return prep,plan,candidate,worker,audit


def bind_actual(case,sha=None):
    prep,_plan,candidate,worker,audit=case
    return shared.bind_identity(prep,candidate,shared.digest(audit),shared.digest(worker),
        floor_id='3F',profile=PROFILE,preparation_sha256=sha or shared.digest(prep))


def test_actual_44972_package_has_fresh_typed_capture_and_creation_distinct_from_kernel_start(tmp_path):
    receipt=bind_actual(actual_binding(tmp_path))
    assert receipt['input_triangles']==53602 and receipt['output_triangles']==44972
    assert receipt['worker_pid']==60376 and receipt['reviewer']=='/root/main_infra_independent_validator'
    assert receipt['after_sha256']=='d51863ee389e02f186b37f488d76fc2b2f500ea8059a27273d5f8118c5b655c3'
    assert receipt['source_after_sha256']=='7b8a2f0dc74ec546d1ae389b50dc2b9ba4a555870150aae33a00a6a81a674a1c'
    assert receipt['hashes']['checkpoint_receipt'].startswith('0686c0d3')
    assert receipt['acceptance'] is False
    shared.recheck(receipt)


@pytest.mark.parametrize('change',['old_namespace','wrong_creation','kernel_time_as_creation','external_preparation','old_checkpoint'])
def test_actual_corrected3f_binding_refuses_other_lifetime_or_old_proof(tmp_path,change):
    case=actual_binding(tmp_path);prep,plan,_candidate,_worker,_audit=case
    if change=='old_namespace':plan['attempt_namespace']='run-20261023-attempt2'
    elif change=='wrong_creation':plan['worker_creation_utc']='2026-10-23T22:43:56.2456961Z'
    elif change=='kernel_time_as_creation':plan['worker_creation_utc']=plan['worker_started_at']
    elif change=='old_checkpoint':plan['sha256']['checkpoint_receipt']='0'*64
    shared.write(prep,plan)
    with pytest.raises(ValueError):bind_actual(case,'0'*64 if change=='external_preparation' else None)
