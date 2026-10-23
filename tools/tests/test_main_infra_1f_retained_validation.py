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

@pytest.mark.parametrize('change',['missing','duplicate','eye_height','headroom','outside_projection','outside_class'])
def test_retained_1f_native_cohort_rejects_drift(change):
    poses=json.loads(NATIVE.read_bytes())['poses']
    walking=next(p for p in poses if p['name'].startswith('eye_0_qualified'))
    if change=='missing':poses.pop()
    elif change=='duplicate':poses[-1]['name']=poses[0]['name']
    elif change=='eye_height':walking['eye_height_above_floor_metres']=.6
    elif change=='headroom':walking['headroom_clear']=False
    elif change=='outside_projection':next(p for p in poses if p.get('viewpoint_class')=='qualified_outside')['projection']='PERSP'
    elif change=='outside_class':next(p for p in poses if p.get('viewpoint_class')=='qualified_outside')['viewpoint_class']='diagnostic'
    with pytest.raises(ValueError):shared.native_pose_inventory(poses,'1F',profile=PROFILE)


def floor_case(remove=False):
    import numpy as np
    from dataclasses import replace
    from engine.tests.fixtures.build import _mesh
    from engine.rays.caster import BruteCaster
    from engine.validate import checks as c
    from engine.validate.floor import Viewpoint
    b=_mesh('tiny',[[0,0,0],[.1,0,0],[.1,.1,0],[0,.1,0]],[[0,0]]*4,[[0,1,2],[0,2,3]],[[0,1,2],[0,2,3]])
    a=replace(b,face_v=b.face_v[1:].copy(),face_vt=b.face_vt[1:].copy(),face_vn=b.face_vn[1:].copy(),face_material=b.face_material[1:].copy()) if remove else b
    lb=np.zeros(2,dtype=np.int64);la=np.zeros(a.n_faces,dtype=np.int64)
    judge=c._Judge(a,BruteCaster(a.positions,a.face_v),la,.05,blockable=c.changed_faces(b,a))
    floor=c._Floor(b,judge,None,lb,np.array([0.]),np.array([0.]),BruteCaster(b.positions,b.face_v),
        [Viewpoint.point([.05,.05,1.])],[dict(kind='probe',index=0,at=[.05,.05,1.])],c.face_normals(b),np.zeros(3))
    p=np.array([.06,.02,0.]);v=np.array([.05,.05,1.])-p;v/=np.linalg.norm(v)
    lines=[dict(before_face=0,line_id=0,point_recentred=p.tolist(),barycentric=[.4,.4,.2],toward=v.tolist(),weight=1.)]
    return floor,lines

def test_forced_floor_reaches_real_measure_even_without_preselected_candidates():
    from tools.main_infra_1f_retained_validation import measure_pairs
    floor,lines=floor_case()
    result=measure_pairs(floor,[0],0,lines)
    assert result['passed'] is True and result['faces'][0]['lost_pixels']==0
    assert result['line_count']==1 and result['lost_lines']==0

def test_forced_floor_rejects_actual_deleted_pixels_and_saved_line():
    from tools.main_infra_1f_retained_validation import measure_pairs
    floor,lines=floor_case(remove=True)
    result=measure_pairs(floor,[0],0,lines)
    assert result['passed'] is False and result['faces'][0]['lost_pixels']>4
    assert result['lost_lines']==1

@pytest.mark.parametrize('change',['omitted','duplicate','foreign','point'])
def test_recorded_twoface_line_cohort_rejects_drift(change):
    from tools.main_infra_1f_retained_validation import require_lines
    path=Path('D:/LLM_BACKUP/Codex session/main-infra-1f-validation-attempt4-20261024/05-Corllenium-UC-Building-Repair-Engine/data/main-infra-1f-validation/execution-ownership-attempt4/deleted-floor-attribution/lost-lines.jsonl')
    lines=[json.loads(row) for row in path.read_text().splitlines()]
    if change=='omitted':lines.pop()
    elif change=='duplicate':lines[-1]=lines[0]
    elif change=='foreign':lines[0]['before_face']=4372
    elif change=='point':lines[0]['point_recentred'][0]=float('nan')
    with pytest.raises(ValueError):require_lines(lines)

def test_actual_fourteen_lines_are_complete():
    from tools.main_infra_1f_retained_validation import require_lines
    path=Path('D:/LLM_BACKUP/Codex session/main-infra-1f-validation-attempt4-20261024/05-Corllenium-UC-Building-Repair-Engine/data/main-infra-1f-validation/execution-ownership-attempt4/deleted-floor-attribution/lost-lines.jsonl')
    assert require_lines([json.loads(row) for row in path.read_text().splitlines()])=={9809:10,10366:4}


def test_retained_source_faces_must_survive_with_bit_exact_tables():
    import numpy as np
    from tools.main_infra_1f_retained_validation import require_retained_mesh
    floor,_=floor_case();b=floor.b
    assert require_retained_mesh(b,b,[0,1],[0,1])==[0,1]
    from dataclasses import replace
    a=replace(b,positions=b.positions.copy());a.positions[0,0]=-0.
    with pytest.raises(ValueError):require_retained_mesh(b,a,[0,1],[0,1])
    a=replace(b,face_v=b.face_v[1:],face_vt=b.face_vt[1:],face_vn=b.face_vn[1:],face_material=b.face_material[1:])
    with pytest.raises(ValueError):require_retained_mesh(b,a,[1],[0])
    with pytest.raises(ValueError):require_retained_mesh(b,b,[1,0],[0,1])


def test_required_floor_receipt_cannot_be_omitted_or_relabelled(tmp_path):
    from tools.main_infra_1f_retained_validation import require_floor_receipt
    from tools.tests.test_main_infra_2f_validation import write,digest
    binding=dict(job_id=shared.JOB,floor_id='1F',source_revision=shared.REV,
        attempt_namespace='run-20261024-1F-retain-visible',worker_pid=123,
        before_sha256='b'*64,after_sha256='a'*64,source_after_sha256='s'*64,paths={},hashes={})
    proof=dict(binding,forced_floor=dict(passed=True,pixel_inches=.02,visible_floor_px=4,pixel_budget=1<<18,
        faces=[dict(face=9809,lost_pixels=0),dict(face=10366,lost_pixels=0)],
        viewpoint=dict(kind='probe',index=422),depth_tolerance_inches=.05,line_count=14,lost_lines=0,
        lines=[dict(line_id=i,lost=False) for i in range(14)]))
    path=tmp_path/'floor.json';write(path,proof)
    require_floor_receipt(path,digest(path),binding)
    for key,value in [('passed',False),('line_count',13),('lost_lines',1),('pixel_inches',.2),('depth_tolerance_inches',.5)]:
        wrong=json.loads(json.dumps(proof));wrong['forced_floor'][key]=value;write(path,wrong)
        with pytest.raises(ValueError):require_floor_receipt(path,digest(path),binding)
    wrong=json.loads(json.dumps(proof));wrong['after_sha256']='old';write(path,wrong)
    with pytest.raises(ValueError):require_floor_receipt(path,digest(path),binding)


def retained_case(tmp_path):
    from tools.tests.test_main_infra_2f_validation import bound,write,digest
    prep,old,oldworker,audit,_state,plan=bound.__wrapped__(tmp_path)
    run=tmp_path/'run-20261024-1F-retain-visible';run.mkdir()
    candidate=run/'1F';old.rename(candidate)
    policy=Path('D:/LLM_BACKUP/Codex session/main-infra-e3-1f-retain-visible-20261024/05-Corllenium-UC-Building-Repair-Engine/docs/superpowers/records/MAIN-INFRA-E3-1F-RETAIN-VISIBLE-20261024/policy.json')
    pol=json.loads(policy.read_bytes());log=Path(pol['original_audit']['path']).parent/'edit-log.jsonl'
    rows=[json.loads(s) for s in log.read_text().splitlines()][:-1]
    selected=[r['site'] for r in rows if not r.get('rolled_back',False) and r['site']!=5]
    faces=next(r['faces'] for r in rows if r['site']==5)
    component='17247d295d809a6405fae8271a4d3d290e04bb59';selection=dict(original_counts=pol['original_counts'],retained_source_faces=faces,
        original_rolled_sites=[8,117,127],
        required_faces=[9809,10366],selected=279,selected_sites=selected,all_original_records_verified=True,
        old_verdict_is_not_reused=True,replay=dict(restored_sites=[5],original_kept_sites=280,remaining_sites=279,fresh_site_check_required=True))
    builder=run/'preparation-1F.json';checkpoint=run/'execution-1F/checked-outcome/checkpoint-receipt.json'
    p=dict(schema_version=1,mode='fresh_checked_e3_visible_replay',run_id='MAIN-INFRA-E3-1F-retain-visible-20261024',
        floor='1F',state='prepared',floor_accepted=False,out=str(candidate),components=dict(HEAD=component,files={}),
        policy=dict(path=str(policy),sha256=digest(policy)),selection=selection,
        required_independent_sightlines=pol['evidence']['lost_lines'],paths=plan['paths'],sha256=plan['sha256'])
    write(builder,p);write(checkpoint,dict(mode='actual_checked_e3_checkpoint'))
    audit.update(builder_component_commit=component,input_triangles=15856,output_triangles=10410,
        kept_edits=279,rolled_back_edits=0,retention_policy_sha256=digest(policy))
    audit['input_receipt']['floor_id']='1F'
    write(candidate/'stage-audit.json',audit)
    worker=dict(state='candidate_saved',floor='1F',run_id=p['run_id'],pid=123,started_utc='2026-10-24T00:00:00Z',
        components=p['components'],preparation=str(builder),preparation_sha256=digest(builder),out=str(candidate),
        final_package=str(candidate),original_source_triangles=15856,original_e3_counts=pol['original_counts'],planned_edits=279,
        kept_edits=279,rolled_back_edits=0,output_triangles=10410,floor_accepted=False,
        checkpoint=str(checkpoint.parent),checkpoint_receipt_sha256=digest(checkpoint),checkpoint_status='verified')
    for filename in ['asset-receipt.json','retention-receipt.json','run-receipt.json']:
        write(candidate/filename,{})
    paths={k:Path(v) for k,v in plan['paths'].items()}
    paths.update(builder_preparation=builder,retention_policy=policy,checkpoint_receipt=checkpoint)
    hashes={k:digest(v) for k,v in paths.items()}
    plan.update(floor_id='1F',validation_profile=PROFILE,attempt_namespace=run.name,builder_component_commit=component,
        candidate=str(candidate),worker_pid=123,worker_started_at=worker['started_utc'])
    return plan,worker,audit,candidate,paths,hashes,p,selection

def test_new_retained_worker_normalises_without_reusing_old_attempt(tmp_path):
    from tools.main_infra_1f_retained_validation import normalise_worker
    plan,worker,audit,candidate,paths,hashes,p,selection=retained_case(tmp_path)
    normal=normalise_worker(plan,worker,audit,candidate,paths,hashes)
    assert normal['floor_id']=='1F' and normal['input_triangles']==15856
    assert normal['candidate']==str(candidate) and normal['accepted'] is False

@pytest.mark.parametrize('kind',['old_run','wrong_count','restored_other','missing_retained','unverified','old_pass'])
def test_retention_cohort_or_actual_checkpoint_drift_rejected(tmp_path,kind):
    from tools.main_infra_1f_retained_validation import normalise_worker
    from tools.tests.test_main_infra_2f_validation import write,digest
    plan,worker,audit,candidate,paths,hashes,p,selection=retained_case(tmp_path)
    if kind=='old_run':worker['run_id']='old'
    if kind=='wrong_count':worker['original_e3_counts']['kept']=279
    if kind=='restored_other':selection['replay']['restored_sites']=[0,2,9]
    if kind=='missing_retained':selection['retained_source_faces']=selection['retained_source_faces'][1:]
    if kind=='unverified':worker['checkpoint_status']='diagnostic_unverified'
    if kind=='old_pass':selection['old_verdict_is_not_reused']=False
    write(paths['builder_preparation'],p);hashes['builder_preparation']=digest(paths['builder_preparation'])
    worker['preparation_sha256']=hashes['builder_preparation']
    with pytest.raises(ValueError):normalise_worker(plan,worker,audit,candidate,paths,hashes)


def test_corrected_1f_entrypoint_help_is_explicit_and_launches_nothing(capsys):
    from tools.main_infra_1f_retained_validation import main
    with pytest.raises(SystemExit) as result:main(['--help'])
    text=capsys.readouterr().out
    assert result.value.code==0 and 'retained-floor' in text and '--floor-sha256' in text

def test_draft_without_actual_terminal_hashes_cannot_bind(tmp_path):
    from tools.main_infra_1f_retained_validation import main
    path=tmp_path/'draft.json';path.write_text('{}')
    with pytest.raises(ValueError):
        main(['guard','--preparation',str(path),'--preparation-sha256',shared.digest(path),
            '--candidate',str(tmp_path/'run-20261024-1F-retain-visible/1F'),
            '--audit-sha256','0'*64,'--worker-sha256','0'*64,'--out',str(tmp_path/'evidence')])


def test_actual_package_receipts_are_external_and_cross_bound(tmp_path):
    from tools.main_infra_1f_retained_validation import bind_package
    from tools.tests.test_main_infra_2f_validation import write,digest
    plan,w,a,c,paths,hashes,p,s=retained_case(tmp_path)
    checkpoint=json.loads(paths['checkpoint_receipt'].read_bytes())
    checkpoint['binding']=dict(paths={'preparation':str(paths['builder_preparation'])},
        sha256={'preparation':hashes['builder_preparation']},run_id=p['run_id'],
        preparation_sha256=hashes['builder_preparation'],components=p['components'],
        selection_digest=__import__('hashlib').sha256((json.dumps(s,sort_keys=True,separators=(',',':'))+'\n').encode()).hexdigest())
    write(paths['checkpoint_receipt'],checkpoint);hashes['checkpoint_receipt']=digest(paths['checkpoint_receipt'])
    w['checkpoint_receipt_sha256']=hashes['checkpoint_receipt']
    ret=dict(schema_version=1,mode='original_e3_visible_retention',run_id=p['run_id'],policy=p['policy'],
        selection=s,checkpoint_receipt_sha256=hashes['checkpoint_receipt'],all_retained_faces_survive=True,
        exact_saved_tables=True,required_independent_sightlines=p['required_independent_sightlines'],acceptance=False,
        input_binding=dict(checkpoint['binding'],paths=dict(checkpoint['binding']['paths'],checked_outcome_receipt=str(paths['checkpoint_receipt'])),
            sha256=dict(checkpoint['binding']['sha256'],checked_outcome_receipt=hashes['checkpoint_receipt'])),
        files={n:digest(c/n) for n in ['candidate.engine.obj','candidate.source.obj','source-faces.json','edit-log.jsonl','stage-audit.json','asset-receipt.json']})
    write(c/'retention-receipt.json',ret)
    w.update(retention_receipt_sha256=digest(c/'retention-receipt.json'),asset_receipt_sha256=digest(c/'asset-receipt.json'),
        stage_audit_sha256=digest(c/'stage-audit.json'),engine_sha256=digest(c/'candidate.engine.obj'),source_sha256=digest(c/'candidate.source.obj'))
    run=dict(w,state='candidate_saved');write(c/'run-receipt.json',run);w['run_receipt_sha256']=digest(c/'run-receipt.json')
    bind_package(w,p,c,paths,hashes)
    assert hashes['retention_receipt']==w['retention_receipt_sha256']
    ret['checkpoint_receipt_sha256']='0'*64;write(c/'retention-receipt.json',ret);w['retention_receipt_sha256']=digest(c/'retention-receipt.json')
    with pytest.raises(ValueError):bind_package(w,p,c,paths,hashes)


def actual_capture():
    from dataclasses import replace
    from engine.io.obj_reader import read_obj
    from engine.validate.checks import Looks
    root=Path('D:/LLM_BACKUP/Codex session/main-infra-e3-1f-retain-visible-20261024/05-Corllenium-UC-Building-Repair-Engine/data/main-infra-e3/retain-visible-preflight/tiny-checkpoint-fixture')
    data=json.loads((root/'checked-outcome/result.json').read_bytes())
    before=replace(read_obj(root/'baseline/before.engine.obj'),physical_quanta=tuple(data['mesh']['physical_quanta']))
    looks=Looks(key={'wall':'original-wall'},flat=frozenset({'original-wall'}))
    return before,looks,root/'checked-outcome'

def test_read_uses_actual_typed_checkpoint_and_external_sha():
    from tools.main_infra_1f_retained_validation import read_checked_capture
    before,looks,out=actual_capture()
    got=read_checked_capture(before,looks,out,'dc3c8ca5cf86302165bb4152e39d37617fb8061a563a2e687b629e8adf06d31e')
    assert got.checks[0]['final']=='NOTHING KEPT' and got.rolled_back[0] is got.edits[0] and got.kept==[]
    with pytest.raises(ValueError):read_checked_capture(before,looks,out,'0'*64)

@pytest.mark.parametrize('change',['array_tamper','duplicate_archive','new_points','partition','wrong_before'])
def test_checkpoint_reader_rejects_resealed_incoherent_payload(tmp_path,change):
    from tools.main_infra_1f_retained_validation import read_checked_capture
    from shutil import copytree
    import zipfile
    before,looks,source=actual_capture();out=tmp_path/'capture';copytree(source,out)
    receipt=json.loads((out/'checkpoint-receipt.json').read_bytes())
    data=json.loads((out/'result.json').read_bytes())
    if change=='array_tamper':(out/'arrays.npz').write_bytes(b'wrong')
    elif change=='duplicate_archive':
        with zipfile.ZipFile(out/'arrays.npz','a') as archive:
            with pytest.warns(UserWarning):archive.writestr('mesh_positions.npy',b'wrong')
    elif change=='new_points':data['edits'][0]['new_points']=[[0,0,0]]
    elif change=='partition':data['kept']=[0]
    elif change=='wrong_before':receipt['before_digest']='0'*64
    (out/'result.json').write_text(json.dumps(data))
    receipt['files']={key:shared.digest(out/key) for key in receipt['files']}
    (out/'checkpoint-receipt.json').write_text(json.dumps(receipt))
    with pytest.raises((ValueError,zipfile.BadZipFile)):read_checked_capture(before,looks,out,shared.digest(out/'checkpoint-receipt.json'))


def complete_retained_graph(tmp_path):
    from tools.tests.test_main_infra_2f_validation import write,digest
    plan,w,a,c,paths,hashes,p,s=retained_case(tmp_path)
    checkpoint=dict(mode='actual_checked_e3_checkpoint',binding=dict(paths={'preparation':str(paths['builder_preparation'])},
        sha256={'preparation':hashes['builder_preparation']},run_id=p['run_id'],preparation_sha256=hashes['builder_preparation'],components=p['components'],
        selection_digest=__import__('hashlib').sha256((json.dumps(s,sort_keys=True,separators=(',',':'))+'\n').encode()).hexdigest()))
    write(paths['checkpoint_receipt'],checkpoint);hashes['checkpoint_receipt']=digest(paths['checkpoint_receipt']);w['checkpoint_receipt_sha256']=hashes['checkpoint_receipt']
    ret=dict(schema_version=1,mode='original_e3_visible_retention',run_id=p['run_id'],policy=p['policy'],selection=s,
        checkpoint_receipt_sha256=hashes['checkpoint_receipt'],all_retained_faces_survive=True,exact_saved_tables=True,
        required_independent_sightlines=p['required_independent_sightlines'],acceptance=False,
        input_binding=dict(checkpoint['binding'],paths=dict(checkpoint['binding']['paths'],checked_outcome_receipt=str(paths['checkpoint_receipt'])),
            sha256=dict(checkpoint['binding']['sha256'],checked_outcome_receipt=hashes['checkpoint_receipt'])),
        files={n:digest(c/n) for n in ['candidate.engine.obj','candidate.source.obj','source-faces.json','edit-log.jsonl','stage-audit.json','asset-receipt.json']})
    write(c/'retention-receipt.json',ret)
    w.update(retention_receipt_sha256=digest(c/'retention-receipt.json'),asset_receipt_sha256=digest(c/'asset-receipt.json'),
        stage_audit_sha256=digest(c/'stage-audit.json'),engine_sha256=digest(c/'candidate.engine.obj'),source_sha256=digest(c/'candidate.source.obj'))
    run=dict(w,state='candidate_saved');write(c/'run-receipt.json',run);w['run_receipt_sha256']=digest(c/'run-receipt.json')
    worker=c.parent/'execution-1F/worker.json';write(worker,w)
    phase=tmp_path/'phase-execute.json';write(phase,{'phase':'e3-retain-visible-execute'})
    terminal=tmp_path/'terminal.json';creation='2026-10-24T00:00:00.0000000Z'
    write(terminal,dict(state='PROCESS_EXITED_ZERO',phase='e3-retain-visible-execute',actual_pid=123,
        actual_creation_utc=creation,actual_exit_code=0,launcher_exit_code=0,abort_reason=None,
        all_owned_exited=True,HEAD=plan['builder_component_commit'],acceptance=False,phase_plan_sha256=digest(phase)))
    paths.update(worker_terminal=terminal,worker_phase_plan=phase)
    hashes.update(worker_terminal=digest(terminal),worker_phase_plan=digest(phase))
    plan.update(worker=str(worker),worker_creation_utc=creation,worker_terminal_phase='e3-retain-visible-execute',
        paths={k:str(v) for k,v in paths.items()},sha256=hashes,evidence_root=str(tmp_path/'proof'),blender='never-executed.exe')
    prep=tmp_path/'independent-preparation.json';write(prep,plan)
    return prep,c,worker,plan

def test_complete_new_profile_saved_metadata_graph_binds(tmp_path):
    prep,c,worker,_=complete_retained_graph(tmp_path)
    receipt=shared.bind_identity(prep,c,shared.digest(c/'stage-audit.json'),shared.digest(worker),floor_id='1F',profile=PROFILE,preparation_sha256=shared.digest(prep))
    assert receipt['input_triangles']==15856 and receipt['output_triangles']==10410
    assert receipt['validation_profile']==PROFILE and receipt['reviewer']=='/root/main_infra_independent_validator'
    assert receipt['hashes']['retention_receipt']==shared.digest(c/'retention-receipt.json')

def test_new_profile_native_plan_uses_same_source_frame_and_46_cameras(tmp_path):
    from tools.main_infra_1f_retained_validation import main
    from tools.tests.test_main_infra_2f_validation import write,digest
    prep,c,worker,plan=complete_retained_graph(tmp_path)
    renderer=tmp_path/'renderer.py';renderer.write_text('raise RuntimeError("never run")')
    plan['paths'].update(native_poses=str(NATIVE),native_renderer=str(renderer))
    plan['sha256'].update(native_poses=digest(NATIVE),native_renderer=digest(renderer));write(prep,plan)
    receipt=shared.bind_identity(prep,c,digest(c/'stage-audit.json'),digest(worker),floor_id='1F',profile=PROFILE,preparation_sha256=digest(prep))
    guard=tmp_path/'guard.json';write(guard,dict(receipt,guard=dict(passed=True),views=26,resolution=[900,600]))
    out=tmp_path/'proof/native'
    code=main(['native-plan','--preparation',str(prep),'--preparation-sha256',digest(prep),'--candidate',str(c),
        '--worker-sha256',digest(worker),'--audit-sha256',digest(c/'stage-audit.json'),'--guard-receipt',str(guard),
        '--guard-sha256',digest(guard),'--out',str(out)])
    report=json.loads((out/'native-plan.json').read_bytes());command=report['command']
    assert code==0 and len(report['poses'])==46 and report['render_launched'] is False
    assert command[command.index('--before-frame')+1]=='source' and command[command.index('--after-frame')+1]=='source'


def test_all_builder_component_bytes_remain_in_postphase_inventory(tmp_path):
    from tools.main_infra_1f_retained_validation import normalise_worker
    from tools.tests.test_main_infra_2f_validation import write,digest
    plan,w,a,c,paths,hashes,p,s=retained_case(tmp_path)
    root=tmp_path/'builder';component=root/'engine/model.py';component.parent.mkdir(parents=True);component.write_bytes(b'fixture component')
    p['components']['files']={'engine/model.py':dict(sha256=digest(component),commit=p['components']['HEAD'])}
    plan['builder_root']=str(root);write(paths['builder_preparation'],p);hashes['builder_preparation']=digest(paths['builder_preparation'])
    w['components']=p['components'];w['preparation_sha256']=hashes['builder_preparation']
    normalise_worker(plan,w,a,c,paths,hashes)
    component.write_bytes(b'changed after binding')
    with pytest.raises(ValueError):shared.recheck(dict(paths={k:str(v) for k,v in paths.items()},hashes=hashes))


def test_retained_preparation_requires_the_external_manifest_hash(tmp_path):
    prep,c,worker,_=complete_retained_graph(tmp_path)
    with pytest.raises(ValueError):
        shared.bind_identity(prep,c,shared.digest(c/'stage-audit.json'),shared.digest(worker),floor_id='1F',profile=PROFILE)


def test_actual_prepared_279_typed_removals_match_reader_encoding_without_model_load():
    from tools.main_infra_1f_retained_validation import removal_rows,removal_digest,canonical
    from engine.repair.types import Edit
    path=Path('D:/LLM_BACKUP/Codex session/main-infra-e3-1f-retain-visible-20261024/05-Corllenium-UC-Building-Repair-Engine/data/main-infra-e3/run-20261024-1F-retain-visible/preparation-1F.json')
    assert shared.digest(path)=='41fcb9a8146891da633289c57c097baba419a59fbafd068ce54951be6fdc583b'
    plan=json.loads(path.read_bytes());selection=plan['selection']
    edits=[Edit(**row) for row in selection['selected_edits']]
    assert len(edits)==279 and len(selection['retained_source_faces'])==274
    assert removal_digest(edits)==selection['typed_plan_digest']
    assert canonical(removal_rows(edits))==canonical(selection['selected_edits'])


def test_old_failed_diagnostic_receipt_cannot_overwrite_new_retention_label(tmp_path):
    from tools.main_infra_1f_retained_validation import normalise_worker
    from tools.tests.test_main_infra_2f_validation import digest
    plan,w,a,c,paths,hashes,p,s=retained_case(tmp_path)
    new=c/'retention-receipt.json';paths['retention_receipt']=new;hashes['retention_receipt']=digest(new)
    normalise_worker(plan,w,a,c,paths,hashes)
    assert paths['retention_receipt']==new and hashes['retention_receipt']==digest(new)
    assert paths['policy_evidence_receipt']!=new


def test_new_provenance_rejects_wrong_prior_rollback_classification(tmp_path):
    from tools.main_infra_1f_retained_validation import normalise_worker
    from tools.tests.test_main_infra_2f_validation import write,digest
    plan,w,a,c,paths,hashes,p,s=retained_case(tmp_path)
    normalise_worker(plan,w,a,c,paths,hashes)
    s['original_rolled_sites']=[8,117,128]
    write(paths['builder_preparation'],p);hashes['builder_preparation']=digest(paths['builder_preparation'])
    w['preparation_sha256']=hashes['builder_preparation']
    with pytest.raises(ValueError):normalise_worker(plan,w,a,c,paths,hashes)


def test_new_provenance_rejects_rehashed_wrong_full_selection_seal(tmp_path):
    from tools.main_infra_1f_retained_validation import bind_package
    from tools.tests.test_main_infra_2f_validation import write,digest
    prep,c,worker_path,plan=complete_retained_graph(tmp_path)
    paths={k:Path(v) for k,v in plan['paths'].items()};hashes=dict(plan['sha256'])
    w=json.loads(worker_path.read_bytes());p=json.loads(paths['builder_preparation'].read_bytes())
    bind_package(w,p,c,paths,hashes)
    cp=json.loads(paths['checkpoint_receipt'].read_bytes());cp['binding']['selection_digest']='0'*64
    write(paths['checkpoint_receipt'],cp);hashes['checkpoint_receipt']=digest(paths['checkpoint_receipt'])
    w['checkpoint_receipt_sha256']=hashes['checkpoint_receipt']
    ret=json.loads((c/'retention-receipt.json').read_bytes())
    ret['checkpoint_receipt_sha256']=hashes['checkpoint_receipt']
    ret['input_binding']=dict(cp['binding'],paths=dict(cp['binding']['paths'],checked_outcome_receipt=str(paths['checkpoint_receipt'])),
        sha256=dict(cp['binding']['sha256'],checked_outcome_receipt=hashes['checkpoint_receipt']))
    write(c/'retention-receipt.json',ret);w['retention_receipt_sha256']=digest(c/'retention-receipt.json')
    run=json.loads((c/'run-receipt.json').read_bytes())
    run.update(checkpoint_receipt_sha256=w['checkpoint_receipt_sha256'],retention_receipt_sha256=w['retention_receipt_sha256'])
    write(c/'run-receipt.json',run);w['run_receipt_sha256']=digest(c/'run-receipt.json')
    with pytest.raises(ValueError):bind_package(w,p,c,paths,hashes)













