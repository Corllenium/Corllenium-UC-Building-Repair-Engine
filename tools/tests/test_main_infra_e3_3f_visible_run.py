import copy,json
from pathlib import Path
import pytest
from engine.io.snapshot import sha256_file

POLICY=Path(__file__).resolve().parents[2]/'docs/superpowers/records/MAIN-INFRA-E3-3F-RETAIN-VISIBLE-20261024/policy.json'
def api():
    from tools import main_infra_e3_3f_visible_run
    return main_infra_e3_3f_visible_run

def pin(path=POLICY):return dict(path=str(path),sha256=sha256_file(path))

def test_actual_report_cohort_restores_native258_and_five_nonfailing_sites():
    p,e,retained=api().read_policy(pin())
    assert len(p['restore_sites'])==263 and len(p['native_sites'])==258
    assert p['subthreshold_extra_sites']==[190,265,267,358,984]
    assert e['signed_preservation_failure_sites']==[] and e['subthreshold_extras_are_failures'] is False
    assert len(e['original_records'])==1821 and len(e['native_changed_pixels'])==119
    assert len(retained)==p['original_counts']['site_faces'] and len(set(retained))==len(retained)
    assert set(p['required_faces'])<=set(retained)

@pytest.mark.parametrize('change',['missing','duplicate','unknown','native','subthreshold','faces','counts','audit','evidence','extra_field'])
def test_rehashed_policy_cannot_change_measured_cohort(tmp_path,change):
    p=json.loads(POLICY.read_text())
    if change=='missing':p['restore_sites'].pop()
    if change=='duplicate':p['restore_sites'].append(p['restore_sites'][0])
    if change=='unknown':p['restore_sites'][-1]=999999
    if change=='native':p['native_sites']=p['native_sites'][1:]
    if change=='subthreshold':p['subthreshold_extra_sites']=[]
    if change=='faces':p['required_faces']=p['required_faces'][1:]
    if change=='counts':p['original_counts']['rolled_back']=144
    if change=='audit':p['original_audit']['sha256']='0'*64
    if change=='evidence':p['evidence']['footprint']['sha256']='0'*64
    if change=='extra_field':p['claim_preservation_pass']=True
    path=tmp_path/'policy.json';path.write_text(json.dumps(p))
    with pytest.raises(ValueError):api().read_policy(pin(path))

def test_namespace_is_new_3f_only(tmp_path):
    base=tmp_path/'run-20261024-3F-retain-visible';api().check_namespace(base/'preparation-3F.json',base/'3F')
    for name in ['run-20261023-attempt2','run-20261024-1F-retain-visible']:
        with pytest.raises(ValueError):api().check_namespace(tmp_path/name/'preparation-3F.json',tmp_path/name/'3F')
    with pytest.raises(ValueError):api().check_namespace(base/'preparation-1F.json',base/'1F')

def test_original1820_verification_precedes_exact1412_ordered_selection(monkeypatch):
    from tools.main_infra_e3_replay import _original_edit
    from tools.main_infra_e7_checkpoint import typed_plan_digest
    m=api();p,e,retained=m.read_policy(pin());rows=e['original_records'][:-1]
    selected=[_original_edit(r,53602) for r in rows if not r.get('rolled_back',False) and r['site'] not in p['restore_sites']]
    seen={}
    def load(before,looks,candidate,**kwargs):
        seen.update(kwargs)
        return selected,dict(original_kept_sites=1675,restored_sites=p['restore_sites'],remaining_sites=1412,remaining_removed_triangles=sum(len(x.faces) for x in selected),fresh_site_check_required=True)
    monkeypatch.setattr(m,'load_replay_plan',load,raising=False)
    result=m.select_plan(None,None,p,e,retained)
    assert seen['restore_sites']==tuple(p['restore_sites'])
    assert result['selected']==1412 and result['selected_sites']==[x.site for x in selected]
    assert result['typed_plan_digest']==typed_plan_digest(selected)
    assert len(result['original_rolled_sites'])==145
    assert set(result['selected_sites']).isdisjoint(set(p['restore_sites'])|set(result['original_rolled_sites']))
    assert result['retained_source_faces']==retained and result['old_verdict_is_not_reused'] is True
