# 1F checked E7 execution preparation

Job MAIN-INFRA-E7-RUN-1F-20261023, isolated branch codex/main-infra-e7-run-1f-20261023 from fe833a5. Approved exact ray-index ff3e8e5 is cherry-picked here as 8fa5d4e. No other-floor process or import path was changed.

The runner `tools/main_infra_e7_1f_run.py` has prepare and execute commands. Prepare verifies independently anchored real source/native/qualification/provenance/baseline/E3-pair/ancestry/material hashes and reuses load_physical_pair. It reads original full source/frame tables, actual looks and signed targets; it never plans or runs E7. The saved preparation freezes all inputs, qualified physical metadata, original/stage counts, original asset inventory, previous signed-target failures and component commit/file hashes. Execute refuses any changed preparation, input or code and any existing worker/candidate.

Execution calls unchanged run_checked_e7 with default SiteJudge/FixProfile and rollback-enabled validate_sites=True. It writes the actual fresh log, binds the exact original source and E3 ancestry to actual kept cuts, saves through the independently reviewed serializer, copies original MTL/PNGs via copy_verified and hashes each NEW copy. It then rebinds the saved models and finalizes a fresh immutable package. Worker JSON is outside that package; candidate_saved appears only after final directory existence. Receipts retain PID/start, code revisions, actual site checks and cuts, geometry/asset hashes, original 15,856 vs E3-stage 10,136 counts and explicit pending independent acceptance. The prior signed failures are labeled input failures; no post-E7 signed-target result is invented.

Test evidence: first attempted RED exposed a missing temporary parent (11 setup errors); creating the owned parent produced intended 11 missing-module failures in 0.55s. Initial focused GREEN 11 passed in 3.24s. Added actual checked small-fixture save/readback + asset copy and related E7/serializer/ray tests: 90 passed in 11.65s. A worker ordering regression then failed with saved states [False, True] before correction; final focused command/output is recorded in the ledger. No real floor kernel had run when these tests were recorded.

Controller GO and independent serializer/ray reviews were received in this session. Actual preparation/run output and PID will be appended after committed execution. This job does not accept or publish a candidate. Independent cumulative baseline is the original qualified fresh 15,856-face mesh.

## Actual committed preparation and run start

Final focused runner GREEN: `13 passed in 4.02s`, exit 0. Initial preparation/run commit 396061b1222312c6a231db75481ed8cbb39618fa. Reviewed ray-index integration 8fa5d4e6eeb60295493779255e2c2fb8be43296d.

Actual prepare output: state prepared; original_source_triangles 15856; stage_input_triangles 10136; preparation SHA ae525196226b71890e028eb0cf688cdce4d2cc70ef9236c5e164b618e6ccad66. Readback asserts both counts, seven assets, unknown_materials=[] and no_texel=[]; final candidate did not exist. Physical axis quanta inches [0.00003937007874015748,0.00003937007874015748,0.000003937007874015748]. Actual materials SHA aafb0e8572a8a3aa544beedfcc9863a9c240e28fc4dcbe0e47d8b45e42982c5c.

Command from owned worktree, PYTHONPATH set to its root:

```powershell
& 'D:/PROJECTS/UC MODEL FIXER/.venv/Scripts/python.exe' -u -m tools.main_infra_e7_1f_run execute --plan data/main-infra-e7/run-20261023/preparation-1F.json --plan-sha256 ae525196226b71890e028eb0cf688cdce4d2cc70ef9236c5e164b618e6ccad66
```

Actual PID 56540; started_utc 2026-10-23T11:53:00.121514+00:00; exec session 65002. Live worker `data/main-infra-e7/run-20261023/execution-1F/worker.json`. Default SiteJudge reached and later read-only stack showed Validator visible_samples/first_hit. Saved snapshot `execution-1F/stack-1157.txt`. No running code, imports or settings changed after start. Full baseline failures remain input facts: different-look flicker1626, same-look1014, cracks2372. Actual candidate and independent post-E7 counts remain pending at this record step.

## Requested read-only exact-coincidence census

During the checked E7 wait, controller requested exact triangle groups on the frozen E3 source. `data/main-infra-e7/run-20261023/exact-coincident-census-1F.py` writes the reproducible evidence JSON, hash 073406675c99a43c16fc3ec1a550f25033a6ee99fb7aa90253af4fa7c7413d5e. All 10,136 stage faces map to original native source triangles; original source position/UV/normal tables are byte-identical, and stage corner indices equal original rows selected by the E3 lineage.

Measured and JSON read back: zero repeated exact sorted world-corner groups; zero pairs of any material/UV/winding classification; zero opposite-winding same-material exact-UV candidates; original source pair list []. No rounding/snapping/plane/coverage/UV tolerance was used. Winding uses exact corner-permutation parity; corner UV tuples are compared at the matching exact world coordinate. Numerical signed zero is one geometric coordinate.

Read legacy9f39e7 `plan_coincident_removal` conditions: original exposure winner/tie, side-pixel confirmation and strict guard remain additional required gates. Its broader 0.001in/0.99 finder was not run. This exact census does not measure differently triangulated/partial/near overlaps and cannot approve the existing broader finder. No coincident repair ran; the E7 process was unchanged.

## Exact axis-plane opposite-union census

Second controller-requested read-only measure is saved as `data/main-infra-e7/run-20261023/exact-axis-opposite-union-census-1F.json`, SHA598bfc7df2decef1208410b0bebd31a77b35c3a8a663f9e14a9473ed6f806cd3, with its reproducible .py beside it. Readback confirms all498 full-cover rows/source IDs and0 UV-compatible full-cover rows.

10,136 stage triangles:9,768 axis-aligned,368 outside this scope.341 groups share exact axis plane coordinate and material;145 have both windings.498 faces have empty Shapely difference and exactlyzero area against the opposite-winding same-material union.0 faces are fully covered by an opposite union with identical exact affine UV mapping. Both directions were counted; no loser or winner was selected. Material counts among the498: quartz_block_side176, concrete_white240, tinted_concrete_white82. First original source IDs:[1,19,22,23,31,39,42,43,50,51,67,102,103,113,132,133,147,215,223,438]; full IDs and overlap contributors are in JSON. None has all intersecting opposite contributors with exact-equal UV maps.

Plane/axis identity uses float64 source equality with no tolerance. Geometry requires empty difference AND area0, no99% threshold. UV equality compares exact rational affine coefficients derived from original float64 XY/UV values, without wrapping or tolerance; compatible opposite triangles must themselves cover the whole source triangle. No repair, exposure decision, SiteJudge or broader legacy finder was invoked. The active E7 code/imports were unchanged.

## Actual attempt1 failure and serial retry preparation

Actual exec65002 exited1. Worker56540 failed at2026-10-23T12:20:17.198522+00:00 after1637.08s, inside kernel default SiteJudge CONFIRM run (`_check_stage` line353), not serialization. NumPy could not allocate1.97MiB float64(258102,) in Validator `_witness_rays`/np.linalg.norm after floor.lattice_seen. Full captured traceback is saved as `execution-1F/stderr-captured-session-65002.txt`; original worker/preparation/stacks retained. Readback confirms final1F directory absent and fresh execution edit-log absent. No checked outcome, saved candidate, new assets, independent pass or acceptance exists.

Actual failure-time Windows Operational Resource-Exhaustion-Detector Event1003 at12:20:17.9077837Z: SystemCommitCharge67,057,364,992B/Limit67,303,272,448B (~99.63%); headroom245,907,456B. Event1008 at12:20:18.2711458Z ErrorCode2147942487. Only permitted counters saved in `execution-1F/windows-exhaustion-counters.json`; no command lines captured. System2004 query returned explicit NoMatchingEventsFound; Operational enabled with matching events. Controller reports2F/3F allocation failures within0.105s of1F. Post-failure commit89% cannot substitute for failure-time evidence. Current escalated helper JobObject query flags0x3000, ProcessMemoryLimit0/JobMemoryLimit0 and64-bitPython; historical failed-process peak/limits were not retained, so are unavailable. Evidence supports shared commit exhaustion; no algorithm or guard change is proposed.

External `watch-e7-memory.ps1` fills the measured logging gap: existing winprobe only measures its own peaks. Observer records system commit/limit/available and the watched worker private/peak commit/working-set every second, holds a process handle and never stops/modifies the worker. TDD RED missing script; actual external-observer GREEN1passed3.87s (two real samples, overwrite refused, watched test process remained alive). It is separate from engine code and settings.

Controller authorized serial attempt2 only after delivery agent explicitly releases webpack/browser heavy work and controller checks at least8GiB commit headroom. At delivery pre-build measurement, margin6.56GiB did not meet that gate. No attempt2 kernel started. Fresh namespace will be `data/main-infra-e7/run-20261023-attempt2/`, with new preparation, execution-1F/worker.json, resource JSONL and immutable1F package. The old namespace is preserved. Same committed E7 runner/wrapper/planner/serializer/caster/guard/targets will be used; actual preparation SHA and invocation follow after commit/readback.

## RepeatWrapping full-cover UV census

Source proof: FreshMainInfraPreview calls DualModelCanvas. DualModelCanvas explicitly sets both wrapping axes to RepeatWrapping for newly created and loaded textures; raw OBJ vt values are copied directly, then stored as Float32 UV buffers. Three Texture defaults repeat(1,1),offset(0,0),rotation0. The original MTL SHA c64c0cb12926c707b55262a82fd324ccd09502f92b0c866801a00e9f3c89d9a3 has six untransformed map_Kd entries. Sampler source hashes: DualModelCanvas e05ef7b0ab47a9fadd9eae634e822ef423e4e976e67488c33ceb1928163e144e; meshbuf7b396c0db1dbf459f757a272c9436d3cd04ed1e400f1815356870bd6cc7ef1e1; full five-file inventory and Three source hash stored in diagnostic JSON.

Exact integer-translation extension JSONSHA f6fabfb6fd2ee7248d7222eab21cc0f482a43356202eb2d746da2ebdb0448939, `data/main-infra-e7/run-20261023/exact-axis-opposite-union-repeat-uv-census-1F.json` (+repro .py). Readback:498 geometry-full covers;0 exact modulo-whole-tile UV-compatible full covers;0 compatible positive-area contributors;0 constant/rank-deficient exclusions. Linear affine parts must match exactly and offset differ by exact integers; scale differences, tolerance and constant maps are excluded. Only conclusion: this narrow exact UV-equivalent full-cover stage has no candidates. No further texture tolerance/census expansion or repair ran. Native/GPU/full Validator acceptance remains separate.
