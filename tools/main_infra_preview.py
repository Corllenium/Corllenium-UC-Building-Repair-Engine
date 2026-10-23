"""Package qualified source/candidate previews without creating an accepted model."""
import argparse
import json
import os
from pathlib import Path
import re
import uuid
from urllib.parse import quote

from engine.io.minecraft_floor import parse_floor
from engine.io.snapshot import copy_verified, sha256_file


def package_preview(*, baseline, qualification, public, revision, run_id, floor, kind='source', candidate=None):
    if kind not in ('source', 'candidate'):
        raise ValueError('Accepted adoption requires the existing independently validated owner-review workflow')
    if not re.fullmatch('[a-f0-9]{64}', revision) or not re.fullmatch('[A-Za-z0-9_-]+', run_id) or floor not in [f'{i}F' for i in range(1, 8)]:
        raise ValueError('Invalid preview identity')
    baseline, qualification, public = Path(baseline), Path(qualification), Path(public)
    if os.name == 'nt' and not str(public).startswith('\\\\?\\'):
        public = Path('\\\\?\\' + str(public.resolve()))
    proof = json.loads(qualification.read_text(encoding='utf-8'))
    if proof.get('floor_id') != floor or proof.get('source_revision') != revision:
        raise ValueError('Qualification identity does not match preview floor/source')
    provenance = json.loads((baseline / 'geometry-provenance.json').read_text(encoding='utf-8'))
    for key, filename in [('source_triangles_sha256', 'before.source.obj'), ('engine_obj_sha256', 'before.engine.obj')]:
        if not proof.get('qualified') or proof.get(key) != sha256_file(baseline / filename):
            raise ValueError('Source qualification hash mismatch')
    source = baseline / 'before.source.obj'
    asset_root = baseline
    if kind == 'candidate':
        if candidate is None:
            raise ValueError('Candidate path is missing')
        asset_root = Path(candidate)
        audit = json.loads((asset_root / 'stage-audit.json').read_text(encoding='utf-8'))
        if audit.get('qualification_sha256') != sha256_file(qualification):
            raise ValueError('Candidate qualification hash mismatch')
        source = asset_root / 'candidate.source.obj'
        if not audit.get('guard', {}).get('passed') or audit.get('source_candidate_sha256') != sha256_file(source):
            raise ValueError('Candidate guard/hash proof mismatch')
        contract = audit.get('cleanup_mode', 'exact_duplicates')
        if contract == 'e3_remove_only':
            from engine.io.obj_reader import read_obj
            from tools.main_infra_e3_binding import bind_saved_e3
            engine_candidate = asset_root / 'candidate.engine.obj'
            if audit.get('engine_candidate_sha256') != sha256_file(engine_candidate):
                raise ValueError('Candidate engine hash mismatch')
            bind_saved_e3(candidate=asset_root, audit=audit,
                before_engine=read_obj(baseline / 'before.engine.obj'), after_engine=read_obj(engine_candidate),
                before_source=read_obj(baseline / 'before.source.obj'), after_source=read_obj(source))
        elif contract != 'exact_duplicates' or not audit.get('source_coverage', {}).get('exact_coverage'):
            raise ValueError('Candidate coverage contract mismatch')
    mesh = parse_floor(source.read_text(encoding='utf-8')).mesh
    if not mesh.mtllib:
        raise ValueError('Preview material library missing')
    files = {'model.obj': source}
    for asset in provenance['assets']:
        relative = asset['path'].replace('\\', '/')
        path = (asset_root / relative).resolve()
        if not path.is_relative_to(asset_root.resolve()) or sha256_file(path) != asset['sha256']:
            raise ValueError('Preview asset hash mismatch')
        files[relative] = path
    if mesh.mtllib.replace('\\', '/') not in files:
        raise ValueError('Material library absent from preview assets')
    base = f'/models/main-infra/{revision}/{floor}/{run_id}/{kind}/'
    manifest = {'schema_version': 1, 'building_id': 'MAIN_INFRA', 'source_revision': revision,
        'run_id': run_id, 'floor': floor, 'floor_id': f'MAIN_INFRA_{floor}', 'kind': kind,
        'display_frame': {'up_axis': 'Y', 'units': 'metres', 'source_local': True},
        'bounds': provenance['source_bounds'], 'obj_url': base + 'model.obj',
        'mtl_url': base + quote(mesh.mtllib.replace('\\', '/'), safe='/'),
        'assets': [{'url': base + quote(name, safe='/'), 'sha256': sha256_file(path)} for name, path in sorted(files.items())]}
    destination = public / 'models/main-infra' / revision / floor / run_id / kind
    if destination.exists():
        saved = destination / 'preview.json'
        if not saved.is_file() or json.loads(saved.read_text(encoding='utf-8')) != manifest:
            raise ValueError('Immutable preview identity already has different content')
        for name, source_path in files.items():
            if not (destination / name).is_file() or sha256_file(destination / name) != sha256_file(source_path):
                raise ValueError('Immutable preview asset hash changed')
    else:
        destination.parent.mkdir(parents=True, exist_ok=True)
        incoming = destination.parent / f'.{kind}-incoming-{uuid.uuid4().hex}'
        incoming.mkdir()
        for name, source_path in files.items():
            target = incoming / name
            target.parent.mkdir(parents=True, exist_ok=True)
            copy_verified(source_path, target, interval_s=0)
        (incoming / 'preview.json').write_text(json.dumps(manifest, indent=2), encoding='utf-8')
        os.rename(incoming, destination)
    return {'manifest_path': destination / 'preview.json', 'manifest_url': base + 'preview.json', 'base_url': base}


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    for name in ['baseline', 'qualification', 'public']:
        parser.add_argument(f'--{name}', type=Path, required=True)
    for name in ['revision', 'run-id', 'floor']:
        parser.add_argument(f'--{name}', required=True)
    parser.add_argument('--kind', choices=['source', 'candidate'], default='source')
    parser.add_argument('--candidate', type=Path)
    parser.add_argument('--progress', type=Path)
    parser.add_argument('--publish-status', type=Path)
    args = vars(parser.parse_args())
    progress, publish = args.pop('progress'), args.pop('publish_status')
    result = package_preview(**args)
    if progress:
        from tools.main_infra_progress import load_progress, update_floor
        doc = load_progress(progress)
        if doc['source_revision'] != args['revision'] or doc['run_id'] != args['run_id']:
            raise ValueError('Published preview does not belong to active run')
        row = doc['floors'][args['floor']]
        state = 'queued' if row['state'] == 'importing' else row['state']
        step = 'Import independently qualified; pilot cleanup pending' if row['state'] == 'importing' else row['step']
        update_floor(progress, args['floor'], state, step, blocker=row['blocker'], published_path=publish,
                     **{f'{args["kind"]}_preview': result['manifest_url']})
    print(json.dumps({key: str(value) for key, value in result.items()}))
