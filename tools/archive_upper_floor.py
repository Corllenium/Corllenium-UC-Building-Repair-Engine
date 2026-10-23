"""Archive one fresh MAIN INFRA floor candidate into repo 04 and copy it into repo 03, with hashes.

Owner decisions 2026-10-23: a candidate that passed invariants, the strict 26-view guard, textures and
visible coverage is archived in 04 and copied into 03 as a labelled *candidate* even when the signed
flicker/crack targets still fail; the measured numbers travel with it. Nothing here is acceptance.

04 layout:  <04>/03_REPAIR_RECORDS/MAIN_INFRA_MINECRAFT_20261023/upper-floors/<F>/{SOURCE_REPAIR_RECORD.json, evidence/*}
            <04>/Exports/Repaired-Buildings-20261023-fresh/ByBuilding/Main-Infrastructure/Model-Floor_0N/{*.fixed.obj,
            *.fixed.source.obj, <mtl>, textures/, report.json}  plus a MANIFEST.json at the export root.
03 layout:  <03>/Assets/Models/Campus/Repaired/Main-Infrastructure/Floor/Model-Floor_0N/{*.fixed.obj (source frame,
            metres, Y-up), <mtl>, textures/}.  The `/Floor/` segment makes CampusModelImporter keep scale 1.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import shutil
from datetime import datetime, timezone
from pathlib import Path

ORDINAL = {'1F': '1st', '2F': '2nd', '3F': '3rd', '4F': '4th', '5F': '5th', '6F': '6th', '7F': '7th'}


def sha256_file(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def _copy(src, dst):
    dst = Path(dst)
    dst.parent.mkdir(parents=True, exist_ok=True)
    shutil.copyfile(src, dst)
    if sha256_file(src) != sha256_file(dst):
        raise ValueError(f'Copy verification failed: {dst}')
    return sha256_file(dst)


def _copy_tree(src, dst):
    out = {}
    for path in sorted(Path(src).rglob('*')):
        if path.is_file():
            rel = path.relative_to(src).as_posix()
            out[rel] = _copy(path, Path(dst) / rel)
    return out


def _mtl_of(obj_path):
    for line in Path(obj_path).read_text(encoding='utf-8').splitlines():
        if line.startswith('mtllib '):
            return line[7:].strip()
    raise ValueError(f'{obj_path} names no mtllib')


def summarize_validation(validation):
    checks = validation['checks']
    kinds = {k: dict(before=row.get('before'), after=row.get('after'), target=row.get('target'), status=row.get('status'))
             for k, row in checks['problems']['kinds'].items()}
    return dict(verdict=validation['verdict'], textures=checks['textures']['status'], nothing_deleted=checks['nothing_deleted']['status'],
                problems=checks['problems']['status'], signed=checks['problems'].get('signed'), kinds=kinds)


def archive_floor(*, root, floor, candidate, validation_dir, repo04, repo03, job_id, run_id, guard_receipt=None,
                  interior_gate=None, cleanup_mode='exact_duplicates_only', now=None):
    root, candidate, validation_dir = Path(root), Path(candidate), Path(validation_dir)
    repo04, repo03 = Path(repo04), Path(repo03)
    stamp = now or datetime.now(timezone.utc).isoformat().replace('+00:00', 'Z')
    audit = json.loads((candidate / 'stage-audit.json').read_text(encoding='utf-8'))
    if not audit.get('guard', {}).get('passed'):
        raise ValueError('Candidate guard has not passed; nothing is archived')
    validation = json.loads((validation_dir / 'validation.json').read_text(encoding='utf-8'))
    if validation['inputs']['after_sha256'] != audit['engine_candidate_sha256']:
        raise ValueError('validation.json belongs to another candidate')
    summary = summarize_validation(validation)
    if summary['textures'] != 'PASS' or summary['nothing_deleted'] != 'PASS':
        raise ValueError('Textures or visible coverage did not pass; nothing is archived')
    manifest = json.loads((root / 'raw-manifest.json').read_text(encoding='utf-8'))
    qualification = json.loads((root / 'independent-validator' / 'import-audit' / f'qualification-{floor}.json').read_text(encoding='utf-8'))
    n = floor[0]
    stem = f'Main_Infrustructure_{ORDINAL[floor]}_floor'
    mtl_name = _mtl_of(candidate / 'candidate.source.obj')

    # ---- repo 04: records + export
    record_dir = repo04 / '03_REPAIR_RECORDS' / 'MAIN_INFRA_MINECRAFT_20261023' / 'upper-floors' / floor
    evidence = {}
    for name in ['stage-audit.json', 'edit-log.jsonl', 'source-faces.json']:
        if (candidate / name).exists():
            evidence[name] = _copy(candidate / name, record_dir / 'evidence' / name)
    for name in ['validation.json', 'physical-precision-inputs.json']:
        if (validation_dir / name).exists():
            evidence[name] = _copy(validation_dir / name, record_dir / 'evidence' / name)
    for label, src in [('independent-guard.json', guard_receipt), ('camera-qualification.json', interior_gate and Path(interior_gate) / 'camera-qualification.json'),
                       ('interior-gate-comparison.json', interior_gate and Path(interior_gate) / 'renders' / 'comparison.json')]:
        if src and Path(src).exists():
            evidence[label] = _copy(src, record_dir / 'evidence' / label)
    for png in ['paired-detail.png', 'all-views.png']:
        src = root / 'candidate-qa' / floor / png
        if src.exists():
            evidence['candidate-' + png] = _copy(src, record_dir / 'evidence' / ('candidate-' + png))
    export_root = repo04 / 'Exports' / 'Repaired-Buildings-20261023-fresh'
    export_dir = export_root / 'ByBuilding' / 'Main-Infrastructure' / f'Model-Floor_0{n}'
    files = {}
    files[f'{stem}.fixed.obj'] = _copy(candidate / 'candidate.engine.obj', export_dir / f'{stem}.fixed.obj')
    files[f'{stem}.fixed.source.obj'] = _copy(candidate / 'candidate.source.obj', export_dir / f'{stem}.fixed.source.obj')
    files[mtl_name] = _copy(candidate / mtl_name, export_dir / mtl_name)
    for rel, digest in _copy_tree(candidate / 'textures', export_dir / 'textures').items():
        files['textures/' + rel] = digest
    report = dict(schema_version=1, job_id=job_id, run_id=run_id, floor_id=f'MAIN_INFRA_{floor}', source_revision=manifest['source_revision'],
                  source_file=f'{ORDINAL[floor]} floor main infra.obj', cleanup_mode=cleanup_mode, status='candidate_not_accepted',
                  input_triangles=audit['input_triangles'], output_triangles=audit['output_triangles'],
                  removed_triangles=audit['input_triangles'] - audit['output_triangles'],
                  guard=dict(passed=True, views=26, totals=audit['guard'].get('totals')), validator=summary,
                  frames=dict(fixed_obj='engine frame (x, -z, y) in inches; CampusModelImporter default scale 0.0254 restores metres',
                              fixed_source_obj='source frame, metres, Minecraft Y-up, identical to the original export frame'),
                  engine_candidate_sha256=audit['engine_candidate_sha256'], source_candidate_sha256=audit['source_candidate_sha256'],
                  qualification_sha256=audit['qualification_sha256'], archived_utc=stamp)
    (export_dir / 'report.json').write_text(json.dumps(report, indent=2) + '\n', encoding='utf-8')
    files['report.json'] = sha256_file(export_dir / 'report.json')
    manifest_path = export_root / 'MANIFEST.json'
    export_manifest = json.loads(manifest_path.read_text(encoding='utf-8')) if manifest_path.exists() else {'schema_version': 1, 'floors': {}}
    export_manifest['floors'][floor] = dict(path=export_dir.relative_to(export_root).as_posix(), files=files, archived_utc=stamp,
                                            run_id=run_id, cleanup_mode=cleanup_mode)
    manifest_path.write_text(json.dumps(export_manifest, indent=2) + '\n', encoding='utf-8')
    record = dict(schema_version=1, job_id=job_id, run_id=run_id, floor_id=f'MAIN_INFRA_{floor}', source_revision=manifest['source_revision'],
                  source_obj_sha256=qualification['source_obj_sha256'], qualification=qualification, cleanup_mode=cleanup_mode,
                  candidate=dict(path=str(candidate), engine_candidate_sha256=audit['engine_candidate_sha256'],
                                 source_candidate_sha256=audit['source_candidate_sha256'], input_triangles=audit['input_triangles'],
                                 output_triangles=audit['output_triangles']),
                  guard=audit['guard'], validator=summary, interior_gate=None, evidence=evidence,
                  export=dict(path=export_dir.relative_to(repo04).as_posix(), files=files), acceptance='open', archived_utc=stamp)
    if interior_gate and (Path(interior_gate) / 'renders' / 'comparison.json').exists():
        gate = json.loads((Path(interior_gate) / 'renders' / 'comparison.json').read_text(encoding='utf-8'))
        record['interior_gate'] = dict(pairs=len(gate['views']), different_pixels=sum(v['different_pixels'] for v in gate['views']),
                                       all_pixels_identical=gate['all_pixels_identical'])
    record_dir.mkdir(parents=True, exist_ok=True)
    (record_dir / 'SOURCE_REPAIR_RECORD.json').write_text(json.dumps(record, indent=2) + '\n', encoding='utf-8')

    # ---- repo 03: consumer copy, source frame under /Floor/ (scale 1)
    game_dir = repo03 / 'Assets' / 'Models' / 'Campus' / 'Repaired' / 'Main-Infrastructure' / 'Floor' / f'Model-Floor_0{n}'
    game = {}
    game[f'{stem}.fixed.obj'] = _copy(candidate / 'candidate.source.obj', game_dir / f'{stem}.fixed.obj')
    game[mtl_name] = _copy(candidate / mtl_name, game_dir / mtl_name)
    for rel, digest in _copy_tree(candidate / 'textures', game_dir / 'textures').items():
        game['textures/' + rel] = digest
    (game_dir / 'RECEIPT.json').write_text(json.dumps(dict(schema_version=1, job_id=job_id, run_id=run_id, floor_id=f'MAIN_INFRA_{floor}',
        source_revision=manifest['source_revision'], status='candidate_not_accepted', cleanup_mode=cleanup_mode,
        frame='source frame, metres, Y-up; path contains /Floor/ so CampusModelImporter applies scale 1',
        validator=summary, triangles=dict(input=audit['input_triangles'], output=audit['output_triangles']),
        archived_from_04=export_dir.relative_to(repo04).as_posix(), files=game, copied_utc=stamp), indent=2) + '\n', encoding='utf-8')
    return dict(record=str(record_dir / 'SOURCE_REPAIR_RECORD.json'), export=str(export_dir), game=str(game_dir),
                files_04=len(files), files_03=len(game) + 1, validator=summary['verdict'], removed=report['removed_triangles'])


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--root', type=Path, required=True)
    parser.add_argument('--floor', choices=list(ORDINAL), required=True)
    parser.add_argument('--candidate', type=Path, required=True)
    parser.add_argument('--validation-dir', type=Path, required=True)
    parser.add_argument('--repo04', type=Path, required=True)
    parser.add_argument('--repo03', type=Path, required=True)
    parser.add_argument('--job-id', required=True)
    parser.add_argument('--run-id', required=True)
    parser.add_argument('--guard-receipt', type=Path)
    parser.add_argument('--interior-gate', type=Path)
    parser.add_argument('--cleanup-mode', default='exact_duplicates_only')
    args = parser.parse_args(argv)
    result = archive_floor(root=args.root, floor=args.floor, candidate=args.candidate, validation_dir=args.validation_dir,
                           repo04=args.repo04, repo03=args.repo03, job_id=args.job_id, run_id=args.run_id,
                           guard_receipt=args.guard_receipt, interior_gate=args.interior_gate, cleanup_mode=args.cleanup_mode)
    print(json.dumps(result))
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
