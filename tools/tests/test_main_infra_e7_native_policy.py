from dataclasses import replace
import hashlib
import gc
import json
from pathlib import Path

import pytest

from engine.io.snapshot import sha256_file
from tools.main_infra_e7_checkpoint import typed_plan_digest
from tools.main_infra_e7_serialization import _dump, _encode
from tools.main_infra_e7_subset import VerifiedSubset, _seal, _look_ids
from tools.main_infra_e3 import _source_digest
from tools.tests.test_main_infra_e7_serialization import fixture


def apply(case):
    from tools.main_infra_e7_native_policy import apply_native_policy
    return apply_native_policy(case['before'],case['looks'],case['subset'],case['pin'])


def rewrite(case,key):
    path=Path(case['policy']['evidence'][key]['path'])
    path.write_text(json.dumps(case[key]))
    case['policy']['evidence'][key]['sha256']=sha256_file(path)
    write_policy(case)


def write_policy(case):
    path=Path(case['pin']['path']);path.write_text(json.dumps(case['policy']))
    case['pin']['sha256']=sha256_file(path)


@pytest.fixture
def case(tmp_path):
    source,engine,before,ancestry,outcome,looks,inputs=fixture(tmp_path,mixed=True)
    edits=tuple(replace(outcome.kept[0],site=i,faces=(i,)) for i in range(273))
    proof=dict(schema_version=1,policy='original_donor_kept_in_original_order_v1',
        before_digest=_source_digest(before).hex(),donor_planned=628,selected=273,
        selected_donor_indices=list(range(273)),selected_sites=list(range(273)),
        excluded_sites=list(range(273,628)),all_original_K1_records_match=True,
        old_verdict_is_not_reused=True,typed_plan_digest=typed_plan_digest(edits),
        selected_edits=[dict(_encode(e),decision=e.decision) for e in edits],
        look_ids={str(k):v for k,v in _look_ids(before,looks).items()})
    subset=VerifiedSubset(edits,proof,_seal(proof,edits))
    failed=dict(run_id='MAIN-INFRA-E7-1F-attempt3-20261023',preparation_sha256='a'*64,
        cut_receipt_sha256='b'*64,source_after_sha256='c'*64,after_sha256='d'*64,
        before_source_sha256='e'*64,source_revision='f'*64)
    native=dict(failed,engine_run_id=failed.pop('run_id'),floor_id='1F',acceptance=False,before_sha256='1'*64,
        original_source_triangles=15856,stage_input_triangles=10136,output_triangles=10578,
        selection_digest=hashlib.sha256(_dump(proof).encode()).hexdigest(),selection_seal=subset.seal,
        qualified_owner_views=dict(count=1,passed=False,views=[dict(name='view',different_pixels=335)]))
    failed['run_id']=native['engine_run_id'];native.pop('run_id',None)
    lineage=[];rows=[];pixels=[]
    for i in range(335):
        site=i%92
        lin=dict(output_face=1000+site,kind='cut_child',site=site,stage_input_face=site,
            original_source_triangle=2000+site,material='fixture',edit_index=site)
        if i<92:lineage.append(lin)
        before_hit=dict(face=2000+site,material='fixture')
        after_hit=dict(face=1000+site,material='fixture',lineage=lin)
        rows.append(dict(name='view',xy=[i,0],before_rgba=[1,2,3,255],after_rgba=[2,2,3,255],
            hits=dict(before_original_float64=before_hit,before_import_vertex_float32=before_hit,
                after_original_float64=after_hit,after_import_vertex_float32=after_hit)))
        pixels.append(dict(x=i,y=0,before=[1,2,3,255],after=[2,2,3,255]))
    signed_sites=[90,91]+list(range(100,109))
    for site in range(100,109):
        lineage.append(dict(output_face=1000+site,kind='cut_child',site=site,stage_input_face=site,
            original_source_triangle=2000+site,material='fixture',edit_index=site))
    for child in range(4):
        lineage.append(dict(output_face=2000+child,kind='cut_child',site=108,stage_input_face=108,
            original_source_triangle=2108,material='fixture',edit_index=108))
    paths={key:tmp_path/(key+'.json') for key in ('native','pixels','rays','lineage')}
    pixel=dict(native_receipt_sha256='',acceptance=False,native_preservation_passed=False,
        summary={'qualified':dict(views=1,changed_views=1,different_pixels=335,rgb_changed=335,alpha_changed=0,silhouette_occupancy_changed=0)},
        all_qualified_changed_pixels={'view':pixels})
    ray=dict(purpose='diagnostic only; approximate analytic pixel-center rays, not native GPU rasterizer primitive IDs',
        limitations=['fixture approximation; no GPU primitive proof'],
        source_hashes=dict(before='e'*64,after='c'*64,lineage=''),
        triangle_counts=dict(before=15856,after=10578),rows=rows)
    case=dict(before=before,looks=looks,subset=subset,native=native,pixels=pixel,rays=ray,
        lineage={'schema_version':1,'mode':'original_source_existing_vertex_cuts','input_sha256':{},'faces':lineage},pin={'path':str(tmp_path/'policy.json'),'sha256':''})
    for key in ('native','lineage'):paths[key].write_text(json.dumps(case[key]))
    pixel['native_receipt_sha256']=sha256_file(paths['native'])
    ray['source_hashes']['lineage']=sha256_file(paths['lineage'])
    for key in ('pixels','rays'):paths[key].write_text(json.dumps(case[key]))
    case['policy']=dict(schema_version=1,policy='exclude_failed_native_and_signed_sites_v1',
        run_id='MAIN-INFRA-E7-1F-attempt4-20261024',failed_attempt=failed,
        counts=dict(donor_planned=628,donor_kept=273,donor_rolled_back=355,pixels=335,native_excluded=92,signed_excluded=11,signed_covered_samples=10,signed_blocked_lines=27,signed_floor_lines=4,excluded=101,retained=172),
        excluded_sites=list(range(92))+list(range(100,109)),evidence={key:dict(path=str(path),sha256=sha256_file(path)) for key,path in paths.items()})
    settings={'n_directions':128,'n_cameras':24,'n_extra_directions':1024}
    floor=[dict(face=9809,covering_faces=[2000,2001],pixels=11.5,fails=True),
        dict(face=10366,covering_faces=[2002,2003],pixels=6.2,fails=True)]
    report=dict(verdict='FAIL',inputs=dict(before_sha256='1'*64,after_sha256='d'*64),settings=settings,
        sites=[dict(faces=[8563,8564,8633,8634],checks=['textures','nothing_deleted'],reasons={'covered':10},samples=10,area_in2=232.5)],
        checks=dict(textures=dict(status='FAIL',samples_failed=10,faces_failed=4,area_failed_in2=232.5),
            nothing_deleted={'floor':dict(status='FAIL',failing=floor)}))
    receipt=dict(verdict='FAIL',diagnostic_only=True,acceptance=False,floor_accepted=False,
        default_settings=settings,validation_json_sha256='')
    covered=[dict(global_sample_id=i,before_face=[8563,8564,8633,8634][i%4],area_in2=23.25) for i in range(10)]
    blocks=[]
    for i in range(27):
        site=signed_sites[i%10]
        lin=next(row for row in lineage if row['output_face']==1000+site)
        blocks.append(dict(global_sample_id=i%10,before_face=covered[i%10]['before_face'],
            standard_view_column=i,covering_after_face=1000+site,lineage=lin))
    floor_rows=[dict(before_face=row['face'],pixels=row['pixels'],covering_after_face=face,
        lineage=next(lin for lin in lineage if lin['output_face']==face)) for row in floor for face in row['covering_faces']]
    for key,value in (('signed_report',report),('signed_receipt',receipt)):
        paths[key]=tmp_path/(key+'.json');paths[key].write_text(json.dumps(value));case[key]=value
    receipt['validation_json_sha256']=sha256_file(paths['signed_report'])
    paths['signed_receipt'].write_text(json.dumps(receipt))
    contributors=dict(diagnostic_only=True,acceptance=False,native_preservation_passed=False,
        source_report=dict(path=str(paths['signed_report']),sha256=sha256_file(paths['signed_report'])),
        source_receipt=dict(path=str(paths['signed_receipt']),sha256=sha256_file(paths['signed_receipt'])),
        before_sha256='1'*64,after_sha256='d'*64,lineage_sha256=sha256_file(paths['lineage']),
        default_settings=settings,selected_samples=100,covered_samples=covered,blocked_lines=blocks,
        texture_covering_faces=sorted({r['covering_after_face'] for r in blocks}),
        texture_contributor_sites=sorted(signed_sites[:10]),floor_failures=floor_rows,
        all_signed_contributor_sites=sorted(signed_sites))
    paths['contributors']=tmp_path/'contributors.json';paths['contributors'].write_text(json.dumps(contributors))
    case['contributors']=contributors
    for key in ('signed_report','signed_receipt','contributors'):
        case['policy']['evidence'][key]=dict(path=str(paths[key]),sha256=sha256_file(paths[key]))
    write_policy(case)
    yield case
    gc.collect()


def test_native_signed_union_leaves_172_identical_ordered_edits_and_preserves_donor_partition(case):
    filtered=apply(case);original=case['subset']
    assert [e.site for e in filtered.edits]==list(range(92,100))+list(range(109,273))
    assert all(got is old for got,old in zip(filtered.edits,original.edits[92:100]+original.edits[109:]))
    assert filtered.proof['donor_selection']==original.proof
    assert filtered.proof['excluded_sites']==list(range(273,628))
    assert filtered.proof['native_policy_excluded_sites']==list(range(92))
    assert filtered.proof['signed_policy_excluded_sites']==[90,91]+list(range(100,109))
    assert filtered.proof['policy_excluded_sites']==list(range(92))+list(range(100,109))
    assert len(filtered.proof['native_policy']['signed_blocked_lines'])==27
    assert len(filtered.proof['native_policy']['signed_floor_failures'])==4
    assert len(filtered.proof['native_policy']['mapped_rows'])==335
    assert filtered.proof['native_policy']['attribution_is_approximate'] is True
    assert filtered.proof['native_policy']['limitations']==case['rays']['limitations']
    assert filtered.proof['old_verdict_is_not_reused'] is True
    assert case['subset'].proof['selected']==273


@pytest.mark.parametrize('key',['native','pixels','rays','lineage','signed_report','signed_receipt','contributors'])
def test_evidence_byte_drift_is_rejected(case,key):
    Path(case['policy']['evidence'][key]['path']).write_text('changed')
    with pytest.raises(ValueError,match='hash'):apply(case)


@pytest.mark.parametrize('change',['duplicate_site','unknown_site','wrong_run','duplicate_pixel','missing_pixel','wrong_parent','wrong_material','wrong_site','wrong_donor_seal','extra_policy_field'])
def test_rehashed_but_wrong_cohort_or_policy_is_rejected(case,change):
    if change=='duplicate_site':case['policy']['excluded_sites'][1]=0
    if change=='unknown_site':case['policy']['excluded_sites'][0]=999
    if change=='wrong_run':case['native']['engine_run_id']='other';rewrite(case,'native')
    if change=='duplicate_pixel':case['rays']['rows'][1]=case['rays']['rows'][0];rewrite(case,'rays')
    if change=='missing_pixel':case['rays']['rows'].pop();rewrite(case,'rays')
    if change=='wrong_parent':case['rays']['rows'][0]['hits']['before_original_float64']['face']=999;rewrite(case,'rays')
    if change=='wrong_material':case['rays']['rows'][0]['hits']['after_original_float64']['material']='other';rewrite(case,'rays')
    if change=='wrong_site':case['rays']['rows'][0]['hits']['after_original_float64']['lineage']['site']=999;rewrite(case,'rays')
    if change=='wrong_donor_seal':case['native']['selection_seal']='0'*64;rewrite(case,'native')
    if change=='extra_policy_field':case['policy']['unchecked_sites']=[999]
    write_policy(case)
    with pytest.raises(ValueError):apply(case)


def test_policy_byte_drift_is_rejected(case):
    Path(case['pin']['path']).write_text('{}')
    with pytest.raises(ValueError,match='hash'):apply(case)

@pytest.mark.parametrize('change',['missing_block','wrong_covering','unknown_signed_site','signed_default_drift'])
def test_signed_failure_cohort_cannot_be_reclassified(case,change):
    if change=='missing_block':case['contributors']['blocked_lines'].pop()
    if change=='wrong_covering':case['contributors']['floor_failures'][0]['covering_after_face']=9999
    if change=='unknown_signed_site':case['contributors']['all_signed_contributor_sites'].append(999)
    if change=='signed_default_drift':case['contributors']['default_settings']={'n_directions':1}
    rewrite(case,'contributors')
    with pytest.raises(ValueError):apply(case)
@pytest.mark.parametrize('change',['consistent_wrong_faces','wrong_replayed_area'])
def test_signed_exact_face_and_area_cohort_is_bound(case,change):
    if change=='consistent_wrong_faces':
        for row in case['contributors']['covered_samples']:row['before_face']+=100
        for row in case['contributors']['blocked_lines']:row['before_face']+=100
    else:
        case['contributors']['covered_samples'][0]['area_in2']+=1
    rewrite(case,'contributors')
    with pytest.raises(ValueError,match='face|area|cohort'):apply(case)