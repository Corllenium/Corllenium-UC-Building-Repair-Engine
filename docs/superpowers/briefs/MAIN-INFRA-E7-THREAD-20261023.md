# MAIN-INFRA-E7-THREAD-20261023

Build job, claimed by Codex-E7 in the main queue. Branch `codex/main-infra-e7-thread-20261023`, base `1302797f2c6f60c4082a4aa78feae79789b8dbd2`.

The controller authorized this narrow implementation under the owner's request to repair fresh MAIN INFRA floors 1-3 while preserving final cuts, facade textures and UVs. The E3 removal candidate passed independent preservation checks but does not meet all remaining problem targets. This job addresses the existing exact-vertex T-junction algorithm gap; E5 winner decisions remain separate.

## Deliverable

- A nonlegacy E7 planner, one cut Edit per original triangle, reusing the existing `_thread_output` math with no region builds.
- Existing vertex indices only; no invented or moved positions. Interpolate each source triangle's own UV and normal values at its inserted corners. Preserve winding and material.
- Reject a proposed cut if the source triangle overlaps another surface, any child lies off its source plane or changes the source triangle outline, children overlap or total area changes. Points outside the existing `thread_tolerance(quanta)` are never threaded.
- A wrapper that always invokes `repair_unit(validate_sites=True)` with default `FixProfile` and default `SiteJudge`; failing sites roll back.
- Small-fixture RED/GREEN evidence and a concrete API handoff. No real-floor run or publishing.

## Boundaries

Do not modify guards, FixProfile, Validator, existing tests, E3 core, source exports, live services or dashboard assets. Do not run full merge, UV fitting for output, region-ring simplification, generic filling or whole-face overlap removal. Do not change existing exact threading tolerance. Only newly created tests belong to this job.

The result is not accepted floor delivery. A later owned input loader must bind the new input hash and physical frame; replacement triangles need explicit original-face lineage and exact source/engine pair serialization, then native appearance checks and an independent signed full Validator run.

## Acceptance

A hand-built visible T-junction is split into the literal expected triangles, while retaining original points/material/winding and source corner attributes. Off-edge, overlapping and boundary-changing cuts are refused. Tests include shared UV seams and a real default SiteJudge pass plus failing-cut rollback. Run existing threading fixtures and focused new tests; report every failure. The controller owns aggregate HANDOFF, session and queue-record integration.
