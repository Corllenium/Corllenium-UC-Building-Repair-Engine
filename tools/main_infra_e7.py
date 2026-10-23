"""Run only strict existing-vertex E7 threading, with fresh default site checks."""
from engine.fixes.pipeline import FixProfile
from engine.repair.engines.e7_thread import E7Thread
from engine.repair.kernel import repair_unit
from engine.repair.types import RepairContext, UnitState
from engine.site_judge import SiteJudge
from tools.main_infra_e3 import _source_digest


def run_checked_e7(before, looks):
    digest = _source_digest(before)
    unit = UnitState(before, None,
        {i: looks.key_of(name) for i, name in enumerate(before.materials)}, None)
    context = RepairContext(FixProfile(), None, SiteJudge(looks))
    result = repair_unit(unit, context, engines=[E7Thread()], validate_sites=True)
    if _source_digest(before) != digest:
        raise ValueError('E7 mutated the original input')
    return result
