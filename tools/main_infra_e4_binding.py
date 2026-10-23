"""Bind a saved E4 (coplanar merge) candidate to its checked edits and to the qualified baseline.

Modelled on `tools/main_infra_e3_binding.py`. The Validator's BEFORE stays the qualified baseline snapshot; the
candidate is proven to be that baseline, minus the faces a checked E3 removed (`e3_then_e4_merge`, chained through
the E3 candidate's own `source-faces.json` and `bind_saved_e3`), with every E4 region replaced exactly as
`region-map.json` says (`tools.main_infra_e4.verify_merged_mesh`, in both frames). The region map and the edit log
are hash-bound to the audit, the log must hold only non-legacy E4 cuts whose kept sites are the mapped regions, the
one site check must end PASS when anything was kept, and the audit must say the strict guard passed.
"""
import json
from dataclasses import replace
from pathlib import Path

from engine.io.minecraft_floor import Frame
from engine.io.obj_reader import read_obj
from engine.io.snapshot import sha256_file
from tools.main_infra_e3_binding import bind_saved_e3
from tools.main_infra_e4 import MODE, verify_merged_mesh

CLEANUP_MODES = {'e4_merge_only': ['E4'], 'e3_then_e4_merge': ['E3', 'E4']}
_ROTATION = Frame(1.0, 'the fixed source Y-up to engine Z-up rotation').rotation


def _hash(path, expected):
    actual = sha256_file(path)
    if actual != expected:
        raise ValueError(f'E4 proof hash mismatch: {path}')
    return actual


def _count(value, expected):
    return type(value) is int and value == expected


def _e3_before(*, audit, before_engine, before_source):
    """The E3 candidate the audit chains through, proven against the baseline: `(e3 engine mesh, e3 source mesh,
    E3 source face list, E3 contract)`."""
    binding = audit.get('e3_candidate')
    if not isinstance(binding, dict) or not binding.get('candidate'):
        raise ValueError('e3_then_e4_merge needs the E3 candidate binding in the audit')
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


def bind_saved_e4(*, candidate, audit, before_engine, after_engine, before_source, after_source,
                  require_guard: bool = True):
    """`require_guard` (the default, the Validator path) refuses an audit without `guard.passed`; the independent
    guard itself calls with `require_guard=False`, since it is what produces that verdict."""
    candidate = Path(candidate)
    mode = audit.get('cleanup_mode')
    if mode not in CLEANUP_MODES or audit.get('executed_stages') != CLEANUP_MODES[mode]:
        raise ValueError('only the checked E4 cleanup contracts are allowed')
    if require_guard and audit.get('guard', {}).get('passed') is not True:
        raise ValueError('E4 candidate strict guard required (guard.passed)')
    mapping_path, log_path = candidate / 'region-map.json', candidate / 'edit-log.jsonl'
    mapping_hash = _hash(mapping_path, audit.get('region_map_sha256'))
    log_hash = _hash(log_path, audit.get('edit_log_sha256'))
    mapping = json.loads(mapping_path.read_text(encoding='utf-8'))
    if before_source.n_faces != before_engine.n_faces or after_source.n_faces != after_engine.n_faces:
        raise ValueError('E4 pair triangle counts differ between frames')

    e3_contract, e3_faces = None, list(range(before_engine.n_faces))
    e4_before_engine, e4_before_source = before_engine, before_source
    if mode == 'e3_then_e4_merge':
        e4_before_engine, e4_before_source, e3_faces, e3_contract = _e3_before(
            audit=audit, before_engine=before_engine, before_source=before_source)
    if (not isinstance(mapping, dict) or not _count(mapping.get('schema_version'), 1) or mapping.get('mode') != MODE
            or not _count(mapping.get('input_triangles'), e4_before_engine.n_faces)
            or not _count(mapping.get('output_triangles'), after_engine.n_faces)
            or not isinstance(mapping.get('kept_source_faces'), list) or not isinstance(mapping.get('regions'), list)):
        raise ValueError('E4 region map contract differs')
    verify_merged_mesh(e4_before_engine, after_engine, mapping)
    verify_merged_mesh(e4_before_source, after_source, mapping, rotation=_ROTATION)

    records = [json.loads(line) for line in log_path.read_text(encoding='utf-8').splitlines() if line.strip()]
    if (not records or any(not isinstance(row, dict) for row in records)
            or set(records[-1]) != {'check'} or any('check' in row for row in records[:-1])):
        raise ValueError('E4 edit log must end in its one site check')
    check = records[-1]['check']
    if (not isinstance(check, dict) or audit.get('checks') != [check]
            or check.get('stage') != 'E4' or check.get('engine') != 'E4'
            or check.get('legacy') is not False or check.get('rollback') is not True):
        raise ValueError('E4 non-legacy rollback-enabled site check required')
    planned_faces, kept, rolled_sites = set(), {}, set()
    n_before = e4_before_engine.n_faces
    for row in records[:-1]:
        faces, removed, added = row.get('faces'), row.get('removed'), row.get('added')
        if (row.get('stage') != 'E4' or row.get('engine') != 'E4' or row.get('kind') != 'cut'
                or row.get('legacy', False) is not False
                or not isinstance(faces, list) or not faces
                or any(type(face) is not int or not 0 <= face < n_before for face in faces)
                or len(set(faces)) != len(faces) or planned_faces.intersection(faces)
                or not isinstance(removed, list) or len(removed) != len(faces)
                or not _count(row.get('n_removed'), len(faces))
                or not isinstance(added, list) or not added or not _count(row.get('n_added'), len(added))
                or not _count(row.get('n_new_points'), 0)
                or any(row.get(key) not in (None, []) for key in ('new_points',))
                or type(row.get('site')) is not int or type(row.get('rolled_back', False)) is not bool):
            raise ValueError('E4 log permits only disjoint non-legacy cut edits over existing points')
        planned_faces.update(faces)
        if row.get('rolled_back', False):
            rolled_sites.add(row['site'])
        else:
            if row['site'] in kept:
                raise ValueError('an E4 site is one cut')
            kept[row['site']] = (sorted(faces), len(added))
    if set(kept) & rolled_sites:
        raise ValueError('E4 site cannot be partly kept and partly rolled back')
    if 'rolled_back' in check:
        rolled = check['rolled_back']
        if (not isinstance(rolled, list) or any(not isinstance(row, dict) for row in rolled)
                or {row.get('site') for row in rolled} != rolled_sites):
            raise ValueError('E4 rollback check differs from the edit log')
    mapped = {int(r['site']): (sorted(int(f) for f in r['source_faces']), len(r['new_triangles']))
              for r in mapping['regions']}
    if mapped != kept:
        raise ValueError('E4 region map differs from the kept cut edits of the log')
    replaced = sorted(f for faces, _n in kept.values() for f in faces)
    expected_kept = [f for f in range(n_before) if f not in set(replaced)]
    if mapping['kept_source_faces'] != expected_kept:
        raise ValueError('E4 kept source faces differ from the kept cut edits')
    runs = check.get('runs')
    if not isinstance(runs, list):
        raise ValueError('E4 site check runs required')
    if kept:
        if (check.get('final') != 'PASS' or check.get('stage_rolled_back') is not None
                or check.get('rounds_exhausted', False) is not False
                or not runs or not isinstance(runs[-1], dict)
                or runs[-1].get('status') != 'PASS' or not _count(runs[-1].get('failing'), 0)
                or not _count(runs[-1].get('unknown', 0), 0)):
            raise ValueError('E4 merge requires its final confirmed PASS check')
    elif check.get('final') not in ('PASS', 'NOTHING KEPT'):
        raise ValueError('E4 no-op check must confirm PASS or NOTHING KEPT')

    # back to the baseline's face ids through the E3 survivor list (the identity without E3)
    to_baseline = lambda faces: [int(e3_faces[f]) for f in faces]
    return dict(candidate_contract=mode, region_map_sha256=mapping_hash, edit_log_sha256=log_hash,
                e3_contract=e3_contract,
                e3_removed_triangles=before_engine.n_faces - len(e3_faces),
                e4_merged_regions=len(kept), e4_replaced_triangles=len(replaced),
                e4_new_triangles=sum(n for _faces, n in kept.values()),
                baseline_kept_source_faces=to_baseline(mapping['kept_source_faces']),
                e4_region_source_faces=[to_baseline(r['source_faces']) for r in mapping['regions']])
