# Task 5 fix round 1 — brief

Repo `D:\PROJECTS\UC MODEL FIXER`, branch `phase2e-fix-pipeline`. Bash tool, POSIX syntax, repo path
`/d/PROJECTS/UC MODEL FIXER`. ALWAYS `.venv/Scripts/python.exe`. 96 tests pass before you start.

Read first: `task-5-brief.md`, `task-5-report.md`, `task-3-4-report.md` (section `## Public signatures`) in this
folder, then `engine/fixes/merge.py`, `engine/guard/compare.py`, `engine/guard/views.py`, their tests.

Rules: TDD per item (failing test first, run, see it fail, implement, pass). One commit per item with the given
message and the trailer `Co-Authored-By: Claude Fable 5.1 <noreply@anthropic.com>`. No refactors beyond the items.
`engine/` imports nothing from `api`, `spike`, fastapi, sqlalchemy; `trimesh`/`embreex` only inside `engine/rays/`.
Vertices are never moved or invented. No randomness in production code. Do not touch `spike/`, `preview/`, `docs/`.
Never dispatch subagents. If items are already committed (check `git log --oneline 1c85bb8..HEAD`), skip them.
Append to the report after EACH item.

Before changing anything, save a baseline of the real-data run (script from the Task 5 report, file
`data/snapshots/ce26e0392ab0/CHTM_SIDE_WALK_2nd_floor.obj`): tris after merge 2,123, guard totals holes 1 /
moved_same_flat 676.

## G1 `fix(engine): guard measures surface displacement, not depth along the ray`

Finding: the guard compares first-hit depth along the camera ray. When the ray skims a surface at under 5 degrees,
a plane offset of 0.005 in becomes a depth change of 0.5 in, so a correct re-triangulation is reported as "moved"
(676 px on the real model). The metric is wrong, the merge is not.

Ruling:
- New displacement metric for pixels where BEFORE and AFTER both hit:
  `d = max( dist(P_before, plane(face_after)), dist(P_after, plane(face_before)) )`, where `P = origin_px + t * view`
  is the hit point and `plane(face)` is the plane of that face's triangle (from the geometry it was rendered with).
  `moved` when `d > depth_tol`. A removed face that reveals a surface behind it still fails at any viewing angle
  (the before point is far from the revealed plane). A coplanar re-triangulation does not.
- `ortho_first_hit` must make hit points recoverable: return, or expose through a small dataclass, the per-pixel ray
  origins and the unit view direction it used. Keep `(depth, tri)` available so existing callers and tests change as
  little as possible. If a face's plane is undefined (zero-area), fall back to `|t_before - t_after|`.
- `classify_pixels`, `compare_views`, `guard_feedback` take what they need to evaluate the metric (both geometries'
  positions and faces, or precomputed plane arrays). You fix the exact signatures and document them.
- Verdict precedence stays: hole, material_changed, moved_same_flat, moved_other.
- Tests, written first:
  1. A large flat quad rendered from a view 1 degree above its plane. AFTER = same quad shifted 0.01 along its
     normal. Old metric would exceed `depth_tol = 0.15`; assert the new metric reports 0 moved pixels.
  2. Same grazing view, AFTER = the quad removed, revealing a parallel quad 10 units behind: assert moved/hole
     failures > 0. This pins that grazing views do not hide real damage.
  3. Every existing guard test still passes unmodified, or, where a signature had to grow, with only the call
     updated and the same assertions.

## G2 `fix(engine): silhouette flicker is its own guard class`

Finding: 1 "hole" pixel on the real model sits on the silhouette, where a boundary moving 1e-3 in against a 2.1 in
pixel flips one sample.

Ruling:
- New code `PX_EDGE_FLICKER`: a pixel that would be a hole AND whose 3x3 neighbourhood in BEFORE contains at least
  one miss. `ViewVerdict` gains `edge_flicker`.
- `compare_views(..., edge_flicker_cap: float = 0.0)`: per view, `edge_flicker` is tolerated only while
  `edge_flicker <= edge_flicker_cap * model_px`. With the default 0.0 every flicker pixel fails exactly like a hole,
  so hidden-face removal keeps its zero-tolerance behaviour. `guard_feedback` always uses 0.0.
- Interior holes (no miss in the 3x3 BEFORE neighbourhood) always fail, in every mode.
- Tests first: silhouette pixel classed `edge_flicker` and failing at cap 0.0, passing at cap 1e-4 when within the
  cap, failing when above it; an interior hole fails at any cap.

## M1 `fix(engine): no interior pins in merged regions`

Finding: 2,123 tris instead of <= 2,073 because `_insert_pins` keeps 37 vertices in the INTERIOR of regions where a
wall stands on a slab.

Ruling: remove interior pinning. A wall resting on the interior of a slab needs no shared vertex: the slab surface is
continuous beneath it, perpendicular contact cannot open a crack, and an interior vertex makes it impossible to
export the region as one polygon later. RING vertices used by other faces stay needed exactly as now.
- The fixture row for `slab_with_wall()` in the plan was wrong. New expectation: the wall foot that lies on the
  slab BORDER survives in the slab's triangulation; the foot on an INTERIOR grid vertex does not have to, and the
  slab merges to the same triangle count it would have without the wall plus what the surviving border vertex costs.
  Hand-count the expected number, state the count and the reasoning in a comment above the assertion.
- Real data must now land at or below 2,073 (the implementer measured 2,051 with pins off).

## M2 `fix(engine): late-skipped regions feed back into the corner pass`

Finding: regions that fail rule 6, 7 or 9 AFTER the global corner pass are copied through with all their vertices,
while their neighbours have already dropped shared border vertices. That can create the T-junctions the kernel
promises not to create (194 faces on the real model were copied through late).

Ruling: fixed-point loop. When a region is skipped late, all its vertices join the `needed` set and pass 2 (ring
simplification + triangulation) reruns for every region, until a round produces no new late skip. Bound it at 10
rounds and report the round count. Deterministic: same order every round.
- Test first: a fixture where region A is forced to skip late (for example a region whose simplified polygon is
  invalid: build one deliberately, or monkeypatch the validity check for one region id in the test) and neighbour B
  shares a border with collinear vertices: assert B keeps every border vertex it shares with A, and that no vertex
  of A lies strictly inside one of B's boundary edges without being one of B's vertices.
- Report `merge_rounds` in `MergeResult.report`.

## Finish

Whole suite, real count. Real-data run again on file A, same script: report tris after merge, regions merged,
skipped by reason, vertices dropped, `merge_rounds`, and the guard of MERGED vs ORIGINAL in two modes:
`strict=True, edge_flicker_cap=0.0` and `strict=True, edge_flicker_cap=1e-4`, every total for both. Then the
hidden-removal feedback once more with the new metric: candidates, restored, removable (it was 1,853 / 34 / 1,819
with the old metric). Whatever the numbers are, report them. Do not tune anything to reach a number.

Append everything to `task-5-report.md` under `## Fix round 1`, ending with an updated `## Public signatures` for
every signature that changed. Return ONLY: status, commit hashes in order, full-suite summary line, the real-data
numbers listed above, concerns.
