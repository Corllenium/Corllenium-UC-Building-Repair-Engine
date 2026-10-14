# Task P2-V2 report: the Validator judges removed and covered faces to the owner's floor

**Status: DONE_WITH_CONCERNS.** Worktree `.claude/worktrees/P2-V2`, branch `claude/P2-V2`, base 7258652. Not merged,
not pushed. Skills: `uc-repair-rules` (read first), test-first throughout.

The owner's floor is in AGENTS.md §5 on `feat-dashboard` (8e40db5), so the brief and AGENTS.md agree.
Controller rulings V2-R1, V2-R2 and V2-R3 are applied; see "Interpretations" below.

## Commits

| commit | what |
|---|---|
| a1fe66d | item 1: `engine/validate/floor.py`, `face_visible_pixels`; `VISIBLE_FLOOR_PX = 4`, `FLOOR_IN_PER_PX = 0.02` |
| 19b608a | perf: `build_caster` casts big batches on a thread pool, with the same answers as one thread (measured equal) |
| 572e9a8 | item 2: removed faces, area-scaled lattice, floor measure, report, crops; CLI line |
| cb3ed1f | items 3 and 4: covered on every line from both sides; only new geometry can block |
| 9786cab | item 5: the site judge carries the floor; the kernel, E8 and CLI tests that change |
| 0d69683 | item 6 and the controller's docstring note: the checks module docstring describes the new judge |
| 077ae78 | docs: item 4's cause, corrected to what was measured |

Items 3 and 4 share one commit. Item 3 alone left 2 fill tests red. On the fill fixture, the dense pixel lines hit the corner
artefact that item 4 removes: unchanged faces "covered" pixels through shared edges. The red run is below.

**History note.** cb3ed1f leaves the E8, kernel, CLI and needs-modelling tests red until 9786cab. I ran only the
Validator suites at cb3ed1f. Those tests change because of item 3's every-line `covered`, and they were updated in
9786cab.

## Per item: tests, red, green

### Item 1, the floor measure
- **Test:** `engine/tests/test_validate_floor.py`, 11 tests. A 1 in square shows 2,500 px (±60) from above and from
  below. Also covered: the oblique view (half the area), edge-on and zero-area faces (0), a half lid, a z-fight layer, a hole, a
  camera with the pixel taken at the face (10 in and 1,000 in away both give 2,450 px), a probe over a wide fan
  (cube map), and the pixels lie on the face.
- **Red:** `ModuleNotFoundError: No module named 'engine.validate.floor'`.
- **Green:** `11 passed in 0.56s`.
- **How it works:**
  - Directions are drawn orthographically, on a 0.02 in grid through the face's centroid.
  - Cameras and probes are drawn on a six-plane cube map round the eye. The angular pitch is 0.02 in divided by the distance to the
    centroid, so faces that wrap round a probe are drawn whole.
  - A pixel counts when its float64 ray-face crossing lies within 0.02 in (z-fight) of Embree's first hit.

### Perf (part of item 2's needs)
- **Test:** `test_validate_threaded_caster.py`: threaded and serial `first_hit` and `any_hit` are array-equal.
- **Red:** ImportError. **Green:** 1 passed.

### Item 2, removed faces go to the measure
- **Tests:** `test_validate_floor_checks.py`, 5 tests:
  - lattice sizes: 49 / 100 / 4,096, capped;
  - item 6's mutation A, a 0.5 × 0.5 in patch of a removed face showing through a hole over a lattice point and no
    sample: FAIL, 600-650 px;
  - item 6's PASS case, the same face showing 3 px from its only viewpoint;
  - an unchanged floor measures nothing;
  - a crop is written for every face above 0 px.
- **Red** (the fixtures through the pre-change Validator, export of 19b608a, `C:/Temp/v2/red_on_base.py`):
  ```
  mutation A (0.5 x 0.5 in patch of a removed face): verdict PASS; check 3 PASS; deleted 0 covered 0 overlaid 0; floor in report: False
  ```
- **Green at the item 2 state:** `249 passed in 173.62s` (the Validator, site-judge and floor suites).

### Items 3 and 4
- **Tests:**
  - `test_validate_floor_covered.py`, 5 tests: mutation B (cover of only the back side), mutation C (cover of a
    second line whose witness is clear), a 0.5 in new plate that misses every sample (FAIL, ~625 px), a 0.015 in
    new face (PASS, ≤ 4 px), and a probe line;
  - `test_validate_floor_corner.py`, 2 tests: the subset fixture has lines one caster lets through and the other
    blocks; and a face-subset AFTER gives 0 covered for every viewpoint, lines through shared vertices included.
- **Red, item 3** (pre-change Validator):
  ```
  mutation B (cover of only the back side): verdict PASS; check 3 PASS; deleted 0 covered 0 overlaid 0
  mutation C (cover of a second line, witness clear): verdict PASS; check 3 PASS; deleted 0 covered 0 overlaid 0
  a 0.5 in new plate missing every sample: verdict PASS; check 3 PASS; deleted 0 covered 0 overlaid 0
  ```
  At the item 2 commit: `4 failed, 1 passed` (B, C and the plate PASS check 3; the covered candidates do not exist).
- **Red, item 4** (at the item 3 state, every line but the whole-AFTER caster):
  `test_an_after_that_is_a_face_subset_of_before_covers_nothing_on_any_line: assert (8 == 0)`. The fill tests at that
  state also fail: the floor's pixel lines are "covered" by unchanged faces 42, 30, 33, 19 and so on.
- **Green (items 3 + 4):** `256 passed in 508.54s`.

### Item 4 measured on CHTM-L05 face 10553
BEFORE is the E8a output; AFTER is BEFORE minus E3's first-run removals, as in `covered_dbg.py`. Script:
`C:/Temp/v2/corner_chtm.py`, output in `corner_chtm.txt`.
```
BEFORE 20624 faces, AFTER 10583 (E3's first run removed 10041)
changed_faces(BEFORE, AFTER) (new geometry, the only faces that may block now): 0
  BEFORE caster: trimesh's float32 frame origin [-807.085, -767.7, -98.425] scale 0.0447135
  AFTER caster: trimesh's float32 frame origin [-807.085, -767.7, -98.425] scale 0.0447135
lines from the samples of 17149 and 17153 to every probe that BEFORE's caster sees clear and AFTER's whole-mesh caster blocks: 4
  sample 11 (face 17149) -> probe 1384 (851.2 in): AFTER's caster hits BEFORE face 10553 at 10.23 in; ray . normal(10553) = +0.9987
  sample 181 (face 17149) -> probe 1384 (854.9 in): AFTER's caster hits BEFORE face 10553 at 13.88 in; ray . normal(10553) = +0.9987
  sample 340 (face 17153) -> probe 1384 (842.4 in): AFTER's caster hits BEFORE face 10553 at 1.41 in; ray . normal(10553) = +0.9987
  sample 341 (face 17153) -> probe 1384 (846.3 in): AFTER's caster hits BEFORE face 10553 at 5.28 in; ray . normal(10553) = +0.9987
the new Validator's focus run on faces 17149 and 17153: {'before_faces': 2, 'after_faces': 0, 'status': 'PASS'} {'deleted': 0, 'covered': 0, 'replaced': 0} floor PASS
```
- These are exactly the 4 false `covered` samples of P2-E3 concern 3, and they are now 0, by construction.
- **Correction:** in cb3ed1f I wrote that the cause is trimesh rounding each mesh in its own frame. On CHTM the two frames are
  identical, so the cause there is the two Embree trees. In the unit fixture it is trimesh's per-mesh scale (0.26
  against 5.88). 077ae78 fixes the docstrings. Either way, the verdict on a line through a shared vertex or edge depends
  on the whole mesh, and blocking now comes only from AFTER faces whose exact corners are not a BEFORE face's
  (`changed_faces`).

### Item 5, the site judge
- **Test:** `test_site_judge_floor.py`, 2 tests:
  - a focus run fails a removed face the floor fails, and charges the site that removed it (touched; E3-R8 intact);
  - removing a sealed face passes.
- **Red:** `KeyError: 'floor'`, twice. **Green:** `47 passed` (site judge suites). Then the kernel and engine tests that use the judge:
  `55 passed`, plus attribution and kernel `21 passed`.
- **How it works:** each failing floor face becomes a failing row `(face, -1 - viewpoint)`, with a lost pixel's point and
  the viewpoint as witness. Its cluster counts it once per reason, so `{"deleted": 1}` for a pure removal.

### Item 6
The four mutations are the tests named under items 2 and 3, all green.

## Interpretations (please rule)
1. **V2-R3 and UV.** The floor's lost pixels are covered, deleted or replaced (another look). A UV shifted under the same look stays
   check 1's `uv`, so check 3 is not made to fail on UV. Counting UV as lost broke
   `test_uvs_shifted_by_half_fail_check_1_and_only_check_1`. I read "same look and UV" as describing where nothing
   was lost, not as making UV-only changes removals.
2. **Which lines may cover.**
   - The witness line and the best-probe line keep today's test along the line, so nothing today fails passes now.
   - Every further line also needs the blocker beyond the tolerance square to the sample's face. Without that, a layer 0.03 in
     over a surface, met by a grazing line, became "covered" instead of "overlaid", and a surface moved 0.015 in
     "covered itself".
   - The floor asks "is the surface still at this place" square to the face, as the squarest witness would.
3. **Covered faces use the standard viewpoints.** Removed faces also use the 1,024 extra directions, as today's
   Validator does for gone faces.
4. **Lattice candidates.** A removed face is measured from a viewpoint only when a seen lattice point is lost there
   (V2-R3). For truly removed faces this is the same set; re-wound and re-cut faces are not measured from every
   viewpoint.
5. **Early stop.** Past 2^18 candidate rays, a measure stops as soon as it is above the floor, and reports `at_least`
   and `pixels_estimate`. This only shortens the count of faces that fail anyway.
6. **The floor never excuses a sample failure.** A face with a covered or deleted sample fails even if it measures
   ≤ 4 px. Whether ≤ 4 px faces may pass would loosen today's judge, and that is for the owner.

## Changed existing tests (each for the controller)
| test | change | reason |
|---|---|---|
| test_validate_fill_site::test_without_fills_validation_json_is_byte_for_byte_the_76ca35a_validator_s | the dump drops `checks.nothing_deleted.floor` | new report section; the rest stays byte-equal |
| test_validate_checks::test_the_cover_is_replayed_from_the_probe_only_where_it_is_not_already_the_best_viewpoint | replaced by `test_the_cover_is_judged_on_every_line_and_cast_only_into_new_geometry` | the replay it counted is gone (item 3); the new test pins 0 casts for an unchanged AFTER and one per seen line otherwise |
| test_validate_checks::test_a_cover_only_an_eye_height_probe_sees_is_found_and_the_crop_is_drawn_from_the_probe | covered count is bounded between strictly-inside and edge-inclusive scratch sets | one line passes exactly through the panel's edge (y = 40.0); the new-geometry caster calls the tie a hit (485 vs 484) |
| test_site_judge::test_the_check_is_the_validators_focus_run_and_names_its_failing_samples | sample set compared on index ≥ 0; asserts the floor's row too | `failing` holds the floor's row (item 5) |
| test_site_attribution: verdict_names, touched_site, two_plates, no_given_site | 5 rows, not 4; the second plate is charged too; the "unknown" case asks a site that changed nothing | floor row; under every-line judging the second plate does cover the face from the 45° viewer its docstring names |
| test_kernel_site_checks::test_two_good_sites_and_one_bad... | failing / charged / touched 5, reasons `{"deleted": 5}` | the floor's row for the deleted face |
| test_e8_solidify::test_a_piece_covering_what_only_a_probe_sees... | NOTHING KEPT; every piece rolled back for covered; the probe wall is among them | the far slab's caps hide its underside and end, seen from below and beside |
| test_e8_solidify::test_pieces_that_cover_nothing_visible_are_all_kept_and_the_stage_passes | renamed `test_pieces_closing_an_open_slab_cover_its_inside_seen_from_below_and_are_rolled_back`, inverted | same cause, on the three-skirt and half-side slabs |
| test_cli_repair_unit: writes_outputs, snapshot_folder, exit_code_0 | kept 0, rolled back 2 `{"covered": 2}`, NOTHING KEPT, exit 0 | same cause |
| test_cli_repair_unit::_FarNoiseJudge (used by exit_code_3 and needs_modelling's stage test) | reports only its unchargeable noise row | otherwise every piece is rolled back on its own charge before the stage could be rolled back whole; the test is about exit 3 |
| test_cli_needs_modelling::test_a_kept_piece_is_not_listed | renamed `test_a_piece_rolled_back_on_its_own_charge_is_listed`; the entries are listed | same cause; no E8 piece is kept any more |

None of these loosens the judge. Each moves an expectation to the stricter verdict, or pins a test harness.

## Acceptance output

**Engine suite** (final, 077ae78):
```
FAILED engine/tests/test_solidify.py::test_a_tooth_given_back_at_real_scale_leaves_no_double_layer[2000.0]
FAILED engine/tests/test_solidify.py::test_a_sign_in_front_of_a_tooth_is_never_a_piece[2000.0]
FAILED engine/tests/test_solidify.py::test_a_lamp_under_a_slab_is_never_a_piece_of_its_bottom[40.0]
FAILED engine/tests/test_solidify.py::test_a_lamp_under_a_slab_is_never_a_piece_of_its_bottom[2000.0]
FAILED engine/tests/test_solidify.py::test_a_middle_strip_of_a_side_is_a_piece_and_the_side_is_closed[40.0]
FAILED engine/tests/test_solidify.py::test_a_middle_strip_of_a_side_is_a_piece_and_the_side_is_closed[2000.0]
FAILED engine/tests/test_solidify.py::test_a_wall_takes_the_look_of_the_pieces_it_really_replaces
7 failed, 1869 passed, 1 xfailed in 1925.82s (0:32:05)
```
All 7 are `numpy._core._exceptions._ArrayMemoryError: Unable to allocate 2.06 MiB` to 12.4 MiB inside `solidify` /
trimesh, which this job does not touch: the shared machine ran out of memory. Rerun alone:
```
engine/tests/test_solidify.py: 112 passed, 1 xfailed in 297.68s (0:04:57)
```
So 1,876 passed and 1 xfailed, with the 7 confirmed on a rerun. I could not get one clean full pass, because of the machine's memory.

**Tools suite:** `180 passed in 14.61s`.

### Item 7: the golden outputs re-judged
Inputs:
- the E8a outputs `C:/Temp/e3/<unit>_e8a`;
- the E8a+E3 outputs `C:/Temp/e3/r1/<unit>` (merged code);
- BEFORE: snapshots ce26e0392ab0 and 0b290ec0bcb4, and CHTM-L05's `before/`.

The old Validator is an export of base 7258652. Both ran one at a time on the same machine with no other job of mine.
Script: `C:/Temp/v2/run_item7.sh`; outputs in `C:/Temp/v2/val_old/` and `C:/Temp/v2/val_new/`. Check 2 FAILs in every run
(signed targets, as in P2-E3).

| run | old: checks 1 / 3 | new: check 1 | new: check 3 (samples) | new: floor | old s | new s |
|---|---|---|---|---|---|---|
| swA E8a | PASS / PASS | FAIL 937 covered | FAIL 937 covered | FAIL 97/97 covered faces | 29 | 28 |
| swA E8a,E3 | PASS / PASS | FAIL 937 covered | FAIL 937 covered | FAIL 109/111 (97 covered + 12 of 14 removed) | 27 | 58 |
| swB E8a | PASS / PASS | FAIL 22 covered | FAIL 22 covered | FAIL 24/24 covered | 59 | 50 |
| swB E8a,E3 | PASS / PASS | FAIL 22 covered | FAIL 22 covered | FAIL 34/34 (24 covered + 10 removed) | 72 | 150 |
| CHTM-L05 E8a | PASS / PASS | PASS | PASS | PASS (0 candidates; 27 new faces, 18,824 lattice pts) | 434 | 188 |
| CHTM-L05 E8a,E3 | PASS / PASS | PASS | FAIL (floor) | FAIL 55/58 removed | 330 | 1,345 |

**Time.** On CHTM 5th the new Validator takes 1,345 s against 330 s (E8a+E3); the floor accounts for 1,155 s of that, almost
all of it the lattice: 2,682,464 points on 8,468 removed faces against 2,579 viewpoints. With E8a alone it takes 188 s against 434 s:
threaded casts, and covers cast only into 27 new faces.

The new CLI's printed lines (real output; the problems line is cut after "targets signed"):
```
== new swA_E8a,E3
  textures        FAIL        41636 samples seen in BEFORE, 937 failed {'covered': 937, 'overlaid': 0, 'deleted': 0, 'look': 0, 'uv': 0, 'side': 0}
  nothing_deleted FAIL        0 deleted, 0 replaced, 937 covered, 0 overlaid (0 samples only the 1024 extra directions saw)
  floor           FAIL        109 of 111 measured faces show more than 4 px at 0.02 in/px (lattice 155290 points on 1060 faces); worst face 1669 (covered) 154981 px from direction 66
  time 57.13 s, peak working set 445.6 MB, peak commit 1166.1 MB
== new swB_E8a,E3
  textures        FAIL        91154 samples seen in BEFORE, 22 failed {'covered': 22, ...}
  nothing_deleted FAIL        0 deleted, 0 replaced, 22 covered, 0 overlaid (1 samples only the 1024 extra directions saw)
  floor           FAIL        34 of 34 measured faces show more than 4 px at 0.02 in/px (lattice 368954 points on 1631 faces); worst face 6890 (covered) 18884 px from direction 44
  time 148.56 s, peak working set 963.7 MB, peak commit 1699.1 MB
== new chtm5_E8a
  floor           PASS        0 of 0 measured faces show more than 4 px at 0.02 in/px (lattice 1800 points on 2 faces)
  time 187.13 s, peak working set 1095.8 MB, peak commit 1866.9 MB
== new chtm5_E8a,E3
  nothing_deleted FAIL        0 deleted, 0 replaced, 0 covered, 0 overlaid (0 samples only the 1024 extra directions saw)
  floor           FAIL        55 of 58 measured faces show more than 4 px at 0.02 in/px (lattice 2682464 points on 8468 faces); worst face 11816 (removed) >=22068 px from probe 1339
  time 1344.24 s, peak working set 1082.3 MB, peak commit 1853.1 MB
```
All lines: `C:/Temp/v2/item7_logs.txt`. Summary of every failing face: `python C:/Temp/v2/summ7.py new`.

**Failing faces, the worst** (pixels lost from the worst viewpoint; `>=` means stopped early, with an estimate):
- **swA (E8a covers):**
  - 1669: 154,981 px (direction 66; covering new faces 4692/4693);
  - 1684: 154,106 (camera 14);
  - 1662: 153,546;
  - 1686: 105,982;
  - 1685: 86,744.
- **swA, removed by E3:**
  - 3987: 12,046;
  - 4551: ≥ 1,181;
  - 2741: ≥ 1,102;
  - 3141: 964;
  - 122: 474;
  - 119: 438;
  - 890: 380;
  - 3396: 380;
  - 2594: 97;
  - 1396: 84;
  - 3253: 53;
  - 1481: 9.
  - 2587 (4 px) and 3254 (2 px) pass.
- **swB:**
  - 6890: 18,884 covered (new face 5619);
  - 6891: 8,351;
  - 5976: 4,860;
  - 7046: removed, ≥ 3,456 (estimate 16,370);
  - 1533: removed, 1,742.
- **CHTM (all removed):**
  - 11816: ≥ 22,068 "replaced" (probe 1339; estimate 310,225);
  - 4011: ≥ 8,663;
  - 9225: ≥ 8,571;
  - 16754: ≥ 1,376;
  - 3870: 1,118;
  - 16676: 579;
  - 3490: 361;
  - 15904: 324;
  - ... 55 in all. 2681, 2762 and 9832 measure 0 px.

**The crops, looked at** (`C:/Temp/v2/val_new/<run>/floor/face-NNNNN.png`, BEFORE | AFTER, lost pixels mixed with magenta):
1. **swA face 1669:** BEFORE shows faces seen from behind (purple tint) with the face's lost band. In AFTER the whole window is one grey front
   face, E8a's new cap, in front of it.
2. **swA face 1684 (camera 14):** the same pattern; a lighter grey new face hides the band.
3. **CHTM face 11816 (probe 1339):** in BEFORE the band is speckled: coincident layers in two looks z-fight. In AFTER, with
   E3's copy removed, a uniform surface seen from behind fills it. A real visible change: the flicker resolves to
   another surface.
4. **CHTM faces 4011 and 9225 (probe 1227):** BEFORE has a speckled band between two surfaces seen from behind. In AFTER a large
   dark front surface fills most of the window. A large visible change.
5. **swB face 6890:** BEFORE has a marked wedge of the face; in AFTER a lighter grey new E8a face covers it.

Also seen:
- swA 3987: a thin strip; another back face shows through after removal.
- swB 7046: a light grey wedge turns purple.
- CHTM 3870: a sliver along an edge; the boundary visibly moves.
- CHTM 16754: BEFORE and AFTER look identical and show no marks, although 1,376 px count as lost. The crop window
  missed the lost pixels, or the new look has the same mean colour. Treat that crop as uninformative.
- The stripes in some crops are the early stop: only the rows measured are marked.

## Concerns, said plainly
1. **E8a vs the owner's both-sides rule.** Every E8 fixture I tried (13 of them) ends NOTHING KEPT under the new judge, and
   sidewalk A's 5 E8a faces cover 97 previously visible faces. Closing an open slab hides its inside: the underside
   and inner skirts, seen from behind from below or beside it. Today's Validator never asked those back-side lines.
   This is the rule as written; whether views from below the ground count, and whether an open solid's inner backs
   count, is for the owner. Until then E8a ships nearly nothing.
2. **E3's output fails the floor on all three units:** 12 / 10 / 55 removed faces, matching P2-E3 concern 1. On CHTM the
   worst are flicker layers whose removal shows another surface.
3. **Time on CHTM:** 1,345 s against 330 s, mostly the brief's lattice (1 per sq in). Inside a repair-unit run, E3's two
   focus checks will each pay roughly this lattice on its removed faces. I did not re-run repair-unit with the new
   judge; that is hours, and the brief asked for the outputs to be re-judged.
4. **The machine's memory:** one full engine run hit 7 transient allocation failures (shown above). Not a clean
   single pass.
5. **Leaks through exact edges.** The BEFORE render, like any float32 caster, can see through an exact shared edge, and
   the floor would then count those pixels. On real data the measured faces match my independent feasibility counts
   (swA 3987: 12,499 visible against 12,046 lost), but I did not prove the absence of such pixels.
6. **Commit history:** cb3ed1f leaves kernel and E8 tests red until 9786cab (see above).
7. **Interpretations 1-6 above** need the controller's ruling, especially UV (1), the square-depth window on
   non-witness lines (2), and lost-only candidates (4).
8. I did not update HANDOFF, the ledger or QUEUE.md; the dispatch limited me to engine/validate, site_judge, the CLI, tests and
   this report.

Rules touched (§3-6):
- **§3 guards:** no `engine/guard/**`, no FixProfile, no `engine/repair/engines/**` change.
- **§3 test-first:** done per item, as shown above.
- **§5/§6:** the judge only became stricter or more exact. The one excused case is the corner artefact, measured as a false positive.
- **Outputs:** only under `C:/Temp/v2`.
- **Processes:** I stopped only my own, by PID: two stale pytest runs, 2198 and 539.

## Item 8: the owner's horizon rule (filed by the controller from the implementer's hand-back; the write was refused)

**Commit:** c0a7792, with the code, the new tests and the changed tests together.

**Suites at c0a7792:**

```
engine/tests: 1880 passed, 1 xfailed in 1388.50s (0:23:08)
tools/tests:  180 passed in 10.78s
```

### The sign rule

A direction `d` is a look direction; the viewer stands infinitely far off at `-d`. The model is Z up, so the viewer
is at or above the horizon when `d_z <= 0`.

- `viewpoints.above_horizon_directions(n)` keeps 64 of the 128 standard directions and 512 of the 1,024 extra ones.
- The Validator's defaults and the site judge (its stage viewpoints and `lattice_seen`) use them.
- Ring cameras and probes are unchanged. The 26 inside-vote rays are not viewpoints, so they still cover the whole
  sphere.
- **Not routed yet:** `engine/campus/needs_modelling.py` still uses the whole sphere.

### New tests (`test_validate_horizon.py`, 4)

- the kept directions have `d_z <= 0`, number n/2, and are a subset of the sphere;
- closing an open slab whose only visible inside is its underside is check 3 PASS;
- a plate over the top, seen from above, still fails `covered`;
- the slot mutation still fails the floor.

Red first: `ImportError`. Through the full-sphere Validator the open slab gives `check3 FAIL covered 122 floor failed
10`. Green: `4 passed`.

### The below-ground-only mutation that flipped to PASS

The fill over a box's open bottom (in `test_validate_fill_site`), renamed. It is still refused as dishonest (the
neighbours are not coplanar).

### Changed existing tests in item 8

- The cube and room tests in `test_validate_checks`: sample, face and direction counts, because the bottom is seen
  only from below the ground.
- `test_validate_focus`: the out-of-focus defect moves from the bottom face to the top face.
- The byte-for-byte fill_site test: both Validators are given the whole sphere explicitly.
- Two `test_kernel_site_checks` overlap helpers: they now drop the top face instead of the bottom.

### Item 7 again, with the horizon rule (outputs in C:/Temp/v2/val_new/)

| Run | Old checks 1 / 3 | New check 3 | New floor | Old s | New s |
|---|---|---|---|---|---|
| sidewalk A, E8a | PASS / PASS | FAIL, 167 covered | FAIL, 16 of 16 covered faces | 29 | 23 |
| sidewalk A, E8a+E3 | PASS / PASS | FAIL, 167 covered | FAIL, 25 of 27 (16 covered, 9 of 11 removed) | 27 | 47 |
| sidewalk B, E8a | PASS / PASS | FAIL, 2 overlaid | PASS | 59 | 49 |
| sidewalk B, E8a+E3 | PASS / PASS | FAIL, 2 overlaid | FAIL, 6 of 6 removed | 72 | 134 |
| CHTM 5th, E8a | PASS / PASS | PASS | PASS | 434 | 210 |
| CHTM 5th, E8a+E3 | PASS / PASS | FAIL (floor) | FAIL, 19 of 22 removed | 330 | 1,194 |

- **Against full-sphere:** sidewalk A 937 → 167 covered, 97 → 16 faces; sidewalk B covered 22 → 0; removed faces
  failing 12 → 9, 10 → 6, 55 → 19.
- **Worst faces:** sidewalk A 1669 154,981 px (covered by E8a's new faces 4691-4693, seen from above); CHTM 11816 ≥
  22,068 px (probe 1339).
- The crops are described; 8810 and 16754 are uninformative.

### Rulings V2-R4 to V2-R9

- **V2-R4:** UV changes stay with check 1.
- **V2-R5:** additional lines cover only beyond the tolerance along the line and square to the face.
- **V2-R6:** covered faces are judged on the standard viewpoints; removed faces also on the extra directions.
- **V2-R7:** a face is measured only where a seen lattice point is lost.
- **V2-R8:** the 2^18-ray cap reports `at_least` with `pixels_estimate`.
- **V2-R9:** the floor never excuses a sample-level failure.

### Concerns

1. Sidewalk A still has 16 faces covered by E8a. Those outputs were built by engines judged with the old Validator;
   the repair-unit re-run with this judge is the proof.
2. E3's outputs fail the floor: 9, 6 and 19 removed faces.
3. CHTM with E3 takes 1,194 s against 330 s.
4. `needs_modelling.py` still uses the whole sphere.
5. Some crops are uninformative.

## Fix round 1 (filed by the controller from the implementer's hand-back; the write was refused)

**Commits:** 093ee7a (re-ruled V2-R5), 342c5f0 (true-area perspective pixels), 2492e98 (present once per point and
side), f1eb82d (minors), 003c219 (crop marks 3 px wide). Each was green against the affected test files when made.

**Suites at 003c219:**

```
engine/tests: 1888 passed, 1 xfailed in 2320.73s (0:38:40)
tools/tests:  180 passed in 12.79s
```

### Item 1: V2-R5 re-ruled

- The square-to-the-face requirement applies only when the blocker is nearly parallel to the sample's face
  (|n_blocker · n_sample| ≥ cos 5°). Any other blocker beyond the along-the-line tolerance covers. The same rule
  applies to the new faces' reverse lattice.
- Test `test_a_plate_across_the_top_of_a_strip_covers_it_from_a_steep_viewer`: the strip shows over 500 px in
  BEFORE and 0 in AFTER. Red: check 3 passed. Green: check 3 FAILs and the floor fails the strip as covered. The two
  motivating cases (a surface moved 0.015 in, a 0.03 in overlay) stay excused.

### Item 2: perspective pixel size

- Each camera or probe pixel counts (r_i / D)² × its gnomonic factor (1 + s² + t²)^-1.5: its own area at 0.02 in
  across the line of sight. Direction views keep weight 1.
- Test `test_a_far_patch_of_a_big_face_counts_its_true_area_at_two_hundredths_across_the_line`: 1 × 1 in patches
  of the 400 in floor triangle from a probe at (5, 5, 63), at x = 60, 100, 266 and 390, each within ±15 % of
  2,500 × cos. Red: (60.0, 35133.0, 1873.2), the near patch at 18.8× and the far one at 0.5×. Green: 25 floor tests
  pass.

### Item 3: speed

- `present` is asked once per (lattice point, side); `blocker` is cast only for lines whose point is not already
  gone. The old path stays as a reference behind `_FLOOR_LATTICE_PER_LINE`; `test_validate_floor_speed.py` compares
  the whole report with the flag on and off on 3 fixtures (identical).
- **No measurable speedup:** CHTM-L05 E8a+E3 1,437 s → 1,425 s, floor 1,162 → 1,174 s. A profile on a tenth of the
  lattice puts `lattice_seen` at 140 of 433 s, almost all of it `visible_samples`: the lattice's visibility cast
  against about 2,000 viewpoints (1,403 probes). `present` and `blocker` are a small share. A faster floor needs a
  cheaper visibility cast for hidden points.

### Item 4: minors

- `needs_modelling.py:213` uses `above_horizon_directions` (test red 128 == 64, then green).
- The floor crop is centred on the largest cluster of lost pixels (`_crop_window` with the Validator's own
  `_components`); marks are drawn 3 px wide. CHTM 8810's loss is a one-pixel sliver about 29 in along a seam
  (4,281 px); its crop now shows a magenta line along the seam. 16754 is no longer measured since item 8 (its only
  view was from below the ground).
- Renames: the E8 test names and comments now say "beside and above" instead of "below". Measured drivers: the
  three-skirt slab by directions just above the horizon and the ring cameras through its open side; the half-side
  slab by directions from above and the cameras; the probe scene mostly by probes.

### Item 5: the floor's known limits

1. On very large faces the lattice is capped at 4,096 points (spacing up to 1.56 in), so a 0.5 in slot can be
   missed by every point.
2. Overlays stay at sample density (V2-R3).
3. A blocker within 5° of parallel and within the depth tolerance stays an overlay rather than a cover on grazing
   lines (the V2-R3 overlay class).
4. Floor pixel counts are float areas, not integers.

### Item 7 at f1eb82d (verdicts and failing faces match item 8's; pixel counts moved with item 2)

| Run | Old checks 1 / 3 | New check 3 | New floor | Old s | New s |
|---|---|---|---|---|---|
| sidewalk A, E8a | PASS / PASS | FAIL, 167 covered | FAIL, 16 of 16 covered faces | 29 | 29 |
| sidewalk A, E8a+E3 | PASS / PASS | FAIL, 167 covered | FAIL, 25 of 27 | 27 | 62 |
| sidewalk B, E8a | PASS / PASS | FAIL, 2 overlaid | PASS | 59 | 52 |
| sidewalk B, E8a+E3 | PASS / PASS | FAIL, 2 overlaid | FAIL, 6 of 6 removed | 72 | 137 |
| CHTM 5th, E8a | PASS / PASS | PASS | PASS | 434 | 234 |
| CHTM 5th, E8a+E3 | PASS / PASS | FAIL (floor) | FAIL, 19 of 22 removed | 330 | 1,798 (load) |

Worst faces: sidewalk A 1684, 1669, 1668, 1685 (each over 116,000 px, covered by E8a's new faces); sidewalk B 7046
removed (≥ 3,456 px); CHTM 11816 (≥ 15,320 px, probe 1339), 4011, 8810 (4,281 px), 9225. Every face is in
`C:/Temp/v2/summ7_new_v3.txt`; runs in `C:/Temp/v2/val_new/`.

### Concerns

1. No measurable speedup from item 3; CHTM with E3 stays at 1,400-1,800 s against the old 330 s.
2. E8a still fails 16 covered faces on sidewalk A and leaves 2 overlaid samples on sidewalk B.
3. E3's outputs still fail the floor: 9, 6 and 19 removed faces.
4. 003c219 (crop drawing only) was not in the item 7 runs; the suites ran on it.
