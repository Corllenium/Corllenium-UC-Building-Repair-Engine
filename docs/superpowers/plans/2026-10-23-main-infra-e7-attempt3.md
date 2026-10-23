# 1F E7 attempt3: fresh checks of the verified 273-site subset

Proposal only, 2026-10-23. No kernel, repair, or validation process is launched by this document. The failed execution tree stays frozen. Implementation needs a claimed job, branch, worktree, TDD, and independent review.

## Measured reason

Attempt2 PID43456 returned a real default checked E7 outcome: 628 planned, 273 kept, 355 rolled back, 10,578 output triangles from the 10,136-triangle E3 stage input. The final stage check passed; source serialization then raised ValueError('source boundary'), before saving any candidate. The original fresh baseline remains 15,856 triangles.

Four actual SiteJudge runs took 785.00s (628 sites, FAIL), 330.96s (298, FAIL), 272.36s (278, FAIL), and 267.69s (273, PASS). These are observations, not an attempt3 runtime promise. All 273 engine-frame proofs pass. Ten source-frame float barycentric/GEOS equality checks fail, while exact binary64-rational plane/inside/winding/area/oriented-boundary proofs pass for all ten. The separate serializer fix must finish its tests and review first.

The original typed Edits, outcome mesh, and their byte digests were not saved. We can reproduce its K1 records and deterministic construction, but cannot compare rederived UV/normal/mesh bytes to an unsaved historical object. Attempt3 is a NEW checked attempt, never a recovered old PASS.

## Frozen donor and input anchors

Donor root: D:/LLM_BACKUP/Codex session/main-infra-e7-run-1f-20261023/05-Corllenium-UC-Building-Repair-Engine/data/main-infra-e7/run-20261023-attempt2.

- Preparation preparation-1F.json: SHA256 1cd147ad337153811478b6f7a02e904f8fd935227aefa89ef794b5b8abc4896f.
- Actual execution-1F/edit-log.jsonl: 7348b39a2a54192c6f44b758be96cb57703e0c24c361b5ea99ed0879f39ce6c7.
- Actual terminal execution-1F/worker.json: e9b61a96b9d0ab3154118f275f7baf44a13385d8c641731c17d696bc50f3654f.
- source-boundary-diagnostic.json: b95a79bcb49e34ac9680202dbb86e80731224aba759d0e0013d6d623756ee8b5.
- source-boundary-exact-rational.json: 92c139f26625ec1aca4558aeb4481c8b0dcca0ab61e3fcaaf1501332f311f663.

All original preparation path/hash facts remain mandatory: raw/native qualification, forward frame, source/engine tables, E3 survivor ancestry, physical quanta, material inventory, original assets and signed targets. The new preparation pins its own clean component HEAD and file hashes. Its E7 planner, interpolation, kernel, SiteJudge, caster, guards, FixProfile and targets retain reviewed donor versions; only the independently reviewed serializer proof and new narrow runner/checkpoint files differ.

## Selection and fresh execution

1. Reuse the qualified loader. Rehash every donor/input file and required component; regenerate the full 628-cut plan using the pinned original E7Thread and defaults.
2. Recompute ALL 628 stage_records and require exact equality, in order, to the donor's 628 edit records, allowing only each literal donor rolled_back:true marker. Reject missing, extra, duplicate or malformed records, wrong flags, faces, site/reason, K1 keys, material or counts. The single donor check and worker counts must agree with that partition. Their verdict is historical metadata, never the new verdict.
3. Select exactly the 273 regenerated Edits without a donor rollback marker, in original order. Exclude all 355 donor-rolled sites. Freeze a new full typed-plan digest, selected donor indices/sites, original plan digest, and selection-policy version in the new preparation. K1 keys alone do not bind attributes; retain full regenerated typed Edits and hashes as this NEW plan.
4. Before heavy work, run the reviewed exact source proof on each selected cut, unchanged engine proof, original-index/no-new-position/material/prefix checks, and input/asset hashes. This is geometric preflight; do not fabricate a KernelResult/check record to get past serializer admission.
5. Use a narrow engine adapter named E7 whose plan returns only that verified subset after checking the input digest and plan seal. Call unchanged repair_unit with default FixProfile(), real SiteJudge(looks), sole nonlegacy E7 adapter, and validate_sites=True. Do not supply max_rounds/rollback overrides. Check input and plan digests again after return.
6. Its actual NEW result, check, rollback partition and K1 log are authoritative. Fresh failures follow the existing rollback/confirm loop; nothing requires all 273 to survive. If none are lost the expected face count is 10,578, but that is not a substitute for the fresh result.

run_checked_e7 currently always instantiates the full E7Thread, so this needs a separate narrow checked-subset wrapper, preserving that default. Serializer _checked already permits a subset: every actual kept Edit must exactly equal the full E7Thread allowed Edit. Preserve that check apart from the separately reviewed source-geometry proof fix.

## Checkpoint before serialization

Immediately after real repair_unit returns, BEFORE prepare_cut_pair, extra admission replans, or the large worker status write, persist the ACTUAL typed result in a new exclusive execution-1F/checked-outcome/ directory. This is separate from candidate staging and remains if serialization fails. Complete a temporary sibling and atomically rename; no overwrite or pickle.

Use a fixed E7-only schema, not a generic framework:

- Exact .npz numerical arrays: all eight outcome mesh tables (positions, uvs, normals, face_v, face_vt, face_vn, face_material, face_line) and every non-None Edit array (new_faces, new_points, new_face_uv, new_face_normal). Preserve dtype, shape and raw bytes, including signed zero/allowed whole-face missing-corner NaNs; load with allow_pickle=False, reject object arrays and unknown members.
- JSON metadata: all MeshData scalars/materials; every Edit scalar, faces, evidence, decision and legacy marker; array references/None markers; actual edit order and kept/rolled indices; actual checks and records; explicit result=None, stages=[], report=None. Restore shared Edit identities through index lists, not separate kept Edit copies. Existing serializer _encode omits decision and uses JSON array lists, so is not alone a complete typed checkpoint.
- Receipt: clean component/input/preparation/selection hashes, BEFORE _source_digest, actual AFTER _source_digest, full per-array dtype/shape/byte hashes, metadata and actual K1-log file hashes, counts, fresh-check summary, schema version and NEW attempt/run_id. Write the actual new edit log with write_records before sealing the checkpoint. Store the external checkpoint-receipt SHA in worker state.
- Read it back BEFORE serialization. Compare every array bitwise to the actual in-memory result, complete metadata/typed Edits and checks/records, and the identity-preserving partition. apply_edits(before, actual_kept) must have the same complete mesh digest as the actual output. Fail closed on differences. Reuse _source_digest, exact-array checks and hash helpers.

Only this freshly captured, hash-bound checkpoint may support a later serializer retry without another kernel run. Changed selected Edits, mesh, inputs, engine semantics or checks invalidate reuse. This is a captured actual result, unlike attempt2's incomplete historical record. Independent floor acceptance remains required.

## Minimum checks and delivery gate

Minimum heavy repair work: ONE new default kernel stage on 273 sites. If its first run passes, the existing kernel requires no second confirming run: its real first PASS is the final check. Charged/unknown failures get the same default rollback/confirmation and whole-stage refusal. Do not promise one pass or copy attempt2's PASS.

Then use the reviewed exact serializer, immutable run-20261023-attempt3/1F, precise writer/readback/lineage binding, and NEW copies of all seven original MTL/PNG assets. Rehash NEW copies against qualified inventory. The separate independent agent must still perform required cumulative preservation/texture/UV/visibility and full signed-target Validator against the ORIGINAL 15,856-triangle source, plus existing qualified native view comparisons. No old baseline substitution, acceptance claim, or publication before those proofs. Do not repeat unrelated suites or the known rejected 628-site candidate.

## Focused TDD and review

- Reject wrong preparation/input/component/donor-log hashes before kernel; reject changed/reordered/missing/extra K1 records and invalid rollback flags/counts. Confirm selected identity/order is exactly 273 donor-kept Edits, never a donor-rolled site.
- Tiny fixture: real default kernel receives only the subset and creates a NEW check/log. Exercise fresh rollback and whole-stage refusal; no donor PASS field can alter the result.
- Checkpoint round trip: all eight mesh tables, full Edit arrays/metadata, identity partition, actual checks; signed zero, optional missing-corner placeholders and absent arrays. Reject tampered metadata/array bytes, mismatched apply_edits output and external receipt hash.
- Inject a serializer exception AFTER checkpoint; recover the exact actual captured result without synthetic old verdicts or another kernel run. No candidate marked saved after the injected failure.
- Existing focused E7/serializer/binding tests stay green; no guard/threshold/Validator/existing-test edits. Independent reviewer checks selection and checkpoint path before real execution.

Root resource GO and serial scheduling remain operational gates. No other floor, build, browser or broad suite is launched.
