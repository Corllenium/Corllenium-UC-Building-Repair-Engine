import json
import os
from pathlib import Path
import subprocess
import sys
import time
from datetime import datetime, timezone

from engine.io.mtl import parse_mtl, texture_flatness
from engine.io.snapshot import copy_verified, sha256_file, snapshot_object
from engine.validate.checks import load_looks
from tools.main_infra_e3 import load_qualified_floor, run_checked_e3, save_survivor_pair

floor = sys.argv[1]
if floor not in ('2F', '3F'):
    raise ValueError('this owned job covers only floors 2 and 3')
root = Path.cwd()
imports = root / 'data/main-infra-fresh/import-2f-3f-20261023'
run = root / 'data/main-infra-e3/run-20261023-attempt2'
run.mkdir(parents=True, exist_ok=True)
qualifiers = root / 'data/main-infra-e3/run-20261023/independent-validator/import-2F3F-audit'
materials = Path(sys.argv[2]).resolve()
candidate = run / floor
worker = run / f'worker-{floor}.json'
if candidate.exists() or worker.exists():
    raise ValueError('existing run output; refusing overwrite')
started = time.perf_counter()
stamp = lambda: datetime.now(timezone.utc).isoformat()
state = dict(pid=os.getpid(), floor_id=floor, state='loading_qualified_input',
             started_at=stamp(), candidate=str(candidate.resolve()), accepted=False)
def status(**fields):
    state.update(fields, updated_at=stamp())
    tmp = worker.with_suffix('.json.tmp')
    tmp.write_text(json.dumps(state, indent=2), encoding='utf-8')
    tmp.replace(worker)
    print(json.dumps(state), flush=True)
status()
try:
    ordinal = {'2F': '2nd', '3F': '3rd'}[floor]
    raw = imports / 'raw' / f'{ordinal} floor main infra.obj'
    baseline = imports / 'normalized' / floor
    source, engine, before, receipt = load_qualified_floor(
        raw=raw, reference=imports / 'reference' / f'{floor}.json', baseline=baseline,
        qualification=qualifiers / f'qualification-{floor}.json')
    if receipt['floor_id'] != floor:
        raise ValueError('qualification floor differs from claimed floor')
    expected_qualifier = {'2F': 'f37cac1ec1842f324409802e67a424b3a7864783f5b52143dc5c7f4a7697069c',
                          '3F': '5e1880c494bb4fa532a1d50bce5515d20cc02e532d82c5e55db69e59a83a7424'}[floor]
    if (receipt['source_revision'] != '7b2f7451b5723f724a1e074fdedc07dbcf7291d330ae550066f4926886136511'
            or receipt['qualification_sha256'] != expected_qualifier
            or json.loads((qualifiers / f'qualification-{floor}.json').read_text(encoding='utf-8'))['job_id'] != 'MAIN-INFRA-CLEAN-20261023'):
        raise ValueError('qualification is outside the approved source revision/job')
    mtls = parse_mtl(baseline / before.mtllib)
    looks = load_looks(materials, [(mtls, baseline)])
    if looks.unknown(before):
        raise ValueError('material namespace does not cover this floor')
    flatness = {name: texture_flatness(baseline / material.map_kd)
                for name, material in mtls.items() if material.map_kd}
    snapshot = snapshot_object(baseline / 'before.engine.obj', run / 'before-snapshots' / floor,
                               expected_tris=before.n_faces, interval_s=0)
    commit = subprocess.check_output(['git', 'rev-parse', 'HEAD'], text=True).strip()
    if commit != '531769cad83dd6d03214a94cbd21e0209f8f2f33':
        raise ValueError('indexed execution component differs from reviewed commit')
    status(state='running_checked_E3', input_triangles=before.n_faces,
           builder_component_commit=commit, input_receipt=receipt,
           materials_sha256=sha256_file(materials), before_snapshot=str(snapshot.dir.resolve()))
    outcome, indices = run_checked_e3(before, looks, flatness)
    engine_path, source_path, mapping = save_survivor_pair(engine, source, indices, candidate)
    for row in receipt['assets']:
        rel = Path(row['path'])
        dst = candidate / rel
        dst.parent.mkdir(parents=True, exist_ok=True)
        copy_verified(baseline / rel, dst, interval_s=0)
        if sha256_file(dst) != row['sha256']:
            raise ValueError('copied candidate asset differs')
    edit_log = candidate / 'edit-log.jsonl'
    edit_log.write_text(''.join(json.dumps(row) + '\n' for row in outcome.records), encoding='utf-8')
    audit = dict(cleanup_mode='e3_remove_only', executed_stages=['E3'], checks=outcome.checks,
        input_triangles=before.n_faces, output_triangles=len(indices),
        kept_edits=len(outcome.kept), rolled_back_edits=len(outcome.rolled_back),
        engine_candidate_sha256=sha256_file(engine_path), source_candidate_sha256=sha256_file(source_path),
        source_faces_sha256=sha256_file(mapping), edit_log_sha256=sha256_file(edit_log),
        qualification_sha256=receipt['qualification_sha256'], assets=receipt['assets'],
        before_snapshot=str(snapshot.dir.resolve()), input_receipt=receipt,
        materials_sha256=sha256_file(materials), builder_component_commit=commit,
        guard=dict(passed=False, state='independent strict guard pending'),
        independent_validation='pending', accepted=False, wall_s=round(time.perf_counter()-started,2),
        engine_candidate=str(engine_path.resolve()), source_candidate=str(source_path.resolve()))
    (candidate / 'stage-audit.json').write_text(json.dumps(audit, indent=2), encoding='utf-8')
    status(state='candidate_saved', output_triangles=len(indices),
           wall_s=audit['wall_s'], checks=outcome.checks)
except BaseException as error:
    status(state='failed', error_type=type(error).__name__, error=str(error),
           wall_s=round(time.perf_counter()-started,2))
    raise
