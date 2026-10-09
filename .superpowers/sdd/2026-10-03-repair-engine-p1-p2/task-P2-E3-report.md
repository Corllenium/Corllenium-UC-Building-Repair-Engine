# Task P2-E3 report: hidden faces, interior-aware, as the repair engine E3

**Status: DONE_WITH_CONCERNS.** Worktree `.claude/worktrees/P2-E3`, branch `claude/P2-E3`, base 9cae2d2.

- **Commits:**
  - eff9c66, the engine with its tests (items 1-5);
  - b238348, the CLI (item 6).
- **Tests:** 12 new tests, red then green. Engine suite: 1846 passed, 1 xfailed. Tools suite: 180 passed.
- **Golden units (`--engines E8a,E3`):**
  - The Validator's deleted count after rollback is 0 on all three.
  - The independent full Validator (original BEFORE against the final output) gives checks 1 and 3 PASS, with 0 deleted and 0 covered, on all three.
- **But:** a denser look than the Validator's samples finds about 12, 16 and 70 sq in of removed surface that some viewpoint does see (concern 1).

Skill used: `uc-repair-rules` (read before the first line of code), with test-first work.

## What E3 does, and the rules it applies

`engine/repair/engines/e3_hidden.py`, `E3Hidden`: name "E3", non-legacy. Its `plan()` works in four steps.

1. **The legacy candidates (E3-R1).**
   - `plan()` runs `stage_hidden` **unchanged** on the stage input, taken as the reference: `stage_solidify` with `solidify=False`, since E8a has already run.
   - Pass 1 (`removed_pass1`) is the candidate set: exposure 0 on both sides from every outside direction (`compute_side_exposure` / `classify_exposure`), or zero area, confirmed by the strict `guard_feedback`.
   - When E8a ran first, the faces its cap guard covered only through rule 6 (`seen_through_shell`) are left out, matched by K1 key, as the legacy stage leaves them out. E8Solidify keeps a new read-only `seen_through` record for this.
2. **Never side meshes (E3-R3).** Where the pipeline marks sides:
   - `solidify._side_faces`: a side face is one with `|n_z| <= top_min_nz`;
   - `_own_side_rows`: the sides hanging from a top's outline;
   - `_wall_pieces`: the pieces in the side band under an outline edge;
   - `replaced` / `replaced_group`: the broken pieces of a side;
   - `new_faces`, with `face_line = -1`: faces solidify invented. `stage_fragments` protects these as "invented".
   - `orient.py` has no side-mesh notion; its "sides" are a face's front and back.

   **The rule I used:** a face is a slab side when `SolidifyResult.side_faces` marks it, or when `face_line < 0`.
   - `side_faces` is a new **read-only** record. It holds the own sides of every top solidify plans, plus every piece it finds in a side band, whole or broken.
   - `face_line < 0` is solidify's own mark for an invented face; every E8 add carries it.
   - E3 runs solidify on its input as a measurement only, and throws the output away.
   - Measured: solidify's output is unchanged against base 9cae2d2 (output below).
3. **Never room surfaces (E3-R4).**
   - A face some eye-height probe sees, from either side, is no candidate.
   - The default view is the new `SiteJudge.probe_seen`: the Validator's own probes, samples and visibility. So `engine/repair` still imports nothing of `engine/validate`.
4. **Sites.**
   - One `remove` edit per edge-connected group, over the welded topology.
   - A group over 512 faces is split by a spatial grid (`split_group`).
   - Evidence: group, cell, faces, area, exposure (front/back max), the legacy rule per face ("hidden" or "zero_area"), centroid and bbox.
   - `report` holds the legacy counts, what each rule took out, the candidates, groups and sites, the probe numbers and the **disagreements**: exposure says hidden, a probe sees it (E3-R5). There is no libigl second opinion.

**CLI (E3-R6).**
- `repair-unit --engines` takes words or comma lists, run in the order given. `E8` is still E8a then E8b. Unknown names exit 2.
- report.json gains `stages_run` and `e3`: the engine report, sites kept and rolled back by reason, `faces_removed`, `deleted_after_rollback`, `after_rollback` and one `site_rows` entry per site.
- `_after_rollback` now also carries `deleted`.

Files changed:
- `engine/repair/engines/e3_hidden.py` (new);
- `engine/fixes/solidify.py` (the read-only `side_faces` record, +13 lines);
- `engine/repair/engines/e8_solidify.py` (the read-only `seen_through` record);
- `engine/site_judge.py` (`probe_seen`);
- `engine/cli.py`;
- `engine/tests/test_e3_hidden.py` (new);
- `engine/tests/test_cli_repair_unit.py` (one edit; see concern 6).

Nothing changed in `engine/guard/**` or `engine/validate/**`, and no FixProfile change.

## Items, with their tests, red and green

All 12 tests are in `engine/tests/test_e3_hidden.py`.

| item | tests |
|---|---|
| 1 engine shape | `test_e3_is_a_non_legacy_engine_named_e3`, `test_plan_gives_non_legacy_e3_removes_one_site_per_connected_group`, `test_apply_edits_reproduces_the_legacy_hidden_stage_when_nothing_is_rolled_back`, `test_plan_leaves_the_unit_mesh_alone` |
| 2 strict rule | `test_the_room_scene_plate_is_seen_only_from_eye_height` (fixture check), `test_a_group_holding_a_face_only_a_probe_sees_is_rolled_back_for_deleted` |
| 3 E3-R3 | `test_a_slab_side_unseen_from_every_viewpoint_is_never_a_candidate`, `test_a_face_solidify_invented_is_never_a_candidate` |
| 4 E3-R4 | `test_a_closed_room_seen_only_from_its_probe_keeps_every_face` |
| 5 splitting | `test_a_group_over_512_faces_is_split_by_a_spatial_grid` (2,048 faces) |
| 6 CLI | `test_repair_unit_runs_e8a_then_e3_in_the_given_order`, `test_repair_unit_refuses_an_unknown_engine_in_a_comma_list` |

How the tests are built:
- **Test 2 (strict rule).**
  - The fixture is `closed_room`, plus a plate whose lower half lies in the floor's sealed cavity and whose upper half stands in the room, plus two far sealed boxes with partitions.
  - The pre-filter is told the upper half is unseen, which is a miss it could make. So the plate's group is planned, and the judge must catch it.
- **Test 3 (E3-R3).** A slab's side is pressed against a taller block. The test first asserts that no viewpoint sees the side, and that the legacy stage would delete it.

**Red, first run** (the module did not exist):
```
E   ModuleNotFoundError: No module named 'engine.repair.engines.e3_hidden'
1 error in 0.83s
```

**Red, against a stub `E3Hidden` that plans nothing:**
```
E       assert ([])
E           AssertionError: assert Counter({'d3b...43bf2828': 1}) == Counter({'d3b...99c28a4c': 1})
E       StopIteration
E       KeyError: 'legacy_removed'
E       KeyError: 'excluded'
E       KeyError: 'legacy_removed'
E       KeyError: 'groups'
E       assert 2 == 0
FAILED ...test_plan_gives_non_legacy_e3_removes_one_site_per_connected_group
FAILED ...test_apply_edits_reproduces_the_legacy_hidden_stage_when_nothing_is_rolled_back
FAILED ...test_a_group_holding_a_face_only_a_probe_sees_is_rolled_back_for_deleted
FAILED ...test_a_slab_side_unseen_from_every_viewpoint_is_never_a_candidate
FAILED ...test_a_face_solidify_invented_is_never_a_candidate
FAILED ...test_a_closed_room_seen_only_from_its_probe_keeps_every_face
FAILED ...test_a_group_over_512_faces_is_split_by_a_spatial_grid
FAILED ...test_repair_unit_runs_e8a_then_e3_in_the_given_order
8 failed, 4 passed in 3.36s
```

Four tests passed against the stub, and I say so plainly:
- the name and attribute check;
- the unit-mesh-untouched check, which a stub that plans nothing passes trivially;
- the fixture-property check;
- the unknown-engine test, because today's code already refuses `E3,bogus` as a whole word.

**Green:**
```
engine/tests/test_e3_hidden.py::test_e3_is_a_non_legacy_engine_named_e3 PASSED
engine/tests/test_e3_hidden.py::test_plan_gives_non_legacy_e3_removes_one_site_per_connected_group PASSED
engine/tests/test_e3_hidden.py::test_apply_edits_reproduces_the_legacy_hidden_stage_when_nothing_is_rolled_back PASSED
engine/tests/test_e3_hidden.py::test_plan_leaves_the_unit_mesh_alone PASSED
engine/tests/test_e3_hidden.py::test_the_room_scene_plate_is_seen_only_from_eye_height PASSED
engine/tests/test_e3_hidden.py::test_a_group_holding_a_face_only_a_probe_sees_is_rolled_back_for_deleted PASSED
engine/tests/test_e3_hidden.py::test_a_slab_side_unseen_from_every_viewpoint_is_never_a_candidate PASSED
engine/tests/test_e3_hidden.py::test_a_face_solidify_invented_is_never_a_candidate PASSED
engine/tests/test_e3_hidden.py::test_a_closed_room_seen_only_from_its_probe_keeps_every_face PASSED
engine/tests/test_e3_hidden.py::test_a_group_over_512_faces_is_split_by_a_spatial_grid PASSED
engine/tests/test_e3_hidden.py::test_repair_unit_runs_e8a_then_e3_in_the_given_order PASSED
engine/tests/test_e3_hidden.py::test_repair_unit_refuses_an_unknown_engine_in_a_comma_list PASSED
12 passed in 26.10s
```

Commits: items 1-5 are in eff9c66 and item 6 is in b238348. I wrote all the tests first, in one file, so items 1-5 went into one commit rather than one commit each.

## Acceptance output

**Suites** (from the worktree root, PYTHONPATH set):
```
engine/tests: 1846 passed, 1 xfailed in 1092.01s (0:18:12)
tools/tests:  180 passed in 15.75s
```
Before committing, the touched areas ran alone (solidify, E8, site judge, kernel, legacy, e3): 330 passed, 1 xfailed.

**Solidify unchanged** (base 9cae2d2's `solidify.py` from `git show`, against this branch's, owner's profile):
```
ce26e0392ab0 mesh arrays equal: True | new_faces equal: True | replaced equal: True | report equal (minus runtime): True | side_faces: 759 of 4692
0b290ec0bcb4 mesh arrays equal: True | new_faces equal: True | replaced equal: True | report equal (minus runtime): True | side_faces: 1162 of 7227
```

**Golden runs.** Commands, from the worktree root, outputs in `C:/Temp/e3/`:
```
"$PY" -m engine.cli repair-unit --snapshot ".../data/snapshots/ce26e0392ab0" --engines E8a,E3 --out C:/Temp/e3/swA --materials ".../data/campus/materials.json"
"$PY" -m engine.cli repair-unit --snapshot ".../data/snapshots/0b290ec0bcb4" --engines E8a,E3 --out C:/Temp/e3/swB --materials ".../data/campus/materials.json"
"$PY" -m engine.cli repair-unit --unit CHTM-L05 --map ".../data/campus/campus_map.json" --source ".../data/campus/source.json" --engines E8a,E3 --out C:/Temp/e3/chtm5 --materials ".../data/campus/materials.json"
```
The same three with `--engines E8a` went to `C:/Temp/e3/<unit>_e8a`, giving the "after E8a" mesh. E8a is deterministic, so that mesh is E3's stage input; the visual script checks this by K1 key on every removed face. Each run exited 0.

Their E3 lines (long site-id lists cut):
```
CHTM_SIDE_WALK_2nd_floor: check E3 (E3, 174 edits, 174 sites): FAIL -> PASS; failing 228 {'deleted': 227, 'uv': 1}; unknown 0; rolled back [...]; 2 run(s), 37.5 s
CHTM_SIDE_WALK_2nd_floor: E3 legacy candidates 2037 {'hidden': 1820, 'zero_area': 217}, left out {'invented': 0, 'side': 420, 'seen_through_shell': 0, 'probe': 4}; 1613 candidate faces in 174 groups (0 split) -> 174 sites; kept 93, rolled back 81 {'deleted': 81, 'uv': 6}; removed 271 faces; deleted after rollback 0; disagreements 13
CHTM_SIDE_WALK_2nd_floor: covered after rollback 0; 4692 -> 4425 faces; 173.09 s; wrote C:\Temp\e3\swA

CHTM_2nd_to_3rd_building_sidewalk_outside: check E3 (E3, 147 edits, 147 sites): FAIL -> PASS; failing 441 {'deleted': 400, 'uv': 15, 'replaced': 26}; unknown 0; rolled back [...]; 2 run(s), 99.7 s
CHTM_2nd_to_3rd_building_sidewalk_outside: E3 legacy candidates 2471 {'hidden': 2392, 'zero_area': 79}, left out {'invented': 26, 'side': 476, 'seen_through_shell': 0, 'probe': 39}; 1930 candidate faces in 142 groups (1 split) -> 147 sites; kept 103, rolled back 44 {'deleted': 44, 'look': 2, 'uv': 11}; removed 789 faces; deleted after rollback 0; disagreements 42
CHTM_2nd_to_3rd_building_sidewalk_outside: covered after rollback 0; 7227 -> 6452 faces; 382.17 s; wrote C:\Temp\e3\swB

CHTM-L05: check E8 (E8, 216 edits, 209 sites): FAIL -> PASS; failing 16077 {'covered': 13350, 'overlaid': 41, 'deleted': 12, 'uv': 2674}; unknown 0; rolled back [...]; 2 run(s), 1188.2 s
CHTM-L05: check E3 (E3, 626 edits, 626 sites): FAIL -> PASS; failing 64 {'covered': 4, 'deleted': 56, 'replaced': 4}; unknown 0; rolled back [...]; 2 run(s), 1008.1 s
CHTM-L05: E3 legacy candidates 13738 {'hidden': 12681, 'zero_area': 1057}, left out {'invented': 23, 'side': 2537, 'seen_through_shell': 0, 'probe': 1137}; 10041 candidate faces in 595 groups (3 split) -> 626 sites; kept 478, rolled back 148 {'covered': 35, 'deleted': 113, 'look': 42}; removed 8067 faces; deleted after rollback 0; disagreements 1676
CHTM-L05: covered after rollback 0; 20599 -> 12557 faces; 2564.88 s; wrote C:\Temp\e3\chtm5
```

**The three units side by side:**

| | sidewalk A | sidewalk B | CHTM 5th |
|---|---|---|---|
| **Candidates** | | | |
| legacy candidates (pass 1: hidden + zero-area) | 2,037 (1,820 + 217) | 2,471 (2,392 + 79) | 13,738 (12,681 + 1,057) |
| taken out: side / invented / probe / through shell | 420 / 0 / 4 / 0 | 476 / 26 / 39 / 0 | 2,537 / 23 / 1,137 / 0 |
| E3 candidate faces | 1,613 | 1,930 | 10,041 |
| groups (split) | 174 (0); largest 311 | 142 (1); largest 726 | 595 (3); largest 2,558 |
| sites | 174 | 147 | 626 |
| **Outcome** | | | |
| sites kept | 93 | 103 | 478 |
| sites rolled back, by reason (a site counts under each of its reasons) | 81: deleted 81, uv 6 | 44: deleted 44, uv 11, look 2 | 148: deleted 113, look 42, covered 35 |
| rolled-back samples by reason | deleted 1,265, uv 6 | deleted 874, look 52, uv 30 | deleted 1,056, covered 140, look 77 |
| ...of the rolled-back sites, charged by their own samples / by the judge's box only | 18 (690 faces) / 63 (652 faces) | 25 (961) / 19 (180) | 14 (507) / 134 (1,467) |
| faces removed | 271 | 789 | 8,067 |
| **The Validator after rollback** | | | |
| Validator deleted after rollback (last check, kept sites) | **0** (confirm run PASS) | **0** | **0** |
| full Validator, original BEFORE vs final: deleted / covered | 0 / 0, checks 1 and 3 PASS | 0 / 0, PASS | 0 / 0, PASS |
| **find_errors hidden count** | | | |
| BEFORE | 1,853 | 2,411 | 12,870 |
| after E8a | 1,854 | 2,422 | 12,893 |
| after E8a+E3 | 1,633 | 1,683 | **5,607** |
| **Disagreements and time** | | | |
| disagreements (exposure hidden, a probe sees it) | 13 (9 removed by legacy) | 42 (39) | 1,676 (1,552) |
| time, whole run | 173 s | 382 s | 2,565 s |
| ...E3 plan (legacy hidden / sides / probes) | 61 s (22 / 35 / 4) | 77 s (23 / 40 / 15) | 257 s (47 / 54 / 156) |
| ...E3 check runs (first / confirm) | 24 / 13 s | 68 / 32 s | 532 / 475 s |

On CHTM 5th, 1,552 of the 1,676 disagreeing faces are faces the legacy hidden stage removes. That is the source of its roughly 22,000 deleted samples: room surfaces only the probes see.

Times were measured while the full suite and other runs shared the machine. The E8a-only CHTM run took 1,141 s here, against 858 s in the E8a report.

**find_errors, every count (owner's FixProfile):**
```
swA BEFORE: faces 4692; hidden 1853; {'flicker_diff': 0, 'flicker_same': 530, 'reversed': 809, 'hidden': 1853, 'loose': 221, 'open_edges': 250, 'cracks': 550}
swA after E8a: faces 4696; hidden 1854; {'flicker_diff': 0, 'flicker_same': 530, 'reversed': 809, 'hidden': 1854, 'loose': 221, 'open_edges': 256, 'cracks': 552}
swA after E8a+E3: faces 4425; hidden 1633; {'flicker_diff': 0, 'flicker_same': 497, 'reversed': 809, 'hidden': 1633, 'loose': 171, 'open_edges': 371, 'cracks': 545}
swB BEFORE: faces 7227; hidden 2411; {'flicker_diff': 321, 'flicker_same': 1026, 'reversed': 838, 'hidden': 2411, 'loose': 79, 'open_edges': 326, 'cracks': 559}
swB after E8a: faces 7241; hidden 2422; {'flicker_diff': 321, 'flicker_same': 1021, 'reversed': 838, 'hidden': 2422, 'loose': 79, 'open_edges': 353, 'cracks': 578}
swB after E8a+E3: faces 6452; hidden 1683; {'flicker_diff': 260, 'flicker_same': 709, 'reversed': 839, 'hidden': 1683, 'loose': 27, 'open_edges': 545, 'cracks': 537}
chtm5 BEFORE: faces 20599; hidden 12870; {'flicker_diff': 5668, 'flicker_same': 4793, 'reversed': 29, 'hidden': 12870, 'loose': 1055, 'open_edges': 346, 'cracks': 3884}
chtm5 after E8a: faces 20624; hidden 12893; {'flicker_diff': 5668, 'flicker_same': 4789, 'reversed': 29, 'hidden': 12893, 'loose': 1057, 'open_edges': 373, 'cracks': 3898}
chtm5 after E8a+E3: faces 12557; hidden 5607; {'flicker_diff': 3418, 'flicker_same': 2017, 'reversed': 35, 'hidden': 5607, 'loose': 263, 'open_edges': 1710, 'cracks': 3250}
```

**Independent full Validator** (`engine.cli validate --before <BEFORE> --after <final .fixed.obj>`, owner settings):
```
validate CHTM_SIDE_WALK_2nd_floor: verdict FAIL
  textures        PASS        41636 samples seen in BEFORE, 0 failed {'covered': 0, 'overlaid': 0, 'deleted': 0, 'look': 0, 'uv': 0, 'side': 0}
  problems        FAIL        targets signed; before -> after: flicker_diff 0->0, flicker_same 530->497, reversed 809->809, hidden 1853->1633, loose 221->171, open_edges 250->371, cracks 550->545
  nothing_deleted PASS        0 deleted, 0 replaced, 0 covered, 0 overlaid (0 samples only the 1024 extra directions saw)
validate CHTM_2nd_to_3rd_building_sidewalk_outside: verdict FAIL
  textures        PASS        91154 samples seen in BEFORE, 0 failed {...all 0}
  problems        FAIL        targets signed; before -> after: flicker_diff 321->260, flicker_same 1026->709, reversed 838->839, hidden 2411->1683, loose 79->27, open_edges 326->545, cracks 559->537
  nothing_deleted PASS        0 deleted, 0 replaced, 0 covered, 0 overlaid (0 samples only the 1024 extra directions saw)
validate CHTM-L05: verdict FAIL
  textures        PASS        275918 samples seen in BEFORE, 0 failed {...all 0}
  problems        FAIL        targets signed; before -> after: flicker_diff 5668->3418, flicker_same 4793->2017, reversed 29->35, hidden 12870->5607, loose 1055->263, open_edges 346->1710, cracks 3884->3250
  nothing_deleted PASS        0 deleted, 0 replaced, 0 covered, 0 overlaid (0 samples only the 1024 extra directions saw)
  time 484.05 s
```

## E3-R2: how the Validator's `deleted` check judges a sample

**Source:** `engine/validate/checks.py`, `validate().run`, lines 1243-1276, with `_witnesses` at 382-400 and `_Judge.present` at 544-563.

How the check works:
- Each sample that some viewpoint sees in BEFORE is judged from **one witness**: the best-conditioned viewpoint, the one least edge-on to the face, chosen among those that see its front whenever any does.
- `present` casts along that single line, from just in front of the sample. It asks whether AFTER has a face of the same look and UV within the depth tolerance, showing its front if BEFORE's front was seen.
- `deleted` means: tested, not covered, and `present == DELETED`.
- Only `covered` is replayed a second time, from the best probe. `deleted` is not.
- The 1,024 extra directions are cast only for samples of suspect faces that no standard viewpoint saw.

**Can removal hide behind the one-witness gap (P2-E8a concern 3)?** No.
- A removed face is gone along every line. What `present` finds is at the sample's own point, so it does not depend on the line.
- Only three things depend on the line: the depth window, the front/back test and the in-triangle test.
- The only removal that passes from one line and fails from another leaves a same-look copy behind:
  - a copy wound the same way is no change at all;
  - a copy wound the other way fails check 1 as `side` from the front-seeing witness.
- So the witness choice cannot hide a deletion.

**Measured:** a sealed tray whose floor F is seen only through a slot in its lid; BEFORE is the tray, AFTER the tray without F. The Validator reports F's samples deleted at every slot width:

| slot | floor samples reported deleted | ...seen only by the extra directions | legacy exposure of F |
|---|---|---|---|
| 6 in | 445 | 130 | above 0 |
| 2 in | 384 | 180 | above 0 |
| 1 in | 336 | 218 | above 0 |
| 0.5 in | 241 | 199 | above 0 |
| 0.2 in | 134 | 119 | above 0 |
| 0.1 in | 103 | 88 | **0.0** |
| 0.05 in | 87 | 87 | **0.0** |

At 0.1 and 0.05 in the 128-direction exposure reads exactly 0, and the Validator still catches the deletion, though the legacy guard restores F there anyway. Script and output: `C:/Temp/e3/r2_gap.py`, `r2_gap.txt`, `r2_gap_narrow.txt`.

**The gap I did find is SAMPLING, not the witness line.** See concern 1.

## Visual pass

The crops are `C:/Temp/e3/<unit>/visual/site-NNNNN.png`. For each site:
- **Views:** from the nearest eye-height probe (perspective, 90°), and from outside (perspective, 40°, 30° up, at 1,150-2,250 in).
- **Panels:** BEFORE (E3's stage input) | AFTER | X-RAY (BEFORE with the group's own faces drawn through everything in red).
- **Measurements on each crop:** the differing pixels, and the exact count of pixels whose BEFORE first hit is a removed face.

I looked at 8 of the 12 kept groups I rendered:

- **sidewalk A, site 118** (23 faces). From the probe: identical. The X-ray shows a vertical plate inside the slab under the top.
  - From outside: 2 pixels differ. I measured them: 3 rays whose first hit changed are depth ties (dt = 0.0000 in) between two kept faces of the same material, `ltstone_-7`. No removed face is involved: the caster's tie order changes when it is rebuilt.
- **sidewalk A, site 146** (16 faces). Identical from both views. Two small upright pieces inside the slab's edge, behind its grey top and side.
- **sidewalk B, site 4** (161 faces of a 726-face group that was split). Identical. The group lies right behind the gold kerb band seen from the probe.
- **sidewalk B, site 21** (21 faces, 6,330 sq in). Identical. A large plate inside the slab, under its top: one big red quad in the X-ray.
- **CHTM 5th, site 62** (500 faces, the largest kept). From the probe inside a room with a window: identical.
  - The X-ray shows the group is the hidden layer inside the room's walls, around the window.
  - From outside: identical, with the group inside a corner of the building.
- **CHTM 5th, site 122** (298 faces of the 2,558-face group). Identical. The probe already sees a surface from its back (purple in both halves); the group lies behind it.
- **CHTM 5th, site 121** (77 faces). Identical from both views.
- **CHTM 5th, site 231** (191 faces). From the probe, 12,143 pixels differ.
  - Measured: **all 12,143 are same-depth ties between back-to-back coincident faces** (normals cos -1.000, the same `concrete_white`), for example 3,004 px going from face 11984 to face 11983. They are existing flicker pairs.
  - The speckle is in both halves; only its pattern differs. No pixel's depth changed, and 0 pixels hit a removed face.
  - From outside: identical.

In all 12 crops, 0 pixels have a removed face as their BEFORE first hit, from either view.

Not done: `repair-unit` writes no `.skp`, so `render_skp.py` and `skp_edge_audit.py` were not run. That matches the E8a job.

## Rules touched (AGENTS.md §3-6)

- **§3, guards are never loosened.** Nothing in `engine/guard/**` or `engine/validate/**` changed, and no FixProfile changed. The legacy guard runs unchanged inside E3.
- **§3, only solidify invents vertices.** E3 only removes: no new faces, no new points. Its `Edit`s carry neither.
- **§3, never touch the protected places.**
  - Inputs were the frozen snapshots under `data/`, read only.
  - Outputs went only to `C:/Temp/e3`.
  - Nothing was written to the export folder, the owner's folders or any `.skp`.
  - I ran only pytest, the CLI and scratch scripts; all ended on their own, and nothing was killed.
- **§4, blocked operations.** None used. Opposite-normal coincident pairs are not treated as duplicates. The work is per unit.
- **§5 and §6, the strict rule.**
  - Enforced by the Validator's site checks: deleted after rollback is 0 on all three units, and so is the full Validator.
  - But see concern 1: about 12, 16 and 70 sq in of removed surface is visible at a sampling denser than the Validator's.

## Concerns, said plainly

1. **The Validator's sampling misses some visible deletions, and E3 ships them.** This is the gap ruling E3-R2 asked for.
   - **The measured example** is CHTM 5th, face 8480 of E3's stage input: `concrete_white`, 290.87 sq in, kept site 62.
     - The Validator gives it 9 samples. No viewpoint sees any of them, the 1,024 extra directions included.
     - Yet 190 of 1,770 points of a dense lattice on it see out.
     - An orthographic crop 4 in wide along direction (0.889, 0.455, -0.048), at 0.02 in per pixel, shows face 8480 on 12,064 px in BEFORE, about 4.8 sq in of that window. In AFTER those pixels show faces 8487 and 14397 instead.
     - Measured separately, the newly "reversed" face 8487 meets 8480 20.28 in out, so the surface seen moves back about 20 in.
     - Image: `C:/Temp/e3/gap_face_8480.png`.
   - **How it was found:** `find_errors` `reversed` rose from 29 to 35. All 6 newly reversed faces are explained by removed faces 6474, 5933 and 8480.
   - **Over every removed face** (36 lattice points per face; the Validator's 128 + 1,024 directions, its ring and its probes):

     | unit | removed faces with a visible point | in sites | estimated visible area |
     |---|---|---|---|
     | sidewalk A | 7 | 6 | 12.4 sq in |
     | sidewalk B | 4 | 4 | 15.7 sq in |
     | CHTM 5th | 10 | 8 | 70.1 sq in |

   - On CHTM, 23 of those points are seen by **eye-height probes**. So my R4 pre-filter, which samples at the Validator's density, does not fully meet "any face a probe sees is not a candidate".
   - **I did not fix it here**, for two reasons:
     - the brief frames R4 as the cheap pre-filter, with the judge as the safety net, and asks for gaps to be reported;
     - a synthetic test fixture for it is not reliable: at these sizes the Validator's own samples see through a slot at grazing angles, and the legacy guard restores the face anyway.
   - **Proposed fix (needs a ruling):** a denser pre-filter in E3, through the site judge: about 36 points per face, or 1 per 9 sq in, against every Validator viewpoint.
     - Measured cost of that check: 388 s on CHTM for its 8,067 removed faces; perhaps 10-12 min for all its candidates.
     - It would have kept those 21 faces. The residual should then be measured again with a different, denser lattice.
     - The other route is the Validator's own sample density, which is `engine/validate` and the owner's.
   - Scripts: `C:/Temp/e3/gap_all.py`, `gap_measure.py`, `reversed_dbg.py`; output in `gap_all.txt`.
2. **The judge's 24 in box rolls back innocent groups.**
   - Measured: every failing sample of the E3 stage lies on a face its own site removed. The `touched` charges sum to the first run's failing count: 228 of 228 on sidewalk A, 441 of 441 on sidewalk B.
   - On CHTM it is 60 of 64; the other 4 are item 3.
   - For a remove-only site, a `box` charge is therefore always an over-charge. It rolled back 63 innocent groups (652 faces) on A, 19 (180) on B and 134 (1,467) on CHTM.
   - A follow-up could charge remove-only sites by `touched` alone (`SiteJudge.attribute`); that needs a ruling. I did not change it.
3. **A ray-caster corner artefact on CHTM.**
   - Kept faces 17149 and 17153 got 4 `covered` samples from a probe 850 in away.
   - In BEFORE the line to the probe misses everything. In AFTER, a subset of BEFORE's faces, the same line hits face 10553: head-on (ray·normal 0.9987), 1.4 to 13.9 in away.
   - Every sample sits at x = 1531.29, z = 2298.72, exactly 10553's corner, so the line passes through that corner. Each mesh's caster gives the same answer on every rebuild, but the two meshes' casters disagree.
   - Cost: 21 sites (340 faces) were rolled back for these 4 samples alone, and 12 more partly.
   - This lies in `engine/validate` (float32 Embree), so I only report it. Script: `C:/Temp/e3/covered_dbg.py`.
4. **Check 2 gets worse on `open_edges`:** 256 to 371 on A, 353 to 545 on B, 373 to 1,710 on CHTM.
   - Removing a hidden group leaves its kept neighbours' edges unshared. `hidden`, `loose`, `flicker` and `cracks` all improve.
   - The site judge checks only checks 1 and 3, so the kernel cannot see this. Whether `open_edges` should count inner edges no one sees is a targets question for the owner.
5. **Zero-area faces are labelled E3.**
   - The legacy observer labels them E1. The brief asks for the exact legacy candidate set, with E3 labels and the rule per face.
   - Evidence `rules` says `zero_area`. E3 kept 50, 52 and 798 of them on A, B and CHTM. A future E1 engine would overlap here.
6. **One existing test edited.**
   - `test_cli_repair_unit.py::test_an_engine_that_is_not_e8_is_refused` used `--engines E3` as its example of a refused engine. Ruling E3-R6 makes E3 valid, so the test failed: it got exit 2 for the missing campus map, without "E3" in the message.
   - I changed `E3` to `E5`, an engine `repair-unit` still refuses. Nothing else changed.
7. **Files outside `e3_hidden.py`.** Each is additive and read-only:
   - `solidify.py`: the `side_faces` record (output unchanged, measured above);
   - `e8_solidify.py`: the `seen_through` record;
   - `site_judge.py`: `probe_seen`.

   The probe pre-filter shares the Validator's visibility code. That is by design (the same probes), but it is not an independent check.
8. **Smaller points.**
   - `seen_through_shell` excluded 0 faces on all three units.
   - The `disagreements` list names at most 1,000 faces; all are counted.
   - E3 site ids start at 0, like E8's. `needs_modelling`'s cross-check gathers rolled-back sites from every stage, so it is slightly more lenient with both stages present.
   - `_print_checks` prints every rolled-back site id, which is a long line for E3.
   - Time: CHTM 5th took 2,565 s on a shared machine; E3's plan is about 257 s of that and its two check runs about 1,008 s.

## Fix round 1 (rulings E3-R7, E3-R8, E3-R9)

**Status: DONE_WITH_CONCERNS.**
- The three rulings are built, each test-first with its own commit. The suites pass, and the Validator's deleted count after rollback is 0 on all three units.
- **Not met as stated:** "the 36-point dense check must find 0".
  - With the pre-filter's own lattice it finds 0 on both sidewalks, and 1 pinhole on CHTM 5th that the OBJ write's rounding produces.
  - With my original, independent 36-point lattice it still flags 14, 11 and 18 removed faces. Some of these are patches of 1-1.6 sq in.
  - Denser lattices find more. This needs a ruling (end of section).

### Items

**Item 1, E3-R7: the dense pre-filter.** Commit 3ac532d.
- `DENSE_POINTS_PER_FACE = 36` (e3_hidden.py). `SiteJudge.lattice_seen(mesh, faces, points_per_face)` places the points.
  - The lattice is the Validator's own equal-area 6 x 6 one (`face_samples` with no area term): 36 cells of equal area per face, whatever its size.
  - It is tested against every Validator viewpoint, from either side: the 128 and the 1,024 extra outside directions, the 24 ring cameras and the eye-height probes.
- Every face still a candidate after the earlier rules is tested; one with any point seen is excluded.
  - `report.json` `e3.dense_excluded` lists each, with points seen, outside or probes, area and centroid.
  - `e3.excluded.dense` counts them; `dense_lattice` and `dense_tested` are recorded too.
- **Test:** `test_a_face_seen_only_between_the_validators_samples_is_never_a_candidate`, with the synthetic fixture `_face_seen_down_a_shaft`, modelled on face 8480.
  - F is a 142.8 sq in triangle in a sealed box, 0.05 in below a 2 in lid, with a 1.3 in shaft over its corner, away from every Validator sample and exposure sample. A box 3,000 in away keeps the legacy guard from resolving the shaft.
  - The test asserts its preconditions first:
    - no Validator viewpoint (extra directions included) sees any of F's 4 samples;
    - a lattice point of F is seen;
    - the legacy pass 1 removes F;
    - with blind views, E3 plans F.
  - Then: with the judge, F is not planned, `dense_excluded == [F]`, and the kernel run keeps F.
  - Red: `AttributeError: 'SiteJudge' object has no attribute 'lattice_seen'`; the other tests failed with `TypeError ... unexpected keyword argument 'dense_view'` (9 failed, 4 passed). Green: 13 passed.
  - No real-geometry crop was needed.
- I also changed some of my own tests from this job (none on the base): those that run without a site judge now pass `dense_view=_blind`.
  - The strict-rule test's views now miss the plate in both pre-filters, so the judge still has something to catch.

**Item 2, E3-R8: remove-only sites, `site_judge.py`.** Commit f7df688.
- In `SiteJudge.attribute`, a site with no new faces (every edit a `remove`) is no longer charged a `deleted` sample through its grown box. It is charged only for samples on faces it touched.
- The Validator reports reasons per cluster of failing samples, not per sample. So a sample counts as `deleted` only when every reason of its cluster is `deleted`.
- Mixed clusters, and every other kind, keep today's attribution, so the corner artefact still rolls back conservatively.
- **Tests,** in the new `engine/tests/test_site_judge_remove_only.py`:
  - two remove-only sites 2 in apart, with the owner's 24 in margin: only the one that deleted a seen sample is rolled back. Red: `assert {0, 1} == {0}`. Green.
  - a `look` failure (another-look twin left behind) still charges the neighbour through the box. This passed before and after the change; it guards against going too far.

**Item 3, E3-R9: zero-area faces are not E3 candidates.** Commit 8ff6a8a.
- Zero-area faces are excluded first and counted in `e3.excluded.zero_area`.
- **Test:** `test_a_zero_area_face_is_never_an_e3_candidate`: a collinear triangle inside a sealed cube. Red: `assert [12, 13, 14] == [12, 13]`. Green.

**Item 4.** Concern 6 is accepted: `test_cli_repair_unit.py::test_an_engine_that_is_not_e8_is_refused` uses E5 instead of E3, the only edit to a test that was on the base.

**Item 5.** Nothing done about the corner artefact, which gets its own job; `open_edges` is recorded for E6/E7.

### Suites (from the worktree root, PYTHONPATH set)
```
engine/tests: 1850 passed, 1 xfailed in 957.95s (0:15:57)
tools/tests:  180 passed in 16.39s
```

### Golden runs, `--engines E8a,E3`

Outputs are in `C:/Temp/e3/r1/<unit>`. E8a is unchanged, so `C:/Temp/e3/<unit>_e8a` is still E3's stage input; the scripts check this by K1 key on every removed face.

```
CHTM_SIDE_WALK_2nd_floor: check E3 (E3, 155 edits, 155 sites): FAIL -> PASS; failing 3 {'deleted': 3}; unknown 0; rolled back [29, 56, 79]; 2 run(s), 37.8 s
CHTM_SIDE_WALK_2nd_floor: E3 legacy candidates 2037 {'hidden': 1820, 'zero_area': 217}, left out {'zero_area': 217, 'invented': 0, 'side': 420, 'seen_through_shell': 0, 'probe': 4, 'dense': 130}; 1266 candidate faces in 155 groups (0 split) -> 155 sites; kept 152, rolled back 3 {'deleted': 3}; removed 1058 faces; deleted after rollback 0; disagreements 13
CHTM_2nd_to_3rd_building_sidewalk_outside: check E3 (E3, 130 edits, 130 sites): FAIL -> PASS; failing 4 {'deleted': 3, 'uv': 1}; unknown 0; rolled back [27, 41]; 2 run(s), 107.8 s
CHTM_2nd_to_3rd_building_sidewalk_outside: E3 legacy candidates 2471 {'hidden': 2392, 'zero_area': 79}, left out {'zero_area': 79, 'invented': 26, 'side': 476, 'seen_through_shell': 0, 'probe': 39, 'dense': 136}; 1715 candidate faces in 125 groups (1 split) -> 130 sites; kept 128, rolled back 2 {'deleted': 2, 'uv': 1}; removed 1610 faces; deleted after rollback 0; disagreements 42
CHTM-L05: check E3 (E3, 524 edits, 524 sites): FAIL -> PASS; failing 5 {'covered': 4, 'deleted': 1}; unknown 0; rolled back [...]; 2 run(s), 879.1 s
CHTM-L05: E3 legacy candidates 13738 {'hidden': 12681, 'zero_area': 1057}, left out {'zero_area': 1057, 'invented': 21, 'side': 2537, 'seen_through_shell': 0, 'probe': 1137, 'dense': 60}; 8926 candidate faces in 502 groups (2 split) -> 524 sites; kept 488, rolled back 36 {'covered': 35, 'deleted': 1}; removed 8470 faces; deleted after rollback 0; disagreements 1676
```

| | sidewalk A | sidewalk B | CHTM 5th |
|---|---|---|---|
| **Candidates** | | | |
| legacy candidates (hidden + zero-area) | 2,037 (1,820 + 217) | 2,471 (2,392 + 79) | 13,738 (12,681 + 1,057) |
| left out: zero-area / invented / side / through shell / probe / **dense** | 217 / 0 / 420 / 0 / 4 / **130** | 79 / 26 / 476 / 0 / 39 / **136** | 1,057 / 21 / 2,537 / 0 / 1,137 / **60** |
| **dense_excluded** (area; points seen from outside / by probes) | 130 faces (17,544.6 sq in; 129 / 1) | 136 faces (28,940.8 sq in; 135 / 10) | 60 faces (14,802.3 sq in; 50 / 22) |
| candidate faces | 1,266 | 1,715 | 8,926 |
| groups (split) | 155 (0) | 125 (1) | 502 (2) |
| sites | 155 | 130 | 524 |
| **Outcome** | | | |
| sites kept | 152 | 128 | 488 |
| sites rolled back, by reason | 3: deleted 3 | 2: deleted 2, uv 1 | 36: covered 35, deleted 1 |
| ...charged by their own samples / by the judge's box only | 3 (208 faces) / **0** | 2 (105) / **0** | 1 (1) / 35 (455): the corner-artefact `covered` samples, kept conservative by ruling |
| faces removed | 1,058 (was 271) | 1,610 (was 789) | 8,470 (was 8,067) |
| **The Validator after rollback** | | | |
| Validator deleted after rollback | **0** | **0** | **0** |
| full Validator, original BEFORE vs final: deleted / covered | 0 / 0, checks 1 and 3 PASS | 0 / 0, PASS | 0 / 0, PASS |
| **find_errors hidden count** | | | |
| BEFORE | 1,853 | 2,411 | 12,870 |
| after E8a | 1,854 | 2,422 | 12,893 |
| after E8a+E3 | **792** | **810** | **4,423** |
| **Disagreements and time** | | | |
| disagreements | 13 | 42 | 1,676 |
| time, whole run | 183 s | 424 s | 2,836 s |
| ...E3 plan (legacy / sides / probes / dense) | 83 s (18 / 28 / 4 / 34) | 138 s (21 / 35 / 13 / 69) | 635 s (46 / 53 / 146 / **390**) |
| ...E3 check runs (first / confirm) | 19 / 19 s | 55 / 52 s | 440 / 439 s |

Other find_errors counts after E8a+E3:

| | sidewalk A | sidewalk B | CHTM 5th |
|---|---|---|---|
| open_edges | 256 → 617 | 353 → 734 | 373 → 2,076 |
| cracks | 552 → 507 | 578 → 480 | 3,898 → 3,143 |
| flicker_same | 530 → 293 | 1,021 → 359 | 4,789 → 1,499 |
| flicker_diff | — | 321 → 107 | 5,668 → 2,751 |
| loose | 221 → 222 | — | 1,057 → 1,061 |
| reversed | 809 → 810 | 838 → 839 | 29 → 29 |

### The dense check rerun on the removed faces

Scripts: `C:/Temp/e3/gap_all.py`, `C:/Temp/e3/r1/crop_all.py`; output `C:/Temp/e3/r1/chtm.txt` and the console lines below.

**1. The pre-filter's own lattice** (6 x 6 equal-area), on the stage input read back from the E8a-only `.fixed.obj`:
```
swA [validator lattice, k=6]: faces with a visible lattice point: 0 (0.0 sq in of face) ...
swB [validator lattice, k=6]: faces with a visible lattice point: 0 ...
chtm5 [validator lattice, k=6]: faces with a visible lattice point: 1 (97.0 sq in of face) ...; points seen by directions 0, cameras 0, probes 1
  face 2681 (site 65, minecraft_prismarine_dark_-1): area 97.02, 1/36 points seen
```
- On the re-read mesh, the engine's own `lattice_seen` also sees that one probe point: `{'outside': [0], 'probes': [1], 'any': [1]}`. During the run, on the in-memory stage input, it saw none.
- So the difference comes from writing the E8a output as an OBJ (3 decimals) and reading it back. The rounding moves invented points and probe positions slightly.
- How visible it is: a view from that probe (705 in away), 12.3 in wide at 0.03 in/px, shows face 2681 at **0 px**. A pinhole line.

**2. My original independent 36-point lattice** (centroids of the 36 upward cells of an 8-subdivision, a different point set):

| unit | faces flagged | in sites |
|---|---|---|
| sidewalk A | 14 | 7 |
| sidewalk B | 11 | 8 |
| CHTM 5th | 18 | 10 |

Each flagged face, cropped along its best seeing direction (4 in window, 0.02 in/px):
- **CHTM 5th:** every crop shows 0-22 px (at most about 0.009 sq in). Pinholes.
- **Sidewalk A:**
  - face 3139: 723 px (0.29 sq in);
  - face 4557: 479 px;
  - the crops around faces 3409, 3410, 3720 and 3721, looking almost straight up from below: 3,599-3,905 px of removed faces, **about 1.4-1.6 sq in**;
  - the rest: 0-47 px.
- **Sidewalk B:**
  - face 455: 3,426 px (**1.37 sq in**);
  - face 2156: 2,488 px;
  - face 2179: 2,522 px (4,587 px of removed faces in that crop);
  - face 2184: 2,575 px (3,098);
  - face 1533: 487 px;
  - the rest: 0-3 px.

**3. Denser lattices find more.** It does not converge, so a fixed point lattice cannot guarantee 0:

| lattice | unit | removed faces with a seen point | estimated visible |
|---|---|---|---|
| area-based, at least 36 points and 1 per 4 sq in | sidewalk B | 6 | 55.8 sq in |
| area-based, at least 36 points and 1 per sq in | sidewalk B | 16 | 106 sq in |
| independent, 78 points per face | sidewalk A | 29 | 121 sq in |
| independent, 136 points per face | sidewalk A | 46 | 135 sq in |

- At 136 points per face, 304 of the 364 seen points lie within 0.25 in of their face's edge, where 36% of all points lie: mostly rays through hairline seam cracks.
- At 36 points per face the seen points are spread over the faces: real openings missed between points.

### Decision needed (ruling E3-R7 follow-up)

The pre-filter as ruled (36 points per face) makes the dense check pass only on its own lattice. A 36-point lattice is coarse on big faces (sidewalk B's 455 is 581 sq in). Options:

1. **Area-based density:** at least 36 points per face, plus 1 per N sq in. On sidewalk B, N = 1 still flags 16 faces that the coarser check does not. CHTM 5th at N = 1 would test about 2.3 M points, which by the 390 s / 305 k-point rate measured here is about 50 min more.
2. **A stated visibility floor** for the acceptance. For example, "no removed face shows more than X px at 0.02 in/px from any Validator viewpoint", measured by crops like these.
3. **A non-sampling test** of whether a face can be seen: an exact or conservative visibility method, a research job. The deferred winding-number check is unreliable here, because the model has thousands of cracks.

### Rules touched in fix round 1

- `engine/site_judge.py` only, for the attribution and `lattice_seen`.
- Nothing in `engine/guard/**` or `engine/validate/**`, and no FixProfile change.
- Removal only. Outputs only under `C:/Temp/e3/r1`. I started only pytest, the CLI and scratch scripts; all ended on their own, and nothing was killed.
