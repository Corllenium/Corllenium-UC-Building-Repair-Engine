"""Build a duplicate-only pilot candidate from a qualified saved fresh-floor baseline."""
import argparse
from dataclasses import asdict
import json
from pathlib import Path
import threading

import numpy as np

from engine.fixes.precut_cleanup import cleanup, verify_exact_coverage
from engine.fixes.pipeline import FixProfile, guard_depth_tol
from engine.guard.compare import compare_views, face_planes
from engine.guard.views import VIEWS_26, ortho_first_hit
from engine.io.minecraft_floor import parse_floor, write_floor
from engine.io.snapshot import copy_verified, sha256_file, snapshot_object
from engine.rays.caster import EmbreeCaster, ReusableCaster
from engine.topo.weld import axis_quanta
try:
    from tools.main_infra_progress import FLOORS as FLOOR_CHOICES
except ImportError:  # loaded by path from a worktree without the progress helper (independent guard)
    FLOOR_CHOICES = tuple(f'{n}F' for n in range(1, 8))


def strict_guard(before, after, source, provenance, *, caster_factory=EmbreeCaster, on_view=None):
    center = (before.positions.min(axis=0) + before.positions.max(axis=0)) / 2
    positions = before.positions - center
    def render(mesh, label):
        factory = ReusableCaster(caster_factory)
        rendered = []
        for index, view in enumerate(VIEWS_26, 1):
            rendered.append((view, ortho_first_hit(positions, mesh.face_v, np.arange(mesh.n_faces),
                             view, positions, (900, 600), factory)))
            print(f'GUARD rendered {mesh.n_faces} triangles view {index}/26', flush=True)
            if on_view:
                on_view(label, index)
        return rendered
    quanta = np.abs(np.asarray(provenance['source_to_engine'])[:3, :3]) @ axis_quanta(source.positions, source.sig_digits)
    depth_tol = guard_depth_tol(quanta, FixProfile())
    print(f'GUARD original sig_digits={source.sig_digits}, transformed quanta={quanta.tolist()}, existing depth tolerance={depth_tol}in', flush=True)
    before_views, after_views = render(before, 'Before'), render(after, 'After')
    print('GUARD comparing saved 26-view buffers', flush=True)
    report = compare_views(before_views, after_views, before.face_material, after.face_material, (),
        depth_tol, strict=True, plane_before=face_planes(positions, before.face_v),
        plane_after=face_planes(positions, after.face_v),
        geometry_before=(positions, before.face_v), geometry_after=(positions, after.face_v),
        caster_factory=caster_factory,
        crack_closed_cap=0.0, fragment_removed_cap=0.0)
    return report, depth_tol


def build_candidate(baseline, qualification, out, *, caster_factory=EmbreeCaster, on_view=None):
    baseline, qualification, out = Path(baseline), Path(qualification), Path(out)
    proof = json.loads(qualification.read_text(encoding='utf-8'))
    provenance = json.loads((baseline / 'geometry-provenance.json').read_text(encoding='utf-8'))
    for key, filename in [('engine_obj_sha256', 'before.engine.obj'),
                          ('source_triangles_sha256', 'before.source.obj')]:
        if not proof.get('qualified') or proof.get(key) != sha256_file(baseline / filename):
            raise ValueError('Import qualification hash missing or mismatched')
    for asset in provenance['assets']:
        path = (baseline / asset['path']).resolve()
        if not path.is_relative_to(baseline.resolve()) or sha256_file(path) != asset['sha256']:
            raise ValueError('Baseline asset hash changed')
    if out.exists():
        raise ValueError('Candidate destination exists; refusing overwrite')
    engine = parse_floor((baseline / 'before.engine.obj').read_text(encoding='utf-8'))
    source = parse_floor((baseline / 'before.source.obj').read_text(encoding='utf-8'))
    result = cleanup(engine.mesh)
    print(f'CLEANUP {engine.mesh.n_faces}->{result.mesh.n_faces}, exact duplicates={len(result.removed_to_survivor)}', flush=True)
    keep = np.zeros(engine.mesh.n_faces, bool)
    keep[result.source_faces] = True
    from engine.fixes.remove import remove_faces
    source_candidate, _ = remove_faces(source.mesh, ~keep)
    source_coverage = verify_exact_coverage(source.mesh, source_candidate)
    guard, depth_tol = strict_guard(engine.mesh, result.mesh, source.mesh, provenance, caster_factory=caster_factory, on_view=on_view)
    if not guard.passed:
        raise ValueError(f'Strict existing 26-view guard refused candidate: {guard.totals}')
    out.mkdir(parents=True)
    for asset in provenance['assets']:
        target = out / asset['path']
        target.parent.mkdir(parents=True, exist_ok=True)
        copy_verified(baseline / asset['path'], target, interval_s=0)
    engine_path, source_path = out / 'candidate.engine.obj', out / 'candidate.source.obj'
    write_floor(engine, engine_path, keep_triangles=keep)
    write_floor(source, source_path, keep_triangles=keep)
    saved_engine = parse_floor(engine_path.read_text(encoding='utf-8')).mesh
    saved_source = parse_floor(source_path.read_text(encoding='utf-8')).mesh
    verify_exact_coverage(engine.mesh, saved_engine)
    verify_exact_coverage(source.mesh, saved_source)
    snapshot = snapshot_object(baseline / 'before.engine.obj', out / 'before-snapshots', interval_s=0)
    events = [{'stage': 'exact_duplicates', 'source_triangle': removed, 'survivor_triangle': survivor,
               'reason': 'identical oriented corners, UVs, normals and material; existing survivor retained'}
              for removed, survivor in sorted(result.removed_to_survivor.items())]
    (out / 'edit-log.jsonl').write_text(''.join(json.dumps(row) + '\n' for row in events), encoding='utf-8')
    report = {'input_triangles': engine.mesh.n_faces, 'output_triangles': saved_engine.n_faces,
        'ray_caster': caster_factory.__name__,
        'removed_exact_duplicates': len(events), 'source_corner_positions_changed': 0,
        'source_coverage': source_coverage, 'engine_coverage': result.coverage,
        'executed_stages': list(result.executed), 'disabled_stages': list(result.disabled),
        'guard_depth_tol_inches': depth_tol,
        'guard_precision_basis': 'existing guard_depth_tol/FixProfile defaults applied to original source axis_quanta transformed into inches; normalized decimal padding is not new source precision',
        'guard': asdict(guard), 'before_snapshot': str(snapshot.dir.resolve()),
        'engine_candidate': str(engine_path.resolve()), 'source_candidate': str(source_path.resolve()),
        'engine_candidate_sha256': sha256_file(engine_path), 'source_candidate_sha256': sha256_file(source_path),
        'qualification_sha256': sha256_file(qualification), 'accepted': False,
        'independent_validation': 'pending', 'skp': 'not produced',
        'assets': [{'path': asset['path'], 'sha256': sha256_file(out / asset['path'])} for asset in provenance['assets']]}
    (out / 'stage-audit.json').write_text(json.dumps(report, indent=2), encoding='utf-8')
    return report


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--baseline', type=Path, required=True)
    parser.add_argument('--qualification', type=Path, required=True)
    parser.add_argument('--out', type=Path, required=True)
    parser.add_argument('--floor', choices=list(FLOOR_CHOICES), required=True)
    parser.add_argument('--progress', type=Path)
    parser.add_argument('--publish-status', type=Path)
    parser.add_argument('--trace-after-seconds', type=int)
    parser.add_argument('--original-oracle', action='store_true', help='Use bounded original float64 oracle for precision-sensitive pilot rays')
    args = parser.parse_args()
    if args.trace_after_seconds:
        import faulthandler
        faulthandler.dump_traceback_later(args.trace_after_seconds)
    from tools.main_infra_progress import heartbeat_progress, update_floor
    stop = threading.Event()
    heartbeat_errors = []
    def pulse():
        while not stop.wait(10):
            try:
                heartbeat_progress(args.progress, published_path=args.publish_status)
            except (ValueError, OSError) as exc:
                heartbeat_errors.append(str(exc))
                return
    worker = None
    if args.progress:
        update_floor(args.progress, args.floor, 'cleaning', 'Exact duplicate cleanup and strict 26-view guard running', published_path=args.publish_status)
        worker = threading.Thread(target=pulse, daemon=True)
        worker.start()
    try:
        if args.original_oracle:
            from engine.rays.bounded_brute import BoundedBruteCaster
        def publish_view(label, index):
            if args.progress:
                update_floor(args.progress, args.floor, 'cleaning', f'Strict guard {label} view {index}/26 rendered; comparing original floor geometry',
                             published_path=args.publish_status)
        report = build_candidate(args.baseline, args.qualification, args.out,
                                 caster_factory=BoundedBruteCaster if args.original_oracle else EmbreeCaster, on_view=publish_view)
        if heartbeat_errors:
            raise ValueError(f'Worker progress publication failed: {heartbeat_errors}')
        if args.progress:
            update_floor(args.progress, args.floor, 'validating', 'Candidate saved; independent full-floor validation pending',
                input_triangles=report['input_triangles'], output_triangles=report['output_triangles'], published_path=args.publish_status)
        print(json.dumps({key: report[key] for key in ['input_triangles', 'output_triangles', 'removed_exact_duplicates', 'before_snapshot', 'engine_candidate']}))
    except (ValueError, OSError) as exc:
        if args.progress:
            update_floor(args.progress, args.floor, 'blocked', 'Cleanup refused; qualified baseline retained', blocker=str(exc), published_path=args.publish_status)
        raise
    finally:
        if args.trace_after_seconds:
            faulthandler.cancel_dump_traceback_later()
        stop.set()
        if worker:
            worker.join()


if __name__ == '__main__':
    main()
