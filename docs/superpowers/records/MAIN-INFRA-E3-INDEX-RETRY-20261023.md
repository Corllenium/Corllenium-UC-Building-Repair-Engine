# Main Infrastructure E3: indexed sequential retry preparation

The original 2F/3F checked runs did not save candidates. At 12:20:17 UTC on
2026-10-23, 1F E7, 2F E3 and 3F E3 all failed allocations within 0.105 seconds.
Windows Resource-Exhaustion-Detector Operational Event 1003 recorded system
commit 67,057,364,992 / 67,303,272,448 bytes at 12:20:17.9077837 UTC (99.63%).
The failed receipts, logs and source packages remain intact. No first-check
verdict or partial geometry is an accepted or saved result.

This execution component ports only the independently reviewed finite ray index
from ff3e8e5c199e52a831865ecce086d581950a802a to the fec7b3e qualified-input
execution tree. Its complete implementation is in engine/rays/caster.py. The
existing first_hit/any_hit/all_hits, _face_bounds and _contains bodies and signed
Validator, guard, kernel, SiteJudge and FixProfile remain unchanged. Candidate
search uses original float64 face bounds and restores the same hit/face order.
Nonfinite coordinates are rejected before constructing the spatial tree.

The original fec7b3e load_qualified_floor implementation is retained. Using the
ff3e8e5 worktree directly would lose that input loader and is not a valid retry.

Measured component blobs:

- caster: 1f68936456b2bb9b00c8d07d0be7da29b1263e66
- spatial recovery tests: 906c29e6d4e2b56861fa7ac6511801f709db91c1
- unchanged tools/main_infra_e3.py: b99e790d9086d90c40202afaa6ddf43db4e67b7e

Actual acceptance output, main virtual environment, this worktree PYTHONPATH,
one BLAS/OMP/MKL thread and a short D: pytest temporary directory:

```
OLD implementation + new spatial regression test:
7 failed, 1 passed in 2.07s

Reviewed implementation + test_caster.py + test_caster_spatial_recovery.py
+ tools/tests/test_main_infra_e3_input.py:
31 passed in 1.95s

git diff --exit-code fec7b3e -- engine/validate engine/guard
  engine/fixes/pipeline.py engine/site_judge.py engine/repair/kernel.py
  tools/main_infra_e3.py
exit 0
```

RED/GREEN command output is preserved in main data/tmp/e3-index-{red,green}-20261023.txt.
This is code verification, not proof that any new real floor was repaired.

Retry policy: one geometry worker at a time after the dashboard build finishes,
fresh attempt folders and invocation/receipt hashes, resource and peak logging,
then independent comparison against the original fresh source. Guards, targets,
site checks and confirmation are never skipped. No retry has started in this
record. The 1F E3 candidate still has passing preservation and failing targets;
no floor is accepted. Codex owns 1F-3F; Claude Code owns 4F-7F.
