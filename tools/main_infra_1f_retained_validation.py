"""Corrected1F profile and the two mandatory default visibility measurements."""
from collections import Counter
from types import SimpleNamespace
import numpy as np
from tools import main_infra_2f_validation as shared

PROFILE=shared.RETAINED_1F
ATTEMPT='run-20261024-1F-retain-visible'
REVIEWER='/root/main_infra_independent_validator'
FACES=(9809,10366)
PROBE=422


def require_retained_mesh(before,after,indices,retained):
    from tools.main_infra_e3 import verify_survivor_mesh
    verify_survivor_mesh(before,after,indices)
    for key in ('positions','uvs','normals'):
        b,a=getattr(before,key),getattr(after,key)
        if b.dtype!=a.dtype or b.shape!=a.shape or b.tobytes()!=a.tobytes():
            raise ValueError('Original source table bytes differ: '+key)
    if not set(retained).issubset(indices):
        raise ValueError('Whole retained original site must survive')
    return [indices.index(face) for face in retained]


def require_floor_receipt(path,sha256,receipt):
    if path is None or sha256 is None:
        raise ValueError('Measured mandatory two-face floor receipt required')
    shared.check(path,sha256);proof=shared.read(path);shared.recheck(proof)
    keys=('job_id','floor_id','source_revision','attempt_namespace','worker_pid',
          'before_sha256','after_sha256','source_after_sha256')
    result=proof.get('forced_floor',{})
    faces=result.get('faces',[]);lines=result.get('lines',[])
    if (any(proof.get(key)!=receipt.get(key) for key in keys)
            or any(proof.get('hashes',{}).get(key)!=value for key,value in receipt['hashes'].items())
            or result.get('passed') is not True or result.get('pixel_inches')!=.02
            or result.get('visible_floor_px')!=4 or result.get('pixel_budget')!=1<<18
            or result.get('depth_tolerance_inches')!=.05
            or result.get('viewpoint',{}).get('kind')!='probe' or result['viewpoint'].get('index')!=PROBE
            or sorted(row.get('face',-1) for row in faces)!=list(FACES)
            or any(not np.isfinite(row.get('lost_pixels',np.nan)) or row['lost_pixels']>4 for row in faces)
            or result.get('line_count')!=14 or result.get('lost_lines')!=0
            or sorted(row.get('line_id',-1) for row in lines)!=list(range(14))
            or any(row.get('lost') is not False for row in lines)):
        raise ValueError('Mandatory original two-face floor proof differs or failed')


def require_lines(lines):
    counts=Counter(row.get('before_face') for row in lines)
    if (len(lines)!=14 or counts!={9809:10,10366:4}
            or sorted(row.get('line_id',-1) for row in lines)!=list(range(14))):
        raise ValueError('All14 original two-face lost lines required')
    for row in lines:
        for key in ('point_recentred','point_engine','barycentric','toward'):
            value=np.asarray(row.get(key),dtype=float)
            if value.shape!=(3,) or not np.isfinite(value).all():
                raise ValueError('Finite exact recorded line geometry required')
        if not np.isfinite(row.get('weight',np.nan)) or row['weight']<=0:
            raise ValueError('Positive recorded pixel weight required')
    return dict(counts)


def measure_pairs(floor,faces,col,lines):
    from engine.validate.floor import VISIBLE_FLOOR_PX,FLOOR_IN_PER_PX,PIXEL_BUDGET
    measured=[]
    for face in faces:
        result=floor.measure(face,col)
        measured.append(dict(face=int(face),visible_pixels=float(result['visible']),
            lost_pixels=float(result['lost']),at_least=bool(result['at_least']),
            reasons=result['reasons'],covering_faces={str(k):float(v) for k,v in result['covering'].items()}))
    verdicts=[]
    for row in lines:
        blk=SimpleNamespace(points=np.asarray([row['point_recentred']],float),
            toward=np.asarray([row['toward']],float),bary=np.asarray([row['barycentric']],float))
        lost,reason,cover=floor._lost(row['before_face'],col,floor.views[col],blk)
        verdicts.append(dict(line_id=row['line_id'],before_face=row['before_face'],
            lost=bool(lost[0]),reason=int(reason[0]),covering_face=int(cover[0]),weight=float(row['weight'])))
    lost_lines=sum(row['lost'] for row in verdicts)
    return dict(passed=all(row['lost_pixels']<=VISIBLE_FLOOR_PX for row in measured) and lost_lines==0,
        pixel_inches=FLOOR_IN_PER_PX,visible_floor_px=VISIBLE_FLOOR_PX,pixel_budget=PIXEL_BUDGET,
        faces=measured,line_count=len(lines),lost_lines=lost_lines,lines=verdicts)


def forced_floor(before,after,looks,receipt):
    import json
    from pathlib import Path
    from engine.validate import checks as c
    path=Path(receipt['paths']['lost_lines'])
    lines=[json.loads(row) for row in path.read_text(encoding='utf-8').splitlines()]
    require_lines(lines)
    if before.n_faces!=15856:
        raise ValueError('Original15856 BEFORE required for mandatory floor')
    b,centre=c.recentred(before);a,_=c.recentred(after,centre)
    for row in lines:
        if not np.array_equal(np.asarray(row['point_recentred'])+centre,np.asarray(row['point_engine'])):
            raise ValueError('Recorded line original coordinate frame differs')
    caster_b=c.build_caster(b);caster_a=c.build_caster(a)
    settings=c.Settings();tol=c.depth_tolerance(c.print_step(before))
    if tol!=.05:
        raise ValueError('Recorded default depth floor differs')
    lo,hi=c.used_bbox(b)
    dirs=c.above_horizon_directions(settings.n_directions)
    extra=c.above_horizon_directions(settings.n_extra_directions)
    cams=c.pedestrian_ring((lo,hi),eye_z=lo[2]+settings.eye,n=settings.n_cameras,margin=settings.camera_margin)
    probes=c.interior_probes(b,eye=settings.eye,caster=caster_b)
    if len(probes)!=762:
        raise ValueError('Original default probe cohort differs')
    views,labels=c.floor_views(dirs,extra,cams,probes,centre)
    col=len(dirs)+len(extra)+len(cams)+PROBE
    attribution=shared.read(receipt['paths']['lost_attribution'])
    if labels[col]!=attribution['viewpoint'] or col!=attribution['view_column']:
        raise ValueError('Exact original probe422 identity differs')
    table=c.LookTable();lb=c.face_look_ids(before,looks,table);la=c.face_look_ids(after,looks,table)
    sizes=[looks.texel.get(key) or (0,0) for key in table.keys]
    tw=np.array([s[0] for s in sizes],float);th=np.array([s[1] for s in sizes],float)
    judge=c._Judge(a,caster_a,la,tol,blockable=c.changed_faces(b,a))
    floor=c._Floor(b,judge,None,lb,tw,th,caster_b,views,labels,c.face_normals(b),centre)
    result=measure_pairs(floor,FACES,col,lines)
    result.update(viewpoint=labels[col],view_column=col,depth_tolerance_inches=tol,
        preselector_used=False,acceptance=False)
    return result




def normalise_worker(plan,worker,audit,candidate,paths,hashes):
    from pathlib import Path
    import json
    p=shared.read(paths['builder_preparation'])
    shared.check(paths['builder_preparation'],hashes['builder_preparation'])
    policy=shared.read(paths['retention_policy']);shared.check(paths['retention_policy'],hashes['retention_policy'])
    expected_counts=dict(planned=283,kept=280,rolled_back=3,site_faces=274)
    run='MAIN-INFRA-E3-1F-retain-visible-20261024'
    selection=p.get('selection',{})
    if (p.get('mode')!='fresh_checked_e3_visible_replay' or p.get('run_id')!=run or p.get('floor')!='1F'
            or p.get('state')!='prepared' or p.get('floor_accepted') is not False
            or Path(p['out']).resolve()!=candidate.resolve() or p['components']['HEAD']!=plan['builder_component_commit']
            or len(plan['builder_component_commit'])!=40
            or p['policy']['sha256']!=hashes['retention_policy']
            or Path(p['policy']['path']).resolve()!=paths['retention_policy'].resolve()
            or policy.get('policy')!='retain_whole_original_e3_site_v1' or policy.get('run_id')!=run
            or policy.get('source_revision')!=shared.REV or policy.get('restore_sites')!=[5]
            or policy.get('required_faces')!=list(FACES) or policy.get('original_counts')!=expected_counts):
        raise ValueError('New retained1F builder preparation/policy required')
    shared.check(policy['original_audit']['path'],policy['original_audit']['sha256'])
    old=Path(policy['original_audit']['path']).parent
    old_audit=shared.read(old/'stage-audit.json');shared.check(old/'edit-log.jsonl',old_audit['edit_log_sha256'])
    rows=[json.loads(row) for row in (old/'edit-log.jsonl').read_text().splitlines()][:-1]
    retained=[row for row in rows if row['site']==5]
    kept=[row['site'] for row in rows if not row.get('rolled_back',False)]
    if (len(rows)!=283 or len(kept)!=280 or len(retained)!=1 or len(retained[0]['faces'])!=274
            or retained[0].get('rolled_back',False) or selection.get('retained_source_faces')!=retained[0]['faces']
            or selection.get('required_faces')!=list(FACES) or selection.get('original_counts')!=expected_counts
            or selection.get('selected')!=279 or selection.get('selected_sites')!=[site for site in kept if site!=5]
            or selection.get('all_original_records_verified') is not True or selection.get('old_verdict_is_not_reused') is not True
            or selection.get('replay',{}).get('restored_sites')!=[5]
            or selection['replay'].get('fresh_site_check_required') is not True
            or p.get('required_independent_sightlines')!=policy['evidence']['lost_lines']):
        raise ValueError('Whole original E3 retention cohort differs')
    if (worker.get('run_id')!=run or worker.get('floor')!='1F' or worker.get('floor_accepted') is not False
            or worker.get('components')!=p['components'] or worker.get('original_source_triangles')!=15856
            or worker.get('original_e3_counts')!=expected_counts or worker.get('planned_edits')!=279
            or worker.get('checkpoint_status')!='verified'
            or worker.get('checkpoint_receipt_sha256')!=hashes['checkpoint_receipt']
            or Path(worker.get('checkpoint','')).resolve()!=paths['checkpoint_receipt'].parent.resolve()
            or worker.get('preparation_sha256')!=hashes['builder_preparation']
            or Path(worker.get('preparation','')).resolve()!=paths['builder_preparation'].resolve()
            or Path(worker.get('final_package','')).resolve()!=candidate.resolve()
            or audit.get('retention_policy_sha256')!=hashes['retention_policy']
            or worker.get('kept_edits')!=audit.get('kept_edits') or worker.get('rolled_back_edits')!=audit.get('rolled_back_edits')
            or worker['kept_edits']+worker['rolled_back_edits']!=279):
        raise ValueError('Actual saved retained1F worker/checkpoint differs')
    for key,path in p['paths'].items():
        shared.check(path,p['sha256'][key])
        if key in hashes and key in ('raw','reference','qualification','materials'):
            if hashes[key]!=p['sha256'][key]:
                raise ValueError('Independent original source anchor differs')
        paths['builder_'+key]=Path(path);hashes['builder_'+key]=p['sha256'][key]
    for name,row in p['components']['files'].items():
        root=Path(plan['builder_root']).resolve();path=(root/name).resolve()
        if not path.is_relative_to(root):raise ValueError('Builder component escapes its checkout')
        shared.check(path,row['sha256']);paths['builder_component_'+name]=path;hashes['builder_component_'+name]=row['sha256']
    for key,pin in policy['evidence'].items():
        shared.check(pin['path'],pin['sha256']);paths['policy_evidence_'+key]=Path(pin['path']);hashes['policy_evidence_'+key]=pin['sha256']
    paths['lost_lines']=paths['policy_evidence_lost_lines'];hashes['lost_lines']=hashes['policy_evidence_lost_lines']
    paths['lost_attribution']=paths['policy_evidence_attribution'];hashes['lost_attribution']=hashes['policy_evidence_attribution']
    return dict(worker,floor_id='1F',started_at=worker['started_utc'],candidate=str(candidate),
        builder_component_commit=p['components']['HEAD'],accepted=False,input_triangles=15856)




def bind_package(worker,plan,candidate,paths,hashes):
    from pathlib import Path
    p=shared.read(paths['builder_preparation'])
    for key,name,field in [('retention_receipt','retention-receipt.json','retention_receipt_sha256'),
            ('run_receipt','run-receipt.json','run_receipt_sha256'),
            ('asset_receipt','asset-receipt.json','asset_receipt_sha256')]:
        path=candidate/name;shared.check(path,worker.get(field));paths[key]=path;hashes[key]=worker[field]
    retained=shared.read(paths['retention_receipt']);run=shared.read(paths['run_receipt'])
    checkpoint=shared.read(paths['checkpoint_receipt'])
    binding=checkpoint.get('binding',{})
    expected=dict(binding,paths=dict(binding.get('paths',{}),checked_outcome_receipt=str(paths['checkpoint_receipt'].resolve())),
        sha256=dict(binding.get('sha256',{}),checked_outcome_receipt=hashes['checkpoint_receipt']))
    filenames=('candidate.engine.obj','candidate.source.obj','source-faces.json','edit-log.jsonl','stage-audit.json','asset-receipt.json')
    if (checkpoint.get('mode')!='actual_checked_e3_checkpoint'
            or binding.get('run_id')!=p['run_id'] or binding.get('components')!=p['components']
            or binding.get('preparation_sha256')!=hashes['builder_preparation']
            or retained.get('schema_version')!=1 or retained.get('mode')!='original_e3_visible_retention'
            or retained.get('run_id')!=p['run_id'] or retained.get('policy')!=p['policy']
            or retained.get('selection')!=p['selection'] or retained.get('input_binding')!=expected
            or retained.get('checkpoint_receipt_sha256')!=hashes['checkpoint_receipt']
            or retained.get('all_retained_faces_survive') is not True or retained.get('exact_saved_tables') is not True
            or retained.get('acceptance') is not False or retained.get('required_independent_sightlines')!=p['required_independent_sightlines']
            or set(retained.get('files',{}))!=set(filenames)
            or run.get('state')!='candidate_saved' or run.get('floor_accepted') is not False
            or Path(run.get('final_package','')).resolve()!=candidate.resolve()
            or any(run.get(key)!=worker.get(key) for key in ('pid','started_utc','components','preparation_sha256',
                'checkpoint_receipt_sha256','original_source_triangles','planned_edits','kept_edits','rolled_back_edits','output_triangles',
                'stage_audit_sha256','engine_sha256','source_sha256','retention_receipt_sha256','asset_receipt_sha256'))):
        raise ValueError('Actual1F retention/run/typed checkpoint cross-binding differs')
    for name in filenames:shared.check(candidate/name,retained['files'][name])
    for key,path in binding.get('paths',{}).items():
        shared.check(path,binding['sha256'][key]);paths['checkpoint_input_'+key]=Path(path);hashes['checkpoint_input_'+key]=binding['sha256'][key]




def canonical(value):
    import json
    return json.dumps(value,sort_keys=True,separators=(',',':'),allow_nan=False)+'\n'


def removal_rows(edits):
    from dataclasses import asdict
    rows=[asdict(edit) for edit in edits]
    for row in rows:row['faces']=list(row['faces'])
    return rows


def removal_digest(edits):
    import hashlib
    return hashlib.sha256((canonical(removal_rows(edits))+canonical({})).encode()).hexdigest()


def read_checked_capture(before,looks,out,sha256):
    from pathlib import Path
    from dataclasses import fields
    import hashlib,json,zipfile
    from engine.model import MeshData
    from engine.repair.types import Edit,apply_edits
    from engine.repair.kernel import KernelResult,stage_records
    from tools.main_infra_e3 import _source_digest,source_survivors
    out=Path(out);shared.check(out/'checkpoint-receipt.json',sha256)
    receipt=shared.read(out/'checkpoint-receipt.json');binding=receipt.get('binding',{})
    names=('positions','uvs','normals','face_v','face_vt','face_vn','face_material','face_line')
    refs={'mesh_'+key for key in names}
    if (receipt.get('schema_version')!=1 or receipt.get('mode')!='actual_checked_e3_checkpoint'
            or receipt.get('capture_only') is not True or set(receipt.get('files',{}))!={'arrays.npz','result.json','edit-log.jsonl'}
            or set(receipt.get('arrays',{}))!=refs or binding.get('before_digest')!=_source_digest(before).hex()
            or not binding.get('run_id') or set(binding.get('paths',{}))!=set(binding.get('sha256',{}))):
        raise ValueError('Actual E3 checkpoint schema/input identity differs')
    for key,path in binding['paths'].items():shared.check(path,binding['sha256'][key])
    for key,value in receipt['files'].items():shared.check(out/key,value)
    data=shared.read(out/'result.json')
    with zipfile.ZipFile(out/'arrays.npz') as archive:
        members=archive.namelist()
        if len(members)!=len(set(members)) or set(members)!={key+'.npy' for key in refs}:
            raise ValueError('Unknown or duplicate E3 checkpoint array member')
    with np.load(out/'arrays.npz',allow_pickle=False) as archive:arrays={key:archive['mesh_'+key] for key in names}
    for key,value in arrays.items():
        actual=dict(dtype=value.dtype.str,shape=list(value.shape),sha256=hashlib.sha256(value.tobytes()).hexdigest())
        if value.dtype.hasobject or actual!=receipt['arrays']['mesh_'+key]:raise ValueError('Actual E3 array digest differs')
    edits=[]
    for row in data['edits']:
        if (set(row)!={f.name for f in fields(Edit)} or row.get('engine')!='E3' or row.get('kind')!='remove'
                or row.get('legacy') is not False or any(row.get(key) is not None for key in
                    ('new_faces','new_points','new_face_uv','new_face_normal'))):
            raise ValueError('Checkpoint contains unsupported typed edits')
        edits.append(Edit(**row))
    partition=data['kept']+data['rolled_back']
    if (any(type(i) is not int or not 0<=i<len(edits) for i in partition) or len(partition)!=len(set(partition))
            or set(partition)!=set(range(len(edits))) or data['kept']!=sorted(data['kept']) or data['rolled_back']!=sorted(data['rolled_back'])):
        raise ValueError('Actual ordered E3 identity partition differs')
    mesh=MeshData(**data['mesh'],**arrays)
    outcome=KernelResult(mesh,data['result'],edits,data['stages'],data['report'],[edits[i] for i in data['kept']],
        [edits[i] for i in data['rolled_back']],data['checks'],data['records'])
    source_survivors(before,outcome)
    if outcome.report is not None or len(outcome.checks)!=1:raise ValueError('Actual sole E3 check required')
    expected,_=apply_edits(before,outcome.kept);check=outcome.checks[0]
    if (_source_digest(expected)!=_source_digest(mesh) or expected.name!=mesh.name
            or {r['site'] for r in check.get('rolled_back',[])}!={e.site for e in outcome.rolled_back}
            or (outcome.kept and (check.get('stage_rolled_back') is not None or check.get('rounds_exhausted',False)
                or not check.get('runs') or check['runs'][-1].get('status')!='PASS'
                or check['runs'][-1].get('failing')!=0 or check['runs'][-1].get('unknown',0)!=0))):
        raise ValueError('Fresh actual E3 result/check differs')
    records=stage_records(before,edits,{i:looks.key_of(name) for i,name in enumerate(before.materials)},'E3')
    for index in data['rolled_back']:records[index]['rolled_back']=True
    records.append({'check':check})
    log=[json.loads(row) for row in (out/'edit-log.jsonl').read_text().splitlines()]
    if (data.get('schema_version')!=1 or records!=outcome.records or log!=records
            or receipt['before_digest']!=_source_digest(before).hex() or receipt['after_digest']!=_source_digest(mesh).hex()
            or receipt['fresh_check']!=check or [receipt[k] for k in ('planned','kept','rolled_back','output_triangles')]
                !=[len(edits),len(outcome.kept),len(outcome.rolled_back),mesh.n_faces]):
        raise ValueError('Actual E3 capture records or digest differs')
    return outcome


def bind_checked_result(receipt,before,after,looks):
    from pathlib import Path
    import json
    from tools.main_infra_e3 import source_survivors
    from tools.main_infra_e3_replay import load_replay_plan
    p={key:Path(value) for key,value in receipt['paths'].items()}
    plan=shared.read(p['builder_preparation']);selection=plan['selection']
    policy=shared.read(p['retention_policy'])
    original=Path(policy['original_audit']['path']).parent
    edits,replay=load_replay_plan(before,looks,original,expected_audit_sha256=policy['original_audit']['sha256'],restore_sites=(5,))
    if (replay!=selection['replay'] or removal_digest(edits)!=selection['typed_plan_digest']
            or canonical(removal_rows(edits))!=canonical(selection['selected_edits'])):
        raise ValueError('All original E3 K1/typed subset proof differs')
    out=p['checkpoint_receipt'].parent
    outcome=read_checked_capture(before,looks,out,receipt['hashes']['checkpoint_receipt'])
    indices=shared.read(p['source-faces.json'])['source_faces']
    records=[json.loads(row) for row in p['edit-log.jsonl'].read_text(encoding='utf-8').splitlines()]
    audit=shared.read(p['audit'])
    if (removal_digest(outcome.edits)!=selection['typed_plan_digest']
            or source_survivors(before,outcome).tolist()!=indices
            or outcome.records!=records or outcome.checks!=audit['checks']
            or len(outcome.kept)!=audit['kept_edits'] or len(outcome.rolled_back)!=audit['rolled_back_edits']):
        raise ValueError('Saved candidate is not the actual fresh checked E3 result')
    require_retained_mesh(before,after,indices,selection['retained_source_faces'])
    for key in ('face_v','face_vt','face_vn','face_material'):
        actual,written=getattr(outcome.mesh,key),getattr(after,key)
        if key=='face_material':
            actual=[outcome.mesh.materials[int(i)] if i>=0 else None for i in actual]
            written=[after.materials[int(i)] if i>=0 else None for i in written]
            if actual!=written:raise ValueError('Actual checkpoint material differs from saved pair')
        elif actual.dtype!=written.dtype or actual.shape!=written.shape or actual.tobytes()!=written.tobytes():
            raise ValueError('Actual checkpoint corners differ from saved pair')
    receipt['retention']=dict(site=5,original_faces=len(selection['retained_source_faces']),
        original_counts=selection['original_counts'],selected=279,actual_kept=len(outcome.kept),
        actual_rolled_back=len(outcome.rolled_back),checkpoint_receipt_sha256=receipt['hashes']['checkpoint_receipt'],
        all_original_records_verified=True,actual_typed_result_verified=True,old_verdict_is_not_reused=True)


def main(argv=None):
    return shared.main(argv,floor_id='1F',profile=PROFILE)


if __name__=='__main__':
    raise SystemExit(main())

