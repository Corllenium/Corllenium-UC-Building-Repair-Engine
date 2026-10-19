# STAGING-ENGINE-1-6-7-V2: MAIN INFRA floors 6, 7 and 1 through the engine, staged into one review .blend

Owner request, 2026-10-19 (worker claude-vertex-opus): run
`D:/PROJECTS/04-Corllenium-Building-Model-Repair/02_STAGING_DEVELOPMENT/MAIN_INFRA-ALL-FLOORS-20261019/run_engine_on_7_floors.py`
with `--floors 6,7,1`, input `MAIN-INFRA-ALL-FLOORS-FIXED-CUTS-V2.blend`, output
`MAIN-INFRA-ALL-FLOORS-ENGINE-STAGED.blend`, work directory `engine-7floors-v2`, and stage every completed
floor's `.fixed.obj` into the output.

- Run the runner with the main checkout's `.venv/Scripts/python.exe`. Do not change engine stages, guard
  settings or the runner. No engine code edits.
- The input .blend is re-saved by a live Blender session (REVIEW.blend open in the GUI; V2 saved at 20:42,
  20:48, 20:51, 20:53 and 21:01). Export and stage-back must read the same bytes, so the run reads a
  sha256-checked copy, `MAIN-INFRA-ALL-FLOORS-FIXED-CUTS-V2.frozen-210156.blend` (sha256 `10ceb8d7…e9d6`,
  the 21:01:56 save). Provenance goes in `engine-7floors-v2/input-provenance.json`.
- The runner stages guard-failing floors by default (`only_passing=False`), so every floor that finishes
  is staged with its guard verdict attached.
- Verify: the runner regression tests; both `.fixed.obj` and `.fixed.ngon.obj` per floor (parse, index ranges,
  hash against the report, materials, area and bbox invariants); a fresh headless Blender readback of the
  output (staged face counts match the receipt, every non-target mesh identical to the input).
- Record actual output. A guard verdict is the runner's 26-view orthographic guard, not the Validator of
  AGENTS.md §6: no floor pass is claimed. Leave the peers' runs (`engine-7floors-2-3`, `-4-5`, `-6-7`) and
  the live Blender session alone.
