# Strict E7 existing-vertex threading: implementation handoff

Job `MAIN-INFRA-E7-THREAD-20261023`, branch `codex/main-infra-e7-thread-20261023`, base `1302797f2c6f60c4082a4aa78feae79789b8dbd2`. Managed worktree: `D:/LLM_BACKUP/Codex session/main-infra-e7-thread-20261023/05-Corllenium-UC-Building-Repair-Engine`.

## Implemented boundary

`engine/repair/engines/e7_thread.py::E7Thread.plan(unit, ctx)` reuses existing `_thread_output` with zero region builds and every original face copied. It does not call full merge, region-ring simplification, UV fitting or any geometry writer. Output is one nonlegacy E7 cut per original triangle/site, existing vertex indices only, no `new_points`. The original triangle supplies its own barycentric UV and normal interpolants; neighbours never supply corner values. Normal values are not normalized during interpolation.

Every accepted cut preserves positive winding, total area and the exact projected source-triangle union. A local-plane reconstruction check permits floating arithmetic roundoff only (32 machine eps times local extent), not source-print or guard slack. A projected union is used only to prove the original triangle outline, never to produce geometry. Source cut boundaries therefore cannot be simplified or moved. Existing geometry plane grouping rejects every detected positive-area projected overlap, without the legacy 99% coverage removal. Partial or nonfinite source corner attributes are refused. The existing `thread_tolerance(quanta)` is unchanged. A point outside it is never searched; even a point inside it is refused if it changes the original source triangle.

`tools/main_infra_e7.py::run_checked_e7(before, looks) -> KernelResult` creates default FixProfile, default SiteJudge and only E7Thread, calls `repair_unit(validate_sites=True)` and checks the source digest for mutation. Every proposed edit is freshly checked and subject to default nonlegacy rollback. It returns the kernel outcome, not a serialized candidate or floor acceptance. `E7Thread.report` exposes candidate/proposed/refusal counts when using the planner directly. No CLI stage or default pipeline order changed.

## Test evidence

- Existing isolated threading baseline: `7 passed, 56 deselected in 1.49s`.
- Initial RED: 13 missing-planner failures in 2.33s; expanded RED: 17 missing-planner/wrapper failures in 1.51s.
- Focused GREEN: `17 passed in 1.13s`.
- Related verification command:

```powershell
$env:PYTHONPATH=(Get-Location).Path
& 'D:/PROJECTS/UC MODEL FIXER/.venv/Scripts/python.exe' -m pytest engine/tests/test_e7_thread.py engine/tests/test_merge.py engine/tests/test_repair_uv.py engine/tests/test_repair_types.py engine/tests/test_kernel_site_checks.py engine/tests/test_kernel_stage_rollback.py engine/tests/test_overlap.py -q -p no:cacheprovider --basetemp=data/test-tmp/e7-related/run --tb=short
```

Actual result: `191 passed in 67.52s (0:01:07)`, exit 0. This is the named related set, not a claim that the complete repository suite passed.

The literal seam fixture replaces source face 0 with `[[0,3,2],[3,1,2]]` and leaves its neighbour unchanged: 2 input triangles, 3 output triangles, 1 kept site. Shared positions retain different source UV/normal seams. Reversed winding, absent attributes, partial attributes, off-edge/off-plane points, overlaps, unused or degenerate-only vertices and malformed output boundary/winding/area are tested. A visible textured cut gets real default SiteJudge first/final PASS. Injecting a faulty +0.25 UV offset into the planner gets first FAIL, final NOTHING KEPT, and the original face/UV indices remain.

## Small fixture artifact readback

Owned artifacts are under `data/main-infra-e7-thread/fixture-20261023/`: `before.obj`, `after.obj`, `summary.json`, 21 engine ray-cast QA PNGs per side, and `paired-fixture.png`. The paired top/oblique image was opened and inspected: silhouettes and filled surfaces match; the intended fan edge joins the existing seam point. These are small engine QA renders, not a Blender native appearance check or a real-floor facade check. No SKP output was produced.

The OBJ readback matches positions, face indices, corner indices and material names. Measured maximum UV roundtrip error is `2.220446049250313e-16`; maximum normal error is 0 on this fixture. An initial readback assertion compared material numeric IDs, which the reader reorders by encounter; the corrected diagnostic compares material names. That diagnostic assertion did not change production code.

## Required next integration proof

Before a real 1F run, bind the precise input hash, qualified physical frame and precision metadata. Serialize cut outputs into both original source and engine frames with explicit original-face lineage and per-corner attributes, and read both saved artifacts back. The E3 survivor-only writer cannot represent these replacements; generic `write_obj` formats UV and normal values to six decimals, so it is not a general exact attribute writer. A compatible writer must prove precision rather than assume it. Verify source cut boundaries, immutable original exports, new output hashes and a fresh edit log. Then run the qualified native appearance pairs and independent full signed Validator against actual remaining problem targets.

No real floor was processed. No source export, existing test, E3 core, guard, FixProfile, Validator, threshold, live service or dashboard asset changed. E5 winner selection remains a separate gap. The controller reviewed the brief for prompt-rule conflicts and owns aggregate HANDOFF/session/queue record integration.
