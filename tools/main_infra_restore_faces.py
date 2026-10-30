"""Restore named faces into a checked E5 candidate: the E5 survivors plus the faces the full Validator still sees.

When the full-floor Validator (128 directions, 24 cameras, probes) fails `textures` / `nothing_deleted` on a few
faces that E5's site judge called invisible, re-keeping exactly those faces is the smallest deterministic repair:
the result is still a pure subset of the checked E3 candidate (no new geometry), saved with the same
`save_survivor_pair` contract, so the strict guard and the Validator can measure it like any other candidate.

  python -m tools.main_infra_restore_faces --root <run root> --floor 4F --e5 <root>/e5/4F --faces 21504,34754,...
      --reason "Validator sites 1-2 of claude-e5-48232" --out <root>/e5/4F-restore1

`--faces` are ORIGINAL (baseline) face ids as the Validator reports them; they must be E3 survivors absent from the
E5 output. Writes candidate.engine.obj / candidate.source.obj / source-faces.json / edit-log.jsonl (E5's log plus one
`restore` record) / stage-audit.json (E5's audit with `restored_faces`, fresh hashes) and the assets.
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
from tools.main_infra_physical_validation import _hash, _same_mesh


def restore(root: Path, floor: str, e5: Path, faces: list[int], reason: str, out: Path) -> dict:
    root, e5, out = root.resolve(), e5.resolve(), out.resolve()
    if out.exists():
        raise ValueError('output exists; refusing overwrite')
    e5_audit = json.loads((e5 / 'stage-audit.json').read_text(encoding='utf-8'))
    if e5_audit.get('cleanup_mode') != 'e3_then_e5_cull':
        raise ValueError('restore needs a checked E5 candidate built from the checked E3 candidate')
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
    e3_map = json.loads((e3_dir / 'source-faces.json').read_text(encoding='utf-8'))['source_faces']  # E3 index -> original id
    original_to_e3 = {orig: i for i, orig in enumerate(e3_map)}
    e5_survivors = json.loads((e5 / 'source-faces.json').read_text(encoding='utf-8'))['source_faces']  # E3 indices
    kept = set(int(i) for i in e5_survivors)
    restored_e3, missing, already = [], [], []
    for orig in sorted(set(int(f) for f in faces)):
        if orig not in original_to_e3:
            missing.append(orig)
        elif original_to_e3[orig] in kept:
            already.append(orig)
        else:
            restored_e3.append(original_to_e3[orig])
    if missing:
        raise ValueError(f'faces not in the E3 candidate (E3 removed them): {missing}')
    if not restored_e3:
        raise ValueError(f'nothing to restore; all faces already kept: {already}')
    indices = sorted(kept | set(restored_e3))
    eng, src, mapping = save_survivor_pair(engine_floor, source_floor, indices, out)
    for asset in provenance['assets']:
        target = out / asset['path']
        target.parent.mkdir(parents=True, exist_ok=True)
        copy_verified(base / asset['path'], target, interval_s=0)
    shutil.copyfile(e5 / 'edit-log.jsonl', out / 'edit-log.jsonl')
    record = dict(kind='restore', stage='E5-restore', faces_e3_index=restored_e3,
                  faces_original=[e3_map[i] for i in restored_e3], already_kept_original=already, reason=reason,
                  source_e5_candidate=str(e5), recorded_utc=time.strftime('%Y-%m-%dT%H:%M:%SZ', time.gmtime()))
    with (out / 'edit-log.jsonl').open('a', encoding='utf-8') as stream:
        stream.write(json.dumps(record) + '\n')
    audit = dict(e5_audit)
    audit.update(cleanup_mode='e3_then_e5_cull', executed_stages=list(e5_audit.get('executed_stages', ['E3', 'E5'])) + ['E5-restore'],
                 output_triangles=len(indices), restored_faces=record,
                 restored_from=dict(candidate=str(e5), engine_candidate_sha256=e5_audit['engine_candidate_sha256'],
                                    stage_audit_sha256=sha256_file(e5 / 'stage-audit.json')),
                 engine_candidate_sha256=sha256_file(eng), source_candidate_sha256=sha256_file(src),
                 source_faces_sha256=sha256_file(mapping), edit_log_sha256=sha256_file(out / 'edit-log.jsonl'),
                 guard=dict(passed=False, state='pending'), independent_validation='pending', accepted=False,
                 independent_guard_receipt=None)
    (out / 'stage-audit.json').write_text(json.dumps(audit, indent=2), encoding='utf-8')
    return dict(out=str(out), input_e5_triangles=e5_audit['output_triangles'], output_triangles=len(indices),
                restored=len(restored_e3), restored_original=record['faces_original'], already_kept=already)


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument('--root', type=Path, required=True)
    parser.add_argument('--floor', required=True)
    parser.add_argument('--e5', type=Path, required=True)
    parser.add_argument('--faces', required=True, help='comma-separated ORIGINAL face ids')
    parser.add_argument('--reason', required=True)
    parser.add_argument('--out', type=Path, required=True)
    args = parser.parse_args(argv)
    faces = [int(f) for f in args.faces.split(',') if f.strip()]
    print(json.dumps(restore(args.root, args.floor, args.e5, faces, args.reason, args.out)))
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
