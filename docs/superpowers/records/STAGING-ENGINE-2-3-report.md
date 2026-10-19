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

Repair in progress. Final artifact verification and guard verdicts pending.
