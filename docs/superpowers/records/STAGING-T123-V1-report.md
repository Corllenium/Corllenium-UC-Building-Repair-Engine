# Blender staging Tasks 1-3 verification, 2026-10-17

Status: file synchronization, both requested pytest runs, runner syntax/import checks, and saved Blender/receipt inspection pass. One acceptance gap remains: `run_chtm_3rd_and_4th_floors.py` ignores `--stages` and `--help`. The pre-existing untracked runner has not been edited; a tested review-only patch is ready, with the owner's exception requested.

## File synchronization

The three implementation files already matched. Main lacked both test files; exact copies were added from `.hermes/worktrees/siege-jev-gate`. All five now match byte-for-byte:

| File | SHA-256 in both checkouts |
|---|---|
| `engine/fixes/building_repair.py` | `26f7883df358fbdbe47b1b659d54c868e0cdbe63029bb95bc0ce0eea75f89af6` |
| `engine/campus/blender_staging.py` | `d968b07e11dcc3c66d380e110ed3dfc4d8c77c305adabe1c0ab6a442e7b26a9d` |
| `engine/campus/bpy_apply_repaired_floors_to_staging.py` | `9ef78fc60096b7ccd5bbb0dec66137133695f983c9040e318cb7ad07233df7fc` |
| `engine/tests/test_building_repair.py` | `e9bab8a2a2d16e323f9b52b7549295fa65b9de6cf5cbf5b842aed596b5a461a3` |
| `engine/tests/test_blender_staging.py` | `a8d9b7feae25fe1ea3d98cdc002faa1d008445f3a1e17b0f19f3d9632649af4b` |

## Pytest

Interpreter: `D:/PROJECTS/05-Corllenium-UC-Building-Repair-Engine/.venv/Scripts/python.exe` (Python 3.12.10). Each process ran from its checkout root with that root as `PYTHONPATH` and `PYTHONDONTWRITEBYTECODE=1`.

```text
-m pytest engine/tests/test_building_repair.py engine/tests/test_blender_staging.py engine/tests/test_merge.py engine/tests/test_floor_gate.py engine/tests/test_checkpoint_push.py -q -p no:cacheprovider
```

The successful runs additionally used separate short temporary directories, `--basetemp D:/ucv-1792241917578/m` and `/w`.

Actual output in main (exit 0):

```text
........................................................................ [ 88%]
.........                                                                [100%]
81 passed in 2.58s
```

Actual output in siege-jev-gate (exit 0):

```text
........................................................................ [ 88%]
.........                                                                [100%]
81 passed in 2.58s
```

Import-origin probes independently confirmed `building_repair`, `blender_staging`, `checkpoint_push`, and `floor_gate` resolved inside the intended checkout for each test environment.

Earlier attempts exposed harness setup issues only: a missing temporary parent (69 passed, 12 setup errors), then a 271-character destination hitting Windows CopyFile2 path handling (80 passed, 1 failed). A short D: basetemp resolved both without source/test changes. Exact successful commands/output and the hash matrix are in `data/verification/staging-t123-1792241917578/`.

## Runners

Both runners exist only in main as pre-existing untracked files. In-memory compilation and safe imports pass from both working directories. Their explicit `sys.path` insertion means all 38 loaded engine modules come from siege-jev-gate, even when `PYTHONPATH` names main.

- `run_chtm_remaining_floors.py`: `--help` passes; a mocked `--stages ' prepare_materials, merge, '` invocation forwards `['prepare_materials', 'merge']` to the selected floors. Default forwards `None`.
- `run_chtm_3rd_and_4th_floors.py`: helper `run_one_floor` accepts `enabled_stages`, but `main()` at line 555 does not parse arguments or forward stages. Mocked calls prove `--stages` and `--help` are ignored. An actual `--help` invocation would execute floor work, so none was made.

Evidence: `data/verification/20261017-runner-checks-08cf287e/`. Both probe processes exited 0; this indicates the probes completed, not that the missing CLI criterion passed. No repair or publishing ran.

## Saved Blender files and receipt

Receipt: `D:/PROJECTS/04-Corllenium-Building-Model-Repair/02_STAGING_DEVELOPMENT/staging-apply-chtm-receipt.json`.

A separate Blender 5.1.2 background process opened each file without saving. Actual result: `all_checks_passed: true`, `failed_checks: []`, process exit 0.

- All 12 unique CHTM floors and their current fixed OBJ hashes match the receipt. Floor vertices, triangle indices, stored source normals, UV loops, and face material indices match in the library, buildings file, and current linked environment collection; material slot names match the fixed OBJs.
- Current environment instance `INST_CHTM` contains the expected combined CHTM LOD0: 44,669 vertices and 99,310 triangles. A separate before-comparison library contains an older LOD0; inspection followed the current instance explicitly.
- Buildings staging is self-contained: zero external libraries, 234 packed file images plus two generated images, zero external image dependencies.
- `ARCHI_7F_Interior_Ceiling_Restored` exists as a local, nonhidden mesh: 188 vertices and 171 triangles. The buildings file matches the receipt's whole-file SHA-256.
- All environment dependencies resolve (22 libraries and 267 external images); self-containment is required of buildings staging only.

| File | SHA-256 before and after inspection |
|---|---|
| `CHTM.blend` | `742a124d14ba5423382ee52507a24e1337dab47902f2cfc35ad0703329105900` |
| `UC-BUILDINGS-STAGING.blend` | `9cd030d09804a07761fb824422f219b7d9cc15d827828369c2c67685a8853bb9` |
| `UC-BUILDINGS-AND-ENVIRONMENT-STAGING.blend` | `a796ae0b2fc579fe5eb2e4cb1656335dcd22ac88d7fc23cbba6905fdf1fb9316` |

Library/buildings hashes match the receipt. Receipt and all three Blender files retained their hashes, sizes, and mtimes. The parent independently reread all three SHA-256 values after the inspection. No `.blend` files were modified.

Evidence and executed verifier: `data/verification/blender-staging-20261017-codex-7a3e8f/`. Material signatures cover face material indices, not shader contents. The receipt supplies no pre-apply ceiling geometry baseline; current presence and the recorded file hash are verified, while historical geometric preservation and visual appearance are not independently proven. No owner/Validator geometry acceptance is claimed.

## Scope and follow-up

Only the two missing main-checkout tests were synchronized. No existing implementation, foreign untracked runner, guard, threshold, Blender model, live export, service, or database was changed. Applying a runner patch requires an explicit exception to AGENTS.md section 3's prohibition on touching pre-existing untracked files.

Prepared proposal: `data/verification/20261017-runner-checks-08cf287e/stages-proposal/run_chtm_3rd_and_4th_floors-stages.patch`. It adds the existing remaining-runner argparse pattern and forwards the normalized stage selection to both floor calls. No floor filters or geometry changes are introduced. Five isolated mocked CLI checks: original has three expected failures; candidate passes all five (CSV trimming/forwarding, default, empty argument, whitespace-only argument, and safe `--help`). Candidate syntax/import and `git apply --check --whitespace=error-all` pass. Audit side-effect attempts: `[]`. Original SHA-256 remains `2c4a9f926b58f158be74baefaae3a3b1c77e89d6eab639ab2712d73e678dc9d8`; candidate SHA-256 is `922cb660e95e6b9997c04e97d9d7c5b6cc53e2c9ac7dd103cc6639889a69cae5`. The patch has not been applied.
