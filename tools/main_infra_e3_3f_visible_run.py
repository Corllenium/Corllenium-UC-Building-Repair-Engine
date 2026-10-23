"""Evidence-bound 3F E3 retention profile; existing checked replay owns repairs."""
import json
from pathlib import Path
from tools import main_infra_e3_visible_run as common
from tools.main_infra_e3_replay import load_replay_plan
from tools.main_infra_e7_checkpoint import typed_plan_digest
from tools.main_infra_e7_serialization import _encode,_read

ROOT=Path(__file__).resolve().parents[1]
FLOOR='3F'
RUN_ID='MAIN-INFRA-E3-3F-retain-visible-20261024'
NAMESPACE='run-20261024-3F-retain-visible'
REVISION=common.REVISION
AUDIT_SHA='56ab090d861106c2801b2dab057ba5e9df6109ac69d87faaf29b718c87389512'
EVIDENCE_SHA=dict(footprint='63eb9d4b3c757adc6a33794f133820b9e670d03185057bd7fae06c30b3f431a1',native='33d60ae794dac1d43033083d63f2365409f72573ec82ef1fd6bb5a6e2533d94a',report='524876c6a356898d8136e9647562317f6f89a74edb752d81080c0a9b51a689e0',receipt='f8ac4b971295c8845fc99241be2305d4b6992aa319b3f41c733db78efa439791',completion='a8ab845148398b583c0e229e1f5568e043bcd97d7c79afd5a1c1706528668f75')


def read_policy(pin):
    common._pin(pin);p=_read(pin['path'])
    required={'schema_version','policy','run_id','floor','source_revision','restore_sites','native_sites','subthreshold_extra_sites','required_faces','original_counts','original_audit','evidence'}
    if (set(p)!=required or p['schema_version']!=1 or p['policy']!='retain_whole_original_e3_sites_v1'
            or p['run_id']!=RUN_ID or p['floor']!=FLOOR or p['source_revision']!=REVISION
            or p['original_counts']!=dict(planned=1820,kept=1675,rolled_back=145,site_faces=6281)
            or p['original_audit']['sha256']!=AUDIT_SHA or set(p['evidence'])!=set(EVIDENCE_SHA)
            or any(p['evidence'][k]['sha256']!=v for k,v in EVIDENCE_SHA.items())):
        raise ValueError('exact3F evidence-bound retention policy required')
    common._pin(p['original_audit'])
    for row in p['evidence'].values():common._pin(row)
    f,n,s,d,c=(_read(p['evidence'][key]['path']) for key in ('footprint','native','report','receipt','completion'))
    old=Path(p['original_audit']['path']).parent;audit=_read(old/'stage-audit.json')
    for name,key in [('edit-log.jsonl','edit_log_sha256'),('source-faces.json','source_faces_sha256'),('candidate.engine.obj','engine_candidate_sha256'),('candidate.source.obj','source_candidate_sha256')]:common._hash(old/name,audit[key])
    records=[json.loads(line) for line in (old/'edit-log.jsonl').read_text().splitlines()]
    rows=records[:-1];by_site={row['site']:row for row in rows};kept={row['site']:row for row in rows if not row.get('rolled_back',False)}
    rolled=sorted(row['site'] for row in rows if row.get('rolled_back',False));owner={face:row['site'] for row in rows for face in row['faces']}
    if (len(records)!=1821 or len(by_site)!=1820 or len(kept)!=1675 or len(rolled)!=145
            or records[-1]!={'check':audit['checks'][0]} or f['actual_kernel_rollback_sites']!=rolled
            or audit['input_triangles']!=53602 or audit['output_triangles']!=38691
            or f['schema_version']!=1 or f['diagnostic_only'] is not True or f['acceptance'] is not False
            or f['native_preservation_passed'] is not False or f['original_source_triangles']!=53602
            or f['candidate_source_triangles']!=38691 or f['removed_source_triangles']!=14911
            or f['actual_kept_e3_sites']!=1675 or f['qualified_changed_pixels']!=119 or f['qualified_changed_views']!=8
            or n['native_preservation_passed'] is not False or n['floor_id']!='3F'
            or n['before_sha256']!=audit['input_receipt']['engine_obj_sha256'] or n['after_sha256']!=audit['engine_candidate_sha256']
            or n['source_after_sha256']!=audit['source_candidate_sha256']):
        raise ValueError('original3F audit/native footprint cohort differs')
    for path,digest in f['input_sha256'].items():common._hash(Path(path),digest)
    for key,value in n['paths'].items():common._hash(Path(value),n['hashes'][key])
    if (not common._same_pin(d['native_failure_retained'],p['evidence']['native'])
            or d['validation_json_sha256']!=p['evidence']['report']['sha256']
            or not common._same_pin(c['validation'],p['evidence']['report'])
            or not common._same_pin(c['diagnostic_receipt'],p['evidence']['receipt'])
            or not common._same_pin(c['native_footprint'],p['evidence']['footprint'])
            or c['signed_preservation_failure_contributor_sites']!=[]
            or c['input_mismatches']!=[] or c['acceptance'] is not False
            or d['acceptance'] is not False or d['publication_eligible'] is not False
            or s['inputs']['before_sha256']!=n['before_sha256'] or s['inputs']['after_sha256']!=n['after_sha256']):
        raise ValueError('actual signed/native context differs')
    native=f['conservative_whole_kept_sites']
    if len(native)!=258 or native!=sorted(set(native)) or not set(native)<=set(kept):raise ValueError('whole native site cohort required')
    whole=f['whole_site_original_faces']
    if [row['site'] for row in whole]!=native or any(row['original_source_triangles']!=kept[row['site']]['faces'] for row in whole):raise ValueError('whole native source face cohort differs')
    changed=[];mapped=set();qual={v['name']:v for v in n['qualified_owner_views']['views'] if v['different_pixels']}
    if len(f['views'])!=8 or {v['name'] for v in f['views']}!=set(qual):raise ValueError('complete qualified native views required')
    for view in f['views']:
        pixels=view['changed_pixels'];covered=set()
        if view['qualified'] is not True or view['camera']['name']!=view['name'] or len(pixels)!=qual[view['name']]['different_pixels'] or view['whole_pixel_padding']!=2 or view['removed_faces_screened_per_variant']!=14911:raise ValueError('actual native pixel cohort differs')
        changed.extend((view['name'],row['x'],row['y']) for row in pixels)
        for row in view['intersections']:
            site=row['kept_e3_site'];face=row['original_source_triangle'];indices=row['changed_pixel_indices']
            if (site not in native or owner.get(face)!=site or row['variant'] not in ('source_float64','import_float32')
                    or not indices or len(set(indices))!=len(indices) or any(type(i) is not int or not 0<=i<len(pixels) for i in indices)):
                raise ValueError('native source lineage/pixel mapping differs')
            covered.update(indices);mapped.add(site)
        if covered!=set(range(len(pixels))):raise ValueError('unmapped qualified changed pixel')
    if len(changed)!=119 or len(set(changed))!=119 or mapped!=set(native):raise ValueError('complete119pixel/native258 cohort required')
    floor=s['checks']['nothing_deleted']['floor'];positive={row['face']:row for row in floor['measured'] if row['pixels']>0}
    witnesses=c['subthreshold_visible_removed_witnesses']
    if (floor['status']!='PASS' or floor['floor_px']!=4 or floor['in_per_px']!=.02 or floor['faces_failed']!=0
            or s['checks']['textures']['status']!='PASS' or s['checks']['nothing_deleted']['status']!='PASS'
            or len(witnesses)!=len(positive) or {w['original_source_triangle'] for w in witnesses}!=set(positive)):
        raise ValueError('signed subthreshold witnesses must remain nonfailures')
    for w in witnesses:
        actual=positive[w['original_source_triangle']]
        if (w['fails'] is not False or actual['fails'] is not False or not 0<w['pixels']<=4
                or w['pixels']!=actual['pixels'] or w['crop']!=actual['crop']
                or owner.get(w['original_source_triangle'])!=w['kept_e3_site']
                or w['already_in_native_conservative_union']!=(w['kept_e3_site'] in native)):
            raise ValueError('actual nonfailing signed source witness differs')
    extras=sorted({w['kept_e3_site'] for w in witnesses}-set(native));restore=sorted(set(native)|set(extras))
    retained=sorted(face for site in restore for face in kept[site]['faces'])
    if (extras!=[190,265,267,358,984] or len(restore)!=263 or len(retained)!=6281 or len(set(retained))!=6281
            or p['restore_sites']!=restore or p['native_sites']!=native or p['subthreshold_extra_sites']!=extras
            or p['required_faces']!=sorted(positive) or not set(positive)<=set(retained)):
        raise ValueError('exact263 whole-site restoration union required')
    evidence=dict(original_records=records,native_changed_pixels=changed,signed_preservation_failure_sites=[],subthreshold_extras_are_failures=False)
    return p,evidence,retained


def check_namespace(plan_path,out):
    plan_path,out=Path(plan_path),Path(out)
    if plan_path.name!='preparation-3F.json' or out.name!=FLOOR or plan_path.parent.resolve()!=out.parent.resolve() or out.parent.name!=NAMESPACE:
        raise ValueError('new visible3F E3 preparation/output namespace required')


def select_plan(before,looks,policy,evidence,retained):
    restore=tuple(policy['restore_sites'])
    edits,replay=load_replay_plan(before,looks,Path(policy['original_audit']['path']).parent,expected_audit_sha256=policy['original_audit']['sha256'],restore_sites=restore)
    rolled=[r['site'] for r in evidence['original_records'][:-1] if r.get('rolled_back',False)]
    if (len(edits)!=1412 or replay['original_kept_sites']!=1675 or replay['restored_sites']!=list(restore)
            or replay['remaining_sites']!=1412 or replay['remaining_removed_triangles']!=8630
            or replay['fresh_site_check_required'] is not True or len(rolled)!=145
            or any(e.site in {*restore,*rolled} or set(e.faces)&set(retained) for e in edits)):
        raise ValueError('verified original3F E3 subset differs')
    return dict(replay=replay,original_counts=policy['original_counts'],original_rolled_sites=rolled,
        native_restored_sites=policy['native_sites'],nonfailing_subthreshold_restored_sites=policy['subthreshold_extra_sites'],
        signed_preservation_failure_sites=[],retained_source_faces=retained,required_faces=policy['required_faces'],selected=len(edits),selected_sites=[e.site for e in edits],typed_plan_digest=typed_plan_digest(edits),selected_edits=[dict(_encode(e),decision=e.decision) for e in edits],all_original_records_verified=True,old_verdict_is_not_reused=True)
