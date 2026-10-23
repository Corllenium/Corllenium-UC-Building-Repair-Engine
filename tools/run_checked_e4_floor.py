"""Run the checked E4 coplanar merge on one of Claude's qualified fresh floors.

Usage (cwd = this worktree so its engine code imports; PYTHONPATH = this worktree):
  python -B -u tools/run_checked_e4_floor.py --root <claude run root> --floor 7F --raw-name "7th floor main infra.obj" [--from-e3 | --from-e5]
      [--crack-judgement <root>/e4/<floor>-crack-judgement.json]
BEFORE is the E3 candidate (`<root>/e3/<floor>/candidate.engine.obj`, with `--from-e3`; audit `e3_then_e4_merge`),
the E3 -> E5 candidate (`<root>/e5/<floor>/candidate.engine.obj`, with `--from-e5`; audit `e3_then_e5_then_e4_merge`,
the E5 audit's own `e3_candidate` carried along) or the normalized baseline;
inputs otherwise come from Claude's run root exactly as `run_checked_e3_floor.py` reads them (raw, reference,
normalized, qualification, materials, duplicate-only candidate). Output goes to `<root>/e4/<floor>/` and must not
exist. `--crack-judgement` restricts the merge to the regions a `tools/main_infra_crack_judge.py` run said to merge.
The guard stays pending: the stage audit says so, and the Validator runs separately.
"""
import argparse
import json
import os
import sys
import time
from pathlib import Path


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--root', type=Path, required=True)
    parser.add_argument('--floor', required=True)
    parser.add_argument('--raw-name', required=True)
    parser.add_argument('--from-e3', action='store_true')
    parser.add_argument('--from-e5', action='store_true')
    parser.add_argument('--crack-judgement', type=Path, default=None)
    args = parser.parse_args(argv)
    root = args.root.resolve()
    F = args.floor
    out = root / 'e4' / F
    if out.exists():
        raise ValueError('Refusing existing attempt output')
    if args.from_e3 and args.from_e5:
        raise ValueError('--from-e3 and --from-e5 exclude each other')

    from engine.io.minecraft_floor import Frame, parse_floor
    from engine.io.mtl import parse_mtl, texture_flatness
    from engine.io.obj_reader import read_obj
    from engine.io.snapshot import copy_verified, sha256_file
    from engine.repair.kernel import write_records
    from engine.validate.checks import load_looks
    from tools.main_infra_e4 import floor_from_candidate, run_checked_e4, save_merged_pair
    from tools.main_infra_physical_validation import _hash, _same_mesh, load_physical_pair

    raw = root / 'raw' / args.raw_name
    reference = root / 'reference' / f'{F}.json'
    qualification = root / 'independent-validator' / 'import-audit' / f'qualification-{F}.json'
    base = root / 'normalized' / F
    materials = root / 'independent-validator' / 'preflight' / f'materials-{F}.json'
    baseline, _, receipt = load_physical_pair(raw=raw, reference=reference, baseline=base,
                                              qualification=qualification, candidate=root / 'candidates' / F)
    native = json.loads(reference.read_text(encoding='utf-8'))
    source = parse_floor(raw.read_text(encoding='utf-8'),
                         triangulations={int(k): v for k, v in native['polygons'].items()})
    provenance = json.loads((base / 'geometry-provenance.json').read_text(encoding='utf-8'))
    frame = Frame(1000 / 25.4, provenance['frame_evidence'])
    mtl = parse_mtl(base / source.mesh.mtllib)
    looks = load_looks(materials, [(mtl, base)])
    flatness = {name: texture_flatness(base / mat.map_kd.replace(chr(92), '/'))
                for name, mat in mtl.items() if mat.map_kd}

    e3_binding, e5_binding = None, None
    if args.from_e5:
        e5_dir = root / 'e5' / F
        e5_audit = json.loads((e5_dir / 'stage-audit.json').read_text(encoding='utf-8'))
        if e5_audit.get('cleanup_mode') != 'e3_then_e5_cull':
            raise ValueError('--from-e5 needs the checked E3 -> E5 candidate (cleanup_mode e3_then_e5_cull)')
        e5_engine = _hash(e5_dir / 'candidate.engine.obj', e5_audit.get('engine_candidate_sha256'))
        e5_source = _hash(e5_dir / 'candidate.source.obj', e5_audit.get('source_candidate_sha256'))
        source_floor = floor_from_candidate(e5_dir / 'candidate.source.obj')
        engine_floor = source_floor.in_frame(frame)
        _same_mesh(read_obj(e5_dir / 'candidate.engine.obj'), engine_floor.mesh)
        e5_binding = dict(candidate=str(e5_dir), engine_candidate_sha256=e5_engine, source_candidate_sha256=e5_source,
                          source_faces_sha256=sha256_file(e5_dir / 'source-faces.json'),
                          stage_audit_sha256=sha256_file(e5_dir / 'stage-audit.json'))
        e3_binding = e5_audit.get('e3_candidate')
        cleanup_mode, stages = 'e3_then_e5_then_e4_merge', ['E3', 'E5', 'E4']
    elif args.from_e3:
        e3_dir = root / 'e3' / F
        e3_audit = json.loads((e3_dir / 'stage-audit.json').read_text(encoding='utf-8'))
        if e3_audit.get('cleanup_mode') != 'e3_remove_only':
            raise ValueError('--from-e3 needs the checked E3 candidate (cleanup_mode e3_remove_only)')
        e3_engine = _hash(e3_dir / 'candidate.engine.obj', e3_audit.get('engine_candidate_sha256'))
        e3_source = _hash(e3_dir / 'candidate.source.obj', e3_audit.get('source_candidate_sha256'))
        source_floor = floor_from_candidate(e3_dir / 'candidate.source.obj')
        engine_floor = source_floor.in_frame(frame)
        _same_mesh(read_obj(e3_dir / 'candidate.engine.obj'), engine_floor.mesh)
        e3_binding = dict(candidate=str(e3_dir), engine_candidate_sha256=e3_engine, source_candidate_sha256=e3_source,
                          source_faces_sha256=sha256_file(e3_dir / 'source-faces.json'),
                          stage_audit_sha256=sha256_file(e3_dir / 'stage-audit.json'))
        cleanup_mode, stages = 'e3_then_e4_merge', ['E3', 'E4']
    else:
        source_floor = source
        engine_floor = source.in_frame(frame)
        _same_mesh(baseline, engine_floor.mesh)
        cleanup_mode, stages = 'e4_merge_only', ['E4']
    before = engine_floor.mesh

    allowed, judgement = None, None
    if args.crack_judgement is not None:
        judgement = json.loads(args.crack_judgement.read_text(encoding='utf-8'))
        allowed = sorted(int(r) for r in judgement['merge'])

    out.parent.mkdir(parents=True, exist_ok=True)
    progress = out.parent / f'worker-{F}.json'
    progress.write_text(json.dumps(dict(pid=os.getpid(), state='running', stage='checked E4 merge',
                                        input_triangles=before.n_faces, started=time.time(), candidate=str(out),
                                        from_e3=bool(args.from_e3), from_e5=bool(args.from_e5)), indent=2))
    print(f'ENGINE E4 starting on fresh {F} ({cleanup_mode}): {before.n_faces} triangles; site checks and rollback '
          f'enabled; allowed regions: {"all" if allowed is None else len(allowed)}', flush=True)
    started = time.perf_counter()
    outcome, mapping = run_checked_e4(before, looks, flatness, allowed_regions=allowed)
    print(f'ENGINE E4 finished: {before.n_faces}->{outcome.mesh.n_faces}; kept sites={len(outcome.kept)}, '
          f'rolled back={len(outcome.rolled_back)}; checks={outcome.checks}', flush=True)
    eng, src, region_map = save_merged_pair(engine_floor, source_floor, mapping, out)
    for asset in provenance['assets']:
        target = out / asset['path']
        target.parent.mkdir(parents=True, exist_ok=True)
        copy_verified(base / asset['path'], target, interval_s=0)
    write_records(out / 'edit-log.jsonl', outcome.records)
    if judgement is not None:
        (out / 'crack-judgement.json').write_text(json.dumps(judgement, indent=2), encoding='utf-8')
    audit = dict(cleanup_mode=cleanup_mode, executed_stages=stages, checks=outcome.checks,
                 input_triangles=before.n_faces, output_triangles=outcome.mesh.n_faces,
                 kept_edits=len(outcome.kept), rolled_back_edits=len(outcome.rolled_back),
                 engine_report=mapping.get('engine_report'), e3_candidate=e3_binding, e5_candidate=e5_binding,
                 crack_judgement=None if args.crack_judgement is None else str(args.crack_judgement),
                 engine_candidate_sha256=sha256_file(eng), source_candidate_sha256=sha256_file(src),
                 region_map_sha256=sha256_file(region_map), edit_log_sha256=sha256_file(out / 'edit-log.jsonl'),
                 qualification_sha256=sha256_file(qualification), assets=provenance['assets'],
                 before_snapshot=str(Path(receipt['before']).parent), input_receipt=receipt,
                 guard=dict(passed=False, state='pending'), independent_validation='pending', accepted=False,
                 owner_approval='chat 2026-10-23: triangulation may change on the fresh MAIN INFRA floors, as a '
                                'separate guarded pass after E3',
                 wall_s=round(time.perf_counter() - started, 2))
    (out / 'stage-audit.json').write_text(json.dumps(audit, indent=2), encoding='utf-8')
    progress.write_text(json.dumps(dict(pid=os.getpid(), state='candidate_saved', input_triangles=before.n_faces,
                                        output_triangles=outcome.mesh.n_faces, wall_s=audit['wall_s'],
                                        checks=outcome.checks, candidate=str(out)), indent=2))
    print(json.dumps({k: audit[k] for k in ('input_triangles', 'output_triangles', 'kept_edits',
                                             'rolled_back_edits', 'wall_s')}), flush=True)
    return 0


if __name__ == '__main__':
    sys.exit(main())
