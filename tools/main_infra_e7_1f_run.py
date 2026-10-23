"""Prepare and run the reviewed, checked 1F E7 stage on frozen fresh inputs."""
import argparse
from datetime import datetime, timezone
import json
import os
from pathlib import Path, PurePosixPath, PureWindowsPath
import subprocess
import time

from engine.io.minecraft_floor import Frame, parse_floor
from engine.io.mtl import parse_mtl
from engine.io.protected import refuse_protected
from engine.io.snapshot import copy_verified, sha256_file
from engine.repair.kernel import write_records
from engine.validate.checks import default_targets_path, load_looks, load_targets
from tools.main_infra_e3 import _source_digest
from tools.main_infra_e3_binding import _hash
from tools.main_infra_e7 import run_checked_e7
from tools.main_infra_e7_serialization import FILES, bind_saved_cut_pair, prepare_cut_pair, save_cut_pair
from tools.main_infra_physical_validation import load_physical_pair

ROOT = Path(__file__).resolve().parents[1]
CLEAN = Path('D:/PROJECTS/UC MODEL FIXER/.claude/worktrees/MAIN-INFRA-CLEAN-20261023/data/main-infra-fresh/run-20261023')
E3 = Path('D:/PROJECTS/UC MODEL FIXER/.claude/worktrees/MAIN-INFRA-E3-20261023/data/main-infra-e3/run-20261023/1F')
ANCHORS = dict(raw='769cbb11cd954d2132b69a78a023f24f63f95b1923f7b336aa8be892d826503f',
    reference='b2c3f91727047fb4b37c5380550d8d213df2700d856a7aa49728fc43bde33039',
    qualification='d2ab32f244207b818de51cca2a54c6643e4c72f63a6feb434885fa355e366e96',
    provenance='eac6bd90fc2c9c596659f658fc140251aac3f2de7afe0d42d02ebc3bff987746',
    baseline_source='26eda65235ce9d1f8c82e97b00d4da21cc1e272d0817e769dddb6ca192f4aea5',
    baseline_engine='bed4b7c24b7a3a164381b8e6e0ca0b7e7bf9998e1df7c2782878d23cd1796df3',
    source_input='ac32d4d054bf10226803e84493db19bd794d2afe0fd98d85dc3451e5e87eaf25',
    engine_input='5c5c25cff8498178f4014f620be7a0473969c835427d03a5fd60817314aff141',
    lineage='4651b2ba97a20eeb49ff59afb07b9e84cb7fae12558652d7b618fcab65c8b4b8',
    materials='aafb0e8572a8a3aa544beedfcc9863a9c240e28fc4dcbe0e47d8b45e42982c5c')
COMPONENTS = ('tools/main_infra_e7_1f_run.py', 'tools/main_infra_e7.py',
    'tools/main_infra_e7_serialization.py', 'tools/main_infra_physical_validation.py',
    'tools/main_infra_e3_binding.py', 'engine/repair/engines/e7_thread.py',
    'engine/repair/kernel.py', 'engine/site_judge.py', 'engine/rays/caster.py')


def _read(path):
    return json.loads(Path(path).read_text(encoding='utf-8-sig'))


def _write(path, value):
    Path(path).write_text(json.dumps(value, indent=2, sort_keys=True, allow_nan=False) + '\n', encoding='utf-8')


def _now():
    return datetime.now(timezone.utc).isoformat()


def real_paths():
    return {name: str(path.resolve()) for name, path in dict(
        raw=CLEAN/'raw/1st floor main infra.obj', reference=CLEAN/'reference/1F.json',
        qualification=CLEAN/'independent-validator/import-audit/qualification-1F.json',
        provenance=CLEAN/'normalized/1F/geometry-provenance.json',
        baseline_source=CLEAN/'normalized/1F/before.source.obj', baseline_engine=CLEAN/'normalized/1F/before.engine.obj',
        source_input=E3/'candidate.source.obj', engine_input=E3/'candidate.engine.obj', lineage=E3/'source-faces.json',
        e3_audit=E3/'stage-audit.json', e3_edit_log=E3/'edit-log.jsonl',
        materials=CLEAN/'independent-validator/preflight-20261023/materials-1F.json', targets=default_targets_path(),
        prior_validation=E3.parent/'independent-validator/1F/validation/validation.json').items()}


def _components():
    def git(*args):
        return subprocess.check_output(['git', '-C', str(ROOT), *args], text=True).strip()
    if git('status', '--porcelain', '--untracked-files=no'):
        raise ValueError('execution needs committed, clean tracked code')
    return dict(HEAD=git('rev-parse', 'HEAD'), files={name: dict(sha256=sha256_file(ROOT/name),
        commit=git('log', '-1', '--format=%H', '--', name)) for name in COMPONENTS})


def _load(paths):
    for key, expected in ANCHORS.items():
        _hash(Path(paths[key]), expected)
    raw, reference, baseline = Path(paths['raw']), Path(paths['reference']), Path(paths['baseline_engine']).parent
    original, before, physical = load_physical_pair(raw=raw, reference=reference, baseline=baseline,
        qualification=paths['qualification'], candidate=Path(paths['engine_input']).parent)
    native, provenance = _read(reference), _read(paths['provenance'])
    source = parse_floor(raw.read_text(encoding='utf-8'),
        triangulations={int(key): value for key, value in native['polygons'].items()})
    engine = source.in_frame(Frame(1000 / 25.4, provenance['frame_evidence']))
    ancestry = _read(paths['lineage'])['source_faces']
    before_dir = Path(physical['before']).parent
    sources = [(parse_mtl(before_dir/'materials.mtl'), before_dir),
               (parse_mtl(Path(paths['engine_input']).parent/before.mtllib), Path(paths['engine_input']).parent)]
    looks = load_looks(paths['materials'], sources)
    unknown = looks.unknown(before)
    no_texel = sorted({looks.key_of(name) for name in before.materials
                      if looks.key_of(name) not in looks.texel and looks.key_of(name) not in looks.flat})
    if unknown or no_texel:
        raise ValueError('unknown materials or missing texture texels')
    targets = load_targets(paths['targets'])
    if targets.get('signed') is not True:
        raise ValueError('signed problem targets required')
    if original.n_faces != 15856 or source.mesh.n_faces != 15856 or before.n_faces != 10136:
        raise ValueError('qualified original/stage triangle counts differ')
    prior = _read(paths['prior_validation'])
    failed = {key: {name: row[name] for name in ('before', 'after', 'target', 'status')}
              for key, row in prior['checks']['problems']['kinds'].items() if row['status'] == 'FAIL'}
    facts = dict(original_source_triangles=original.n_faces, stage_input_triangles=before.n_faces,
        before_digest=_source_digest(before).hex(), physical=physical, unknown_materials=unknown,
        no_texel=no_texel, assets=provenance['assets'], prior_failed_targets=failed)
    return source, engine, before, ancestry, looks, facts


def prepare(paths, plan_path, out):
    plan_path, out = Path(plan_path), Path(out)
    refuse_protected(plan_path); refuse_protected(out)
    if plan_path.exists() or out.exists():
        raise ValueError('preparation or output exists; refusing overwrite')
    *_, facts = _load(paths)
    value = dict(schema_version=1, floor='1F', state='prepared', prepared_utc=_now(),
        paths=paths, sha256={key: sha256_file(path) for key, path in paths.items()},
        components=_components(), out=str(out.resolve()), inputs=facts, **facts)
    plan_path.parent.mkdir(parents=True, exist_ok=True)
    _write(plan_path, value)
    return value


def copy_assets(source, candidate, assets):
    source, candidate = Path(source).resolve(), Path(candidate).resolve()
    refuse_protected(candidate)
    seen, rows = set(), []
    reserved = FILES | {'cut-receipt.json', 'asset-receipt.json', 'run-receipt.json'}
    for row in assets:
        text = row['path'].replace('\\', '/')
        relative = PurePosixPath(text)
        key = text.casefold()
        if (relative.is_absolute() or PureWindowsPath(text).drive or '..' in relative.parts
                or key in seen or key in reserved or not relative.parts):
            raise ValueError('unsafe or duplicate asset path')
        seen.add(key)
        src, dst = (source/text).resolve(), (candidate/text).resolve()
        if not src.is_relative_to(source) or not dst.is_relative_to(candidate):
            raise ValueError('asset escapes package')
        if dst.exists():
            raise ValueError('asset output exists; refusing overwrite')
        _hash(src, row['sha256'])
        dst.parent.mkdir(parents=True, exist_ok=True)
        copy_verified(src, dst)
        _hash(src, row['sha256']); _hash(dst, row['sha256'])
        rows.append(dict(path=row['path'], sha256=row['sha256'], bytes=dst.stat().st_size))
    return rows


def execute(plan_path, expected_sha256):
    plan_path = Path(plan_path); _hash(plan_path, expected_sha256)
    plan = _read(plan_path)
    if plan['components'] != _components():
        raise ValueError('prepared component revisions changed')
    for name, path in plan['paths'].items():
        _hash(Path(path), plan['sha256'][name])
    source, engine, before, ancestry, looks, facts = _load(plan['paths'])
    if facts != plan['inputs']:
        raise ValueError('prepared physical inputs changed')
    out = Path(plan['out']); work = out.parent/'execution-1F'
    refuse_protected(out); refuse_protected(work)
    if out.exists() or work.exists():
        raise ValueError('execution or candidate exists; refusing overwrite')
    work.mkdir(parents=True)
    worker = dict(schema_version=1, floor='1F', state='checking', pid=os.getpid(), started_utc=_now(),
        components=plan['components'], preparation=str(plan_path.resolve()), preparation_sha256=expected_sha256,
        original_source_triangles=source.mesh.n_faces, stage_input_triangles=before.n_faces,
        out=str(out), floor_accepted=False, independent_validation='pending')
    def status(**update):
        worker.update(update, updated_utc=_now())
        temp = work/'worker.json.tmp'; _write(temp, worker); temp.replace(work/'worker.json')
        print(json.dumps({key: worker[key] for key in ('state', 'pid', 'updated_utc')}), flush=True)
    status()
    started = time.perf_counter()
    try:
        outcome = run_checked_e7(before, looks)
        status(state='serializing', planned_cuts=len(outcome.edits), kept_cuts=len(outcome.kept),
               rolled_back_cuts=len(outcome.rolled_back), output_triangles=outcome.mesh.n_faces, checks=outcome.checks)
        edit_log = work/'edit-log.jsonl'; write_records(edit_log, outcome.records)
        paths, hashes = dict(plan['paths'], edit_log=str(edit_log.resolve())), dict(plan['sha256'], edit_log=sha256_file(edit_log))
        for index, row in enumerate(facts['assets']):
            key = f'asset_{index}'; paths[key] = str(Path(paths['raw']).parent/row['path']); hashes[key] = row['sha256']
        binding = dict(paths=paths, sha256=hashes, before_digest=facts['before_digest'])
        pair = prepare_cut_pair(source, engine, before, ancestry, outcome, looks, binding=binding)
        candidate = work/'candidate'
        receipt = save_cut_pair(pair, candidate)
        assets = copy_assets(Path(paths['raw']).parent, candidate, facts['assets'])
        _write(candidate/'asset-receipt.json', dict(schema_version=1, copied_new=True, assets=assets))
        bind_saved_cut_pair(source, engine, before, ancestry, looks, candidate, binding=binding,
                            expected_receipt_sha256=receipt['receipt_sha256'])
        for row in assets:
            _hash(candidate/row['path'], row['sha256'])
        status(state='finalizing', wall_s=round(time.perf_counter()-started, 2),
            source_sha256=sha256_file(candidate/'candidate.source.obj'),
            engine_sha256=sha256_file(candidate/'candidate.engine.obj'), cut_receipt_sha256=receipt['receipt_sha256'],
            asset_receipt_sha256=sha256_file(candidate/'asset-receipt.json'), assets=assets,
            prior_failed_targets=facts['prior_failed_targets'], post_e7_signed_targets='not independently measured')
        _write(candidate/'run-receipt.json', dict(worker, state='candidate_saved', final_package=str(out.resolve())))
        candidate.rename(out)
        status(state='candidate_saved', final_package=str(out.resolve()), run_receipt_sha256=sha256_file(out/'run-receipt.json'))
        return worker
    except Exception as exc:
        status(state='failed', error=f'{type(exc).__name__}: {exc}', wall_s=round(time.perf_counter()-started, 2))
        raise


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('action', choices=['prepare', 'execute'])
    parser.add_argument('--plan', type=Path, required=True)
    parser.add_argument('--out', type=Path)
    parser.add_argument('--plan-sha256')
    args = parser.parse_args(argv)
    if args.action == 'prepare':
        if args.out is None:
            parser.error('prepare requires --out')
        value = prepare(real_paths(), args.plan, args.out)
        print(json.dumps(dict(state=value['state'], original_source_triangles=value['original_source_triangles'],
            stage_input_triangles=value['stage_input_triangles'], plan_sha256=sha256_file(args.plan))), flush=True)
    else:
        if not args.plan_sha256:
            parser.error('execute requires --plan-sha256')
        execute(args.plan, args.plan_sha256)
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
