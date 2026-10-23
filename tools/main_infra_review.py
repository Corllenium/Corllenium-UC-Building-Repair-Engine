"""Expose a real independent floor verdict and evidence without granting owner acceptance."""
import argparse
import json
import os
from pathlib import Path
import re

from engine.io.snapshot import copy_verified, sha256_file
from tools.main_infra_progress import FLOORS as FLOOR_CHOICES, load_progress, update_floor, write_progress


def evidence_locations(root, revision, run_id, floor, validation_run=None):
    if validation_run is not None and not re.fullmatch(r'[a-z0-9]+(?:-[a-z0-9]+)*', validation_run):
        raise ValueError('validation evidence run must be a single lowercase slug')
    reports = Path(root) / 'independent-validator'
    base = f'/models/main-infra/{revision}/{floor}/{run_id}/evidence/'
    if validation_run is not None:
        reports /= validation_run
        base += validation_run + '/'
    return reports / floor, base


def bind_independent_review(*, validation, candidate, qualification, independent, source_revision,
                            run_id, floor, qualification_sha256, validation_sha256, expected_before_sha256):
    identity = {'source_revision': source_revision, 'floor_id': floor}
    if not qualification.get('qualified') or any(qualification.get(k) != v for k, v in identity.items()):
        raise ValueError('Qualification identity mismatch')
    if candidate.get('qualification_sha256') != qualification_sha256:
        raise ValueError('Candidate belongs to another qualification')
    if expected_before_sha256 != qualification.get('engine_obj_sha256') or validation['inputs']['before_sha256'] != expected_before_sha256:
        raise ValueError('Validation does not use the qualified BEFORE snapshot')
    if validation['inputs']['after_sha256'] != candidate['engine_candidate_sha256']:
        raise ValueError('Validation belongs to another candidate')
    required = dict(identity, job_id=run_id.upper(), verdict=validation['verdict'], validation_json_sha256=validation_sha256)
    readback = independent.get('post_validation_input_hashes', {})
    if (any(independent.get(k) != v for k, v in required.items()) or not independent.get('reviewer')
        or readback.get('before') != expected_before_sha256 or readback.get('after') != candidate['engine_candidate_sha256']
        or readback.get('matches_report') is not True):
        raise ValueError('Independent reviewer identity, verdict or hash does not match this run')


def review_state(validation, candidate):
    if validation['inputs']['after_sha256'] != candidate['engine_candidate_sha256']:
        raise ValueError('Validation belongs to another candidate')
    checks = validation['checks']
    if validation['verdict'] == 'PASS' and all(checks[key]['status'] == 'PASS' for key in ['textures', 'nothing_deleted', 'problems']) and checks['problems']['signed']:
        return 'needs_review', None
    counts = ', '.join(f'{key}={row["after"]}' for key, row in checks['problems']['kinds'].items()
                       if isinstance(row.get('target'), (int, float)) and row['after'] > row['target'])
    blocker = f'Independent validation {validation["verdict"]}: textures {checks["textures"]["status"]}; visible coverage {checks["nothing_deleted"]["status"]}; signed problem targets {checks["problems"]["status"]}'
    return 'blocked', blocker + (f'; remaining {counts}' if counts else '')


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--root', type=Path, required=True)
    parser.add_argument('--floor', choices=list(FLOOR_CHOICES), required=True)
    parser.add_argument('--public', type=Path, required=True)
    parser.add_argument('--progress', type=Path, required=True)
    parser.add_argument('--publish-status', type=Path, required=True)
    parser.add_argument('--validation-run', help='Immutable batch containing a source-precision rerun')
    args = parser.parse_args()
    doc = load_progress(args.progress)
    root, base = evidence_locations(args.root, doc['source_revision'], doc['run_id'], args.floor, args.validation_run)
    audit_path = args.root / 'candidates' / args.floor / 'stage-audit.json'
    audit = json.loads(audit_path.read_text(encoding='utf-8'))
    if sha256_file(Path(audit['engine_candidate'])) != audit['engine_candidate_sha256']:
        raise ValueError('Saved candidate changed after build')
    report = json.loads((root / 'validation.json').read_text(encoding='utf-8'))
    qualification_path = args.root / 'independent-validator' / 'import-audit' / f'qualification-{args.floor}.json'
    qualification = json.loads(qualification_path.read_text(encoding='utf-8'))
    independent_path = root / 'independent-review.json'
    independent = json.loads(independent_path.read_text(encoding='utf-8'))
    snapshots = list(Path(audit['before_snapshot']).glob('*.obj'))
    if len(snapshots) != 1 or Path(report['inputs']['before']).resolve() != snapshots[0].resolve():
        raise ValueError('Validation BEFORE path is not the candidate baseline snapshot')
    if sha256_file(Path(report['inputs']['before'])) != report['inputs']['before_sha256']:
        raise ValueError('Validation BEFORE snapshot changed')
    bind_independent_review(validation=report, candidate=audit, qualification=qualification, independent=independent,
        source_revision=doc['source_revision'], run_id=doc['run_id'], floor=args.floor,
        qualification_sha256=sha256_file(qualification_path), validation_sha256=sha256_file(root / 'validation.json'),
        expected_before_sha256=sha256_file(snapshots[0]))
    state, blocker = review_state(report, audit)
    destination = args.public.resolve() / base.lstrip('/')
    if os.name == 'nt':
        destination = Path('\\\\?\\' + str(destination))
    destination.mkdir(parents=True, exist_ok=True)
    files = {name: root / name for name in ['validation.json', 'independent-review.json', 'input-readback.json', 'invocation.json']}
    if args.validation_run is not None:
        precision = root / 'physical-precision-inputs.json'
        if json.loads(precision.read_text(encoding='utf-8')) != report.get('physical_precision'):
            raise ValueError('Physical precision receipt differs from validation report')
        files[precision.name] = precision
    files['stage-audit.json'] = audit_path
    files['candidate-paired-detail.png'] = args.root / 'candidate-qa' / args.floor / 'paired-detail.png'
    files['candidate-all-views.png'] = args.root / 'candidate-qa' / args.floor / 'all-views.png'
    for name, source in files.items():
        target = destination / name
        if target.exists() and sha256_file(target) != sha256_file(source):
            raise ValueError('Published immutable evidence changed')
        if not target.exists():
            copy_verified(source, target, interval_s=0)
    proof = dict(source_revision=doc['source_revision'], run_id=doc['run_id'], floor_id=f'MAIN_INFRA_{args.floor}',
        candidate_preview=doc['floors'][args.floor]['candidate_preview'], validator_ref=base + 'validation.json',
        independent_review_ref=base + 'independent-review.json', validator_passed=state == 'needs_review', independent=True,
        before_sha256=report['inputs']['before_sha256'], engine_candidate_sha256=audit['engine_candidate_sha256'],
        source_candidate_sha256=audit['source_candidate_sha256'], validation_sha256=sha256_file(root / 'validation.json'),
        independent_review_sha256=sha256_file(independent_path), qualification_sha256=sha256_file(qualification_path))
    update_floor(args.progress, args.floor, state, 'Independent floor validation complete; inspect evidence', blocker=blocker,
        validation_proof=proof,
        validator_ref=base + 'validation.json', evidence_refs=[base + name for name in ['independent-review.json', 'candidate-paired-detail.png', 'candidate-all-views.png']],
        published_path=args.publish_status)
    doc = load_progress(args.progress)
    doc.pop('candidate_count', None)
    doc.pop('accepted_floor_count', None)
    doc.update(dashboard_connection='isolated_preview', next_action='Resolve pilot residuals with measured guarded passes; remaining floors wait for both pilot gates',
               report='docs/superpowers/records/MAIN-INFRA-CLEAN-20261023.md')
    write_progress(args.progress, doc, published_path=args.publish_status)
    print(json.dumps({'floor': args.floor, 'state': state, 'blocker': blocker, 'validator_ref': base + 'validation.json'}))
