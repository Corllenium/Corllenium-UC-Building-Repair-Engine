"""Judge the Validator's cracks by coplanar region before E4 merges them (MAIN-INFRA-E4-MERGE-20261023).

Given the mesh and the crack face set (`errors.json`'s `{"faces": {"cracks": [...]}}`, or the Validator's crack
sites' faces), the crack faces are grouped by the coplanar region E4 will merge (`e4_topology`, the same region ids
`E4Merge` uses), and the Decider is asked ONE `choice` question per region, `crack.region`:
"flat panel with slits -- merge" / "real opening, step or stair -- keep" / "unsure -- owner".

The question's state is the region's `_spot`-style summary (centre, size, faces: `engine.detectors.errors._spot`)
plus its 2D outline (extent in the region plane), material, areas, open-edge counts and what the merge kernel would do
to it. There is no renderer here: the state is text, which is what the Decider keys and logs.

The deterministic rule (`crack_rule`, provider `rules`, confidence 1.0) decides first:
- `keep` when the region's material is a stair material (name matches `STAIR_PATTERN`) or any open edge of the region
  lies on a stair material (both its ends are vertices of a stair-material face);
- `merge` when the merge kernel keeps the region's area (and passes E4's other region rules);
- otherwise the rules cannot say (None): Jev, when a key is available, may SUGGEST; in `suggest` mode (the default,
  AGENTS.md: rules first, a model never bypasses them) that suggestion is recorded and the region goes to the owner
  as `unsure`. The judgement records the provider of every decision.

Output (`crack-judgement.json`): `regions` (one row per region with cracks: region, material, crack faces, decision,
provider, confidence, suggestion, state), `merge` / `keep` / `unsure` (region ids), `unassigned_faces` (crack faces
in no region: E4 cannot merge them), `decider` (providers, jev on/off). `E4Merge(allowed_regions=judgement["merge"])`
then merges only those regions (`run_checked_e4_floor.py --crack-judgement`).
"""
import argparse
import json
import re
import sys
from pathlib import Path

import numpy as np

from engine.decide.decider import Decider, Question, QuestionType, RuleProvider
from engine.detectors.errors import _spot
from engine.fixes.pipeline import FixProfile
from engine.repair.engines import e4_merge
from engine.repair.engines.e4_merge import e4_topology, region_changes
from engine.topo.edges import EDGE_OPEN
from engine.topo.planes import plane_basis

QTYPE = 'crack.region'
CRACK_REGION = QuestionType(
    QTYPE, 'choice',
    'A fresh Minecraft floor export cut this flat coplanar surface into slivers with T-junctions; the Validator '
    'reports cracks (diagonal slits) on it. Should the engine re-triangulate the whole region as one clean surface '
    'over its existing vertices (merge), or is the slit a real opening, step or stair edge that must stay (keep)?',
    (('merge', 'flat panel with slits -- merge'), ('keep', 'real opening, step or stair -- keep'),
     ('unsure', 'unsure -- owner')))
STAIR_PATTERN = re.compile(r'stair|step', re.IGNORECASE)
_RULE_REASONS_OK = (None, 'unchanged', 'not_allowed')


def crack_rule(q: Question):
    """The deterministic answer, or None when the rules cannot say."""
    s = q.state
    if s.get('stair_material') or s.get('stair_open_edges', 0) > 0:
        return 'keep'
    if s.get('area_preserved') and s.get('merge_reason') in _RULE_REASONS_OK:
        return 'merge'
    return None


def build_decider(decide_dir, *, jev=None):
    """A Decider over `CRACK_REGION`: the rules, then Jev when `jev` (a JevDecider / RemoteDecider) is given."""
    from engine.decide.providers import AskProvider
    decide_dir = Path(decide_dir)
    decide_dir.mkdir(parents=True, exist_ok=True)
    providers = [RuleProvider({QTYPE: crack_rule})]
    if jev is not None:
        providers.append(AskProvider('jev', jev))
    return Decider([CRACK_REGION], providers, log_path=decide_dir / 'crack-decide-log.jsonl',
                   cache_path=decide_dir / 'crack-decide-cache.jsonl')


def region_states(mesh, crack_faces, *, flatness, profile=FixProfile(), stair_pattern=STAIR_PATTERN):
    """`(states, unassigned)`: one state dict per coplanar region holding a crack face (ascending region id), and the
    crack faces in no region."""
    flat, topo = e4_topology(mesh, flatness, profile)
    result = e4_merge.merge_regions(mesh, topo, flat)      # the very kernel E4 runs (and tests patch)
    changes = {c.region: c for c in region_changes(mesh, topo, result, flat)}
    stair_materials = {i for i, name in enumerate(mesh.materials) if stair_pattern.search(name)}
    stair_faces = np.isin(mesh.face_material, sorted(stair_materials))
    stair_vertices = set(topo.face_w[stair_faces].ravel().tolist()) if stair_faces.any() else set()
    open_edge = np.asarray(topo.edge_class) == EDGE_OPEN
    fe = topo.table.face_edges
    pos = topo.positions_w
    tri = pos[topo.face_w]
    area = 0.5 * np.linalg.norm(np.cross(tri[:, 1] - tri[:, 0], tri[:, 2] - tri[:, 0]), axis=1)
    region_of = np.asarray(topo.face_region)

    by_region, unassigned = {}, []
    for f in sorted({int(f) for f in crack_faces}):
        if not 0 <= f < mesh.n_faces or region_of[f] < 0:
            unassigned.append(f)
            continue
        by_region.setdefault(int(region_of[f]), []).append(f)
    states = []
    for region in sorted(by_region):
        members = np.flatnonzero(region_of == region)
        material = int(mesh.face_material[members[0]])
        name = None if material < 0 else mesh.materials[material]
        edges = fe[members]
        edges = edges[edges >= 0]
        open_rows = np.unique(edges[open_edge[edges]])
        ends = topo.table.edges[open_rows] if len(open_rows) else np.zeros((0, 2), np.int64)
        stair_open = int(sum(1 for a, b in ends.tolist() if a in stair_vertices and b in stair_vertices))
        corners = tri[members].reshape(-1, 3)
        normal = np.cross(tri[members, 1] - tri[members, 0], tri[members, 2] - tri[members, 0]).sum(axis=0)
        length = float(np.linalg.norm(normal))
        outline = None
        if length > 0:
            e1, e2 = plane_basis(normal / length)
            centre = corners.mean(axis=0)
            xy = np.column_stack([(corners - centre) @ e1, (corners - centre) @ e2])
            outline = {'normal': [round(float(v), 6) for v in normal / length],
                       'extent': [round(float(v), 3) for v in np.ptp(xy, axis=0)]}
        change = changes.get(region)
        states.append({
            'region': region, 'material': name, 'crack_faces': by_region[region],
            'region_faces': int(len(members)), 'area': round(float(area[members].sum()), 4),
            'open_edges': int(len(open_rows)), 'stair_open_edges': stair_open,
            'stair_material': material in stair_materials,
            'merge_reason': None if change is None else change.reason,
            'merge_faces_after': None if change is None else int(len(change.rows)),
            'area_preserved': bool(change is not None and change.reason not in
                                   ('area_changed', 'off_plane', 'flipped', 'uv_lost', 'uv_seam', 'too_large',
                                    'mixed_material')),
            'spot': _spot(f'cracks ({len(by_region[region])} faces) in region {region}', corners,
                          float(area[members].sum()), members.tolist()),
            'outline': outline})
    return states, unassigned


def judge_cracks(mesh, crack_faces, *, flatness, decider, profile=FixProfile(), stair_pattern=STAIR_PATTERN):
    """The crack judgement (see the module docstring)."""
    states, unassigned = region_states(mesh, crack_faces, flatness=flatness, profile=profile,
                                       stair_pattern=stair_pattern)
    questions = [Question(QTYPE, f'region-{s["region"]}', s) for s in states]
    answers = decider.ask(questions) if questions else []
    rows, buckets = [], {'merge': [], 'keep': [], 'unsure': []}
    for state, answer in zip(states, answers):
        decision = answer.answer if answer.accepted and answer.answer in buckets else 'unsure'
        rows.append({'region': state['region'], 'material': state['material'], 'crack_faces': state['crack_faces'],
                     'region_faces': state['region_faces'], 'decision': decision, 'provider': answer.provider,
                     'confidence': float(answer.confidence), 'suggestion': answer.suggestion, 'state': state})
        buckets[decision].append(state['region'])
    providers = [p.name for p in getattr(decider, '_providers', [])]
    return {'qtype': QTYPE, 'regions': rows, **buckets, 'unassigned_faces': unassigned,
            'decider': {'providers': providers, 'jev': 'on' if 'jev' in providers else 'off'}}


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--before', type=Path, required=True, help='the engine-frame BEFORE mesh (OBJ)')
    parser.add_argument('--errors', type=Path, required=True, help='errors.json with faces.cracks')
    parser.add_argument('--out', type=Path, required=True, help='crack-judgement.json to write (must not exist)')
    parser.add_argument('--flatness', type=Path, default=None, help='json {material: texture std}')
    parser.add_argument('--decide-dir', type=Path, default=None, help='where the Decider log and cache go')
    parser.add_argument('--jev', action='store_true', help='also ask Jev (a suggestion only, in suggest mode)')
    args = parser.parse_args(argv)
    if args.out.exists():
        raise ValueError('crack judgement output exists; refusing overwrite')
    from engine.io.obj_reader import read_obj
    mesh = read_obj(args.before)
    errors = json.loads(args.errors.read_text(encoding='utf-8'))
    cracks = errors.get('faces', {}).get('cracks', [])
    flatness = {} if args.flatness is None else json.loads(args.flatness.read_text(encoding='utf-8'))
    jev = None
    if args.jev:
        from engine.decide.jev import JevDecider
        jev = JevDecider()
        if not jev.available:
            jev = None
    decider = build_decider(args.decide_dir or args.out.parent / 'decide', jev=jev)
    judgement = judge_cracks(mesh, cracks, flatness=flatness, decider=decider)
    judgement['inputs'] = {'before': str(args.before), 'errors': str(args.errors), 'crack_faces': len(cracks)}
    args.out.parent.mkdir(parents=True, exist_ok=True)
    args.out.write_text(json.dumps(judgement, indent=2), encoding='utf-8')
    print(json.dumps({k: len(judgement[k]) for k in ('merge', 'keep', 'unsure', 'unassigned_faces')}), flush=True)
    return 0


if __name__ == '__main__':
    sys.exit(main())
