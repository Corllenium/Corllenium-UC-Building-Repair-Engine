"""Run Codex's checked E3 recipe (E3 branch code) on one of Claude's qualified fresh floors.

Usage (cwd = the E3 worktree so its engine code imports; PYTHONPATH = that worktree):
  python -B -u tools/run_checked_e3_floor.py --root <claude run root> --floor 7F --raw-name "7th floor main infra.obj"
Inputs come from Claude's run root (raw, reference, normalized, qualification, materials, duplicate-only candidate);
output goes to <root>/e3/<floor>/ and must not exist. Mirrors the 1F script Codex ran on 2026-10-23 17:40 +08.
"""
import argparse, json, os, time
from pathlib import Path
from engine.io.minecraft_floor import parse_floor, Frame
from engine.io.mtl import parse_mtl, texture_flatness
from engine.io.snapshot import sha256_file, copy_verified
from engine.repair.kernel import write_records
from engine.validate.checks import load_looks
from tools.main_infra_physical_validation import load_physical_pair
from tools.main_infra_e3 import run_checked_e3, save_survivor_pair

parser = argparse.ArgumentParser()
parser.add_argument('--root', type=Path, required=True)
parser.add_argument('--floor', required=True)
parser.add_argument('--raw-name', required=True)
args = parser.parse_args()
root = args.root.resolve()
F = args.floor
out = root / 'e3' / F
if out.exists():
    raise ValueError('Refusing existing attempt output')
raw = root / 'raw' / args.raw_name
reference = root / 'reference' / f'{F}.json'
qualification = root / 'independent-validator' / 'import-audit' / f'qualification-{F}.json'
base = root / 'normalized' / F
materials = root / 'independent-validator' / 'preflight' / f'materials-{F}.json'
before, _, receipt = load_physical_pair(raw=raw, reference=reference, baseline=base, qualification=qualification, candidate=root / 'candidates' / F)
native = json.loads(reference.read_text())
source = parse_floor(raw.read_text(encoding='utf-8'), triangulations={int(k): v for k, v in native['polygons'].items()})
provenance = json.loads((base / 'geometry-provenance.json').read_text())
engine_floor = source.in_frame(Frame(1000 / 25.4, provenance['frame_evidence']))
mtl = parse_mtl(base / source.mesh.mtllib)
looks = load_looks(materials, [(mtl, base)])
flatness = {name: texture_flatness(base / mat.map_kd.replace(chr(92), '/')) for name, mat in mtl.items() if mat.map_kd}
out.parent.mkdir(parents=True, exist_ok=True)
progress = out.parent / f'worker-{F}.json'
progress.write_text(json.dumps(dict(pid=os.getpid(), state='running', stage='checked E3 repair', input_triangles=before.n_faces, started=time.time(), candidate=str(out)), indent=2))
print(f'ENGINE E3 starting on fresh {F}: {before.n_faces} triangles; site checks and rollback enabled', flush=True)
started = time.perf_counter()
outcome, indices = run_checked_e3(before, looks, flatness)
print(f'ENGINE E3 finished: {before.n_faces}->{outcome.mesh.n_faces}; kept edits={len(outcome.kept)}, rolled back={len(outcome.rolled_back)}; checks={outcome.checks}', flush=True)
eng, src, mapping = save_survivor_pair(engine_floor, source, indices, out)
for asset in provenance['assets']:
    target = out / asset['path']
    target.parent.mkdir(parents=True, exist_ok=True)
    copy_verified(base / asset['path'], target, interval_s=0)
write_records(out / 'edit-log.jsonl', outcome.records)
audit = dict(cleanup_mode='e3_remove_only', executed_stages=['E3'], checks=outcome.checks, input_triangles=before.n_faces,
             output_triangles=outcome.mesh.n_faces, kept_edits=len(outcome.kept), rolled_back_edits=len(outcome.rolled_back),
             engine_candidate_sha256=sha256_file(eng), source_candidate_sha256=sha256_file(src), source_faces_sha256=sha256_file(mapping),
             edit_log_sha256=sha256_file(out / 'edit-log.jsonl'), qualification_sha256=sha256_file(qualification), assets=provenance['assets'],
             before_snapshot=str(Path(receipt['before']).parent), input_receipt=receipt, guard=dict(passed=False, state='pending'),
             independent_validation='pending', accepted=False, wall_s=round(time.perf_counter() - started, 2))
(out / 'stage-audit.json').write_text(json.dumps(audit, indent=2), encoding='utf-8')
progress.write_text(json.dumps(dict(pid=os.getpid(), state='candidate_saved', input_triangles=before.n_faces, output_triangles=outcome.mesh.n_faces, wall_s=audit['wall_s'], checks=outcome.checks, candidate=str(out)), indent=2))
print(json.dumps({k: audit[k] for k in ('input_triangles', 'output_triangles', 'kept_edits', 'rolled_back_edits', 'wall_s')}), flush=True)
