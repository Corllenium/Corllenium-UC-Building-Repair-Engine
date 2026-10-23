"""Bind saved E3 removals to checked edits and exact original source survivors."""
import json
from pathlib import Path

from engine.io.snapshot import sha256_file
from tools.main_infra_e3 import verify_survivor_mesh


def _hash(path, expected):
    actual = sha256_file(path)
    if actual != expected:
        raise ValueError(f'E3 proof hash mismatch: {path}')
    return actual


def _count(value, expected):
    return type(value) is int and value == expected


def bind_saved_e3(*, candidate, audit, before_engine, after_engine, before_source, after_source):
    candidate = Path(candidate)
    if audit.get('cleanup_mode') != 'e3_remove_only' or audit.get('executed_stages') != ['E3']:
        raise ValueError('only the sole checked E3 cleanup contract is allowed')
    mapping_path, log_path = candidate / 'source-faces.json', candidate / 'edit-log.jsonl'
    mapping_hash = _hash(mapping_path, audit.get('source_faces_sha256'))
    log_hash = _hash(log_path, audit.get('edit_log_sha256'))
    mapping = json.loads(mapping_path.read_text(encoding='utf-8'))
    if (not isinstance(mapping, dict) or not _count(mapping.get('schema_version'), 1)
            or mapping.get('mode') != 'original_source_survivors'
            or not _count(mapping.get('input_triangles'), before_engine.n_faces)
            or before_source.n_faces != before_engine.n_faces
            or not _count(mapping.get('output_triangles'), after_engine.n_faces)
            or after_source.n_faces != after_engine.n_faces
            or not isinstance(mapping.get('source_faces'), list)):
        raise ValueError('E3 source survivor mapping contract differs')
    indices = mapping['source_faces']
    verify_survivor_mesh(before_engine, after_engine, indices)
    verify_survivor_mesh(before_source, after_source, indices)

    records = [json.loads(line) for line in log_path.read_text(encoding='utf-8').splitlines() if line.strip()]
    if (not records or any(not isinstance(row, dict) for row in records)
            or set(records[-1]) != {'check'}
            or any('check' in row for row in records[:-1])):
        raise ValueError('E3 edit log must end in its one site check')
    check = records[-1]['check']
    if (not isinstance(check, dict) or audit.get('checks') != [check]
            or check.get('stage') != 'E3' or check.get('engine') != 'E3'
            or check.get('legacy') is not False or check.get('rollback') is not True):
        raise ValueError('E3 non-legacy rollback-enabled site check required')

    planned_faces, removed_faces, kept_sites, rolled_sites = set(), set(), set(), set()
    for row in records[:-1]:
        faces, removed = row.get('faces'), row.get('removed')
        if (row.get('stage') != 'E3' or row.get('engine') != 'E3' or row.get('kind') != 'remove'
                or row.get('legacy', False) is not False
                or not isinstance(faces, list) or not faces
                or any(type(face) is not int or not 0 <= face < before_engine.n_faces for face in faces)
                or len(set(faces)) != len(faces) or planned_faces.intersection(faces)
                or not isinstance(removed, list) or len(removed) != len(faces)
                or not _count(row.get('n_removed'), len(faces))
                or row.get('added') != [] or not _count(row.get('n_added'), 0)
                or not _count(row.get('n_new_points'), 0)
                or any(row.get(key) not in (None, []) for key in
                       ('new_points', 'new_faces', 'new_face_uv', 'new_face_normal'))
                or type(row.get('site')) is not int
                or type(row.get('rolled_back', False)) is not bool):
            raise ValueError('E3 log permits only disjoint original-face remove edits')
        planned_faces.update(faces)
        if row.get('rolled_back', False):
            rolled_sites.add(row['site'])
        else:
            kept_sites.add(row['site'])
            removed_faces.update(faces)
    if kept_sites & rolled_sites:
        raise ValueError('E3 site cannot be partly kept and partly rolled back')
    if 'rolled_back' in check:
        rolled = check['rolled_back']
        if (not isinstance(rolled, list) or any(not isinstance(row, dict) for row in rolled)
                or {row.get('site') for row in rolled} != rolled_sites):
            raise ValueError('E3 rollback check differs from the edit log')
    expected = [face for face in range(before_engine.n_faces) if face not in removed_faces]
    if indices != expected:
        raise ValueError('E3 source survivor map differs from kept remove edits')
    runs = check.get('runs')
    if not isinstance(runs, list):
        raise ValueError('E3 site check runs required')
    if removed_faces:
        if (check.get('final') != 'PASS' or check.get('stage_rolled_back') is not None
                or check.get('rounds_exhausted', False) is not False
                or not runs or not isinstance(runs[-1], dict)
                or runs[-1].get('status') != 'PASS' or not _count(runs[-1].get('failing'), 0)
                or not _count(runs[-1].get('unknown', 0), 0)):
            raise ValueError('E3 removal requires its final confirmed PASS check')
    elif check.get('final') not in ('PASS', 'NOTHING KEPT'):
        raise ValueError('E3 no-op check must confirm PASS or NOTHING KEPT')
    return dict(candidate_contract='e3_remove_only', source_faces_sha256=mapping_hash,
                edit_log_sha256=log_hash, e3_removed_triangles=len(removed_faces))
