"""The same strict 26-view guard and the same signed Validator, run on ANY fresh MAIN INFRA candidate.

Owner decision 2026-10-29 ("Validate both, keep the better"): Codex's and Claude's 4F-7F candidates are judged by one
identical, independent measurement so the better one per floor can be published. The candidate only has to be a
`candidate.engine.obj` / `candidate.source.obj` pair with its MTL and textures beside it; no stage-audit schema is
needed. What is checked, in order:

1. The qualified baseline (frozen raw OBJ, Blender reference, normalized BEFORE pair, import qualification,
   geometry provenance) is hash-bound exactly as `tools.main_infra_physical_validation.load_physical_pair` binds it.
2. The candidate keeps the baseline's vertex, UV, normal and material tables; every AFTER face lies on a BEFORE face
   (`verify_exact_coverage`, engine and source frames); face membership (retained / removed / added) is counted in
   both frames and must agree.
3. The candidate's MTL and textures hash-equal the qualified baseline assets.
4. Optional `--drop-before-faces`: the owner-authorized orange marker faces (approved-selection.json, 24 per floor)
   are removed from BEFORE first, so a candidate that dropped them is not charged for them; they must all be gone
   from the candidate. Recorded in the receipt.
5. `strict_guard` from `--helper` (tools/main_infra_candidate.py of the Claude worktree): 26 orthographic views,
   zero tolerance, optionally the float64 `BoundedBruteCaster` oracle (`--original-oracle`).
6. `engine.validate.checks.validate` with the owner's signed targets, under the `--allow` classes (recorded).

Receipt: `<out>/external-validation.json` (one JSON with every hash, count and verdict), `<out>/guard.json`,
`<out>/validation/validation.json` plus evidence crops. Exit 0 = guard PASS and Validator PASS; 2 = measured FAIL.
"""
from __future__ import annotations

import argparse
import ctypes
import importlib.util
import json
import os
import subprocess
import sys
import time
import traceback
from dataclasses import asdict, replace
from datetime import datetime, timezone
from pathlib import Path

import numpy as np

from engine.fixes.precut_cleanup import verify_exact_coverage
from engine.io.minecraft_floor import Frame, parse_floor
from engine.io.mtl import parse_mtl
from engine.io.obj_reader import read_obj
from engine.io.snapshot import sha256_file
from engine.model import MeshData
from engine.validate.checks import _rows_in, load_looks
from tools.main_infra_physical_validation import _same_mesh, settings_for

DEFAULT_REVISION = '7b2f7451b5723f724a1e074fdedc07dbcf7291d330ae550066f4926886136511'


def now() -> str:
    return datetime.now(timezone.utc).isoformat()


def face_rows(mesh: MeshData) -> np.ndarray:
    """One int64 row per face: corners, UV corners, normal corners and the material index; identical rows are
    the same face with the same look."""
    return np.column_stack([mesh.face_v, mesh.face_vt, mesh.face_vn, mesh.face_material.reshape(-1, 1)]).astype(np.int64)


def membership(before: MeshData, after: MeshData):
    """(counts, removed BEFORE mask, added AFTER mask). `added` faces are new geometry (cuts) or re-looked faces."""
    rows_before, rows_after = face_rows(before), face_rows(after)
    kept_after = _rows_in(rows_after, rows_before)
    retained_before = _rows_in(rows_before, rows_after)
    counts = dict(before_faces=int(len(rows_before)), after_faces=int(len(rows_after)), retained=int(kept_after.sum()),
                  removed=int((~retained_before).sum()), added=int((~kept_after).sum()))
    return counts, ~retained_before, ~kept_after


def drop_faces(mesh: MeshData, ids) -> MeshData:
    """`mesh` without the faces at `ids` (face order kept). Out-of-range or repeated ids are a ValueError."""
    ids = [int(i) for i in ids]
    n = len(mesh.face_v)
    if len(set(ids)) != len(ids) or any(i < 0 or i >= n for i in ids):
        raise ValueError(f'face ids to drop must be distinct and within 0..{n - 1}')
    keep = np.ones(n, dtype=bool)
    keep[ids] = False
    return replace(mesh, face_v=mesh.face_v[keep].copy(), face_vt=mesh.face_vt[keep].copy(), face_vn=mesh.face_vn[keep].copy(),
                   face_material=mesh.face_material[keep].copy(), face_line=mesh.face_line[keep].copy())


def orange_face_ids(selection: Path, floor: str) -> list[int]:
    """The owner-approved marker faces of `floor` from Codex's approved-selection.json (original face ids)."""
    doc = json.loads(Path(selection).read_text(encoding='utf-8'))
    for entry in doc.get('floors', []):
        if entry.get('floor') == floor:
            return [int(i) for i in entry['original_face_ids']]
    raise ValueError(f'no approved orange selection for {floor}')


def free_physical_gb() -> float | None:
    if os.name != 'nt':
        return None

    class Status(ctypes.Structure):
        _fields_ = [('dwLength', ctypes.c_ulong), ('dwMemoryLoad', ctypes.c_ulong), ('ullTotalPhys', ctypes.c_ulonglong),
                    ('ullAvailPhys', ctypes.c_ulonglong), ('ullTotalPageFile', ctypes.c_ulonglong),
                    ('ullAvailPageFile', ctypes.c_ulonglong), ('ullTotalVirtual', ctypes.c_ulonglong),
                    ('ullAvailVirtual', ctypes.c_ulonglong), ('ullAvailExtendedVirtual', ctypes.c_ulonglong)]
    status = Status()
    status.dwLength = ctypes.sizeof(Status)
    ctypes.windll.kernel32.GlobalMemoryStatusEx(ctypes.byref(status))
    return status.ullAvailPhys / 2 ** 30


def wait_for_ram(min_free_gb: float, max_wait_s: float, label: str) -> float | None:
    started = time.monotonic()
    while True:
        free = free_physical_gb()
        if free is None or free >= min_free_gb:
            return free
        if time.monotonic() - started > max_wait_s:
            raise RuntimeError(f'{label}: free RAM {free:.1f} GB below the {min_free_gb} GB gate for {max_wait_s:.0f}s')
        print(f'{label}: waiting for RAM ({free:.1f} GB free, gate {min_free_gb} GB)', flush=True)
        time.sleep(30)


def git_head(path: Path) -> str | None:
    try:
        return subprocess.run(['git', '-C', str(path), 'rev-parse', 'HEAD'], capture_output=True, text=True, check=True,
                              timeout=30).stdout.strip()
    except Exception:
        return None


def verify_candidate_assets(provenance: dict, candidate: Path) -> list[dict]:
    """Every qualified baseline asset (MTL, textures) must exist under the candidate with the same hash."""
    rows = provenance.get('assets')
    if not isinstance(rows, list) or not rows:
        raise ValueError('baseline provenance has no asset inventory')
    verified = []
    for row in rows:
        path = (candidate / row['path']).resolve()
        if not path.is_relative_to(candidate.resolve()):
            raise ValueError('asset path escapes the candidate package')
        actual = sha256_file(path)
        if actual != row['sha256']:
            raise ValueError(f'candidate asset differs from the qualified baseline: {row["path"]}')
        verified.append(dict(path=row['path'], sha256=actual))
    return verified


def build_parser():
    from engine.validate.checks import ALLOWED_CHANGE_CLASSES
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument('--root', type=Path, required=True, help='run root: raw/, reference/, normalized/, independent-validator/')
    parser.add_argument('--floor', required=True)
    parser.add_argument('--raw-name', required=True)
    parser.add_argument('--snapshot', type=Path, required=True, help='qualified BEFORE snapshot dir (before.engine.obj, materials.mtl, tex/)')
    parser.add_argument('--candidate', type=Path, required=True, help='dir holding candidate.engine.obj and candidate.source.obj')
    parser.add_argument('--out', type=Path, required=True)
    parser.add_argument('--helper', type=Path, required=True, help='tools/main_infra_candidate.py holding strict_guard')
    parser.add_argument('--label', required=True, help='candidate label for the comparison table, e.g. codex-omb-58064')
    parser.add_argument('--worker', required=True, choices=['codex', 'claude'])
    parser.add_argument('--job-id', required=True)
    parser.add_argument('--reviewer', required=True)
    parser.add_argument('--expected-revision', default=DEFAULT_REVISION)
    parser.add_argument('--allow', action='append', default=[], choices=sorted(ALLOWED_CHANGE_CLASSES))
    parser.add_argument('--original-oracle', action='store_true', help='float64 BoundedBruteCaster oracle for the guard')
    parser.add_argument('--drop-before-faces', type=Path, default=None,
                        help='approved-selection.json: drop that floor\'s owner-authorized orange marker faces from BEFORE')
    parser.add_argument('--min-free-gb', type=float, default=5.0)
    parser.add_argument('--max-wait-s', type=float, default=7200.0)
    return parser


def main(argv=None):
    args = build_parser().parse_args(argv)
    from engine.campus.winprobe import peak_memory_mb
    from engine.io.protected import refuse_protected
    from engine.validate.checks import default_targets_path, load_targets, validate
    from engine.validate.evidence import write_evidence
    run, F = args.root.resolve(), args.floor
    candidate, out, snapshot = args.candidate.resolve(), args.out.resolve(), args.snapshot.resolve()
    refuse_protected(out)
    if out.exists():
        raise ValueError('external validation output exists; refusing overwrite')
    out.mkdir(parents=True)
    started = time.perf_counter()
    try:
        paths = dict(manifest=run / 'raw-manifest.json', raw=run / 'raw' / args.raw_name, reference=run / 'reference' / f'{F}.json',
                     qualification=run / 'independent-validator' / 'import-audit' / f'qualification-{F}.json',
                     provenance=run / 'normalized' / F / 'geometry-provenance.json',
                     source_baseline=run / 'normalized' / F / 'before.source.obj',
                     engine_baseline=run / 'normalized' / F / 'before.engine.obj',
                     materials=run / 'independent-validator' / 'preflight' / f'materials-{F}.json',
                     before=snapshot / 'before.engine.obj', before_mtl=snapshot / 'materials.mtl',
                     after=candidate / 'candidate.engine.obj', source_after=candidate / 'candidate.source.obj',
                     helper=args.helper.resolve())
        manifest = json.loads(paths['manifest'].read_text(encoding='utf-8'))
        assert manifest['source_revision'] == args.expected_revision and len(manifest['files']) == 36
        for row in manifest['files']:
            assert sha256_file(run / 'raw' / row['path']) == row['sha256'], 'Frozen source changed: ' + row['path']
        proof = json.loads(paths['qualification'].read_text(encoding='utf-8'))
        provenance = json.loads(paths['provenance'].read_text(encoding='utf-8'))
        native = json.loads(paths['reference'].read_text(encoding='utf-8'))
        assert proof['qualified'] is True and proof['floor_id'] == F and proof['source_revision'] == args.expected_revision
        for key, name in [('source_obj_sha256', 'raw'), ('native_reference_sha256', 'reference'),
                          ('source_triangles_sha256', 'source_baseline'), ('engine_obj_sha256', 'engine_baseline'),
                          ('engine_obj_sha256', 'before')]:
            assert sha256_file(paths[name]) == proof[key], name
        for key, proof_key in [('source_sha256', 'source_obj_sha256'), ('reference_sha256', 'native_reference_sha256'),
                               ('source_triangles_sha256', 'source_triangles_sha256'), ('engine_obj_sha256', 'engine_obj_sha256')]:
            assert provenance.get(key) == proof[proof_key], 'provenance hash differs: ' + key
        assert native['source_sha256'] == proof['source_obj_sha256'] and native['unmatched_polygons'] == 0
        source = parse_floor(paths['raw'].read_text(encoding='utf-8'),
                             triangulations={int(k): v for k, v in native['polygons'].items()})
        frame = Frame(1000 / 25.4, provenance.get('frame_evidence', ''))
        assert np.array_equal(np.asarray(provenance['source_to_engine']), frame.matrix)
        expected = source.in_frame(frame).mesh
        before, after, source_after = read_obj(paths['before']), read_obj(paths['after']), read_obj(paths['source_after'])
        _same_mesh(before, expected)
        _same_mesh(read_obj(paths['source_baseline']), source.mesh)
        for field in ('positions', 'uvs', 'normals'):
            assert np.array_equal(getattr(before, field), getattr(after, field)), 'engine vertex table differs: ' + field
            assert np.array_equal(getattr(source.mesh, field), getattr(source_after, field)), 'source vertex table differs: ' + field
        assert before.materials == after.materials, 'engine material order differs'
        assert source.mesh.materials == source_after.materials, 'source material order differs'
        verify_exact_coverage(expected, after)
        verify_exact_coverage(source.mesh, source_after)
        engine_counts, removed_engine, added_engine = membership(before, after)
        source_counts, removed_source, added_source = membership(source.mesh, source_after)
        assert engine_counts == source_counts, f'engine/source membership differ: {engine_counts} vs {source_counts}'
        assert np.array_equal(removed_engine, removed_source), 'engine/source removed faces differ'
        assets = verify_candidate_assets(provenance, candidate)
        dropped = None
        before_judged = before
        if args.drop_before_faces is not None:
            ids = orange_face_ids(args.drop_before_faces, F)
            still_present = [i for i in ids if not removed_engine[i]]
            assert not still_present, f'owner-authorized marker faces still in the candidate: {still_present[:8]}'
            before_judged = drop_faces(before, ids)
            dropped = dict(selection=str(args.drop_before_faces.resolve()), selection_sha256=sha256_file(args.drop_before_faces),
                           face_ids=ids, count=len(ids), reason='owner-authorized orange marker faces (2026-10-26) removed from BEFORE')
        judged_counts, _, _ = membership(before_judged, after)
        hashes = {key: sha256_file(path) for key, path in paths.items()}
        receipt = dict(job_id=args.job_id, floor_id=F, label=args.label, worker=args.worker, reviewer=args.reviewer,
                       source_revision=proof['source_revision'], pid=os.getpid(), started_utc=now(),
                       engine_root=str(Path(__file__).resolve().parents[1]), engine_head=git_head(Path(__file__).resolve().parents[1]),
                       helper=str(paths['helper']), helper_head=git_head(paths['helper'].parents[1]),
                       paths={key: str(path) for key, path in paths.items()}, hashes=hashes,
                       candidate_dir=str(candidate), candidate_engine_sha256=hashes['after'], candidate_source_sha256=hashes['source_after'],
                       input_triangles=int(len(before.face_v)), output_triangles=int(len(after.face_v)),
                       membership=engine_counts, membership_after_drop=judged_counts, dropped_before_faces=dropped,
                       assets=assets, physical_axis_quanta_inches=list(expected.physical_quanta),
                       source_to_engine=frame.matrix.tolist(), allowed_changes=sorted(args.allow), acceptance=False)
        (out / 'external-validation.json').write_text(json.dumps(receipt, indent=2), encoding='utf-8')
        print(json.dumps(dict(phase='bound', label=args.label, membership=engine_counts, dropped=dropped and dropped['count'])), flush=True)

        # 5. the unchanged strict 26-view guard
        receipt['free_ram_gb_before_guard'] = wait_for_ram(args.min_free_gb, args.max_wait_s, args.label)
        spec = importlib.util.spec_from_file_location('external_strict_guard_helper', paths['helper'])
        module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)
        caster_kwargs = {}
        if args.original_oracle:
            oracle_path = paths['helper'].parent.parent / 'engine' / 'rays' / 'bounded_brute.py'
            oracle_spec = importlib.util.spec_from_file_location('external_bounded_brute', oracle_path)
            oracle = importlib.util.module_from_spec(oracle_spec)
            oracle_spec.loader.exec_module(oracle)
            caster_kwargs['caster_factory'] = oracle.BoundedBruteCaster

        def view_done(label, index):
            (out / 'guard-progress.json').write_text(json.dumps(dict(job_id=args.job_id, floor_id=F, label=args.label,
                phase='strict26 guard', pair=label, completed_views=index, views_per_pair=26, pid=os.getpid(),
                observed_utc=now())), encoding='utf-8')

        guard_started = time.perf_counter()
        report, tol = module.strict_guard(before_judged, after, source.mesh, provenance, on_view=view_done, **caster_kwargs)
        guard = dict(passed=bool(report.passed), totals=report.totals, report=asdict(report), depth_tol_inches=tol,
                     resolution=[900, 600], views=26,
                     caster='BoundedBruteCaster (original float64 oracle)' if args.original_oracle else 'EmbreeCaster default',
                     wall_s=round(time.perf_counter() - guard_started, 3), finished_utc=now())
        (out / 'guard.json').write_text(json.dumps(guard, indent=2), encoding='utf-8')
        receipt['guard'] = {k: v for k, v in guard.items() if k != 'report'}
        (out / 'external-validation.json').write_text(json.dumps(receipt, indent=2), encoding='utf-8')
        print(json.dumps(dict(phase='guard', label=args.label, passed=guard['passed'], totals=guard['totals'], wall_s=guard['wall_s'])), flush=True)

        # 6. the signed Validator under the allowed classes
        receipt['free_ram_gb_before_validator'] = wait_for_ram(args.min_free_gb, args.max_wait_s, args.label)
        settings = settings_for(args.allow)
        sources = [(parse_mtl(paths['before_mtl']), snapshot)]
        if after.mtllib:
            sources.append((parse_mtl(candidate / after.mtllib), candidate))
        looks = load_looks(paths['materials'], sources)
        targets_path = default_targets_path()
        targets = load_targets()
        if not targets or targets.get('signed') is not True:
            raise ValueError('signed default problem targets required')
        materials_hash, targets_hash = sha256_file(paths['materials']), sha256_file(targets_path)
        shown = {'tenth': -1}

        def progress(done, total):
            tenth = int(10 * done / max(total, 1))
            if tenth != shown['tenth']:
                shown['tenth'] = tenth
                print(f'{done}/{total} samples cast', file=sys.stderr, flush=True)

        validation_dir = out / 'validation'
        validation_dir.mkdir()
        before_v = replace(before_judged, physical_quanta=expected.physical_quanta)
        after_v = replace(after, physical_quanta=expected.physical_quanta)
        validator_started = time.perf_counter()
        result = validate(before_v, after_v, looks, targets=targets, settings=settings, progress=progress)
        write_evidence(result, validation_dir)
        assert sha256_file(paths['materials']) == materials_hash and sha256_file(targets_path) == targets_hash
        for key, path in paths.items():
            assert sha256_file(path) == hashes[key], 'validator input changed: ' + key
        vreport = dict(allowed_changes_active=sorted(settings.allowed_changes), **result.report)
        vreport['inputs'] = dict(before=str(paths['before']), after=str(paths['after']), materials=str(paths['materials']),
                                 targets=str(targets_path.resolve()), before_sha256=hashes['before'], after_sha256=hashes['after'],
                                 materials_sha256=materials_hash, targets_sha256=targets_hash,
                                 allowed_changes=sorted(settings.allowed_changes), dropped_before_faces=dropped)
        vreport['peak_working_set_mb'], vreport['peak_commit_mb'] = peak_memory_mb()
        vreport['wall_s'] = round(time.perf_counter() - validator_started, 2)
        (validation_dir / 'validation.json').write_text(json.dumps(vreport, indent=2), encoding='utf-8')
        receipt['validator'] = dict(verdict=vreport.get('verdict'), passed=bool(result.passed), checks=vreport.get('checks'),
                                    targets=vreport.get('targets'), allowed_changes_active=sorted(settings.allowed_changes),
                                    wall_s=vreport['wall_s'], path=str(validation_dir / 'validation.json'))
        receipt['passed'] = bool(guard['passed'] and result.passed)
        receipt['wall_s'] = round(time.perf_counter() - started, 3)
        receipt['finished_utc'] = now()
        (out / 'external-validation.json').write_text(json.dumps(receipt, indent=2), encoding='utf-8')
        print(json.dumps(dict(phase='done', label=args.label, guard_passed=guard['passed'], validator=vreport.get('verdict'),
                              checks=vreport.get('checks'), wall_s=receipt['wall_s'])), flush=True)
        return 0 if receipt['passed'] else 2
    except Exception:
        (out / 'failure.txt').write_text(traceback.format_exc(), encoding='utf-8')
        raise


if __name__ == '__main__':
    raise SystemExit(main())
