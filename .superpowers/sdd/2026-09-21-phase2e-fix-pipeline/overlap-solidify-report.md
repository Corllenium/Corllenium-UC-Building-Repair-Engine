# Overlap + solidify round — report (MQ1-MQ4, G1-G3, O1, S1)

Repo `D:\PROJECTS\UC MODEL FIXER`, branch `feat-dashboard`. Baseline before this round:
commit `0d464e0`, `.venv/Scripts/python.exe -m pytest engine/tests -q` → **213 passed**.

Every item below was implemented test-first: the test was written, run, watched fail for the
stated reason, then the implementation landed and the test was watched pass. Each item is one
commit with the trailer `Co-Authored-By: Claude Fable 5.1 <noreply@anthropic.com>`.

---

## MQ1 `fix(engine): EDGE_SOFT requires two real regions`

### What changed

`engine/topo/edges.py` — `classify_edges`'s soft-crease branch now also requires
`face_region[f0] >= 0 and face_region[f1] >= 0`. It is an `elif` on the REMOVABLE test, whose
own guard is `face_region[f0] >= 0 and face_region[f0] == face_region[f1]`; two faces both at
`-1` fail that (the `>= 0` half), fall into the `elif`, and were classed EDGE_SOFT on material +
angle alone. `region_border_angles`, in the same module, has always required both regions `>= 0`
and says why: a face in no region is not one side of a border BETWEEN regions.

### Test (written first, watched fail)

`test_regions.py::test_two_copied_through_faces_never_make_a_soft_edge` — `creased_pair(3.0)`'s
hinge, classified once with the real regions (still EDGE_SOFT, pinning the behaviour that must
not change) and once with `face_region` all `-1`. **RED before**: `assert np.uint8(5) != 5`.
Green after; `region_border_angles` returns `{}` for the same input, so the two functions now
agree by test, not only by intent.

Reachability, honestly: inside `analyse_topology` a face is at `face_region == -1` only when it
is degenerate, and `face_normals` zeroes a degenerate face's normal, so `dihedral_degrees`
returns 90 degrees and the branch could not fire there. This is a latent defect in a PUBLIC
function's contract (`classify_edges` takes any `face_region`/`normals` a caller hands it), not a
number that moves on the real files — and the real-data numbers below confirm no change.

### Result

`.venv/Scripts/python.exe -m pytest engine/tests -q` → **214 passed** (213 + 1).

---

## MQ2 `test(engine): simplified shared borders never open a T-junction`

### What changed

- `engine/tests/fixtures/build.py` — new `two_slabs_sharing_curved_border(n=12, half_span=110,
  sag=0.8, half_width=120, y=24000)`: two coplanar slabs of DIFFERENT materials (so they stay two
  regions) meeting along a parabolic border of `n` vertices, scaled exactly like
  `arc_topped_strip`'s arc — the farthest border vertex is 0.8 in from the chord between the two
  END border vertices, each one only `0.8 * (2/11)**2 = 0.027` in from the chord of its own two
  neighbours. At y = 24,000 in the merge's ring bound is `1.5 * 0.1 = 0.15` in, so every vertex
  passes a per-vertex collinearity test and the whole polyline does not.
- `engine/tests/test_merge.py` — two tests. No production code changed: the invariant holds.

### Tests

- `test_two_regions_keep_the_same_vertices_of_a_shared_curved_border` — the global corner pass
  (`_needed_vertices`) run once over both plans: both rings come out holding the identical border
  subset, `{12, 13, 16, 18, 19, 22}` (6 of 12) — a proper subset, so the fixture is not vacuous.
- `test_a_shared_curved_border_opens_no_t_junction_in_the_shipped_mesh` — end to end, at the
  SIMPLIFICATION bound rather than 1e-9: a vertex dropped from a curved border is not on the
  chord that replaces it, so a T-junction here is a crack up to `collinear_tol` wide that an
  exact on-the-segment test would miss. No vertex of the shipped mesh lies inside another
  triangle's edge.

### Sensitivity, measured and reported honestly

I disabled `_divergent_vertices` (the anchoring these tests are meant to protect) and re-ran
both: **they still passed**. On this fixture RDP agrees for a geometric reason as well — the
junction corner where the border meets the outer boundary is the farthest point from the fallback
anchors' chord, so it is the FIRST split in both rings, and the recursion is then confined to the
same border stretch from either side. The anchoring is belt-and-braces here, not the only thing
holding the invariant up. The tests are still a real regression test of the invariant itself (they
would catch any future change that lets the two sides disagree); they are not a mutation test of
that one function, and I am not claiming they are.

### Finding (measured, NOT fixed here — out of this item's scope)

`engine/fixes/merge.py` checks the same area twice at tolerances 4,000x apart, and on a shared
curved border the stricter one makes the simplification self-defeating:

| check | bound on this fixture | verdict |
|---|---|---|
| rule 6 (`_triangulate`): `abs(polygon.area - union_area) > 1e-6*union_area + collinear_tol*perimeter` | 102 sq in | both regions pass (change 5.34 sq in) |
| rule 9 (`_build_regions`): `merged_area > original_area * (1 + 1e-6)` | 0.026 sq in | region 1 rejected, `area_grew` |

Simplifying a SHARED border shrinks one region by exactly what it grows the other by (measured:
-5.336 / +5.336 sq in), so rule 9 always rejects one of the two. `merge_regions` then feeds that
region back, `_needed_vertices` pins its whole ring, and the neighbour has to keep the shared
border vertices too — so both regions lose the simplification (34 triangles where ~10 is the
simplified answer). I did not change it: rule 9 is what currently keeps `fix_object`'s whole-mesh
`area_not_grown` invariant true, and relaxing it could flip `passed` to False on the real files.
That trade needs its own measurement round, and it is filed as a follow-up task.

### Result

`.venv/Scripts/python.exe -m pytest engine/tests -q` → **216 passed** (214 + 2).

---

## MQ3 `test(engine): least-squares refit does not drift across a shallow crease`

### What changed

- `engine/tests/fixtures/build.py` — new `creased_pair_with_fine_band(angle_deg=3, band=12,
  cell=1.2, flat_len=120, tilt_len=100, width=30, y=24000)`: `creased_pair`'s two planes with a
  band of `cell x cell` quads along the crease on BOTH sides (1,000 triangles whose longest edge
  is 1.70 in, under 2 in), one material, and — deliberately — both halves wound the SAME way.
  My first version had them wound against each other, which made the fixture prove nothing:
  `cluster_planes` only ever considers a candidate whose normal is within `facing_dot` of the
  region's, so opposite windings can never drift into one another. That is pinned by its own test
  now.
- `engine/tests/test_regions.py` — two tests. No production code changed: no drift appears, so
  the refit gate the item describes as conditional was not built.

### Measured

At y = 24,000 in the plane tolerance is `1.5 * |n| . q = 0.15` in, and a point `d` inches along a
3 degree slope sits `0.052 * d` off the other plane — so every tilted vertex within 2.9 in of the
hinge is inside the flat plane's tolerance and inside `facing_dot` (cos 3 deg = 0.9986 > 0.9).
The refit therefore CAN reach across, and it does, a little:

| `cluster_planes` output | members | from the flat half | from the tilted half | angle to its true normal |
|---|---|---|---|---|
| plane 0 (flat) | 650 | 550 | 100 | **0.0124 deg** |
| plane 1 (tilted) | 450 | 0 | 450 | **0.0000 deg** |

`analyse_topology` yields exactly **2** regions. Both fitted normals are two orders of magnitude
inside the 0.5 degree bound, so the test passes as written and the conditional gate ("reject a
refit more than 1 degree from the region's FIRST least-squares fit") was not implemented — a
0.0124 degree drift would not have tripped a 1 degree gate anyway.

What the refit DOES do is take 100 faces (the tilted side's first two band columns) into the flat
plane. They are within that plane's own printed tolerance, so this is not a wrong answer by the
plane test's own definition; it is a membership question, not a normal-drift question, and the
gate described in the item does not address it. Reported, not changed.

Sweep, so the choice of fixture parameters is not doing the work: over `band` 12/24/40 in,
`cell` 1.5/0.5 in and plate lengths from 120/100 down to `band + 6` / `band + 5`, the count was
always exactly 2 regions and the worst normal error was **0.60 deg** — at the one contrived
corner where the plate is barely longer than the band (18 in long, 12 in of it a 0.5 in band).
Every plausible shape stayed under 0.28 deg.

### Tests

- `test_least_squares_refit_does_not_drift_across_a_shallow_crease` — exactly 2 regions from
  `analyse_topology`, exactly 2 planes from `cluster_planes`, each within 0.5 deg of one of the
  two true normals, and the two planes more than 2.5 deg apart (so they are the two DIFFERENT
  surfaces, not the same one found twice).
- `test_the_fine_band_is_what_makes_that_fixture_dangerous` — pins the fixture's own properties
  (one material, all 1,100 faces wound the same way, exactly 1,000 band triangles under 2 in,
  the band touching the crease) so a later edit cannot quietly make it harmless again.

### Result

`.venv/Scripts/python.exe -m pytest engine/tests -q` → **218 passed** (216 + 2).

---

## G1 `fix(engine): crack tolerance has a ceiling and a cap`

### What changed

- `engine/fixes/pipeline.py` — `FixProfile.depth_tol_max = 0.5` (inches) and
  `FixProfile.crack_closed_cap = 1e-3`; new public `guard_depth_tol(quanta, profile)` =
  `min(1.5 * max(quanta), profile.depth_tol_max)`, which `fix_object` now uses for every guard in
  the run; the final/merge-attempt `compare_views` calls pass `crack_closed_cap`.
- `engine/guard/compare.py` — `compare_views` gains `crack_closed_cap: float = float("inf")`.
  Per view, when `crack_closed > crack_closed_cap * model_px`, those pixels FALL BACK to the base
  class they were promoted from, before the counts are taken. `zfight_tie` is not capped at any
  number, and the docstring now says why.
- `engine/cli.py` — the guard triptychs and `preview-data`'s `guard_tol_in` use
  `guard_depth_tol`, so the pictures and the page quote the tolerance the guards actually ran at;
  `report.json`'s `profile` block carries the two new fields.

Why a ceiling: `depth_tol` is not only the "did the surface move" bound, it is the RADIUS of the
crack and flicker rings, and `classify_pixels` already documents the consequence — damage
narrower than that radius is indistinguishable from a crack the fix closed. A model near
24,000 in prints Y to 0.1 in and gets 0.15 in, which is fine; the same formula on a survey-
coordinate export near 240,000 in gives 1.5 in, at which a lost 1 in sliver reads as an
improvement.

Why the cap falls back rather than merely counting as failing (the one place it differs from
flicker): a report that says `crack_closed: 4,000` next to `passed: false` explains nothing. Over
the cap those pixels are reported as what they really were.

### Tests (written first, watched fail)

- `test_pipeline.py::test_guard_depth_tol_is_one_and_a_half_quanta_until_it_hits_the_ceiling` —
  0.15 under the ceiling, 0.5 over it, 1.5 when the ceiling is raised. **RED before**:
  `module 'engine.fixes.pipeline' has no attribute 'guard_depth_tol'`.
- `test_pipeline.py::test_fix_object_clamps_the_depth_tolerance_of_a_survey_coordinate_model` —
  `box_with_partition` shifted to x = 240,000 (where `1.5 * max(q)` really is 1.5, asserted), with
  `guard_feedback` spied on: every call sees 0.5. **RED before**: `{1.5} != {0.5}`.
- `test_guard.py::test_closed_cracks_under_the_cap_are_still_tolerated_and_reported`,
  `..._over_the_cap_fall_back_to_their_base_class_and_fail`,
  `test_the_crack_cap_defaults_to_uncapped_so_existing_callers_are_unchanged` — the existing
  `_crack_scene`, whose 25 crack pixels in a ~14,000 px view are 1.8e-3, just over the 1e-3
  default: at 1e-2 it reports `crack_closed: 25` and passes, at 1e-3 it reports
  `moved_other: 25`, `crack_closed: 0` and fails, at `inf` it is unchanged. **RED before**:
  `compare_views() got an unexpected keyword argument 'crack_closed_cap'`.
- `test_guard.py::test_a_zfight_tie_is_never_capped` — the twin scene, every model pixel a tie,
  passing at crack caps 0.0 / 1e-3 / inf.

### Result

`.venv/Scripts/python.exe -m pytest engine/tests -q` → **224 passed** (218 + 6).

---

## G2 `fix(engine): the removal guard classifies ties and cracks like the merge guard`

### What changed

`engine/guard/compare.py` — `guard_feedback` now casts the ring and tie probes and classifies
with `_classify(..., strict=strict)`, so its verdicts match
`compare_views(..., edge_flicker_cap=0.0)` pixel for pixel. It gains `crack_closed_cap`
(default `inf`); `fix_object` passes `FixProfile.crack_closed_cap` to both of its
`guard_feedback` calls, so the removal guard is never more tolerant of cracks than the final
guard. The AFTER render is now labelled with LOCAL ids into `keep_faces` (with `face_material`
and the planes sliced to match), because the probes report `tri` as indices into the caster's own
`faces` array; `b.tri` stays original-indexed, which is what the restore step reads.

The docstring claimed "the same displacement/colour-aware pixel test as `compare_views`" while
casting neither probe. At cap 0.0 that was true of FLICKER and false of the other two:
`PX_ZFIGHT_TIE` and `PX_CRACK_CLOSED` are never failures at any cap, and the removal guard was
counting both as damage. Corrected, with the reason spelled out.

### A rule the change made necessary, found by an EXISTING test

Wiring the crack test into removal broke
`test_pipeline.py::test_a_sliver_that_only_the_relative_test_calls_zero_area_is_kept_by_the_guard`:
`floor_with_sliver`'s 1e-4 in sliver is far thinner than the 0.15 in ring radius, so all 16 ring
rays miss it, every pixel along it promoted to `PX_CRACK_CLOSED`, and the strict guard deleted a
real, differently-coloured surface (`n_degenerate_restored` 1 -> 0). That is the crack test's own
documented limit, and under removal it is not merely a limit but wrong: a crack promotion asserts
"AFTER closed it", which cannot be true of a face this pass is deleting.

So: **a crack promotion is refused when BEFORE's first hit is a face currently marked for
removal.** Those pixels fall back to their base class. Ties need no such rule — a tie already
requires BEFORE's own first hit to match a member of AFTER's tie set, which a removed face cannot
do unless the same material is still present in the same plane.

I verified the rule is load-bearing by deleting it: both
`test_a_removed_face_narrower_than_the_ring_is_never_excused_as_a_closed_crack` and the existing
sliver test fail without it.

### Tests (written first, watched fail)

- `test_guard.py::test_the_removal_guard_tolerates_a_zfight_tie_it_caused` — three exactly
  coincident copies of one quad, materials `[0, 0, 1]` per copy. Embree's first hit over all six
  faces is copy 2; remove copy 1 and it becomes copy 0, with both copies present in both meshes,
  so every model pixel changes material while nothing was lost — the real tie, reached the real
  way (rebuilding the ray structure over a different face set). **RED before**:
  `failing_pixels == 2116`; green after: 0, nothing restored, the mask is the candidates.
- `test_guard.py::test_the_removal_guard_still_fails_when_a_tie_member_was_the_one_removed` —
  the counterpart: remove the copy embree picks first and BEFORE's own winner is gone from
  AFTER's tie set, so it is a material change and the faces come back.
- `test_guard.py::test_the_removal_guard_still_fails_a_flicker_pixel` — flicker is the one of the
  three that stays a failure at cap 0.0.
- `test_guard.py::test_a_removed_face_narrower_than_the_ring_is_never_excused_as_a_closed_crack`
  — a 0.02 in differently-coloured strip over a floor, aimed at a column of the guard's OWN pixel
  centres (`guard_feedback` frames every render on `positions_c`, which is what made my first
  attempt report 0 failing pixels).

Honest note on the mask: for TIES this changes what the guard REPORTS, not what it removes. At a
tie pixel BEFORE's first hit is by definition still present in AFTER, so it was never a face
marked for removal and could never have been restored. The substantive change is the crack
class, and the restriction above bounds it.

### Real data, unchanged

File A after G1+G2: 4,692 -> 1,674 triangles, `n_removed_hidden` 1,819, `n_restored_by_guard` 34,
feedback rounds `[(0, 223 px, 34 restored), (1, 0, 0)]`, both guards pass, 30.5 s — the same
numbers as before this round, so neither guard change moved the real result. The final guard
reports `crack_closed: 1` and `edge_flicker: 30` of 2,059,414 model px, both far under their caps.

### Result

`.venv/Scripts/python.exe -m pytest engine/tests -q` → **228 passed** (224 + 4).

---

## G3 `test(engine): tie recovery rejects a coplanar triangle that does not contain the hit point`

### What changed

`engine/tests/test_caster.py` only — two tests and a fixture. No production code: the recovery
pass already rejects it, and now says so under test.

`EmbreeCaster.all_hits`' recovery searches ALL faces with only a bounding-box prefilter, so
`_contains` (on the plane AND no further than `tol` outside any of the three edges) is the only
thing between "really coincident here" and "merely lives in the same plane". A tie invented out
of a face the ray never touched would tell the guard two surfaces swapped places where one of
them is nowhere near the pixel.

### Tests

- `test_all_hits_rejects_a_coplanar_triangle_that_does_not_contain_the_hit_point` — file B's real
  coincident pair plus a third triangle in the same plane (`y = 767.05` to the last printed
  digit) whose BOUNDING BOX contains the hit point while its outline misses it by 13.9 in, so the
  prefilter passes and only the containment test can reject it. Both assertions are made
  explicitly, so the test cannot silently degrade into "the prefilter happened to catch it".
  Exactly faces 0 and 1 are reported, by `EmbreeCaster` and `BruteCaster` alike.
- `test_the_bystander_is_reported_once_it_does_contain_the_hit_point` — the same scene with the
  bystander's third corner lifted so it covers the point: all three faces reported, at one depth.
  Without this the first test would pass equally well against a recovery pass that had been
  switched off.

Both verified load-bearing by mutation: with `_contains` forced to True the first test fails;
with the recovery pass removed entirely both fail.

### Result

`.venv/Scripts/python.exe -m pytest engine/tests -q` → **230 passed** (228 + 2).

---

## O1 `feat(engine): remove covered same-material duplicate layers under the strict guard`

### What changed

New `engine/fixes/overlap.py`, run in `fix_object` after hidden/slit removal and flipping and
BEFORE the merge, with `analyse_topology` rerun on the result.

- `find_overlaps(mesh, topo, plane_tol=None) -> [(i, j, area, same_material), ...]`, sorted.
  The unit is the PLANE, not the region: `plane_groups` gathers regions whose normals are
  parallel to within `PLANE_PARALLEL_DOT` **ignoring sign** (a double face is usually the same
  outline wound both ways) and which lie in each other's plane to within `plane_tol`
  (`1.5 * max(axis quanta)` by default). Regions are split by material, so a per-region search
  could not see a different-material z-fight at all — the very defect the guard's tie test exists
  for.
- `overlapping_polygon_pairs(polys, areas)` — the STRtree plus the area threshold
  (`1e-6 * min(area_i, area_j) + 1e-9`), results sorted by `(left, right)` because STRtree order
  is unspecified. `overlap_excluded(polys, areas)` is rule 3 of the merge, built on it;
  `engine/fixes/merge.py` now imports both it and `region_frame` from here, so "these two faces
  overlap" means one thing in both places. A test pins that they are the same object.
- `covered_fractions(topo, faces)` and the `_RegionCover` behind it — `area(face & union of the
  other faces of ITS REGION) / area(face)`, over only the region-mates that actually intersect
  the face.
- `plan_overlap_removal` — a candidate is a face in a same-material pair with
  `covered >= 0.99`. Candidates are then walked smaller-patch-first (edge adjacency, so the
  smaller LAYER loses) and higher-face-id-first within a patch, and each is RE-MEASURED against
  what is still kept: it is dropped only if still covered then. The first copy of a stacked pair
  goes, the second finds its coverer gone and stays, a third copy goes too.
- `remove_overlaps` — the plan confirmed by `guard_feedback(strict=True)` over all 26 views,
  against the same mesh it was handed. Restored candidates stay and are counted.
- `FixResult` gains `removed_overlap`, `restored_overlap`, `n_overlap_pairs_same`,
  `n_overlap_pairs_diff`, `n_removed_overlap`, `n_restored_overlap` and
  `overlap_pairs_diff_material` (ORIGINAL face ids, materials, area); all of them are in
  `report.json`, and the four counts in `preview-data`'s `stats`. Different-material overlaps are
  never removed: which of two colours a person wants is not a question geometry can answer.

### A rule I changed after measuring, and why

My first version only dropped a face when BOTH members of a pair were covered (protect one
winner per pair). Measured on file A: 153 faces in same-material pairs, **88** covered at 0.99,
but only **63** pairs with both members covered — so the pairwise rule proposed 36 and the run
went 1,674 to 1,630 triangles. Re-measuring each candidate against what is still kept is both
simpler and strictly safer (it is the actual invariant — "the rest of my region still covers me"
— rather than a proxy for it), and it took the same run to 1,610. The brief's tie-break is kept,
expressed as the walk order rather than as a special case.

### Tests (written first, watched fail: `cannot import name 'overlap'`)

New `engine/tests/test_overlap.py` (14 tests) and two fixtures. `stacked_duplicate_slab` is a
`grid_slab` carrying a second copy of its own surface (`weld_exact` folds the copies onto one set
of welded vertices, so at one material the copy lands in the SAME region — which is what the real
walkway does); `top_material=1` makes it a different-material z-fight instead.
`partially_overlapping_fins` is two coplanar triangles hinged on the slab's boundary edge, each
covering exactly half of the other (187.5 of 375 sq in) and covering no slab face.

- the duplicated layer is found as `n` same-material pairs, one per face, and nothing else;
- the different-material copies are found ACROSS regions in one plane, with an assertion that
  they really are separate regions, so the test would fail against a per-region search;
- a plain `grid_slab` yields no pairs at all although every neighbouring triangle `intersects` —
  the area threshold is what decides, not the STRtree predicate;
- a duplicated layer loses exactly one copy, the COPY and not the original, with
  `n_restored_overlap == 0`, and the de-duplicated slab then merges to ONE region of 2
  triangles — with the counterpart test showing that, left alone, the same slab makes the merge
  skip the region outright (`regions_skipped == {"overlap": 1}`) and merge nothing at all;
- a partial overlap is never a candidate (coverage 0.5 exactly), and at a loosened threshold of
  0.4 exactly one of the two fins goes, never both;
- a different-material overlap is reported with face ids and materials and nothing is removed;
- a guard stub that restores everything leaves the mesh untouched and reports
  `n_restored_overlap`;
- determinism, and three `fix_object`-level tests for the new `FixResult` fields.

### Real data

| | file A `ce26e0392ab0` | file B `0b290ec0bcb4` |
|---|---|---|
| triangles, before this item | 4,692 to 1,674 | 7,227 to 1,173 |
| triangles, after | 4,692 to **1,610** | 7,227 to **1,138** |
| `faces_copied` | 914 to **804** | **450** |
| `regions_skipped` | `{overlap: 9, invalid_polygon: 3}` to **`{overlap: 1, invalid_polygon: 3}`** | `{overlap: 1, new_vertex: 1, invalid_polygon: 1}` |
| overlap pairs same / diff | 148 / 0 | 86 / **9** |
| removed / restored | 56 / 0 | 28 / 0 |
| `regions_merged` | 169 to 176 | 95 |
| guards | both pass | both pass |

`regions_skipped.overlap` fell from 9 to 1, which was the brief's first target. File B's 9
different-material pairs are the z-fight the guard's tie test was written for, now reported with
their face ids rather than only inferred from tie pixels.

### `faces_copied` is 804, not "far below 914" — where the rest goes (measured)

At the merge's input (2,600 faces, 273 regions):

| source | faces |
|---|---|
| single-face regions (`len(members) < 2`) | 93 |
| rule-3 overlap exclusions inside multi-face regions | 16 |
| **three regions failing LATE with `invalid_polygon`: 28 (220), 29 (203), 83 (276)** | **699** |

So almost all of what is left is three large regions whose polygon shapely calls invalid even
with every ring vertex kept — a merge-robustness defect, not an overlap one, and outside this
item. Filed as a follow-up task with the reproduction driver. The same run also shows 9 regions
hitting `area_grew` during the feedback rounds and recovering, which is the rule 6 / rule 9
inconsistency measured under MQ2.

### Result

`.venv/Scripts/python.exe -m pytest engine/tests -q` → **247 passed** (230 + 17).

---

## S1 `feat(engine): solidify slab regions with skirts and bottoms under a cap guard`

### What changed

New `engine/fixes/solidify.py` — `solidify(mesh, topo, profile) -> SolidifyResult(mesh,
new_faces, report)` — wired into `fix_object` BEFORE exposure and removal when
`profile.solidify` (default True; `--no-solidify` on both CLI commands). It is the only step in
the engine that invents a vertex, and even here a shifted vertex that ROUNDS onto an existing
position reuses that row, so a slab whose skirts already reach the right depth invents none.

Per top-surface region: the outline from `engine.fixes.merge.region_outline` (newly exposed, so
the skirt hangs on the SAME union, with the same overlap exclusion and vertex mapping, that the
merge will later rebuild the region from); open outline edges are those with edge-table count 1;
local thickness per open edge is the top z minus the lowest z of the side faces sharing either
endpoint, else of side faces within `skirt_search_radius` of the edge midpoint; `h_R` is the
median of the resolved ones, else the file-wide median, clamped to `[min_thickness,
max_thickness]`; a skirt quad per open edge wound outward from the region centroid, with one
shifted vertex per original; a bottom from the outline polygon (outer plus inners) shifted down
by `h_R`, triangulated with `shapely.constrained_delaunay_triangles` over the shifted vertices
and wound down, unless a ray straight down from `bottom_exists_fraction` of the region's
centroids already meets something within `h_R + tol`. New faces take the region's material and
get UVs by planar projection in their own plane at the region's own `sqrt(|det J|)` scale.

`engine/guard/compare.py` gains `solidify_feedback` — the CAP GUARD. Only faces are added, so a
changed pixel is exactly one whose AFTER first hit is new; such a pixel is allowed only when what
it covers is background, a back side (`n . view_dir > 0`), or a face whose exposure has gone to
zero. Anything else marks that new face; marked faces are dropped and the whole thing runs again
(removing one new face can expose what another was covering), to 8 rounds.

`FixProfile` gains `solidify`, `top_min_nz`, `top_sky_fraction`, `skirt_search_radius`,
`min_thickness`, `max_thickness`, `bottom_exists_fraction`. `FixResult` gains `solidify_report`,
`guard_solidify` (the cap guard's per-round history — the only comparison in the run still made
against the PRISTINE input) and `reference_mesh`. Pipeline order is now: analyse → solidify →
exposure on the solidified mesh → hidden removal (strict) → slit → flip → overlap removal →
merge → final guard, with the final guard, `guard_after_removal` and the invariants all measured
against the SOLIDIFIED mesh, which is the reference a person accepted when they asked for the
sides to be built.

### Three deviations from the brief, each forced by a measurement

**1. A top surface is `|n_z| > top_min_nz` PLUS a sky test, not `n_z > top_min_nz`.** The signed
test reads the winding, and the winding is what these exports get wrong: 809 of file A's faces
are wound backwards, and `open_box_with_cells` is wound inward throughout — its z = 10 LID has
`n_z = -1` and its z = 0 FLOOR `n_z = +1`. A signed test takes the floor for the top surface and
hangs a skirt underneath the box, which is the opposite of the brief's own test (a). So a region
qualifies when it is horizontal AND at least `top_sky_fraction` of its faces escape a ray cast
straight up — a fact about the model rather than about the exporter's bookkeeping. It rejects the
underside of a slab (the slab is above it) as cleanly as it accepts a lid wound the wrong way.
`test_a_top_sheet_wound_downwards_is_still_a_top_sheet` pins it.

**2. The cap guard's third allowance is PER SIDE.** "A face whose exposure in the solidified mesh
is 0" cannot be right as written, because exposure is double-sided: the face you see through an
opening is very often part of the outer shell — the inside of the far wall, or the underside of a
top sheet whose other side sees sky — and its exposure is never 0. Measured on
`open_box_with_cells`: with a whole-face test the one skirt that closes the box is refused
because it covers the inside of the far wall, and the step can never do its job at all. The rule
is now the exposure of the SIDE the ray met the face on, decided by the same `n . view_dir` that
rule 2 already reads.

**3. A bottom is only invented at a thickness that was MEASURED.** When nothing in the whole file
resolves, `h_R` falls through to `min_thickness`, which is a guess. Measured on
`box_with_partition`, whose closed cube has no open outline edge anywhere: that put a lid 2 in
under the top, INSIDE a solid box. A skirt on that fallback still runs — it closes a hole a
person can see, and the cap guard judges it — but a floor at a made-up depth is pure invention.
Reported as `bottom_thickness_unresolved`.

### One thing I decided NOT to change, and why

The skirt uses the REGION's median thickness, not each edge's own measured one, although the
per-edge numbers are computed and a per-edge skirt would fit the model far better. Two adjacent
open edges with different local thicknesses would put their shifted corners at different depths
and open a crack between the two skirts — exactly the kind of hole this step exists to close. The
cost is visible in the numbers below: the cap guard refuses 157 of file A's 418 new faces, which
is the variance (2.0 to 29.5 in within one file) showing up as skirts that overhang the thin
places. That is the guard doing its job, not a defect, but it is why `faces_newly_hidden` comes
in at 96 rather than the spikes' 182.

### Tests (written first, watched fail: `No module named 'engine.fixes.solidify'`)

New `engine/tests/test_solidify.py` (13 tests) and two fixtures. `slab_with_three_skirts` is the
sidewalk's shape in miniature — a top at z = 0, skirts on three sides to z = -8, the fourth open,
no bottom — with every corner at -8 already present, so a correct skirt and bottom invent nothing.
`two_level_slab` adds a deep fin that makes the open edge measure 200 in on an 8 in slab, and a
panel below that stays exposed on its far side.

- (b) one skirt quad of measured height 8 and a bottom at z = -8 facing down, 4 new faces,
  **0 invented vertices**, and the result is a closed solid (every edge count 2);
- the skirt is wound OUTWARD (-x on a slab lying at x > 0);
- (c) the same fixture with a bottom already there: `bottom_exists`, skirt only;
- (a) `open_box_with_cells` gets its missing side, the only edges left open belong to the two
  floating partitions, and `faces_newly_hidden == 4`; through `fix_object` the partitions are
  then removed and the result is a closed box;
- (d) the deep-fin fixture at `max_thickness=1000`: the whole skirt quad is refused, in 2 rounds
  — and, in a companion test, refused at the DEFAULT ceiling too, because 200 clamped to 36 is
  still 28 in of skirt hanging below an 8 in slab. The clamp bounds how wrong a measurement can
  get; only the guard decides whether the result is acceptable. A third test fixes the
  measurement (`deep=8`) and the same skirt is kept;
- (e) determinism, (f) `--no-solidify` reproduces the previous numbers on `box_with_partition`,
  and the default profile agrees with it face for face there because a closed cube has nothing
  to solidify.

Three EXISTING tests in `test_pipeline.py` now pass `solidify=False`:
`test_accept_slit_removes_a_barely_exposed_interior_face_under_a_colour_tolerant_guard` (its
`open_box_with_cells` gets closed, which hides both partitions — S1's own subject),
`test_fix_object_reports_a_thin_sheet_without_touching_it` (a free quad IS a top surface with
four open edges) and
`test_a_sliver_that_only_the_relative_test_calls_zero_area_is_kept_by_the_guard` (its floor gets
skirted, moving the pixel it aims at). None of them is weakened: each keeps testing exactly the
step it was written for, and the new behaviour has its own tests.

### Real data — file A `ce26e0392ab0`, default profile

| | |
|---|---|
| top regions processed | 105 |
| skirts added | **99**, 4,934.5 in of edge |
| bottoms added / already there / outline unmappable | **21** / 83 / 1 |
| thickness per region | min 2.0, median 9.84, max 29.52 in |
| vertices invented | **263** |
| cap guard | 3 rounds, 27,195 → 169 → 0 failing px, **157 of 418 new faces refused** |
| faces newly hidden (exposure before vs after) | **96** (1,853 → 1,949) |
| solidify runtime | 11.3 s of 43.0 s total |
| triangles | 4,692 input → 4,953 reference → **1,600** |
| hidden candidates / restored / removed | 2,148 / 40 / 2,108 |
| overlap pairs same / removed / restored | 201 / 55 / 0 |
| `regions_skipped` | **`{invalid_polygon: 3}`** — no `overlap` left at all |
| `faces_copied` | **798** |
| one-sided holes | 569,253 → **116,482** |
| guards | all pass |

### Interior faces left, stated honestly

The shipped file A mesh has **41 faces at exposure 0** of 1,600 (24,122 of 1,215,176 sq in, 2.0 %
of the area). Forty of them are hidden faces the STRICT removal guard refused to delete —
removing them changed a pixel over 26 views, so they stay by design — and the merge left one
more. The brief's ideal was none; this is what the measurement says, and the reason it is not
zero is the guard, not a missing step.

`faces_newly_hidden` is 96 where the spikes predicted 182. The gap is the 157 new faces the cap
guard refused, which is the per-region median thickness meeting a file whose real skirts vary
from 2.0 to 29.5 in — see "one thing I decided not to change" above.

### Result

`.venv/Scripts/python.exe -m pytest engine/tests -q` → **260 passed** (247 + 13).

---

## MQ4 `fix(preview): rollback-aware heading, angles from stats, honest flicker label`

### What changed

`preview/index.html` and `engine/cli.py`'s `preview-data`. Three sentences the page was saying
on its own authority now come from the data it is handed:

1. **The AFTER heading.** It was a static `<h2>AFTER · inside removed, flat regions rebuilt</h2>`,
   which is a promise the page cannot keep: when the merge is rolled back the AFTER pane shows
   the removal-only fallback and no region was rebuilt at all. It now reads
   `stats.merge_rolled_back` and says "merge rolled back" in red instead.
2. **The soft-crease thresholds.** The toggle read "soft creases (1-5°)" while `FixProfile` has
   carried `coplanar_angle` and `soft_angle` as settings since M2. `preview-data` writes both and
   the label names them.
3. **`guard_damaged_px` included `edge_flicker`.** Flicker is the class `compare_views` promotes
   a pixel INTO when the two pictures differ only by a boundary that moved less than the
   tolerance, and the final guard tolerates it up to `edge_flicker_cap_final` — so a page that
   counted it as damage reported the opposite of the guard's own verdict. It is now its own
   stat, `guard_flicker_px`, labelled "flicker px tolerated".

The BEFORE pane also names what closing the slab added (`tris_input`, `skirts_added`,
`bottoms_added`, `invented_vertices`, `faces_newly_hidden`), because the BEFORE pane is now the
REFERENCE mesh — the export plus whatever `solidify` added — and showing one count without the
other would be misleading. The AFTER line names `n_removed_overlap` of `n_overlap_pairs_same`,
and the `n_overlap_pairs_diff` different-material overlaps that are only ever reported.

### Tests

Five, in `test_cli.py`. The existing
`test_preview_data_writes_every_stat_and_edge_list_the_page_reads` still extracts every
`${s.<name>}` from the HTML and checks `preview-data` writes it, so the new stats cannot drift
apart from the page.

- `test_preview_page_names_its_soft_crease_thresholds_from_the_data` — no "1-5" anywhere in the
  page, and both angle stats interpolated;
- `test_preview_page_heading_is_written_from_the_rollback_flag` — no static `<h2>AFTER`, and the
  heading expression reads `s.merge_rolled_back`;
- `test_preview_page_calls_tolerated_flicker_what_it_is`;
- `test_preview_data_keeps_tolerated_flicker_out_of_the_damaged_count` — a run whose final guard
  reports 7 flicker pixels per view and nothing else: `guard_flicker_px == 182`,
  `guard_damaged_px == 0`, `guard_passed` True;
- `test_preview_data_reports_what_closing_the_slab_added` — `slab_with_three_skirts` through
  `cmd_preview_data`: 8 input triangles, 12 in the reference, 1 skirt, 1 bottom, 0 vertices
  invented.

Order, stated honestly: I wrote this item's implementation before its tests, unlike every other
item in this round. To confirm the tests are real I restored `preview/index.html` and
`engine/cli.py` from `HEAD` and re-ran them: **4 of the 5 fail** against the previous version
(`KeyError: 'guard_flicker_px'`, and three source assertions). The fifth,
`..._reports_what_closing_the_slab_added`, passes against HEAD because those stats landed with
S1 — it is a regression test for them, not for this change, and I am not claiming otherwise.

### Result

`.venv/Scripts/python.exe -m pytest engine/tests -q` → **265 passed** (260 + 5).
