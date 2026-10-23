"""Validate hash-bound fresh pilots with source precision in the recorded inch frame."""
from dataclasses import replace
import argparse
import json
from pathlib import Path, PurePosixPath
import sys
import time

import numpy as np

from engine.fixes.precut_cleanup import verify_exact_coverage
from engine.io.minecraft_floor import Frame, parse_floor
from engine.io.obj_reader import read_obj
from engine.io.mtl import parse_mtl
from engine.io.snapshot import sha256_file


def _hash(path, expected):
    actual = sha256_file(Path(path))
    if actual != expected:
        raise ValueError(f'hash mismatch: {path}')
    return actual


def _same_mesh(actual, expected):
    for field in ('positions', 'uvs', 'normals', 'face_v', 'face_vt', 'face_vn', 'face_material'):
        if not np.array_equal(getattr(actual, field), getattr(expected, field)):
            raise ValueError(f'qualified frame readback differs: {field}')
    if actual.materials != expected.materials:
        raise ValueError('qualified frame material names differ')


def _verify_assets(raw, baseline, candidate, snapshot, source, provenance, audit):
    assets = provenance.get('assets')
    if not isinstance(assets, list) or audit.get('assets') != assets:
        raise ValueError('candidate asset inventory differs')
    verified = []
    for row in assets:
        for root in (raw.parent, baseline, candidate):
            path = (root / row['path']).resolve()
            if not path.is_relative_to(root.resolve()):
                raise ValueError('asset path escapes qualified package')
            _hash(path, row['sha256'])
        verified.append(dict(path=row['path'], sha256=row['sha256']))
    if not source.mtllib:
        return verified
    material_path = (raw.parent / source.mtllib).resolve()
    by_path = {(raw.parent / row['path']).resolve(): row['sha256'] for row in assets}
    if material_path not in by_path:
        raise ValueError('source material missing from asset inventory')
    _hash(snapshot / 'source.mtl', by_path[material_path])
    materials = parse_mtl(material_path)
    expected = []
    for name in source.materials:
        if name not in materials:
            raise ValueError('source material definition missing')
        material = materials[name]
        expected.append(f'newmtl {name}')
        for line in material.lines:
            if line.startswith('map_Kd ') and material.map_kd:
                rel = material.map_kd.replace(chr(92), '/')
                texture = (material_path.parent / rel).resolve()
                if texture not in by_path:
                    raise ValueError('texture missing from asset inventory')
                basename = PurePosixPath(rel).name
                _hash(snapshot / 'tex' / basename, by_path[texture])
                line = f'map_Kd tex/{basename}'
            expected.append(line)
        expected.append('')
    expected_bytes = '\n'.join(expected).encode('utf-8')
    if (snapshot / 'materials.mtl').read_bytes() != expected_bytes:
        raise ValueError('snapshot material derivation differs')
    verified.append(dict(path='snapshot/materials.mtl', sha256=sha256_file(snapshot / 'materials.mtl')))
    return verified


def load_physical_pair(*, raw, reference, baseline, qualification, candidate):
    raw, reference, baseline, qualification, candidate = map(Path, (raw, reference, baseline, qualification, candidate))
    proof = json.loads(qualification.read_text(encoding='utf-8'))
    provenance = json.loads((baseline / 'geometry-provenance.json').read_text(encoding='utf-8'))
    audit = json.loads((candidate / 'stage-audit.json').read_text(encoding='utf-8'))
    if proof.get('qualified') is not True or not proof.get('floor_id') or not proof.get('source_revision'):
        raise ValueError('independent import qualification required')
    hashes = {}
    for key, path in [('source_obj_sha256', raw), ('native_reference_sha256', reference),
                      ('source_triangles_sha256', baseline / 'before.source.obj'),
                      ('engine_obj_sha256', baseline / 'before.engine.obj')]:
        hashes[key] = _hash(path, proof.get(key))
    _hash(qualification, audit.get('qualification_sha256'))
    for key, proof_key in [('source_sha256', 'source_obj_sha256'),
                           ('reference_sha256', 'native_reference_sha256'),
                           ('source_triangles_sha256', 'source_triangles_sha256'),
                           ('engine_obj_sha256', 'engine_obj_sha256')]:
        if provenance.get(key) != hashes[proof_key]:
            raise ValueError(f'provenance hash differs: {key}')
    snapshots = list(Path(audit['before_snapshot']).glob('*.obj'))
    if len(snapshots) != 1:
        raise ValueError('candidate must bind one BEFORE snapshot')
    before_path, after_path = snapshots[0], candidate / 'candidate.engine.obj'
    _hash(before_path, hashes['engine_obj_sha256'])
    _hash(after_path, audit.get('engine_candidate_sha256'))
    _hash(candidate / 'candidate.source.obj', audit.get('source_candidate_sha256'))
    if audit.get('guard', {}).get('passed') is not True:
        raise ValueError('candidate strict guard required')
    native = json.loads(reference.read_text(encoding='utf-8'))
    if native.get('source_sha256') != hashes['source_obj_sha256'] or native.get('unmatched_polygons') != 0:
        raise ValueError('Reference source or polygon binding differs')
    source = parse_floor(raw.read_text(encoding='utf-8'),
                         triangulations={int(line): value for line, value in native['polygons'].items()})
    assets = _verify_assets(raw, baseline, candidate, before_path.parent, source.mesh, provenance, audit)
    frame = Frame(1000 / 25.4, provenance.get('frame_evidence', ''))
    if not np.array_equal(np.asarray(provenance.get('source_to_engine')), frame.matrix):
        raise ValueError('frame differs from owner scale and qualified Y-up rotation')
    expected = source.in_frame(frame).mesh
    _same_mesh(read_obj(baseline / 'before.source.obj'), source.mesh)
    before, after = read_obj(before_path), read_obj(after_path)
    _same_mesh(before, expected)
    source_after = read_obj(candidate / 'candidate.source.obj')
    cleanup_mode = audit.get('cleanup_mode', 'exact_duplicates')
    if cleanup_mode == 'exact_duplicates':
        verify_exact_coverage(expected, after)
        verify_exact_coverage(source.mesh, source_after)
        contract = dict(candidate_contract='exact_duplicates')
    elif cleanup_mode == 'e3_remove_only':
        from tools.main_infra_e3_binding import bind_saved_e3
        contract = bind_saved_e3(candidate=candidate, audit=audit, before_engine=expected,
                                 after_engine=after, before_source=source.mesh, after_source=source_after)
    else:
        raise ValueError(f'unsupported candidate cleanup contract: {cleanup_mode!r}')
    before = replace(before, physical_quanta=expected.physical_quanta)
    after = replace(after, physical_quanta=expected.physical_quanta)
    receipt = dict(**hashes, floor_id=proof['floor_id'], source_revision=proof['source_revision'],
        before=str(before_path.resolve()), after=str(after_path.resolve()),
        before_sha256=sha256_file(before_path), after_sha256=sha256_file(after_path),
        qualification_sha256=sha256_file(qualification), source_sig_digits=source.mesh.sig_digits,
        source_coord_decimals=source.mesh.coord_decimals, physical_axis_quanta_inches=list(expected.physical_quanta),
        source_to_engine=frame.matrix.tolist(),
        assets=assets, **contract,
        method='original source axis_quanta, transformed by absolute qualified frame; existing topology multipliers unchanged')
    return before, after, receipt


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    for name in ('raw', 'reference', 'baseline', 'qualification', 'candidate', 'materials', 'out'):
        parser.add_argument('--' + name, type=Path, required=True)
    args = parser.parse_args(argv)
    from engine.campus.winprobe import peak_memory_mb
    from engine.io.protected import refuse_protected
    from engine.validate.checks import Settings, default_targets_path, load_looks, load_targets, validate
    from engine.validate.evidence import write_evidence
    started = time.perf_counter()
    refuse_protected(args.out)
    if (args.out / 'validation.json').exists():
        raise ValueError('validation output already exists; refusing overwrite')
    before, after, receipt = load_physical_pair(raw=args.raw, reference=args.reference, baseline=args.baseline,
                                               qualification=args.qualification, candidate=args.candidate)
    before_dir = Path(receipt['before']).parent
    sources = [(parse_mtl(before_dir / 'materials.mtl'), before_dir)]
    if after.mtllib:
        sources.append((parse_mtl(args.candidate / after.mtllib), args.candidate))
    looks = load_looks(args.materials, sources)
    targets_path = default_targets_path()
    targets = load_targets()
    if not targets or targets.get('signed') is not True:
        raise ValueError('signed default problem targets required')
    materials_hash, targets_hash = sha256_file(args.materials), sha256_file(targets_path)
    shown = {'tenth': -1}
    def progress(done, total):
        tenth = int(10 * done / max(total, 1))
        if tenth != shown['tenth']:
            shown['tenth'] = tenth
            print(f'{done}/{total} samples cast', file=sys.stderr, flush=True)
    args.out.mkdir(parents=True, exist_ok=True)
    (args.out / 'physical-precision-inputs.json').write_text(json.dumps(receipt, indent=2), encoding='utf-8')
    result = validate(before, after, looks, targets=targets, settings=Settings(), progress=progress)
    write_evidence(result, args.out)
    _hash(args.materials, materials_hash)
    _hash(targets_path, targets_hash)
    load_physical_pair(raw=args.raw, reference=args.reference, baseline=args.baseline,
                       qualification=args.qualification, candidate=args.candidate)
    report = result.report
    report['inputs'] = dict(before=receipt['before'], after=receipt['after'], materials=str(args.materials.resolve()),
        targets=str(targets_path.resolve()), before_sha256=receipt['before_sha256'], after_sha256=receipt['after_sha256'],
        materials_sha256=materials_hash, targets_sha256=targets_hash)
    report['physical_precision'] = receipt
    report['peak_working_set_mb'], report['peak_commit_mb'] = peak_memory_mb()
    report['wall_s'] = round(time.perf_counter() - started, 2)
    (args.out / 'validation.json').write_text(json.dumps(report, indent=2), encoding='utf-8')
    print(json.dumps(dict(verdict=report['verdict'], checks=report['checks'], wall_s=report['wall_s'])))
    return 0 if result.passed else 2


if __name__ == '__main__':
    raise SystemExit(main())
