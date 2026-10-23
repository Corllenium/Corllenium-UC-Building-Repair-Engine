import copy,json
from pathlib import Path
import pytest
from data.tmp.three_f_native_phase import assess

def controls():
    p=json.loads(Path('docs/superpowers/records/MAIN-INFRA-3F-VALIDATE-ATTEMPT2-20261024/preparation.json').read_bytes())
    comparison=Path(p['paths']['native_control_report'])
    return json.loads(Path(p['paths']['native_poses']).read_bytes())['poses'],json.loads(comparison.read_bytes()),json.loads(comparison.with_name('png-readback.json').read_bytes())

def test_actual_retained_import_control_cohort():
    q,d=assess(*controls());assert q['passed'] is True and q['count']==33 and d['count']==13

@pytest.mark.parametrize('change',['missing_comparison','missing_png','duplicate_png','relabel_png','wrong_count'])
def test_native_metadata_cohort_drift_is_refused(change):
    poses,c,p=controls()
    if change=='missing_comparison':c['views'].pop()
    if change=='missing_png':p['views'].pop()
    if change=='duplicate_png':p['views'][-1]=p['views'][0]
    if change=='relabel_png':p['views'][0]['name']='unknown'
    if change=='wrong_count':p['png_pairs_readback']=45
    with pytest.raises(ValueError):assess(poses,c,p)

def test_one_actual_qualified_byte_change_is_fail():
    poses,c,p=controls();next(v for v in p['views'] if v['name']=='view_0_0_1')['different_pixels']=1
    q,d=assess(poses,c,p);assert q['passed'] is False

def test_diagnostic_change_is_kept_separate():
    poses,c,p=controls();next(v for v in p['views'] if v['name']=='eye_0')['different_pixels']=100
    q,d=assess(poses,c,p);assert q['passed'] is True and any(v['different_pixels'] for v in d['views'])
