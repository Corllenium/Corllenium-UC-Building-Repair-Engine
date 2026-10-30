"""Drop the owner-authorized orange marker faces from a checked E5 candidate.

The source scans carry two orange 1-block registration cubes (24 faces) per floor. The owner authorized deleting them
on every floor (approved-selection.json, 2026-10-26), but no pipeline stage removes them, so they pass through E3 and
E5 into the published model. The result is a pure subset of the checked E3 candidate, saved with the same
`save_survivor_pair` contract as `main_infra_restore_faces`. Measure it with `--drop-before-faces` so the guard and the
Validator judge it against a BEFORE without those faces.

  python -m tools.main_infra_drop_markers --root <run root> --floor 7F --e5 <root>/e5/7F
      --selection docs/superpowers/records/MAIN-INFRA-ORANGE-BOX-CLEANUP-20261026/approved-selection.json
      --out <root>/e5/7F-drop-markers
"""
from __future__ import annotations

import argparse
import json
import shutil
import time
from pathlib import Path

from engine.io.minecraft_floor import Frame
from engine.io.obj_reader import read_obj
from engine.io.snapshot import copy_verified, sha256_file
from tools.main_infra_e3 import save_survivor_pair
from tools.main_infra_e4 import floor_from_candidate
from tools.main_infra_external_validate import orange_face_ids
from tools.main_infra_physical_validation import _hash, _same_mesh


def split_markers(survivors: list[int], e3_map: list[int], marker_ids: list[int]) -> tuple[list[int], list[int]]:
    """Survivors (E3 indices) without the marker faces (original ids), and the dropped ones. All markers must be present."""
    wanted = set(marker_ids)
    kept, dropped = [], []
    for index in survivors:
        (dropped if e3_map[index] in wanted else kept).append(index)
    missing = sorted(wanted - {e3_map[index] for index in dropped})
    if missing:
        raise ValueError(f'marker faces not in the candidate: {missing}')
    return kept, dropped


def drop(root: Path, floor: str, e5: Path, selection: Path, out: Path) -> dict:
    root, e5, out = root.resolve(), e5.resolve(), out.resolve()
    if out.exists():
        raise ValueError('output exists; refusing overwrite')
    e5_audit = json.loads((e5 / 'stage-audit.json').read_text(encoding='utf-8'))
    if e5_audit.get('cleanup_mode') != 'e3_then_e5_cull':
        raise ValueError('needs a checked E5 candidate built from the checked E3 candidate')
    e3_dir = Path(e5_audit['e3_candidate']['candidate'])
    _hash(e3_dir / 'candidate.engine.obj', e5_audit['e3_candidate']['engine_candidate_sha256'])
    _hash(e3_dir / 'candidate.source.obj', e5_audit['e3_candidate']['source_candidate_sha256'])
    _hash(e5 / 'candidate.engine.obj', e5_audit['engine_candidate_sha256'])
    _hash(e5 / 'source-faces.json', e5_audit['source_faces_sha256'])
    base = root / 'normalized' / floor
    provenance = json.loads((base / 'geometry-provenance.json').read_text(encoding='utf-8'))
    frame = Frame(1000 / 25.4, provenance['frame_evidence'])
    source_floor = floor_from_candidate(e3_dir / 'candidate.source.obj')
    engine_floor = source_floor.in_frame(frame)
    _same_mesh(read_obj(e3_dir / 'candidate.engine.obj'), engine_floor.mesh)
    e3_map = json.loads((e3_dir / 'source-faces.json').read_text(encoding='utf-8'))['source_faces']
    survivors = [int(i) for i in json.loads((e5 / 'source-faces.json').read_text(encoding='utf-8'))['source_faces']]
    kept, dropped = split_markers(survivors, e3_map, orange_face_ids(selection, floor))
    indices = sorted(kept)
    eng, src, mapping = save_survivor_pair(engine_floor, source_floor, indices, out)
    for asset in provenance['assets']:
        target = out / asset['path']
        target.parent.mkdir(parents=True, exist_ok=True)
        copy_verified(base / asset['path'], target, interval_s=0)
    shutil.copyfile(e5 / 'edit-log.jsonl', out / 'edit-log.jsonl')
    record = dict(kind='drop_markers', stage='E5-drop-markers', faces_e3_index=dropped, faces_original=[e3_map[i] for i in dropped],
                  selection_sha256=sha256_file(selection), reason='owner-authorized orange marker faces (2026-10-26)',
                  source_e5_candidate=str(e5), recorded_utc=time.strftime('%Y-%m-%dT%H:%M:%SZ', time.gmtime()))
    with (out / 'edit-log.jsonl').open('a', encoding='utf-8') as stream:
        stream.write(json.dumps(record) + '\n')
    audit = dict(e5_audit)
    audit.update(executed_stages=list(e5_audit.get('executed_stages', ['E3', 'E5'])) + ['E5-drop-markers'],
                 output_triangles=len(indices), dropped_markers=record,
                 dropped_from=dict(candidate=str(e5), engine_candidate_sha256=e5_audit['engine_candidate_sha256'],
                                   stage_audit_sha256=sha256_file(e5 / 'stage-audit.json')),
                 engine_candidate_sha256=sha256_file(eng), source_candidate_sha256=sha256_file(src),
                 source_faces_sha256=sha256_file(mapping), edit_log_sha256=sha256_file(out / 'edit-log.jsonl'),
                 guard=dict(passed=False, state='pending'), independent_validation='pending', accepted=False,
                 independent_guard_receipt=None)
    (out / 'stage-audit.json').write_text(json.dumps(audit, indent=2), encoding='utf-8')
    return dict(out=str(out), input_triangles=len(survivors), output_triangles=len(indices), dropped=len(dropped))


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument('--root', type=Path, required=True)
    parser.add_argument('--floor', required=True)
    parser.add_argument('--e5', type=Path, required=True)
    parser.add_argument('--selection', type=Path, required=True)
    parser.add_argument('--out', type=Path, required=True)
    args = parser.parse_args(argv)
    print(json.dumps(drop(args.root, args.floor, args.e5, args.selection, args.out)))
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
