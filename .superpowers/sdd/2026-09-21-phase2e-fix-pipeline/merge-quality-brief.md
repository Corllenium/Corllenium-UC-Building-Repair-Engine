# Merge quality — brief (task M: one slab = one face)

Repo `D:\PROJECTS\UC MODEL FIXER`, branch `feat-dashboard`. Bash tool, POSIX syntax, repo path
`/d/PROJECTS/UC MODEL FIXER`. Python ALWAYS `.venv/Scripts/python.exe`. Do not stop/restart the running
servers (8190, 5190, 5180). Leave untracked files alone.

## Problem (measured on the real file)
`engine/topo/planes.py::cluster_planes` accepts a triangle into a region when all three vertices lie within
`1.5 * sum(|n_i| * q_i)` of the SEED triangle's plane. The seed normal carries rounding noise (coordinates are
printed to 0.1 in on Y, 0.01 in on X/Z). Over a 40 m slab that tilt exceeds the tolerance, so one SketchUp
face arrives as several regions and the viewer draws "region outlines" inside a flat slab. The user's target
is a slab with no lines inside; only real edges (creases, steps, kerbs, material borders, open edges) remain.

## M1 `fix(engine): plane regions grow with an iterative least-squares refit`
- Region growing per seed (largest triangle first, ascending region ids, deterministic): accept candidates
  (same material, `n . n_region > facing_dot`, all 3 vertices within `tol` of the CURRENT region plane), refit
  the plane by least squares (SVD on the centred accepted vertices, normal oriented like the seed), re-test ALL
  unassigned candidates against the refit plane, repeat until the member set stops changing (max 8 rounds).
  Vertices previously rejected may join later. `tol` unchanged: `tol_quanta * sum(|n_i| * q_i)` evaluated with
  the CURRENT normal. Store the final plane (n, p0) on the region; `plane_basis` and everything downstream use it.
- `build_regions`, `merge_regions`, `classify_edges`, `edge classes` unchanged in API.
- Tests, written first: (a) a 60-vertex-long slab whose vertex coordinates are rounded to 0.1 in with a
  deliberate seed triangle (the largest) placed near one end -> ONE region with the old code it would be more
  than one (assert the new code yields exactly one and that every face is in it); (b) two genuinely different
  planes meeting at a 3-degree crease -> two regions (no over-merging); (c) determinism: run twice, identical
  `face_region`; (d) all existing merge/region tests pass unmodified.
- Real data: `analyse_topology` + `merge_regions` on the same removal state the engine round used for
  `data/snapshots/ce26e0392ab0/CHTM_SIDE_WALK_2nd_floor.obj` (run `fix_object` and read `merge_report`).
  Report region count, triangles after merge, and the number of EDGE_REAL edges whose two faces are within
  1 degree of coplanar (these are the false lines inside slabs; expect near zero afterwards). Also run file B.

## M2 `feat(engine): EDGE_SOFT class for creases that cannot be merged without moving vertices`
- `engine/topo/edges.py`: new class `EDGE_SOFT = 5` for an edge with exactly two faces, same material, in
  different regions, whose dihedral angle is above `coplanar_angle` (default 1 degree) and at or below
  `soft_angle` (default 5 degrees, the project's historic limited-dissolve ceiling). Both thresholds are keyword
  arguments of `classify_edges` and fields on `FixProfile`. Edges at or below `coplanar_angle` between different
  regions are reported in `topology_stats` as `coplanar_region_borders` (a diagnostic: after M1 it should be ~0).
- `topology_stats` gains `soft_edges`. `engine/transport/meshbuf.py` edge_class values pass through unchanged
  (the viewer decides how to draw class 5). `engine/cli.py preview-data` puts EDGE_SOFT edges into a new
  `edges.soft_after` list so the preview page can give them their own toggle later (do not edit the page).
- `MergeResult.rings` gains inner loops: for every merged region, `rings[region] = {"outer": [vertex ids],
  "inners": [[vertex ids], ...]}` after the corner pass (regions with holes included; OBJ export keeps
  triangles for those, the SketchUp export will use the loops). Update `write_obj_polygons` to read
  `rings[r]["outer"]` for hole-free regions only. Tests: `slab_with_hole` -> one region with one inner loop of
  4 vertices; `grid_slab` -> outer loop of 4, no inners.
- Tests first for every rule above.

## M0 `fix(engine): a rolled-back merge keeps the guard report that failed`
`fix_object` currently replaces `guard_final` with the fallback mesh's guard when it rolls back, so the failure
that caused the rollback is invisible. Keep it: `FixResult.guard_merge_attempt` (the GuardReport of the merged
mesh vs the reference, or None when the merge did not converge), written into `report.json` by the CLI with its
per-view verdicts. Test: the existing rollback test asserts `guard_merge_attempt.passed is False`. Then run file A
(`data/snapshots/ce26e0392ab0`) and paste the failing view(s) and pixel classes: this explains why the 2026-09-23
engine round still rolled the merge back to 2,656 triangles with 0 failures in the fallback guard.

## M3 `fix(engine): ring simplification with a global deviation bound`
The corner pass tests each ring vertex against the chord of its own neighbours (distance <= 1.5 * max(q)), so a
run of nearly-collinear vertices can be dropped one after another and the final chord can deviate from the
original boundary by far more than that tolerance. The guard's ring test assumes the bound holds. Replace the
per-vertex test with Ramer-Douglas-Peucker on each ring with tolerance `1.5 * max(q)`: a vertex is dropped only
if the whole original polyline between the surviving neighbours stays within the tolerance of the new chord;
vertices in the global `needed` set are forced to survive (they split the polyline into independently simplified
runs). Deterministic (start the recursion at the ring's lowest vertex id). Test: a ring with 12 vertices on a
gentle arc, each within 0.1 of its neighbours' chord but 0.8 off the end-to-end chord -> the old rule would keep
only the ends; the new rule keeps enough vertices that no original vertex is farther than the tolerance from the
simplified ring (assert the max deviation). Real data: file A merge must now pass the final guard or the M0
report must show exactly which pixels still fail and why.

## M4 `fix(engine): z-fight ties are not damage`
Measured on file B (`data/snapshots/0b290ec0bcb4`, view `(1.013, 1.007, 0.011)`): 12 `material_changed` pixels
where BEFORE hits face 2654 (material 1) and AFTER hits face 73 (material 0) at the SAME depth (5867.73 in
both), and neither face was removed. They are coplanar overlapping faces of different materials (a real
z-fight defect, to be resolved later by the overlap detector); rebuilding the ray structure with a different
face set changes which one wins. The guard must not call that a change:
- Add `all_hits(origins, directions) -> (ray_index, tri, t)` to the `RayCaster` protocol, `EmbreeCaster`
  (`intersects_location(multiple_hits=True)`), `BruteCaster` and `ReusableCaster`.
- New pixel class `PX_ZFIGHT_TIE`: for a would-be `material_changed`, `moved_same_flat` or `moved_other` pixel,
  collect BEFORE's hits along the centre ray with `|t - t_first| <= depth_tol` (the BEFORE tie set) and AFTER's
  likewise. The pixel is a tie iff AFTER's first hit matches a member of BEFORE's tie set (same material, hit
  point within `depth_tol` of that member's plane) AND BEFORE's first hit matches a member of AFTER's tie set.
  Both directions, so a removed member is still a failure. Ties are never failures at any cap and are reported
  as `zfight_tie` in totals (they are evidence for the overlap detector).
- Evaluate ties before the ring test. Tests: two overlapping coplanar quads of different materials, AFTER =
  same geometry with the face order reversed so the tie flips -> `zfight_tie`, passed; AFTER with one member
  removed -> `material_changed`, failed; same-material coincident pair with one removed -> no change at all.
- Real data: file B `guard_after_removal` must reach 0 failures with `zfight_tie` about 12; then report whether its
  merge passes.

## M5 `fix(engine): a closed crack is an improvement, not damage`
Measured on file A (`data/snapshots/ce26e0392ab0`), the ONLY pixel that rolled the merge back: view
`(-0.987, 0.007, -0.989)`, pixel `(530, 338)`. BEFORE hits ramp face 2540 at t = 3318.66; the merged mesh hits
region face 938 (189 source faces) at t = 3302.35, 16.3 in closer. A scan at 0.02 in steps shows only 2 of 201
BEFORE rays reach the ramp: the centre ray passed through a crack about 0.02 in wide (a T-junction gap).
14 of 16 ring rays (radius 0.15 and 0.075 in) already hit the region surface in BEFORE. The merge closed the
crack. Rule: after the z-fight tie test and before the ring flicker test, for any would-be failure pixel cast
the 16 BEFORE ring rays; if at least 12 reproduce AFTER's centre verdict (same material, hit point within
`depth_tol` of AFTER's centre-hit face plane, or a miss when AFTER's centre is a miss), classify
`PX_CRACK_CLOSED`: BEFORE's centre was a sub-tolerance crack or sliver hit. Never a failure at any cap;
reported as `crack_closed` in totals (a positive metric: sparkle pixels removed). This also covers a removed
sub-pixel sliver of a different material. Document the limit: damage narrower than the ring radius is
indistinguishable from a closed crack. Test: a slab of two big triangles with a 0.02 in gap between them over a
lower surface, AFTER = the gap closed -> `crack_closed` on the gap pixels, passed; AFTER = one whole triangle
removed -> failure. Real data: file A merge must now pass; report `crack_closed` for both files.

## R1 fixes (from the review of the orientation / polygon export / CLI batch)
R1a `fix(engine): thin sheets are never flipped` — `classify_orientation`: THIN_SHEET (both sides exposed,
`min/max >= sheet_ratio`) takes precedence over FLIP; FLIP only when not a thin sheet and `back > front`.
The review found about 35 genuine thin sheets flipped on file A (`n_thin_sheets` 47 where 82 were measured),
each opening a one-sided hole. Test with a free-standing quad seen from both sides. Report the new
`n_flipped` / `n_thin_sheets` / `one_sided_holes_after` on file A.
R1b `fix(engine): unavoidable diagonals are classified by region id, not array identity` — `engine/cli.py`
`_after_edges` tests `src[a] is src[b]`, but `fix_object` rebuilds `source_faces` with `.astype`, so the
identity never holds and `tri_after` is always empty: every triangulation diagonal is drawn as a real edge.
Add `FixResult.face_region_final` (int64 over final faces, -1 for copied-through faces, from the merge) and
classify an edge as an unavoidable diagonal when both faces share a region id >= 0. Test: preview-data on a
merged fixture asserts `tri_after` non-empty, `unavoidable_diagonals_after > 0`, and `outline_edges_after`
equals the ring edge count.
R1c `fix(preview): page text reads the real numbers` — `preview/index.html` (the only file outside `engine/`
this task may edit): remove the hardcoded "guard 0 damaged px" and the "rough preview ... flattens vertices"
sentence; show the guard totals, `crack_closed`, `zfight_tie`, `soft_edges`, and whether the merge was rolled
back, from `stats`. Add a "soft creases" toggle reading `edges.soft_after`.

## R2 fixes (from the review of the 2026-09-23 engine round) and E4 concerns
R2b `fix(engine): the ring test cannot be skipped silently` — `compare_views` skips the ring when
`plane_before` / `plane_after` are None even though `edge_flicker_cap > 0`; the `ValueError` only checks
geometry. Compute the planes from `geometry_before` / `geometry_after` inside `compare_views` when they are not
supplied; raise `ValueError` when a cap above zero is requested and neither planes nor geometry exist.
R2c `test(engine): ring tests say what they test` — remove comments that still describe the deleted 3x3 / 5x5
rule; make `_flicker_report` supply planes (or geometry) so every flicker test actually reaches the ring; add a
test for an interior hole whose rim is flanked by coplanar same-material survivors (cond 1 of the ring test is
satisfied there, cond 2 must not be): it must stay a hole at any cap.
R2d `fix(engine): only a failing base class is ever promoted` — E4 measured a regression: with `strict=False`,
991 `moved_same_flat` pixels are tolerated, but 15 of them were re-classed `edge_flicker` and then capped in a
9,291 px view (cap 1e-4 allows 0.93 px), so an `--accept-slit` run that passed before now fails. Rule: ties
(M4), crack-closed (M5) and ring flicker are evaluated ONLY for pixels whose base class fails under the current
strictness: hole, material_changed, moved_other, and moved_same_flat only when strict. A tolerated base class
keeps its class. Test: a non-strict report with moved_same_flat pixels on a silhouette reports 0 flicker and
passes at cap 0.0.
M0 extension `feat(engine): CLI writes a triptych for every failing view` — besides the six axis views, write
`guard_fail_<index>.png` for every view with any failure or flicker in `guard_merge_attempt`,
`guard_after_removal` or `guard_final` (E4 could not show the failing oblique views).

## After the guard round (2026-09-23): two hardening items for this round
M4b `fix(engine): tie sets are found by geometry, not vertex sharing` — trimesh's `multiple_hits=True` cannot
return two hits at one depth, so the guard round's `all_hits` recovers coincident faces by looking at faces that
share a vertex with the hit triangle; a coincident face sharing no vertex is missed (reported as damage, so safe
but wrong). Replace the recovery with geometry: candidate faces = faces whose plane contains the hit point within
`depth_tol` AND whose triangle contains the point in its own plane (point-in-triangle with a `depth_tol`
margin), found with a bounding-box prefilter over all faces (numpy mask; only failing pixels reach this code).
Test: two coincident quads triangulated so that no vertex is shared -> tie detected.
M0b `fix(engine): failing-view images only for real failures` — `FixResult` records `strict_final`; the CLI
writes `guard_fail_<index>.png` only for views with a failure under that strictness or with flicker counted
against the cap, never for tolerated base classes (non-strict runs wrote 13-18 images of tolerated pixels).

## Finish
Whole engine suite (`.venv/Scripts/python.exe -m pytest engine/tests -q`, real count). Re-run
`python -m engine.cli fix data/snapshots/ce26e0392ab0 --out data/output` and the same for
`data/snapshots/0b290ec0bcb4`, then `preview-data` for both into `preview/data`. Report per file: regions
merged, triangles after merge, `coplanar_region_borders`, `soft_edges`, guard totals, passed. Write the report to
`merge-quality-report.md` next to this brief, ending with `## Public signatures`. Commit messages as given, trailer
`Co-Authored-By: Claude Fable 5.1 <noreply@anthropic.com>`. Edit only files under `engine/`.
