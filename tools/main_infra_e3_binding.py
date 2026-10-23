"""Bind saved E3 removals to checked edits and exact original source survivors.

`bind_remove_only` is the proof itself, for any remove-only engine stage: the saved pair is the BEFORE minus exactly the
faces of the kept non-legacy `remove` edits of that engine's one checked, rollback-enabled stage, in both frames, with
`source-faces.json` and `edit-log.jsonl` hash-bound to the audit. `bind_saved_e3` is that proof for E3's contract
(`e3_remove_only`); `tools/main_infra_e5_binding.py` uses it for E5's. `chained_e3_before` proves the E3 candidate a
chained audit (`e3_candidate`) names, for the stages that run after E3 (E5, E4).
"""
import json
from dataclasses import replace
from pathlib import Path

from engine.io.obj_reader import read_obj
from engine.io.snapshot import sha256_file
from tools.main_infra_e3 import verify_survivor_mesh


def _hash(path, expected, engine='E3'):
    actual = sha256_file(path)
    if actual != expected:
        raise ValueError(f'{engine} proof hash mismatch: {path}')
    return actual


def _count(value, expected):
    return type(value) is int and value == expected


def bind_remove_only(*, engine, candidate, audit, before_engine, after_engine, before_source, after_source):
    """Prove the saved remove-only candidate of `engine` ("E3" or "E5") against its BEFORE pair; returns
    `{source_faces_sha256, edit_log_sha256, removed_triangles, source_faces}` (the survivors, as BEFORE face ids)."""
    candidate = Path(candidate)
    mapping_path, log_path = candidate / 'source-faces.json', candidate / 'edit-log.jsonl'
    mapping_hash = _hash(mapping_path, audit.get('source_faces_sha256'), engine)
    log_hash = _hash(log_path, audit.get('edit_log_sha256'), engine)
    mapping = json.loads(mapping_path.read_text(encoding='utf-8'))
    if (not isinstance(mapping, dict) or not _count(mapping.get('schema_version'), 1)
            or mapping.get('mode') != 'original_source_survivors'
            or not _count(mapping.get('input_triangles'), before_engine.n_faces)
            or before_source.n_faces != before_engine.n_faces
            or not _count(mapping.get('output_triangles'), after_engine.n_faces)
            or after_source.n_faces != after_engine.n_faces
            or not isinstance(mapping.get('source_faces'), list)):
        raise ValueError(f'{engine} source survivor mapping contract differs')
    indices = mapping['source_faces']
    verify_survivor_mesh(before_engine, after_engine, indices)
    verify_survivor_mesh(before_source, after_source, indices)

    records = [json.loads(line) for line in log_path.read_text(encoding='utf-8').splitlines() if line.strip()]
    if (not records or any(not isinstance(row, dict) for row in records)
            or set(records[-1]) != {'check'}
            or any('check' in row for row in records[:-1])):
        raise ValueError(f'{engine} edit log must end in its one site check')
    check = records[-1]['check']
    if (not isinstance(check, dict) or audit.get('checks') != [check]
            or check.get('stage') != engine or check.get('engine') != engine
            or check.get('legacy') is not False or check.get('rollback') is not True):
        raise ValueError(f'{engine} non-legacy rollback-enabled site check required')

    planned_faces, removed_faces, kept_sites, rolled_sites = set(), set(), set(), set()
    for row in records[:-1]:
        faces, removed = row.get('faces'), row.get('removed')
        if (row.get('stage') != engine or row.get('engine') != engine or row.get('kind') != 'remove'
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
            raise ValueError(f'{engine} log permits only disjoint original-face remove edits')
        planned_faces.update(faces)
        if row.get('rolled_back', False):
            rolled_sites.add(row['site'])
        else:
            kept_sites.add(row['site'])
            removed_faces.update(faces)
    if kept_sites & rolled_sites:
        raise ValueError(f'{engine} site cannot be partly kept and partly rolled back')
    if 'rolled_back' in check:
        rolled = check['rolled_back']
        if (not isinstance(rolled, list) or any(not isinstance(row, dict) for row in rolled)
                or {row.get('site') for row in rolled} != rolled_sites):
            raise ValueError(f'{engine} rollback check differs from the edit log')
    expected = [face for face in range(before_engine.n_faces) if face not in removed_faces]
    if indices != expected:
        raise ValueError(f'{engine} source survivor map differs from kept remove edits')
    runs = check.get('runs')
    if not isinstance(runs, list):
        raise ValueError(f'{engine} site check runs required')
    if removed_faces:
        if (check.get('final') != 'PASS' or check.get('stage_rolled_back') is not None
                or check.get('rounds_exhausted', False) is not False
                or not runs or not isinstance(runs[-1], dict)
                or runs[-1].get('status') != 'PASS' or not _count(runs[-1].get('failing'), 0)
                or not _count(runs[-1].get('unknown', 0), 0)):
            raise ValueError(f'{engine} removal requires its final confirmed PASS check')
    elif check.get('final') not in ('PASS', 'NOTHING KEPT'):
        raise ValueError(f'{engine} no-op check must confirm PASS or NOTHING KEPT')
    return dict(source_faces_sha256=mapping_hash, edit_log_sha256=log_hash, removed_triangles=len(removed_faces),
                source_faces=indices)


def bind_saved_e3(*, candidate, audit, before_engine, after_engine, before_source, after_source):
    if audit.get('cleanup_mode') != 'e3_remove_only' or audit.get('executed_stages') != ['E3']:
        raise ValueError('only the sole checked E3 cleanup contract is allowed')
    proof = bind_remove_only(engine='E3', candidate=candidate, audit=audit, before_engine=before_engine,
                             after_engine=after_engine, before_source=before_source, after_source=after_source)
    return dict(candidate_contract='e3_remove_only', source_faces_sha256=proof['source_faces_sha256'],
                edit_log_sha256=proof['edit_log_sha256'], e3_removed_triangles=proof['removed_triangles'])


def chained_e3_before(*, audit, before_engine, before_source):
    """The E3 candidate the audit chains through (`e3_candidate`: its dir and the hashes of its engine and source
    candidate, `source-faces.json` and `stage-audit.json`), proven against the baseline with `bind_saved_e3`:
    `(e3 engine mesh, e3 source mesh, E3 source face list, E3 contract)`."""
    binding = audit.get('e3_candidate')
    if not isinstance(binding, dict) or not binding.get('candidate'):
        raise ValueError('a chained audit needs the E3 candidate binding (e3_candidate)')
    e3_dir = Path(binding['candidate'])
    _hash(e3_dir / 'stage-audit.json', binding.get('stage_audit_sha256'))
    e3_audit = json.loads((e3_dir / 'stage-audit.json').read_text(encoding='utf-8'))
    for key, name in (('engine_candidate_sha256', 'candidate.engine.obj'),
                      ('source_candidate_sha256', 'candidate.source.obj'), ('source_faces_sha256', 'source-faces.json')):
        if e3_audit.get(key) != binding.get(key):
            raise ValueError(f'E3 candidate binding differs from its audit: {key}')
        _hash(e3_dir / name, binding.get(key))
    e3_engine = replace(read_obj(e3_dir / 'candidate.engine.obj'), physical_quanta=before_engine.physical_quanta)
    e3_source = read_obj(e3_dir / 'candidate.source.obj')
    contract = bind_saved_e3(candidate=e3_dir, audit=e3_audit, before_engine=before_engine, after_engine=e3_engine,
                             before_source=before_source, after_source=e3_source)
    faces = json.loads((e3_dir / 'source-faces.json').read_text(encoding='utf-8'))['source_faces']
    return e3_engine, e3_source, faces, contract
