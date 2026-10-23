"""Replay a hash-bound subset of original E3 edits through fresh default site checks."""
from dataclasses import replace
import json
from pathlib import Path

import numpy as np

from engine.fixes.pipeline import FixProfile
from engine.io.obj_reader import read_obj
from engine.io.snapshot import sha256_file
from engine.repair.kernel import edit_keys, repair_unit
from engine.repair.types import Edit, RepairContext, UnitState
from engine.site_judge import SiteJudge
from tools.main_infra_e3 import _source_digest, source_survivors, verify_survivor_mesh


def _hash(path, expected):
    actual = sha256_file(path)
    if actual != expected:
        raise ValueError(f'original E3 artifact hash mismatch: {path}')
    return actual


def _original_edit(row, count):
    faces = row.get('faces')
    if (row.get('stage') != 'E3' or row.get('engine') != 'E3' or row.get('kind') != 'remove'
            or row.get('legacy', False) is not False or not isinstance(faces, list) or not faces
            or any(type(face) is not int or not 0 <= face < count for face in faces)
            or len(set(faces)) != len(faces) or row.get('n_removed') != len(faces)
            or not isinstance(row.get('removed'), list) or len(row['removed']) != len(faces)
            or row.get('added') != [] or row.get('n_added') != 0 or row.get('n_new_points') != 0
            or row.get('material') is not None or type(row.get('site')) is not int
            or not isinstance(row.get('reason'), str)
            or type(row.get('rolled_back', False)) is not bool
            or any(row.get(key) not in (None, []) for key in
                   ('new_points', 'new_faces', 'new_face_uv', 'new_face_normal'))):
        raise ValueError('original E3 log must contain original-face remove edits only')
    return Edit('E3', 'remove', tuple(faces), None, None, row['site'], row['reason'], {})


def load_replay_plan(before, looks, original_candidate, *, expected_audit_sha256, restore_sites=(0, 2, 9)):
    candidate = Path(original_candidate)
    audit_hash = _hash(candidate / 'stage-audit.json', expected_audit_sha256)
    audit = json.loads((candidate / 'stage-audit.json').read_text(encoding='utf-8'))
    if audit.get('cleanup_mode') != 'e3_remove_only' or audit.get('executed_stages') != ['E3']:
        raise ValueError('original sole E3 cleanup contract required')
    receipt = audit['input_receipt']
    before_paths = list(Path(audit['before_snapshot']).glob('*.obj'))
    if len(before_paths) != 1:
        raise ValueError('original BEFORE snapshot must contain one OBJ')
    before_hash = _hash(before_paths[0], receipt.get('before_sha256'))
    if before_hash != receipt.get('engine_obj_sha256'):
        raise ValueError('original BEFORE qualification hash differs')
    quanta = receipt.get('physical_axis_quanta_inches')
    if (not isinstance(quanta, list) or len(quanta) != 3
            or not np.isfinite(quanta).all() or min(quanta) <= 0):
        raise ValueError('original BEFORE source precision required')
    expected = replace(read_obj(before_paths[0]), physical_quanta=tuple(quanta))
    if _source_digest(before) != _source_digest(expected):
        raise ValueError('incoming BEFORE differs from original source and precision')
    map_hash = _hash(candidate / 'source-faces.json', audit.get('source_faces_sha256'))
    log_hash = _hash(candidate / 'edit-log.jsonl', audit.get('edit_log_sha256'))
    _hash(candidate / 'candidate.engine.obj', audit.get('engine_candidate_sha256'))
    _hash(candidate / 'candidate.source.obj', audit.get('source_candidate_sha256'))
    mapping = json.loads((candidate / 'source-faces.json').read_text(encoding='utf-8'))
    saved = read_obj(candidate / 'candidate.engine.obj')
    if (mapping.get('schema_version') != 1 or mapping.get('mode') != 'original_source_survivors'
            or mapping.get('input_triangles') != before.n_faces
            or mapping.get('output_triangles') != saved.n_faces):
        raise ValueError('original source face mapping differs')
    verify_survivor_mesh(before, saved, mapping['source_faces'])
    records = [json.loads(line) for line in (candidate / 'edit-log.jsonl').read_text(encoding='utf-8').splitlines()]
    if (not records or set(records[-1]) != {'check'}
            or any('check' in row for row in records[:-1])):
        raise ValueError('original E3 log must end in one check')
    check = records[-1]['check']
    if (audit.get('checks') != [check] or check.get('stage') != 'E3' or check.get('engine') != 'E3'
            or check.get('legacy') is not False or check.get('rollback') is not True
            or check.get('final') != 'PASS'):
        raise ValueError('original checked E3 plan required')
    all_edits = [_original_edit(row, before.n_faces) for row in records[:-1]]
    look_ids = {i: looks.key_of(name) for i, name in enumerate(before.materials)}
    keys = edit_keys(before, all_edits, look_ids)
    if any(row['removed'] != key['removed'] for row, key in zip(records[:-1], keys)):
        raise ValueError('original E3 source K1 keys differ')
    planned, removed, kept_sites, rolled_sites, kept = set(), set(), set(), set(), []
    for row, edit in zip(records[:-1], all_edits):
        if planned.intersection(edit.faces):
            raise ValueError('original E3 source faces are not disjoint')
        planned.update(edit.faces)
        if row.get('rolled_back', False):
            rolled_sites.add(edit.site)
        else:
            kept_sites.add(edit.site)
            removed.update(edit.faces)
            kept.append(edit)
    if kept_sites & rolled_sites:
        raise ValueError('original E3 site cannot be partly kept')
    if mapping['source_faces'] != [face for face in range(before.n_faces) if face not in removed]:
        raise ValueError('original E3 kept edits differ from source survivors')
    restore = tuple(restore_sites)
    if (any(type(site) is not int for site in restore) or len(set(restore)) != len(restore)
            or not set(restore).issubset(kept_sites)):
        raise ValueError('restored sites must be unique original kept E3 sites')
    replay = [edit for edit in kept if edit.site not in restore]
    proof = dict(original_audit_sha256=audit_hash, original_before_sha256=before_hash,
                 original_edit_log_sha256=log_hash, original_source_faces_sha256=map_hash,
                 original_kept_sites=len(kept_sites), restored_sites=sorted(restore),
                 remaining_sites=len({edit.site for edit in replay}),
                 remaining_removed_triangles=sum(len(edit.faces) for edit in replay),
                 fresh_site_check_required=True)
    return replay, proof


class _ReplayE3:
    name = 'E3'

    def __init__(self, edits):
        self.edits = tuple(edits)

    def plan(self, unit, ctx):
        return list(self.edits)


def run_checked_replay(before, looks, original_candidate, *, expected_audit_sha256, restore_sites=(0, 2, 9)):
    edits, receipt = load_replay_plan(before, looks, original_candidate,
        expected_audit_sha256=expected_audit_sha256, restore_sites=restore_sites)
    digest = _source_digest(before)
    unit = UnitState(mesh=before, topo=None,
        looks={i: looks.key_of(name) for i, name in enumerate(before.materials)}, viewpoints=None)
    context = RepairContext(profile=FixProfile(), decider=None, validator=SiteJudge(looks))
    outcome = repair_unit(unit, context, engines=[_ReplayE3(edits)], validate_sites=True)
    if _source_digest(before) != digest:
        raise ValueError('E3 replay mutated the original BEFORE')
    return outcome, source_survivors(before, outcome), receipt
