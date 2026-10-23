"""Publish a Claude floor's independent evidence to the dashboard and set its floor state from the Validator.

Mirrors what tools/main_infra_review.py does for Codex's floors, for the E3 candidate layout of Claude's run
root, without the shared ``freshMainInfra`` publish (the upper publisher loop carries ``current-upper.json``).
"""
from __future__ import annotations

import argparse
import json
import os
import shutil
from pathlib import Path

from engine.io.snapshot import sha256_file
from tools.main_infra_progress import load_progress, update_floor


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--root', type=Path, required=True)
    parser.add_argument('--floor', required=True)
    parser.add_argument('--candidate', type=Path, required=True)
    parser.add_argument('--validation', type=Path, required=True, help='validation.json')
    parser.add_argument('--guard-receipt', type=Path, required=True)
    parser.add_argument('--interior', type=Path, required=True, help='e3-interior/<F> dir with renders/ and camera-qualification.json')
    parser.add_argument('--native-qa', type=Path, required=True, help='render dir holding paired-detail.png and all-views.png')
    parser.add_argument('--public', type=Path, action='append', required=True)
    parser.add_argument('--progress', type=Path, required=True)
    parser.add_argument('--before-counts', default='', help='text appended to the blocker, e.g. the pre-E3 counts')
    args = parser.parse_args(argv)
    doc = load_progress(args.progress)
    F = args.floor
    base = f"/models/main-infra/{doc['source_revision']}/{F}/{doc['run_id']}/evidence/"
    renders = args.interior / 'renders'
    gate = json.loads((renders / 'comparison.json').read_text(encoding='utf-8'))
    worst = sorted(gate['views'], key=lambda v: -v['different_pixels'])[0]
    files = {'validation.json': args.validation, 'independent-guard.json': args.guard_receipt,
             'interior-gate-comparison.json': renders / 'comparison.json',
             'camera-qualification.json': args.interior / 'camera-qualification.json',
             'stage-audit.json': args.candidate / 'stage-audit.json',
             'candidate-paired-detail.png': args.native_qa / 'paired-detail.png',
             'candidate-all-views.png': args.native_qa / 'all-views.png'}
    if worst['different_pixels']:
        files[f"interior-{worst['name']}.diff.png"] = renders / f"{worst['name']}.diff.png"
    for public in args.public:
        dest = public.resolve() / base.lstrip('/')
        if os.name == 'nt':
            dest = Path('\\\\?\\' + str(dest))  # long dashboard paths exceed MAX_PATH
        dest.mkdir(parents=True, exist_ok=True)
        for name, src in files.items():
            target = dest / name
            if target.exists() and sha256_file(target) != sha256_file(src):
                raise ValueError('Published immutable evidence changed: ' + name)
            if not target.exists():
                shutil.copyfile(src, target)
    validation = json.loads(args.validation.read_text(encoding='utf-8'))
    audit = json.loads((args.candidate / 'stage-audit.json').read_text(encoding='utf-8'))
    checks = validation['checks']
    kinds = checks['problems']['kinds']
    counts = ', '.join(f"{key}={row['after']}" for key, row in kinds.items()
                       if isinstance(row.get('target'), (int, float)) and row['after'] > row['target'])
    total = sum(v['different_pixels'] for v in gate['views'])
    passed = validation['verdict'] == 'PASS' and checks['problems'].get('signed')
    state = 'needs_review' if passed else 'blocked'
    blocker = None if passed else (
        f"Independent validation {validation['verdict']}: textures {checks['textures']['status']}; visible coverage "
        f"{checks['nothing_deleted']['status']}; signed problem targets {checks['problems']['status']}; remaining {counts}"
        + (f" ({args.before_counts})" if args.before_counts else '')
        + f". Strict-26 guard PASS; {len(gate['views'])} walking-height interior pairs: {total} changed px, no holes.")
    refs = [base + n for n in files if n != 'validation.json' and n != 'stage-audit.json' and n != 'camera-qualification.json']
    update_floor(args.progress, F, state, 'Independent floor validation complete; inspect evidence', blocker=blocker,
                 validator_ref=base + 'validation.json', evidence_refs=refs,
                 input_triangles=audit['input_triangles'], output_triangles=audit['output_triangles'])
    print(json.dumps(dict(floor=F, state=state, validator_ref=base + 'validation.json', interior_changed_px=total, remaining=counts)))
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
