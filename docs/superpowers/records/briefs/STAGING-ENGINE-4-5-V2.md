# STAGING-ENGINE-4-5-V2: MAIN INFRA floors 4 and 5 through the engine on freshly updated FIXED-CUTS-V2, staged into MAIN-INFRA-FLOORS-4-5-ENGINE.blend

Owner request, 2026-10-19 (worker claude-argon): run
`D:/PROJECTS/04-Corllenium-Building-Model-Repair/02_STAGING_DEVELOPMENT/MAIN_INFRA-ALL-FLOORS-20261019/run_engine_on_7_floors.py`
with `--floors 4,5`, input `MAIN-INFRA-ALL-FLOORS-FIXED-CUTS-V2.blend`, output
`MAIN-INFRA-FLOORS-4-5-ENGINE.blend`, work directory `engine-7floors-4-5-v2`, and stage the repaired `.fixed.obj`
outputs into the output `.blend`.

- Run the runner with the main checkout's `.venv/Scripts/python.exe`. Do not change engine stages, guard
  settings or the runner. No engine code edits.
- The input .blend is re-saved by a live Blender session (V2 re-saved at 21:50:57 and 21:56:50). Export and
  stage-back must read the same bytes, so the run reads a sha256-checked copy,
  `MAIN-INFRA-ALL-FLOORS-FIXED-CUTS-V2.frozen-215650.blend` (sha256 `0d3ffedb…d8a8`, the 21:56:50 save).
  Provenance goes in `engine-7floors-4-5-v2/input-provenance.json`.
- The runner stages guard-failing floors by default (`only_passing=False`), so every floor that finishes
  is staged with its guard verdict attached.
- Verify: the runner regression tests; both `.fixed.obj` and `.fixed.ngon.obj` per floor (parse, index ranges,
  hash against the report, materials, area and bbox invariants); a fresh headless Blender readback of the
  output (staged face counts match the receipt, every non-target mesh identical to the input).
- Record actual output. A guard verdict is the runner's 26-view orthographic guard, not the Validator of
  AGENTS.md §6: no floor pass is claimed. Leave the peers' runs (`engine-7floors-2-3`, `engine-7floors-v2`) and
  the live Blender session alone.
