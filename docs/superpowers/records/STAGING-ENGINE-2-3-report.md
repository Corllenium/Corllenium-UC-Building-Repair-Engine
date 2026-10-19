# MAIN INFRA floors 2–3 engine run

Owner request (2026-10-19): run `run_engine_on_7_floors.py` for floors `2,3`, input `MAIN-INFRA-ALL-FLOORS-FIXED-CUTS-V2.blend`, output `MAIN-INFRA-FLOORS-2-3-ENGINE.blend`, work directory `engine-7floors-2-3`; stage failed floors and verify both OBJ variants.

Working directory for artifacts: `D:/PROJECTS/04-Corllenium-Building-Model-Repair/02_STAGING_DEVELOPMENT/MAIN_INFRA-ALL-FLOORS-20261019/`.

## Execution

- Queue job `STAGING-ENGINE-2-3` claimed by `codex-sol`.
- Used repo `.venv/Scripts/python.exe`; engine stages and guard defaults unchanged. No engine code edits.
- Initial command with `--stage-failed` rejected: `error: unrecognized arguments: --stage-failed`.
- Current runner stages all requested floors by default (`only_passing=False`); retried without obsolete flag. This preserves requested staging behavior.
- Initial input SHA-256: `6F801DB55201BEA0539026571CD2786DD4ADF41AC38F449D86415AA77737AFD7`.
- Export output:

```text
EXPORTED 2F: 53,605 tris, 51,191 verts, 71 materials, 72 objects
EXPORTED 3F: 58,216 tris, 47,635 verts, 80 materials, 68 objects
EXPORT_OK
```

Runner regression check:

```text
.venv/Scripts/python.exe -m pytest D:/PROJECTS/04-Corllenium-Building-Model-Repair/02_STAGING_DEVELOPMENT/MAIN_INFRA-ALL-FLOORS-20261019/test_run_engine_on_7_floors.py -q -p no:cacheprovider
..........................                                               [100%]
26 passed in 6.58s
```

Repair in progress. Final artifact verification and guard verdicts pending. Read-only artifact and Blender readback check scripts prepared inside this run's work directory.

## Long-running job recovery

- Orchestrator PID at launch: 48164 (Python shim), 39300 (interpreter); terminal session 14888.
- Floor 2 PID: 43692 (interpreter), 37360 (shim).
- Read-only `py-spy dump --nonblocking` confirms time is spent in `stage_fragments` / `_confirm_debris` / `piece_ray_check`, not a stalled Blender export. Initial fragment check has 755 candidate units and restores one per refusal round. At 20:05 +08:00 it reached round 52. Do not restart or duplicate this run while those processes are alive.
- Automatic verifier launched hidden (shim PID 54844): `engine-7floors-2-3/verify_when_complete.py`. It waits for `summary.json`, then runs `verify_outputs.py` and `verify_blend_readback.py` (fresh background Blender with factory startup).
- Inspect `verification-status.json`, `artifact-verification.json`, `blend-readback-verification.json`, `artifact-verification.log`, and `blend_readback-verification.log` in the work directory. `verified` is an artifact/readback result, not an owner's Validator acceptance.
- Guards, final evidence-image review, and owner acceptance are still pending. No floor pass claimed.
