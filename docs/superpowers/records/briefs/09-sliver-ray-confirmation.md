# Brief 09 — confirm every debris removal with rays through the piece itself

Source: brief 08's report `.superpowers/sdd/2026-09-21-phase2e-fix-pipeline/review2a-fixes-report.md`
(concern 1 and the per-piece verdicts) and review 2a (`review-hermes-fixes.md`, C1 fix alternative 2).

Where: main checkout, branch `feat-dashboard` (HEAD after 64023ad, 462 tests). The side rebuild
(brief 02, SR6) runs in `.claude/worktrees/side-rebuild` and changes `engine/fixes/solidify.py` and
the cap guard: do not edit those. Append fixtures at the END of `engine/tests/fixtures/build.py`.
Test-first, one commit per item, message bodies that say why.

## Why

Brief 08 re-judged the 21 pieces the fragment pass had removed at 670ad50: **10 were real surface**
(thin risers, a rim band of needles, a fold pair closing the top of a ramp side wall) and each shipped
a hairline crack onto the inside of the model, while every guard passed, because at real-file scale
(1.5 to 3.5 in per guard pixel) no guard pixel meets a strip 0.001 to 0.05 in wide. The open-border
rule (536fca7) now keeps them, but two still ship slots on file A: face 3540 (rim lip, 0.0015 x 16 in:
303 of its lines, 1.6%, reach unexposed sides through coplanar face 3435, which the hidden pass
removed) and face 4659 (0.0034 x 15 in: 4,608 lines, 28%, reach unexposed sides even with the hidden
faces kept). Their free edge is open in the reference, so the open-border rule names them. Pixels
cannot judge a sub-pixel piece; rays through the piece can.

## Items

1. **`fix(engine): a debris removal is confirmed by rays through the piece itself`.** For every
   fragment or sliver candidate, sample points on the candidate (area-stratified; say how many and
   why) and cast, from each exposure direction that reaches the candidate from outside, the ray that
   first hits the candidate on the reference; with the candidate removed, follow that ray on: if it
   reaches a face SIDE that was unexposed on the reference (the inside of a shell), refuse the
   removal. Use the existing ray casters (`engine/rays/`) and exposure data; no pixel grid. Report per
   candidate the lines tested and the lines that reached an unexposed side. Tests: review experiment
   `e2b_interior_strip_large.py` (a sandwiched strip in a 2000 in slab) is refused; a rim-lip slot
   like A 3540/4659 (a sliver whose free edge is open but which covers a slot onto the inside) is
   refused; a free needle pointing into the sky is removed; a double layer lying on a coplanar face
   (A 49/174 kind) is removed; determinism.
2. **Folds.** Two triangles folded onto the same side of their shared edge, covering the same area
   twice (file B faces 5750/5751 at x = 2948.84, which together close the top of a ramp side wall and
   now show as two visible lines of 85.9 + 43.0 in in the `.skp`; also B's merge region 79, OBJ lines
   10834 and 11402, 47.7 sq in covered twice): detect them and resolve each fold by removing the
   redundant member only when item 1's ray check confirms nothing reaches the inside; report the
   ones left. Test with a folded pair fixture.
3. **Keep the review scripts runnable.** `detect_fragments` now requires `max_width`, so
   `docs/superpowers/records/scripts/review2a/e3_tjunction_stub.py` and `e3b_tjunction_stub_large.py`
   fail at their own call; update them (they are evidence scripts, not tests).

## Finish

Suite count; both real runs and `preview-data` (they write the owner's `.skp` only on a pass); per
file: triangles, the removal list with each piece's ray verdict (lines tested, lines reaching an
unexposed side), the folds resolved and left, every guard total, invariants, passed; the SketchUp
audit (`docs/superpowers/records/scripts/skp_edge_audit.py`); close-ups of A 3540, A 4659 and the B
fold after the change, read and described. Report
`.superpowers/sdd/2026-09-21-phase2e-fix-pipeline/sliver-rays-report.md` (force-add), ending with
`## Public signatures`.
