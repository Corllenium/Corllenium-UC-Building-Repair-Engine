# Task P2-E8a report: strict solidify as the repair engine E8

Worktree `D:/PROJECTS/UC MODEL FIXER/.claude/worktrees/P2-E8a`, branch `claude/P2-E8a`, base b43d27f. Not merged, not pushed.

## Commits

| commit | what |
|---|---|
| c4ccf65 | test(p2-e8a): the failing tests (ruling (c): written first, seen red, committed) |
| ce6a8ff | feat(p2-e8a): `E8Solidify`; `SolidifyResult` gains a read-only piece record (items 1 and 2) |
| 679828d | fix(unit_before): a face with no material keeps the look `material:<none>` (item 4) |
| 602a8d9 | feat(p2-e8a): `engine.cli repair-unit` (item 3) |

Files: `engine/repair/engines/e8_solidify.py` (new), `engine/fixes/solidify.py` (read-only record only), `engine/campus/unit_before.py`, `engine/cli.py`; tests `engine/tests/test_e8_solidify.py`, `engine/tests/test_unit_before_no_material.py`, `engine/tests/test_cli_repair_unit.py` (all new). No existing test edited. Nothing in `engine/guard/**` or `engine/validate/**`, no `FixProfile` change, `cover_max_exposure` untouched (ruling (a)).

## Items

### Item 1: `E8Solidify` (engine/repair/engines/e8_solidify.py)

- **What it does.** `E8Solidify(flatness={})`, with `name="E8"` and `legacy=False`.
  - `plan()` runs `engine.fixes.solidify.solidify` unchanged, on the topology `start_fix` gives it (the pipeline's own recipe).
  - It returns one site per piece. A piece is a solidify closing group: one wall under an outline edge, or one region's bottom.
- **The read-only grouping.** `SolidifyResult` had no piece record, so three fields were added. They are filled where solidify already registers each group, and nothing it builds changes.
  - `face_group`: the group of each shipped invented face, -1 for the input's faces.
  - `replaced_group`: for each replaced input face, the group that replaced it, -1 for the rest.
  - `pieces`: kind, region, material, length, and per wall the edge ends, the height at each end and the measured height; per bottom, the depth.
- **The edits of a piece.**
  - An `add`, carrying:
    - `new_points` (the invented points its faces use, numbered from the input's point count);
    - `new_face_uv` (solidify's UV values at each corner);
    - `new_face_normal`: solidify writes no `vn`, so every face is the all-NaN K1b placeholder and ends up `vn = -1`, as in solidify's own output;
    - `evidence["material"]`.
  - Or one `cut`, when the piece replaced broken pieces that are all in its own material.
  - When the replaced faces are in another material, the piece becomes an `add` plus a `remove`, both in the same site, because a cut inherits its input faces' material.
- **Reason and evidence.** Each edit has a `reason` (for example "E8 solidify: a wall under an outline edge of top region 12 (39.37 in long, 8.00 in deep), replacing 7 broken piece(s)"). Its `evidence` holds: `piece`, `group`, `region`, `material`, `length`, `thickness`, `replaced`, `faces`, `edge` and `measured` (walls only), and `solidify` (the region's rows of the solidify report: thickness, bottom depth, representative side depth).
- **Ruling (b), face order.**
  - `apply_edits(input, E8 edits)` equals solidify's output as a multiset of (face key, corner UVs), with the same face count and the same sorted materials. That is what the tests assert.
  - On both real sidewalks it is even equal row by row: same corner positions in the same face order.
  - The vertex numbering and the point count differ. Every edit counts its points from the input's count, so a point two pieces share is written once per piece. And E8 carries only the points its kept faces use, while solidify's mesh keeps the points of refused faces too: sidewalk A has 1,718 points against 1,839, sidewalk B 3,082 against 3,114.
  - The duplicates do not change any count: `find_errors` on sidewalk B's output, as written and with points merged, gives open_edges 353 / 353, cracks 578 / 578, hidden 2,422 / 2,422.

Tests (engine/tests/test_e8_solidify.py):

| test | covers |
|---|---|
| `test_e8_is_a_non_legacy_engine_named_e8` | name and `legacy` |
| `test_plan_gives_non_legacy_e8_edits_one_site_per_piece[12 fixtures]` | every edit is E8 and non-legacy; one distinct site per piece; one add or cut per site; UV and normal carried; evidence keys; each site names exactly the faces it replaced |
| `test_apply_edits_reproduces_solidifys_own_output[12 fixtures]` | apply_edits reproduces solidify (multiset of keys and UVs, face count, materials) |
| `test_a_broken_side_is_replaced_by_a_cut` | `slab_with_sawtooth_side` gives cuts of exactly `replaced` |
| `test_adds_carry_the_points_solidify_invented` | `slab_with_two_depths` |
| `test_plan_leaves_the_unit_mesh_alone` | the unit's mesh is not modified |
| `test_a_piece_replacing_faces_of_another_material_is_an_add_and_a_remove_of_one_site` | the add-plus-remove branch |

The 12 fixtures: slab_with_three_skirts, compartment_with_deep_wall, slab_with_sawtooth_side, open_box_with_cells, slab_with_half_side, slab_with_partial_underside, slab_with_two_depths, slab_continuing_under_a_landing, sloped_slab, slab_with_a_bottom_strip, slab_beside_a_lower_top, two_level_slab.

Said plainly: `test_a_piece_replacing_faces_of_another_material_is_an_add_and_a_remove_of_one_site` was written AFTER the code. No fixture in `build.py` reaches that branch: the sawtooth and deep-tooth walls take their teeth's material, so they come out as cuts. I wrote the test once I saw that, and it passed on first run. Every other test was red first.

### Item 2: the kernel runs E8 with `validate_sites=True`

No kernel change was needed: `repair_unit(..., engines=[E8Solidify()], validate_sites=True)` with the site judge in `ctx.validator`.

- **`test_the_probe_scene_deep_wall_is_seen_only_from_eye_height`** checks the new fixture `_probe_scene`.
  - The fixture: `compartment_with_deep_wall`, 40 in wide, lifted so its open end spans z 55..65 at eye height, inside a court of 400 in walls with a closed floor box. Far off sits a `slab_with_three_skirts`.
  - The deep wall's 18 samples are seen by 0 outside directions, 0 ring cameras, and all 18 by eye-height probes.
- **`test_a_piece_covering_what_only_a_probe_sees_is_rolled_back_and_the_others_are_kept`** runs E8 on that scene with the site judge.
  - Verdict FIRST FAIL, then FINAL PASS after a confirm run, with no stage rollback.
  - Exactly one site is rolled back, with reasons `{"covered": n}` only. It is the wall at x = 0, z 55..65, and legacy solidify's cap guard KEPT it (`cap_guard_passed`).
  - The far slab's wall and bottom are kept, and the shipped mesh equals `apply_edits(before, kept)`.
  - `edit_log.jsonl` marks only that site's lines `rolled_back`, and its check line names the reason `covered`.
- **`test_pieces_that_cover_nothing_visible_are_all_kept_and_the_stage_passes`** runs `slab_with_three_skirts` and `slab_with_half_side`: first PASS, final PASS, nothing rolled back, and everything solidify built ships.

### Item 3: `engine.cli repair-unit`

`repair-unit (--unit <UNIT> | --snapshot <dir>) --engines E8 --out <dir> [--map] [--source] [--materials]`. The `--snapshot` form is for the sidewalks, which are snapshots rather than campus units.

- **What it does.**
  - Builds the BEFORE with `build_unit_before` (what `campus-unit-before` runs) into `<out>/before/`.
  - Runs `repair_unit` with E8 only, `validate_sites=True`, and `SiteJudge(load_looks(materials, [(BEFORE mtl, BEFORE dir)]))`, as `fix --kernel --validate-sites` builds it, with the owner's `FixProfile()`.
  - Writes `<unit>.fixed.obj` (plus `materials.mtl`), `edit_log.jsonl` and `report.json`. It writes no .skp.
- **`report.json` contents.**
  - `sites`: built, kept, rolled_back, rolled_back_by_reason (sites per Validator reason), rolled_back_samples_by_reason, and by_piece.
  - `pieces`: one row per site, with kind, faces, new points, replaced, kept and reasons.
  - `covered_after_rollback` and `after_rollback` (taken from the stage's last check run).
  - `stages` (the check records), the `solidify` report summary, and `seconds`.
- **Guards on the command.** Any engine other than E8 is refused (exit 2). `--out` goes through `refuse_protected` (`_OUTPUT_ARGS`). Exit 0 when the run completes.
- **Tests** (engine/tests/test_cli_repair_unit.py):
  - `test_the_parser_takes_a_unit_or_a_snapshot_and_the_engines`
  - `test_an_engine_that_is_not_e8_is_refused`
  - `test_repair_unit_refuses_a_protected_output`
  - `test_repair_unit_writes_the_fixed_obj_the_edit_log_and_the_report` (slab_with_three_skirts as a campus unit: 2 built, 2 kept)
  - `test_repair_unit_reports_a_rolled_back_piece_by_reason` (compartment_with_deep_wall: 1 built, 1 rolled back `{"covered": 1}`, BEFORE ships, covered after rollback 0)
  - `test_repair_unit_takes_a_snapshot_folder_as_the_before`

### Item 4: `unit_before`, material index -1

- **What was wrong.** Line 111 already skipped negative indexes, but `write_obj` writes no `usemtl` for -1. A later member's face with no material therefore read back from the unit's OBJ as the earlier member's last material.
- **The fix.** Such a face now gets the material `NO_MATERIAL = "<none>"`. Its look is then `material:<none>`, which is what `face_keys` gives index -1, and its name is `<none>`, which is what `material_name` gives. It has no `newmtl` in the merged MTL.
- **Real units.** Per the end-of-P1 review, no snapshot has such a face (0 of 85), so no real unit changes.
- **Test.** `test_a_member_face_with_no_material_keeps_the_look_none_in_the_unit_before` (new file).

## Red, then green (real output)

Red, before any implementation (c4ccf65):

```
$ pytest engine/tests/test_e8_solidify.py engine/tests/test_unit_before_no_material.py engine/tests/test_cli_repair_unit.py -q -p no:cacheprovider
ERROR collecting engine/tests/test_e8_solidify.py
E   ModuleNotFoundError: No module named 'engine.repair.engines.e8_solidify'
1 error in 1.03s

$ pytest engine/tests/test_unit_before_no_material.py engine/tests/test_cli_repair_unit.py -q -p no:cacheprovider
E       AssertionError: not the earlier member's last material
E       assert 'brick' == '<none>'
E               argparse.ArgumentError: argument command: invalid choice: 'repair-unit' (choose from fix, preview-data, errors, campus-freeze, campus-index, campus-materials, campus-skp-check, validate, campus-unit-before, census, campus-inventory, campus-errors-skp, decide-pilot, decide-pull, decide-import-pilot)
E       KeyError: 'repair-unit'
E       AttributeError: module 'engine.cli' has no attribute 'cmd_repair_unit'
FAILED engine/tests/test_unit_before_no_material.py::test_a_member_face_with_no_material_keeps_the_look_none_in_the_unit_before
FAILED engine/tests/test_cli_repair_unit.py::test_the_parser_takes_a_unit_or_a_snapshot_and_the_engines
FAILED engine/tests/test_cli_repair_unit.py::test_an_engine_that_is_not_e8_is_refused
FAILED engine/tests/test_cli_repair_unit.py::test_repair_unit_refuses_a_protected_output
FAILED engine/tests/test_cli_repair_unit.py::test_repair_unit_writes_the_fixed_obj_the_edit_log_and_the_report
FAILED engine/tests/test_cli_repair_unit.py::test_repair_unit_reports_a_rolled_back_piece_by_reason
FAILED engine/tests/test_cli_repair_unit.py::test_repair_unit_takes_a_snapshot_folder_as_the_before
7 failed in 1.34s
```

Green:

```
$ pytest engine/tests/test_e8_solidify.py -q        (after ce6a8ff's code, before the add+remove test)
31 passed in 15.79s
$ pytest engine/tests/test_e8_solidify.py engine/tests/test_solidify.py -q
144 passed, 1 xfailed in 235.67s (0:03:55)
$ pytest engine/tests/test_unit_before_no_material.py engine/tests/test_unit_before.py -q
15 passed in 1.47s
$ pytest engine/tests/test_cli_repair_unit.py -q
6 passed in 1.78s
```

## Acceptance commands (real output)

```
$ ( cd <worktree> && PYTHONPATH="$PWD" "$PY" -m pytest engine/tests -q -p no:cacheprovider )
1754 passed, 1 xfailed in 610.19s (0:10:10)
$ ( cd <worktree> && PYTHONPATH="$PWD" "$PY" -m pytest tools/tests -q -p no:cacheprovider )
123 passed in 13.16s
```

Engine: the base's 1715 plus 39 new tests. The xfail is the pre-existing one.

### E8 only, on the golden units (owner's FixProfile and settings; outputs in C:/Temp/e8a/, no .skp written)

Commands:

```
"$PY" -m engine.cli repair-unit --snapshot ".../data/snapshots/ce26e0392ab0" --engines E8 --out C:/Temp/e8a/swA --materials ".../data/campus/materials.json"
"$PY" -m engine.cli repair-unit --snapshot ".../data/snapshots/0b290ec0bcb4" --engines E8 --out C:/Temp/e8a/swB --materials ".../data/campus/materials.json"
"$PY" -m engine.cli repair-unit --unit CHTM-L05 --engines E8 --out C:/Temp/e8a/chtm5 --map ".../data/campus/campus_map.json" --source ".../data/campus/source.json" --materials ".../data/campus/materials.json"
```

Their summary lines (the rolled-back site id lists are cut short here):

```
CHTM_SIDE_WALK_2nd_floor: check E8 (E8, 66 edits, 66 sites): FAIL -> PASS; failing 3293 {'covered': 2937, 'overlaid': 2, 'uv': 354}; unknown 0; rolled back [2, 3, 4, ... 172]; 2 run(s), 20.3 s
CHTM_SIDE_WALK_2nd_floor: site checks done in 39.3 s (the whole kernel run)
CHTM_SIDE_WALK_2nd_floor: E8 built 66 pieces (59 walls, 7 bottoms); kept 4, rolled back 62 {'covered': 57, 'overlaid': 6, 'uv': 54}; covered after rollback 0; 4692 -> 4696 faces; 39.36 s; wrote C:\Temp\e8a\swA

CHTM_2nd_to_3rd_building_sidewalk_outside: check E8 (E8, 56 edits, 54 sites): FAIL -> PASS; failing 8408 {'covered': 8118, 'uv': 290}; unknown 0; rolled back [0, 2, 3, ... 97]; 2 run(s), 88.1 s
CHTM_2nd_to_3rd_building_sidewalk_outside: site checks done in 112.1 s (the whole kernel run)
CHTM_2nd_to_3rd_building_sidewalk_outside: E8 built 54 pieces (40 walls, 14 bottoms); kept 10, rolled back 44 {'covered': 43, 'uv': 38}; covered after rollback 0; 7227 -> 7241 faces; 112.23 s; wrote C:\Temp\e8a\swB

CHTM-L05: check E8 (E8, 216 edits, 209 sites): FAIL -> PASS; failing 16077 {'covered': 13350, 'overlaid': 41, 'deleted': 12, 'uv': 2674}; unknown 0; rolled back [0, 3, 4, ... 365]; 2 run(s), 799.2 s
CHTM-L05: site checks done in 857.8 s (the whole kernel run)
CHTM-L05: E8 built 209 pieces (97 walls, 112 bottoms); kept 8, rolled back 201 {'covered': 192, 'deleted': 69, 'overlaid': 154, 'uv': 187}; covered after rollback 0; 20599 -> 20624 faces; 858.47 s; wrote C:\Temp\e8a\chtm5
```

| unit | pieces built (walls / bottoms) | kept (walls / bottoms) | rolled back | sites per reason | first run, all pieces = legacy solidify: covered | after rollback: covered | time |
|---|---|---|---|---|---|---|---|
| sidewalk A (ce26e0392ab0) | 66 (59 / 7) | 4 (4 / 0) | 62 | covered 57, uv 54, overlaid 6 | 2,937 (+354 uv, 2 overlaid) | **0** (confirm run on the 4 kept: 0 failing) | 39.4 s |
| sidewalk B (0b290ec0bcb4) | 54 (40 / 14) | 10 (7 / 3) | 44 | covered 43, uv 38 | 8,118 (+290 uv) | **0** (confirm run on the 10 kept: 0 failing) | 112.2 s |
| CHTM 5th (CHTM-L05) | 209 (97 / 112) | 8 (5 / 3) | 201 | covered 192, uv 187, overlaid 154, deleted 69 | **13,350** (+2,674 uv, 41 overlaid, 12 deleted) | **0** (confirm run on the 8 kept: 0 failing) | 858.5 s |

- A site counts under every reason the Validator gave its charged samples.
- No stage was rolled back whole, and no failure was charged to no site (unknown 0) in any run.
- The first run judges every piece the cap guard kept, which is legacy solidify's output. Its covered count on CHTM 5th, 13,350, is the controller's legacy figure exactly.
- Rolled-back samples by reason on CHTM 5th: covered 776,041, uv 77,607, overlaid 2,143, deleted 828. A sample charged to several sites is counted once per site.
- CHTM run times: the first focus run took 353 s plus 95 s of cover step, the confirm run 347 s plus 4 s.

### Independent full Validator on each E8 output (`engine.cli validate`, owner settings)

```
=== swA
validate CHTM_SIDE_WALK_2nd_floor: verdict FAIL
  textures        PASS        41636 samples seen in BEFORE, 0 failed {'covered': 0, 'overlaid': 0, 'deleted': 0, 'look': 0, 'uv': 0, 'side': 0}
  problems        FAIL        targets signed; before -> after: flicker_diff 0->0, flicker_same 530->530, reversed 809->809, hidden 1853->1854, loose 221->221, open_edges 250->256, cracks 550->552
  nothing_deleted PASS        0 deleted, 0 replaced, 0 covered, 0 overlaid (0 samples only the 1024 extra directions saw)
  time 23.1 s
=== swB
validate CHTM_2nd_to_3rd_building_sidewalk_outside: verdict FAIL
  textures        PASS        91154 samples seen in BEFORE, 0 failed {'covered': 0, 'overlaid': 0, 'deleted': 0, 'look': 0, 'uv': 0, 'side': 0}
  problems        FAIL        targets signed; before -> after: flicker_diff 321->321, flicker_same 1026->1021, reversed 838->838, hidden 2411->2422, loose 79->79, open_edges 326->353, cracks 559->578
  nothing_deleted PASS        0 deleted, 0 replaced, 0 covered, 0 overlaid (0 samples only the 1024 extra directions saw)
  time 60.76 s
=== chtm5
validate CHTM-L05: verdict FAIL
  textures        PASS        275918 samples seen in BEFORE, 0 failed {'covered': 0, 'overlaid': 0, 'deleted': 0, 'look': 0, 'uv': 0, 'side': 0}
  problems        FAIL        targets signed; before -> after: flicker_diff 5668->5668, flicker_same 4793->4789, reversed 29->29, hidden 12870->12893, loose 1055->1057, open_edges 346->373, cracks 3884->3898
  nothing_deleted PASS        0 deleted, 0 replaced, 0 covered, 0 overlaid (0 samples only the 1024 extra directions saw)
  time 383.39 s
```

On all three units, checks 1 and 3 PASS with 0 covered and 0 deleted. Check 2 fails; see concern 2.

### Solidify unchanged

Measured: base b43d27f's `solidify.py`, loaded from `git show`, against this branch's, on both sidewalks with the owner's profile.

```
ce26e0392ab0 mesh arrays equal: True | new_faces equal: True | replaced equal: True | report equal (minus runtime): True
0b290ec0bcb4 mesh arrays equal: True | new_faces equal: True | replaced equal: True | report equal (minus runtime): True
```

`apply_edits(input, E8 edits)` against solidify on the same units:

```
ce26e0392ab0 faces 4801 4801 | keys+UV multiset equal: True | same corner positions row by row: True | points 1718 vs 1839 | edits 66 sites 66
0b290ec0bcb4 faces 7480 7480 | keys+UV multiset equal: True | same corner positions row by row: True | points 3082 vs 3114 | edits 56 sites 54
```

### Visual pass (what I saw)

`repair-unit` writes no .skp, so `render_skp.py` and `skp_edge_audit.py` were not run. Instead, a scratch script rendered BEFORE | AFTER crops of every kept piece into `C:/Temp/e8a/<run>/visual/site_*.png`, with the piece's new faces in red, from three views: far in front, 3 in in front, and 3 in behind. I looked at 6 of them.

- **sidewalk B, site 95** (a cut replacing 7 broken pieces): from far in front, BEFORE and AFTER are identical. 3 in in front, the jagged teeth along the band under the edge become one clean red quad.
- **sidewalk B, site 19** (a 12-face bottom): from far below, identical. 3 in below, it fills a gap through which inner faces showed.
- **CHTM 5th, site 210** (a wall): from far, identical. Up close it fills a gap.
- **CHTM 5th, site 85** (a bottom): from far, identical. Up close it lies almost entirely behind other faces.
- **sidewalk A, site 128** (a cut): from far in front, a thin red sliver, plus a wedge of the neighbouring kept sites 142/143, now shows where BEFORE showed empty background. Those kept pieces are themselves visible: they close an opening to the void and cover nothing. That is allowed by the rule, but the owner will see them.

## Rules touched (AGENTS.md §3-6)

- **Only solidify invents vertices.** E8's points are solidify's invented points, carried unchanged. `Edit` accepts `new_points` from E8 only in add or cut edits.
- **Guards.** Nothing in `engine/guard/**` changed; `cover_max_exposure` stays 0.10 (ruling E8-R1). The strictness comes from the site checks: measured above, covered 13,350 drops to 0 on CHTM 5th.
- **The visible rule (§5) and validation (§6).** Every shipped piece passed the Validator's focus check. The full Validator finds 0 covered and 0 deleted on all three units.
- **Blocked operations (§4).** None used. E8 is the owner's E8 exception engine. Each run is per unit, never the whole campus.
- **Data.** Inputs were frozen snapshots under `data/`, read-only. Outputs went only to C:/Temp/e8a. Nothing was written to the export folder, the owner's folders or the master. The only processes I started were the pytest and CLI runs, which ended on their own; nothing was killed.

## Concerns, said plainly

1. **Most pieces are rolled back:** 4 of 66, 10 of 54 and 8 of 209 are kept. That is the strict rule doing its job (ruling E8-R1), and the rolled-back pieces' holes stay open for E8b and E8c. E8 alone closes few slabs.
2. **Check 2 gets slightly worse with E8 alone.**
   - The changes on CHTM 5th: open_edges 346 -> 373, cracks 3,884 -> 3,898, hidden 12,870 -> 12,893.
   - The kept pieces are isolated (their neighbouring pieces were rolled back), so their own borders add open edges and T-junctions. The duplicated points are not the cause: the counts are identical with them merged.
   - The site judge checks only checks 1 and 3, so the kernel cannot see this. The controller may want E8 followed by later engines, or a check-2 gate.
3. **A covered BACK side may not be caught.** This is the Validator's design, not changed here because `engine/validate` is out of scope.
   - It judges each sample from one viewpoint, preferring one that sees its FRONT.
   - So when a face's front is seen from outside and its back through an opening, a new piece covering the back is not counted as covered. On `slab_with_three_skirts`, the new wall and bottom close the box, whose inner backs were visible through the open side, and the check passes.
   - Unity draws both sides. If the owner's "0 % visible" includes backs seen through an opening, the Validator needs a change, which needs the owner.
4. **Time.** CHTM 5th takes 858 s, almost all in the two focus runs. The site judge's conservative cover candidates reach most of the floor (the P1-K3 docstring says so).
5. **Points.** Points shared between pieces are written once per piece (the K1 convention), so the output carries more point rows than needed. That is harmless for topology (measured above) but visible in the OBJ.
6. **Material `<none>`.** It is written as `usemtl <none>` with no `newmtl`, so viewers show their default material for it, as they would for a face before any `usemtl`. No real snapshot has such a face.
7. **One test was written after its code:** the add-plus-remove test (see item 1).
8. **Exit code.** `repair-unit` exits 0 when the run completes, whatever was rolled back; the verdicts are in report.json and on the printed lines.

## Fix round 1 (review: Spec PASS, Quality APPROVED, five Minor findings)

One commit per finding on `claude/P2-E8a`, test first. Not merged, not pushed.

| finding | commit | change |
|---|---|---|
| 1 | 514ea40 | `repair-unit --snapshot` runs `refuse_protected(snapshot)` before `_load_snapshot`. The error says the folder is read only through `engine/io/snapshot.py`. |
| 2 | bfa8257 | When the built BEFORE does not match the campus map (`matches_campus_map` false), the command prints a "DIFFERS from the campus map's tris" message on stderr and exits 1 before the kernel runs, as `campus-unit-before` does. |
| 3 | 62bbf88 | Exit 0 when the E8 stage passed; exit 3 (`REPAIR_STAGE_FAILED`) when it was rolled back whole or ended any other way. The files are still written and the BEFORE ships. `report.json` gains `exit_code`, and the help (parser description), the module docstring and `cmd_repair_unit` list the codes 0/1/2/3. |
| 4 | 5066211 | The protected-output test is real: `cli.main([... "--out", "D:/PROJECTS/UC ENVIRONMENT BUILDING/x"])` returns 2 with "protected" on stderr; `cmd_repair_unit` with that `--out` raises ValueError; nothing is created there. |
| 5 | f90364f | `E8Solidify.plan` raises ValueError when `replaced_group` names a piece that has no face in `face_group`, instead of silently keeping the replaced faces. |

Three points to note:
- **Finding 3, what counts as passed.** "NOTHING KEPT" counts as a passing stage. Every piece was rolled back on its own charge, each confirmed by the Validator, and the stage's input ships. Exit 3 is for `stage_rolled_back`, or any final verdict other than PASS or NOTHING KEPT (FAIL or UNCONFIRMED). The existing test `test_repair_unit_reports_a_rolled_back_piece_by_reason` (compartment, NOTHING KEPT) keeps exit 0.
- **Finding 3, the exit-3 test.** It swaps in `SiteJudge` through a monkeypatch: the real Validator plus one failing sample whose face id (999,999) is in no site's focus. That failure is charged to no site, so the stage is rolled back whole. My first try used face 0, but attribution charges by face membership in a site's box set, so face 0 was charged to both sites. The test was corrected before any code was written.
- **Finding 4 was never red.** The guard already existed; the finding was that the old test asserted only the `_OUTPUT_ARGS` entry. So the new test passed on first run. To show it has teeth, I ran it once with `cli.refuse_protected` and `cli._refuse_protected_outputs` monkeypatched to no-ops: it FAILS, because stderr shows `error: [Errno 2] No such file or directory: ...no_map.json` instead of a refusal. That run could write nothing either: the map file does not exist.

### Red, then green (real output)

Finding 1, red:
```
$ pytest engine/tests/test_cli_repair_unit.py -k live_export
E   AssertionError            <- raised by the monkeypatched _load_snapshot: the live export path was being read
1 failed, 6 deselected in 1.77s
```
Finding 1, green: `7 passed in 1.58s` (test_cli_repair_unit.py)

Finding 2, red:
```
$ pytest engine/tests/test_cli_repair_unit.py -k differs
E       assert 0 == 1
1 failed, 7 deselected in 9.63s
```
Finding 2, green: `8 passed in 1.45s`

Finding 3, red (the test's judge already corrected; its assertions before the exit code hold):
```
$ pytest engine/tests/test_cli_repair_unit.py -k "exit_code or help"
E       KeyError: 'exit_code'
E       assert (0 == 3)
E       AssertionError: assert ('exit 0' in 'usage: python -m engine.cli repair-unit [-h] ...')
3 failed, 8 deselected in 1.28s
```
Finding 3, green: `11 passed in 1.71s`

Finding 4: `1 passed, 10 deselected in 0.72s` (green at once). With the guards disabled:
```
E        +  where "error: [Errno 2] No such file or directory: '...\no_map.json'\n" = CaptureResult(...).err
FAILED engine/tests/test_cli_repair_unit.py::test_repair_unit_refuses_a_protected_output
1 failed, 10 deselected in 0.21s
```

Finding 5, red:
```
$ pytest engine/tests/test_e8_solidify.py -k replaced_face_whose
E       Failed: DID NOT RAISE ValueError
1 failed, 32 deselected in 1.10s
```
Finding 5, green: `33 passed in 14.32s` (test_e8_solidify.py)

### Suites after the fix round

```
$ ( cd <worktree> && PYTHONPATH="$PWD" "$PY" -m pytest engine/tests -q -p no:cacheprovider )
1760 passed, 1 xfailed in 564.68s (0:09:24)
$ ( cd <worktree> && PYTHONPATH="$PWD" "$PY" -m pytest tools/tests -q -p no:cacheprovider )
123 passed in 14.70s
```

Engine: 1754 plus 6 new tests (finding 4 rewrote an existing one). The xfail is the pre-existing one. The golden-unit runs were not repeated. No change in this round alters what E8 plans: finding 5 only adds a refusal, and on the real runs every replaced face's piece shipped faces, as the earlier 66, 54 and 209 sites show.

Measured after the fix round: `E8Solidify.plan` with the finding-5 check, owner's profile, on the three golden units. None raises, and the edit and site counts are the earlier runs':
```
CHTM_SIDE_WALK_2nd_floor plan ok: 66 edits 66 sites
CHTM_2nd_to_3rd_building_sidewalk_outside plan ok: 56 edits 54 sites
CHTM-L05 plan ok: 216 edits 209 sites
```
