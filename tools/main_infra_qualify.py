"""Independent import qualification for one fresh MAIN INFRA floor, derived only from saved artifacts.

Reproduces the reviewer-made ``qualification-<F>.json`` and ``materials-<F>.json`` of the 1F/4F pilots:
hashes bind the raw OBJ, the Blender reference, the normalized engine OBJ and the source triangles; the
render-pair audit re-reads the saved before/after PNGs and counts RGB and alpha changes separately;
material look keys come from ``engine.campus.materials.build_materials``. Nothing here moves geometry
or changes guards or targets. A refusal is recorded, never silently passed.
"""
from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path

import numpy as np

from engine.campus.materials import build_materials
from tools.main_infra_progress import FLOORS, utc_now
from tools.repair_fresh_main_infra import FILES

SCOPE = 'Independent import baseline qualification only; no candidate repair or floor acceptance verdict.'


def sha256_file(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def _png(path):
    from PIL import Image
    with Image.open(path) as image:
        return np.asarray(image.convert('RGBA'), dtype=np.int16)


def audit_render_pairs(out_dir):
    """Re-read every saved before/after PNG pair of a render-pair run and count changed pixels by channel."""
    out_dir = Path(out_dir)
    report = json.loads((out_dir / 'comparison.json').read_text(encoding='utf-8'))
    views = []
    for view in report['views']:
        before, after = _png(out_dir / f"{view['name']}.before.png"), _png(out_dir / f"{view['name']}.after.png")
        if before.shape != after.shape:
            raise ValueError(f"Render pair {view['name']} has different image sizes")
        delta = np.abs(before - after)
        any_pixels = int(np.any(delta > 0, axis=2).sum())
        rgb = int(np.any(delta[:, :, :3] > 0, axis=2).sum())
        alpha = int((delta[:, :, 3] > 0).sum())
        occupancy = int(((before[:, :, 3] > 0) != (after[:, :, 3] > 0)).sum())
        views.append({'name': view['name'], 'different_pixels': any_pixels, 'rgb_different_pixels': rgb,
                      'alpha_different_pixels': alpha, 'alpha_occupancy_different_pixels': occupancy,
                      'report_difference_matches': any_pixels == int(view['different_pixels'])})
    return {'pairs': len(views), 'different_pixels': sum(v['different_pixels'] for v in views),
            'rgb_different_pixels': sum(v['rgb_different_pixels'] for v in views),
            'alpha_different_pixels': sum(v['alpha_different_pixels'] for v in views),
            'alpha_occupancy_different_pixels': sum(v['alpha_occupancy_different_pixels'] for v in views),
            'all_report_counts_match': all(v['report_difference_matches'] for v in views),
            'before_sha256': report.get('before_sha256'), 'after_sha256': report.get('after_sha256'), 'views': views}


def build_qualification(*, floor, source_revision, raw, reference, baseline, source_qa, frame_qa, reviewer,
                        audit_ref='import-audit.json', now=None):
    """The qualification record for one floor; ``qualified`` is False with ``refusals`` when any gate fails."""
    if floor not in FLOORS:
        raise ValueError('Unknown fresh floor')
    raw, reference, baseline = Path(raw), Path(reference), Path(baseline)
    refusals = []
    reference_doc = json.loads(reference.read_text(encoding='utf-8'))
    raw_sha = sha256_file(raw)
    if reference_doc.get('schema_version') != 1 or reference_doc.get('source_sha256') != raw_sha:
        refusals.append('reference was built from a different raw OBJ')
    if reference_doc.get('unmatched_polygons') != 0 or not reference_doc.get('blender_version'):
        refusals.append(f"reference has {reference_doc.get('unmatched_polygons')} unmatched source polygons")
    provenance = json.loads((baseline / 'geometry-provenance.json').read_text(encoding='utf-8'))
    if provenance.get('source_corner_positions_changed', 1) != 0:
        refusals.append('normalization moved source corners')
    if provenance.get('triangle_count') != reference_doc.get('triangle_count'):
        refusals.append('normalized triangle count differs from the reference tessellation')
    if provenance.get('source_sha256') not in (None, raw_sha):
        refusals.append('normalized baseline was built from a different raw OBJ')
    source_audit = audit_render_pairs(source_qa)
    if source_audit['different_pixels'] != 0 or not source_audit['all_report_counts_match']:
        refusals.append(f"raw-versus-triangulated source renders differ in {source_audit['different_pixels']} pixels")
    frame_audit = audit_render_pairs(frame_qa)
    if frame_audit['alpha_different_pixels'] != 0 or frame_audit['alpha_occupancy_different_pixels'] != 0:
        refusals.append(f"engine-frame renders change silhouette or alpha in {frame_audit['alpha_different_pixels']} pixels")
    if not frame_audit['all_report_counts_match']:
        refusals.append('engine-frame render report counts do not match the saved PNG pairs')
    doc = {
        'schema_version': 1,
        'qualified': not refusals,
        'floor_id': floor,
        'source_revision': source_revision,
        'source_obj_sha256': raw_sha,
        'engine_obj_sha256': sha256_file(baseline / 'before.engine.obj'),
        'source_triangles_sha256': sha256_file(baseline / 'before.source.obj'),
        'native_reference_sha256': sha256_file(reference),
        'reviewer': reviewer,
        'reviewed_utc': now or utc_now(),
        'audit_ref': audit_ref,
        'scope': SCOPE,
        'frame_rgb_different_pixels': frame_audit['rgb_different_pixels'],
        'frame_alpha_different_pixels': frame_audit['alpha_different_pixels'],
        'guards_or_targets_modified': False,
    }
    if refusals:
        doc['refusals'] = refusals
    doc['_audit'] = {'source_renders': source_audit, 'frame_renders': frame_audit, 'provenance': provenance}
    audit = doc.pop('_audit')
    build_qualification.last_audit = audit
    return doc


build_qualification.last_audit = None


def _mtl_of(baseline):
    for line in (Path(baseline) / 'before.source.obj').read_text(encoding='utf-8').splitlines():
        if line.startswith('mtllib '):
            return Path(baseline) / line[7:].strip()
    raise ValueError('Normalized baseline names no mtllib')


def write_materials(baseline, out):
    """Material look keys for the Validator, from the normalized baseline's own MTL and textures."""
    doc = build_materials(_mtl_of(baseline), Path(baseline))
    if out is not None:
        Path(out).parent.mkdir(parents=True, exist_ok=True)
        Path(out).write_text(json.dumps(doc, indent=2) + '\n', encoding='utf-8')
    return doc


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--root', type=Path, required=True, help='run root holding raw/, reference/, normalized/')
    parser.add_argument('--floor', choices=list(FLOORS), required=True)
    parser.add_argument('--source-qa', type=Path, required=True, help='render-pair output: raw versus before.source.obj')
    parser.add_argument('--frame-qa', type=Path, required=True, help='render-pair output: raw versus before.engine.obj')
    parser.add_argument('--reviewer', required=True)
    parser.add_argument('--out-dir', type=Path, required=True)
    args = parser.parse_args(argv)
    manifest = json.loads((args.root / 'raw-manifest.json').read_text(encoding='utf-8'))
    out_dir = args.out_dir
    out_dir.mkdir(parents=True, exist_ok=True)
    qualification = out_dir / f'qualification-{args.floor}.json'
    if qualification.exists():
        raise SystemExit(f'Refusing to overwrite {qualification}')
    doc = build_qualification(floor=args.floor, source_revision=manifest['source_revision'],
                              raw=args.root / 'raw' / FILES[args.floor], reference=args.root / 'reference' / f'{args.floor}.json',
                              baseline=args.root / 'normalized' / args.floor, source_qa=args.source_qa, frame_qa=args.frame_qa,
                              reviewer=args.reviewer, audit_ref=f'import-audit-{args.floor}.json')
    audit = dict(build_qualification.last_audit)
    audit.update(floor_id=args.floor, source_revision=manifest['source_revision'], qualified=doc['qualified'],
                 refusals=doc.get('refusals', []), reviewer=args.reviewer, reviewed_utc=doc['reviewed_utc'])
    (out_dir / f'import-audit-{args.floor}.json').write_text(json.dumps(audit, indent=2) + '\n', encoding='utf-8')
    qualification.write_text(json.dumps(doc, indent=2) + '\n', encoding='utf-8')
    write_materials(args.root / 'normalized' / args.floor, out_dir.parent / 'preflight' / f'materials-{args.floor}.json')
    print(json.dumps({'floor': args.floor, 'qualified': doc['qualified'], 'refusals': doc.get('refusals', []),
                      'frame_rgb_different_pixels': doc['frame_rgb_different_pixels'],
                      'frame_alpha_different_pixels': doc['frame_alpha_different_pixels']}))
    return 0 if doc['qualified'] else 2


if __name__ == '__main__':
    raise SystemExit(main())
