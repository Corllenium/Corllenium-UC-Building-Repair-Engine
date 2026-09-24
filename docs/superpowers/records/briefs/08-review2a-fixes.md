# Brief 08 — fixes from review 2a (of the brief-07 work)

Source: `.superpowers/sdd/2026-09-21-phase2e-fix-pipeline/review-hermes-fixes.md` (verdict: Changes
required; 1 Critical, 1 Important, 11 Minor). Its experiment scripts are in
`docs/superpowers/records/scripts/review2a/` (run with `PYTHONPATH=<tree root>`).

Where: main checkout, branch `feat-dashboard` (HEAD after 2c00a99). The side rebuild (brief 02) is
still running in `.claude/worktrees/side-rebuild` and changes solidify.py, the cap guard in
compare.py, pipeline.py and cli.py on its own branch: keep your hunks in other functions where you
can. Append fixtures at the END of `engine/tests/fixtures/build.py`. Test-first, one commit per
item, a message body that says why.

## Items, in this order

1. **C1 `fix(engine): a sliver is debris only when one of its long edges is an open border`.**
   `engine/detectors/fragments.py` names a face a sliver by quality, area and width alone, so a
   thin strip whose two long sides are both shared with real faces (a needle inside a wall or a
   walking surface) is removed and a slit opens onto the inside; at real-file scale (about 2 in per
   guard pixel) no guard pixel meets it: review experiment `e2b_interior_strip_large.py` (a 29.5 in
   strip 0.05-0.14 in wide in a 2000 in slab: removed, `passed` True, 97 of 97 rays pass through the
   slit). Name a sliver only when at least one of its long edges is an open border (not shared, and
   with no T-junction partner); derive the width bound from `default_collinear_tol(topo.quanta)`
   instead of the constant 0.15. Make `test_fragments.py:272` assert that a sandwiched strip is NOT
   a sliver, and add E2b's real-scale case as a test. Then re-check every sliver removed on the real
   files (A 14, B 6; B's faces 5750 and 5751, about 129 in long and 0.016 in wide in the plane
   x = 2948.84, first) for sandwiching, with close-up renders, and report which were real surface.
2. **Invented faces are never fragment candidates.** File A's removed "fragment" face 4721 has an
   id above the input's 4,692 faces: a bottom triangle solidify invented (its area and width equal
   face 174's). Faces solidify added are part of the shell being closed; exclude them from fragment
   detection (or explain with evidence why 4721 is a coincident duplicate that must go, and handle it
   as an overlap instead). Test it.
3. **I1 `test(engine): the fragment join through T-junctions is pinned`.** Disabling the T-junction
   union in `fragments.py` leaves the suite green. Add review experiment E3b
   (`e3b_tjunction_stub_large.py`: an upright 5.7 x 0.6 in piece whose feet lie inside the top's
   edge, at a scale where the fragment cap does not trip) as a test asserting
   `n_joined_by_tjunction > 0` and that `fix_object` keeps the piece; also assert
   `n_joined_by_tjunction` in `test_a_patch_joined_only_through_t_junctions_is_not_debris`.
4. **M2 `fix(engine): the bbox invariant allows the merge's own border movement`.** Comparing the
   used-vertex bbox exactly fails a legitimate merge that drops a corner vertex within the 0.15 in
   border tolerance (review E4: guard passes, `bbox_same` False, `passed` False, and with I2 the
   owner's file is then not updated). Compare within `border_shift_tol`; record why deleted faces are
   left to the guards (f285ef3 excluded them after 0b4b8e9 left the suite red). Test with E4.
5. **Minor 1 `fix(engine,cli): guard images and preview know the new pixel classes`.** `cli.py`
   calls `classify_pixels(..., removed_before=...)` without `exposed_after`, so its guard images
   class excused debris pixels as damage: pass `exposed_after=result.exposed_final`. Add `grown` to
   `_failing_view_indices`, give code 10 a colour in `engine/guard/render.py::save_triptych`, count
   it in the preview's damaged pixels, and fix `ViewVerdict`'s "the three always sum" comment (four
   now). Tests.
6. **Minors 3, 6: docstrings.** `classify_pixels` and the comment at `compare.py:587` still say the
   surface "really moved" (it is a clearance to the nearest triangle; say so, and mention grown
   pixels); `qa_render.py:6` and `cli.py:397-399` still say the QA sheet shows the edges SketchUp
   will draw (it does not: the writer hides more).
7. **Minor 5 (= old M6): re-run the `ON_FACE_TOL` sweep** in `engine/io/skp_writer.py:120-126` on the
   current output and restate its numbers, with the script that produced them.
8. **Minor 7 (M8 tests):** a non-`SketchUpError` exception in `_write_skp`, and a QA-step exception,
   leave no stale `report.json` and are recorded.
9. **Minor 8 (I2 gaps):** fix the `_write_skp` docstring ("the copy replaces the previous run's"),
   delete a stale `<name>.fixed.FAILED.skp` when a later run passes, and say on the CLI line that the
   previous copy was kept.
10. **Minor 9:** size `fragment_removed_cap` from the real files' measured per-view maximum (about
    1.2e-4), not the 120 x 80 test fixture (it now trips only above about 400 px); loosen it inside the
    test that needs more.
11. **Minor 4:** report the pixels `PX_GROWN` re-classes per file (base class counts: the flicker,
    border-shift and crack pixels that came from it).
12. **Minor 11 (nit):** the `_PAIR_BLOCK` comment overstates what is bounded; measure the peak memory
    of `_coplanar_contacts` on file A and state it.

## Finish

Suite count; both real runs and `preview-data` (main checkout; they write the owner's `.skp` when the
run passes); per file: triangles, the removal list with each piece's verdict (real surface or not)
and close-up renders of every removed sliver, grown re-class counts, every guard total, invariants,
passed; the SketchUp audit (`docs/superpowers/records/scripts/skp_edge_audit.py`); two QA images
read. Report `.superpowers/sdd/2026-09-21-phase2e-fix-pipeline/review2a-fixes-report.md` (force-add)
ending with `## Public signatures`; ledger entry; claim released.
