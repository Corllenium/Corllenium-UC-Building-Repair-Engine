# Brief 02 — SR: rebuild broken slab sides as clean walls, faces outward

**Status (2026-09-24 18:40):** worktree `D:\PROJECTS\UC MODEL FIXER\.claude\worktrees\side-rebuild`,
branch `feat/side-rebuild` (synced with feat-dashboard at `ce79c44`, which does NOT yet contain the
writer softening 8ee9e4d or the T-junction threading 28d63df; do not merge them in, the
reconcile job does). SR0 committed `ff4a0ec` (`feat(engine): count back faces seen from outside`).
SR2 is written but **not committed** (engine/cli.py, engine/fixes/pipeline.py,
engine/fixes/solidify.py, engine/guard/compare.py, engine/tests/fixtures/build.py,
engine/tests/test_cli.py, engine/tests/test_solidify.py). Measured with it: back faces seen from
outside A 119,610 -> 29,225 px, B 21,959 -> 5,258 px, both passed, **but file A's merge rolls back**
(2,668 triangles instead of about 900). First: if the SR2 tests pass as they stand, commit SR2; then
find the rollback's cause from the merge-attempt guard's report (which views, which pixel classes,
where) before changing anything. A rolled-back merge is not an acceptable end state.

Work only in that worktree. Python: `"/d/PROJECTS/UC MODEL FIXER/.venv/Scripts/python.exe"` with `-m`
from the worktree root; `PYTHONPATH` = worktree root for plain scripts. Snapshots exist only in the
main checkout: run `-m engine.cli fix "D:/PROJECTS/UC MODEL FIXER/data/snapshots/<id>" --out
data/output --skp-dir "OBJ FIXED RESULT"` from the worktree root so outputs stay in the worktree.
Do not edit `engine/fixes/merge.py` or `engine/io/skp_writer.py`.

## The owner's complaint

SketchUp screenshots of the cleaned file: a slab side along one edge is a jagged sawtooth of faces
showing the purple BACK side, with gaps you see through, plus interior walls and floating thin slabs
visible inside. "this is still broken and not yet completed on building it, this is the part you
will build the mesh and fixed". Located: file B, under the slope between the upper landing and the
lower slab in the middle of the model (a row of triangular teeth with gaps; render
`render_skp.py` of B's `.skp`, view `side_low_a.png`).

Cause: `engine/fixes/solidify.py` adds a wall only along OPEN outline edges of top regions, and its
cap guard (`solidify_feedback` in `engine/guard/compare.py`) refuses any new face that would cover an
original face whose original exposure is 0.10 or more. A side that exists but is broken is visible,
so it is preserved, and the interior seen through its gaps stays too. Measured before SR: file A's
cap guard refused 133 of 290 new faces in its first round (25,672 changed pixels), file B 67 of 276.
Also from the merge round: on file B, region 38 is two original side-face triangles with a solidify
wall laid over them, because solidify took that side face's top edge (used by one face only) for an
open edge; an existing side is not an open edge.

## Items (test-first)

- **SR0** (done, ff4a0ec): `backface_px` for input, reference and final mesh over the 26 guard views.
- **SR1** (investigation): for every wall face the cap guard refuses, classify what its failing
  pixels covered: (a) broken side piece within a few inches of the wall plane, roughly parallel;
  (b) interior face inside the slab volume (under the top region's footprint, above its measured
  bottom depth, behind the wall plane); (c) something outside the slab volume. Counts, distances,
  positions; close-ups before/after with back faces tinted purple; explicitly the sawtooth spot.
- **SR2** `feat(engine): solidify rebuilds a broken side instead of preserving it`: walls along
  every outline edge whose side is missing OR broken, down to that edge's measured height; class (a)
  pieces inside `FixProfile.side_band` (default from SR1's measured distribution, documented
  ceiling) are REPLACED (removed with the wall's acceptance); class (b) may be covered whatever their
  exposure (the hidden-face step then removes them); class (c) never covered. The cap guard gains
  exactly these two named allowed changes and still fails anything else. Top faces never removed or
  covered. Report `sides_rebuilt`, `side_pieces_replaced`, `interior_faces_covered`,
  `walls_refused` with reasons. Tests: sawtooth side within 1 in of the wall plane with a gap ->
  clean wall, sawtooth removed, interior hidden and removed, back faces 0; a railing or wall
  standing OUTSIDE the edge -> never covered; a partial side -> the rest built; determinism.
- **SR3**: with slabs closed, report `backface_px` and thin sheets before/after; if closed slabs
  still show back faces from outside, fix `engine/fixes/orient.py` test-first under
  `fix(engine): faces of a closed slab face outward`.

## Added from review part 1 (2026-09-24 19:45; `review-since-b2134e9.md`, probes in `docs/superpowers/records/scripts/review-probes/`)

- **SR4 = review C1** `fix(engine): the cap guard measures back-side covers`: rule 2 of the cap guard
  (`compare.py` `back_side = covered & (normal @ direction > 1e-9)`, never bad) lets an invented face
  cover any back-side hit unmeasured, which contradicts the double-sided decision. Probes:
  `probe_reversed_underside.py` (S-C1's fixture with the real underside wound +z: the real underside
  is deleted, the invented one at -9.8 in ships, passed True) and `probe_duplicate_skirt.py` (a skirt
  laid exactly over an existing side wound inward: a z-fighting double layer, passed True). Fix: judge
  a back-side hit by the ORIGINAL-mesh exposure of the side the ray met (`compute_side_exposure`'s
  back half is already computed and thrown away); exempt only the backs of the shell being closed (the
  region's own top faces and the side faces its heights were measured from); refuse any new face that
  coincides with an existing face (coplanar-overlap test, e.g. `engine.fixes.overlap.find_overlaps`,
  not pixels); do not treat an outline edge as open when existing side faces cover it through
  T-junctions (`_open_edges`). Both probes become regression tests.
- **SR5 = review I1** `fix(engine): an open edge takes its height from the slab's own sides`:
  `solidify.py` takes an edge's height from the deepest side face at either endpoint, so a 2 in slab
  whose corner touches a 30 in wall becomes a 30 in box (`probe_deep_corner.py`, passed True). Take
  the height only from side faces hanging from this region's outline (sharing an edge with a region
  face, or starting at the region's top along the outline), the shallowest of them; place the bottom
  no deeper than the shallowest existing side of the region, closed sides included; report every
  region whose skirt or bottom is deeper than its own existing sides.
- **M1**: the S-I2 test reaches the cut-off path with 0 rounds; add a `max_rounds=1` case asserting
  `history[-1]` is round 1 with 0 failing, 0 removed, and `cap_guard_passed` True
  (`probe_cap_rounds.py`).

## Finish

Suite count; both real runs in the worktree; per file: triangles, sides_rebuilt,
side_pieces_replaced, interior_faces_covered, walls_refused, hidden removed, thin sheets,
backface_px input/reference/final, every guard's totals, invariants, passed, merge rolled back (must
be no); audit both `.skp` with `docs/superpowers/records/scripts/skp_edge_audit.py`; read three QA
images per file and the SR1 close-ups after the change; byte-identical `report.json` on two runs of
A. Report `.superpowers/sdd/2026-09-21-phase2e-fix-pipeline/side-rebuild-report.md` in the worktree
(force-add), ending with `## Public signatures`. If SR1 shows the problem is something else, stop
after SR1 and report.
