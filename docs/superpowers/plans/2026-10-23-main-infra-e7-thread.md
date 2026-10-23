# Strict E7 Threading Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [x]`) syntax for tracking.

**Goal:** Expose existing exact-vertex threading as a strict checked E7 stage without rebuilding planar regions.

**Architecture:** Call `_thread_output` with no region builds and every source triangle copied, then form one nonlegacy cut per accepted original triangle. Validate each triangle's shape and interpolate only its own corner attributes. The fresh MAIN INFRA wrapper always runs the default kernel site checks.

**Tech Stack:** Python 3.12, NumPy, existing Shapely triangle proof and repair kernel.

**Spec:** `docs/superpowers/briefs/MAIN-INFRA-E7-THREAD-20261023.md`; original E6/E7 math in `engine/fixes/merge.py`.

## Global Constraints

- Guards, default thresholds, FixProfile and Validator remain unchanged.
- Existing `thread_tolerance(quanta)` remains unchanged; no new positions.
- No full merge, region simplification, output UV fitting, E5 decisions or real-floor execution.
- Use the main `.venv/Scripts/python.exe`, this worktree PYTHONPATH and owned D: scratch.

## Review Focus

- UV seams share a geometric vertex but must keep each source triangle's distinct interpolation.
- Off-edge candidate points must not move a source cut boundary.
- Overlapped triangles must remain unchanged.
- Degenerate triangles and incomplete corner attributes must not invent a surface or appearance.
- A future planner mistake must fail the real default SiteJudge and roll back.

### Task 1: Strict original-triangle threading planner

**Files:** Create `engine/repair/engines/e7_thread.py`; create `engine/tests/test_e7_thread.py`.

**Interfaces:** `E7Thread.plan(unit: UnitState, ctx: RepairContext) -> list[Edit]`; `E7Thread.report` contains proposed/refused counts. Reuse `_thread_output`, `_barycentric`, `thread_tolerance` without changing them. Output contains existing-index cut faces, no new points, one original face and site per Edit.

- [x] Write literal fixture expectations for a minimal seam, shared UV/normal seams, winding/material, absent attributes, off-edge points, overlapped triangles and input immutability.
- [x] Run new tests and observe missing-planner failures.
- [x] Implement the smallest planner: existing threading, per-triangle overlap/outline/plane/area proof, source-corner interpolation.
- [x] Run new tests and existing seven threading fixtures; fix production code until green.
- [x] Commit planner, tests and updated ledger by named paths.

### Task 2: Always-checked MAIN INFRA API

**Files:** Create `tools/main_infra_e7.py`; extend only the new `engine/tests/test_e7_thread.py`.

**Interfaces:** `run_checked_e7(before: MeshData, looks: Looks) -> KernelResult`. It constructs default `FixProfile`, default `SiteJudge`, E7Thread and invokes kernel checks with `validate_sites=True`. It verifies that the source mesh was not mutated. It does not serialize a model.

- [x] Add visible fixture pass and real default SiteJudge rollback tests, using a deliberately faulty cut to prove rollback.
- [x] Observe the missing-wrapper failures, implement the wrapper, and run the focused tests.
- [x] Record API, outputs not yet supported and later input/serialization/native/full-validation requirements.
- [x] Run the related source geometry, kernel and attribute tests once; commit by named paths.

Baseline already measured: existing threading selection `7 passed, 56 deselected in 1.49s`. No complete-suite or real-floor claim follows from that baseline. Existing unrelated full-suite failures remain the controller's recorded baseline.

Ruling: the planner and always-checked wrapper form one reviewable safe entry; commit them together with their shared fixture tests and report. Controller approved the plan before production code.
