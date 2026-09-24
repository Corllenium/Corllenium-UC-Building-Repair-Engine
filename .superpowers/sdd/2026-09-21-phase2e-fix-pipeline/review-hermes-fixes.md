# Review 2a: Hermes's brief-07 fixes (a1e0349..4f2fe22, merged as 19f97cc)

Read-only review, 2026-09-25. Scope: `git diff c04a260..4f2fe22` (the branch forked at cb8b04d, one
commit before c04a260) and the merge 19f97cc. Commits: a1e0349 (C2), 63eabfc (I2 + M8), 0b4b8e9 (M2),
ba61235 (M3 + M4), f285ef3 (M2 again + M7), 4f2fe22 (report). Every `file:line` is at 4f2fe22; the
merge changed no engine line after it.

## Verdict: Changes required

**Findings: 1 Critical, 1 Important, 11 Minor.**

Most of the brief is done well:
- The own-pixel rule, the per-view cap, the removal list, the failed-run `.skp` handling and
  `PX_GROWN` are implemented as the brief asks, and each is pinned by a test that fails when it is
  removed.
- The T-junction join is also correct in code.

Two things block approval:
- **The sliver path still ships a hole in real surface with `passed = True`** at the real files'
  scale (C1). The new width bound narrowed the old rule but did not close this, and the new
  comments claim it did.
- **No test pins the T-junction join** that gives a1e0349 its name (I1).

## How it was checked

- A detached worktree at 19f97cc, with `PYTHONPATH` pinned (`engine.__file__` confirmed inside it):
  **431 passed in 69.23 s, 0 skipped**. That matches the report's count.
- The review's probes were run against 19f97cc:
  - `probe_fragment_patch.py`: the patch is kept, `n_components` is 1, `passed` is True, and a ray
    down through the patch hits z = 0.
  - `probe_failed_run_skp.py`: exit 2, and the owner's copy is untouched (27 bytes). The file is
    written as `box_with_partition.fixed.FAILED.skp`, and `copied_to` names it.
  - The four brief-02 probes print their defects unchanged, as expected: that is brief 02's scope.
- **Mutation copies.** I exported `engine/` at 19f97cc with `git archive` into the scratchpad (not
  worktrees) and disabled one fix per copy (`apply_mutations.py`, results in `mutations.txt`).
- **Experiments** (scripts beside this file): E2/E2b interior strip, E3/E3b T-junction stub, E4
  bbox, E5 helpers, E6 determinism, E-img guard images. All inputs are synthetic.
- **Not done, by rule:** no real data was run, the CLI was not run on real data, the SketchUp GUI
  was not opened, and the API tests were not run. So statements about the real files below rest on
  the report and the code, and are marked unverified where they matter.

## Item by item

| Item | Status | One line |
|---|---|---|
| C2 | **Partial** | Joins across T-junctions and coplanar contact are done, at `1.5 x quanta.max()`, the tolerance `analyse_topology` uses. The own-pixel rule, the per-view cap and the `fragment_removals` list in report.json are also done. But sandwiched slivers still ship holes (C1), the T-junction join is untested (I1), and the real-file report is partial: no close-up renders, the old set is not judged in the report, and "none real surface" is unsupported. |
| I2 | Complete | The file is copied only on pass, `.fixed.FAILED.skp` is written on failure, and `skp.copied_to` names it. The CLI line prints that path. Small gaps are in Minor 8. |
| M8 | Complete, untested | `report.json` is unlinked before the exports (`cli.py:382`), and `_write_skp` catches `Exception` (`cli.py:344`). No test covers either. |
| M3 | Complete in code; report short | `PX_GROWN` is a failing base, excused by the ring and the border shift, symmetric to a loss. The re-class count per file that the brief asked for is not reported. |
| M4 | Partial | Hermes chose the docstring route. Only `compare_views` now says "clearance"; `classify_pixels` and the comment at `compare.py:587` still say "really moved". |
| M2 | Complete for the brief's test | The bbox of used vertices can now fail (one-face mesh). It can also fail a legitimate merge (E4). The second commit's reason (a red suite) is not recorded. |
| M7 | Partial | The `polygon_edges` docstring is fixed. `qa_render.py:6` and `cli.py:397-399` still say the sheet shows "the edges SketchUp will draw". |
| M6 | **Missing** | `skp_writer.py:120-126` is unchanged and still cites the stale sweep (A 73, B 9). The report says only "Verified". |
| Finish | Partial | Missing: the SketchUp audit (`skp_edge_audit.py`), the two QA images read, close-up renders, and the grown re-class count. |

---

## Critical

### C1. A sliver sandwiched inside a surface is still removed, and at the real files' scale the slit ships with `passed = True`

**Where:**
- `engine/detectors/fragments.py:370` is the sliver rule: quality under 0.02, area at most 4 sq in,
  width at most 0.15 in. Nothing in it asks whether the face is on the surface's border.
- `fragments.py:60-63` and the profile comment at `engine/fixes/pipeline.py:143-148` justify the new
  bound. They say every point of a sliver lies within its width of the surface left on either side,
  so "a sliver's removal is a change the rest of the engine already names and bounds" (a border
  shift of at most 0.15 in).
- `engine/tests/test_fragments.py:269-273` asserts that the detector names
  `slab_with_interior_strip(width=0.1)` a sliver (comment: "within the bound: a ragged edge").
  - That fixture's own docstring says the strip "shares all three edges with the fat triangles
    around it ... so removing it opens a slit `width` wide through the top".
  - The test's docstring (`:265-266`) says the same.

**Why the justification is wrong:** it holds for a sliver on a surface's border, where removing it
moves the border by at most its width. It does not hold for a sliver whose long sides are both shared
with real faces (a T-junction needle inside a wall or a walking surface). Removing that one opens a
slit onto whatever is behind the surface. The border-shift measurement then reads each lost point as
within tolerance of the remaining surface. The module's own docstring (`fragments.py:16-21`) says the
guard cannot help: at the real files' 900 x 600 guard size a pixel spans 1.5 to 3.5 in, so a
sub-pixel strip is rarely met at all.

**Failure (E2b, `e2b_interior_strip_large.py`):**
- Setup:
  - A closed 2000 x 2000 x 8 in slab: about 2 in per guard pixel, like the real files.
  - Its top carries a 29.5 in strip of walking surface, sandwiched between fat triangles (the
    test's own fixture, scaled).
  - Default guard size, `n_dirs=32`, merged engine at 19f97cc.
- Result at width 0.05, 0.10 and 0.14 in:
  - The detector names the strip a sliver, the fragment guard confirms it (0 restored), and it is
    removed.
  - `passed` is True and every invariant is True.
  - guard_final: holes 0, moved 0, `fragment_removed` 0 px. No guard pixel ever met the strip.
  - The merge was not rolled back and did not close the slit: **97 of 97 rays cast down along the
    strip pass through the top and hit the inside of the bottom at z = -8.**
- At fixture scale (E2: 40 in slab, about 0.04 in per pixel) the same strip is restored. The new
  own-pixel rule sees the inside of the shell. That is why the suite does not notice the problem.

This is review C2's failure shape: real surface named as debris, a hole to the inside, `passed` True.
The review listed the sliver rule under C2 ("the same rules also delete ... thin plate sides").

**Scope:** the rule was not introduced here. The old rule removed this strip at any width, and the
width bound narrowed it. But the new comments and test now assert that the remaining removals are
bounded border moves, and the report's verdict depends on that.

**Effect on the report's verdict:** the report says "None was real surface" for A's 14 slivers
(up to 0.047 in wide) and B's 6 (up to 0.0164 in). The only evidence is their widths, and width
cannot tell a ragged border from a sandwiched needle. Two of B's faces are an example:
- 5750 and 5751 lie in one plane, x = 2948.84, so they are not a wall's two faces.
- Each is about 129 in long and 0.016 in wide (from the report's bboxes).
- They look like needles inside a single-layer wall.
- If they are sandwiched, a 129 in hairline crack ships in the owner's current `.skp`. HANDOFF says
  those files were regenerated from 19f97cc. **Unverified:** real data was not run.

**Fix:**
1. Name a sliver only when one of its two long edges is an open border: not shared, and with no
   T-junction partner. Inside a flat region the merge's re-triangulation dissolves an interior
   needle anyway, with no area lost.
2. Alternatively, confirm each candidate by rays sampled inside the candidate itself, not on the
   pixel grid. Refuse the removal when a ray reaches a side that was unexposed on the reference.
3. Make `test_fragments.py:272` assert the opposite for a sandwiched strip. Add E2b's
   real-scale case as a test.
4. Derive the width bound from `default_collinear_tol(topo.quanta)` instead of the constant 0.15
   (Minor, but it is the bound's own argument).
5. Re-check the 14 + 6 real slivers for sandwiching and report them with close-up renders, as the
   brief asked.

---

## Important

### I1. The T-junction join, the headline of a1e0349, is not covered by any test

**Where:** `fragments.py:270-275` joins through T-junctions. The only T-junction test is
`test_fragments.py:240-248`, the infill patch.

**Evidence:**
- **Mutation:** replacing the union at `fragments.py:275` with `pass`, then running the full suite
  on that copy, gives **423 passed, 8 skipped, 0 failed**. The 8 skips are the preview-page tests,
  which need `preview/index.html`, absent from an `engine/`-only export.
- **Why the patch test does not catch it:** the infill patch is coplanar with the surround, so
  coplanar contact alone joins it. The test asserts `n_components == 1` but never
  `n_joined_by_tjunction > 0`.

**Failure, if the join regresses (E3b, `e3b_tjunction_stub_large.py`):**
- Setup:
  - A 2000 in closed slab.
  - An upright 5.7 x 0.6 in piece (3.4 sq in, extent under 6 in) stands on it.
  - Its two foot vertices lie inside the top's diagonal edge: no shared edge, no shared vertex, no
    common plane.
- **Merged code:** `n_joined_by_tjunction` is 1 and the piece is kept.
- **With the join disabled:**
  - The piece is named a fragment and removed, with `passed` True and `fragment_removed` 2 px.
  - The new own-pixel rule allows this, because what lies behind the piece (the slab top, the sky)
    is exposed.
  - For non-coplanar contact, the T-junction join is the only defence.

**Fix:** add E3 as a fixture:
- assert `n_joined_by_tjunction > 0` and that `fix_object` keeps the piece;
- use a size where the 5e-3 cap does not trip. At 40 in the cap restored the piece by itself in E3,
  which hides the defect;
- also assert `n_joined_by_tjunction` in `test_a_patch_joined_only_through_t_junctions_is_not_debris`.

---

## Minor

**1. The guard images and the preview were not updated for either guard change. This is a
regression.**
- (a) `cli.py:299-305` still calls `classify_pixels(..., removed_before=...)` without
  `exposed_after`. Under the new rule that means only the sky excuses a debris pixel.
  - E-img: `fix_object` on `slab_with_strays` passes, and guard_final view 12 counts 6
    `fragment_removed`, 0 holes, 0 moved.
  - `guard_-z.png` classes the same 6 pixels as damage.
  - The comment at `:299-300` says they are "excused here exactly as the real guard excuses them".
  - `FixResult.exposed_final` (`pipeline.py:258`, `:610`) was computed for exactly this and is
    never read.
- (b) Nothing downstream knows `PX_GROWN`:
  - `_failing_view_indices` (`cli.py:249`) omits `grown`, so a view that fails only on growth
    gets no `guard_fail_<i>.png`.
  - `save_triptych` (`engine/guard/render.py:90-93`) has no colour for code 10.
  - The preview's "damaged px" (`cli.py:568-569`) omits `grown`, so it can show FAILED with
    0 damaged px.
  - `ViewVerdict`'s comment (`compare.py:625`) still says "the three always sum to
    `edge_flicker`"; there are now four.
- **Fix:** pass `exposed_after=result.exposed_final`, and add `grown` to all three consumers plus a
  colour.

**2. M2: the new invariant fails a legitimate merge, and the reason for the second commit is not
recorded.**
- **E4:**
  - A single-layer 40 in plate with the real files' 0.1 in print step (`sig_digits=3`, collinear
    tolerance 0.15 in).
  - Its unique max-x vertex sits 0.1 in off the straight east edge.
  - The merge drops it, and the guard passes: 532 border-shift px, all measured within 0.15 in.
  - But `bbox_same` is False, so `passed` is False. With I2, the owner's file is then not
    updated.
- **Why the second commit:**
  - 0b4b8e9 left the suite red: 2 failed,
    `test_fix_object_removes_the_stray_triangle_and_the_needle_and_keeps_the_quad` and
    `test_every_removed_component_is_reported_with_its_faces_area_and_bbox`. Deleting the stray at
    the model's top shrank the used bbox.
  - f285ef3 therefore excludes every deleted face (`pipeline.py:623`). The invariant now checks
    only merge and flip.
  - Neither commit message nor the report says so.
- **Fix:** compare within `border_shift_tol`, and record why deletions are left to the guards.

**3. M4 is only partly done.** `compare.py:405-417` (`classify_pixels`) still says "the surface
under it really moved no further than that tolerance" and "the displacement is the distance". The
same paragraph does not mention grown pixels, and `:587` still asks how far the surface "REALLY"
moved. The report says the docstrings were updated, and says why only in a parenthetical in
`compare_views`.

**4. M3's requested count is missing.** The brief asked how many pixels `PX_GROWN` re-classes on
A and B. The report gives only the final `grown: 0`. Against T1:
- `border_shift` rose on A from 106 to 141, and on B from 47 to 55.
- But the shipped meshes also changed: A 1,013 to 1,019 triangles, B 601 to 593.
- So the growth share cannot be read from the report.
- Report base-`PX_GROWN` counts per file: the flicker, border-shift and crack pixels that came from
  it.

**5. M6 was not done.** `engine/io/skp_writer.py:120-126` is unchanged and still gives the sweep
from before d6ef1a9 and 28d63df ("73 in A, 9 in B"). No sweep, script or number accompanies the
report's "Verified".

**6. M7 is only partly done.** `qa_render.py:6` still says the sheet shows "the EDGES SKETCHUP WILL
DRAW", and `cli.py:397-399` says the same. The brief allowed the docstring route, but these two
still make the claim.

**7. M8 has no test.** Nothing covers a non-`SketchUpError` exception in `_write_skp`, or a QA-step
exception leaving no stale `report.json`.

**8. I2 has small gaps.**
- The `_write_skp` docstring (`cli.py:326-327`) still says "the copy replaces the previous run's".
- A `.fixed.FAILED.skp` from an earlier failed run stays beside a newer passing `.fixed.skp`.
- The CLI line names the FAILED path but does not say that the previous copy was kept.

**9. `fragment_removed_cap = 5e-3` (`pipeline.py:150-155`) does nothing on the real files.**
- It was sized to pass the 120 x 80 test fixture (1.7e-3).
- That is about 40 x the real files' measured maximum (1.2e-4).
- On A's average view of about 79,000 model px, it trips only above about 400 px of debris per
  view.
- Size it from real measurements. Where a fixture needs more, loosen the cap in that test.

**10. The report has inaccuracies and gaps.**
- It says "6 long real surface wall strips" for B but lists 4. The six are A's 3203 and 3401 plus
  B's four.
- A's one "fragment", face 4721, is not export debris:
  - its id is above the input's 4,692 faces, and its bbox is horizontal, so it is a bottom triangle
    solidify invented;
  - its area and width equal face 174's.
- The old removal set's verdict appears only in code comments:
  - real surface was removed: A 3203, 3401 and 3703, and B 692, 698, 1804 and 2734;
  - the report itself does not say so.
- There are no close-up renders, no SketchUp audit, and no QA images read.
- B's drop from 12 slivers to 6 is not reconciled; the width bound accounts for 4.
- **Process:**
  - 0b4b8e9 was a red commit.
  - M7 went into an M2 follow-up commit.
  - The commit messages have no body.

**11. Nit: the `_PAIR_BLOCK` comment (`fragments.py:96-97`) overstates what is bounded.** It says
"the pair list stays bounded". Only each block's candidates are. `_box_pairs` concatenates every
overlapping pair, and `_coplanar_contacts` processes them all at once. Peak memory on the real files
was not measured.

### Residual risk (the brief's rule, not a defect of this work)

The own-pixel rule excuses any side whose exposure on the reference is above 0. That protects only
truly closed shells:
- On the real files, interior sides are exposed through broken sides (session record section 6,
  items 1 and 4).
- A see-through slit in a single-layer surface shows sky or exposed faces.

In both cases a wrongful removal is excused, so the detector remains the only defence
(`fragments.py:16-21` says as much). That is why C1 and I1 matter.

## Checked and found sound

- **Merge 19f97cc:** a clean union. Against its first parent it adds the engine changes plus the
  report; against its second it adds the review documents. No conflict edits.
- **The fixes are pinned by tests.** Each mutation below fails a test:

  | Fix disabled | Failing test |
  |---|---|
  | Coplanar contact | `test_fragments.py:254` |
  | Width bound | `test_fragments.py:270` |
  | Own-pixel rule | `test_fragments.py:298` |
  | Fragment cap | `test_fragments.py:404` |
  | `PX_GROWN` | `test_guard.py:1785` |
  | bbox invariant | `test_pipeline.py:724` |

  The I2 test fails on the old copy logic.
- **Helpers:**
  - `_box_pairs` equals brute force in 40 random trials at block sizes of 2,000,000, 7 and 1,
    including ties along x.
  - `_triangle_gap` matches shapely's distance to 1.8e-15 on 4,000 random pairs.
- **`PX_GROWN`:**
  - It reaches only `compare_views`, `guard_feedback` and `fragment_feedback`. Removal cannot grow
    a silhouette in the last two.
  - `solidify_feedback` does not call `_classify`, so cap-guard verdicts are unchanged.
  - Its ring and border-shift handling mirrors a loss: an AFTER point is measured against the
    BEFORE triangles.
- **Final guard:** `strict_final` is True unless `--accept-slit` removed faces, so a debris pixel
  that is not excused and shows the inside of a shell does fail as `moved_same_flat`.
- **Determinism (E6):** two `cmd_fix` runs each on `slab_with_strays` and `slab_with_infill_patch`,
  with solidify on, give identical `report.json` (without runtime) and identical OBJ bytes.
- **No broken callers:** only the pipeline calls `detect_fragments` and `fragment_feedback`, so the
  new required `contact_tol` breaks nothing.
- **SketchUp writer:** unchanged.
- **The B strip claim follows from the code.** Faces 692, 698, 1804 and 2734 are 30-40 in long and
  0.19-0.26 in wide:
  - the old rule named them: quality about 0.014, area 3.84 sq in (under 4);
  - the width bound keeps them;
  - `test_fix_object_keeps_a_strip_of_real_surface` confirms this on the scaled fixture.
- **The A claim does not follow.** "15 pieces removed, none real surface" is not supported by the
  code (C1) or by any evidence in the report.

## Evidence files (this folder)

- Suite outputs: `suite_19f97cc.txt`, `suite_0b4b8e9.txt`.
- Mutations: `apply_mutations.py`, `mutations.txt`, `mut_tj_full.txt`.
- Experiments: `e2_interior_strip.py`, `e2b_interior_strip_large.py`, `e3_tjunction_stub.py`,
  `e3b_tjunction_stub_large.py`, `e4_bbox_false_fail.py`, `e5_helpers.py`, `e6_determinism.py`,
  `e_img.py`.
- To run any script: `PYTHONPATH=<a tree at 19f97cc> .venv/Scripts/python.exe <script>`.
