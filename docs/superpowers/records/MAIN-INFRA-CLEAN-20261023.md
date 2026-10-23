# Fresh MAIN INFRA execution - current status

Owner approved the replacement plan in this chat on October 23, 2026. Execution
job: MAIN-INFRA-CLEAN-20261023. Source: the designated fresh seven-floor Z: package;
owner scale: 1 block = 1 metre. Preserve cuts, facade look/UVs and visible coverage.

## Actual progress

- Real per-floor UI and canonical progress publisher implemented in isolated branches.
  Dashboard commit a1e234f. New/existing UI tests: 20 passed. Publisher: 8 passed.
- TypeScript, scoped lint and production build passed. Real browser test passed:
  seven actual disk-backed rows, actual publisher event observed by polling,
  floor selection and mobile viewport. Only browser authentication uses a read-only
  fixture; model/progress data is read from the real canonical publisher output.
- Dashboard preview: localhost:4192, /pipelines?tab=buildings&building=MAIN_INFRA.
  This is isolated local implementation evidence, not a production deployment.
- Prior importer/cleanup modules reused after missing-module RED. New immutable
  freezing and explicit tessellation-reference tests observed RED then GREEN.
  Combined focused importer/cleanup/freeze/gate/publisher suite: 59 passed in 0.79s.
- Real source import qualification is next. No fresh candidate, independent floor
  pass, accepted model or SKP has been produced yet. No live service/database changed.

## Evidence and pointers

### Import qualification and pilot runner, 2026-10-23

- Frozen package: 36 files, 10,795,763 bytes; source revision
  7b2f7451b5723f724a1e074fdedc07dbcf7291d330ae550066f4926886136511.
- Native strict ingest failures reproduced: 1F line 10224 and 4F line 36210,
  nonplanar polygon. Explicit Blender 5.1.2 reference matched all 8,008/40,518
  original polygons (15,856/78,160 triangles), zero unmatched polygons/corner moves.
- Saved original-frame triangulations: 30 paired textured views per pilot,
  including 26 directions and four eye-height cameras. Independent PNG byte
  readback: zero differences in both pilots. Inspected all-view sheets and detail
  pairs: textured floors, white walls, green bands, orange markers and cut edges
  agree. No cleanup has been used to achieve import equivalence.
- Separate saved inch/Z-up frame render: 123/190 changed RGB pixels total over
  30 views each. Independent review measures no alpha/silhouette changes, exact
  forward-transform coordinates and inverse error at most 3.55e-15 metres.
  Float32 display path differs by at most 3.8147e-6 metres; this is recorded,
  not presented as an identical engine-frame raster or a Validator pass.
- Relative-path QA attempt was invalid: Blender resolved paths to C: and failed
  texture decoding. Added a failing relative-path regression; fixed absolute
  path resolution/decoded-image checks; removed only this session's exact invalid
  PNGs from C:. Valid evidence is exclusively import-qa-v2/frame-qa-v2.
- Real guarded runner now checks exact source/engine appearance sets, existing
  strict 26-view guard at 900x600, saved-file/asset readback and import hashes.
  It uses unchanged guard_depth_tol/FixProfile on original source axis_quanta
  converted to inches. Printed normalization decimals do not imply new precision.
  An initial artificial zero-depth setting failed on identical geometry from
  floating-point ray/plane residuals and was replaced with the existing formula.
- All new behavior observed RED before implementation; focused suite actual
  output: `67 passed in 10.37s`. Log: run-20261023/qualification-tests.txt.
- Independent reviewer identified correct signed Validator commit 33606ce9;
  the implementation base has v0 and will not be used to claim policy compliance.
  Correct Validator's pixel/horizon tests: 16 passed. Floor verdicts pending.
- No SKP produced. No accepted floor or production deployment claimed.

- Plan: ../plans/2026-10-23-main-infra-fresh-cleanup.md
- Ledger: .superpowers/sdd/2026-10-23-main-infra-fresh-cleanup/progress.md
- Canonical state: main checkout data/main-infra-fresh/current.json
- Screenshots: implementation worktree data/main-infra-fresh/evidence/dashboard/
- Engine branch codex/main-infra-clean-20261023; dashboard branch
  codex/main-infra-fresh-20261023 in sibling SIEGE-MAIN-INFRA-20261023 worktree.
