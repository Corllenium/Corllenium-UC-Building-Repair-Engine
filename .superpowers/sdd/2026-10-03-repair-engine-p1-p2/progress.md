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
