"""Execute only the reviewed3F native plan and read saved PNGs; no model changes."""
import importlib.util,json,subprocess,time,traceback
from pathlib import Path
from types import SimpleNamespace
from tools import main_infra_2f_validation as core
ROOT=Path(__file__).resolve().parents[2]
OUT=ROOT/'data/main-infra-3f-validation/run-20261024-attempt2/3F/native'
PLAN=OUT/'native-plan.json'
PLAN_SHA='6ae017fd48e9f75cc69a8c5e783961c8947fb62bce16d87b45f5f56c0c4f3ec8'
GUARD=OUT.parent/'guard/independent-guard.json'
GUARD_SHA='01dc21dcc6362247698b5f898503dcb78b543c96344b96d57f8de0135c2a3e7f'

def assess(poses,comparison,pixels):
    core.native_pose_inventory(poses,'3F');names=[p['name'] for p in poses]
    rows=pixels['views']
    if ([v['name'] for v in comparison['views']]!=names or pixels['png_pairs_readback']!=46
            or len(rows)!=46 or len({v['name'] for v in rows})!=46 or {v['name'] for v in rows}!=set(names)
            or any(type(v['different_pixels']) is not int or v['different_pixels']<0 for v in rows)):
        raise ValueError('Native saved comparison/PNG cohort differs')
    by_name={v['name']:v for v in rows};qualified=[];diagnostic=[]
    for pose in poses:
        owner=(pose.get('viewpoint_class')=='actual_unchanged_qualified_walking_probe'
               or pose['name'].startswith('view_') and int(pose['name'].rsplit('_',1)[1])>=0)
        row=dict(by_name[pose['name']],viewpoint_class=pose['viewpoint_class'])
        (qualified if owner else diagnostic).append(row)
    if len(qualified)!=33 or len(diagnostic)!=13:raise ValueError('Native owner/diagnostic partition differs')
    return dict(count=33,passed=all(v['different_pixels']==0 for v in qualified),views=qualified),dict(count=13,views=diagnostic)

def main():
    core.check(PLAN,PLAN_SHA);plan=core.read(PLAN);receipt=plan['binding'];core.recheck(receipt)
    if (receipt['floor_id']!='3F' or receipt['input_triangles']!=53602 or receipt['output_triangles']!=38691
            or receipt['source_after_sha256']!='a910864443ea698855836b9f725664d2a9e86f9b11270b503515eaacc9ad907a'
            or receipt['after_sha256']!='c3664f9e796c5c63cdcdcd1ba36be6996e07bee2727a908204ec08cbc37ed09d'):
        raise ValueError('Actual3F native input identity differs')
    args=SimpleNamespace(guard_receipt=GUARD,guard_sha256=GUARD_SHA);core.require_guard(args,receipt)
    preparation=core.read(receipt['paths']['preparation']);p=receipt['paths']
    core.check(preparation['blender'],preparation['blender_sha256'])
    expected=[preparation['blender'],'--background','--factory-startup','--python-exit-code','13','--python',p['native_renderer'],'--',
        '--before',p['source_baseline'],'--after',p['candidate.source.obj'],'--before-frame','source','--after-frame','source',
        '--poses',p['native_poses'],'--out',str(OUT/'paired'),'--size','512']
    if plan['command']!=expected or plan['render_launched'] is not False:raise ValueError('Exact native command differs')
    if any((OUT/name).exists() for name in ['paired','renderer.log','native-readback.json','failure.txt']):
        raise ValueError('Prior native run exists; refusing overwrite')
    started=time.monotonic()
    try:
        with (OUT/'renderer.log').open('wb') as log:subprocess.run(expected,check=True,stdout=log,stderr=subprocess.STDOUT)
        spec=importlib.util.spec_from_file_location('existing_native_png_reader',p['native_readback']);reader=importlib.util.module_from_spec(spec);spec.loader.exec_module(reader);reader.summarize(OUT/'paired')
        comparison=core.read(OUT/'paired/comparison.json');pixels=core.read(OUT/'paired/png-readback.json')
        if (comparison['before_sha256']!=receipt['hashes']['source_baseline'] or comparison['after_sha256']!=receipt['source_after_sha256']
                or comparison['before_frame']!='source' or comparison['after_frame']!='source'
                or comparison['size']!=512 or comparison['blender_version']!='5.1.2'):
            raise ValueError('Actual source-frame native renderer identity differs')
        qualified,diagnostic=assess(plan['poses'],comparison,pixels)
        core.check(PLAN,PLAN_SHA);core.require_guard(args,receipt);core.recheck(receipt)
        result=core.read(GUARD);result['paths']=dict(result['paths']);result['hashes']=dict(result['hashes'])
        result.update(qualified_owner_views=qualified,diagnostic_views=diagnostic,native_preservation_passed=qualified['passed'],
            before_source_role='qualified_baseline',before_source_sha256=receipt['hashes']['source_baseline'],
            guard_receipt_sha256=GUARD_SHA,native_plan_sha256=PLAN_SHA,native_wall_s=time.monotonic()-started,acceptance=False)
        for key,path,value in [('independent_guard',GUARD,GUARD_SHA),('native_phase_code',Path(__file__),core.digest(__file__)),('blender_executable',Path(preparation['blender']),preparation['blender_sha256'])]:
            result['paths'][key]=str(path);result['hashes'][key]=value
        for path in sorted(OUT.rglob('*')):
            if path.is_file():
                key='native_saved_'+path.relative_to(OUT).as_posix();result['paths'][key]=str(path);result['hashes'][key]=core.digest(path)
        core.recheck(result);core.write(OUT/'native-readback.json',result)
        print(json.dumps(dict(qualified_passed=qualified['passed'],qualified_views=33,diagnostic_views=13,receipt=str(OUT/'native-readback.json'),sha256=core.digest(OUT/'native-readback.json'))),flush=True)
        return 0 if qualified['passed'] else 2
    except Exception:
        (OUT/'failure.txt').write_text(traceback.format_exc(),encoding='utf-8');raise
if __name__=='__main__':raise SystemExit(main())
