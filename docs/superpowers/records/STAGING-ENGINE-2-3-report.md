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

## First attempt allocation failure

At 21:24:30 +08:00, after reaching at least fragment verification round 240, floor 2 failed before writing either fixed OBJ variant:

```text
numpy._core._exceptions._ArrayMemoryError: Unable to allocate 2.14 MiB for an array with shape (31202, 3, 3) and data type float64
[21:24:30] 2F: MemoryError with 2933 MB of commit free on the machine; retrying in 60 s (1/3)
```

Failure occurred in `piece_ray_check` -> `_Unit.follow` -> `EmbreeCaster.first_hit` -> trimesh triangle allocation. Preserved the full first attempt as `2F/engine-attempt1.log`. The orchestrator automatically restarted floor 2; retry interpreter PID 49648, shim PID 57960. No guard or geometry settings changed. Both fixed OBJ variants, final Blender output, and verification remain pending.

## Second allocation failure and stable-source restart

At 22:42:41 +08:00 the retry failed around fragment round 160:

```text
numpy._core._exceptions._ArrayMemoryError: Unable to allocate 1.42 MiB for an array with shape (31106, 2, 3) and data type float64
[22:42:41] 2F: MemoryError with 6074 MB of commit free on the machine; retrying in 120 s (2/3)
```

System commit availability subsequently fell below 1 GB. The job's own waiting orchestrator was stopped by verified PID before another floor process started. Other sessions and services were untouched.

The source file was externally replaced during execution: its SHA-256 is now `18949DA28A317E0A67996C48B954DCFBEAE268B9D7F8F2E1DC2480A6353D465E` (different from the initial `6F801D...`). The first export and both failures were archived under `engine-7floors-2-3/attempts/source-6f801db55201/`; those exports cannot be staged against the changed source.

The current source was copied and checked before/after copying. Stable input: sibling `MAIN-INFRA-FLOORS-2-3-SOURCE-SNAPSHOT.blend` (same `18949D...` hash), preserving relative asset paths; an additional copy and provenance are under `engine-7floors-2-3/source/`. The new run re-exports floors 2,3 from that snapshot, retains the requested output/work paths and default failed-floor staging, and adds only resource options `--min-commit-free-mb 10000 --max-commit-wait 86400`. It waits for 10 GB of free commit rather than repeatedly losing long guard runs under memory pressure. Geometry, guard stages, thresholds, and existing code remain unchanged by this worker.

Automatic artifact verification now expects the stable `18949D...` snapshot. At restart, export is waiting for memory; fixed OBJ variants and Blender output remain pending.

## Active queued run

- Engine shim PID **57684**, interpreter PID **6316**, terminal session **40241**.
- Automatic verifier restarted hidden (shim PID **6300**); it now checks engine liveness and reports a failure if the engine exits without a summary. Scripts compile successfully.
- `engine-7floors-2-3/run-process.json` records the active engine and stable input hash.
- Startup is blocked on shared commit headroom: fresh checks found only 1.6–4.1 GB available against the 10 GB requirement. The process remains active and will continue automatically when that memory is available (maximum wait 86400 seconds).
- Both `.fixed.obj` and `.fixed.ngon.obj` outputs and `MAIN-INFRA-FLOORS-2-3-ENGINE.blend` are **not yet produced or verified**. No guard or owner-validation pass is claimed. The two failed attempts and original-source exports remain archived.
- Automatic results will appear in `engine-7floors-2-3/verification-status.json`, `artifact-verification.json`, and `blend-readback-verification.json`. Guard PNGs still require visual review after a completed repair.
