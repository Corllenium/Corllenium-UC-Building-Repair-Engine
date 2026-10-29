"""Publish the Codex-vs-Claude candidate comparison to the dashboard (owner decision 2026-10-29: validate both, keep the better).

Builds the comparison with tools/main_infra_compare_candidates.py (loaded by path from the engine worktree that ran
the external validations), writes `codex-vs-claude-comparison.{json,md}` into every 4F-7F floor's evidence folder in
each `--public` dashboard root, adds the JSON ref to the floor's `evidence_refs`, and writes a one-line-per-candidate
summary into the floor's `blocker` text so the card shows the measured verdicts. With `--live`, the four evidence
folders are also uploaded to the live site over the same SSH path the status publisher uses. Floor `state` and
previews are left untouched: publishing the better candidate is a separate, deliberate step.
"""
from __future__ import annotations

import argparse
import importlib.util
import io
import json
import os
import subprocess
import tarfile
from pathlib import Path

from tools.main_infra_progress import load_progress, update_floor
from tools.publish_upper_status_live import REMOTE, ssh_args

UPPER = ('4F', '5F', '6F', '7F')
NAME = 'codex-vs-claude-comparison'


def load_compare(path: Path):
    spec = importlib.util.spec_from_file_location('main_infra_compare_candidates', path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def floor_line(row: dict) -> str:
    guard = 'PASS' if row['guard_passed'] else ('FAIL' if row['guard_passed'] is False else 'running')
    if not row['complete']:
        return f"{row['label']} ({row['worker']}, {row['output_triangles']:,} tri): guard {guard} {row['guard_px']} px, Validator running"
    checks = row['check_status'] or {}
    t = row['targets'] or {}
    after = ', '.join(f"{k} {t[k]['before']} to {t[k]['after']}" for k in ('flicker_diff', 'flicker_same', 'reversed', 'cracks') if k in t)
    return (f"{row['label']} ({row['worker']}, {row['output_triangles']:,} tri, removed {row['removed']:,}, added {row['added']}): "
            f"guard {guard} {row['guard_px']} px (ties {row['guard_zfight_tie']}); textures {checks.get('textures')} "
            f"({row['textures_failed']} samples); visible coverage {checks.get('nothing_deleted')}; signed targets "
            f"{checks.get('problems')}: {after}; Validator {row['validator_verdict']}")


def upload_live(public: Path, rev: str, run: str, key: str, known_hosts: str) -> None:
    """tar the four floors' evidence folders from `public` and extract them under both live web roots."""
    buffer = io.BytesIO()
    with tarfile.open(fileobj=buffer, mode='w:gz') as tar:
        for F in UPPER:
            rel = Path('models/main-infra') / rev / F / run / 'evidence'
            src = public / rel
            if os.name == 'nt':
                src = Path('\\\\?\\' + str(src))  # dashboard evidence paths exceed MAX_PATH
            if src.exists():
                tar.add(str(src), arcname=str(rel).replace(os.sep, '/'))
    app_public = os.path.dirname(REMOTE[0])
    web_root = os.path.dirname(REMOTE[1])
    remote = f"set -e; tar -xzf - -C {app_public}; for F in {' '.join(UPPER)}; do d=models/main-infra/{rev}/$F/{run}/evidence; mkdir -p {web_root}/$d; cp -rf {app_public}/$d/. {web_root}/$d/; done"
    subprocess.run(ssh_args(key, known_hosts) + [remote], input=buffer.getvalue(), check=True, timeout=300)


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--external', type=Path, required=True)
    parser.add_argument('--compare-tool', type=Path, required=True, help='tools/main_infra_compare_candidates.py of the engine worktree')
    parser.add_argument('--progress', type=Path, required=True)
    parser.add_argument('--public', type=Path, action='append', required=True)
    parser.add_argument('--live', action='store_true')
    parser.add_argument('--key', default=str(Path.home() / '.ssh' / 'corllenium_siege_ed25519'))
    parser.add_argument('--known-hosts', default='D:/PROJECTS/02-Corllenium-Siege/deploy/known_hosts')
    args = parser.parse_args(argv)
    compare = load_compare(args.compare_tool.resolve())
    doc = compare.build(args.external.resolve())
    (args.external / 'comparison.json').write_text(json.dumps(doc, indent=2), encoding='utf-8')
    (args.external / 'comparison.md').write_text(compare.markdown(doc), encoding='utf-8')
    progress = load_progress(args.progress)
    rev, run = progress['source_revision'], progress['run_id']
    published = {}
    for F in UPPER:
        entry = doc['floors'].get(F)
        if not entry:
            continue
        floor_doc = dict(rule=doc['rule'], floor=F, **entry)
        floor_md = compare.markdown(dict(rule=doc['rule'], floors={F: entry}))
        base = f'/models/main-infra/{rev}/{F}/{run}/evidence/'
        for public in args.public:
            dest = public.resolve() / base.lstrip('/')
            if os.name == 'nt':
                dest = Path('\\\\?\\' + str(dest))
            dest.mkdir(parents=True, exist_ok=True)
            (dest / f'{NAME}.json').write_text(json.dumps(floor_doc, indent=2), encoding='utf-8')
            (dest / f'{NAME}.md').write_text(floor_md, encoding='utf-8')
        row = progress['floors'][F]
        refs = list(row.get('evidence_refs') or [])
        ref = base + f'{NAME}.json'
        if ref not in refs:
            refs.append(ref)
        lines = [floor_line(r) for r in entry['rows']]
        better = f"Better so far: {entry['better']} ({entry['better_worker']})" if entry['better'] else 'No candidate fully measured yet'
        blocker = f"Codex vs Claude, one identical strict guard + Validator (allow coincident_backface_removed). {better}. " + ' | '.join(lines)
        update_floor(args.progress, F, row['state'], row['step'], blocker=blocker[:4000], evidence_refs=refs)
        published[F] = dict(measured=entry['measured'], candidates=entry['candidates'], better=entry['better'])
    if args.live:
        upload_live(args.public[0].resolve(), rev, run, args.key, args.known_hosts)
        published['live'] = True
    print(json.dumps(published))
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
