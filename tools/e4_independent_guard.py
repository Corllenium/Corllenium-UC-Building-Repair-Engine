"""Independent saved-E4 candidate readback plus the unchanged strict 26-view guard, for any fresh floor.

The E4 twin of `tools/e3_independent_guard.py` (the 4F-7F worktree; that file is not touched): the same frozen-source
manifest, qualification, provenance, snapshot and asset checks, then the E4 binding (`bind_saved_e4`: positions
identical, kept faces identical, every new triangle inside its region's plane and footprint, materials, hashes, the
chain through the E3 candidate for `e3_then_e4_merge`), then the UNCHANGED `strict_guard` loaded by path from
`--helper` (`tools/main_infra_candidate.py` of the clean worktree; `--original-oracle` loads
`engine/rays/bounded_brute.py` beside it as the caster). The guard compares material IDS, and `read_obj` numbers a
candidate's materials by first use, so the AFTER's ids are rebound to the BEFORE's by NAME before the guard runs
(`material_ids_rebound_by_name`; `material_order_equal` says whether that changed anything).

Writes `input-readback.json` and `independent-guard.json` with the E3 guard's keys (`removed_triangles` here counts
the faces the candidate no longer has as such: E3-removed plus E4-replaced; `new_triangles` the merged ones). Run with
PYTHONPATH = this worktree.
"""
import argparse
import importlib.util
import json
import os
import sys
import time
import traceback
from dataclasses import asdict, replace
from datetime import datetime, timezone
from pathlib import Path

import numpy as np

from engine.io.minecraft_floor import Frame, parse_floor
from engine.io.mtl import parse_mtl
from engine.io.obj_reader import read_obj
from engine.io.snapshot import sha256_file
from engine.validate.checks import depth_tolerance, load_looks, print_step
from tools.main_infra_e4_binding import bind_saved_e4
from tools.main_infra_physical_validation import _same_mesh, _verify_assets

DEFAULT_REVISION = '7b2f7451b5723f724a1e074fdedc07dbcf7291d330ae550066f4926886136511'


def now():
    return datetime.now(timezone.utc).isoformat()


def rebind_materials(before, after):
    """`after` with its material ids renumbered to `before`'s by name (the guard compares ids)."""
    index = {name: i for i, name in enumerate(before.materials)}
    if any(name not in index for name in after.materials):
        raise ValueError('candidate names a material the BEFORE does not have')
    table = np.array([index[name] for name in after.materials], np.int64)
    face_material = np.where(after.face_material >= 0, table[np.maximum(after.face_material, 0)], after.face_material)
    return replace(after, face_material=face_material.astype(after.face_material.dtype), materials=list(before.materials))


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--root', type=Path, required=True, help='run root: raw/, reference/, normalized/, independent-validator/')
    parser.add_argument('--floor', required=True)
    parser.add_argument('--raw-name', required=True)
    parser.add_argument('--candidate', type=Path, required=True, help='the saved E4 candidate directory')
    parser.add_argument('--out', type=Path, required=True)
    parser.add_argument('--helper', type=Path, required=True, help='tools/main_infra_candidate.py holding strict_guard')
    parser.add_argument('--job-id', required=True)
    parser.add_argument('--reviewer', required=True)
    parser.add_argument('--expected-revision', default=DEFAULT_REVISION)
    parser.add_argument('--original-oracle', action='store_true',
                        help='bounded float64 caster (engine/rays/bounded_brute.py beside --helper) for precision-sensitive floors')
    args = parser.parse_args(argv)
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
                 audit=candidate / 'stage-audit.json', mapping=candidate / 'region-map.json',
                 edit_log=candidate / 'edit-log.jsonl', after=candidate / 'candidate.engine.obj',
                 source_after=candidate / 'candidate.source.obj', helper=args.helper.resolve())
    try:
        manifest = json.loads(paths['manifest'].read_text(encoding='utf-8'))
        assert manifest['source_revision'] == args.expected_revision, 'frozen source revision differs'
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
        if isinstance(audit.get('e3_candidate'), dict) and audit['e3_candidate'].get('candidate'):
            e3_dir = Path(audit['e3_candidate']['candidate'])
            paths.update(e3_candidate=e3_dir / 'candidate.engine.obj', e3_source_candidate=e3_dir / 'candidate.source.obj',
                         e3_source_faces=e3_dir / 'source-faces.json', e3_audit=e3_dir / 'stage-audit.json')
        if isinstance(audit.get('e5_candidate'), dict) and audit['e5_candidate'].get('candidate'):
            e5_dir = Path(audit['e5_candidate']['candidate'])
            paths.update(e5_candidate=e5_dir / 'candidate.engine.obj', e5_source_candidate=e5_dir / 'candidate.source.obj',
                         e5_source_faces=e5_dir / 'source-faces.json', e5_audit=e5_dir / 'stage-audit.json')
        source = parse_floor(paths['raw'].read_text(encoding='utf-8'),
                             triangulations={int(k): v for k, v in native['polygons'].items()})
        frame = Frame(1000 / 25.4, provenance.get('frame_evidence', ''))
        assert np.array_equal(np.asarray(provenance['source_to_engine']), frame.matrix)
        expected = source.in_frame(frame).mesh
        before, after, source_after = read_obj(paths['before']), read_obj(paths['after']), read_obj(paths['source_after'])
        _same_mesh(before, expected)
        _same_mesh(read_obj(paths['source_baseline']), source.mesh)
        # this guard produces the verdict the audit's guard.passed records, so it does not require it
        contract = bind_saved_e4(candidate=candidate, audit=audit, before_engine=expected, after_engine=after,
                                 before_source=source.mesh, after_source=source_after, require_guard=False)
        assets = _verify_assets(paths['raw'], run / 'normalized' / F, candidate, paths['before'].parent,
                                source.mesh, provenance, audit)
        looks = load_looks(paths['materials'], [(parse_mtl(paths['before'].parent / 'materials.mtl'), paths['before'].parent),
                                                (parse_mtl(candidate / after.mtllib), candidate)])
        assert not looks.unknown(before) and not looks.unknown(after)
        material_order_equal = before.materials == after.materials
        after_bound = rebind_materials(before, after)
        # `before` is the qualified baseline: its faces are the kept ones plus everything the chained stages took
        # (E3 removed, E5 culled) plus what E4 replaced; `bind_saved_e4` has already proven the kept faces against the
        # chained BEFORE and mapped them back to the baseline's ids
        kept = int(len(contract['baseline_kept_source_faces']))
        replaced = int(contract['e3_removed_triangles'] + contract.get('e5_removed_triangles', 0)
                       + contract['e4_replaced_triangles'])
        new = int(contract['e4_new_triangles'])
        assert before.n_faces == kept + replaced and after.n_faces == kept + new, \
            (before.n_faces, after.n_faces, kept, replaced, new)
        precision = []
        for label, step in [('stored', print_step(before)), ('physical', max(expected.physical_quanta))]:
            precision.append(dict(grid=label, step_inches=step, depth_tolerance_inches=depth_tolerance(step),
                                  kept_faces=kept, removed_faces=replaced, added_faces=new,
                                  kept_faces_identical=True, new_faces_inside_region_footprint=True))
        assert depth_tolerance(print_step(before)) == depth_tolerance(max(expected.physical_quanta))
        hashes = {key: sha256_file(path) for key, path in paths.items()}
        readback = dict(job_id=args.job_id, floor_id=F, reviewer=args.reviewer,
                        source_revision=proof['source_revision'], pid=os.getpid(), readback_utc=now(),
                        paths={key: str(path) for key, path in paths.items()}, hashes=hashes,
                        manifest_files=len(manifest['files']),
                        source_sig_digits=source.mesh.sig_digits, physical_axis_quanta_inches=expected.physical_quanta,
                        input_triangles=before.n_faces, output_triangles=after.n_faces, removed_triangles=replaced,
                        new_triangles=new, contract=contract, assets=assets, precision=precision,
                        stored_physical_membership_equal=True, material_order_equal=material_order_equal,
                        material_ids_rebound_by_name=True, source_to_engine=frame.matrix.tolist(), acceptance=False)
        (out / 'input-readback.json').write_text(json.dumps(readback, indent=2), encoding='utf-8')
        spec = importlib.util.spec_from_file_location('independent_existing_strict_guard', paths['helper'])
        module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)
        caster_kwargs = {}
        if args.original_oracle:
            oracle_path = paths['helper'].parent.parent / 'engine' / 'rays' / 'bounded_brute.py'
            oracle_spec = importlib.util.spec_from_file_location('independent_bounded_brute', oracle_path)
            oracle = importlib.util.module_from_spec(oracle_spec)
            oracle_spec.loader.exec_module(oracle)
            caster_kwargs['caster_factory'] = oracle.BoundedBruteCaster

        def view_done(label, index):
            (out / 'guard-progress.json').write_text(json.dumps(dict(job_id=args.job_id, floor_id=F, phase='strict26 guard',
                pair=label, completed_views=index, views_per_pair=26, pid=os.getpid(), observed_utc=now())), encoding='utf-8')

        report, tol = module.strict_guard(before, after_bound, source.mesh, provenance, on_view=view_done, **caster_kwargs)
        for key, path in paths.items():
            assert sha256_file(path) == hashes[key], 'guard input changed: ' + key
        _verify_assets(paths['raw'], run / 'normalized' / F, candidate, paths['before'].parent, source.mesh, provenance, audit)
        receipt = dict(**readback, guard=asdict(report), guard_depth_tol_inches=tol,
                       resolution=[900, 600], views=26,
                       caster='BoundedBruteCaster (original float64 oracle)' if args.original_oracle else 'unchanged helper EmbreeCaster default',
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
    sys.exit(main())
