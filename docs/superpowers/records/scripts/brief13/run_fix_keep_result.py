"""Run `python -m engine.cli fix` exactly as the CLI does, and keep the in-memory FixResult.

Usage (repo root as cwd and PYTHONPATH): run_fix_keep_result.py <snapshot dir> <out root> <skp dir>
       <pickle path>

`engine.cli.fix_object` is wrapped so the FixResult the CLI builds its report from is pickled
beside the CLI's own outputs -- one run gives both the report.json and exact arrays to measure."""
import pickle
import sys
import time

import engine.cli as cli

snap, out, skp_dir, pkl = sys.argv[1:5]
captured = {}
real = cli.fix_object


def spy(mesh, flatness, profile):
    result = real(mesh, flatness, profile)
    captured.update(result=result, input=mesh, flatness=flatness, profile=profile)
    return result


cli.fix_object = spy
start = time.time()
rc = cli.main(["fix", snap, "--out", out, "--skp-dir", skp_dir])
print(f"rc={rc} seconds={time.time() - start:.0f}")
with open(pkl, "wb") as fh:
    pickle.dump(captured, fh)
print(f"pickled {pkl}")
