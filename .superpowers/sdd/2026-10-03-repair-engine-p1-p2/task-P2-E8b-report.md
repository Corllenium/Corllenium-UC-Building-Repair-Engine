# Task P2-E8b report: the narrow flat fill — NEEDS_CONTEXT

**Status: NEEDS_CONTEXT.** Ruling E8b-R1 contradicts the data. On all three golden units, before and after E8a, **no
hole passes R1**: 0 candidate holes, so E8b would fill nothing, and the exit's six fill crops cannot exist. As the
dispatch says, I stopped here instead of loosening the ruling. Item 1 (the engine, rulings R1-R5, with its tests) is
committed. Items 2-4 (the Validator's `fill_site` class, the kernel wiring, and the CLI `fills` / `not_filled`) are
**not started**.

- Worktree: `D:/PROJECTS/UC MODEL FIXER/.claude/worktrees/P2-E8b`, branch `claude/P2-E8b`, base 76ca35a.
- Commit: **724300b** `feat(p2-e8b): E8FlatFill plans the narrow flat fill (rulings E8b-R1..R5) and lists every refused hole`.
- Nothing touched in `engine/guard/**`, `engine/validate/**`, `FixProfile`, or any existing test. No live data,
  container or owner folder was touched. Real-data reads went to `C:/Temp/e8b/probe/`.

## Item 1: E8FlatFill (`engine/repair/engines/e8_fill.py`), done

Files:
- `engine/repair/engines/e8_fill.py`: `E8FlatFill` (name `E8b`, not legacy), `ear_clip`, and `FILL_MAX_DIAMETER = 39.37`
  as a named constant.
- `engine/tests/fixtures/holes.py`: `holed_slab`, a closed or open slab with holes on a lattice.
- `engine/tests/test_e8_flat_fill.py`: 12 tests.

What it does, in test order (the first rule that fails names the refusal):
- **R1.** It finds the components of the open edges. These are the same open edges `find_errors` counts
  (`analyse_topology`'s `EDGE_OPEN`).
  - A component in which some point has other than two open edges is refused: `not_a_simple_loop`.
  - **R2 planarity:** the loop's points must lie within `plane_tol = 2 × print_step` of their least-squares plane.
  - **R1 simplicity:** the loop must not cross itself in its plane (`self_crossing`).
  - **R2 neighbours:** every face on a loop edge must have its normal within 1° of the plane's and all its corners
    within `plane_tol` of the plane.
  - **Hole or patch border:** if all neighbours lie inside the loop, it is a patch's outer border, which is counted and
    never filled. If all lie outside, it is a hole. If they lie on both sides, it is refused.
  - **R1 inner loop:** the hole is refused when another open-edge loop lies inside it (`inner_loop`), or when any face
    passes through it (`faces_inside`).
- **R3.** The inscribed diameter comes from `shapely.ops.polylabel`, with a tolerance of 0.005 in.
- **R4.**
  - The neighbours must have one look, as `face_keys` keys a look.
  - They must all face one side.
  - One affine UV map, fitted with `fit_uv`, must leave a residual of at most 1e-3 on every neighbour corner.
- **R5.** The ear-clipping is written in the repo. It produces n − 2 triangles of positive area, whose areas must sum to
  the polygon's within 1e-6. The edit is `Edit(engine="E8", kind="add", new_points=None)` with:
  - `evidence["material"]`;
  - `new_face_uv` (the neighbours' UV map continued) and `new_face_normal`;
  - the mark for R6: `evidence["flat_fill"] = True` and `evidence["loop"]` (the vertex ids).
- **The list.** Every refused hole goes in `not_filled`, with its rule, reason, detail, vertex count, centroid, points
  and the measured value. `report` holds the counts and every hole's inscribed diameter, for the histogram.

Additions beyond the brief's letter. Each one only refuses more, never less:
- `faces_inside`: a post standing in a hole has no open edge inside it, but a fill would cut through it.
- `neighbours_on_both_sides` and `neighbours_face_both_ways`.
- `no_material`: `apply_edits` cannot write an add without a material index.

### Red, then green

The first red run, before the module existed:

```
E   ModuleNotFoundError: No module named 'engine.repair.engines.e8_fill'
ERROR engine/tests/test_e8_flat_fill.py
1 error in 0.98s
```

Green, the 11 tests of items 1 and 2 (one fill, the ear-clipper, and the six refusals of the brief):

```
...........                                                              [100%]
11 passed in 1.03s
```

I added `test_a_hole_a_post_passes_through_is_refused` after the code was written. To see it fail for the right
reason, I ran it with `_faces_inside` patched to return False:

```
engine\tests\test_e8_flat_fill.py:103: AssertionError
FAILED engine/tests/test_e8_flat_fill.py::test_a_hole_a_post_passes_through_is_refused
1 failed, 11 deselected in 0.63s
```

Then, unpatched: `12 passed in 0.89s`.

The tests cover:
- One square hole in a closed slab: 8 points, 6 triangles, no new point, area 400 within 1e-6, faces up, the
  neighbours' UV `(x, y) × 0.05` continued, and open edges 8 → 0.
- An L-shaped (concave) hole: 6 triangles, area 300, open edges → 0.
- `ear_clip` skipping collinear ears.
- Each refusal: a corner raised 3 print steps on a 16-point loop (0.023 in off the plane, against plane_tol 0.02); a
  wall at 90°; two looks; a UV seam (+0.37); a 60 in hole (diameter 60.0); an island inside a hole; and a post
  through a hole.

## Why I stopped: R1 against the data

I ran the engine in plan mode only (no kernel, no Validator) on the BEFOREs and on the E8a outputs. The E8a outputs
are the stage inputs `--engines E8` would give E8b: P2-E8a's own runs in `C:/Temp/e8a/*`, from the code that merged
as 76ca35a. Output saved in `C:/Temp/e8b/probe/r1_measure.txt`:

```
== swA BEFORE: faces 4692; open edges 250, cracks(T-vertices) 550
   components 81: {'open chain': 64, 'branching (a point with 3+ open edges)': 15, 'closed loop': 2}
   E8b: loops 2 -> outer boundaries 2, holes 0, planned 0; not_filled {'not_a_simple_loop': 79}
   chain ends 181: at a T-vertex 49
   open chains: edges per chain {1: 33, 2: 19, 3: 14, 4: 1, 5: 2, 6: 3, 7: 1, 8: 1}
== swA after E8a: faces 4696; open edges 256, cracks(T-vertices) 552
   components 84: {'open chain': 67, 'branching (a point with 3+ open edges)': 15, 'closed loop': 2}
   E8b: loops 2 -> outer boundaries 2, holes 0, planned 0; not_filled {'not_a_simple_loop': 82}
== swB BEFORE: faces 7227; open edges 326, cracks(T-vertices) 559
   components 94: {'open chain': 76, 'branching (a point with 3+ open edges)': 11, 'closed loop': 7}
   E8b: loops 7 -> outer boundaries 2, holes 0, planned 0; not_filled {'not_a_simple_loop': 87, 'self_crossing': 5}
   chain ends 197: at a T-vertex 25
== swB after E8a: faces 7241; open edges 353, cracks(T-vertices) 578
   components 100: {'open chain': 81, 'branching (a point with 3+ open edges)': 12, 'closed loop': 7}
   E8b: loops 7 -> outer boundaries 2, holes 0, planned 0; not_filled {'not_a_simple_loop': 93, 'self_crossing': 5}
== chtm5 BEFORE: faces 20599; open edges 346, cracks(T-vertices) 3884
   components 190: {'open chain': 173, 'closed loop': 4, 'branching (a point with 3+ open edges)': 13}
   E8b: loops 4 -> outer boundaries 3, holes 0, planned 0; not_filled {'neighbour_not_coplanar': 1, 'not_a_simple_loop': 186}
   chain ends 393: at a T-vertex 271
   open chains: edges per chain {1: 132, 2: 25, 3: 13, 4: 7, 5: 4, 6: 1, 7: 4, 8: 1}
== chtm5 after E8a: faces 20624; open edges 373, cracks(T-vertices) 3898
   components 198: {'open chain': 180, 'closed loop': 5, 'branching (a point with 3+ open edges)': 13}
   E8b: loops 5 -> outer boundaries 4, holes 0, planned 0; not_filled {'neighbour_not_coplanar': 1, 'not_a_simple_loop': 193}
```

The open-edge totals equal P2-E8a's `find_errors` figures (sidewalk A 250 → 256, sidewalk B 326 → 353, CHTM-L05
346 → 373; cracks 550 → 552, 559 → 578, 3,884 → 3,898). So the edge set is the right one.

What the closed loops are:
- **Sidewalk B's 5 `self_crossing` loops are bow-ties.** Each has 4 points in a vertical plane x = const, for example
  (2673.25, 22945.0, 1779.53), (2673.25, 22945.0, 1787.91), (2712.62, 22945.0, 1783.9), (2712.62, 22945.0, 1793.74).
  The two sloped sides cross, so these are twisted gaps between two ramp sides, not flat holes.
- **CHTM-L05's one hole** (8 points, centroid (1506.68, 23037.31, 2320.87)) has a neighbour at 90°, so R2 refuses it.
- **Every other closed loop is a patch's outer border.**

The open edges come mostly as **open chains**: 1 to 3 edges whose two ends are dead ends. On CHTM-L05, 271 of the 393
ends are T-vertices. A hole in this model is usually bordered by open edges plus a stretch along another face's edge
(a T-junction side), so its border is never a closed loop of open edges alone.

### What a broader R1 would yield (an upper bound, for the decision only; not built)

I took the open chains with two ends whose closing segment (end to end) lies along an existing non-open edge
(`C:/Temp/e8b/probe/r1_chains.txt`):

```
== swA: ... 'closing segment on an existing edge, planar, with area': 19 ... ; inscribed diameter quantiles [0.64, 6.22, 9.62, 9.68, 10.59, 13.62]
== swB: ... 'closing segment on an existing edge, planar, with area': 17 ... ; inscribed diameter quantiles [2.36, 19.68, 22.14, 26.25, 26.25, 27.22]
== chtm5: ... 'closing segment on an existing edge, planar, with area': 12 ... ; inscribed diameter quantiles [2.28, 4.92, 11.52, 19.69, 19.7, 19.7]
```

I put those through R2-R4 unchanged. Their neighbours are the faces on the open edges plus the faces on the closing
edge (`C:/Temp/e8b/probe/r1_broader.txt`):

```
== swA: open chains closed along an existing edge -> {'R2 neighbour not coplanar': 13, 'no area / not simple': 1, 'not planar': 1, 'would pass R2-R4': 6}
== swB: open chains closed along an existing edge -> {'R2 neighbour not coplanar': 12, 'R4 uv seam': 4, 'not planar': 1, 'would pass R2-R4': 1}
== chtm5: open chains closed along an existing edge -> {'R2 neighbour not coplanar': 9, 'no area / not simple': 18, 'would pass R2-R4': 3}
```

So even with R1 broadened that way, at most **6 / 1 / 3** holes would reach the Validator on sidewalk A, sidewalk B and
CHTM-L05. That is 10 in all, before the hole-or-border, inner-loop and Validator checks. A fill along a T-junction
side also leaves a T-junction where its edge meets the longer edge, so the crack count would not fall.

### The decision needed (controller or owner)

1. **Keep R1 as written.** E8b then fills nothing on the golden units, and every loop goes to E8c. Items 2-4 can still
   be built and tested on fixtures, but the exit's real-run figures and six crops would be empty.
2. **Broaden R1** to "open edges, closed by at most one segment lying along an existing face edge" (or another
   definition). This adds a case the brief does not name. The Validator class (R6: "inside that fill's own loop")
   would then also have to accept a loop with one non-open side.
3. **Re-scope E8b.** Most of the open structure is open chains and cracks, which no flat fill on existing points closes.

Items 2-4 do not depend on R1's definition and need no number changed, so they can go ahead once the controller says
which of these to follow.

## Acceptance commands

- New tests: red, then green (above).
- Full suites on 724300b: see below.
- Golden runs with `--engines E8`: **not run**, because `repair-unit` does not run E8b yet (item 4 is not started).
  The plan-only measurements above take their place for the decision.
- Visual pass: **not done**. No fill exists on any golden unit, so there is nothing to crop.

### Suites

```
engine/tests (on 724300b): 1772 passed, 1 xfailed in 758.72s (0:12:38)
tools/tests:               123 passed in 16.15s
```

Before this job the engine suite had 1,760 tests; the 12 new ones are this job's. The worktree is clean.

## Things I am unsure of, said plainly

- The after-E8a figures come from P2-E8a's own output files (`C:/Temp/e8a/*`), not from a fresh run on 76ca35a. Their
  open-edge and crack counts equal the figures P2-E8a reported.
- The "broader R1" numbers come from a scratch script (`probe_r1c.py` / `probe_r1d.py` in my scratchpad), not from
  committed code. They are an upper bound to help the decision, not a result.
