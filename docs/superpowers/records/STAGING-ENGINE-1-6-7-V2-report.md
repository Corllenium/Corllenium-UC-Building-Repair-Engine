# MAIN INFRA floors 6, 7 and 1: engine run on FIXED-CUTS-V2, staged into ENGINE-STAGED

Brief: [briefs/STAGING-ENGINE-1-6-7-V2.md](briefs/STAGING-ENGINE-1-6-7-V2.md). Queue job `STAGING-ENGINE-1-6-7-V2`,
claimed by `claude-vertex-opus`. Artifacts live in
`D:/PROJECTS/04-Corllenium-Building-Model-Repair/02_STAGING_DEVELOPMENT/MAIN_INFRA-ALL-FLOORS-20261019/`.

## Setup (2026-10-19)

- Runner `run_engine_on_7_floors.py` sha256 `9b84a394…23bb` (the same file the 4-5 run used). Engine at
  `92fce36` plus the uncommitted `engine/fixes/building_repair.py` (sha256 `66a94b57…f94e2`); every hash is in
  `engine-7floors-v2/input-provenance.json`. No engine or runner edits.
- Runner regression suite:

```text
.venv/Scripts/python.exe -m pytest test_run_engine_on_7_floors.py -q -p no:cacheprovider
..........................                                               [100%]
26 passed in 10.99s
```

- The requested input is re-saved by a live Blender GUI session (PID 26224 has REVIEW.blend open; V2 and REVIEW
  were saved together at 20:42, 20:48, 20:51, 20:53 and 21:01). The runner opens `--input` twice (export, then
  stage-back), so the run reads a frozen copy made with a before/after hash check:

```text
src_before=10ceb8d75c33022ca4b400de1eef354ba72052088b03b57613f8289a49d9e9d6 frozen=10ceb8d75c33022ca4b400de1eef354ba72052088b03b57613f8289a49d9e9d6 src_after=10ceb8d75c33022ca4b400de1eef354ba72052088b03b57613f8289a49d9e9d6 mtime=2026-10-19 21:01:56.549701800 +0800 / 2026-10-19 21:01:56.549701800 +0800 size=20969316
```

- Launched hidden at 21:08:47 (orchestrator PID 41992), logs `engine-7floors-v2/run.log` and `run.err.log`:

```text
"D:/PROJECTS/05-Corllenium-UC-Building-Repair-Engine/.venv/Scripts/python.exe" run_engine_on_7_floors.py \
    --floors 6,7,1 --input MAIN-INFRA-ALL-FLOORS-FIXED-CUTS-V2.frozen-210156.blend \
    --output-blend MAIN-INFRA-ALL-FLOORS-ENGINE-STAGED.blend --work-dir engine-7floors-v2 --max-commit-wait 7200
```

  `--max-commit-wait 7200` only lets the runner wait longer (default 1800 s) for its 3,000 MB commit headroom
  before each step. Three other engine runs share the machine (2-3, 4-5, 6-7), and the first log line was:

```text
[21:08:49] blender export: only 1756 MB of commit free on the machine (need 3000); waiting up to 7200 s
```

## Results

Pending. No floor pass is claimed: a guard verdict is the runner's 26-view orthographic guard, not the
Validator of AGENTS.md §6.
