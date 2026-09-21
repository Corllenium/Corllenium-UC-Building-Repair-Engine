# Phase 0 spike results — 2026-09-21

All numbers produced by scripts in `spike\` run against a sha256-pinned snapshot in
`data\spike\snapshot\`. Raw output: `data\spike\results.json`. Images: `data\spike\*.png`.

Snapshot: `CHTM_SIDE_WALK_2nd_floor.obj` sha256 `ce26e039...`, 4,692 tris = manifest.
`CHTM_2nd_to_3rd_building_sidewalk_outside.obj` sha256 `0b290ec0...`, 7,227 tris = manifest.
Textures missing: 0.

## Gates

| Gate | Result | Evidence |
|---|---|---|
| G1 embreex works | **PASS** | embreex 4.4.0 under numpy 2.5.3, 4,909,481 rays/s, hit fraction 1.0 |
| G2 region merge worth it and safe | **FAIL as designed**, passes after redesign (below) | as designed: 6.46 % and 21.77 % reduction, needed 40 %. Safety fine: area error 2e-15, UV residual p99 0.007 |
| G3 culling trick = brute force | **PASS** | 32,000 rays, 0 hit/miss disagreements, 0 depth disagreements, worst depth diff 0.0002 in |

## Re-measure vs spec

Identical to the previous export: edge valence 453/3,732/1,629/303 and 534/7,615/1,216/538,
zero-area 217 and 79, duplicate faces 11 and 31 (all opposite winding, 24 with different material).
Drift: `vt` 2,771 (was 2,772) and 1,829 (was 1,831). File bytes changed, geometry counts did not.

## Why G2 failed — root cause investigation

Four hypotheses, tested one variable at a time.

| # | Hypothesis | Test | Verdict |
|---|---|---|---|
| H1 | Kept border vertices dominate (polygon with n ring vertices needs n+2h-2 tris) | keep only vertices that are a corner in some region | **partly**: B 21.5 -> 33.7 %, A 6.3 -> 7.4 % |
| H2 | Stacked duplicate coplanar layers | layering = sum of areas / union area per plane | **rejected**: overall 1.023 and 1.024. My plane-level overlap flag was too coarse (0.5 in2 overlap flagged a 682-tri plane) |
| H3 | UV classes shatter planes for no visual reason | ignore UV, corners only | **confirmed**: A 8.1 -> 28.4 %, B 38.7 -> 56.3 % |
| H4 | Interior faces pin vertices and hold many tris | remove never-visible first, then merge | **partly**: A -> 38.2 %, B -> 62.6 % (before the reversed/interior split below) |

Texture evidence behind H3: all four sidewalk textures are **16x16 noise, std 3.04 / 255, range
217-227**. `-3`, `-7`, `-8` have identical statistics. A UV seam on these cannot be seen. One ramp
plane had 183 tris in 21 UV classes, one underside 682 tris in 41 classes.

## Visibility: what the first pass got wrong

First pass called 672 / 870 tris "never visible". Rendering it (rule: look at it) showed holes in
the top surface under culling. Testing the **back** side separated two classes:

| | front visible | of which back also exposed | **reversed** (front hidden, back exposed) | **interior** (neither side exposed) |
|---|---|---|---|---|
| file A | 3,803 | 2,843 | 448 tris, 4.30 % area | 224 tris, 1.44 % area |
| file B | 6,278 | 4,130 | 583 tris, 4.67 % area | 287 tris, 1.59 % area |

- Two thirds of the first-pass "interior" set was reversed skin. Deleting it would have removed
  real top-surface faces. **Orientation pass must run before interior detection.** Spec already
  orders it that way, spike confirms it is mandatory.
- Most visible faces have their back exposed: the sidewalk is largely **zero-thickness sheets**,
  not closed slabs.
- Remaining white cut-outs after flipping have no face of either orientation: real openings or
  geometry owned by a neighbour object. Not a defect of this object.

Full pipeline (drop zero-area, flip reversed, delete interior, merge ignoring UV, corners only):
**A 4,692 -> 3,111 (33.7 %), B 7,227 -> 3,003 (58.45 %)**. G2's "at least one file >= 40 %" is met by B.
File A is genuinely made of many small planar pieces (681 rings after merge).

## Corrections to the design spec

1. **Wrong fact, corrected**: spec says "Unity is single-sided". Project sets every campus material
   to `_Cull = 0` (`D:\PROJECTS\UC\01-UNITY\UC-Campus\Assets\Editor\CampusDoubleSided.cs`). Reversed
   faces are a lighting issue today, not holes. Engine keeps both semantics as a profile switch.
   Safe default needs no choice: a face never visible under single-sided occlusion (fewer blockers)
   is also never visible under double-sided, so deleting that set is safe in both. Flipping a
   reversed face is harmless under double-sided and correct under single-sided.
2. **Coordinate quantum is per axis.** Exporter prints 6 significant digits: step 0.1 in on Y
   (values near 22,000), 0.01 in on X and Z. Plane tolerance = `1.5 * sum(|n_i| * q_i)`.
3. **UV handling becomes a preference.** "Flat texture" rule: when a material's texture colour std
   is below a threshold, UV seams do not delimit regions and the guard compares sampled texel
   colour instead of UV modulo 1. Off = respect UV (file A then gains ~8 %).
4. **Border vertices**: a ring vertex survives only when some region needs it as a corner, decided
   globally so both sides of a shared border drop the same vertices. No new T-junctions.
5. **Overlap handling per triangle, not per plane.** Union can also create new vertices where
   overlapping edges cross (snap distance up to 94 in observed). Overlapping faces must be resolved
   or excluded before a region is re-triangulated, otherwise "existing vertices only" is violated.
6. Validated and carried into Phase 1 unchanged: greedy plane clustering by largest triangle,
   iterative least-squares UV refit, exact weld on printed decimals, snapshot stability check,
   manifest parser, per-direction front-facing scene for culled visibility, no-GPU ray-cast renderer
   (doubles as the image guard).
