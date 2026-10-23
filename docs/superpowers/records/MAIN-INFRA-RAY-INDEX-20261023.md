# MAIN-INFRA-RAY-INDEX-20261023

Controller-authorized scope (2026-10-23): reuse only the existing coincident face-bounds
index from ce4e3258b3a46991ebd74a35545e58d7524270e8, based on b603d39. Add a test-first,
fail-closed refusal of nonfinite mesh coordinates before caster construction/indexing.
This is an API/performance integration candidate, not a floor repair or validation pass.

Independent reuse receipt (read-only existing evidence):
MAIN-INFRA-E3-20261023/data/main-infra-e3/run-20261023/independent-validator/import-2F3F-audit/ce4e325-reuse-review.json
SHA256 c83d6aef5be24b8826fc30a585a369928e0f8959d93d83ac9972a3ec828c995b.
It establishes criterion equivalence on finite, valid, immutable mesh coordinates/face boxes,
not exact native float32 ray depths. It measured a NaN face poisoning ancestor bounds and
silently hiding a valid coincident duplicate. Actual 1F/2F/3F inputs in that receipt are finite.

Acceptance:
- Preserve first_hit, any_hit, all_hits, _face_bounds and _contains logic and all tolerances.
- Reuse the existing tree/index arithmetic and ordering; no new acceleration mechanism.
- Observe the new nonfinite constructor tests fail before adding minimal input refusal.
- Run focused caster/spatial tests, then applicable isolated suites; name every failure.
- No mesh repair run, source/candidate edit, live status write, server or database action.
- No changes to guards, Validator defaults, owner targets, welding/filling, cuts or appearance.
- Leave active E3/floor worker checkouts unchanged. Independent review precedes adoption.

History:
- Claimed the main queue job as Codex-Ray-Index; app-created isolated worktree at b603d39,
  branch codex/main-infra-ray-index-20261023.
- Baseline: 15 caster tests passed in 1.25s using the main repository interpreter and this
  worktree PYTHONPATH. No real-data worker was run.

- RED: six nonfinite-coordinate cases failed with DID NOT RAISE ValueError (NaN/+Inf/-Inf,
  both referenced and unused vertices); 6 failed, 2 deselected in 1.24s.
- GREEN: reused only reviewed caster blob c5b7308487b3679f6a091e4c1a5d9960b21c5921, then
  added the finite-coordinate check immediately after float64 conversion and before native setup.
  Focused caster + spatial tests: 23 passed in 2.17s.
- Readback: tree and _coincident_with exactly match ce4e325 after line-ending normalization;
  any_hit, first_hit, all_hits, _face_bounds and _contains exactly match b603d39.
  Evidence is in MAIN-INFRA-RAY-INDEX-20261023/reuse-readback.json.
- Broader engine/tests + tools/tests run is currently active at below-normal priority with
  task-owned D: temp files. No API/DB tests or actual floor run were launched. Its result is pending.
- No geometry or default tolerance was changed; no model preservation/repair pass is claimed.
