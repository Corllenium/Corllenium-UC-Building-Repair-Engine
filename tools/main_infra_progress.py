"""Versioned MAIN INFRA events and atomic publication into the existing dashboard feed."""
from __future__ import annotations

import argparse
import copy
from datetime import datetime, timezone
import json
import os
from pathlib import Path
import re
import tempfile
import threading

FLOORS = tuple(f'{n}F' for n in range(1, 8))
STATES = {'queued', 'importing', 'cleaning', 'validating', 'blocked', 'needs_review', 'accepted', 'failed', 'cancelled'}
_LOCK = threading.RLock()


def utc_now():
    return datetime.now(timezone.utc).isoformat().replace('+00:00', 'Z')


def _date(value):
    if not isinstance(value, str):
        raise ValueError('Missing progress timestamp')
    parsed = datetime.fromisoformat(value.replace('Z', '+00:00'))
    if parsed.tzinfo is None:
        raise ValueError('Progress timestamps must include a timezone')
    return parsed


def validate_progress(doc):
    if not isinstance(doc, dict) or type(doc.get('schema_version')) is not int or doc['schema_version'] != 1:
        raise ValueError('Unsupported progress schema')
    if doc.get('building_id') != 'MAIN_INFRA' or type(doc.get('scale_metres_per_block')) not in (int, float) or doc['scale_metres_per_block'] != 1:
        raise ValueError('Wrong building or block scale')
    revision = doc.get('source_revision')
    if revision is not None and (not isinstance(revision, str) or not re.fullmatch('[a-f0-9]{64}', revision)):
        raise ValueError('Source revision must be a manifest SHA-256')
    for key in ('run_id', 'source_label', 'source_state', 'state', 'step'):
        if not isinstance(doc.get(key), str) or not doc[key].strip():
            raise ValueError(f'Missing {key}')
    for key in ('updated_at', 'last_work_event_at'):
        _date(doc.get(key))
    if doc.get('heartbeat_at') is not None:
        _date(doc['heartbeat_at'])
    if not isinstance(doc.get('floors'), dict) or set(doc['floors']) != set(FLOORS):
        raise ValueError('All seven fresh floors are required')
    for floor_id in FLOORS:
        floor = doc['floors'][floor_id]
        if not isinstance(floor, dict) or floor.get('floor_id') != f'MAIN_INFRA_{floor_id}' or floor.get('state') not in STATES:
            raise ValueError(f'Invalid floor identity or state: {floor_id}')
        if not isinstance(floor.get('step'), str) or not floor['step'].strip():
            raise ValueError(f'Missing step: {floor_id}')
        if floor.get('blocker') is not None and not isinstance(floor['blocker'], str):
            raise ValueError('Invalid blocker')
        refs = [floor.get(key) for key in ('source_preview', 'candidate_preview', 'accepted_preview', 'validator_ref', 'owner_decision_ref')]
        if not isinstance(floor.get('evidence_refs'), list) or not all(isinstance(ref, str) and ref.strip() for ref in floor['evidence_refs']):
            raise ValueError('Evidence references must be a list')
        for ref in refs + floor['evidence_refs']:
            if ref is None:
                continue
            if not revision or not isinstance(ref, str) or not ref.startswith(f'/models/main-infra/{revision}/{floor_id}/{doc["run_id"]}/') or any(char in ref for char in ('..', '\\', '%', '?', '#')):
                raise ValueError('Asset reference does not belong to this frozen floor')
        for key in ('input_triangles', 'output_triangles'):
            if key in floor and (type(floor[key]) is not int or floor[key] < 0):
                raise ValueError('Invalid measured triangle count')
        if floor['state'] in ('needs_review', 'accepted'):
            proof = floor.get('validation_proof', {})
            if not isinstance(proof, dict):
                raise ValueError('Independent review proof must be an object')
            required = {'source_revision': revision, 'run_id': doc['run_id'], 'floor_id': floor['floor_id'],
                'candidate_preview': floor.get('candidate_preview'), 'validator_ref': floor.get('validator_ref'),
                'validator_passed': True, 'independent': True}
            hashes = ('before_sha256', 'engine_candidate_sha256', 'source_candidate_sha256', 'validation_sha256',
                      'independent_review_sha256', 'qualification_sha256')
            if (not revision or not floor.get('candidate_preview') or not floor.get('validator_ref')
                or any(proof.get(key) != value for key, value in required.items())
                or not all(isinstance(proof.get(key), str) and re.fullmatch('[a-f0-9]{64}', proof[key]) for key in hashes)
                or proof.get('independent_review_ref') not in floor['evidence_refs']):
                raise ValueError('Matching independent review proof is required before automatic After display')
        if floor['state'] == 'accepted':
            proof = floor.get('acceptance_proof', {})
            required = {'source_revision': revision, 'run_id': doc['run_id'], 'floor_id': floor['floor_id'],
                        'validator_passed': True, 'independent': True, 'owner_decision': 'accepted'}
            if not revision or not all(floor.get(key) for key in ('accepted_preview', 'validator_ref', 'owner_decision_ref')) or any(proof.get(key) != value for key, value in required.items()):
                raise ValueError('Acceptance requires matching independent validation and owner proof')
        elif floor.get('accepted_preview') is not None:
            raise ValueError('Unaccepted floor cannot expose an accepted model')
    return doc


def load_progress(path):
    return validate_progress(json.loads(Path(path).read_text(encoding='utf-8')))


def _atomic_json(path, doc):
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = None
    try:
        with tempfile.NamedTemporaryFile(mode='w', encoding='utf-8', dir=path.parent, prefix=path.name + '.', suffix='.tmp', delete=False) as stream:
            temporary = Path(stream.name)
            json.dump(doc, stream, indent=2, ensure_ascii=False)
            stream.write('\n')
            stream.flush()
            os.fsync(stream.fileno())
        os.replace(temporary, path)
    finally:
        if temporary is not None:
            temporary.unlink(missing_ok=True)


def write_progress(path, doc, *, published_path=None):
    with _LOCK:
        doc = validate_progress(copy.deepcopy(doc))
        path = Path(path)
        if path.exists():
            old = load_progress(path)
            same_run = old['run_id'] == doc['run_id']
            if not same_run and doc.get('replaces_run_id') != old['run_id']:
                raise ValueError('Another run requires explicit replacement')
            if _date(doc['updated_at']) < _date(old['updated_at']):
                raise ValueError('Older progress cannot replace a newer event')
            if same_run:
                if old['state'] == 'cancelled' and doc != old:
                    raise ValueError('Cancelled run cannot be resurrected')
                if old['source_revision'] is not None and doc['source_revision'] != old['source_revision']:
                    raise ValueError('Frozen source changed within a run')
                for floor in FLOORS:
                    if old['floors'][floor]['state'] == 'cancelled' and doc['floors'][floor]['state'] != 'cancelled':
                        raise ValueError('Cancelled floor cannot be resurrected')
        published = None
        if published_path is not None:
            target = Path(published_path)
            published = json.loads(target.read_text(encoding='utf-8')) if target.exists() else {}
            if not isinstance(published, dict):
                raise ValueError('Dashboard feed must be an object')
            published['freshMainInfra'] = doc
        _atomic_json(path, doc)
        if published is not None:
            _atomic_json(published_path, published)
        return doc


def heartbeat_progress(path, *, now=None, published_path=None):
    with _LOCK:
        doc = load_progress(path)
        doc['heartbeat_at'] = doc['updated_at'] = now or utc_now()
        return write_progress(path, doc, published_path=published_path)


def update_floor(path, floor_id, state, step, *, blocker=None, published_path=None, now=None, **measured):
    with _LOCK:
        doc = load_progress(path)
        if floor_id not in FLOORS:
            raise ValueError('Unknown fresh floor')
        stamp = now or utc_now()
        doc['updated_at'] = doc['last_work_event_at'] = doc['heartbeat_at'] = stamp
        doc['state'], doc['step'] = 'running', f'{floor_id}: {step}'
        doc['floors'][floor_id].update(state=state, step=step, blocker=blocker, last_work_event_at=stamp, **measured)
        return write_progress(path, doc, published_path=published_path)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--canonical', type=Path, required=True)
    parser.add_argument('--publish', type=Path, required=True)
    parser.add_argument('--initialize-run')
    parser.add_argument('--step')
    parser.add_argument('--heartbeat', action='store_true')
    args = parser.parse_args()
    if args.heartbeat:
        if args.step or args.initialize_run:
            parser.error('Heartbeat cannot create a work event')
        heartbeat_progress(args.canonical, published_path=args.publish)
        return
    doc = load_progress(args.canonical)
    if args.initialize_run:
        doc['replaces_run_id'], doc['run_id'] = doc['run_id'], args.initialize_run
        doc['implementation_started'] = True
        doc['state'] = 'implementing_status'
    if args.step:
        doc['step'] = args.step
    doc['updated_at'] = doc['last_work_event_at'] = utc_now()
    write_progress(args.canonical, doc, published_path=args.publish)
    print(f"Published {doc['building_id']} {doc['run_id']}: seven actual floor states")


if __name__ == '__main__':
    main()
