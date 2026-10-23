"""Two reported default floor failures only; diagnostic data, never acceptance."""
from dataclasses import replace
import hashlib,json
from pathlib import Path
import numpy as np
from tools import main_infra_e7_independent_attempt4 as api
from engine.io.obj_reader import read_obj
from engine.validate import checks as c
from engine.validate.floor import face_pixels,PIXEL_BUDGET,VISIBLE_FLOOR_PX

ROOT=api.ROOT;PROOF=api.OWNED/'1F';RT=ROOT/'data/main-infra-1f-validation/execution-ownership-attempt4'
OUT=RT/'deleted-floor-attribution';REPORT=PROOF/'native-failure-diagnostic/validation.json'
REPORT_SHA='b1865442179e278dde9993ee35922991bb73bbb8c2b11addbd4a8bc0040c5c43'
RECEIPT=PROOF/'native-failure-diagnostic/diagnostic-receipt.json'
RECEIPT_SHA='8622d58fa4e05f9c0d3617307bd4b454c18924051a82ccf81c41a740097a1104'
PREPARED_SHA='4e80ed648780216562bd6ee746fe78d5b8efca009ec84b0a5c76a6a8c1e52d9b'

def scalar(value):return float(value) if np.isfinite(value) else None

def main():
    api.check(REPORT,REPORT_SHA);api.check(RECEIPT,RECEIPT_SHA)
    report=api.read(REPORT);receipt=api.read(RECEIPT)
    assert receipt['diagnostic_only'] and not receipt['native_preservation_passed'] and not receipt['acceptance']
    native_pin=receipt['native_failure_retained'];api.check(native_pin['path'],native_pin['sha256'])
    native=api.read(native_pin['path']);api.recheck(native);assert native['qualified_owner_views']['passed'] is False
    source,before,after,looks,provenance,inputs=api.load_prepared(PROOF/'prepared-inputs.json',PREPARED_SHA,PROOF)
    plan=api.read(inputs['preparation']);api.check(plan['paths']['engine_input'],plan['sha256']['engine_input'])
    stage=replace(read_obj(plan['paths']['engine_input']),units=before.units,physical_quanta=before.physical_quanta)
    assert (before.n_faces,stage.n_faces,after.n_faces)==(15856,10136,10393)
    ancestry=api.read(plan['paths']['lineage'])['source_faces']
    lineage=api.read(inputs['paths']['candidate_cut-lineage.json'])['faces']
    children={}
    for row in lineage:children.setdefault(row['stage_input_face'],[]).append(row)
    expected={row['face']:row for row in report['checks']['nothing_deleted']['floor']['failing']}
    assert set(expected)=={9809,10366}
    assert all(row['viewpoint']['kind']=='probe' and row['viewpoint']['index']==422 and row['reasons'].keys()=={'deleted'} for row in expected.values())
    b,centre=c.recentred(before);a,_=c.recentred(after,centre);e,_=c.recentred(stage,centre)
    caster_b=c.build_caster(b);caster_a=c.build_caster(a);caster_e=c.build_caster(e)
    settings=c.Settings();tol=c.depth_tolerance(c.print_step(before));assert tol==0.05
    lo,hi=c.used_bbox(b)
    dirs=c.above_horizon_directions(settings.n_directions)
    extra=c.above_horizon_directions(settings.n_extra_directions)
    cams=c.pedestrian_ring((lo,hi),eye_z=lo[2]+settings.eye,n=settings.n_cameras,margin=settings.camera_margin)
    probes=c.interior_probes(b,eye=settings.eye,caster=caster_b);assert len(probes)==762
    views,labels=c.floor_views(dirs,extra,cams,probes,centre)
    col=len(dirs)+len(extra)+len(cams)+422
    assert labels[col]==expected[9809]['viewpoint']==expected[10366]['viewpoint']
    table=c.LookTable();lb=c.face_look_ids(before,looks,table);la=c.face_look_ids(after,looks,table);le=c.face_look_ids(stage,looks,table)
    sizes=[looks.texel.get(key) or (0,0) for key in table.keys];tw=np.array([s[0] for s in sizes],float);th=np.array([s[1] for s in sizes],float)
    ja=c._Judge(a,caster_a,la,tol,blockable=c.changed_faces(b,a));je=c._Judge(e,caster_e,le,tol,blockable=c.changed_faces(b,e))
    normals=c.face_normals(b)
    floor=c._Floor(b,ja,None,lb,tw,th,caster_b,views,labels,normals,centre)
    baseline=c._Floor(b,je,None,lb,tw,th,caster_b,views,labels,normals,centre)
    if OUT.exists():raise ValueError('exclusive attribution output required')
    OUT.mkdir();summary=[];sites=set();unresolved=0;line_count=0

    def describe(mesh_kind,fid):
        fid=int(fid)
        if fid<0:return dict(face=-1)
        if mesh_kind=='stage':return dict(face=fid,original_source_triangle=int(ancestry[fid]),current_lineage=children.get(fid,[]))
        return dict(face=fid,lineage=lineage[fid])

    def present_details(judge,mesh_kind,face,p,toward,bary):
        n=normals[face];side=n*(1.0 if toward@n>0 else -1.0)
        w=c._Witnesses(col=np.array([col]),need_front=np.array([toward@n>0]),toward=side[None],
            origin=p[None]+c.EPS_ORIGIN*side,dirn=side[None],reach=np.array([np.inf]),is_dir=np.array([True]))
        look=lb[[face]];uv=c.uv_at(b,np.array([face]),bary[None]);t_b=tol+c._PRESENT_BACK
        start=p[None]+side[None]*t_b;u=-side[None]
        actual=judge.present(p[None],w,look,uv,tw[look],th[look])
        native_id,native_t=judge.caster.first_hit(start,u)
        hand=judge._by_hand(start,u,t_b,np.array([0]),look,uv,tw[look],th[look],w.need_front)
        rr,ff=judge._grid.lookup(p[None]);s0=start[0]+u[0]*(t_b-tol);s1=start[0]+u[0]*(t_b+tol)
        lo2=np.minimum(s0,s1)-1e-6;hi2=np.maximum(s0,s1)+1e-6
        ff=ff[((lo2<=judge.face_hi[ff])&(hi2>=judge.face_lo[ff])).all(axis=1)]
        rows=np.zeros(len(ff),dtype=np.int64)
        window,look_ok,uv_ok,side_ok=judge._flags(start,u,t_b,ff,rows,look,uv,tw[look],th[look],w.need_front,inside=True)
        plane_window,*_=judge._flags(start,u,t_b,ff,rows,look,uv,tw[look],th[look],w.need_front,inside=False)
        candidates=[];support=[]
        for i,g in enumerate(ff):
            if not plane_window[i]:continue
            den=float(u[0]@judge.raw[g]);t=float((judge.a0[g]-start[0])@judge.raw[g]/den)
            q=start+u*t;weights=c._barycentric(judge.after.positions,judge.after.face_v[[g]],q)[0]
            good=bool(window[i] and look_ok[i] and uv_ok[i] and side_ok[i])
            candidates.append(dict(describe(mesh_kind,g),plane_depth=scalar(t),barycentric=[scalar(x) for x in weights],
                window_inside=bool(window[i]),look=bool(look_ok[i]),uv=bool(uv_ok[i]),side=bool(side_ok[i]),supports=good))
            if good:support.append(int(g))
        return dict(status=int(actual[0]),by_hand_status=int(hand[0]),origin=start[0].tolist(),direction=u[0].tolist(),
            native_hit=dict(describe(mesh_kind,native_id[0]),depth=scalar(native_t[0])),candidates=candidates,support_faces=support)

    with (OUT/'lost-lines.jsonl').open('wb') as stream:
        for face in sorted(expected):
            measured=floor.measure(face,col)
            assert round(float(measured['lost']),1)==expected[face]['pixels'] and measured['at_least']==expected[face]['at_least']
            rays=0;lost_weight=0.0;old_lost_weight=0.0;num_lines=0;face_sites=set();face_unresolved=0
            for blk in face_pixels(b,face,views[col],caster_b):
                rays+=blk.rays
                if len(blk):
                    mask,reason,cover=floor._lost(face,col,views[col],blk)
                    weights=np.ones(len(blk)) if blk.weight is None else blk.weight
                    lost_weight+=float(weights[mask].sum())
                    for index in np.flatnonzero(mask):
                        p=blk.points[index];toward=blk.toward[index];bary=blk.bary[index]
                        one=replace(blk,points=p[None],toward=toward[None],reach=blk.reach[index:index+1],ij=blk.ij[index:index+1],
                            plane=blk.plane[index:index+1],t=blk.t[index:index+1],bary=bary[None],weight=weights[index:index+1])
                        oldmask,oldreason,oldcover=baseline._lost(face,col,views[col],one)
                        if oldmask[0]:old_lost_weight+=float(weights[index])
                        ed=present_details(je,'stage',face,p,toward,bary);ad=present_details(ja,'after',face,p,toward,bary)
                        contributors=[]
                        for g in ed['support_faces']:
                            cut_rows=[r for r in children.get(g,[]) if r['kind']=='cut_child']
                            if cut_rows:contributors.append(dict(site=g,original_source_triangle=int(ancestry[g]),children=cut_rows))
                        if not oldmask[0] and contributors:
                            face_sites.update(row['site'] for row in contributors)
                        else:face_unresolved+=1
                        row=dict(before_face=face,line_id=line_count,plane=int(blk.plane[index]),ij=blk.ij[index].tolist(),
                            weight=float(weights[index]),point_recentred=p.tolist(),point_engine=(p+centre).tolist(),barycentric=bary.tolist(),toward=toward.tolist(),
                            after_reason=int(reason[index]),after_cover_face=int(cover[index]),E3_lost=bool(oldmask[0]),E3_reason=int(oldreason[0]),
                            stage_present=ed,after_present=ad,potential_cut_contributors=contributors)
                        stream.write((json.dumps(row,sort_keys=True,allow_nan=False)+'\n').encode());line_count+=1;num_lines+=1
                if rays>=PIXEL_BUDGET and lost_weight>VISIBLE_FLOOR_PX and rays<blk.of_rays:break
            assert np.isclose(lost_weight,measured['lost'],rtol=0,atol=1e-10)
            summary.append(dict(face=face,reported_pixels=expected[face]['pixels'],reproduced_lost_weight=lost_weight,
                stage_lost_weight_on_exact_actual_lost_lines=old_lost_weight,lost_lines=num_lines,potential_sites=sorted(face_sites),unresolved_lines=face_unresolved))
            sites.update(face_sites);unresolved+=face_unresolved
    api.recheck(inputs);api.check(REPORT,REPORT_SHA);api.check(RECEIPT,RECEIPT_SHA)
    api.check(native_pin['path'],native_pin['sha256']);api.recheck(native)
    result=dict(diagnostic_only=True,acceptance=False,native_preservation_passed=False,source_report=dict(path=str(REPORT),sha256=REPORT_SHA),
        source_receipt=dict(path=str(RECEIPT),sha256=RECEIPT_SHA),input_binding=inputs,viewpoint=labels[col],view_column=col,
        depth_tolerance_inches=tol,pixel_inches=c.FLOOR_IN_PER_PX,visible_floor_px=VISIBLE_FLOOR_PX,pixel_budget=PIXEL_BUDGET,
        comparison_scope='Only current reported lost lines; baseline full floor was not rerun',faces=summary,potential_contributor_sites=sorted(sites),
        unresolved_lines=unresolved,lines=dict(path=str(OUT/'lost-lines.jsonl'),sha256=api.digest(OUT/'lost-lines.jsonl'),count=line_count),
        limitations=['Candidate cut support is mapped on exact default lost lines, not inferred from empty covering_faces',
            'Unchanged default floating predicates retained; any unresolved or baseline-lost line remains explicit; no acceptance verdict'])
    api.write(OUT/'attribution.json',result);print(str(OUT/'attribution.json'));print(api.digest(OUT/'attribution.json'))

if __name__=='__main__':main()
