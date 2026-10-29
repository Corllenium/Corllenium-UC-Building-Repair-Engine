"""The owner's flag -> site -> replay loop for E4 on one fresh floor (after real 7F chain run #3).

Usage (cwd = this worktree, PYTHONPATH = it):
  python -B -u tools/run_e4_replay_loop.py --root <claude run root> --floor 7F --raw-name "7th floor main infra.obj"
      --rounds 3 --allow coincident_backface_removed --helper <.../tools/main_infra_candidate.py> --job-id <id>
      --reviewer <name> [--expected-revision <sha>] [--no-allow-growth] [--interior-poses <json> --interior-px-max 60]

Each round k: E4 (`run_checked_e4_floor.py --from-e5 [--allow-growth] [--exclude-regions <union so far>]`), the output
moved to `<root>/e4/<F>-round<k>`; the E4 independent guard (`independent-validator/e4-guard/<F>-round<k>`; a PASS is
recorded into the round's audit as `guard.passed` with the receipt's path and hash, which the Validator's binding
requires); the Validator (`independent-validator/e4-validation/<F>-round<k>`, `--allow` classes). If check 3
(`nothing_deleted`) passes the loop stops `pass` and copies that round to `<root>/e4/<F>` for the chain. Otherwise
`tools/main_infra_e4_replay.py` maps the failing floor faces to regions; a failure no region explains stops the loop
(`unexplained`); the explained regions join the exclusions and the next round reruns E4 without them. Every round's
outputs stay; `<root>/e4/<F>-replay-summary.json` records the rounds, their verdicts, exclusions and the reason the
loop stopped. With `--interior-poses` the qualified walking-height poses would be rendered and their changed pixels
compared against `--interior-px-max` per view; this worktree holds no renderer (render_pair / contact sheet live in the
4F-7F worktree), so the loop records `interior: unavailable` and stops with that reason unless a `render_interior`
callable is injected; a view over the threshold is recorded `unmapped` (bbox projection through the saved camera is
not implemented) and stops the loop too.
"""
import argparse
import json
import shutil
import sys
import time
from pathlib import Path

from engine.io.snapshot import sha256_file

CBR = 'coincident_backface_removed'


def _run_e4(*, root, floor, raw_name, exclude, allow_growth, e5_candidate, out, **_kw):
    from tools.run_checked_e4_floor import main
    argv = ['--root', str(root), '--floor', floor, '--raw-name', raw_name, '--from-e5',
            '--e5-candidate', str(e5_candidate), '--out', str(out)]
    if allow_growth:
        argv.append('--allow-growth')
    if exclude is not None:
        argv += ['--exclude-regions', str(exclude)]
    return main(argv)


def _run_e5(*, root, floor, raw_name, exclude, out, **_kw):
    from tools.run_checked_e5_floor import main
    return main(['--root', str(root), '--floor', floor, '--raw-name', raw_name, '--from-e3',
                 '--exclude-sites', str(exclude), '--out', str(out)])


def _run_guard(*, root, floor, raw_name, candidate, out, helper, job_id, reviewer, expected_revision, **_kw):
    from tools.e4_independent_guard import main
    if helper is None:
        raise ValueError('the E4 independent guard needs --helper (tools/main_infra_candidate.py holding strict_guard)')
    argv = ['--root', str(root), '--floor', floor, '--raw-name', raw_name, '--candidate', str(candidate), '--out', str(out),
            '--helper', str(helper), '--job-id', job_id, '--reviewer', reviewer]
    if expected_revision:
        argv += ['--expected-revision', expected_revision]
    return main(argv)


def _run_validator(*, root, floor, raw_name, candidate, out, allow, **_kw):
    from tools.main_infra_physical_validation import main
    argv = ['--raw', str(root / 'raw' / raw_name), '--reference', str(root / 'reference' / f'{floor}.json'),
            '--baseline', str(root / 'normalized' / floor),
            '--qualification', str(root / 'independent-validator' / 'import-audit' / f'qualification-{floor}.json'),
            '--candidate', str(candidate),
            '--materials', str(root / 'independent-validator' / 'preflight' / f'materials-{floor}.json'),
            '--out', str(out)]
    for name in allow:
        argv += ['--allow', name]
    return main(argv)


def _record_guard(candidate: Path, receipt_path: Path) -> None:
    audit_path = candidate / 'stage-audit.json'
    audit = json.loads(audit_path.read_text(encoding='utf-8'))
    audit['guard'] = dict(passed=True, state='passed', receipt=str(receipt_path), receipt_sha256=sha256_file(receipt_path),
                          recorded_by='tools/run_e4_replay_loop.py')
    audit_path.write_text(json.dumps(audit, indent=2), encoding='utf-8')


def run_loop(*, root, floor, raw_name, rounds=3, allow=(CBR,), allow_growth=True, helper=None, job_id='e4-replay',
             reviewer='replay-loop', expected_revision=None, interior_poses=None, interior_px_max=60,
             run_e4=None, run_e5=None, run_guard=None, run_validator=None, render_interior=None, inputs=None) -> dict:
    """Run the loop (see the module docstring); returns the summary it also writes. `run_e4`, `run_e5`, `run_guard`,
    `run_validator` and `render_interior` are the steps, injectable for tests; `inputs` is passed through to them.
    When a round's failures name E5 sites, the next round reruns E5 (`--from-e3 --exclude-sites`) into
    `<root>/e5/<F>-round<k>` and E4 reads that candidate."""
    root = Path(root).resolve()
    run_e4 = run_e4 or _run_e4
    run_e5 = run_e5 or _run_e5
    run_guard = run_guard or _run_guard
    run_validator = run_validator or _run_validator
    e4_root, e5_root = root / 'e4', root / 'e5'
    e4_root.mkdir(parents=True, exist_ok=True)
    live = e4_root / floor
    if live.exists():
        raise ValueError(f'{live} exists: move the previous E4 candidate aside before the replay loop')
    current_e5 = e5_root / floor
    if not (current_e5 / 'stage-audit.json').exists():
        raise ValueError(f'{current_e5} holds no E5 candidate: run E5 (--from-e3) first')
    started = time.perf_counter()
    summary = dict(schema_version=2, root=str(root), floor=floor, raw_name=raw_name, allow=sorted(allow),
                   allow_growth=bool(allow_growth), rounds_requested=int(rounds), rounds=[], excluded_regions=[],
                   excluded_sites=[], exclusion_reasons={}, e5_exclusion_reasons={}, status='rounds_exhausted',
                   final_candidate=None, final_e5_candidate=str(current_e5), interior=None)
    excluded: set[int] = set()
    excluded_sites: set[int] = set()
    reasons: dict[str, list] = {}
    site_reasons: dict[str, list] = {}
    e5_dirty = False                                         # new E5 exclusions since the last E5 run
    for k in range(1, int(rounds) + 1):
        if e5_dirty:
            e5_exclude = e5_root / f'{floor}-round{k}-exclude-sites.json'
            e5_exclude.write_text(json.dumps(dict(e5_sites=sorted(excluded_sites), reasons=site_reasons, round=k), indent=2),
                                  encoding='utf-8')
            e5_out = e5_root / f'{floor}-round{k}'
            code = run_e5(root=root, floor=floor, raw_name=raw_name, exclude=e5_exclude, out=e5_out, inputs=inputs)
            if code != 0 or not (e5_out / 'stage-audit.json').exists():
                summary['status'] = 'e5_failed'
                break
            current_e5 = e5_out
            e5_dirty = False
        exclude_path = None
        if excluded:
            exclude_path = e4_root / f'{floor}-round{k}-exclude.json'
            exclude_path.write_text(json.dumps(dict(regions=sorted(excluded), reasons=reasons, round=k), indent=2),
                                    encoding='utf-8')
        candidate = e4_root / f'{floor}-round{k}'
        code = run_e4(root=root, floor=floor, raw_name=raw_name, exclude=exclude_path, allow_growth=allow_growth,
                      e5_candidate=current_e5, out=candidate, inputs=inputs)
        if code != 0 or not candidate.exists():
            summary['status'] = 'e4_failed'
            break
        row = dict(round=k, candidate=str(candidate), e5_candidate=str(current_e5), excluded_regions=sorted(excluded),
                   excluded_sites=sorted(excluded_sites), exclude_file=None if exclude_path is None else str(exclude_path),
                   guard=None, validation=None, nothing_deleted=None, verdict=None,
                   explained_regions=[], explained_e5_sites=[], unexplained=[])
        summary['rounds'].append(row)
        guard_out = root / 'independent-validator' / 'e4-guard' / f'{floor}-round{k}'
        code = run_guard(root=root, floor=floor, raw_name=raw_name, candidate=candidate, out=guard_out, helper=helper,
                         job_id=job_id, reviewer=reviewer, expected_revision=expected_revision, inputs=inputs)
        receipt_path = guard_out / 'independent-guard.json'
        row['guard'] = dict(returncode=code, receipt=str(receipt_path) if receipt_path.exists() else None)
        if code != 0:
            summary['status'] = 'guard_failed'
            break
        _record_guard(candidate, receipt_path)
        val_out = root / 'independent-validator' / 'e4-validation' / f'{floor}-round{k}'
        code = run_validator(root=root, floor=floor, raw_name=raw_name, candidate=candidate, out=val_out, allow=allow,
                             inputs=inputs)
        validation = val_out / 'validation.json'
        if not validation.exists():
            summary['status'] = 'validator_failed'
            row['validation'] = dict(returncode=code, path=None)
            break
        report = json.loads(validation.read_text(encoding='utf-8'))
        g = report['checks']['nothing_deleted']
        row.update(validation=dict(returncode=code, path=str(validation)), nothing_deleted=g['status'],
                   verdict=report.get('verdict'), failed_by=g.get('failed_by'),
                   textures=report['checks'].get('textures', {}).get('status'))
        if interior_poses is not None:
            if render_interior is None:
                summary['interior'] = dict(status='unavailable', poses=str(interior_poses),
                                           reason='no renderer in this worktree (render_pair / contact sheet live in the '
                                                  '4F-7F worktree); inject render_interior or run the interior gate apart')
                summary['status'] = 'interior_unavailable'
                break
            views = render_interior(poses=interior_poses, candidate=candidate, root=root, floor=floor, out=val_out / 'interior')
            over = {name: px for name, px in views.items() if px > interior_px_max}
            summary['interior'] = dict(status='over_threshold' if over else 'pass', views=views, px_max=interior_px_max,
                                       over=over, mapping='unmapped' if over else None)
            row['interior'] = summary['interior']
            if over:
                summary['status'] = 'interior_unmapped'
                break
        if g['status'] == 'PASS':
            summary['status'] = 'pass'
            summary['final_candidate'] = str(candidate)
            summary['final_e5_candidate'] = str(current_e5)
            shutil.copytree(candidate, live)
            break
        from tools.main_infra_e4_replay import explain_failures
        explained = explain_failures(candidate=candidate, validation=validation)
        (e4_root / f'{floor}-round{k}-explained.json').write_text(json.dumps(explained, indent=2), encoding='utf-8')
        row['explained_regions'] = explained['e4_regions']
        row['explained_e5_sites'] = explained['e5_sites']
        row['unexplained'] = explained['unexplained']
        if explained['unexplained']:
            summary['status'] = 'unexplained'
            break
        new = set(explained['e4_regions']) - excluded
        new_sites = set(explained['e5_sites']) - excluded_sites
        if not new and not new_sites:
            summary['status'] = 'no_new_exclusions'
            break
        excluded |= new
        for r, rows in explained['reasons']['e4_regions'].items():
            reasons.setdefault(r, []).extend(dict(row_, round=k) for row_ in rows)
        if new_sites:
            excluded_sites |= new_sites
            e5_dirty = True
            for s, rows in explained['reasons']['e5_sites'].items():
                site_reasons.setdefault(s, []).extend(dict(row_, round=k) for row_ in rows)
    summary.update(rounds_run=len(summary['rounds']), excluded_regions=sorted(excluded), exclusion_reasons=reasons,
                   excluded_sites=sorted(excluded_sites), e5_exclusion_reasons=site_reasons,
                   wall_s=round(time.perf_counter() - started, 2))
    (e4_root / f'{floor}-replay-summary.json').write_text(json.dumps(summary, indent=2), encoding='utf-8')
    return summary


def build_parser():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--root', type=Path, required=True)
    parser.add_argument('--floor', required=True)
    parser.add_argument('--raw-name', required=True)
    parser.add_argument('--rounds', type=int, default=3)
    parser.add_argument('--allow', action='append', default=[], help='Validator allowed-change class (repeatable)')
    parser.add_argument('--allow-growth', action=argparse.BooleanOptionalAction, default=True)
    parser.add_argument('--helper', type=Path, default=None, help='tools/main_infra_candidate.py holding strict_guard')
    parser.add_argument('--job-id', default='e4-replay')
    parser.add_argument('--reviewer', default='replay-loop')
    parser.add_argument('--expected-revision', default=None)
    parser.add_argument('--interior-poses', type=Path, default=None)
    parser.add_argument('--interior-px-max', type=int, default=60)
    return parser


def main(argv=None):
    args = build_parser().parse_args(argv)
    summary = run_loop(root=args.root, floor=args.floor, raw_name=args.raw_name, rounds=args.rounds,
                       allow=tuple(args.allow), allow_growth=args.allow_growth, helper=args.helper, job_id=args.job_id,
                       reviewer=args.reviewer, expected_revision=args.expected_revision,
                       interior_poses=args.interior_poses, interior_px_max=args.interior_px_max)
    print(json.dumps({k: summary[k] for k in ('status', 'rounds_run', 'excluded_regions', 'final_candidate', 'wall_s')}),
          flush=True)
    return 0 if summary['status'] == 'pass' else 2


if __name__ == '__main__':
    sys.exit(main())
