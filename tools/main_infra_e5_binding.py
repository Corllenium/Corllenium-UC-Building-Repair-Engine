"""Bind a saved E5 (coincident-layer cull) candidate to its checked edits and to the qualified baseline.

E5 is remove-only, so the proof is E3's (`tools.main_infra_e3_binding.bind_remove_only`, engine "E5"): the candidate is
its BEFORE minus exactly the faces of the kept non-legacy E5 `remove` edits of one checked, rollback-enabled stage, in
both frames, with `source-faces.json` and `edit-log.jsonl` hash-bound to the audit. `cleanup_mode` is `e5_cull_only`
(BEFORE = the qualified baseline, `executed_stages == ["E5"]`) or `e3_then_e5_cull` (BEFORE = the E3 candidate the
audit's `e3_candidate` names, proven by `chained_e3_before`; `["E3", "E5"]`). The Validator's BEFORE stays the
baseline; `baseline_kept_source_faces` maps the candidate's faces back to it through E3's survivor list.

The 4F-7F worktree's `tools/e3_independent_guard.py` binds a candidate with `bind_saved_e3`, which accepts only
`e3_remove_only`; to run that guard on an E5 candidate it needs the same relaxation (`bind_saved_e5`, or
`bind_remove_only` with the engine from the audit's `executed_stages[-1]`). That worktree is not edited here.
"""
import json
from dataclasses import replace
from pathlib import Path

from engine.io.obj_reader import read_obj
from tools.main_infra_e3_binding import _hash, bind_remove_only, chained_e3_before

CLEANUP_MODES = {'e5_cull_only': ['E5'], 'e3_then_e5_cull': ['E3', 'E5']}


def bind_saved_e5(*, candidate, audit, before_engine, after_engine, before_source, after_source,
                  require_guard: bool = True):
    """`require_guard` (the default, the Validator path) refuses an audit without `guard.passed`; the independent
    guard, and a later stage chaining through this candidate, call with `require_guard=False`."""
    mode = audit.get('cleanup_mode')
    if mode not in CLEANUP_MODES or audit.get('executed_stages') != CLEANUP_MODES[mode]:
        raise ValueError('only the checked E5 cleanup contracts are allowed')
    if require_guard and audit.get('guard', {}).get('passed') is not True:
        raise ValueError('E5 candidate strict guard required (guard.passed)')
    e3_contract, e3_faces = None, list(range(before_engine.n_faces))
    e5_before_engine, e5_before_source = before_engine, before_source
    if mode == 'e3_then_e5_cull':
        e5_before_engine, e5_before_source, e3_faces, e3_contract = chained_e3_before(
            audit=audit, before_engine=before_engine, before_source=before_source)
    proof = bind_remove_only(engine='E5', candidate=candidate, audit=audit, before_engine=e5_before_engine,
                             after_engine=after_engine, before_source=e5_before_source, after_source=after_source)
    return dict(candidate_contract=mode, source_faces_sha256=proof['source_faces_sha256'],
                edit_log_sha256=proof['edit_log_sha256'], e3_contract=e3_contract,
                e3_removed_triangles=before_engine.n_faces - len(e3_faces),
                e5_removed_triangles=proof['removed_triangles'], e5_source_faces=proof['source_faces'],
                baseline_kept_source_faces=[int(e3_faces[f]) for f in proof['source_faces']])


def chained_e5_before(*, audit, before_engine, before_source):
    """The E3 -> E5 candidate a later stage's audit chains through (`e5_candidate`: its dir and the hashes of its
    engine and source candidate, `source-faces.json` and `stage-audit.json`), proven against the baseline through its
    own `e3_candidate`: `(e5 engine mesh, e5 source mesh, baseline face id of each E5 candidate face, E5 contract)`."""
    binding = audit.get('e5_candidate')
    if not isinstance(binding, dict) or not binding.get('candidate'):
        raise ValueError('a chained audit needs the E5 candidate binding (e5_candidate)')
    e5_dir = Path(binding['candidate'])
    _hash(e5_dir / 'stage-audit.json', binding.get('stage_audit_sha256'), 'E5')
    e5_audit = json.loads((e5_dir / 'stage-audit.json').read_text(encoding='utf-8'))
    if e5_audit.get('cleanup_mode') != 'e3_then_e5_cull':
        raise ValueError('a chained E5 candidate must be the checked E3 -> E5 cull (cleanup_mode e3_then_e5_cull)')
    for key, name in (('engine_candidate_sha256', 'candidate.engine.obj'),
                      ('source_candidate_sha256', 'candidate.source.obj'), ('source_faces_sha256', 'source-faces.json')):
        if e5_audit.get(key) != binding.get(key):
            raise ValueError(f'E5 candidate binding differs from its audit: {key}')
        _hash(e5_dir / name, binding.get(key), 'E5')
    e5_engine = replace(read_obj(e5_dir / 'candidate.engine.obj'), physical_quanta=before_engine.physical_quanta)
    e5_source = read_obj(e5_dir / 'candidate.source.obj')
    contract = bind_saved_e5(candidate=e5_dir, audit=e5_audit, before_engine=before_engine, after_engine=e5_engine,
                             before_source=before_source, after_source=e5_source, require_guard=False)
    return e5_engine, e5_source, contract['baseline_kept_source_faces'], contract
