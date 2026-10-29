"""Run only checked E5 (the coincident-layer cull) and prove the surviving source triangle indices.

E5 is remove-only like E3, so its candidate is the same contract as E3's (`tools/main_infra_e3.py`): the surviving
source faces, in order, saved by `save_survivor_pair` as `candidate.engine.obj`, `candidate.source.obj` and
`source-faces.json` (`mode: original_source_survivors`). `run_checked_e5` runs `E5Coincident` under the kernel's site
checks with the Validator as judge and proves the outcome with `source_survivors(..., engine='E5')`. The stage audit's
`cleanup_mode` is `e5_cull_only` (over the baseline) or `e3_then_e5_cull` (over a checked E3 candidate); the binding
for both is `tools/main_infra_e5_binding.bind_saved_e5`.
"""
from engine.fixes.pipeline import FixProfile
from engine.repair.engines.e5_coincident import E5Coincident
from engine.repair.kernel import repair_unit
from engine.repair.types import RepairContext, UnitState
from engine.site_judge import SiteJudge
from engine.validate.checks import CBR, Settings
from tools.main_infra_e3 import _source_digest, save_survivor_pair, source_survivors, verify_survivor_mesh  # noqa: F401

CLEANUP_MODES = {'e5_cull_only': ['E5'], 'e3_then_e5_cull': ['E3', 'E5']}
#: How many kept-face rows of the engine report the stage audit keeps (the rest is counted).
KEPT_FACES_LISTED = 1000
#: The owner-approved Validator classes the E5 site judge runs with (owner decision 2026-10-24): the solid-facing twin
#: of a back-to-back pair may go, whatever its look.
ALLOWED_CHANGES = (CBR,)


def run_checked_e5(before, looks, flatness, priority=None, *, report=None, allowed_changes=ALLOWED_CHANGES,
                   prior_removed=None, exclude_sites=None):
    """`(outcome, survivor indices)` of one checked E5 stage over `before` with the Validator as site judge, judging
    under the owner-approved classes `allowed_changes` (`()` for the strict Validator). `priority(material name) ->
    int` overrides the default facade-wins rule; `prior_removed` are the triangles (k, 3, 3) an earlier stage removed
    (the `covers_prior_removal` rule); `exclude_sites` the E5 site ids not to plan (the replay loop); `report`, a dict,
    receives the engine's report (`audit_report` trims it for the stage audit)."""
    original = _source_digest(before)
    unit = UnitState(mesh=before, topo=None,
                     looks={i: looks.key_of(name) for i, name in enumerate(before.materials)}, viewpoints=None)
    engine = E5Coincident(flatness=flatness, priority=priority, prior_removed=prior_removed,
                          exclude_sites=None if exclude_sites is None else {int(s) for s in exclude_sites})
    judge = SiteJudge(looks, settings=Settings(allowed_changes=frozenset(allowed_changes)))
    context = RepairContext(profile=FixProfile(), decider=None, validator=judge)
    outcome = repair_unit(unit, context, engines=[engine], validate_sites=True)
    if _source_digest(before) != original:
        raise ValueError('E5 mutated the source input')
    if report is not None and engine.report is not None:
        report.update(engine.report)
    return outcome, source_survivors(before, outcome, engine='E5')


def audit_report(report):
    """The engine report for the stage audit: `kept_faces` cut to `KEPT_FACES_LISTED` rows, their total kept."""
    if not report:
        return None
    out = dict(report)
    rows = out.get('kept_faces') or []
    out['kept_faces_total'] = len(rows)
    out['kept_faces'] = rows[:KEPT_FACES_LISTED]
    return out
