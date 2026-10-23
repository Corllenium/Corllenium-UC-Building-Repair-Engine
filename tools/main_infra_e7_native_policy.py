"""Conservative whole-site exclusions bound to failed native evidence."""
import hashlib
from pathlib import Path

from tools.main_infra_e3_binding import _hash
from tools.main_infra_e7_checkpoint import typed_plan_digest
from tools.main_infra_e7_serialization import _dump, _encode, _read
from tools.main_infra_e7_subset import VerifiedSubset, _seal, _verify_plan

RUN_ID='MAIN-INFRA-E7-1F-attempt4-20261024'
POLICY='exclude_failed_native_and_signed_sites_v1'


def _read_policy(pin):
    if not isinstance(pin,dict) or set(pin)!={'path','sha256'}:
        raise ValueError('exact external policy pin required')
    _hash(Path(pin['path']),pin['sha256'])
    policy=_read(pin['path'])
    if (set(policy)!={'schema_version','policy','run_id','failed_attempt','counts','excluded_sites','evidence'}
            or policy['schema_version']!=1 or policy['policy']!=POLICY or policy['run_id']!=RUN_ID):
        raise ValueError('native policy schema/identity differs')
    if set(policy['evidence'])!={'native','pixels','rays','lineage','signed_report','signed_receipt','contributors'}:
        raise ValueError('complete native evidence inventory required')
    evidence={}
    for key,row in policy['evidence'].items():
        if set(row)!={'path','sha256'}:
            raise ValueError('evidence pin differs')
        _hash(Path(row['path']),row['sha256']);evidence[key]=_read(row['path'])
    return policy,evidence


def _native_sites(policy,evidence,subset):
    native,pixels,rays,lineage=(evidence[k] for k in ('native','pixels','rays','lineage'))
    failed=policy['failed_attempt']
    fields={'run_id','preparation_sha256','cut_receipt_sha256','source_after_sha256',
        'after_sha256','before_source_sha256','source_revision'}
    if set(failed)!=fields or any(native.get('engine_run_id' if k=='run_id' else k)!=v for k,v in failed.items()):
        raise ValueError('failed attempt cohort differs')
    if (native.get('floor_id')!='1F' or native.get('acceptance') is not False
            or native.get('selection_seal')!=subset.seal
            or native.get('selection_digest')!=hashlib.sha256(_dump(subset.proof).encode()).hexdigest()
            or native.get('qualified_owner_views',{}).get('passed') is not False
            or pixels.get('native_receipt_sha256')!=policy['evidence']['native']['sha256']
            or pixels.get('native_preservation_passed') is not False or pixels.get('acceptance') is not False):
        raise ValueError('failed native donor binding differs')
    if (rays.get('source_hashes')!=dict(before=failed['before_source_sha256'],after=failed['source_after_sha256'],
            lineage=policy['evidence']['lineage']['sha256'])
            or rays.get('triangle_counts')!=dict(before=native['original_source_triangles'],after=native['output_triangles'])
            or 'approximate' not in rays.get('purpose','') or not rays.get('limitations')):
        raise ValueError('analytic ray source/limitations differ')
    expected={}
    for name,rows in pixels['all_qualified_changed_pixels'].items():
        for row in rows:
            key=(name,row['x'],row['y'])
            if key in expected:raise ValueError('duplicate pixel evidence')
            expected[key]=(row['before'],row['after'])
    native_views={r['name']:r['different_pixels'] for r in native['qualified_owner_views']['views']}
    if any(sum(k[0]==name for k in expected)!=count for name,count in native_views.items()):
        raise ValueError('native per-view pixel cohort differs')
    if set(k[0] for k in expected)-set(native_views):raise ValueError('unknown native viewpoint')
    summary=pixels['summary']['qualified']
    if (summary['different_pixels']!=len(expected) or summary['rgb_changed']!=len(expected)
            or summary['alpha_changed']!=0 or summary['silhouette_occupancy_changed']!=0):
        raise ValueError('native pixel summary differs')
    if lineage.get('schema_version')!=1 or lineage.get('mode')!='original_source_existing_vertex_cuts':
        raise ValueError('actual saved cut-lineage schema required')
    table={row['output_face']:row for row in lineage['faces']}
    if len(table)!=len(lineage['faces']):raise ValueError('duplicate output lineage')
    donor_sites={edit.site:i for i,edit in enumerate(subset.edits)}
    seen=set();sites=set()
    for row in rays['rows']:
        key=(row['name'],*row['xy'])
        if key in seen or key not in expected or expected[key]!=(row['before_rgba'],row['after_rgba']):
            raise ValueError('duplicate or mismatched ray pixel cohort')
        seen.add(key);site=None
        for variant in ('original_float64','import_vertex_float32'):
            before=row['hits']['before_'+variant];after=row['hits']['after_'+variant]
            lin=after['lineage'];candidate_site=lin['site']
            if (type(candidate_site) is not int or candidate_site not in donor_sites
                    or lin!=table.get(after['face']) or lin.get('kind')!='cut_child'
                    or lin['stage_input_face']!=candidate_site or lin['edit_index']!=donor_sites[candidate_site]
                    or lin['original_source_triangle']!=before['face']
                    or lin['material']!=before['material'] or lin['material']!=after['material']):
                raise ValueError('ray source/material/site lineage differs')
            if site is not None and site!=candidate_site:raise ValueError('ray variants disagree on site')
            site=candidate_site
        sites.add(site)
    if seen!=set(expected):raise ValueError('incomplete ray pixel cohort')
    return sites,len(seen)


def _signed_sites(policy,evidence,subset):
    report,receipt,mapping=(evidence[k] for k in ('signed_report','signed_receipt','contributors'))
    native=evidence['native'];table={row['output_face']:row for row in evidence['lineage']['faces']}
    ranks={edit.site:i for i,edit in enumerate(subset.edits)}
    if (mapping.get('source_report')!=policy['evidence']['signed_report']
            or mapping.get('source_receipt')!=policy['evidence']['signed_receipt']
            or receipt.get('validation_json_sha256')!=policy['evidence']['signed_report']['sha256']
            or report.get('verdict')!='FAIL' or receipt.get('verdict')!='FAIL'
            or mapping.get('diagnostic_only') is not True or mapping.get('acceptance') is not False
            or receipt.get('diagnostic_only') is not True or receipt.get('acceptance') is not False
            or mapping.get('before_sha256')!=native['before_sha256']
            or mapping.get('after_sha256')!=native['after_sha256']
            or report['inputs']['before_sha256']!=native['before_sha256']
            or report['inputs']['after_sha256']!=native['after_sha256']
            or mapping.get('lineage_sha256')!=policy['evidence']['lineage']['sha256']
            or mapping.get('default_settings')!=report['settings']
            or mapping.get('default_settings')!=receipt['default_settings']):
        raise ValueError('signed failed-attempt/default-settings binding differs')
    def site_of(row):
        lin=row['lineage'];site=lin['site']
        if (type(site) is not int or site not in ranks or lin!=table.get(row['covering_after_face'])
                or lin.get('kind')!='cut_child' or lin['stage_input_face']!=site or lin['edit_index']!=ranks[site]):
            raise ValueError('signed covering lineage/site differs')
        return site
    samples={row['global_sample_id']:row for row in mapping['covered_samples']}
    texture=report['checks']['textures']
    reported_faces={face for site in report['sites'] if 'textures' in site['checks']
        and site['reasons'].get('covered',0)>0 for face in site['faces']}
    if ({row['before_face'] for row in samples.values()}!=reported_faces
            or round(sum(row['area_in2'] for row in samples.values()),2)!=texture['area_failed_in2']):
        raise ValueError('signed exact covered-face/area cohort differs')
    if (len(samples)!=len(mapping['covered_samples']) or len(samples)!=texture['samples_failed']
            or len({s['before_face'] for s in samples.values()})!=texture['faces_failed']):
        raise ValueError('signed covered-sample cohort differs')
    seen=set();covered=set();texture_sites=set();covering_faces=set()
    for row in mapping['blocked_lines']:
        sample=row['global_sample_id'];key=(sample,row['standard_view_column'])
        if key in seen or sample not in samples or samples[sample]['before_face']!=row['before_face']:
            raise ValueError('duplicate/unknown signed blocked sample')
        seen.add(key);covered.add(sample);texture_sites.add(site_of(row));covering_faces.add(row['covering_after_face'])
    if (covered!=set(samples) or sorted(texture_sites)!=mapping['texture_contributor_sites']
            or sorted(covering_faces)!=mapping['texture_covering_faces']):
        raise ValueError('incomplete signed texture contributors')
    expected={(r['face'],face):r['pixels'] for r in report['checks']['nothing_deleted']['floor']['failing']
        for face in r['covering_faces'] if r['fails'] is True}
    floor_seen=set();floor_sites=set()
    for row in mapping['floor_failures']:
        key=(row['before_face'],row['covering_after_face'])
        if key in floor_seen or key not in expected or row['pixels']!=expected[key]:
            raise ValueError('signed floor covering cohort differs')
        floor_seen.add(key);floor_sites.add(site_of(row))
    sites=texture_sites|floor_sites
    if floor_seen!=set(expected) or sorted(sites)!=mapping['all_signed_contributor_sites']:
        raise ValueError('incomplete signed contributor union')
    return sites

def apply_native_policy(before,looks,subset,pin):
    _verify_plan(before,looks,subset)
    if (subset.proof.get('policy')!='original_donor_kept_in_original_order_v1'
            or subset.proof.get('all_original_K1_records_match') is not True
            or subset.proof.get('old_verdict_is_not_reused') is not True):
        raise ValueError('original verified donor selection required before exclusions')
    policy,evidence=_read_policy(pin)
    native_sites,pixel_count=_native_sites(policy,evidence,subset)
    signed_sites=_signed_sites(policy,evidence,subset)
    sites=native_sites|signed_sites
    declared=policy['excluded_sites'];counts=policy['counts']
    if (any(type(x) is not int for x in declared) or len(set(declared))!=len(declared)
            or declared!=sorted(sites)):
        raise ValueError('duplicate/unknown/mismatched policy sites')
    edits=tuple(e for e in subset.edits if e.site not in sites)
    expected=dict(donor_planned=subset.proof['donor_planned'],donor_kept=len(subset.edits),
        donor_rolled_back=len(subset.proof['excluded_sites']),pixels=pixel_count,native_excluded=len(native_sites),signed_excluded=len(signed_sites),
        signed_covered_samples=len(evidence['contributors']['covered_samples']),
        signed_blocked_lines=len(evidence['contributors']['blocked_lines']),
        signed_floor_lines=len(evidence['contributors']['floor_failures']),excluded=len(sites),retained=len(edits))
    if counts!=expected:raise ValueError('policy counts differ from verified donor/native cohort')
    indices=[i for i,e in enumerate(subset.edits) if e.site not in sites]
    proof=dict(subset.proof,policy=POLICY,donor_selection=subset.proof,
        selected=len(edits),selected_sites=[e.site for e in edits],
        selected_donor_indices=[subset.proof['selected_donor_indices'][i] for i in indices],
        native_policy_excluded_sites=sorted(native_sites),signed_policy_excluded_sites=sorted(signed_sites),
        policy_excluded_sites=declared,
        native_policy=dict(pin=pin,evidence=policy['evidence'],mapped_rows=evidence['rays']['rows'],
            signed_blocked_lines=evidence['contributors']['blocked_lines'],
            signed_floor_failures=evidence['contributors']['floor_failures'],
            attribution_is_approximate=True,limitations=evidence['rays']['limitations']),
        typed_plan_digest=typed_plan_digest(edits),
        selected_edits=[dict(_encode(e),decision=e.decision) for e in edits])
    return VerifiedSubset(edits,proof,_seal(proof,edits))
