"""Per-floor comparison table of every external-validation receipt (owner decision 2026-10-29: validate both, keep the better).

Reads `<external-dir>/*/external-validation.json` written by tools/main_infra_external_validate.py and writes
`comparison.json` and `comparison.md` beside them. "Better" is decided by the owner's acceptance bar in order:
guard PASS, then Validator checks (textures, nothing-deleted, floor) PASS, then fewer signed-target residuals
(flicker_diff + flicker_same + reversed + cracks after), then more triangles removed. The table only reports; it
never publishes.
"""
from __future__ import annotations

import argparse
import json
from pathlib import Path

TARGET_KINDS = ('flicker_diff', 'flicker_same', 'reversed', 'cracks', 'hidden')


def summarize(receipt: dict) -> dict:
    guard = receipt.get('guard') or {}
    totals = guard.get('totals') or {}
    guard_px = sum(int(totals.get(k, 0)) for k in ('holes', 'material_changed', 'moved_same_flat', 'moved_other',
                                                    'crack_closed', 'edge_flicker', 'fragment_removed', 'border_shift', 'grown'))
    validator = receipt.get('validator') or {}
    checks = validator.get('checks') or {}
    statuses = {name: (check.get('status') if isinstance(check, dict) else None) for name, check in checks.items()}
    kinds = ((checks.get('problems') or {}).get('kinds') or {})
    targets = {k: dict(before=kinds[k].get('before'), after=kinds[k].get('after'), status=kinds[k].get('status'))
               for k in TARGET_KINDS if k in kinds}
    textures = checks.get('textures') or {}
    residual = sum(int((targets.get(k) or {}).get('after') or 0) for k in ('flicker_diff', 'flicker_same', 'reversed', 'cracks'))
    membership = receipt.get('membership') or {}
    return dict(label=receipt.get('label'), worker=receipt.get('worker'), floor=receipt.get('floor_id'),
                candidate_dir=receipt.get('candidate_dir'), candidate_engine_sha256=receipt.get('candidate_engine_sha256'),
                input_triangles=receipt.get('input_triangles'), output_triangles=receipt.get('output_triangles'),
                removed=membership.get('removed'), added=membership.get('added'),
                dropped_marker_faces=((receipt.get('dropped_before_faces') or {}).get('count') or 0),
                guard_passed=guard.get('passed'), guard_px=guard_px, guard_zfight_tie=totals.get('zfight_tie'),
                guard_material_changed=totals.get('material_changed'), guard_moved_other=totals.get('moved_other'),
                guard_caster=guard.get('caster'),
                validator_verdict=validator.get('verdict'), validator_passed=validator.get('passed'), check_status=statuses,
                textures_failed=textures.get('samples_failed'), targets=targets, residual_after=residual,
                allowed_changes=validator.get('allowed_changes_active'), finished_utc=receipt.get('finished_utc'),
                wall_s=receipt.get('wall_s'), receipt=None)


def rank_key(row: dict):
    non_target = [s for name, s in (row['check_status'] or {}).items() if name != 'problems']
    all_pass = bool(non_target) and all(s == 'PASS' for s in non_target)
    return (0 if row['guard_passed'] else 1, 0 if all_pass else 1, row['residual_after'] if row['validator_verdict'] else 10 ** 9,
            -(row['removed'] or 0))


def build(external: Path) -> dict:
    rows = []
    for receipt_path in sorted(external.glob('*/external-validation.json')):
        receipt = json.loads(receipt_path.read_text(encoding='utf-8'))
        row = summarize(receipt)
        row['receipt'] = str(receipt_path)
        row['complete'] = 'finished_utc' in receipt
        rows.append(row)
    floors = {}
    for row in rows:
        floors.setdefault(row['floor'], []).append(row)
    verdicts = {}
    for floor, items in sorted(floors.items()):
        complete = [r for r in items if r['complete']]
        complete.sort(key=rank_key)
        best = complete[0] if complete else None
        verdicts[floor] = dict(candidates=len(items), measured=len(complete), better=best and best['label'],
                               better_worker=best and best['worker'], rows=sorted(items, key=lambda r: (not r['complete'], rank_key(r))))
    return dict(rule='guard PASS, then non-target checks PASS, then fewer signed residuals (flicker_diff+flicker_same+reversed+cracks after), then more removed',
                floors=verdicts)


def markdown(doc: dict) -> str:
    lines = ['# MAIN INFRA 4F-7F: Codex vs Claude candidates under one identical guard + Validator', '',
             f'Rule for "better": {doc["rule"]}.', '']
    for floor, entry in doc['floors'].items():
        lines += [f'## {floor}: {entry["measured"]}/{entry["candidates"]} measured, better so far: {entry["better"] or "none yet"} ({entry["better_worker"] or "-"})', '',
                  '| candidate | worker | triangles | removed / added | guard | guard px (ties) | textures | other checks | flicker_diff | flicker_same | reversed | cracks | hidden | verdict |',
                  '|---|---|---|---|---|---|---|---|---|---|---|---|---|---|']
        for r in entry['rows']:
            t = r['targets'] or {}
            cell = lambda k: (f'{t[k]["before"]} to {t[k]["after"]}' if k in t else '-')
            others = ', '.join(f'{n}:{s}' for n, s in (r['check_status'] or {}).items() if n not in ('textures', 'problems')) or '-'
            guard = 'PASS' if r['guard_passed'] else ('FAIL' if r['guard_passed'] is False else 'running')
            lines.append(f'| {r["label"]} | {r["worker"]} | {r["input_triangles"]} to {r["output_triangles"]} | {r["removed"]} / {r["added"]} | {guard} | {r["guard_px"]} ({r["guard_zfight_tie"]}) | '
                         f'{(r["check_status"] or {}).get("textures") or "-"} ({r["textures_failed"]}) | {others} | {cell("flicker_diff")} | {cell("flicker_same")} | {cell("reversed")} | {cell("cracks")} | {cell("hidden")} | {r["validator_verdict"] or ("running" if not r["complete"] else "-")} |')
        lines.append('')
    return '\n'.join(lines)


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--external', type=Path, required=True)
    args = parser.parse_args(argv)
    doc = build(args.external)
    (args.external / 'comparison.json').write_text(json.dumps(doc, indent=2), encoding='utf-8')
    (args.external / 'comparison.md').write_text(markdown(doc), encoding='utf-8')
    print(markdown(doc))
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
