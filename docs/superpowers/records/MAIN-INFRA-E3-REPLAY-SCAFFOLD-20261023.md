# Optional checked E3 replay scaffold

This helper is unused. No real floor replay, restored candidate, or new model was produced. The controller stopped the proposed restoration after independent validation qualified the walking viewpoints. The earlier eye0 image difference came from a camera 0.6002 m above its walking floor with 1 m headroom; it is not evidence of a failed pedestrian facade check. The controller owns the independent full-validation result and aggregate floor records.

`tools/main_infra_e3_replay.py` loads only a trusted SHA-bound original E3 audit, its BEFORE snapshot, edit log, source-face map and saved candidate pair. It checks the original physical precision and all source mesh arrays, verifies original K1 keys against the supplied looks, and admits original kept remove edits only. A requested restoration excludes whole original sites. The wrapper sends the remaining edits through `repair_unit(validate_sites=True)`, the default `FixProfile` and the default `SiteJudge`; it does not reuse the original PASS as a new verdict. It returns the fresh outcome and existing `source_survivors` result for the existing pair writer. It changes no engine, guard, Validator or threshold.

The original diagnostic log had 280 kept sites and 5,720 removals. Excluding sites 0, 2 and 9 would retain 716 original triangles and propose 277 sites / 5,004 removals before fresh checks. These are plan counts, not an executed outcome or an accepted cleanup choice. The original real candidate remains unchanged.

Test-first evidence: the 17 tests first failed because the helper did not exist. After implementation, the final scoped command was:

```powershell
$env:PYTHONPATH=(Get-Location).Path
& 'D:/PROJECTS/UC MODEL FIXER/.venv/Scripts/python.exe' -m pytest tools/tests/test_main_infra_e3_replay.py -q -p no:cacheprovider --basetemp=data/test-tmp/e3-replay-final/run --tb=short
```

Actual output: `17 passed in 5.11s`, exit 0. An earlier final invocation had 17 fixture setup errors because the parent temporary directory was absent; creating that owned directory resolved the invocation error. The tests reject changed artifacts, flip/add/other-engine/new-point edits, unbound source geometry and precision, forged K1 keys and changed looks. One test runs the real default SiteJudge: despite the saved original PASS, the fresh visible-removal fixture returns first `FAIL`, final `NOTHING KEPT`, and preserves every original source face.

Diagnostic erratum: `eye0-diagnosis/pixels512/eye0-pixel-face-sites.json` used the label `source_obj_line` for `MeshData.face_line` from the generated BEFORE.engine.obj. It is not the raw Minecraft OBJ polygon line. Original triangle IDs and site mappings remain correctly identified. The scratch data is not part of this commit.

Only this report, the helper and its tests belong to this change. No source export, real candidate, dashboard asset, prompt file or shared progress record was edited.
