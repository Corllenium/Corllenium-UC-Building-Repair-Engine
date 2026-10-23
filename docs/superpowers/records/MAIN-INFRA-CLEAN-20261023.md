# Fresh MAIN INFRA execution - current status

## Source precision blocker and correction, 2026-10-23

The independent audit found raw/source sig9 versus normalized engine sig17.
Original physical quanta [1e-7,1e-8,1e-7]m become
[3.937007874e-6,3.937007874e-6,3.937007874e-7]in; inferred engine quanta were
39,370,078.74x smaller. Six deterministic512-face real subsets changed plane
partitions under inference, while physical source/engine partitions agreed.
Full4F validation was stopped at1810.21s after771696casts: no validation.json,
no full verdict/counts. All diagnostic artifacts remain. Earlier1F numeric
problem counts are literal storage-precision diagnostics pending requalification.
Saved geometry/materials and30paired4F PNGs remain unchanged.

RED fixture: a source plane splits into two regions solely after conversion.
Explicit physical-quanta propagation now retains the plane and cache identity.
21frame/topology tests pass;9hash-binding tests pass. Hash-bound raw/reference,
independent import proof, saved baseline/snapshot and both candidate files are
checked before attaching physical precision. No threshold/guard/target changed.
Signed33606ce9 integration and independent reruns are pending; cards show blocked.

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

### 4F saved candidate, 2026-10-23

The committed original-oracle pilot completed all52renders and PASSED the strict
guard:4,853,024modelpixels; holes, moved_other, material changes and grown0.
78,160->78,160triangles, exact duplicates0, exact source/engine coverage missing0
and added0. Candidate engine SHA924ac3984bf199e632d00e5e6eaa226a29a7920b07a50820622c602102ca8b05;
source SHA2a217d63f6dbc6556e4713bff06bf66316f66580272d3bbbcca0719be1e586b9.
19assets verified. Output is under run-20261023/candidates/4F, not an accepted result.

Saved native fresh-raw/source-candidate QA:30texturedpairs including26directions
and4eye-height views; decoded PNG readback0differentpixels. Inspected all-view
and paired-detail sheets: tiled floors, white facade textures/green bands,
openings/cut edges and orange source markers match; diff images black.
Initial Blender run exited0 but a user addon logged a shutdown exception; that
run is preserved under candidate-qa-addon-shutdown/4F. Final evidence is exclusively
candidate-qa/4F, rerendered with --factory-startup, exit0, no addon startup.
Independent full-floor Validator input readback is in progress. No floor pass,
repaired-target success, owner acceptance or deployment is implied by the guard.

### Fresh model dashboard and precision investigation, 2026-10-23

- Final post-review compiled browser test passed in8.9s. Inspected pending After
  screenshot: empty grid, no invented slab. Source/candidate textures inspected.
  Clean webpack build completed26pages. Dashboard commits2800a66/de060b9;46
  committed preview/evidence files re-read from Git match disk bytes exactly.
- Bounded original oracle independently passed118focused tests and20extra probes;
  exact reviewed blob68c93434. A later max-depth optimization failed a near-parallel
  corner oracle case and was withdrawn to exactly that reviewed blob. Regression
  retained. Shared Embree/default guards remain unchanged.
- Real4F timing:19200rays,1.924s,1,877,285leaf pairs vs1,500,672,000exhaustive;
  sampled12first/all results match exhaustive oracle. Explicit factory integration
  observed RED then GREEN:12tests passed29.01s, including actual52tiny-fixture
  renders and saved audit. Real full guard next; no4F verdict implied.

- Owner reiterated the source is the fresh Minecraft export and requested the
  existing seven cards/Before-After window. The isolated dashboard now selects
  fresh MAIN_INFRA_1F through 7F, including old MAIN INFRA unit links. Source and
  candidate objects use immutable revision/run/floor paths and hash-checked OBJ,
  MTL and texture assets. Default After waits for independent validation;
  a failed candidate requires explicit inspection and is labelled not accepted.
- Review caught a legacy pending slab and three provenance gates. Test-first
  corrections keep pending fresh scenes empty, bind preview floor/revision and
  candidate qualification, bind independent report to the exact qualified Before,
  and require matching review proof before automatic After. Null evidence links
  are rejected. Actual focused results: 17 Python tests, 28 UI tests; typecheck
  passes. Earlier browser readback passed in 9.5s; final post-review rerun pending.
- The source and explicit candidate screenshot show the same tiled floor, stairs,
  white walls, green facade bands and orange source pieces. No floor is accepted.
  The isolated preview is not a live deployment. No fixer service/database touched.
- Broad collectable engine suite after the committed spatial lookup: 1734 passed,
  1 xfailed in 548.03s. The two original missing-module collection errors remain
  excluded by exact filename; the full suite is not claimed as passing.
- 4F's original native float32 depths disagree with original face planes above
  its existing 5.905511811023622e-6 inch depth tolerance, even with no deletions.
  A shared-caster depth refinement passed 115 independent checks but failed two
  independent nearest-hit counterexamples. That experiment was withdrawn, with
  its diff/tests preserved under evidence. Shared caster is restored to ce4e325.
  No guard or threshold changed and no 4F candidate/pass was produced.
- Ruling: qualify a bounded version of the existing float64 BruteCaster oracle
  for this pilot via the guard's existing caster_factory hook. Original-face
  bounding boxes reduce work; the unchanged oracle decides every leaf hit.
  New exhaustive/random/parallel/corner/collapsed-sheet tests: 8 passed in 0.77s.
  Independent review and real-floor timing are required before integration.

### First pilot verdict and ray lookup diagnosis

1F exact-duplicate-only candidate retained all15,856 triangles. Strict26guard
passed. Independent Validator33606ce9 reported FAIL solely on signed problem
targets: flicker_diff5668->5668, flicker_same3347->3347, cracks2744->2744, all
targets0. Textures/UV/side and visible coverage pass:108,392 visible BEFORE
samples, no failures;24pedestrian cameras,762interior probes,64outside and
512extra directions. Runtime158.12s. Actual report/independent readback is under
run-20261023/independent-validator/1F. This floor is blocked, not accepted.

4F found no exact duplicates either. Its unchanged guard completed52renders but
spent minutes in the existing all-hit coincident recovery:51reported hitpoints
times78,160face boxes per block, for BEFORE and AFTER. Owned attempts were stopped
without verdict/output; faulthandler trace retained. A new conservative face-box
hierarchy avoids the full product while retaining exactly the old geometric
predicates/tolerances, face exclusion and output ordering. New equivalence/work
regression observed RED;20caster/pilot tests pass. Independent read-only review:
no blocking findings;17ray and70existing guard tests pass. Real4F rerun follows
this commit. No guard source, target or FixProfile threshold was changed.

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
