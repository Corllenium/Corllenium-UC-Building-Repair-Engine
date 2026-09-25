# Brief 14: what can still flicker in Unity (2026-09-25)

Worktree `.claude/worktrees/coincident`, branch `feat/coincident-pairs`, continuing from brief 13
(`coincident-pairs-report.md`). The goal is "no flicker in Unity". Every number below was measured
in this session on the snapshots `ce26e0392ab0` (A) and `0b290ec0bcb4` (B), with the main
checkout's `.venv` and `PYTHONPATH` set to the worktree. The measurements use the `FixResult` the
brief 13 real runs pickled (engine code 6c7ad6e, unchanged since: `git diff e81e72a HEAD -- engine`
is empty).

**Status: DONE_WITH_CONCERNS. Nothing removed; every source traced.** A still has 28 z-fight
sources, 3,723.5 sq in, and B has 2, 49.3 sq in. None of them is a defect within the existing rules,
so no engine code changed. Every one is a PARTIAL overlap of two exported layers, and the merge does
not create any of them. What would remove them is either a wider rule, which is the owner's call, or
a change to solidify's side rebuild. solidify.py belongs to brief 11 and was not touched. Both are
written down with their measured effect in section 5. For 9 of A's 14 source planes, the overlapping
pieces unite into one polygon with no new vertex. Those planes hold 95 % of the source area and 95 of
its 141 visible pixels.

| Commit | Item |
|---|---|
| 488437d | item 1: `brief14/zfight_sources.py`, every source measured and traced |
| ccf95fe | items 2-3: `brief14/trace_sources.py`, why each is kept, the wider rule measured, the export's own view |
| (this file) | the report |

## 1. Every z-fight source (item 1)

A SOURCE is two final faces overlapping by more than 1 sq in in one plane: parallel
(|n . m| > 0.999), every corner of each within the guard's depth tolerance (0.15 in) of the other's
plane. Winding and material can be anything. Every pair found has a separation of 0.0 in, except B's
last, at 0.0022 in. The columns:
- **UV res**: the distance, in tiles, from one whole-tile shift over all six corners (0 = the same
  mapping). Every material in both files is flat (texture std 3.04).
- **px**: pixels of the 26 guard views of the SHIPPED mesh (900 x 600) whose first hit is one of the
  pair and whose ray meets the other within 0.15 in. These are the pixels where the two can trade
  places, which is what flickers in Unity.
- **export**: the two layers' windings in the input.
- **flipped**: per side, which source faces the orientation step re-wound.
- **own region covers**: at the duplicate-layer pass, the part of each side its own region covers.
  The pass removes at 0.99.

**A** (28 sources, 10 opposite-wound and 18 same-wound, 3,723.5 sq in, 9 seen in the guard views,
141 px):

| final faces | winding | sq in | cover each | at (x, y, z) | UV res | px | export | flipped | regions | own region covers |
|---|---|---|---|---|---|---|---|---|---|---|
| 64 / 75 | OPP | 1307.0 | 0.75 / 0.75 | 1276, 22797, 1602 | 5.99 | 42 | same | - / F+F | 7 / 11 | 0.00 / 0.00 |
| 64 / 78 | same | 436.1 | 0.25 / 0.75 | 1276, 22758, 1602 | 5.99 | 8 | same | - / - | 7 / 12 | 0.00 / 0.00 |
| 703 / 817 | OPP | 436.0 | 0.75 / 0.75 | 1315, 22817, 1602 | 2.00 | 4 | same | F / - | 151 / 189 | 0.00 / 0.00 |
| 740 / 745 | OPP | 436.0 | 0.75 / 0.75 | 1374, 22719, 1602 | 2.00 | 0 | same | - / F | 162 / 164 | 0.00 / 0.00 |
| 703 / 816 | same | 145.5 | 0.25 / 0.75 | 1315, 22804, 1602 | 2.00 | 0 | same | F / F | 151 / 188 | 0.00 / 0.00 |
| 740 / 741 | same | 145.5 | 0.25 / 0.75 | 1374, 22732, 1602 | 2.00 | 1 | same | - / - | 162 / 163 | 0.00 / 0.00 |
| 719 / 720 | same | 139.3 | 0.48 / 0.36 | 1335, 22776, 1601 | 1.00 | 0 | same | - / - | 155 / 156 | 0.00 / 0.00 |
| 719 / 721 | OPP | 131.7 | 0.45 / 0.75 | 1335, 22771, 1602 | 1.00 | 0 | same | - / F+F | 155 / 157 | 0.00 / 0.00 |
| 706 / 804 | same | 77.5 | 0.80 / 0.20 | 1346, 22748, 1603 | 1.00 | 0 | mixed | F+F+- / - | 153 / 184 | 0.00 / 0.00 |
| 130 / 731 | same | 72.9 | 0.50 / 0.75 | 1305, 22658, 1619 | 1.00 | 0 | same | F+F / F+F | 15 / 158 | 0.00 / 0.00 |
| 794 / 803 | OPP | 72.9 | 0.62 / 0.38 | 1344, 22761, 1622 | 2.00 | 0 | mixed | -+F / - | 180 / 183 | 0.00 / 0.00 |
| 793 / 803 | OPP | 62.7 | 0.61 / 0.33 | 1350, 22759, 1622 | 1.60 | 0 | mixed | -+F / - | 180 / 183 | 0.00 / 0.00 |
| 131 / 729 | OPP | 48.3 | 1.00 / 1.00 | 1305, 22666, 1615 | 0.50 | 0 | same | - / F+F | 16 / 158 | 0.00 / 0.00 |
| 598 / 603 | same | 37.3 | 0.20 / 0.79 | 2582, 22824, 1769 | 2.00 | 0 | same | - / - | 101 / 101 | 0.22 / 0.96 |
| 532 / 559 | same | 24.6 | 1.00 / 1.00 | 2680, 22720, 1780 | 0.00 | 39 | mixed | F+F / mostly - | 71 / 84 | 0.00 / 0.00 |
| 496 / 505 | same | 24.4 | 0.50 / 0.50 | 2595, 23275, 1768 | 0.50 | 0 | opp | - / F | 58 / 58 | 0.83 / 0.42 |
| 132 / 731 | OPP | 24.1 | 0.50 / 0.25 | 1305, 22664, 1619 | 1.00 | 0 | same | - / F+F | 16 / 158 | 0.00 / 0.00 |
| 719 / 813 | OPP | 19.8 | 0.07 / 0.17 | 1335, 22784, 1610 | 1.01 | 1 | same | - / F | 155 / 187 | 0.00 / 0.00 |
| 706 / 806 | OPP | 19.4 | 0.20 / 0.20 | 1353, 22748, 1616 | 1.00 | 0 | mixed | F+F+- / F+F | 153 / 185 | 0.00 / 0.00 |
| 496 / 504 | same | 16.2 | 0.33 / 0.34 | 2595, 23272, 1770 | 1.00 | 0 | opp | - / F | 58 / 58 | 0.83 / 0.42 |
| 527 / 568 | same | 15.7 | 0.11 / 0.32 | 2679, 22720, 1779 | 1.68 | 35 | opp | F / - | 47 / 47 | 0.14 / 0.34 |
| 597 / 603 | same | 9.1 | 0.19 / 0.19 | 2582, 22821, 1765 | 2.00 | 0 | same | - / - | 101 / 101 | 0.06 / 0.96 |
| 527 / 566 | same | 5.6 | 0.04 / 0.23 | 2682, 22720, 1779 | 1.66 | 7 | opp | F / - | 47 / 47 | 0.14 / 0.11 |
| 598 / 604 | same | 4.5 | 0.02 / 0.62 | 2582, 22821, 1769 | 2.00 | 0 | same | - / - | 101 / 101 | 0.22 / 0.98 |
| 606 / 619 | same | 3.0 | 0.50 / 0.50 | 2582, 22822, 1765 | 0.50 | 0 | same | - / - | 105 / 111 | 0.00 / 0.00 |
| 608 / 619 | same | 3.0 | 0.50 / 0.50 | 2583, 22819, 1765 | 0.50 | 0 | same | - / - | 105 / 111 | 0.00 / 0.00 |
| 529 / 566 | same | 2.8 | 0.11 / 0.11 | 2683, 22721, 1779 | 1.66 | 4 | opp | F / - | 47 / 47 | 0.02 / 0.11 |
| 597 / 604 | same | 2.5 | 0.05 / 0.34 | 2582, 22818, 1766 | 1.95 | 0 | same | - / - | 101 / 101 | 0.06 / 0.98 |

**B** (2 sources, both same-wound, 49.3 sq in, 7 px):

| final faces | winding | sq in | cover each | at (x, y, z) | UV res | px | export | flipped | regions | own region covers |
|---|---|---|---|---|---|---|---|---|---|---|
| 428 / 473 | same | 47.7 | 0.37 / 0.37 | 2905, 23445, 1816 | 1.00 | 5 | same | F / F | 56 / 56 | 0.37 / 0.37 |
| 438 / 469 | same | 1.6 | 0.01 / 0.01 | 2935, 23479, 1827 | 0.00 | 2 | same | - / - | 49 / 49 | 0.01 / 0.01 |

**The guard's `zfight_tie`:**
- A's final guard counts 1 tie pixel. The guard was re-run from the pickle with its classifier
  wrapped, and its totals match `guard_final`. That one pixel belongs to none of the 28 sources:
  BEFORE met reference face 4691, which solidify invented, and AFTER met final face 266.
- B's final guard counts 0.
- So `guard_tie_px` is 0 for every source. The guard only counts a tie where the WINNER changed
  between the reference and the shipped mesh. A double layer present in both, with the same
  winner, is `PX_OK` to it. That is why the column above is px and not `zfight_tie`.

**The trace, for all 30 sources:**
- Every source face comes from the export (all are input faces, none invented by solidify).
- Every overlap already exists before the merge. The merge only re-triangulates, and never adds
  overlap area: before the merge 72.4 sq in at the riser, after it 48.3 + 24.1.
- Windings: on A, 7 of the 10 opposite-wound sources are SAME-wound in the export. The per-face
  orientation step made them opposite by flipping one layer, one whose only real exposure is on
  its back, while the other layer is thin and stays as it is. The other 3 are mixed in the export.
  The flip also works the other way: 5 same-wound sources were opposite-wound in the export.
- Why the duplicate-layer pass keeps them: its own region covers no source face at 0.99. Either the
  two layers are separate regions (cover 0.00), or the overlap is partial. The closest are 0.96 and
  0.98, on the x 2582.2 plane, and the threshold stays 0.99.
- Why brief 13's rule keeps them: none of them is exact before the merge, the only stage it
  judges.

## 2. The same-wound duplicate on A, 24.6 sq in at z 1779.53 (item 2)

It is final faces 532 and 559: exactly coincident, same winding, same material, UV mapping the same
modulo whole tiles (offset -1.998, -1.998). The pass does not see a copy there, because at its stage
there is none:
- reference face 3075 (145.6 sq in, input 3105, flipped up) is in region 71;
- it overlaps ONE face, reference 3728 (72.8 sq in) of region 84, by 24.6 sq in: 17 % of 3075 and
  34 % of 3728;
- both are in the same plane cluster (18), and no welded edge joins them, so they are two regions;
- each region's cover of its own face is 0.00.
The merge then triangulates each region, threading the vertices lying on its edges. Two of the
resulting triangles coincide exactly, one in each region.

So it is not a defect within the existing rules. It is a partial overlap of two separate regions,
and the guard is not involved (nothing was put back). What would remove it are two wider rules,
measured here and not adopted:
- **W1**: a same-wound face goes when the OTHER faces of its whole PLANE GROUP with the same material
  and the same winding cover it at 0.99, whatever their region. Candidates are walked like
  `plan_overlap_removal`, each re-measured against what is still kept, and then the strict guard is
  asked.
  - Measured at the pass: A would lose 1 more face, reference 3506 (input 3537, 6.0 sq in at
    2582.6, 22820.4, 1764.8), and the guard confirms it. That resolves sources 606/619 and 608/619
    (3.0 sq in each, 0 px). The pass's own 11 are still confirmed. B would lose nothing.
  - W1 does NOT resolve 532/559: 3075 and 3728 each stay only partly covered.
- **W2**: after the merge, a triangle goes that exactly coincides with another shipped triangle of
  the same material, the same winding and the same UV mapping modulo whole tiles.
  - Measured on the shipped meshes: 1 triangle on A (532/559, 24.6 sq in), none on B.
  - The `.skp` is written from the merge's polygons (`rings`), not its triangles. So W2 must take the
    triangle out of its region's polygon too. It is a merge change, not a filter.
- This pair renders identically whichever face wins: same material, winding and UV mapping. It
  cannot flicker unless Unity lights the two differently. Different lightmap charts per triangle
  would do that. Unverified: I have not checked how the campus is lit.

## 3. The riser pair on A, x 1305.14 (item 3)

**What makes it.** The export does. The side at x = 1305.14 is drawn twice, by two exported pieces:
- reference faces 96, 97 and 98 (inputs 107-109, OBJ lines 5157-5159), a fan from (y 22659.6,
  z 1612.2);
- reference faces 4195 and 4196 (inputs 4236-4237, OBJ lines 9286-9287), the lower rectangle,
  z 1612.2 to 1622.05.
All five face +x in the export and overlap by 145.3 sq in. The orientation step then:
- flips 96, 97, 4195 and 4196 to -x: each one's exposure is on its back, for example 4195's back
  0.0625 against its front 0.002;
- leaves 98, which is thin (front 0.0039, back 0.0078);
- has the sheet rule refuse to re-wind 98, because 4195 and 4196 lie on it. That is rule 3, and it
  is A's `faces_lying_on_another` 1.
The merge threads 98 at the T-vertex (22669.4, 1622.05) and triangulates the region of 4195 and
4196. That makes 131/729 an exact opposite-wound pair (48.3 sq in) and leaves 132/731 partial
(24.1). Beside them, 130/731 is a same-wound partial pair (72.9).

**Not the merge, so no merge fix.** It adds no overlap: 72.4 sq in before, 48.3 + 24.1 after.
**Not the side rebuild either.** solidify left all five faces in the reference: none of them was
replaced. The spot is enclosed: it shows in none of the 26 guard views (0 px).

**The exact change, for brief 11 or the next brief (solidify.py, not touched here).** A side plane
whose pieces overlap is ONE side. Replace the pieces with one wall over their union, wound to the
side that is seen, and report them as side pieces replaced.
- At x 1305.14 the union of the five is the square y 22649.7 to 22669.4, z 1612.2 to 1631.89
  (387.9 sq in, from pieces totalling 533.2 sq in).
- Its four corners are existing vertices, so no vertex is invented.
- It should face -x, the side the reference sees (4195: back 0.0625, front 0.002).

The same change applies to every source plane on A. Per plane, the source faces' union:

| plane | source faces (reference) | source sq in (opposite) | px | union / pieces sq in | vertices to invent |
|---|---|---|---|---|---|
| x 1275.6 | 60, 78, 79, 87 | 1,743.2 (1) | 50 | 5,811.7 / 7,554.9 | 0 |
| x 1315.0 | 4127, 4541, 4542 | 581.5 (1) | 4 | 1,551.2 / 2,132.7 | 0 |
| x 1374.0 | 4219, 4221, 4222 | 581.5 (1) | 1 | 1,551.2 / 2,132.7 | 0 |
| x 1334.7 | 4148, 4150-4152, 4540 | 290.8 (2) | 1 | 834.1 / 1,124.9 | 0 |
| x 1305.1 | 96-98, 4195, 4196 | 145.3 (2) | 0 | 387.9 / 533.2 | 0 |
| z 1622.0 | 4516, 4517, 4522 | 135.6 (2) | 0 | 1,090.6 / 1,226.2 | 2 |
| y 22748.2 | 4138, 4139, 4525, 4535-4537 | 96.9 (1) | 0 | 1,550.0 / 1,646.9 | 0 |
| x 2582.2 | 3402, 3403, 3419, 3420 | 53.4 (0) | 0 | 382.5 / 436.1 | 0 |
| x 2594.5 | 2655, 2925 | 40.6 (0) | 0 | 105.2 / 145.8 | 2 |
| z 1779.5 | 3075, 3076 and region 84's 21 | 24.6 (0) | 39 | 3,125.4 / 3,150.0 | 0 |
| sloped, 3 planes near d 2153 | 3073, 3074, 3266, 3267 | 24.1 (0) | 46 | - | 1 to 3 each |
| z 1764.8 | 3430, 3431, 3506 | 6.0 (0) | 0 | 48.5 / 54.5 | 0 |

The planes with nothing to invent carry 3,523 of the 3,724 sq in and 95 of the 141 px. The x 1275.6
to 1374.0 planes are the lower landing's walls, z 1582.7 to 1622. There, too, the export draws each
wall twice: most of these pairs cover each other 0.75 / 0.75 or 0.25 / 0.75.

## 4. Finish (item 4)

- **Engine suite**: `604 passed` at e81e72a (brief 13's final count). Brief 14 changed no engine
  code (`git diff e81e72a HEAD -- engine` is empty), so the count stands.
- **Real runs**: the engine is unchanged since the brief 13 runs (`data/out_b13`, code 6c7ad6e), so
  before = after.

| | A | B |
|---|---|---|
| triangles | 884 | 510 |
| passed, merge rolled back | yes, no | yes, no |
| `zfight_tie` px, before / after | 1 / 1 | 0 / 0 |
| z-fight sources / sq in / px in the guard views | 28 / 3,723.5 / 141 | 2 / 49.3 / 7 |

- **Renders**: nothing was fixed, so there is no before and after. Brief 13's close-ups of the
  lower landing (`data/skp_render/b13/A_after_landing/`) show the planes of the biggest sources. The
  walls at x 1275.6, 1315.0, 1334.7 and 1374.0 carry purple patches, faces seen from their back.
  `side_nx_sides.png` looks toward +x and shows one under the raised walkway's edge: SketchUp face 30,
  in the x 1275.6 plane, 2,159 px. I did not trace which layer of which source each patch is. A
  ray-cast render cannot show the flicker itself: it breaks every tie the same way.

## 5. For the owner and the controller

Ranked by what shows:
- A's lower-landing walls (x 1275.6 to 1374.0, and y 22748.2) carry 56 of the 141 px and 3,439 of
  the 3,724 sq in.
- The z 1779.5 and sloped planes carry the other 85 px. They are same-wound, so their flicker is
  only a texture offset on flat materials (std 3.04).

1. **Side-plane union (solidify, brief 11)**, as in section 3. It removes 9 of A's 14 source planes
   without inventing a vertex, and the other five with one to three invented each. That is the only
   change here that ends in one clean face per side, in the OBJ and in SketchUp alike.
2. **Keep the export's relative winding (orientation)**: flip overlapping same-material layers of
   one plane together, not one alone.
   - It would turn A's 7 export-same-wound opposite sources back to same-wound: 2,403 sq in,
     including the 1,307 sq in wall at x 1275.6 (42 px).
   - That removes the lighting difference between the two layers but not the texture offset. It
     changes `engine/fixes/orient.py`'s flip rule and runs against its rule 3.
   - Not measured end to end.
3. **W1** (a copy covered by its whole plane group) and **W2** (exact same-wound triangles after the
   merge): measured in section 2 as 6.0 and 24.6 sq in on A, nothing on B. Small.

Two things stay wider than any rule here:
- B's 47.7 sq in same-wound pair (UV one tile mirrored, 5 px);
- the partial overlaps with invented vertices.
