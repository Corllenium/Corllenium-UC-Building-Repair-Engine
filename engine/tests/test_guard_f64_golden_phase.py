import importlib.util
import json
from pathlib import Path
import sys

import numpy as np
import pytest

from engine.tests.fixtures.build import cube
from engine.topo.weld import axis_quanta
from engine.fixes.pipeline import FixProfile, guard_depth_tol

SCRIPT = Path(__file__).resolve().parents[2] / 'docs/superpowers/records/MAIN-INFRA-GUARD-F64-20261024/golden_guard_phase.py'
spec = importlib.util.spec_from_file_location('golden_guard_phase', SCRIPT)
phase = importlib.util.module_from_spec(spec)
sys.modules[spec.name] = phase
spec.loader.exec_module(phase)


def pair():
    b, a = cube(), cube()
    b.positions += [12000, 23000, 8000]
    a.positions = a.positions[::-1].copy() + [12000, 23000, 8000]
    a.face_v = 7 - a.face_v
    b.materials = ['wall', 'unused-before']
    a.materials = ['unused-after', 'wall']
    a.face_material[:] = 1
    return b, a


def test_genuine_separate_position_tables_use_one_before_center_and_exact_material_names():
    b, a = pair()
    bp, ap = b.positions.copy(), a.positions.copy()
    p = phase.prepare_pair(b, a)
    np.testing.assert_array_equal(p['before_positions'], bp - p['center'])
    np.testing.assert_array_equal(p['after_positions'], ap - p['center'])
    np.testing.assert_array_equal(p['before_materials'], p['after_materials'])
    assert p['depth_tol'] == guard_depth_tol(axis_quanta(bp, b.sig_digits), FixProfile())
    result = phase.measure_view(p, (0.013, 0.007, -0.989), (16, 12), phase.corrected)
    assert result['passed'] and result['totals']['model_px'] > 0
    np.testing.assert_array_equal(b.positions, bp)
    np.testing.assert_array_equal(a.positions, ap)


def test_genuine_material_change_and_surface_translation_are_not_normalized_away():
    b, a = pair()
    a.materials[1] = 'different-wall'
    result = phase.measure_view(phase.prepare_pair(b, a), (0.013, 0.007, -0.989), (16, 12), phase.corrected)
    assert not result['passed'] and result['totals']['material_changed'] > 0
    b, a = pair()
    a.positions += [0, 0, 2]
    result = phase.measure_view(phase.prepare_pair(b, a), (0.013, 0.007, -0.989), (16, 12), phase.corrected)
    assert not result['passed'] and result['totals']['moved_other'] > 0


def test_genuine_removed_visible_face_stays_a_failure():
    b, a = pair()
    a.face_v = a.face_v[:2]
    a.face_material = a.face_material[:2]
    result = phase.measure_view(phase.prepare_pair(b, a), (0.013, 0.007, -0.989), (16, 12), phase.corrected)
    assert not result['passed']


def plan(tmp_path):
    f = tmp_path / 'bound'; f.write_bytes(b'bytes')
    return dict(schema_version=1, unit='tiny-schema-only', before=str(f), after=str(f), baseline_compare=str(f), output=str(tmp_path/'out'), pins=[dict(path=str(x), sha256=phase.sha(x)) for x in [f, SCRIPT, Path(phase.corrected.__file__)]], views=[list(x) for x in phase.VIEWS_26], size=[900, 600], strict=True, caps=dict(edge_flicker=0, crack_closed=0, fragment_removed=0, border_shift=0), acceptance=False)


def test_plan_requires_exact_complete_file_hashes_and_refuses_existing_output(tmp_path):
    p = plan(tmp_path)
    phase.verify_plan(p)
    Path(p['before']).write_bytes(b'changed')
    with pytest.raises(ValueError, match='hash'):
        phase.verify_plan(p)
    p = plan(tmp_path)
    Path(p['output']).mkdir()
    with pytest.raises(ValueError, match='exists'):
        phase.verify_plan(p)


@pytest.mark.parametrize('change', ['views', 'size', 'strict', 'caps', 'missing_pin'])
def test_cli_cannot_override_the_full_strict_guard_protocol(tmp_path, change):
    p = plan(tmp_path)
    if change == 'views': p['views'] = p['views'][:1]
    if change == 'size': p['size'] = [16, 12]
    if change == 'strict': p['strict'] = False
    if change == 'caps': p['caps']['crack_closed'] = 1e-3
    if change == 'missing_pin': p['pins'] = []
    with pytest.raises(ValueError):
        phase.verify_plan(p)


def test_baseline_loader_is_the_exact_retained_module_with_unchanged_dependencies():
    old = Path('D:/LLM_BACKUP/Codex session/main-infra-2f-validation-20261023/05-Corllenium-UC-Building-Repair-Engine/engine/guard/compare.py')
    baseline = phase.load_baseline(old)
    assert Path(baseline.__file__).resolve() == old.resolve()
    assert baseline._displacement is not phase.corrected._displacement
    b, a = pair()
    result = phase.measure_view(phase.prepare_pair(b, a), (0.013, 0.007, -0.989), (16, 12), baseline)
    assert result['passed']