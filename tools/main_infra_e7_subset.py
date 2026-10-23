"""Propose a hash-bound donor-kept E7 subset and check it as a new real stage."""
from dataclasses import dataclass
import hashlib
import json
from pathlib import Path

from engine.fixes.pipeline import FixProfile
from engine.repair.engines.e7_thread import E7Thread
from engine.repair.kernel import repair_unit, stage_records
from engine.repair.types import RepairContext, UnitState, apply_edits
from engine.site_judge import SiteJudge
from tools.main_infra_e3 import _source_digest
from tools.main_infra_e3_binding import _hash
from tools.main_infra_e7_checkpoint import typed_plan_digest
from tools.main_infra_e7_serialization import _dump, _encode, _read

FROZEN_COMPONENTS = ('tools/main_infra_e7_1f_run.py', 'tools/main_infra_e7.py',
    'tools/main_infra_physical_validation.py', 'tools/main_infra_e3_binding.py',
    'engine/repair/engines/e7_thread.py', 'engine/repair/kernel.py',
    'engine/site_judge.py', 'engine/rays/caster.py')


def _look_ids(before, looks):
    return {i: looks.key_of(name) for i, name in enumerate(before.materials)}


def _seal(proof, edits):
    return hashlib.sha256((_dump(proof) + typed_plan_digest(edits)).encode()).hexdigest()


@dataclass(frozen=True)
class VerifiedSubset:
    edits: tuple
    proof: dict
    seal: str


def verify_donor_subset(before, looks, *, paths, expected_sha256, component_root, expected_counts=(628, 273)):
    if set(paths) != {'preparation', 'edit_log', 'worker'} or set(paths) != set(expected_sha256):
        raise ValueError('complete trusted donor inventory required')
    for key, path in paths.items():
        _hash(Path(path), expected_sha256[key])
    plan, worker = _read(paths['preparation']), _read(paths['worker'])
    if (worker.get('preparation_sha256') != expected_sha256['preparation']
            or worker.get('components') != plan['components']
            or plan['inputs']['before_digest'] != _source_digest(before).hex()
            or set(plan['paths']) != set(plan['sha256'])):
        raise ValueError('donor preparation or input binding differs')
    for key, path in plan['paths'].items():
        _hash(Path(path), plan['sha256'][key])
    for name in FROZEN_COMPONENTS:
        _hash(Path(component_root)/name, plan['components']['files'][name]['sha256'])
    rows = [json.loads(line) for line in Path(paths['edit_log']).read_text().splitlines()]
    planned_count, selected_count = expected_counts
    if len(rows) != planned_count + 1 or set(rows[-1]) != {'check'}:
        raise ValueError('donor record count differs')
    check = rows[-1]['check']
    if (worker.get('checks') != [check]
            or any(check.get(k) != v for k, v in dict(stage='E7', engine='E7', legacy=False, rollback=True).items())
            or worker.get('planned_cuts') != planned_count or worker.get('kept_cuts') != selected_count
            or worker.get('rolled_back_cuts') != planned_count-selected_count):
        raise ValueError('donor check/count metadata differs')
    look_ids = _look_ids(before, looks)
    edits = E7Thread().plan(UnitState(before, None, look_ids, None), RepairContext(FixProfile(), None, None))
    if len(edits) != planned_count:
        raise ValueError('donor regenerated plan count differs')
    selected_indices, rolled_sites = [], []
    for i, (row, actual) in enumerate(zip(stage_records(before, edits, look_ids, 'E7'), rows[:-1])):
        if 'rolled_back' in actual:
            if actual['rolled_back'] is not True:
                raise ValueError('invalid donor rollback marker')
            row['rolled_back'] = True
            rolled_sites.append(edits[i].site)
        else:
            selected_indices.append(i)
        if row != actual:
            raise ValueError('original donor K1 record differs')
    if (len(selected_indices) != selected_count or len(set(e.site for e in edits)) != planned_count
            or set(rolled_sites) != {row['site'] for row in check.get('rolled_back', [])}):
        raise ValueError('donor rollback partition/count differs')
    selected = tuple(edits[i] for i in selected_indices)
    predicted, _ = apply_edits(before, selected)
    if worker.get('output_triangles') != predicted.n_faces:
        raise ValueError('donor output triangle count differs')
    proof = dict(schema_version=1, policy='original_donor_kept_in_original_order_v1',
        donor_paths=paths, donor_sha256=expected_sha256, input_sha256=plan['sha256'],
        before_digest=_source_digest(before).hex(), donor_planned=planned_count, selected=selected_count,
        selected_donor_indices=selected_indices, selected_sites=[e.site for e in selected],
        excluded_sites=rolled_sites, all_original_K1_records_match=True, old_verdict_is_not_reused=True,
        regenerated_full_plan_digest=typed_plan_digest(edits), typed_plan_digest=typed_plan_digest(selected),
        selected_edits=[dict(_encode(e), decision=e.decision) for e in selected],
        look_ids={str(k): v for k, v in look_ids.items()})
    return VerifiedSubset(selected, proof, _seal(proof, selected))


def _verify_plan(before, looks, subset):
    if subset.proof['before_digest'] != _source_digest(before).hex():
        raise ValueError('verified subset input digest differs')
    if (subset.seal != _seal(subset.proof, subset.edits)
            or subset.proof['typed_plan_digest'] != typed_plan_digest(subset.edits)):
        raise ValueError('verified subset plan seal differs')
    if subset.proof['look_ids'] != {str(k): v for k, v in _look_ids(before, looks).items()}:
        raise ValueError('verified subset material input differs')


def run_checked_subset(before, looks, subset):
    _verify_plan(before, looks, subset)
    class BoundE7Subset:
        name = 'E7'
        def plan(self, unit, ctx):
            _verify_plan(unit.mesh, looks, subset)
            return list(subset.edits)
    unit = UnitState(before, None, _look_ids(before, looks), None)
    context = RepairContext(FixProfile(), None, SiteJudge(looks))
    outcome = repair_unit(unit, context, engines=[BoundE7Subset()], validate_sites=True)
    _verify_plan(before, looks, subset)
    return outcome
