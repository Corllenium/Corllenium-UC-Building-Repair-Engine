"""Independent saved-E3 candidate readback plus the unchanged strict 26-view guard, for any fresh floor.

Parametrized version of the 1F reviewer script Codex used on 2026-10-23
(`.claude/worktrees/MAIN-INFRA-E3-20261023/.../preflight/iv_e3_guard.py`): same checks, same guard,
no hard-coded floor, run or materials hash. Run with PYTHONPATH = the E3 worktree (for
tools.main_infra_e3_binding and the P2 validation helpers); `--helper` points at the strict_guard
implementation in tools/main_infra_candidate.py of the clean/Claude worktree.
"""
import argparse
import importlib.util
import json
import os
from dataclasses import asdict
from datetime import datetime, timezone
from pathlib import Path
import time
import traceback

import numpy as np
from engine.io.minecraft_floor import Frame, parse_floor
from engine.io.obj_reader import read_obj
from engine.io.mtl import parse_mtl
from engine.io.snapshot import sha256_file
from engine.validate.checks import (LookTable, depth_tolerance, face_fingerprints, face_look_ids,
                                    load_looks, print_step, _rows_in)
from tools.main_infra_e3_binding import bind_saved_e3
from tools.main_infra_physical_validation import _same_mesh, _verify_assets


def now():
    return datetime.now(timezone.utc).isoformat()


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--root', type=Path, required=True, help='run root: raw/, reference/, normalized/, independent-validator/')
    parser.add_argument('--floor', required=True)
    parser.add_argument('--raw-name', required=True)
    parser.add_argument('--candidate', type=Path, required=True)
    parser.add_argument('--out', type=Path, required=True)
    parser.add_argument('--helper', type=Path, required=True, help='tools/main_infra_candidate.py holding strict_guard')
    parser.add_argument('--job-id', required=True)
    parser.add_argument('--reviewer', required=True)
    parser.add_argument('--expected-revision', default='7b2f7451b5723f724a1e074fdedc07dbcf7291d330ae550066f4926886136511')
    args = parser.parse_args()
    run, F = args.root.resolve(), args.floor
    candidate, out = args.candidate.resolve(), args.out.resolve()
    if out.exists():
        raise ValueError('Independent guard evidence exists; refusing overwrite')
    out.mkdir(parents=True)
    started = time.perf_counter()
    paths = dict(manifest=run / 'raw-manifest.json', raw=run / 'raw' / args.raw_name, reference=run / 'reference' / f'{F}.json',
                 qualification=run / 'independent-validator' / 'import-audit' / f'qualification-{F}.json',
                 provenance=run / 'normalized' / F / 'geometry-provenance.json',
                 source_baseline=run / 'normalized' / F / 'before.source.obj',
                 engine_baseline=run / 'normalized' / F / 'before.engine.obj',
                 materials=run / 'independent-validator' / 'preflight' / f'materials-{F}.json',
                 audit=candidate / 'stage-audit.json', mapping=candidate / 'source-faces.json',
                 edit_log=candidate / 'edit-log.jsonl', after=candidate / 'candidate.engine.obj',
                 source_after=candidate / 'candidate.source.obj', helper=args.helper.resolve())
    try:
        manifest = json.loads(paths['manifest'].read_text(encoding='utf-8'))
        assert manifest['source_revision'] == args.expected_revision and len(manifest['files']) == 36
        for row in manifest['files']:
            assert sha256_file(run / 'raw' / row['path']) == row['sha256'], 'Frozen source changed: ' + row['path']
        proof = json.loads(paths['qualification'].read_text(encoding='utf-8'))
        audit = json.loads(paths['audit'].read_text(encoding='utf-8'))
        provenance = json.loads(paths['provenance'].read_text(encoding='utf-8'))
        native = json.loads(paths['reference'].read_text(encoding='utf-8'))
        assert proof['qualified'] is True and proof['floor_id'] == F
        assert proof['source_revision'] == args.expected_revision
        for key, name in [('source_obj_sha256', 'raw'), ('native_reference_sha256', 'reference'),
                          ('source_triangles_sha256', 'source_baseline'), ('engine_obj_sha256', 'engine_baseline')]:
            assert sha256_file(paths[name]) == proof[key], name
        assert sha256_file(paths['qualification']) == audit['qualification_sha256']
        assert sha256_file(paths['after']) == audit['engine_candidate_sha256']
        assert sha256_file(paths['source_after']) == audit['source_candidate_sha256']
        assert native['source_sha256'] == proof['source_obj_sha256'] and native['unmatched_polygons'] == 0
        before_paths = list(Path(audit['before_snapshot']).glob('*.obj'))
        assert len(before_paths) == 1
        paths['before'] = before_paths[0]
        assert sha256_file(paths['before']) == proof['engine_obj_sha256']
        source = parse_floor(paths['raw'].read_text(encoding='utf-8'),
                             triangulations={int(k): v for k, v in native['polygons'].items()})
        frame = Frame(1000 / 25.4, provenance.get('frame_evidence', ''))
        assert np.array_equal(np.asarray(provenance['source_to_engine']), frame.matrix)
        expected = source.in_frame(frame).mesh
        before, after, source_after = read_obj(paths['before']), read_obj(paths['after']), read_obj(paths['source_after'])
        _same_mesh(before, expected)
        _same_mesh(read_obj(paths['source_baseline']), source.mesh)
        contract = bind_saved_e3(candidate=candidate, audit=audit, before_engine=expected, after_engine=after,
                                 before_source=source.mesh, after_source=source_after)
        assets = _verify_assets(paths['raw'], run / 'normalized' / F, candidate, paths['before'].parent,
                                source.mesh, provenance, audit)
        if before.materials != after.materials:
            raise ValueError('Strict helper numeric material-ID ordering differs; canonical look binding required')
        looks = load_looks(paths['materials'], [(parse_mtl(paths['before'].parent / 'materials.mtl'), paths['before'].parent),
                                                (parse_mtl(candidate / after.mtllib), candidate)])
        assert not looks.unknown(before) and not looks.unknown(after)
        table = LookTable()
        lb = face_look_ids(before, looks, table)
        la = face_look_ids(after, looks, table)
        source_ids = np.asarray(json.loads(paths['mapping'].read_text())['source_faces'], dtype=np.int64)
        drop = np.ones(before.n_faces, dtype=bool)
        drop[source_ids] = False
        precision, masks = [], []
        for label, step in [('stored', print_step(before)), ('physical', max(expected.physical_quanta))]:
            fb = face_fingerprints(before, step, lb)
            fa = face_fingerprints(after, step, la)
            missing = ~_rows_in(fb, fa)
            added = ~_rows_in(fa, fb)
            assert np.array_equal(fb[source_ids], fa), label + ' retained fingerprint mismatch'
            assert np.array_equal(missing, drop), label + ' removed membership mismatch'
            assert not added.any(), label + ' added fingerprint'
            masks.append(missing)
            precision.append(dict(grid=label, step_inches=step, depth_tolerance_inches=depth_tolerance(step),
                                  before_unique=len(np.unique(fb, axis=0)), after_unique=len(np.unique(fa, axis=0)),
                                  removed_faces=int(missing.sum()), added_faces=int(added.sum()),
                                  membership_matches_exact_source_survivors=True))
        assert np.array_equal(*masks)
        assert depth_tolerance(print_step(before)) == depth_tolerance(max(expected.physical_quanta))
        hashes = {key: sha256_file(path) for key, path in paths.items()}
        readback = dict(job_id=args.job_id, floor_id=F, reviewer=args.reviewer,
                        source_revision=proof['source_revision'], pid=os.getpid(), readback_utc=now(),
                        paths={key: str(path) for key, path in paths.items()}, hashes=hashes,
                        source_sig_digits=source.mesh.sig_digits, physical_axis_quanta_inches=expected.physical_quanta,
                        input_triangles=before.n_faces, output_triangles=after.n_faces, removed_triangles=int(drop.sum()),
                        contract=contract, assets=assets, precision=precision, stored_physical_membership_equal=True,
                        material_order_equal=True, source_to_engine=frame.matrix.tolist(), acceptance=False)
        (out / 'input-readback.json').write_text(json.dumps(readback, indent=2), encoding='utf-8')
        spec = importlib.util.spec_from_file_location('independent_existing_strict_guard', paths['helper'])
        module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)

        def view_done(label, index):
            (out / 'guard-progress.json').write_text(json.dumps(dict(job_id=args.job_id, floor_id=F, phase='strict26 guard',
                pair=label, completed_views=index, views_per_pair=26, pid=os.getpid(), observed_utc=now())), encoding='utf-8')

        report, tol = module.strict_guard(before, after, source.mesh, provenance, on_view=view_done)
        for key, path in paths.items():
            assert sha256_file(path) == hashes[key], 'guard input changed: ' + key
        _verify_assets(paths['raw'], run / 'normalized' / F, candidate, paths['before'].parent, source.mesh, provenance, audit)
        receipt = dict(**readback, guard=asdict(report), guard_depth_tol_inches=tol,
                       resolution=[900, 600], views=26, caster='unchanged E3 worktree EmbreeCaster default',
                       wall_s=round(time.perf_counter() - started, 3), finished_utc=now(),
                       post_guard_input_hashes=dict(before=sha256_file(paths['before']), after=sha256_file(paths['after']),
                                                    source_after=sha256_file(paths['source_after']), matches_receipt=True))
        receipt_path = out / 'independent-guard.json'
        receipt_path.write_text(json.dumps(receipt, indent=2), encoding='utf-8')
        print(json.dumps(dict(guard_passed=report.passed, guard_receipt=str(receipt_path),
                              receipt_sha256=sha256_file(receipt_path), totals=report.totals, wall_s=receipt['wall_s'])), flush=True)
        return 0 if report.passed else 2
    except Exception:
        (out / 'failure.txt').write_text(traceback.format_exc(), encoding='utf-8')
        raise


if __name__ == '__main__':
    raise SystemExit(main())
