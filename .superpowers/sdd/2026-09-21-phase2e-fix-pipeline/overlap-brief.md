# Overlap resolution — brief (task O: remove stacked duplicate layers so the merge can run)

Repo `D:\PROJECTS\UC MODEL FIXER`, branch `feat-dashboard`. Bash, POSIX syntax, repo path
`/d/PROJECTS/UC MODEL FIXER`. Python ALWAYS `.venv/Scripts/python.exe`. Do not touch the running servers.
Leave untracked files alone. Edit only files under `engine/`.

## Measured (file A, `data/snapshots/ce26e0392ab0`, 2026-09-23)
After the merge-quality round: 1,674 final triangles, of which 914 were copied through unmerged (234 top,
179 side, 501 underside); `regions_skipped = {overlap: 9, invalid_polygon: 3}`. On the removal-stage mesh
(2,656 faces) there are 120 overlapping coplanar pairs, ALL the same material, involving 133 faces in 25
regions (worst regions 16, 11, 7, 7, 7 pairs). The walkway carries a second copy of its own surface. The
merge excludes overlapping triangles (rule 3) and skips regions whose union still overlaps, so the walkway
keeps every triangle and their edges are drawn. File B has 14 different-material overlaps (z-fight ties).

## O1 `feat(engine): remove covered same-material duplicate layers under the strict guard`
New `engine/fixes/overlap.py`, run in `fix_object` after hidden/slit removal and flipping, BEFORE the merge:
1. `find_overlaps(mesh, topo) -> list[(i, j, area, same_material)]` over each region's triangles projected to
   the region plane (STRtree + intersection area above `1e-6 * min(area_i, area_j) + 1e-9`); factor the
   merge's own rule-3 overlap test into this function so both use one implementation.
2. Per face in an overlapping pair: `covered = area(face ∩ union of the OTHER faces of its region) / area`.
   Same-material candidates = faces with `covered >= 0.99`. Between two mutually covered twins, drop the one
   in the smaller connected patch of candidates (edge adjacency); on a tie, the higher original face id.
   Deterministic order.
3. Remove candidates through `guard_feedback(strict=True)` exactly like hidden faces (a coincident twin cannot
   change a pixel; the z-fight tie rule already tolerates the tie flip). Restored ones stay and are reported.
4. Different-material overlaps are never removed here: report them as `overlap_pairs_diff_material` with
   face ids and materials (input for the later preference-driven resolution).
5. `FixResult` gains `removed_overlap` (bool over original faces), `n_overlap_pairs_same`,
   `n_overlap_pairs_diff`, `n_removed_overlap`, `n_restored_overlap`; `report.json` and `preview-data` stats
   carry them. Rerun `analyse_topology` after the removal before the merge.
Tests, written first: a slab whose top layer is duplicated exactly (same material) -> one layer removed,
`n_restored_overlap == 0`, merge yields one region of 2 triangles; a partial overlap (30 % covered) -> not a
candidate; a different-material overlap -> nothing removed, reported; determinism; guard invariance (the
final guard against the original passes with zfight ties only).
Real data: file A must show `regions_skipped.overlap` near 0, `faces_copied` far below 914, and fewer
triangles than 1,674; file B likewise; both guards passing. Report the numbers.

## G1-G3 (guard follow-ups from the guard-round review), do these AFTER O1
G1 `fix(engine): crack tolerance has a ceiling and a cap` — `FixProfile.depth_tol_max = 0.5` in;
`depth_tol = min(1.5 * max(axis quanta), depth_tol_max)`; `crack_closed` counted against a per-view
`FixProfile.crack_closed_cap` (default 1e-3 of the view's model pixels) like flicker; above the cap the pixels
fall back to their base class and fail; `zfight_tie` stays uncapped and reported. Tests for the clamp and the cap.
G2 `fix(engine): the removal guard classifies ties and cracks like the merge guard` — `guard_feedback` uses
the same classification with cap 0.0 (flicker fails there; ties and closed cracks are tolerated); fix the
docstring that claims they already agree. Test: a removal whose only changed pixel is a z-fight tie restores nothing.
G3 `test(engine): tie recovery rejects a coplanar triangle that does not contain the hit point`.

## Finish
Engine suite (real count); `python -m engine.cli fix` and `preview-data` for both files; report the numbers
above plus guard totals; write `overlap-report.md` next to this brief ending with `## Public signatures`.
Commit messages as given, trailer `Co-Authored-By: Claude Fable 5.1 <noreply@anthropic.com>`.
