"""Prepare a new 1F E7 donor-kept subset run and checkpoint actual checks before saving."""
import argparse
import hashlib
import os
from pathlib import Path
import subprocess
import time

from engine.io.protected import refuse_protected
from engine.io.snapshot import sha256_file
from engine.repair.engines.e7_thread import _source_weights
from tools import main_infra_e7_1f_run as legacy
from tools.main_infra_e3_binding import _hash
from tools.main_infra_e7_checkpoint import save_e7_checkpoint, restore_e7_checkpoint
from tools.main_infra_e7_serialization import (_dump, _inputs, _prove_exact_source_coverage,
    prepare_cut_pair, save_cut_pair, bind_saved_cut_pair)
from tools.main_infra_e7_subset import verify_donor_subset, run_checked_subset

ROOT = Path(__file__).resolve().parents[1]
DONOR_HEAD = 'd7e8b14e60e24fa08c569dda5ca937d9c42a7628'
SOURCE_PROOF_SHA = '6456ac625441ce9c2649e088247ba73e094995858b074a127d7a54292365a44a'
RUN_ID = 'MAIN-INFRA-E7-1F-attempt3-20261023'
DONOR = Path('D:/LLM_BACKUP/Codex session/main-infra-e7-run-1f-20261023/05-Corllenium-UC-Building-Repair-Engine/data/main-infra-e7/run-20261023-attempt2')
DONOR_HASHES = dict(preparation='1cd147ad337153811478b6f7a02e904f8fd935227aefa89ef794b5b8abc4896f',
    edit_log='7348b39a2a54192c6f44b758be96cb57703e0c24c361b5ea99ed0879f39ce6c7',
    worker='e9b61a96b9d0ab3154118f275f7baf44a13385d8c641731c17d696bc50f3654f')
NEW_COMPONENTS = ('tools/main_infra_e7_attempt3.py', 'tools/main_infra_e7_subset.py', 'tools/main_infra_e7_checkpoint.py')
_load, _read, _write, _now = legacy._load, legacy._read, legacy._write, legacy._now


def real_donor():
    return dict(preparation=str(DONOR/'preparation-1F.json'),edit_log=str(DONOR/'execution-1F/edit-log.jsonl'),
                worker=str(DONOR/'execution-1F/worker.json'))


def _components():
    value = legacy._components()
    subprocess.check_call(['git','-C',str(ROOT),'ls-files','--error-unmatch','--',*NEW_COMPONENTS],
                          stdout=subprocess.DEVNULL)
    subprocess.check_call(['git','-C',str(ROOT),'diff','--quiet',DONOR_HEAD,'--','engine'])
    _hash(ROOT/'tools/main_infra_e7_serialization.py',SOURCE_PROOF_SHA)
    names = set(NEW_COMPONENTS) | {p.relative_to(ROOT).as_posix() for p in (ROOT/'engine').rglob('*.py')}
    value['files'].update({name:dict(sha256=sha256_file(ROOT/name),commit=value['HEAD']) for name in sorted(names)})
    return value


def _select(before,looks,paths,hashes):
    return verify_donor_subset(before,looks,paths=paths,expected_sha256=hashes,component_root=ROOT)


def _source_binding(paths,hashes,facts,log):
    return dict(paths=dict(paths,edit_log=str(log)),sha256=dict(hashes,edit_log=sha256_file(log)),
                before_digest=facts['before_digest'])


def _preflight(source,engine,before,ancestry,subset,paths,hashes,facts,donor):
    source_before,_ = _inputs(source,engine,before,ancestry,
        _source_binding(paths,hashes,facts,donor['edit_log']))
    for edit in subset.edits:
        _prove_exact_source_coverage(source_before,edit.faces[0],edit.new_faces)
        _source_weights(before,edit.faces[0],edit.new_faces)
    return dict(exact_source_passed=len(subset.edits),engine_proof_passed=len(subset.edits),
        accepted_sites=[e.site for e in subset.edits],rejected_sites=[],source_positions_unchanged=True)


def prepare(paths,donor,donor_hashes,plan_path,out):
    plan_path,out = Path(plan_path),Path(out)
    refuse_protected(plan_path); refuse_protected(out)
    if plan_path.exists() or out.exists() or (out.parent/'execution-1F').exists():
        raise ValueError('preparation or output exists; refusing overwrite')
    components = _components()
    source,engine,before,ancestry,looks,facts = _load(paths)
    hashes = {key:sha256_file(path) for key,path in paths.items()}
    subset = _select(before,looks,donor,donor_hashes)
    if subset.proof['input_sha256'] != hashes:
        raise ValueError('new input hashes differ from qualified donor')
    preflight = _preflight(source,engine,before,ancestry,subset,paths,hashes,facts,donor)
    value = dict(schema_version=1,mode='fresh_checked_e7_donor_subset',run_id=RUN_ID,floor='1F',
        state='prepared',prepared_utc=_now(),paths=paths,sha256=hashes,components=components,inputs=facts,
        donor_paths=donor,donor_sha256=donor_hashes,selection=subset.proof,selection_seal=subset.seal,
        preflight=preflight,out=str(out.resolve()),floor_accepted=False)
    plan_path.parent.mkdir(parents=True,exist_ok=True)
    _write(plan_path,value)
    return value


def execute(plan_path,expected_sha256):
    plan_path = Path(plan_path); _hash(plan_path,expected_sha256)
    plan = _read(plan_path)
    if (plan.get('mode') != 'fresh_checked_e7_donor_subset' or plan.get('run_id') != RUN_ID
            or plan['components'] != _components()):
        raise ValueError('prepared component or attempt identity changed')
    for name,path in plan['paths'].items():
        _hash(Path(path),plan['sha256'][name])
    out = Path(plan['out']); work = out.parent/'execution-1F'
    refuse_protected(out); refuse_protected(work)
    if out.exists() or work.exists():
        raise ValueError('execution or candidate exists; refusing overwrite')
    source,engine,before,ancestry,looks,facts = _load(plan['paths'])
    if facts != plan['inputs']:
        raise ValueError('prepared physical inputs changed')
    subset = _select(before,looks,plan['donor_paths'],plan['donor_sha256'])
    if subset.proof != plan['selection'] or subset.seal != plan['selection_seal']:
        raise ValueError('prepared typed subset selection changed')
    if plan['preflight'] != _preflight(source,engine,before,ancestry,subset,plan['paths'],plan['sha256'],facts,plan['donor_paths']):
        raise ValueError('prepared exact source preflight changed')
    work.mkdir(parents=True)
    worker = dict(schema_version=1,run_id=RUN_ID,floor='1F',state='checking',pid=os.getpid(),
        started_utc=_now(),components=plan['components'],preparation=str(plan_path.resolve()),
        preparation_sha256=expected_sha256,original_source_triangles=source.mesh.n_faces,
        stage_input_triangles=before.n_faces,planned_cuts=len(subset.edits),out=str(out),
        floor_accepted=False,independent_validation='pending')
    def status(**update):
        worker.update(update,updated_utc=_now())
        temporary = work/'worker.json.tmp'; _write(temporary,worker); temporary.replace(work/'worker.json')
        print(_dump({key:worker[key] for key in ('state','pid','updated_utc')}),flush=True)
    status()
    started = time.perf_counter()
    try:
        outcome = run_checked_subset(before,looks,subset)
        bound_paths,bound_hashes = dict(plan['paths']),dict(plan['sha256'])
        for name,path in plan['donor_paths'].items():
            bound_paths['donor_'+name] = path
            bound_hashes['donor_'+name] = plan['donor_sha256'][name]
        checkpoint_binding = dict(paths=bound_paths,sha256=bound_hashes,before_digest=facts['before_digest'],
            run_id=RUN_ID,preparation_sha256=expected_sha256,components=plan['components'],
            selection_digest=hashlib.sha256(_dump(subset.proof).encode()).hexdigest())
        checkpoint = work/'checked-outcome'
        receipt = save_e7_checkpoint(before,outcome,looks,checkpoint,binding=checkpoint_binding)
        status(state='checked_checkpoint_saved',checkpoint=str(checkpoint.resolve()),
            checkpoint_receipt_sha256=receipt['receipt_sha256'],kept_cuts=len(outcome.kept),
            rolled_back_cuts=len(outcome.rolled_back),output_triangles=outcome.mesh.n_faces,checks=outcome.checks)
        outcome = restore_e7_checkpoint(before,looks,checkpoint,binding=checkpoint_binding,
            expected_receipt_sha256=receipt['receipt_sha256'])
        paths,hashes = dict(bound_paths),dict(bound_hashes)
        for name,path in dict(preparation=plan_path,checked_outcome_receipt=checkpoint/'checkpoint-receipt.json').items():
            paths[name] = str(path.resolve()); hashes[name] = sha256_file(path)
        for index,row in enumerate(facts['assets']):
            key = f'asset_{index}'; paths[key] = str(Path(plan['paths']['raw']).parent/row['path']); hashes[key] = row['sha256']
        binding = _source_binding(paths,hashes,facts,checkpoint/'edit-log.jsonl')
        pair = prepare_cut_pair(source,engine,before,ancestry,outcome,looks,binding=binding)
        candidate = work/'candidate'; cut = save_cut_pair(pair,candidate)
        assets = legacy.copy_assets(Path(plan['paths']['raw']).parent,candidate,facts['assets'])
        _write(candidate/'asset-receipt.json',dict(schema_version=1,copied_new=True,assets=assets))
        bind_saved_cut_pair(source,engine,before,ancestry,looks,candidate,binding=binding,
                            expected_receipt_sha256=cut['receipt_sha256'])
        for row in assets:
            _hash(candidate/row['path'],row['sha256'])
        status(state='finalizing',wall_s=round(time.perf_counter()-started,2),
            source_sha256=sha256_file(candidate/'candidate.source.obj'),engine_sha256=sha256_file(candidate/'candidate.engine.obj'),
            cut_receipt_sha256=cut['receipt_sha256'],asset_receipt_sha256=sha256_file(candidate/'asset-receipt.json'),
            assets=assets,prior_failed_targets=facts['prior_failed_targets'],post_e7_signed_targets='not independently measured')
        _write(candidate/'run-receipt.json',dict(worker,state='candidate_saved',final_package=str(out.resolve())))
        candidate.rename(out)
        status(state='candidate_saved',final_package=str(out.resolve()),run_receipt_sha256=sha256_file(out/'run-receipt.json'))
        return worker
    except Exception as exc:
        status(state='failed',error=f'{type(exc).__name__}: {exc}',wall_s=round(time.perf_counter()-started,2))
        raise


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('action',choices=['prepare','execute'])
    parser.add_argument('--plan',type=Path,required=True)
    parser.add_argument('--out',type=Path)
    parser.add_argument('--plan-sha256')
    args = parser.parse_args(argv)
    if args.action == 'prepare':
        if args.out is None:
            parser.error('prepare requires --out')
        value = prepare(legacy.real_paths(),real_donor(),DONOR_HASHES,args.plan,args.out)
        print(_dump(dict(state=value['state'],run_id=RUN_ID,selected=value['selection']['selected'],plan_sha256=sha256_file(args.plan))))
    else:
        if not args.plan_sha256:
            parser.error('execute requires --plan-sha256')
        execute(args.plan,args.plan_sha256)
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
