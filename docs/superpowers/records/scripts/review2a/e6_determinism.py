import hashlib, json, tempfile
from pathlib import Path
import engine.cli as cli
from engine.fixes.pipeline import FixProfile
from engine.tests.fixtures.build import slab_with_infill_patch, slab_with_strays
from engine.tests.test_cli import _write_snapshot

def strip(o):
    if isinstance(o, dict):
        return {k: strip(v) for k, v in o.items() if "runtime" not in k}
    if isinstance(o, list):
        return [strip(v) for v in o]
    return o

for build in (slab_with_strays, slab_with_infill_patch):
    digests = []
    with tempfile.TemporaryDirectory() as d:
        d = Path(d)
        m = build()
        snap = _write_snapshot(d, m)
        for run in range(2):
            out = d / f"out{run}"
            code = cli.cmd_fix(snap, out, accept_slit=False,
                               profile=FixProfile(guard_size=(120, 80), n_dirs=32, qa_size=(160, 100)),
                               solidify=True, skp=False)
            rep = json.loads((out / m.name / "report.json").read_text(encoding="utf-8"))
            obj = (out / m.name / f"{m.name}.fixed.obj").read_bytes()
            digests.append((code, hashlib.sha256(json.dumps(strip(rep), sort_keys=True).encode()).hexdigest()[:16],
                            hashlib.sha256(obj).hexdigest()[:16], len(rep.get("fragment_removals", []))))
    print(build.__name__, digests, "identical:", digests[0] == digests[1])
