# MAIN INFRA floors 4 and 5: engine run on freshly updated FIXED-CUTS-V2, staged into MAIN-INFRA-FLOORS-4-5-ENGINE.blend

Brief: [briefs/STAGING-ENGINE-4-5-V2.md](briefs/STAGING-ENGINE-4-5-V2.md). Queue job `STAGING-ENGINE-4-5-V2`,
claimed by `claude-argon`. Artifacts live in
`D:/PROJECTS/04-Corllenium-Building-Model-Repair/02_STAGING_DEVELOPMENT/MAIN_INFRA-ALL-FLOORS-20261019/`.

## Setup (2026-10-19)

- Runner `run_engine_on_7_floors.py` sha256 `9b84a394…23bb`. Engine at `9c856f2` plus the uncommitted
  `engine/fixes/building_repair.py` (sha256 `66a94b57…3f8f`); every hash is in
  `engine-7floors-4-5-v2/input-provenance.json`. No engine or runner edits.
- Runner regression suite:

```text
.venv/Scripts/python.exe -m pytest test_run_engine_on_7_floors.py -q -p no:cacheprovider
..........................                                               [100%]
26 passed in 8.22s
```

- The requested input is re-saved by a live Blender session (V2 was re-saved at 21:50:57 with sha256 `a515e34d…0029`
  and again at 21:56:50 with sha256 `0d3ffedb…d8a8`). Because `run_engine_on_7_floors.py` opens `--input` twice
  (export, then stage-back), the run reads a frozen copy of the 21:56:50 save made with a before/after hash check:

```text
frozen=D:/PROJECTS/04-Corllenium-Building-Model-Repair/02_STAGING_DEVELOPMENT/MAIN_INFRA-ALL-FLOORS-20261019/MAIN-INFRA-ALL-FLOORS-FIXED-CUTS-V2.frozen-215650.blend src_before=0d3ffedb4f2daa46d31b408af7035bffe66f2c115711eff0241150522a32d8a8 frozen_hash=0d3ffedb4f2daa46d31b408af7035bffe66f2c115711eff0241150522a32d8a8 src_after=0d3ffedb4f2daa46d31b408af7035bffe66f2c115711eff0241150522a32d8a8 size=20974262 mtime=2026-10-19T21:56:50.7196291+08:00
```

- Launched hidden at 21:59:51 (orchestrator PID 47836), logs `engine-7floors-4-5-v2/run.log` and `run.err.log`:

```text
"D:/PROJECTS/05-Corllenium-UC-Building-Repair-Engine/.venv/Scripts/python.exe" run_engine_on_7_floors.py \
    --floors 4,5 --input MAIN-INFRA-ALL-FLOORS-FIXED-CUTS-V2.frozen-215650.blend \
    --output-blend MAIN-INFRA-FLOORS-4-5-ENGINE.blend --work-dir engine-7floors-4-5-v2 --max-commit-wait 7200
```

## Export (21:59:51 - 21:59:56)

```text
EXPORTED 4F: 45,004 tris, 32,223 verts, 72 materials, 186 objects
EXPORTED 5F: 34,464 tris, 24,382 verts, 40 materials, 177 objects
EXPORT_OK
```

- `export.json` names `MAIN-INFRA-ALL-FLOORS-FIXED-CUTS-V2.frozen-215650.blend` as `input_blend`.
- Caps among the objects: 4F 180 of 186, 5F 171 of 177.
- Compared with the earlier 19:34 export on the pre-update V2 (`engine-7floors-4-5`), 4F dropped from 63,252 tris /
  51,985 verts to 45,004 tris / 32,223 verts.

## Results

Pending (4F engine running since 21:59:56, then 5F, then stage-back into `MAIN-INFRA-FLOORS-4-5-ENGINE.blend`). No
floor pass is claimed: a guard verdict is the runner's 26-view orthographic guard, not the Validator of AGENTS.md §6.
