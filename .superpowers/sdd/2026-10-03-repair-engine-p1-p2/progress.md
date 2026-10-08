# SDD ledger — plan: D:/PROJECTS/UC MODEL FIXER/docs/superpowers/plans/2026-10-03-repair-engine-p1-p2.md

Spec: docs/superpowers/specs/2026-10-03-uc-repair-engine-design.md §4, §5, §9 (approved 2026-10-03).
Integration branch: feat/repair-p1p2, made 2026-10-08 from feat-dashboard 4d00397 (P0 closed), worktree
.claude/worktrees/repair-p1p2. Controller: the "3d uc building repair engine" session. A second controller session
("... (jev implementation)") runs the Jev/mods plan and asks this one before merging into feat/repair-p0 or
feat/repair-p1p2.

## Pre-flight scan (2026-10-08)

| Pair / task | Produces -> consumes | Finding | Ruling |
|---|---|---|---|
| K1 -> K2, K3, D1, every engine | `Edit`, `Site`, `UnitState`, `RepairContext`, `RepairEngine`, `face_keys`, `apply_edits` | consistent | — |
| K1 self | `Edit` is `frozen=True` with ndarray fields | frozen dataclass eq/hash over arrays raises | K1-R1: `@dataclass(frozen=True, eq=False)`; equality is never used |
| K1 self | `FaceKey` = vertices "snapped to the print step" | which print step? `engine/validate/checks.print_step` exists, but the kernel must not lean on the judge | K1-R2: `engine/repair` computes its own step from the OBJ's printed precision (`MeshData.coord_decimals`); the validator never imports `engine/repair` |
| K2 -> K3 | edit log, the legacy engines | consistent | — |
| K3 self | "the Validator in fast mode on the touched sites" | the Validator has no fast/site mode today | K3-R1: settled when K3's brief is written (measure CHTM 5th per-site cost first) |
| D1 -> D2 | `Decider`, providers | D2 also consumes P0-17's `JevDecider` (merged) | — |
| S1, S3 | speed jobs | already done: merged in P0 as P1-S1/S1b/S3/S3b | S-R1: not re-dispatched; S2 remains |
| E4, E5 -> P1-H1 item 1 | the look-based flicker split | E4/E5 need one same-look definition (final P0 review, important 2) | E-R1: P1-H1 item 1 must merge before E4 or E5 is queued |
| E5 -> D1 | the Decider for ties | consistent with spec §9 | — |
| Rolling briefs | each engine's failing tests written by Claude just before queueing | consistent | — |

No task's own text contradicts itself beyond the rulings above.

## Tasks
- Task K1 (P1-K1): claimed; BASE 4d00397; worktree .claude/worktrees/P1-K1 (claude/P1-K1); brief task-K1-brief.md (plan lines 91-126 + rulings K1-R1, K1-R2); engine-builder (sonnet) dispatched 2026-10-08.
- P1-D2 reserved for the Jev session (its 'Jev on the VPS' design: RemoteDecider over HTTPS to a uc-fixer-decide container; owner-confirmed answers only; 1M tokens/day cap). This controller sends it D1's interface when D1 merges. VPS deploy steps need the owner's OK at the time.
- Jev session started feat/jev-vps (from feat-dashboard d78ff24; plan docs/superpowers/plans/2026-10-08-jev-vps-service.md; jobs J1-J8; owner: build now with Jev OFF, switch on with P2's 'next repair step' question). Overlap ruling D1-R1: P1-D1 adds engine/decide/decider.py and must not edit engine/decide/jev.py; its question-type names follow spec §9 and the qtype strings J1 sets (asked for).
- K1 implementer DONE_WITH_CONCERNS: 0a250e6; 30 tests (red: collection error, plus a mutation check of the rotation loop: 4 failed); full engine suite 1227 passed, 1 xfailed.
  - Ruling K1-R3: flip sets face_vn to -1 (as orient.flip_faces) - accepted. K1-R4: new faces get vt/vn -1; a cut inherits its first input face's material; an add must name evidence['material'] - accepted; E5's brief must produce UVs for cut faces (else Validator check 1 fails). K1-R5: new_to_old is -1 for appended faces; lineage stays in the edit log (K2 may extend) - accepted.
- K1 task review (sonnet): Spec ✅, Quality APPROVED, 5 minors. Fix round 1 sent to the implementer: new_points refused on remove/flip and for E5 outside a cut; finiteness; arrays copied and read-only; mixed-material cut raises; untested asserts added.
- K2 brief written (task-K2-brief.md): ruling K2-R1 = split fix_object into stage functions as a pure refactor (fix_object keeps its API), legacy engines wrap the stages, edits are derived by K1 face-key multiset diffs (observe-only), engine.cli fix --kernel; exit = report.json and .fixed.obj sha256 identical to the base on A, B, CHTM 5th, edit-log accounting, determinism. Implementer model: opus (refactor of a 400-line monolith under exactness).
- K1 fix round 1: efc6e90 (10 red then 42 green; full suite 1239 passed). Scoped re-review done by the controller itself (the classifier refused a reviewer launch): diff matches all 5 items, 42 passed. Task K1: complete - merged into feat/repair-p1p2 (merged tree == efc6e90 tree). P1-K2 claimed; worktree .claude/worktrees/P1-K2 from the merge.
- K2 dispatched: engine-builder (opus), BASE 5de9287, brief task-K2-brief.md.
- D1 brief written (task-D1-brief.md; conventions from D1-alignment-with-jev-vps.md; ruling D1-R2: promotion is computed by stats but applied only by an explicit promote/demote call that logs it). P1-D1 claimed; worktree .claude/worktrees/P1-D1 from 5de9287.
- D1 implementer launch REFUSED by the auto-mode classifier ('Auto-Mode Bypass'), as was the K1 re-review launch earlier; not worked around. D1 stays claimed with worktree and brief ready; waiting for the owner's decision (approve the launch, or run D1 after K2 finishes).
- K2 implementer DONE_WITH_CONCERNS: df07bbf, 3680c63, 146fbf9, 205bf86. report.json and .fixed.obj sha256 identical to the base on A, B, CHTM 5th, with and without --kernel (15 runs rc 0); edit log accounts for every face; per-stage counts equal report.json; determinism OK; full suite 1295 passed, 1 xfailed.
  - Rulings K2-R2..R7: solidify may log E8 flips (same multiset) - accepted, K3 must allow E8 flips; pass 1 labelled per face (E1 zero-area, else E3) - accepted; merge cuts grouped by material, one site per stage - accepted for observe-only, K3 needs region-level sites; duplicate-copy convention, log without arrays, repair_unit extra kwargs - accepted; a stale edit_log.jsonl surviving a non-kernel run - parked to P1-H1; process slip (item 2 red shown after writing) - noted.
- K2 task review (sonnet): Spec ✅, Quality APPROVED; refactor verified behaviour-preserving (diff read line by line, symtable/ast state-flow check, non-default profile paths probed). 1 Important (kernel tests miss slit / fragments-off / rollback paths) + 6 minor. Fix round 1 sent to the implementer (tests for those paths, test rename, observe-only limits documented for K3, import order).
- K2 fix round 1: b2d56af, cbeb582 (fixtures for slit / fragments-off / rollback; red shown by a deliberate break; suite 1313 passed). Controller re-check: only the test file and legacy.py docstrings changed; 74 kernel tests passed. Task K2: complete - merged into feat/repair-p1p2 (merged tree == cbeb582 tree). P1-D1 worktree fast-forwarded to the K2 merge.
- D1 implementer launched (engine-builder, sonnet) on 76c9fae - accepted this time with no other agent running (pattern so far: launches are refused while another sub-agent runs).
