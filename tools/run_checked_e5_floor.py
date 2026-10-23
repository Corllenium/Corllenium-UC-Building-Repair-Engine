"""Run the checked E5 coincident-layer cull on one of Claude's qualified fresh floors.

Usage (cwd = this worktree so its engine code imports; PYTHONPATH = this worktree):
  python -B -u tools/run_checked_e5_floor.py --root <claude run root> --floor 7F --raw-name "7th floor main infra.obj" [--from-e3]
BEFORE is the E3 candidate (`<root>/e3/<floor>/candidate.engine.obj`, with `--from-e3`; the audit then says
`e3_then_e5_cull`) or the normalized baseline (`e5_cull_only`); inputs otherwise come from Claude's run root exactly
as `run_checked_e4_floor.py` reads them (raw, reference, normalized, qualification, materials, duplicate-only
candidate). Output goes to `<root>/e5/<floor>/` and must not exist: `candidate.engine.obj`, `candidate.source.obj`,
`source-faces.json` (E3's survivor contract), `edit-log.jsonl`, `stage-audit.json`, the assets. The guard stays
pending: the stage audit says so, and the Validator runs separately. E4 then runs on this output with `--from-e5`.
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
    args = parser.parse_args(argv)
    root = args.root.resolve()
    F = args.floor
    out = root / 'e5' / F
    if out.exists():
        raise ValueError('Refusing existing attempt output')

    from engine.io.minecraft_floor import Frame, parse_floor
    from engine.io.mtl import parse_mtl, texture_flatness
    from engine.io.obj_reader import read_obj
    from engine.io.snapshot import copy_verified, sha256_file
    from engine.repair.kernel import write_records
    from engine.validate.checks import load_looks
    from tools.main_infra_e3 import save_survivor_pair
    from tools.main_infra_e4 import floor_from_candidate
    from tools.main_infra_e5 import audit_report, run_checked_e5
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

    e3_binding = None
    if args.from_e3:
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
        cleanup_mode, stages = 'e3_then_e5_cull', ['E3', 'E5']
    else:
        source_floor = source
        engine_floor = source.in_frame(frame)
        _same_mesh(baseline, engine_floor.mesh)
        cleanup_mode, stages = 'e5_cull_only', ['E5']
    before = engine_floor.mesh

    out.parent.mkdir(parents=True, exist_ok=True)
    progress = out.parent / f'worker-{F}.json'
    progress.write_text(json.dumps(dict(pid=os.getpid(), state='running', stage='checked E5 cull',
                                        input_triangles=before.n_faces, started=time.time(), candidate=str(out),
                                        from_e3=bool(args.from_e3)), indent=2))
    print(f'ENGINE E5 starting on fresh {F} ({cleanup_mode}): {before.n_faces} triangles; site checks and rollback '
          f'enabled', flush=True)
    started = time.perf_counter()
    report = {}
    outcome, indices = run_checked_e5(before, looks, flatness, report=report)
    print(f'ENGINE E5 finished: {before.n_faces}->{outcome.mesh.n_faces}; kept sites={len(outcome.kept)}, '
          f'rolled back={len(outcome.rolled_back)}; pairs={report.get("pairs")}; dropped={report.get("dropped")}; '
          f'checks={outcome.checks}', flush=True)
    eng, src, mapping = save_survivor_pair(engine_floor, source_floor, indices, out)
    for asset in provenance['assets']:
        target = out / asset['path']
        target.parent.mkdir(parents=True, exist_ok=True)
        copy_verified(base / asset['path'], target, interval_s=0)
    write_records(out / 'edit-log.jsonl', outcome.records)
    audit = dict(cleanup_mode=cleanup_mode, executed_stages=stages, checks=outcome.checks,
                 input_triangles=before.n_faces, output_triangles=outcome.mesh.n_faces,
                 kept_edits=len(outcome.kept), rolled_back_edits=len(outcome.rolled_back),
                 engine_report=audit_report(report), e3_candidate=e3_binding,
                 engine_candidate_sha256=sha256_file(eng), source_candidate_sha256=sha256_file(src),
                 source_faces_sha256=sha256_file(mapping), edit_log_sha256=sha256_file(out / 'edit-log.jsonl'),
                 qualification_sha256=sha256_file(qualification), assets=provenance['assets'],
                 before_snapshot=str(Path(receipt['before']).parent), input_receipt=receipt,
                 guard=dict(passed=False, state='pending'), independent_validation='pending', accepted=False,
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
