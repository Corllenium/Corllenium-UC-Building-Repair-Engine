"""Prepare and run the evidence-bound original 1F E3 replay retaining whole site5."""
import argparse
from collections import Counter
from dataclasses import replace
from datetime import datetime,timezone
import hashlib
import json
import os
from pathlib import Path
import subprocess
import sys
import time

from engine.io.snapshot import sha256_file
from engine.io.protected import refuse_protected
from tools.main_infra_e3_binding import _hash
from tools.main_infra_e7_serialization import _dump,_read

ROOT=Path(__file__).resolve().parents[1]
FLOOR='1F'
RUN_ID='MAIN-INFRA-E3-1F-retain-visible-20261024'
NAMESPACE='run-20261024-1F-retain-visible'
REVISION='7b2f7451b5723f724a1e074fdedc07dbcf7291d330ae550066f4926886136511'
AUDIT_SHA='4daec2c27b2049ad61923f74e5c10cb3cfe750c24042bea9775a9f0caff6d3bf'
POLICY='retain_whole_original_e3_site_v1'


def _pin(row):
    if not isinstance(row,dict) or set(row)!={'path','sha256'}:raise ValueError('exact external evidence pin required')
    _hash(Path(row['path']),row['sha256'])


def _same_pin(first,second):
    return first['sha256']==second['sha256'] and Path(first['path']).resolve()==Path(second['path']).resolve()


def read_policy(pin):
    _pin(pin);p=_read(pin['path'])
    if (set(p)!={'schema_version','policy','run_id','source_revision','restore_sites','required_faces','original_counts','original_audit','evidence'}
            or p['schema_version']!=1 or p['policy']!=POLICY or p['run_id']!=RUN_ID or p['source_revision']!=REVISION
            or p['restore_sites']!=[5] or p['required_faces']!=[9809,10366]
            or p['original_counts']!=dict(planned=283,kept=280,rolled_back=3,site_faces=274)
            or p['original_audit']['sha256']!=AUDIT_SHA
            or set(p['evidence'])!={'attribution','lost_lines','provenance','report','receipt','original_validation'}):
        raise ValueError('exact retained visible E3 policy/cohort required')
    _pin(p['original_audit'])
    for row in p['evidence'].values():_pin(row)
    evidence={k:_read(v['path']) for k,v in p['evidence'].items() if k!='lost_lines'}
    lines=[json.loads(s) for s in Path(p['evidence']['lost_lines']['path']).read_text().splitlines()]
    evidence['lost_lines']=lines;a=evidence['attribution'];prov=evidence['provenance']
    old=Path(p['original_audit']['path']).parent;audit=_read(old/'stage-audit.json')
    log=[json.loads(s) for s in (old/'edit-log.jsonl').read_text().splitlines()]
    _hash(old/'edit-log.jsonl',audit['edit_log_sha256']);_hash(old/'source-faces.json',audit['source_faces_sha256'])
    if (not _same_pin(prov['E3_edit_log'],dict(path=str(old/'edit-log.jsonl'),sha256=audit['edit_log_sha256']))
            or not _same_pin(prov['E3_survivors'],dict(path=str(old/'source-faces.json'),sha256=audit['source_faces_sha256']))
            or not _same_pin(prov['attribution'],p['evidence']['attribution'])
            or not _same_pin(a['source_report'],p['evidence']['report']) or not _same_pin(a['source_receipt'],p['evidence']['receipt'])
            or not _same_pin(a['lines'],p['evidence']['lost_lines']) or a['lines']['count']!=14
            or prov['diagnostic_only'] is not True or prov['acceptance'] is not False
            or prov['lost_line_count']!=14 or prov['baseline_deleted_lines']!=14
            or prov['original_faces']!=[dict(face=face,E3_survives=False) for face in p['required_faces']]
            or len(prov['records'])!=1 or prov['records'][0]['log_line']!=6
            or prov['records'][0]['raw_record']!=log[5] or log[5]['site']!=5 or log[5].get('rolled_back',False)
            or hashlib.sha256((old/'edit-log.jsonl').read_bytes().splitlines()[5]).hexdigest()!=prov['records'][0]['raw_record_sha256']
            or len(log)!=284 or sum(r.get('rolled_back',False) for r in log[:-1])!=3
            or a['viewpoint']['kind']!='probe' or a['viewpoint']['index']!=422 or a['pixel_inches']!=.02
            or len(lines)!=14 or [r['line_id'] for r in lines]!=list(range(14))
            or Counter(r['before_face'] for r in lines)!={9809:10,10366:4}
            or any(r['E3_lost'] is not True or r['E3_reason']!=1 or r['after_reason']!=1 for r in lines)):
        raise ValueError('actual missing-line/source removal cohort differs')
    retained=log[5]['faces']
    if len(retained)!=274 or len(set(retained))!=274 or not set(p['required_faces'])<=set(retained):
        raise ValueError('whole original site5 faces required')
    evidence['original_records']=log
    return p,evidence,retained


def check_namespace(plan_path,out):
    plan_path,out=Path(plan_path),Path(out)
    if (plan_path.name!='preparation-1F.json' or out.name!='1F' or plan_path.parent.resolve()!=out.parent.resolve()
            or out.parent.name!=NAMESPACE):raise ValueError('new visible E3 preparation/output namespace required')


def components(*,extra_files=()):
    from tools import main_infra_e7_1f_run as shared
    value=shared._components()
    subprocess.check_call(['git','-C',str(ROOT),'diff','--quiet','95dad1de1be241e613cb0763447b662b918f7eca','--','engine'])
    names={'tools/main_infra_e3_visible_run.py','tools/main_infra_e3_checkpoint.py','tools/main_infra_e3_replay.py',
        'tools/main_infra_e3.py','tools/main_infra_e7_checkpoint.py','engine/validate/targets.json'}
    names.update(extra_files)
    names|={p.relative_to(ROOT).as_posix() for p in (ROOT/'engine').rglob('*.py')}
    subprocess.check_call(['git','-C',str(ROOT),'ls-files','--error-unmatch','--',*sorted(names)],stdout=subprocess.DEVNULL)
    value['files'].update({name:dict(sha256=sha256_file(ROOT/name),commit=value['HEAD']) for name in sorted(names)})
    return value


def real_paths():
    from tools.main_infra_e7_1f_run import real_paths as shared_paths
    return shared_paths()


def load_inputs(paths):
    from tools import main_infra_e7_1f_run as shared
    from tools.main_infra_e3 import _source_digest
    from engine.io.obj_reader import read_obj
    source,engine,_old_stage,_ancestry,looks,old=shared._load(paths)
    before=replace(read_obj(old['physical']['before']),physical_quanta=engine.mesh.physical_quanta)
    if before.n_faces!=15856 or looks.unknown(before):raise ValueError('qualified original BEFORE required')
    facts=dict(old,stage_input_triangles=before.n_faces,retired_stage_triangles=old['stage_input_triangles'],
        before_digest=_source_digest(before).hex())
    return source,engine,before,looks,facts


from tools.main_infra_e3_replay import load_replay_plan,run_checked_replay


def select_plan(before,looks,policy,evidence,retained):
    from tools.main_infra_e7_checkpoint import typed_plan_digest
    from tools.main_infra_e7_serialization import _encode
    original=Path(policy['original_audit']['path']).parent
    edits,replay=load_replay_plan(before,looks,original,expected_audit_sha256=policy['original_audit']['sha256'],restore_sites=(5,))
    records=evidence['original_records'][:-1];rolled=[r['site'] for r in records if r.get('rolled_back',False)]
    if (len(edits)!=279 or replay['original_kept_sites']!=280 or replay['restored_sites']!=[5]
            or replay['remaining_sites']!=279 or replay['remaining_removed_triangles']!=5446
            or replay['fresh_site_check_required'] is not True or len(rolled)!=3
            or any(e.site in {5,*rolled} or set(e.faces)&set(retained) for e in edits)):
        raise ValueError('verified original E3 cohort/whole-site retention differs')
    return dict(replay=replay,original_counts=policy['original_counts'],original_rolled_sites=rolled,
        retained_source_faces=retained,required_faces=policy['required_faces'],selected=len(edits),selected_sites=[e.site for e in edits],
        typed_plan_digest=typed_plan_digest(edits),selected_edits=[dict(_encode(e),decision=e.decision) for e in edits],
        all_original_records_verified=True,old_verdict_is_not_reused=True)


def _write(path,value):
    Path(path).write_text(_dump(value),encoding='utf-8')


def _inventory(paths,hashes):
    if set(paths)!=set(hashes):raise ValueError('complete pinned input inventory required')
    for key,path in paths.items():_hash(Path(path),hashes[key])



def _profile(profile):
    return sys.modules[__name__] if profile is None else profile


def required_sightlines(policy):
    return policy['evidence']['lost_lines']


def prepare(paths,plan_path,out,*,policy_pin,profile=None):
    scope=_profile(profile)
    plan_path,out=Path(plan_path),Path(out);scope.check_namespace(plan_path,out)
    for target in (plan_path,out,out.parent/f'execution-{scope.FLOOR}'):refuse_protected(target)
    if plan_path.exists() or out.exists() or (out.parent/f'execution-{scope.FLOOR}').exists():raise ValueError('preparation/output exists')
    frozen=scope.components();policy,evidence,retained=scope.read_policy(policy_pin)
    source,engine,before,looks,facts=scope.load_inputs(paths)
    selected=scope.select_plan(before,looks,policy,evidence,retained)
    bound=dict(paths);bound['retention_policy']=policy_pin['path']
    bound['original_audit']=policy['original_audit']['path']
    bound.update({'retention_'+k:v['path'] for k,v in policy['evidence'].items()})
    hashes={k:sha256_file(v) for k,v in bound.items()};_hash(Path(policy_pin['path']),policy_pin['sha256'])
    if frozen!=scope.components():raise ValueError('components changed during preparation')
    value=dict(schema_version=1,mode='fresh_checked_e3_visible_replay',run_id=scope.RUN_ID,floor=scope.FLOOR,state='prepared',
        prepared_utc=datetime.now(timezone.utc).isoformat(),paths=bound,sha256=hashes,components=frozen,inputs=facts,
        policy=policy_pin,selection=selected,required_independent_sightlines=scope.required_sightlines(policy),
        out=str(out.resolve()),floor_accepted=False)
    plan_path.parent.mkdir(parents=True,exist_ok=True);_write(plan_path,value)
    return value


def serialize_result(source,engine,before,outcome,looks,facts,plan,binding,checkpoint_receipt,candidate,*,profile=None):
    scope=_profile(profile)
    import numpy as np
    from engine.fixes.remove import remove_faces
    from engine.io.obj_reader import read_obj
    from engine.repair.kernel import write_records
    from tools.main_infra_e3 import source_survivors,save_survivor_pair
    from tools.main_infra_e3_binding import bind_saved_e3
    from tools.main_infra_e7_serialization import _tables
    from tools.main_infra_e7_1f_run import copy_assets
    indices=source_survivors(before,outcome)
    retained=plan['selection']['retained_source_faces']
    if not set(retained)<=set(indices.tolist()):raise ValueError('all whole-site retained faces must survive')
    engine_path,source_path,map_path=save_survivor_pair(engine,source,indices,candidate)
    write_records(candidate/'edit-log.jsonl',outcome.records)
    assets=copy_assets(Path(plan['paths']['raw']).parent,candidate,facts['assets'])
    _write(candidate/'asset-receipt.json',dict(schema_version=1,copied_new=True,assets=assets))
    input_receipt={k:v for k,v in facts['physical'].items() if k not in ('after','after_sha256','candidate_contract',
        'source_faces_sha256','edit_log_sha256','e3_removed_triangles')}
    audit=dict(cleanup_mode='e3_remove_only',executed_stages=['E3'],checks=outcome.checks,input_triangles=before.n_faces,
        output_triangles=len(indices),kept_edits=len(outcome.kept),rolled_back_edits=len(outcome.rolled_back),
        engine_candidate_sha256=sha256_file(engine_path),source_candidate_sha256=sha256_file(source_path),
        source_faces_sha256=sha256_file(map_path),edit_log_sha256=sha256_file(candidate/'edit-log.jsonl'),
        qualification_sha256=sha256_file(plan['paths']['qualification']),assets=facts['assets'],
        before_snapshot=str(Path(facts['physical']['before']).parent),input_receipt=input_receipt,
        builder_component_commit=plan['components']['HEAD'],guard=dict(passed=False,state='independent strict guard pending'),
        independent_validation='pending',accepted=False,retention_policy_sha256=plan['policy']['sha256'])
    _write(candidate/'stage-audit.json',audit)
    after_engine,after_source=read_obj(engine_path),read_obj(source_path)
    bind_saved_e3(candidate=candidate,audit=audit,before_engine=before,after_engine=after_engine,
        before_source=source.mesh,after_source=after_source)
    drop=np.ones(source.mesh.n_faces,bool);drop[indices]=False
    expected_source,_=remove_faces(source.mesh,drop);expected_engine,_=remove_faces(engine.mesh,drop)
    _tables(after_source,expected_source);_tables(after_engine,expected_engine)
    for row in assets:_hash(candidate/row['path'],row['sha256'])
    retention=dict(schema_version=1,mode='original_e3_visible_retention',run_id=scope.RUN_ID,input_binding=binding,
        policy=plan['policy'],selection=plan['selection'],checkpoint_receipt_sha256=checkpoint_receipt['receipt_sha256'],
        all_retained_faces_survive=True,exact_saved_tables=True,required_independent_sightlines=plan['required_independent_sightlines'],
        files={name:sha256_file(candidate/name) for name in ('candidate.engine.obj','candidate.source.obj','source-faces.json',
            'edit-log.jsonl','stage-audit.json','asset-receipt.json')},acceptance=False)
    _write(candidate/'retention-receipt.json',retention)
    return dict(source_sha256=audit['source_candidate_sha256'],engine_sha256=audit['engine_candidate_sha256'],
        stage_audit_sha256=sha256_file(candidate/'stage-audit.json'),retention_receipt_sha256=sha256_file(candidate/'retention-receipt.json'),
        asset_receipt_sha256=sha256_file(candidate/'asset-receipt.json'),assets=assets)


def execute(plan_path,expected_sha256,*,policy_pin=None,profile=None):
    scope=_profile(profile)
    from tools.main_infra_e3_checkpoint import save_e3_checkpoint,restore_e3_checkpoint
    from tools.main_infra_e7_checkpoint import typed_plan_digest
    plan_path=Path(plan_path);_hash(plan_path,expected_sha256);plan=_read(plan_path);out=Path(plan['out'])
    scope.check_namespace(plan_path,out)
    if (plan.get('mode')!='fresh_checked_e3_visible_replay' or plan.get('run_id')!=scope.RUN_ID or plan.get('floor')!=scope.FLOOR
            or plan['components']!=scope.components() or (policy_pin is not None and plan['policy']!=policy_pin)):
        raise ValueError('prepared E3 identity/component/policy differs')
    _inventory(plan['paths'],plan['sha256']);policy,evidence,retained=scope.read_policy(plan['policy'])
    source,engine,before,looks,facts=scope.load_inputs(plan['paths']);selected=scope.select_plan(before,looks,policy,evidence,retained)
    if facts!=plan['inputs'] or selected!=plan['selection']:raise ValueError('prepared physical inputs/typed selection differs')
    work=out.parent/f'execution-{scope.FLOOR}'
    for target in (out,work):refuse_protected(target)
    if out.exists() or work.exists():raise ValueError('execution/candidate exists')
    work.mkdir(parents=True);started=time.perf_counter()
    worker=dict(schema_version=1,run_id=scope.RUN_ID,floor=scope.FLOOR,state='checking',pid=os.getpid(),
        started_utc=datetime.now(timezone.utc).isoformat(),components=plan['components'],preparation=str(plan_path.resolve()),
        preparation_sha256=expected_sha256,out=str(out),original_source_triangles=before.n_faces,
        original_e3_counts=policy['original_counts'],planned_edits=selected['selected'],floor_accepted=False,independent_validation='pending')
    def status(**update):
        worker.update(update,updated_utc=datetime.now(timezone.utc).isoformat())
        temporary=work/'worker.json.tmp';_write(temporary,worker);temporary.replace(work/'worker.json')
        print(_dump({k:worker[k] for k in ('state','pid','updated_utc')}),flush=True)
    status();checkpoint=work/'checked-outcome'
    try:
        outcome,_indices,replay=run_checked_replay(before,looks,Path(policy['original_audit']['path']).parent,
            expected_audit_sha256=policy['original_audit']['sha256'],restore_sites=tuple(policy['restore_sites']))
        worker.update(kept_edits=len(outcome.kept),rolled_back_edits=len(outcome.rolled_back),output_triangles=outcome.mesh.n_faces,checks=outcome.checks)
        paths=dict(plan['paths'],preparation=str(plan_path.resolve()));hashes=dict(plan['sha256'],preparation=expected_sha256)
        for i,row in enumerate(facts['assets']):
            paths['asset_'+str(i)]=str(Path(plan['paths']['raw']).parent/row['path']);hashes['asset_'+str(i)]=row['sha256']
        binding=dict(paths=paths,sha256=hashes,before_digest=facts['before_digest'],run_id=scope.RUN_ID,
            preparation_sha256=expected_sha256,components=plan['components'],selection_digest=hashlib.sha256(_dump(selected).encode()).hexdigest())
        capture=save_e3_checkpoint(before,outcome,looks,checkpoint,binding=binding)
        worker.update(checkpoint=str(checkpoint.resolve()),checkpoint_receipt_sha256=capture['receipt_sha256'],checkpoint_status='diagnostic_unverified')
        _hash(plan_path,expected_sha256);_inventory(paths,hashes)
        if plan['components']!=scope.components() or replay!=selected['replay'] or typed_plan_digest(outcome.edits)!=selected['typed_plan_digest']:
            raise ValueError('components/original replay/actual typed proposal changed during kernel')
        status(state='checked_checkpoint_saved',checkpoint_status='verified')
        outcome=restore_e3_checkpoint(before,looks,checkpoint,binding=binding,expected_receipt_sha256=capture['receipt_sha256'])
        binding=dict(binding,paths=dict(paths,checked_outcome_receipt=str((checkpoint/'checkpoint-receipt.json').resolve())),
            sha256=dict(hashes,checked_outcome_receipt=capture['receipt_sha256']))
        candidate=work/'candidate';status(state='serializing')
        saved=serialize_result(source,engine,before,outcome,looks,facts,plan,binding,capture,candidate,profile=scope)
        status(state='finalizing',**saved,wall_s=round(time.perf_counter()-started,2),post_replay_signed_targets='not independently measured')
        _write(candidate/'run-receipt.json',dict(worker,state='candidate_saved',final_package=str(out.resolve())))
        candidate.rename(out)
        status(state='candidate_saved',final_package=str(out.resolve()),run_receipt_sha256=sha256_file(out/'run-receipt.json'))
        return worker
    except Exception as exc:
        captured=checkpoint/'checkpoint-receipt.json'
        if worker.get('checkpoint_status')!='verified' and captured.is_file():
            worker.update(checkpoint=str(checkpoint.resolve()),checkpoint_receipt_sha256=sha256_file(captured),checkpoint_status='diagnostic_unverified')
        status(state='failed',error=f'{type(exc).__name__}: {exc}',wall_s=round(time.perf_counter()-started,2))
        raise


def main(argv=None,*,profile=None):
    scope=_profile(profile)
    parser=argparse.ArgumentParser(description=scope.__doc__);parser.add_argument('action',choices=['prepare','execute'])
    for name in ('plan','policy'):parser.add_argument('--'+name,type=Path,required=True)
    parser.add_argument('--policy-sha256',required=True);parser.add_argument('--out',type=Path);parser.add_argument('--plan-sha256')
    args=parser.parse_args(argv);pin=dict(path=str(args.policy.resolve()),sha256=args.policy_sha256)
    if args.action=='prepare':
        if args.out is None:parser.error('prepare requires --out')
        p=prepare(scope.real_paths(),args.plan,args.out,policy_pin=pin,profile=scope)
        print(_dump(dict(state=p['state'],selected=p['selection']['selected'],plan_sha256=sha256_file(args.plan))))
    else:
        if not args.plan_sha256:parser.error('execute requires --plan-sha256')
        execute(args.plan,args.plan_sha256,policy_pin=pin,profile=scope)
    return 0


if __name__=='__main__':raise SystemExit(main())
