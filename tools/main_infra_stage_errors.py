"""Per-face stage classifications for the fresh MAIN INFRA dashboard, in the errors.json shape, from saved run dirs.

`tools/main_infra_errors.py` (the 4F-7F worktree) writes the detector census: ``{"schema_version": 1, "n_faces": N,
"counts": {kind: n}, "faces": {kind: [triangle ids]}}`` with the seven kinds flicker_diff, flicker_same, reversed,
hidden, loose, open_edges, cracks. This tool writes the SAME shape with the repair-stage and crack-judgement kinds, for
the BEFORE model (the first given stage's input) and the AFTER model (the last given stage's output), reading only the
artifacts the floor runners saved:

- an E5 run dir (`<root>/e5/<F>/`: stage-audit.json, edit-log.jsonl, source-faces.json; input = the E3 candidate the
  audit's `e3_candidate` names, else the baseline snapshot): `backface_twin` and `interior_seam` (faces removed by the
  rules backface_twin / interior_twins), `two_sided_sheet` (the audit's kept pairs with reason both_exposed),
  `e5_rolled_back` (faces of rolled-back sites, the judge's reasons in `details.e5_rolled_back[face]`);
- an E4 run dir (`<root>/e4/<F>/`: region-map.json, stage-audit.json, edit-log.jsonl): `merge_region` (source faces of
  the kept regions on BEFORE, their new triangles on AFTER), `merge_refused` (faces of the refused regions, kept on
  AFTER, the reason in `details.merge_refused[face]`), `e4_rolled_back` (faces of rolled-back sites);
- a crack judgement (`tools/main_infra_crack_judge.py`): `jev_merge`, `jev_keep`, `jev_unsure` (every face of the
  judged regions, `details.jev[face] = {provider, reason}`); its ids are the E4 input's.

Ids: the edit log, the survivor map and the region map carry each stage's own input ids; faces are carried back to the
BEFORE model through the earlier stage's survivors (`source-faces.json`) and forward to the AFTER model through the
survivors, E4's `kept_source_faces` and the kept regions' `new_triangles`. Every id is checked against the face count of
the OBJ the audits name (refused when out of range). The E5 edit log does not record the rule per face: a site whose
reason names one rule is that rule; in a mixed site the coincident opposite pairs are the interior seams and the rest
take the one remaining rule, else the site is listed in `details.e5_unresolved` and classified nowhere.

`--with-census` also runs `engine.detectors.errors.find_errors` on each model so one errors.json carries everything;
`--merge-into-before/--merge-into-after <existing>` keep the existing file's other kinds and extra keys, replace the
stage kinds and refuse a different `n_faces`.
"""
from __future__ import annotations

import argparse
import ast
import json
import re
from pathlib import Path

from engine.fixes.pipeline import FixProfile
from engine.io.obj_reader import read_obj
from engine.pipeline import analyse_topology_memo

BASE_KINDS = ('flicker_diff', 'flicker_same', 'reversed', 'hidden', 'loose', 'open_edges', 'cracks')
E5_KINDS = ('backface_twin', 'interior_seam', 'two_sided_sheet', 'e5_rolled_back')
E4_KINDS = ('merge_region', 'merge_refused', 'e4_rolled_back')
JEV_KINDS = ('jev_merge', 'jev_keep', 'jev_unsure')
STAGE_KINDS = E5_KINDS + E4_KINDS + JEV_KINDS
#: The E5 engine's by_rule dict as its edit reason prints it: "... that stay ({'backface_twin': 3}); ..."
_BY_RULE = re.compile(r"\((\{[^{}]*\})\)")
_COINCIDENT_DECIMALS = 6


# ------------------------------------------------------------------------------------------------- reading

def _json(path):
    return json.loads(Path(path).read_text(encoding='utf-8'))


def read_log(path):
    """`(edit lines, check records)` of an edit-log.jsonl."""
    edits, checks = [], []
    for raw in Path(path).read_text(encoding='utf-8').splitlines():
        if not raw.strip():
            continue
        line = json.loads(raw)
        (checks if 'check' in line else edits).append(line.get('check', line))
    return edits, checks


def _check_ids(ids, n, what):
    bad = [int(f) for f in ids if not 0 <= int(f) < n]
    if bad:
        raise ValueError(f'{what}: face ids out of range of the {n}-face model: {bad[:10]}')
    return sorted({int(f) for f in ids})


def stage_input_obj(audit):
    """The engine OBJ a stage audit names as its input: the E5 candidate, else the E3 candidate, else the baseline
    snapshot's before.engine.obj."""
    for key in ('e5_candidate', 'e3_candidate'):
        binding = audit.get(key)
        if binding:
            return Path(binding['candidate']) / 'candidate.engine.obj'
    snapshot = audit.get('before_snapshot')
    if not snapshot:
        raise ValueError('the stage audit names no input (no e5_candidate, e3_candidate or before_snapshot)')
    return Path(snapshot) / 'before.engine.obj'


def _rolled_back_details(checks):
    """site -> {reasons, stage_rolled_back} from the stage's check record(s)."""
    out = {}
    for check in checks:
        for row in check.get('rolled_back') or []:
            out[int(row['site'])] = {'reasons': dict(row.get('reasons') or {}),
                                     'stage_rolled_back': bool(row.get('stage_rolled_back', False))}
    return out


# ------------------------------------------------------------------------------------------- id mapping

class E5Map:
    """One remove-only stage: `survivors[i]` is the input id of output face i."""

    def __init__(self, survivors, n_in, n_out):
        self.survivors = [int(f) for f in survivors]
        if len(self.survivors) != n_out:
            raise ValueError(f'source-faces.json lists {len(self.survivors)} survivors, the output has {n_out} faces')
        _check_ids(self.survivors, n_in, 'source-faces.json survivors')
        self._fwd = {f: i for i, f in enumerate(self.survivors)}

    def forward(self, face):
        return [self._fwd[face]] if face in self._fwd else []

    def back(self, face_out):
        return self.survivors[face_out]


class E4Map:
    """One merge stage: kept source faces first (`kept_source_faces[i]` is the input id of output face i), then the
    kept regions' new triangles, each region mapping its source faces to its `new_triangles`."""

    def __init__(self, mapping, n_in, n_out):
        self.kept = [int(f) for f in mapping['kept_source_faces']]
        _check_ids(self.kept, n_in, 'region-map.json kept_source_faces')
        self._fwd = {f: [i] for i, f in enumerate(self.kept)}
        self._back = {}
        for region in mapping['regions']:
            source = _check_ids(region['source_faces'], n_in, f'region-map.json region {region["region"]} source_faces')
            new = _check_ids(region['new_triangles'], n_out, f'region-map.json region {region["region"]} new_triangles')
            for f in source:
                self._fwd[f] = list(new)
            for t in new:
                self._back[t] = None
        if len(self.kept) + len(self._back) != n_out:
            raise ValueError(f'region-map.json accounts for {len(self.kept) + len(self._back)} output faces, the output has {n_out}')

    def forward(self, face):
        return list(self._fwd.get(face, []))

    def back(self, face_out):
        return self.kept[face_out] if face_out < len(self.kept) else None


def map_back(faces, stages):
    """Input ids of the stage after `stages` carried back to the first stage's input ids."""
    out = set()
    for f in faces:
        for stage in reversed(stages):
            f = stage.back(f)
            if f is None:
                break
        if f is not None:
            out.add(int(f))
    return sorted(out)


def map_forward(faces, stages):
    """Input ids of `stages[0]` carried forward to the last stage's output ids (merged faces land on their region's
    new triangles; removed faces vanish)."""
    current = {int(f) for f in faces}
    for stage in stages:
        current = {t for f in current for t in stage.forward(f)}
    return sorted(current)


# ------------------------------------------------------------------------------------------------ E5 kinds

def _by_rule(line):
    found = _BY_RULE.search(line.get('reason') or '')
    if not found:
        return {}
    try:
        parsed = ast.literal_eval(found.group(1))
    except (ValueError, SyntaxError):
        return {}
    return {str(k): int(v) for k, v in parsed.items()} if isinstance(parsed, dict) else {}


def _coincidence_key(mesh, face):
    corners = mesh.positions[mesh.face_v[face]]
    return tuple(sorted(tuple(round(float(v), _COINCIDENT_DECIMALS) for v in p) for p in corners))


def classify_e5_removals(mesh, lines):
    """`{'backface_twin': [...], 'interior_seam': [...], 'unresolved': [...]}` from the kept (not rolled-back) E5 remove
    lines, see the module docstring for the mixed-site rule."""
    out = {'backface_twin': set(), 'interior_seam': set(), 'unresolved': []}
    for line in lines:
        if line.get('engine') != 'E5' or line.get('kind') != 'remove' or line.get('rolled_back'):
            continue
        faces = [int(f) for f in line['faces']]
        rules = _by_rule(line)
        if len(rules) == 1:
            (rule,) = rules
            if rule == 'backface_twin':
                out['backface_twin'].update(faces)
            elif rule == 'interior_twins':
                out['interior_seam'].update(faces)
            continue
        interior = set()
        if 'interior_twins' in rules:
            by_key = {}
            for f in faces:
                by_key.setdefault(_coincidence_key(mesh, f), []).append(f)
            interior = {f for group in by_key.values() if len(group) > 1 for f in group}
        rest = [f for f in faces if f not in interior]
        other_rules = [r for r in rules if r != 'interior_twins']
        if rest and len(other_rules) != 1:
            out['unresolved'].append({'site': int(line['site']), 'faces': faces, 'by_rule': rules})
            continue
        out['interior_seam'].update(interior)
        if rest and other_rules[0] == 'backface_twin':
            out['backface_twin'].update(rest)
    return {'backface_twin': sorted(out['backface_twin']), 'interior_seam': sorted(out['interior_seam']),
            'unresolved': out['unresolved']}


def e5_kinds(e5_dir, mesh_in, n_in):
    """`(faces by E5 kind in the E5 input's ids, details)`."""
    e5_dir = Path(e5_dir)
    audit = _json(e5_dir / 'stage-audit.json')
    lines, checks = read_log(e5_dir / 'edit-log.jsonl')
    removals = classify_e5_removals(mesh_in, lines)
    rolled_sites = _rolled_back_details(checks)
    faces = {'backface_twin': _check_ids(removals['backface_twin'], n_in, 'E5 backface_twin'),
             'interior_seam': _check_ids(removals['interior_seam'], n_in, 'E5 interior_seam')}
    report = audit.get('engine_report') or {}
    pairs = [row for row in report.get('kept_pairs') or [] if row.get('reason') == 'both_exposed']
    faces['two_sided_sheet'] = _check_ids([f for row in pairs for f in row['faces']], n_in, 'E5 kept_pairs')
    rolled, rolled_details = [], {}
    for line in lines:
        if line.get('engine') == 'E5' and line.get('rolled_back'):
            site = int(line['site'])
            for f in _check_ids(line['faces'], n_in, f'E5 rolled-back site {site}'):
                rolled.append(f)
                rolled_details[str(f)] = {'site': site, **rolled_sites.get(site, {'reasons': {}, 'stage_rolled_back': False})}
    faces['e5_rolled_back'] = sorted(set(rolled))
    details = {'e5_rolled_back': rolled_details}
    if removals['unresolved']:
        details['e5_unresolved'] = removals['unresolved']
    listed, total = len(report.get('kept_pairs') or []), report.get('kept_pairs_total')
    if total is not None and total > listed:
        details['two_sided_sheet_truncated'] = {'listed': listed, 'total': int(total)}
    return faces, details


# ------------------------------------------------------------------------------------------------ E4 kinds

def region_faces(mesh, flat_materials):
    """region id -> faces of the E4 input's coplanar regions, exactly as `E4Merge` numbers them (`e4_topology` at the
    profile's angles over the audit's `flat_materials`)."""
    profile = FixProfile()
    topo = analyse_topology_memo(mesh, frozenset(int(m) for m in flat_materials), coplanar_angle=profile.coplanar_angle,
                                 soft_angle=profile.soft_angle)
    out = {}
    for f, r in enumerate(topo.face_region.tolist()):
        if r >= 0:
            out.setdefault(int(r), []).append(int(f))
    return out


def e4_kinds(e4_dir, mesh_in, n_in, n_out):
    """`(before faces by E4 kind in the E4 input's ids, after faces in the E4 output's ids for merge_region, details,
    the E4Map)`."""
    e4_dir = Path(e4_dir)
    audit = _json(e4_dir / 'stage-audit.json')
    mapping = _json(e4_dir / 'region-map.json')
    lines, checks = read_log(e4_dir / 'edit-log.jsonl')
    stage = E4Map(mapping, n_in, n_out)
    faces = {'merge_region': sorted({f for r in mapping['regions'] for f in r['source_faces']})}
    after = {'merge_region': sorted({t for r in mapping['regions'] for t in r['new_triangles']})}
    report = audit.get('engine_report') or mapping.get('engine_report') or {}
    refused_rows = report.get('refused') or []
    refused, refused_details = [], {}
    if refused_rows:
        regions = region_faces(mesh_in, report.get('flat_materials') or [])
        for row in refused_rows:
            region = int(row['region'])
            if region not in regions:
                raise ValueError(f'refused region {region} is not a coplanar region of the E4 input')
            for f in _check_ids(regions[region], n_in, f'E4 refused region {region}'):
                refused.append(f)
                refused_details[str(f)] = str(row.get('reason'))
    faces['merge_refused'] = sorted(set(refused))
    rolled_sites = _rolled_back_details(checks)
    rolled, rolled_details = [], {}
    for line in lines:
        if line.get('engine') == 'E4' and line.get('rolled_back'):
            site = int(line['site'])
            for f in _check_ids(line['faces'], n_in, f'E4 rolled-back site {site}'):
                rolled.append(f)
                rolled_details[str(f)] = {'site': site, **rolled_sites.get(site, {'reasons': {}, 'stage_rolled_back': False})}
    faces['e4_rolled_back'] = sorted(set(rolled))
    return faces, after, {'merge_refused': refused_details, 'e4_rolled_back': rolled_details}, stage


# ----------------------------------------------------------------------------------------------- Jev kinds

def _jev_reason(row):
    state = row.get('state') or {}
    decision, provider = row.get('decision'), row.get('provider')
    if provider == 'rules' and decision == 'keep':
        if state.get('stair_material'):
            return 'stair material'
        return f'{state.get("stair_open_edges", 0)} open edge(s) on a stair material'
    if provider == 'rules' and decision == 'merge':
        return 'the merge kernel keeps the region\'s area'
    reason = f'rules could not say (merge_reason={state.get("merge_reason")})'
    suggestion = row.get('suggestion')
    if suggestion:
        reason += f'; {suggestion.get("provider")} suggests {suggestion.get("answer")} ({suggestion.get("confidence")})'
    return reason


def jev_kinds(judgement_path, n):
    """`(faces by jev kind in the judged mesh's ids, details)`: every face of each judged region, by decision."""
    judgement = _json(judgement_path)
    faces = {k: set() for k in JEV_KINDS}
    details = {}
    for row in judgement.get('regions') or []:
        decision = row.get('decision')
        kind = f'jev_{decision}'
        if kind not in faces:
            raise ValueError(f'crack judgement region {row.get("region")}: unknown decision {decision!r}')
        members = ((row.get('state') or {}).get('spot') or {}).get('faces') or row.get('crack_faces') or []
        members = _check_ids(members, n, f'crack judgement region {row.get("region")}')
        faces[kind].update(members)
        for f in members:
            details[str(f)] = {'provider': row.get('provider'), 'reason': _jev_reason(row)}
    return {k: sorted(v) for k, v in faces.items()}, {'jev': details}


# ------------------------------------------------------------------------------------------------- the docs

def census(mesh):
    from engine.detectors.errors import find_errors
    report = find_errors(mesh)
    return {k: sorted(int(f) for f in report['faces'].get(k, [])) for k in BASE_KINDS}


def compose(n_faces, stage_faces, details, *, existing=None, base=None, provenance=None):
    """The errors.json document: `existing` (a loaded errors.json, same n_faces) keeps its other kinds and keys,
    `base` (the census) sets the seven detector kinds, `stage_faces` set the stage kinds."""
    doc = dict(existing or {})
    if existing is not None and int(existing.get('n_faces', -1)) != n_faces:
        raise ValueError(f'--merge-into n_faces {existing.get("n_faces")} differs from the model\'s {n_faces}')
    faces = {k: v for k, v in (doc.get('faces') or {}).items() if k not in STAGE_KINDS}
    if base is not None:
        faces.update(base)
    faces.update({k: sorted(int(f) for f in v) for k, v in stage_faces.items()})
    for k, v in faces.items():
        _check_ids(v, n_faces, k)
    merged_details = {k: v for k, v in (doc.get('details') or {}).items()}
    merged_details.update(details)
    doc.update(schema_version=1, n_faces=int(n_faces), counts={k: len(v) for k, v in faces.items()}, faces=faces,
               details=merged_details)
    if provenance:
        doc['stage_errors'] = provenance
    return doc


def stage_errors(*, e5=None, e4=None, judgement=None, with_census=False, existing_before=None, existing_after=None):
    """`(before doc, after doc)`; see the module docstring."""
    if e5 is None and e4 is None:
        raise ValueError('give --e5 and/or --e4')
    chain, provenance = [], {}
    before_faces, after_faces, before_details, after_details = {}, {}, {}, {}
    before_obj = after_obj = None
    e5_map = e4_map = None
    if e5 is not None:
        e5 = Path(e5)
        audit = _json(e5 / 'stage-audit.json')
        before_obj = stage_input_obj(audit)
        e5_out = e5 / 'candidate.engine.obj'
        mesh_in = read_obj(before_obj)
        n_in, n_out = int(mesh_in.n_faces), int(read_obj(e5_out).n_faces)
        survivors = _json(e5 / 'source-faces.json')['source_faces']
        e5_map = E5Map(survivors, n_in, n_out)
        faces, details = e5_kinds(e5, mesh_in, n_in)
        before_faces.update(faces)
        before_details.update(details)
        for k, v in faces.items():
            after_faces[k] = map_forward(v, [e5_map])
        after_details['e5_rolled_back'] = {str(t): d for f, d in details['e5_rolled_back'].items()
                                           for t in e5_map.forward(int(f))}
        chain.append(e5_map)
        after_obj = e5_out
        provenance['e5'] = str(e5)
    if e4 is not None:
        e4 = Path(e4)
        audit = _json(e4 / 'stage-audit.json')
        e4_in = stage_input_obj(audit)
        if e5 is not None:
            named = (audit.get('e5_candidate') or {}).get('candidate')
            if named is None or Path(named).resolve() != e5.resolve():
                raise ValueError(f'the E4 audit\'s e5_candidate ({named}) is not the given E5 dir ({e5})')
            e4_in = after_obj
        mesh_in = read_obj(e4_in)
        e4_out = e4 / 'candidate.engine.obj'
        n_in, n_out = int(mesh_in.n_faces), int(read_obj(e4_out).n_faces)
        if e5_map is not None and len(e5_map.survivors) != n_in:
            raise ValueError(f'the E5 output has {len(e5_map.survivors)} faces, the E4 input {n_in}')
        faces, after_new, details, e4_map = e4_kinds(e4, mesh_in, n_in, n_out)
        for k, v in faces.items():
            before_faces[k] = map_back(v, chain)
        after_faces['merge_region'] = after_new['merge_region']
        for k in ('merge_refused', 'e4_rolled_back'):
            after_faces[k] = map_forward(faces[k], [e4_map])
        before_details['merge_refused'] = {str(map_back([int(f)], chain)[0]): r for f, r in details['merge_refused'].items()}
        after_details['merge_refused'] = {str(t): r for f, r in details['merge_refused'].items() for t in e4_map.forward(int(f))}
        before_details['e4_rolled_back'] = {str(map_back([int(f)], chain)[0]): d for f, d in details['e4_rolled_back'].items()}
        after_details['e4_rolled_back'] = {str(t): d for f, d in details['e4_rolled_back'].items() for t in e4_map.forward(int(f))}
        # the E5 kinds, carried through E4 as well
        for k in E5_KINDS:
            if k in after_faces:
                after_faces[k] = map_forward(after_faces[k], [e4_map])
        if 'e5_rolled_back' in after_details:
            after_details['e5_rolled_back'] = {str(t): d for f, d in after_details['e5_rolled_back'].items()
                                               for t in e4_map.forward(int(f))}
        if before_obj is None:
            before_obj = e4_in
        after_obj = e4_out
        chain.append(e4_map)
        provenance['e4'] = str(e4)
    if judgement is not None:
        # the judgement's ids are the E4 input's: after the E5 stage, before E4
        pre_e4 = [s for s in chain if isinstance(s, E5Map)]
        post = [s for s in chain if isinstance(s, E4Map)]
        n_judged = len(pre_e4[-1].survivors) if pre_e4 else int(read_obj(before_obj).n_faces)
        faces, details = jev_kinds(judgement, n_judged)
        for k, v in faces.items():
            before_faces[k] = map_back(v, pre_e4)
            after_faces[k] = map_forward(v, post)
        before_details['jev'] = {str(map_back([int(f)], pre_e4)[0]): d for f, d in details['jev'].items()}
        after_details['jev'] = {str(t): d for f, d in details['jev'].items() for t in map_forward([int(f)], post)}
        provenance['judgement'] = str(judgement)
    n_before, n_after = int(read_obj(before_obj).n_faces), int(read_obj(after_obj).n_faces)
    base_before = census(read_obj(before_obj)) if with_census else None
    base_after = census(read_obj(after_obj)) if with_census else None
    prov_before = dict(provenance, model=str(before_obj), side='before')
    prov_after = dict(provenance, model=str(after_obj), side='after')
    before = compose(n_before, before_faces, before_details, existing=existing_before, base=base_before, provenance=prov_before)
    after = compose(n_after, after_faces, after_details, existing=existing_after, base=base_after, provenance=prov_after)
    return before, after


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument('--e5', type=Path, default=None, help='the E5 run dir (<root>/e5/<F>)')
    parser.add_argument('--e4', type=Path, default=None, help='the E4 run dir (<root>/e4/<F>)')
    parser.add_argument('--judgement', type=Path, default=None, help='crack-judgement.json (main_infra_crack_judge.py)')
    parser.add_argument('--before-out', type=Path, required=True, help='errors.json for the BEFORE model')
    parser.add_argument('--after-out', type=Path, required=True, help='errors.json for the AFTER model')
    parser.add_argument('--merge-into-before', type=Path, default=None, help='an existing errors.json whose other kinds stay')
    parser.add_argument('--merge-into-after', type=Path, default=None, help='an existing errors.json whose other kinds stay')
    parser.add_argument('--with-census', action='store_true', help='also run find_errors on both models (the 7 base kinds)')
    args = parser.parse_args(argv)
    before, after = stage_errors(
        e5=args.e5, e4=args.e4, judgement=args.judgement, with_census=args.with_census,
        existing_before=None if args.merge_into_before is None else _json(args.merge_into_before),
        existing_after=None if args.merge_into_after is None else _json(args.merge_into_after))
    for out, doc in ((args.before_out, before), (args.after_out, after)):
        out.parent.mkdir(parents=True, exist_ok=True)
        out.write_text(json.dumps(doc, separators=(',', ':')), encoding='utf-8')
    print(json.dumps({'before': {'n_faces': before['n_faces'], 'counts': before['counts']},
                      'after': {'n_faces': after['n_faces'], 'counts': after['counts']}}))
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
