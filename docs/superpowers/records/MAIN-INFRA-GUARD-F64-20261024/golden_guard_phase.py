"""Private frozen-pair comparison of the retained and corrected guard metrics."""
from __future__ import annotations

import argparse
from dataclasses import asdict
import hashlib
import importlib.util
import json
from pathlib import Path
import sys
import time

import numpy as np

from engine.guard import compare as corrected
from engine.guard.render import save_triptych
from engine.guard.views import VIEWS_26, ortho_first_hit
from engine.fixes.pipeline import FixProfile, guard_depth_tol
from engine.io.obj_reader import read_obj
from engine.rays.caster import EmbreeCaster
from engine.topo.weld import axis_quanta

ROOT = Path(__file__).resolve().parents[4]


def sha(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def verify_plan(plan, *, output_may_exist=False):
    protocol = (plan.get('schema_version') == 1 and plan.get('views') == [list(x) for x in VIEWS_26]
                and plan.get('size') == [900, 600] and plan.get('strict') is True
                and plan.get('caps') == dict(edge_flicker=0, crack_closed=0, fragment_removed=0, border_shift=0)
                and plan.get('acceptance') is False)
    if not protocol:
        raise ValueError('golden plan must use the complete strict26 protocol')
    pins = plan.get('pins')
    if not isinstance(pins, list) or not pins:
        raise ValueError('golden pins missing')
    paths = set()
    for pin in pins:
        p = Path(pin['path']).resolve()
        if p in paths or sha(p) != pin['sha256']:
            raise ValueError(f'golden hash/duplicate pin: {p}')
        paths.add(p)
    required = [plan['before'], plan['after'], plan['baseline_compare'], __file__, corrected.__file__]
    if any(Path(p).resolve() not in paths for p in required):
        raise ValueError('golden required hash pin missing')
    if not output_may_exist and Path(plan['output']).exists():
        raise ValueError('golden output exists')


def load_baseline(path):
    spec = importlib.util.spec_from_file_location('_golden_retained_compare', Path(path))
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


def prepare_pair(before, after):
    center = (before.positions.min(axis=0) + before.positions.max(axis=0)) / 2
    names = sorted(set(before.materials) | set(after.materials))
    indices = {name: i for i, name in enumerate(names)}
    bm = np.array([indices[before.materials[i]] for i in before.face_material], dtype=np.int64)
    am = np.array([indices[after.materials[i]] for i in after.face_material], dtype=np.int64)
    bp = np.asarray(before.positions, dtype=np.float64) - center
    ap = np.asarray(after.positions, dtype=np.float64) - center
    quanta = axis_quanta(before.positions, before.sig_digits)
    return dict(center=center, names=names, before_positions=bp, after_positions=ap,
                before_faces=before.face_v, after_faces=after.face_v,
                before_materials=bm, after_materials=am, quanta=quanta,
                depth_tol=guard_depth_tol(quanta, FixProfile()),
                before_planes=corrected.face_planes(bp, before.face_v),
                after_planes=corrected.face_planes(ap, after.face_v))


def buffers(pair, view, size):
    bp, ap = pair['before_positions'], pair['after_positions']
    bf, af = pair['before_faces'], pair['after_faces']
    if 'casters' not in pair:
        pair['casters'] = (EmbreeCaster(bp, bf), EmbreeCaster(ap, af))
    def factory(p, f):
        if p is bp and f is bf: return pair['casters'][0]
        if p is ap and f is af: return pair['casters'][1]
        raise ValueError('unexpected golden geometry')
    b = ortho_first_hit(bp, bf, np.arange(len(bf)), view, bp, size, factory)
    a = ortho_first_hit(ap, af, np.arange(len(af)), view, bp, size, factory)
    return b, a, factory


def measure_view(pair, view, size, module, rendered=None):
    b, a, factory = rendered if rendered is not None else buffers(pair, view, size)
    report = module.compare_views([(view, b)], [(view, a)],
        pair['before_materials'], pair['after_materials'], frozenset(), pair['depth_tol'],
        strict=True, plane_before=pair['before_planes'], plane_after=pair['after_planes'],
        geometry_before=(pair['before_positions'], pair['before_faces']),
        geometry_after=(pair['after_positions'], pair['after_faces']), caster_factory=factory,
        edge_flicker_cap=0, crack_closed_cap=0, fragment_removed_cap=0, border_shift_tol=0)
    return asdict(report)


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--plan', required=True, type=Path)
    parser.add_argument('--plan-sha256', required=True)
    args = parser.parse_args(argv)
    if sha(args.plan) != args.plan_sha256:
        raise ValueError('golden external plan hash mismatch')
    plan = json.loads(args.plan.read_text())
    verify_plan(plan)
    if Path(corrected.__file__).resolve() != ROOT / 'engine/guard/compare.py':
        raise ValueError('golden imported the wrong worktree')
    out = Path(plan['output']).resolve()
    if not out.is_relative_to(ROOT / 'data'):
        raise ValueError('golden output must be in owned worktree data')
    out.mkdir(parents=True, exist_ok=False)
    started = time.monotonic()
    before, after = read_obj(plan['before']), read_obj(plan['after'])
    pair = prepare_pair(before, after)
    baseline = load_baseline(plan['baseline_compare'])
    reports = dict(baseline=[], corrected=[])
    qa = []
    for index, view in enumerate(VIEWS_26):
        rendered = buffers(pair, view, (900, 600))
        for role, module in [('baseline', baseline), ('corrected', corrected)]:
            reports[role].append(measure_view(pair, view, (900, 600), module, rendered))
        b, a, _ = rendered
        codes = corrected.classify_pixels(b.depth, b.tri, a.depth, a.tri,
            pair['before_materials'], pair['after_materials'], frozenset(), pair['depth_tol'],
            origins=b.origins, direction=b.direction, plane_before=pair['before_planes'],
            plane_after=pair['after_planes'], strict=True)
        png = out / 'qa' / f'view-{index:02d}-base-classification.png'
        save_triptych(png, b, a, codes, pair['before_planes'][:, :3], pair['after_planes'][:, :3])
        qa.append(dict(path=str(png), sha256=sha(png)))
        print(json.dumps(dict(view=index, baseline=reports['baseline'][-1]['passed'],
                             corrected=reports['corrected'][-1]['passed'])), flush=True)
    verify_plan(plan, output_may_exist=True)
    if sha(args.plan) != args.plan_sha256:
        raise ValueError('golden plan changed during comparison')
    summary = {}
    for role, rows in reports.items():
        totals = {k: sum(row['totals'][k] for row in rows) for k in rows[0]['totals']}
        summary[role] = dict(passed=all(row['passed'] for row in rows), totals=totals, views=[v for row in rows for v in row['views']])
    result = dict(schema_version=1, unit=plan['unit'], plan_sha256=args.plan_sha256,
        before_sha256=sha(plan['before']), after_sha256=sha(plan['after']),
        before_triangles=before.n_faces, after_triangles=after.n_faces,
        center_inches=pair['center'].tolist(), source_quanta_inches=pair['quanta'].tolist(),
        source_sig_digits=before.sig_digits, depth_tol_inches=pair['depth_tol'],
        common_material_names=pair['names'], size=[900, 600], view_count=26,
        protocol='strict26; all materials patterned; zero edge/crack/fragment/border allowances',
        reports=summary, evidence=qa, input_pins=plan['pins'], wall_s=time.monotonic()-started,
        qa_limitation='PNG DIFF is base classification without ring/tie promotions; reports contain authoritative compare_views outcomes.',
        model_acceptance=False, owner_signed_validator_run=False)
    (out/'guard-comparison.json').write_text(json.dumps(result, indent=2)+'\n')
    print(json.dumps(dict(output=str(out/'guard-comparison.json'), sha256=sha(out/'guard-comparison.json'), baseline=summary['baseline']['passed'], corrected=summary['corrected']['passed'])), flush=True)
    return 0 if summary['corrected']['passed'] else 2


if __name__ == '__main__':
    raise SystemExit(main())