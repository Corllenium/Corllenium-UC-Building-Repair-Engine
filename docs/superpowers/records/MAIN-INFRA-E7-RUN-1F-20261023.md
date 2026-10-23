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
