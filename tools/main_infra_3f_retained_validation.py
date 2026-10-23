"""Corrected3F cohort binding over the existing retained E3 proof helpers."""
import json
from pathlib import Path
from tools import main_infra_2f_validation as shared
from tools.main_infra_1f_retained_validation import (bind_package, read_checked_capture,
    require_retained_mesh, bind_checked_result as _bind_checked_result)

PROFILE='e3_3f_retain_visible_20261024'
ATTEMPT='run-20261024-3F-retain-visible'
RUN='MAIN-INFRA-E3-3F-retain-visible-20261024'
POLICY_SHA='ffaf9bf6773076cef324aa5eb305fc4b38deccf173b5f6e4dd536ad15f214899'
COUNTS=dict(planned=1820,kept=1675,rolled_back=145,site_faces=6281)
REQUIRED=[897,1318,1323,4311,7760,13602,22979,26120,29747]


def require_cohort(p,policy,rows):
    selection=p.get('selection',{})
    restore=policy.get('restore_sites',[])
    kept=[row for row in rows if not row.get('rolled_back',False)]
    rolled=[row for row in rows if row.get('rolled_back',False)]
    by_site={row['site']:row for row in kept}
    if (len(rows)!=1820 or len({row['site'] for row in rows})!=1820 or len(kept)!=1675 or len(rolled)!=145
            or len(restore)!=263 or restore!=sorted(set(restore)) or not set(restore).issubset(by_site)
            or policy.get('policy')!='retain_whole_original_e3_sites_v1' or policy.get('run_id')!=RUN
            or policy.get('floor')!='3F' or policy.get('source_revision')!=shared.REV
            or policy.get('original_counts')!=COUNTS or policy.get('required_faces')!=REQUIRED
            or len(policy.get('native_sites',[]))!=258 or policy.get('subthreshold_extra_sites')!=[190,265,267,358,984]
            or set(restore)!=set(policy['native_sites'])|set(policy['subthreshold_extra_sites'])):
        raise ValueError('Original3F policy or all1820 records differ')
    retained=sorted({face for site in restore for face in by_site[site]['faces']})
    selected=[row['site'] for row in kept if row['site'] not in restore]
    old_rolled=sorted(row['site'] for row in rolled)
    if (len(retained)!=6281 or selection.get('retained_source_faces')!=retained
            or not set(REQUIRED).issubset(retained) or selection.get('required_faces')!=REQUIRED
            or selection.get('original_counts')!=COUNTS or selection.get('original_rolled_sites')!=old_rolled
            or selection.get('selected')!=1412 or selection.get('selected_sites')!=selected
            or selection.get('native_restored_sites')!=policy['native_sites']
            or selection.get('nonfailing_subthreshold_restored_sites')!=policy['subthreshold_extra_sites']
            or selection.get('signed_preservation_failure_sites')!=[]
            or selection.get('all_original_records_verified') is not True or selection.get('old_verdict_is_not_reused') is not True
            or selection.get('replay',{}).get('restored_sites')!=restore
            or selection['replay'].get('fresh_site_check_required') is not True
            or selection['replay'].get('original_kept_sites')!=1675 or selection['replay'].get('remaining_sites')!=1412
            or p.get('required_independent_sightlines')!={'native':policy['evidence']['footprint'],
                'subthreshold_completion':policy['evidence']['completion']}):
        raise ValueError('Whole original3F retention/rollback/selection cohort differs')
    return dict(selected=1412,restored_sites=restore,retained_faces=retained,required_faces=REQUIRED,
        old_rolled_sites=old_rolled,old_rolled_faces=sorted({face for row in rolled for face in row['faces']}))


def normalise_worker(plan,worker,audit,candidate,paths,hashes):
    p=shared.read(paths['builder_preparation']);shared.check(paths['builder_preparation'],hashes['builder_preparation'])
    shared.check(paths['retention_policy'],hashes['retention_policy'])
    policy=shared.read(paths['retention_policy'])
    if (p.get('mode')!='fresh_checked_e3_visible_replay' or p.get('run_id')!=RUN or p.get('floor')!='3F'
            or p.get('state')!='prepared' or p.get('floor_accepted') is not False
            or Path(p['out']).resolve()!=candidate.resolve() or p['components']['HEAD']!=plan['builder_component_commit']
            or len(plan['builder_component_commit'])!=40 or hashes['retention_policy']!=POLICY_SHA
            or p.get('policy')!={'path':str(paths['retention_policy']), 'sha256':POLICY_SHA}):
        raise ValueError('New retained3F builder preparation/policy required')
    shared.check(policy['original_audit']['path'],policy['original_audit']['sha256'])
    old=Path(policy['original_audit']['path']).parent
    old_audit=shared.read(old/'stage-audit.json');shared.check(old/'edit-log.jsonl',old_audit['edit_log_sha256'])
    records=[json.loads(row) for row in (old/'edit-log.jsonl').read_text().splitlines()]
    if records[-1]!={'check':old_audit['checks'][0]}:raise ValueError('Original3F log check differs')
    require_cohort(p,policy,records[:-1])
    if (worker.get('run_id')!=RUN or worker.get('floor')!='3F' or worker.get('floor_accepted') is not False
            or worker.get('components')!=p['components'] or worker.get('original_source_triangles')!=53602
            or worker.get('original_e3_counts')!=COUNTS or worker.get('planned_edits')!=1412
            or worker.get('checkpoint_status')!='verified'
            or worker.get('checkpoint_receipt_sha256')!=hashes['checkpoint_receipt']
            or Path(worker.get('checkpoint','')).resolve()!=paths['checkpoint_receipt'].parent.resolve()
            or worker.get('preparation_sha256')!=hashes['builder_preparation']
            or Path(worker.get('preparation','')).resolve()!=paths['builder_preparation'].resolve()
            or Path(worker.get('final_package','')).resolve()!=candidate.resolve()
            or audit.get('retention_policy_sha256')!=POLICY_SHA
            or worker.get('kept_edits')!=audit.get('kept_edits') or worker.get('rolled_back_edits')!=audit.get('rolled_back_edits')
            or worker['kept_edits']+worker['rolled_back_edits']!=1412):
        raise ValueError('Actual saved retained3F worker/checkpoint differs')
    for key,path in p['paths'].items():
        shared.check(path,p['sha256'][key])
        if key in hashes and key in ('raw','reference','qualification','materials') and hashes[key]!=p['sha256'][key]:
            raise ValueError('Independent original source anchor differs')
        paths['builder_'+key]=Path(path);hashes['builder_'+key]=p['sha256'][key]
    for name,row in p['components']['files'].items():
        root=Path(plan['builder_root']).resolve();path=(root/name).resolve()
        if not path.is_relative_to(root):raise ValueError('Builder component escapes its checkout')
        shared.check(path,row['sha256']);paths['builder_component_'+name]=path;hashes['builder_component_'+name]=row['sha256']
    for key,pin in policy['evidence'].items():
        shared.check(pin['path'],pin['sha256']);paths['policy_evidence_'+key]=Path(pin['path']);hashes['policy_evidence_'+key]=pin['sha256']
    return dict(worker,floor_id='3F',started_at=worker['started_utc'],candidate=str(candidate),
        builder_component_commit=p['components']['HEAD'],accepted=False,input_triangles=53602)


def bind_checked_result(receipt,before,after,looks):
    p={key:Path(value) for key,value in receipt['paths'].items()}
    policy=shared.read(p['retention_policy']);original=Path(policy['original_audit']['path']).parent
    plan=shared.read(p['builder_preparation'])
    rows=[json.loads(row) for row in (original/'edit-log.jsonl').read_text().splitlines()][:-1]
    cohort=require_cohort(plan,policy,rows)
    _bind_checked_result(receipt,before,after,looks,restore_sites=tuple(cohort['restored_sites']),selected=1412)
    indices=shared.read(p['source-faces.json'])['source_faces']
    require_retained_mesh(before,after,indices,cohort['old_rolled_faces'])
    info=receipt['retention'];info.pop('site')
    info.update(sites=cohort['restored_sites'],old_rollback_sites=cohort['old_rolled_sites'],
        old_rollback_original_faces=len(cohort['old_rolled_faces']),all_old_rollback_faces_survive=True)


def main(argv=None):
    return shared.main(argv,floor_id='3F',profile=PROFILE)


if __name__=='__main__':
    raise SystemExit(main())
