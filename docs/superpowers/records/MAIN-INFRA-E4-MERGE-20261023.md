# E4, the checked coplanar merge for the fresh MAIN INFRA floors (2026-10-23)

Branch `claude/MAIN-INFRA-E4-MERGE-20261023` (worktree `.claude/worktrees/MAIN-INFRA-E4-MERGE-20261023`, from
`codex/main-infra-e3-pilot-20261023` at 531769c). Nothing here has run on a real floor: unit fixtures only, as the
brief said (another worker holds the engine). Nothing under `engine/guard/**`, no `FixProfile` threshold and no
existing test was changed.

## Owner approval

The owner approved, in chat on 2026-10-23, that the engine may CHANGE TRIANGULATION on the fresh MAIN INFRA floors
(the Minecraft floor exports), as a separate guarded pass after E3. That is the one thing E3's remove-only contract
forbade and E4 does. The approval covers those floors; it is not a general release of the merge into the legacy
pipeline, and the stage audit carries it (`owner_approval`).

## The problem

The fresh exports cut every flat wall, glass panel and floor into coplanar slivers with T-junctions. The Validator
reads them as `cracks` (diagonal slits) and the owner sees stray internal lines (`plines`). The hidden-face engine E3
cannot touch them (7F: cracks 5429 -> 4705). The owner wants one clean surface per coplanar material region with no
internal line, without moving or inventing a vertex and without bridging a real opening.

## The contract

`engine/repair/engines/e4_merge.py`, `E4Merge(name="E4", legacy=False)`:

- Topology exactly as the legacy profile reads it (`e4_topology`: `flat_material_indices` at `flat_texture_std`,
  `analyse_topology_memo` at `coplanar_angle` / `soft_angle`), then the EXISTING `engine.fixes.merge.merge_regions`
  (constrained Delaunay over each region's union ring, holes kept, one affine UV map per region, positions never
  moved, appended or re-indexed).
- ONE site per coplanar region whose triangulation changed: `Edit(engine="E4", kind="cut", faces=<the region's input
  faces>, new_faces=<its new triangles>, new_points=None, new_face_uv, new_face_normal)`. A `cut` is the kernel's
  "replace these faces by those" and is allowed to every engine; an `add` is E8's alone and E4 never needs one. The
  cut inherits the region's material and lowest source line.
- A region is one site and is never split; a region over `max_site_faces` (512, E3's cap) is refused `too_large`.
- `unchanged` (skipped): the merge returned the same triangles, or the same triangle count over the same vertices (a
  re-diagonalisation removes no sliver, T-junction or internal line). So a second E4 run over a merged floor plans
  nothing; the test proves it.
- Refused before the judge sees it (`report["refused"]`, with the reason and the numbers): `area_changed` (area
  after differs from area before by more than 1e-6 relative), `off_plane` (a new corner farther than
  `1.5 x max(axis quanta)` from the input faces' area-weighted plane), `flipped`, `uv_lost`, `uv_seam` (for a
  TEXTURED material the one affine UV map of the new triangles misses an input corner by more than 1e-3 UV units;
  for a FLAT material the merge re-bases the UVs by whole tiles, which is invisible and only recorded),
  `mixed_material`.
- `plan` raises if `merge_regions` ever returned different `positions`.
- `allowed_regions` restricts the plan to the region ids a crack judgement said to merge.
- Evidence per site: `region`, `material`, `look`, `faces_before`, `faces_after`, `area_before`, `area_after`,
  `ring_vertices`, `plane_offset`, `uv_residual`, `centroid`, `bbox`.

What is guarded, and by whom:

| Guard | Where |
|---|---|
| no vertex moved, added or re-indexed | `merge_regions` by construction; `region_changes` asserts positions equal; `Edit` refuses `new_points` for E4; `verify_merged_mesh` re-checks the saved pair |
| area equal per region (1e-6 relative) | `region_changes` (refuses), `verify_merged_mesh` (refuses on readback) |
| new triangles in the region plane and inside the source faces' footprint | `region_changes` (plane), `verify_merged_mesh` (plane and shapely footprint, buffered by the region tolerance) |
| holes kept, nothing bridged | the merge keeps inner rings; the footprint check refuses a triangle over an opening; test `test_a_region_with_a_real_opening_keeps_the_hole_open` |
| UVs continuous | `region_changes` (`uv_seam` for textured materials); the Validator's texture check is the independent judge |
| nothing visible deleted or covered | the kernel's site checks with the Validator as site judge (`validate_sites=True`); a charged site is rolled back whole and its slivers copied through unchanged |
| the saved pair is what the kernel kept | `merged_mapping` (outcome == `apply_edits(before, kept)`), `verify_merged_mesh` on readback in both frames |

What is NOT guarded here:

- The strict guard (`engine/guard`) has not run: `stage-audit.json` says `guard: pending`, `accepted: false`.
- The Validator's full floor run (textures, nothing-visible-deleted, signed problem counts) has not run on an E4
  candidate. `load_physical_pair` now accepts the E4 cleanup modes (follow-up below), so it can.
- Faces OUTSIDE a merged region that `merge_regions` splits at a threaded vertex (`copied_split`) are NOT taken: E4
  copies them through unchanged, so a T-junction between a merged region and a neighbouring face of another region
  can remain. Measured on fixtures only.
- The crack judgement has no renderer: the question state is the `_spot` summary and the region's outline as text.

## Files

- `engine/repair/engines/e4_merge.py` -- the engine, `e4_topology`, `region_changes` (shared with the judge).
- `engine/tests/test_e4_merge.py` -- 13 tests: 4 slivers with two T-junctions -> one cut of 2 triangles, area 800
  kept; vertices never move; UVs continuous at 5 sample points (1e-6); a second run is a no-op; a flat material's
  whole-tile re-basing recorded not refused; a shifted sliver is its own region; a hole stays open (4 open edges,
  no triangle inside); `area_changed` refusal; `uv_seam` refusal; a moved vertex raises; `allowed_regions`; the
  checked kernel keeps a clean merge; a judge that fails one site rolls back that region only (its slivers copied
  through, the other region merged, `first FAIL / final PASS`).
- `tools/main_infra_e4.py` -- `run_checked_e4(before, looks, flatness, allowed_regions=None) -> (outcome, mapping)`,
  `merged_mapping`, `merged_mesh`, `verify_merged_mesh`, `floor_from_candidate`, `save_merged_pair(engine_floor,
  source_floor, mapping, out)` writing `candidate.engine.obj`, `candidate.source.obj` (new triangles by vertex
  index; new normal rows rotated back with the frame) and `region-map.json`
  (`{mode: e4_coplanar_merge, kept_source_faces, appended_uvs, appended_normals, regions: [{site, region, material,
  source_faces, new_triangles, face_v, face_vt, face_vn, area_before, area_after, ring_vertices}], engine_report}`).
- `tools/run_checked_e4_floor.py` -- the floor runner (below); refuses an existing `<root>/e4/<F>/`.
- `tools/main_infra_crack_judge.py` -- `crack.region` Choice question per coplanar region with cracks; `crack_rule`
  (`keep` for a stair material or an open edge on one, `merge` when the merge keeps the area and passes E4's rules,
  else the owner); Jev only as a recorded suggestion in `suggest` mode; `crack-judgement.json` with
  `merge` / `keep` / `unsure` region ids and `provider` per decision.
- `tools/tests/test_main_infra_e4.py` (7) and `tools/tests/test_main_infra_crack_judge.py` (5).

## Commands

From the worktree root, `PYTHONPATH` set to it, `-p no:cacheprovider`:

```powershell
$env:PYTHONPATH=(Get-Location).Path
$PY='D:/PROJECTS/05-Corllenium-UC-Building-Repair-Engine/.venv/Scripts/python.exe'
& $PY -m pytest engine/tests/test_e4_merge.py tools/tests/test_main_infra_e4.py tools/tests/test_main_infra_crack_judge.py -q -p no:cacheprovider
```

Scoped output (2026-10-23): `13 passed in 3.95s`, `7 passed in 5.87s`, `5 passed in 2.08s`.

Whole suites (same interpreter, `-p no:cacheprovider`, run 2026-10-23/24):

```
pytest tools/tests  -> 304 passed in 97.52s (0:01:37), exit 0
pytest engine/tests -> 2 failed, 1965 passed, 1 xfailed in 2903.80s (0:48:23), exit 1
  FAILED engine/tests/test_site_judge.py::test_the_repair_package_imports_nothing_from_the_validator
         AssertionError: e1_loose.py imports engine.validate.checks
  FAILED engine/tests/test_unity_mirror.py::test_a_real_round_trip_under_a_neutral_preset_is_unity_safe
         MirrorError: mirror importer copy is stale: mirror (none) != owner ea37ed71...; run tools/unity_mirror.py sync
```

Both failures predate this branch: `git show 531769c:engine/repair/engines/e1_loose.py` already imports
`engine.validate.*` (lines 25-29), and the Unity mirror copy is absent in this environment. `e4_merge.py` imports
nothing from `engine.validate` or `engine.site_judge`; only `tools/main_infra_e4.py` does, like `tools/main_infra_e3.py`.

Run E4 on 7F from the E3 candidate (NOT run; the engine is in use by another worker):

```powershell
$env:PYTHONPATH=(Get-Location).Path
& $PY -B -u tools/run_checked_e4_floor.py --root <claude run root> --floor 7F --raw-name "7th floor main infra.obj" --from-e3
```

Optionally first judge the cracks and pass the judgement (then only `merge` regions run):

```powershell
& $PY tools/main_infra_crack_judge.py --before <root>/e3/7F/candidate.engine.obj --errors <root>/.../errors.json --flatness <flatness.json> --out <root>/e4/7F-crack-judgement.json [--jev]
& $PY -B -u tools/run_checked_e4_floor.py --root <root> --floor 7F --raw-name "7th floor main infra.obj" --from-e3 --crack-judgement <root>/e4/7F-crack-judgement.json
```

Output: `<root>/e4/7F/{candidate.engine.obj, candidate.source.obj, region-map.json, edit-log.jsonl,
stage-audit.json (cleanup_mode e3_then_e4_merge, guard pending), assets}`.

## Open questions

1. `merge_regions`' ring simplification (`_ring_keep`, `collinear_tol = 1.5 x max(quanta)`) may move a border by up
   to that much and rule 9 lets a region's area grow by `collinear_tol x perimeter`. E4 refuses any site whose area
   changes by more than 1e-6 relative, so such a region is dropped rather than shipped -- on a real floor that may
   refuse regions the owner wanted merged. Passing `collinear_tol=0.0` is not an option: `merge_regions` reads
   `None` as the default and `0.0` as a bound of zero, which would still drop exactly-collinear vertices; worth a
   measured trial on 7F.
2. `_region_uvs` re-bases a FLAT material's UVs so the minimum lies in [0, 1): a whole-tile shift. E4 records it and
   does not refuse. For a flat material WITH a (low-variance) texture that does not tile at UV unit boundaries this
   would be visible; the Validator's texture check is the judge.
3. The merge appends `vn` rows; E4 carries them only when every input face of the region had a normal.
4. `max_site_faces = 512` mirrors E3; a floor slab of more slivers is refused `too_large` and listed. The cap may
   need raising for real floors (a region cannot be split).
5. (closed by the follow-up below) `load_physical_pair` accepts `e4_merge_only` / `e3_then_e4_merge`.
6. Bootstrap order: `bind_saved_e4` requires `guard.passed` (as asked, and as `load_physical_pair` already did for
   E3), yet the independent guard is what produces that verdict and the runner writes `guard: pending`. As for E3,
   the reviewer sets the flag before the guard and validation run; alternatively the binding could take
   `require_guard=False` when called from the guard itself. CLOSED (coordinator, 2026-10-24): `bind_saved_e4` takes
   `require_guard: bool = True`; `tools/e4_independent_guard.py` calls it with `require_guard=False` (the guard
   produces the verdict and never writes the audit), the Validator path keeps the default. After the guard passes the
   reviewer records its receipt in the audit (`guard.passed`), as the E3 flow does. Tests: the binding accepts a
   pending audit only with `require_guard=False` and refuses it by default and with `True`; the guard runs to a PASS
   receipt on a candidate whose audit still says pending and leaves that audit unchanged.

## Follow-up (2026-10-24): the E4 binding and the E4 independent guard

- `tools/main_infra_e4_binding.py: bind_saved_e4(*, candidate, audit, before_engine, after_engine, before_source,
  after_source, require_guard=True)`, modelled on `bind_saved_e3`: `cleanup_mode` in {`e4_merge_only` (`executed_stages == ["E4"]`),
  `e3_then_e4_merge` (`["E3", "E4"]`)}; `guard.passed` required; `region-map.json` and `edit-log.jsonl` hash-bound to
  the audit (`region_map_sha256`, `edit_log_sha256`); in the chained mode the audit's `e3_candidate` binding (dir and
  the hashes of its engine/source candidate, `source-faces.json`, `stage-audit.json`) is checked and `bind_saved_e3`
  proves E3 candidate = baseline minus removed; then `verify_merged_mesh` proves the E4 candidate = that BEFORE with
  the mapped regions replaced, in both frames; the log may hold only non-legacy E4 cuts with no new points whose kept
  sites equal the mapped regions (faces and triangle counts); `kept_source_faces` must be the complement of the
  replaced faces; the one check must be stage E4, non-legacy, rollback-enabled and, when anything was kept, end PASS
  with a last run of 0 failing / 0 unknown. Returns `{candidate_contract, region_map_sha256, edit_log_sha256,
  e3_contract, e3_removed_triangles, e4_merged_regions, e4_replaced_triangles, e4_new_triangles,
  baseline_kept_source_faces, e4_region_source_faces}` (face ids mapped back to the BASELINE through E3's list).
- `tools/main_infra_physical_validation.load_physical_pair` dispatches those two modes to it (one `elif`; BEFORE
  stays the qualified baseline snapshot, AFTER is the E4 candidate).
- `tools/e4_independent_guard.py` -- the E4 twin of the 4F-7F worktree's `tools/e3_independent_guard.py` (that file
  is not edited): the same manifest / qualification / provenance / snapshot / asset checks, `bind_saved_e4` in place
  of the fingerprint membership test, looks loaded and checked, the AFTER's material ids rebound to the BEFORE's by
  NAME (`read_obj` numbers materials by first use and `strict_guard` compares ids; `material_order_equal` and
  `material_ids_rebound_by_name` are recorded), then the UNCHANGED `strict_guard` loaded by path from `--helper`
  (`--original-oracle` loads `engine/rays/bounded_brute.py` beside it). Writes `input-readback.json` and
  `independent-guard.json` with the E3 guard's keys (`removed_triangles` = E3-removed + E4-replaced, plus
  `new_triangles` and `manifest_files`), `guard-progress.json` per view, `failure.txt` on any failure; exit 0 pass,
  2 fail. The manifest's file count is recorded, not asserted (the E3 guard hard-codes 36).
- Tests: `tools/tests/test_main_infra_e4_binding.py` (19) and `tools/tests/test_e4_independent_guard.py` (4). The
  guard tests use a fake `strict_guard` helper beside a fake oracle (the real one lives in another worktree and
  renders 26 views): they prove the plumbing, the readback and the rebinding, not the renderer.
- Whole tools suite after the follow-up: `pytest tools/tests -q -p no:cacheprovider` ->
  `327 passed in 139.68s (0:02:19)`, exit 0 (304 before + 19 + 4); after the `require_guard` change:
  `329 passed in 140.97s (0:02:20)`, exit 0 (the two E4 files alone: `25 passed in 52.97s`).

Commands (worktree root, `PYTHONPATH` = it):

```powershell
& $PY -m pytest tools/tests/test_main_infra_e4_binding.py tools/tests/test_e4_independent_guard.py -q -p no:cacheprovider
# the independent guard on an E4 candidate (the audit's guard.passed must be set first; see open question 6):
& $PY -B -u tools/e4_independent_guard.py --root <root> --floor 7F --raw-name "7th floor main infra.obj" --candidate <root>/e4/7F --out <root>/e4/7F-independent-guard --helper D:/PROJECTS/05-Corllenium-UC-Building-Repair-Engine/.claude/worktrees/MAIN-INFRA-CLAUDE-4F-7F-20261023/tools/main_infra_candidate.py --job-id <id> --reviewer <name> [--original-oracle]
# the Validator on it (BEFORE = baseline, AFTER = <root>/e4/7F):
& $PY tools/main_infra_physical_validation.py --raw "<root>/raw/7th floor main infra.obj" --reference <root>/reference/7F.json --baseline <root>/normalized/7F --qualification <root>/independent-validator/import-audit/qualification-7F.json --candidate <root>/e4/7F --materials <root>/independent-validator/preflight/materials-7F.json --out <root>/e4/7F-validation
```

## E5, the checked coincident-layer cull (2026-10-24), and the chained order E3 -> E5 -> E4

Branch `claude/MAIN-INFRA-E4-MERGE-20261023`, commits 9e17b3a (engine), 987a446 (tools), plus this record. Fixtures
only: nothing ran on a real floor (another worker holds the engine). Nothing under `engine/guard/**`, no `FixProfile`
threshold, no `engine/site_judge.py` default and no existing test was changed.

### Why (measured, the E4 trial on the real 7F E3 candidate, 2026-10-24, 4 h 11 min)

1,243 coplanar regions; the site judge rolled back 968 of them, every one with reasons `{"covered": n}`: the merged
clean triangle covers samples that lie on a COINCIDENT TWIN LAYER (a second face on the same plane within the depth
tolerance, overlapping footprint) which the Validator counts as `flicker_same` (same look) or `flicker_diff` (different
look). The fresh Minecraft export is full of these twins: 7F before E3, flicker_diff 4518, flicker_same 7091. And 123
of the 275 kept regions GREW (2 input faces -> 8-14 triangles) because `keep_all` rings carry many vertices. So: one
layer of each twin has to go before the merge (E5), and a merge that gains triangles is refused (E4 `grew`).

### The E5 contract

`engine/repair/engines/e5_coincident.py`, `E5Coincident(flatness, looks=None, priority=None, max_site_faces=512,
name="E5", legacy=False)`:

- REMOVE ONLY: `Edit(engine="E5", kind="remove")` and nothing else; no cut, no new point, no new face (the E5 cut of
  AGENTS.md section 4 is not used: never clip, never add geometry).
- THE PAIRS ARE THE VALIDATOR'S: `engine.fixes.overlap.double_layers(positions_c, face_w, guard_depth_tol(quanta,
  profile), VIEWS_26, profile.guard_size, centre=centre)` over `analyse_topology(mesh, frozenset(), coplanar_angle,
  soft_angle)`, exactly as `find_errors` calls it, so E5 targets exactly the faces counted as flicker. Only SAME-FACING
  pairs are taken (`opposite` false and the normals' dot > 0.7); opposite-facing sheets are left alone
  (`report["pairs"]["opposite"]`).
- WHO LOSES, per coincident group (union-find over the pairs), each face in ascending (area, -id) order against the
  kept faces overlapping it: (a) same look -> the larger face wins (equal area: the lower id, so an identical copy
  keeps its first occurrence); (b) different look -> the higher `priority(material name)` wins (`default_priority`:
  2 for a name containing UC_PAL_05, UC_PAL_12, UC_PAL_00, quartz_block_top, quartz_block_side, iron_block, glass,
  wool, trim, facade; 0 for concrete_white / concrete_gray; 1 otherwise), at equal priority the larger area, at equal
  priority and area nobody (`no_winner`: the owner decides). A face is dropped only when the union of the faces that
  beat it covers at least 98 % of its footprint (shapely in the group plane; `uncovered` otherwise: partial overlap is
  never clipped). Winners are ANCHORED (they cannot lose later in the run) so no pair loses both faces; a final pass
  puts back a dropped face that the FINAL kept faces no longer cover 98 % (`only_coverage`), so a drop never opens a
  hole beyond the 2 % the rule allows.
- SITES: one `remove` per edge-connected group of dropped faces (E3's `_components`), split by `split_group` over
  `max_site_faces` (512). Evidence per site: `pairs` rows (`face`, `material`, `look`, `area`, `winners`,
  `winner_looks`, `winner_areas`, `overlap_fraction`, `rule` in {same_look, priority, larger_area}), `area`,
  `centroid`, `bbox`. Report: `pairs` counts, `groups`, `dropped`, `by_rule`, `kept` (reason counts), `kept_faces`,
  `planned`, `seconds`.

What is guarded, and by whom:

| Guard | Where |
|---|---|
| remove only, no geometry invented | the engine emits only `remove`; `source_survivors(..., engine='E5')` refuses anything else; `verify_survivor_mesh` on readback |
| the pairs are the Validator's | `double_layers` at the pipeline's depth tolerance, as `find_errors` |
| never both faces of a pair | anchoring of winners (test `never_both_faces_of_a_pair`) |
| never the only coverage of a footprint | 98 % cover by the winners, re-checked against the final kept faces (`only_coverage`) |
| opposite-facing sheets untouched | the `opposite` flag and the facing dot (test) |
| nothing visible deleted or covered | the kernel's site checks with the Validator as judge (`validate_sites=True`): removing an identical coplanar copy passes; removing the different-look copy FAILS check 1 `look` / check 3 `replaced` in today's Validator and is rolled back (test `the_judge_keeps_the_identical_twin_drop_and_rolls_back_the_different_look_drop`) |
| the saved pair is the BEFORE minus the kept removes | `save_survivor_pair` + `bind_remove_only` (hash-bound `source-faces.json`, `edit-log.jsonl`) |

NOT guarded here: the strict guard (`guard: pending` in the audit); the Validator's full floor run on an E5 candidate;
anything on a real floor. OPEN: as the Validator stands (its docstring: "v0 has NO allowed-change classes"), every
different-look drop (rule `priority` / `larger_area`) is rolled back by the site judge, so on 7F E5 will take the
flicker_same twins and leave the flicker_diff ones until the Validator names E5's allowed-change class (the owner's
table: "Where both sides are seen with different looks, the owner decides").

### E4: `allow_growth`

`E4Merge(allow_growth: bool = False)`: a region whose merge returns more triangles than it had input faces is refused
`grew` (in `report["refused"]` with `faces_before` / `faces_after`), checked before the area rule so a grown region is
named as such. `allow_growth=True` restores the old behaviour. Tests `engine/tests/test_e4_growth.py` (3): refused by
default, let through with the flag (area kept, 6 triangles over the same six vertices), the fixtures never grow.

### Tools

- `tools/main_infra_e5.py`: `run_checked_e5(before, looks, flatness, priority=None, *, report=None) -> (outcome,
  survivor_indices)` via `repair_unit(..., engines=[E5Coincident(...)], validate_sites=True)` and
  `tools.main_infra_e3.source_survivors(before, outcome, engine='E5')` (the E3 proof, now taking the engine name);
  `save_survivor_pair` is E3's (same `source-faces.json`, `mode: original_source_survivors`); `audit_report` trims the
  engine report for the stage audit. Cleanup modes `e5_cull_only` (`["E5"]`) and `e3_then_e5_cull` (`["E3", "E5"]`).
- `tools/main_infra_e3_binding.py`: the remove-only proof is now `bind_remove_only(engine=...)`; `bind_saved_e3` keeps
  its contract (same keys, same mode check); `chained_e3_before` (moved from the E4 binding) proves the `e3_candidate`
  an audit chains through.
- `tools/main_infra_e5_binding.py`: `bind_saved_e5(..., require_guard=True)` for both E5 modes (the chained one
  through `chained_e3_before`); `chained_e5_before` for the stage after E5. `load_physical_pair` dispatches
  `e5_cull_only` / `e3_then_e5_cull` to it, and `e3_then_e5_then_e4_merge` to `bind_saved_e4`, which proves the E5
  candidate through `chained_e5_before` (its own `e3_candidate` inside) and maps face ids back to the baseline through
  both survivor lists; its receipt adds `e5_contract` and `e5_removed_triangles`.
- The 4F-7F worktree's `tools/e3_independent_guard.py` binds with `bind_saved_e3` (only `e3_remove_only`): to run it
  on an E5 candidate it needs the same relaxation (`bind_saved_e5`, or `bind_remove_only` with the engine taken from
  `executed_stages[-1]`, and `require_guard=False` as the E4 guard does). That worktree is NOT edited here.
- `tools/run_checked_e5_floor.py --root --floor --raw-name [--from-e3]` writes `<root>/e5/<F>/` (the candidate pair,
  `source-faces.json`, `edit-log.jsonl`, `stage-audit.json` with `cleanup_mode`, `source_faces_sha256`,
  `edit_log_sha256`, `e3_candidate`, `engine_report`, `guard: pending`, the assets); refuses an existing output.
- `tools/run_checked_e4_floor.py --from-e5`: BEFORE = `<root>/e5/<F>/candidate.engine.obj` (its audit must say
  `e3_then_e5_cull`), audit `cleanup_mode e3_then_e5_then_e4_merge`, `executed_stages ["E3", "E5", "E4"]`,
  `e5_candidate` binding plus the E5 audit's `e3_candidate` carried along; `--from-e3` and `--from-e5` exclude each other.

Tests: `engine/tests/test_e5_coincident.py` (13: exact smaller twin dropped and the footprint unchanged; an identical
copy drops the higher ids; a 98 %-covered face dropped; a half-overlapped face kept (25 % / 75 % per triangle); the
default priority ranking; facade beats concrete; equal priority -> the larger area, else both kept; a custom priority;
opposite-facing sheets untouched; a face that is the only coverage of part of its footprint is never dropped (96 %
covered, stays); never both faces of a pair (anchoring; a second run takes the middle layer); the cap splits a group
into sites; the real site judge keeps the identical-twin drop and rolls back the different-look drop, `first FAIL /
final PASS`), `engine/tests/test_e4_growth.py` (3), `tools/tests/test_main_infra_e5.py` (17: the run, survivor-proof
refusals, save and readback in both frames, both modes through `load_physical_pair`, hash and rehash refusals, the
guard bootstrap, both runners' refusals, and the E3 -> E5 -> E4 chain on a fixture run root: E5 `--from-e3` 8 -> 4
triangles, E4 `--from-e5` 4 -> 2, `load_physical_pair` on the E4 candidate -> `e3_removed 1, e5_removed 4,
e4_replaced 4, e4_new 2`, a changed E5 proof breaks the chain).

### Commands (worktree root, `PYTHONPATH` = it, `-p no:cacheprovider`)

```powershell
$env:PYTHONPATH=(Get-Location).Path
$PY='D:/PROJECTS/05-Corllenium-UC-Building-Repair-Engine/.venv/Scripts/python.exe'
& $PY -m pytest engine/tests/test_e5_coincident.py engine/tests/test_e4_growth.py engine/tests/test_e4_merge.py -q -p no:cacheprovider
& $PY -m pytest tools/tests -q -p no:cacheprovider
```

Output (2026-10-24, this interpreter):

```
pytest engine/tests/test_e5_coincident.py engine/tests/test_e4_growth.py engine/tests/test_e4_merge.py
  -> 29 passed in 146.95s (0:02:26), exit 0   (13 + 3 + the 13 existing E4 tests)
pytest tools/tests -> 346 passed in 218.80s (0:03:38), exit 0   (329 before + 17)
pytest tools/tests/test_main_infra_e5.py -> 17 passed in 82.23s
pytest tools/tests/test_main_infra_e3.py test_main_infra_e3_binding.py test_main_infra_e3_replay.py test_main_infra_e4.py
  test_main_infra_e4_binding.py test_e4_independent_guard.py -> 87 passed in 110.02s (the suites the refactor touched)
```

The chained order on 7F (NOT run; the engine is in use by another worker): E5 on the E3 candidate, then E4 on the E5
candidate.

```powershell
& $PY -B -u tools/run_checked_e5_floor.py --root <claude run root> --floor 7F --raw-name "7th floor main infra.obj" --from-e3
& $PY -B -u tools/run_checked_e4_floor.py --root <claude run root> --floor 7F --raw-name "7th floor main infra.obj" --from-e5
```

Output: `<root>/e5/7F/{candidate.engine.obj, candidate.source.obj, source-faces.json, edit-log.jsonl, stage-audit.json
(e3_then_e5_cull, guard pending), assets}`, then `<root>/e4/7F/{..., region-map.json, stage-audit.json
(e3_then_e5_then_e4_merge)}`. The Validator on the E4 candidate (after the guard's receipt is recorded as `guard.passed`):

```powershell
& $PY tools/main_infra_physical_validation.py --raw "<root>/raw/7th floor main infra.obj" --reference <root>/reference/7F.json --baseline <root>/normalized/7F --qualification <root>/independent-validator/import-audit/qualification-7F.json --candidate <root>/e4/7F --materials <root>/independent-validator/preflight/materials-7F.json --out <root>/e4/7F-validation
```

### Open questions (E5)

1. Different-look drops are planned by the priority rule but rolled back by today's Validator (check 1 `look`, check 3
   `replaced`); the flicker_diff twins stay until the Validator names E5's allowed-change class (an owner decision).
2. A three-layer stack loses one layer per E5 run (anchoring); a real floor may need E5 twice before E4.
3. `double_layers` renders 26 views per plan (as `find_errors` does); on a real floor the plan's
   `seconds["double_layers"]` is the number to read first.
4. `max_site_faces = 512` mirrors E3; a dropped group over it is split by a centroid grid (a site is never partly kept).
5. The E4 independent guard (`tools/e4_independent_guard.py`) binds with `bind_saved_e4`, which now accepts the triple
   mode, so an E4-after-E5 candidate needs no change there; an E5-only candidate has no independent guard yet (see the
   4F-7F note above).

## E5 `backface_twin` and the Validator's owner-approved class `coincident_backface_removed` (2026-10-24)

Commit d391ec3 on the same branch, plus this record. Fixtures only; nothing ran on a real floor. `engine/guard/**`,
`FixProfile` thresholds, the strict 26-view guard, `engine/site_judge.py` defaults and existing tests are untouched.
`engine/validate/checks.py` IS changed: the owner approved one allowed-change class (below); the approval reached this
worker through the coordinator's message, not first-hand.

### The owner decision and its measured basis (coordinator, 2026-10-24)

The engine MAY remove the solid-facing twin of a back-to-back coincident pair regardless of look, judged under a new
owner-approved allowed-change class in the Validator. Measured on the real 7F E3 candidate: the first E5 (same-facing
rules only) planned 0 edits because `double_layers` reported 4,783 pairs, ALL `opposite`, 0 same-facing; the error
census on the same candidate shows 5,556 flicker faces of which 4,974 are also `hidden` (128-direction census), i.e. a
face whose normal points into solid lying exactly on its visible twin. E3 never proposes them (its sample points on the
shared plane see the room through the twin, a depth tie) and the first E5 skipped them by the "opposite-facing sheets
are not duplicates" rule.

### E5 rule (c), `backface_twin` (`E5Coincident.cull_opposite_backfaces: bool = True`)

For each pair `double_layers` flags `opposite` (within the depth tolerance, overlapping footprint, the same coverage
test as rules a / b), the per-face front and back exposure is measured exactly as `find_errors` measures it
(`engine.vis.exposure.compute_side_exposure(positions_c, faces, ok, n_dirs=profile.n_dirs)`): the face whose FRONT
exposure is 0 loses to a twin whose front exposure is above 0, whatever the looks; both hidden or both exposed keep
both (`kept["no_backface_winner"]`). Anchoring (never both faces of a pair) and the 98 % cover rules apply unchanged.
Evidence per dropped face: `rule: backface_twin`, `look` / `winner_looks`, `front` / `back` of the face, `winner_front`
/ `winner_back` of its twins, `overlap_fraction`. The group plane is now signed toward the largest face's normal so a
back-to-back pair's normals do not cancel. `report["cull_opposite_backfaces"]`, `report["exposure_n_dirs"]`,
`seconds["exposure"]`.

### The Validator class (`engine/validate/checks.py`: `CBR = "coincident_backface_removed"`, `ALLOWED_CHANGE_CLASSES`)

`Settings.allowed_changes` (frozenset, EMPTY by default: every existing caller and test keeps the strict behaviour;
an unknown name raises; `as_dict` writes a sorted list, so the site judge's `Settings(**as_dict())` round-trips).
With the class enabled, a tested, uncovered BEFORE sample whose AFTER status is `deleted` or `look` (check 3
`deleted` / `replaced`) is reclassified as allowed iff (a) its face's fingerprint is gone in AFTER, (b) a BEFORE face
kept in AFTER lies on the sample within the depth tolerance (the sample inside it, barycentric), its normal opposite to
the sample's face normal (dot < -0.7) and its own front exposure in BEFORE above 0 (the twin was the visible surface),
and (c) the sample's face had front exposure 0 in BEFORE (`compute_side_exposure` at `settings.n_directions`). Such a
sample fails neither check 1 nor check 3 (`reason1 = OK`, left out of `unmet`, `deleted`, `replaced`), a removed face
ALL of whose tested samples were allowed is excused from the floor's pixel measure, and the report gains
`allowed_changes: {coincident_backface_removed: {samples, deleted, look, faces, faces_excused_from_floor, area_in2,
candidates, rule}}` plus a note "ALLOWED CHANGES active (owner-approved class, 2026-10-24)". `covered`, `overlaid`,
`uv`, `side`, same-facing twins and any deletion whose face was exposed stay as strict as today.

Site judge: `SiteJudge(looks, settings=Settings(allowed_changes={CBR}))` passes the class through to `validate`, so an
E5 `backface_twin` site is kept; the default settings roll it back. `tools.main_infra_e5.run_checked_e5(...,
allowed_changes=ALLOWED_CHANGES)` (default `(CBR,)`; `()` for the strict judge) and the E5 floor runner records
`allowed_changes` and the owner approval in the stage audit. `tools/main_infra_physical_validation.py --allow
coincident_backface_removed` (repeatable; `build_parser`, `settings_for`) runs the Validator under the class and writes
it into `validation.json` as the header key `allowed_changes_active`, `settings.allowed_changes`, `inputs.allowed_changes`
and the physical-precision receipt.

Tests: `engine/tests/test_validate_allowed_changes.py` (6: settings default / round trip / unknown name; the strict
default still fails removing the inward twin of another look; with the class the same removal passes, is reported
under `allowed_changes`, reclassifies exactly the strictly-failing samples and excuses both faces from the floor; a
non-coincident deletion still fails with the class; a same-facing twin removal is not covered; removing the exposed face
and keeping the inward twin is not covered); `engine/tests/test_e5_coincident.py` +4 (the solid-facing twin dropped
whatever its look, with its exposures in the evidence; the rule switched off; both-hidden pair kept; the site judge
keeps the site under the class and rolls it back without it -- `NOTHING KEPT`); the opposite-sheets test now also
asserts `no_backface_winner`; `tools/tests/test_main_infra_e5.py` +2 (`run_checked_e5` judges under the class by
default and strictly on request; the CLI's repeatable `--allow` builds the settings and refuses an unknown class).

Output (2026-10-24, worktree root, `PYTHONPATH` = it, `-p no:cacheprovider`):

```
pytest engine/tests/test_validate_allowed_changes.py -> 6 passed in 7.55s
pytest engine/tests/test_e5_coincident.py -> 17 passed (16 + the corrected site-judge test: 1 passed in 14.69s)
pytest tools/tests/test_main_infra_e5.py -> 19 passed in 72.10s
pytest engine/tests/test_validate_checks.py test_site_judge.py test_site_judge_remove_only.py test_site_judge_cover.py
  test_cli_validate_sites.py tools/tests/test_main_infra_physical_validation.py
  -> 1 failed, 137 passed in 207.99s: the one failure is the pre-existing
     test_the_repair_package_imports_nothing_from_the_validator (e1_loose.py imports engine.validate.checks, since
     531769c; e5_coincident.py imports engine.vis.exposure, nothing of engine.validate)
pytest tools/tests -> 348 passed in 150.47s (0:02:30), exit 0   (346 + 2)
```

### 7F commands (NOT run; the engine is in use by another worker)

```powershell
$env:PYTHONPATH=(Get-Location).Path
$PY='D:/PROJECTS/05-Corllenium-UC-Building-Repair-Engine/.venv/Scripts/python.exe'
# E5 on the E3 candidate: the site judge runs under coincident_backface_removed by default (recorded in the audit)
& $PY -B -u tools/run_checked_e5_floor.py --root <claude run root> --floor 7F --raw-name "7th floor main infra.obj" --from-e3
# E4 on the E5 candidate
& $PY -B -u tools/run_checked_e4_floor.py --root <claude run root> --floor 7F --raw-name "7th floor main infra.obj" --from-e5
# the Validator on the E4 candidate (after guard.passed is recorded), under the owner-approved class
& $PY tools/main_infra_physical_validation.py --raw "<root>/raw/7th floor main infra.obj" --reference <root>/reference/7F.json --baseline <root>/normalized/7F --qualification <root>/independent-validator/import-audit/qualification-7F.json --candidate <root>/e4/7F --materials <root>/independent-validator/preflight/materials-7F.json --out <root>/e4/7F-validation --allow coincident_backface_removed
```

### Open questions (backface)

1. Condition (b) uses the twin's GLOBAL front exposure (above 0 from some census direction), not exposure from the
   sample's own viewing side; a twin exposed only elsewhere still qualifies. Tighter: test the twin's front along the
   sample's witness ray. Measured on fixtures only.
2. A removed face is excused from the floor only when every tested sample of it was allowed; a face partly under
   its twin keeps its floor measure and its uncovered samples still fail.
3. The E5 plan now costs one `compute_side_exposure` (128 directions over the whole floor) whenever an opposite pair
   exists -- the same measure the census already runs; `seconds["exposure"]` records it.
4. The E4 independent guard and the strict 26-view guard know nothing of the class: an E5 backface cull changes which
   face answers a pixel on the shared plane (a depth tie in BEFORE), and the strict guard's verdict on that is not yet
   measured.

## After the first real 7F chain run: E5 `interior_twins`, the class excuses `uv`, E4 `--allow-growth`, the guard's chained count (2026-10-24)

The feature commit preceding this record on the branch, plus this record. Fixtures only here; the measured numbers
below are the coordinator's from the first real E3 -> E5 -> E4 chain on 7F.

### Measured (coordinator, real 7F E3 candidate, first chain run)

E5: pairs 4,783, all opposite; faces_in_pairs 5,599; dropped 498 (`backface_twin`); kept `no_backface_winner` 4,476,
`uncovered` 140, `no_overlap` 485; 214 sites, 57 rolled back with reasons {uv: 1250, replaced: 5}. E4 after E5:
regions 4,524, changed 1,904, refused 1,604 = grew 1,250, uv_seam 344, too_large 4, off_plane 4, area_changed 2; 300
sites, 237 kept, 63 rolled back (covered 147). Net 20,625 -> 19,814. The E4 independent guard on the chained candidate
(baseline 26,152 -> E3 20,625 -> E5 20,308 -> E4 19,814) failed its face-count assertion because `before` is the
baseline while the contract counted only E3-removed + E4-replaced.

### 1. E5 rule (d), `interior_twins`

An opposite-facing coincident pair BOTH of whose fronts have exposure 0 (both EXP_HIDDEN by the 128-direction census)
is an interior block-against-block seam: both faces are planned for removal as ONE site (the seam's faces are joined
into one site even when their vertices are not welded, test `interior_twins_are_one_site_even_when_their_vertices_are_
not_shared`); the cover and only-coverage rules do not apply to the seam, the site judge decides, and a seam any sample
sees rolls back as any site does (test: the judge keeps the sealed partition's seam). `kept.both_exposed` now names the
both-exposed pairs (a legitimate two-sided zero-thickness slab); `no_backface_winner` remains only for the mixed case
with no exposure measured. `report["kept_pairs"]` samples the kept opposite pairs (at most `KEPT_PAIRS_LISTED`, 500
rows: `faces`, `looks`, `front`, `back` of both faces, `reason`), `kept_pairs_total` counts them all;
`by_rule.interior_twins` counts the dropped seam faces. Evidence rows of a seam face carry `rule: interior_twins`,
its exposures and its partners' (`winners`, `winner_front`, `winner_back`).

### 2. The class excuses `uv`

`coincident_backface_removed` now reclassifies a sample whose AFTER status is `uv` under the same conditions (a)-(c)
(its face gone, its front exposure 0 in BEFORE, a kept opposite exposed face on it within the depth tolerance), and
counts it as `allowed_changes[CBR].uv`. Strict default unchanged. Test: an inward same-look twin with a 0.37-shifted
UV layout fails `uv` strictly and passes with the class, the excused count equal to the strict `uv` count; the same
shifted twin OUTWARD (both fronts exposed) still fails with the class.

### 3. E4 `--allow-growth`

`tools/run_checked_e4_floor.py --allow-growth` passes `allow_growth=True` to `E4Merge` through
`run_checked_e4(..., allow_growth=...)`; default False; the mapping's `engine_report.allow_growth` and the stage audit's
`allow_growth` record it. Rationale (coordinator): coplanar same-material triangle edges are invisible in the textured
game render, the slit (crack) is the visible defect; the merge's `area_changed`, `off_plane`, `flipped`, `uv_seam`
refusals and the site judge still stand.

### 4. The E4 independent guard on a chained candidate

`tools/e4_independent_guard.py`: `before` is the qualified baseline snapshot, so its face count is kept + E3-removed +
E5-removed + E4-replaced (`contract.e3_removed_triangles + contract.get('e5_removed_triangles', 0) +
contract.e4_replaced_triangles`); `after` stays kept + new. The kept faces themselves are already proven by
`bind_saved_e4` against the chained BEFORE and mapped back to the baseline's ids (`baseline_kept_source_faces`), which
the guard reads. The E5 candidate's files (`candidate.engine.obj`, `candidate.source.obj`, `source-faces.json`,
`stage-audit.json`) join the guard's hashed inputs when the audit names `e5_candidate`. Test
`test_the_e4_independent_guard_reads_back_the_chained_e3_e5_e4_candidate` (fixture root, fake `strict_guard`):
contract `e3_then_e5_then_e4_merge`, input 9, output 2, removed 9 = 1 + 4 + 4, receipt PASS.

### Output (2026-10-24, worktree root, `PYTHONPATH` = it, `-p no:cacheprovider`)

```
pytest engine/tests/test_e5_coincident.py -> 1 failed, 18 passed in 245.99s, then the corrected sheets test alone
  -> 1 passed in 13.59s (the failure was my fixture arithmetic: a flipped quad's triangles use the other diagonal, so
     the two sheets form 4 kept pairs, not 2)   (19 tests)
pytest engine/tests/test_validate_allowed_changes.py -> 7 passed in 11.93s
pytest engine/tests/test_e4_merge.py engine/tests/test_e4_growth.py -> 16 passed in 7.56s
pytest tools/tests -> 350 passed in 275.50s (0:04:35), exit 0   (348 + 2: the chained guard test and the
  run_checked_e4 allow_growth test; the chain test now runs E4 with --allow-growth and reads it from the audit)
```

### 7F commands (NOT run here)

```powershell
$env:PYTHONPATH=(Get-Location).Path
$PY='D:/PROJECTS/05-Corllenium-UC-Building-Repair-Engine/.venv/Scripts/python.exe'
& $PY -B -u tools/run_checked_e5_floor.py --root <claude run root> --floor 7F --raw-name "7th floor main infra.obj" --from-e3
& $PY -B -u tools/run_checked_e4_floor.py --root <claude run root> --floor 7F --raw-name "7th floor main infra.obj" --from-e5 --allow-growth
& $PY -B -u tools/e4_independent_guard.py --root <root> --floor 7F --raw-name "7th floor main infra.obj" --candidate <root>/e4/7F --out <root>/e4/7F-independent-guard --helper D:/PROJECTS/05-Corllenium-UC-Building-Repair-Engine/.claude/worktrees/MAIN-INFRA-CLAUDE-4F-7F-20261023/tools/main_infra_candidate.py --job-id <id> --reviewer <name> [--original-oracle]
& $PY tools/main_infra_physical_validation.py --raw "<root>/raw/7th floor main infra.obj" --reference <root>/reference/7F.json --baseline <root>/normalized/7F --qualification <root>/independent-validator/import-audit/qualification-7F.json --candidate <root>/e4/7F --materials <root>/independent-validator/preflight/materials-7F.json --out <root>/e4/7F-validation --allow coincident_backface_removed
```

(An existing `<root>/e5/7F` or `<root>/e4/7F` must be moved aside first: both runners refuse an existing output.)

### Open questions

1. An interior seam's two faces may be seen by nothing yet still carry the only coverage of a footprint between two
   solid blocks (a sealed cavity): the site judge sees nothing there and keeps the drop; the strict guard's 26 views
   see nothing there either. Whether the owner wants sealed cavities opened is not decided; the plan records every
   seam in `by_rule.interior_twins` and the evidence.
2. The 57 rolled-back E5 sites (uv 1,250) on the first run were the `uv` status the class did not yet excuse; after
   item 2 they should hold -- to be measured on the next chain run.
3. `--allow-growth` trades invisible coplanar edges for merged regions; the E4 `grew` numbers of the next run say how
   many of the 1,250 come back and what the judge does with them.

## Dashboard kinds: the per-face stage classifications (2026-10-24)

`tools/main_infra_stage_errors.py` writes, for the BEFORE model (the first given stage's input) and the AFTER model (the
last given stage's output), an errors.json in the dashboard's census shape -- `{"schema_version": 1, "n_faces": N,
"counts": {kind: n}, "faces": {kind: [triangle ids]}, "details": {...}}`, triangle ids in the OBJ face order of the model
the dashboard loads -- carrying these ten kinds beside the census's seven (flicker_diff, flicker_same, reversed, hidden,
loose, open_edges, cracks; `tools/main_infra_errors.py` in the 4F-7F worktree). It reads only saved artifacts: the E5
run dir (stage-audit.json, edit-log.jsonl, source-faces.json), the E4 run dir (region-map.json, stage-audit.json,
edit-log.jsonl) and the crack judgement. Every id is checked against the face count of the OBJ the audits name (the E5
input is the audit's `e3_candidate`, else the baseline snapshot; the E4 input the `e5_candidate`, else `e3_candidate`,
else the snapshot) and refused when out of range.

| kind | source | BEFORE ids | AFTER ids | colour proposal |
| --- | --- | --- | --- | --- |
| `backface_twin` | E5 edit log, kept remove sites whose rule is `backface_twin` | the removed faces | none (removed) | `#d94f4f` red: the solid-facing twin that went |
| `interior_seam` | E5 edit log, kept remove sites whose rule is `interior_twins` | both faces of each interior seam | none (removed) | `#8e44ad` purple: block-against-block seam |
| `two_sided_sheet` | E5 audit `engine_report.kept_pairs` with reason `both_exposed` | both faces of each kept pair | the same faces as survivors (then through E4) | `#2e86de` blue: a legitimate zero-thickness slab, kept |
| `e5_rolled_back` | E5 edit log lines with `rolled_back: true`; reasons from the check record | the site's faces | the same faces (they survive) | `#f39c12` amber: the judge refused the drop |
| `merge_region` | E4 region-map `regions[].source_faces` / `new_triangles` | the kept regions' source faces | the regions' new triangles | `#27ae60` green: re-triangulated as one surface |
| `merge_refused` | E4 audit `engine_report.refused` (region ids -> faces via the E4 input's coplanar regions, `flat_materials` from the audit) | the refused regions' faces | the same faces (kept) | `#e67e22` orange: the engine refused the merge |
| `e4_rolled_back` | E4 edit log lines with `rolled_back: true`; reasons from the check record | the site's source faces | the same faces (kept) | `#c0392b` dark red: the judge refused the merge |
| `jev_merge` | crack judgement regions with decision `merge` | every face of the region | the region's new triangles when E4 merged it, else the faces | `#1abc9c` teal |
| `jev_keep` | crack judgement regions with decision `keep` | every face of the region | the same faces | `#34495e` slate |
| `jev_unsure` | crack judgement regions with decision `unsure` (owner queue) | every face of the region | the same faces | `#f1c40f` yellow: owner decision pending |

`details`: `e5_rolled_back[face]` and `e4_rolled_back[face]` = `{site, reasons: {validator reason: samples},
stage_rolled_back}`; `merge_refused[face]` = the E4 refusal reason (`area_changed`, `off_plane`, `flipped`, `uv_lost`,
`uv_seam`, `too_large`, `mixed_material`, `grew`); `jev[face]` = `{provider, reason}` (the rule that decided, or
"rules could not say" with Jev's recorded suggestion). The judgement's ids are the E4 input's (what
`main_infra_crack_judge.py --before` read) and are carried back to the BEFORE model through the E5 survivors.

Id mapping: the edit log, the survivor map and the region map carry each stage's own input ids. E4 ids go back to the
BEFORE model through `source-faces.json` (output i = input `source_faces[i]`); everything goes forward to the AFTER model
through the survivors, then E4's `kept_source_faces` (kept face -> its position) and the kept regions'
`source_faces -> new_triangles`. A removed face has no AFTER id.

Known limit: the E5 edit log does not record the rule per face (it is in the plan's evidence, which the log drops), only
the site's `by_rule` counts in its reason text. A single-rule site is that rule; in a mixed site the coincident opposite
pairs (same three corner positions) are the interior seams and the rest take the one remaining rule; a site that still
mixes two rules is listed in `details.e5_unresolved` and classified nowhere. Persisting `evidence["rules"]` in the log
line would remove the limit.

`--with-census` runs `find_errors` on each model so one errors.json carries all seventeen kinds;
`--merge-into-before/--merge-into-after <existing>` keep the existing file's other kinds and keys, replace the stage
kinds and refuse a different `n_faces`. Tests: `tools/tests/test_main_infra_stage_errors.py` (a synthetic
E3 -> E5 -> E4 tree with a mixed E5 site, a rolled-back site per stage, a refused region and a three-decision judgement;
the real fixture chain through both runners with `--with-census`; merge-into; out-of-range refusals).

### 7F command (NOT run here; root = the 4F-7F worktree's `data/main-infra-fresh/run-claude-4f-7f-20261023`)

```powershell
$env:PYTHONPATH=(Get-Location).Path
$PY='D:/PROJECTS/05-Corllenium-UC-Building-Repair-Engine/.venv/Scripts/python.exe'
$ROOT='D:/PROJECTS/05-Corllenium-UC-Building-Repair-Engine/.claude/worktrees/MAIN-INFRA-CLAUDE-4F-7F-20261023/data/main-infra-fresh/run-claude-4f-7f-20261023'
& $PY -B -u tools/main_infra_stage_errors.py --e5 "$ROOT/e5/7F" --e4 "$ROOT/e4/7F" --judgement "$ROOT/e4/7F/crack-judgement.json" --before-out "$ROOT/e4/7F-dashboard/errors_before.json" --after-out "$ROOT/e4/7F-dashboard/errors_after.json" --with-census
```

(Drop `--judgement` when the E4 run was not judged; the BEFORE model is then `<root>/e3/7F/candidate.engine.obj`, the
AFTER model `<root>/e4/7F/candidate.engine.obj`. To fold the kinds into census files the dashboard already has, replace
`--with-census` by `--merge-into-before <its errors_before.json> --merge-into-after <its errors_after.json>`.)

### Output (2026-10-24, worktree root, `PYTHONPATH` = it, `-p no:cacheprovider`)

```
pytest tools/tests/test_main_infra_stage_errors.py -> 8 passed in 17.44s
pytest tools/tests -> 358 passed in 228.54s (0:03:48), exit 0   (350 + the 8 stage-errors tests)
```

## After real 7F chain run #2 (2026-10-24): E4 winding and twins, E5 seam visibility, check 3's deciding measure, the covered rollbacks measured

The feature commit preceding this record, plus this record. The measurements below were made READ-ONLY on the run-2
artifacts under `.claude/worktrees/MAIN-INFRA-CLAUDE-4F-7F-20261023/data/main-infra-fresh/run-claude-4f-7f-20261023`
(`e5/7F`, `e4/7F`, `independent-validator/e4-validation/7F`); nothing ran on the floor from here.

### Run #2 as reported (coordinator)

E5: by_rule backface_twin 497, interior_twins 3,738; 412 sites, 223 kept, 189 rolled back {deleted 18,191, uv 3,174,
look 1,861, replaced 80, side 62}; 20,625 -> 19,731. E4 (`--allow-growth`): regions 3,905, changed 1,860, refused
uv_seam 636 / area_changed 16 / off_plane 6 / too_large 4; 1,198 sites, 279 kept, 919 rolled back, all {covered 9,372}
(how: box 7,589, cover 1,341, touched 197); 19,731 -> 20,222. E4 independent guard PASS (holes 0, zfight_tie 2).
Validator (`--allow coincident_backface_removed`): textures PASS; nothing_deleted FAIL with deleted = replaced =
covered = overlaid = 0; problems flicker_diff 1,739, flicker_same 2,772, cracks 4,301, reversed 0 -> 36 (ids
19860-19997, appended E4 triangles); 16 interior renders 466 changed px; allowed_changes excused 16 samples.

### Measured here

1. check 3's FAIL with zero sample counters WAS THE FLOOR: `nothing_deleted.floor.status == FAIL`, `faces_measured 108`,
   `faces_failed 4` -- face 14087 (kind covered, 85 px `deleted`, direction 15), 13114 (27.1 px `covered` by appended
   triangles 19794 / 19733, probe 758), 14059 (14 px deleted), 15438 (kind removed, 7 px deleted, extra direction 326);
   lattice 7,491 faces / 1,936,028 points, candidates removed 38 / covered 70. The report never said which sub-measure
   decided.
2. E4 winding: over the 279 kept regions (1,571 new triangles), 0 new triangles wind against their source faces'
   largest-face winding and 0 regions have mixed-winding sources. The 36 `reversed` census faces lie in 26 regions of
   2 input faces -> 3-11 triangles (grown regions, `--allow-growth`), all `minecraft_concrete_white_-1`: the census's
   `reversed` is `classify_orientation(front, back)` from sampled exposure, and a grown region's many small triangles
   sample differently from its two slivers. NOT a winding flip of the merge.
3. E4 covered rollbacks: 919 sites, 8,222 charged sample faces classified against each site's region: other 5,663
   (69 %), neighbour (shares a vertex) 1,227, same-facing coplanar 681, opposite twin 472 (5.7 %), the region's own
   faces 179. 578 of the 919 sites were charged by BOUNDING BOX ALONE (`how.cover + how.touched == 0`); 341 had a
   cover or touched charge. The remaining twins are a minor cause; the box attribution is the major one.

### Changes

1. `engine/repair/engines/e4_merge.py`: the region normal is the input faces' OWN winding -- the largest face's cross
   product is the reference, agreeing faces' cross products are summed (area-weighted), never a plane fit; a region
   with a disagreeing face is refused `mixed_winding` BEFORE the `unchanged` skip, with `winding: {agreeing_area,
   disagreeing_area, faces_disagreeing}` in every record. Measured: the merge already keeps a clockwise quad clockwise,
   and `analyse_topology` never puts opposite normals in one region, so the guard is driven directly in its test and
   cannot fire from today's topology. `skip_twinned: bool = True`: the Validator's `double_layers` opposite pairs are
   read on the E4 input (as E5 reads them) and a region any input face of which still has an opposite partner is
   SKIPPED `twinned` (`report.twinned_faces`, `seconds.twins`); `skip_twinned=False` restores the old plan.
2. `engine/repair/engines/e5_coincident.py`: an interior seam is planned only when the Validator's own viewpoint set
   sees NEITHER face: `seam_view(mesh, faces)` (default: the site judge's `lattice_seen` at `DENSE_POINTS_PER_FACE`
   plus `probe_seen`, as E3-R7 / E3-R4); a seam with a seen face stays whole (`kept.seam_seen`, `points_seen` per face,
   partners kept with it); with no view and no judge no seam is planned (`kept.seam_unverified`).
   `report.interior_filtered = {seams, seen, unverified, planned}` says how many the filter took.
3. `engine/validate/checks.py`: `checks.nothing_deleted.failed_by = {samples, floor, floor_faces_failed,
   samples_failed}` names the deciding sub-measure. The class now asks EVERY sample of every removed hidden-front face
   for its twin (tested or not) and excuses from the floor each face all of whose samples lie under an exposed opposite
   twin (`allowed_changes[CBR].faces_eligible`); the sample reclassification stays limited to tested failing samples.
   Run #2 excused 16 samples on 9 faces while 497 backface twins were culled: their samples were mostly never seen, so
   never tested, so never excused, and the floor measured them.
4. Proposed, NOT implemented (engine/site_judge.py attribution): charge a `covered` sample to a cut site only when one
   of the site's NEW faces is the covering face (`how.cover` or `touched`), not by bounding box -- the E3-R8 ruling for
   remove-only sites, extended to cuts. On run #2 that would have spared 578 of the 919 rolled-back E4 regions
   (the 341 with a cover/touched charge would still roll back). The 179 self-charges (a merged triangle covering its
   own replaced slivers' samples at a depth tie) are the Validator's cover test at the tolerance and also deserve a
   look. Both need the owner's word: they loosen the judge.

Tests: `engine/tests/test_e4_winding_and_twins.py` (6: clockwise quad merges clockwise with winding evidence;
`mixed_winding` refusal driven through `merge_regions`; opposite-winding faces fall in separate single-winding regions;
`twinned` skip, the switch, a plain quad not twinned), `engine/tests/test_e5_coincident.py` (+4: unseen seam planned
with the view, a seen seam kept whole while the unseen one is planned, no view and no judge -> `seam_unverified`, the
judge supplies the view), `engine/tests/test_validate_allowed_changes.py` (`failed_by` on the strict and the passing
case, `faces_eligible == 2`).

### Output (2026-10-24, worktree root, `PYTHONPATH` = it, `-p no:cacheprovider`)

```
pytest engine/tests/test_e4_winding_and_twins.py engine/tests/test_e4_merge.py engine/tests/test_e4_growth.py
  -> 2 failed, 20 passed in 13.47s (the two mixed-winding tests expected a mixed REGION, which the topology never
     builds), then engine/tests/test_e4_winding_and_twins.py alone, rewritten -> 6 passed in 10.23s
pytest engine/tests/test_e5_coincident.py -> 1 failed, 21 passed in 192.85s (my assertion: the unseen seam is still
  planned while the seen one stays), corrected test -> passed (22 tests)
pytest engine/tests/test_validate_allowed_changes.py engine/tests/test_validate_checks.py -> 1 failed, 84 passed in
  199.08s (my test read `allowed` before assigning it), corrected test -> passed; the two corrected tests together
  -> 2 passed in 7.25s
pytest tools/tests -> 358 passed in 213.18s (0:03:33), exit 0
```

### 7F commands (NOT run here; move an existing `<root>/e5/7F`, `<root>/e4/7F` aside first)

```powershell
$env:PYTHONPATH=(Get-Location).Path
$PY='D:/PROJECTS/05-Corllenium-UC-Building-Repair-Engine/.venv/Scripts/python.exe'
& $PY -B -u tools/run_checked_e5_floor.py --root <claude run root> --floor 7F --raw-name "7th floor main infra.obj" --from-e3
& $PY -B -u tools/run_checked_e4_floor.py --root <claude run root> --floor 7F --raw-name "7th floor main infra.obj" --from-e5 --allow-growth
& $PY -B -u tools/e4_independent_guard.py --root <root> --floor 7F --raw-name "7th floor main infra.obj" --candidate <root>/e4/7F --out <root>/e4/7F-independent-guard --helper D:/PROJECTS/05-Corllenium-UC-Building-Repair-Engine/.claude/worktrees/MAIN-INFRA-CLAUDE-4F-7F-20261023/tools/main_infra_candidate.py --job-id <id> --reviewer <name> [--original-oracle]
& $PY tools/main_infra_physical_validation.py --raw "<root>/raw/7th floor main infra.obj" --reference <root>/reference/7F.json --baseline <root>/normalized/7F --qualification <root>/independent-validator/import-audit/qualification-7F.json --candidate <root>/e4/7F --materials <root>/independent-validator/preflight/materials-7F.json --out <root>/e4/7F-validation --allow coincident_backface_removed
```

What to read on run #3: E5 `interior_filtered` (how many of the 1,869 seams the judge's viewpoints see), E5 rolled-back
reasons (expect the `deleted` 18,191 to fall), E4 `skipped.twinned` and the rolled-back `how` split (the box share is
the case for the attribution ruling), `nothing_deleted.failed_by` and `allowed_changes[CBR].faces_eligible`.

### Open questions

1. The seam view costs the judge's lattice (36 points per seam face) and probes over every seam face per plan: on 7F
   that is 3,738 faces; `seconds.seam_view` records it.
2. `skip_twinned` runs `double_layers` (26 views) once more inside E4; `seconds.twins` records it. E5's own pair list
   could be handed through the audit instead.
3. The floor's 4 failing faces on run #2 (7-85 px) are real pixel losses the samples did not catch; whether E5 or E4
   caused each (faces 14087, 13114, 14059, 15438 of the baseline) is for the next run's `failed_by` and
   `floor.failing` with the chained face maps.
4. The covered-attribution ruling (change 4) is proposed only; it is the judge's rule and the owner's call.

## After real 7F chain run #3: the owner's flag -> site -> replay loop (2026-10-24)

The feature commit preceding this record, plus this record. Fixture chain only; no real-floor run from here.

### Run #3 as reported (coordinator, on 5912516)

E5 20,625 -> 18,708 (interior_filtered seams 2,150 / seen 448 / planned 1,702; 350 sites kept, 49 rolled back:
deleted 64, replaced 15). E4 `--allow-growth` 18,708 -> 19,009 (regions 3,429, changed 1,688, skipped twinned 676 /
unchanged 639, refused uv_seam 433; 562 sites, 216 kept, 346 rolled back all covered: how box 2,069 / cover 756 /
touched 90). E4 guard PASS (holes 0, grown 0). Validator `--allow coincident_backface_removed`: textures PASS, reversed 0,
flicker_diff 852, flicker_same 2,089, cracks 4,216, hidden 3,770; nothing_deleted FAIL by the floor only: faces 8384
(covered 196.8 px, probe 924), 14087 (covered 85 px, direction 15), 16674 (covered 61 px, direction 13), 14059 (covered
14 px, direction 2), 15438 (removed 7 px, extra direction 326). Interior gate 466 px, same two views as run #2. Against
run #2: the `deleted` 18,191 fell to 64 (the seam view), `reversed` 36 -> 0, box charges 7,589 -> 2,069.

### The loop

1. `tools/main_infra_e4_replay.py --candidate <e4 dir> --validation <validation.json> [--interior <renders dir>] --out
   <json>`: for each failing floor face (baseline ids) the responsible regions are the one whose NEW triangles include a
   `covering_faces` entry (`how: covering_face`), for `removed` the one whose source faces (the receipt's
   `e4_region_source_faces`, baseline ids, carried in `validation.json` as `physical_precision`) contain it
   (`source_face`), and every region whose new triangles lie within the depth tolerance of the face's plane with an
   overlapping footprint (shapely, `coplanar_overlap`). The baseline snapshot (`physical_precision.before`) gives the
   geometry; its positions must equal the candidate's. Output `{regions, reasons: {region: [{face, kind, pixels,
   viewpoint, how, site}]}, unexplained, validation_sha256, region_map_sha256, depth_tolerance_in}`; a failure no region
   explains is listed under `unexplained` and the command returns 2.
2. `tools/run_checked_e4_floor.py --exclude-regions <json>`: the plan is every `e4_topology` region of the input minus
   the listed ids (intersected with a crack judgement when both are given); the audit records `excluded_regions`,
   `exclude_regions_file`, `exclude_regions_sha256`, and the file is copied into the candidate as
   `exclude-regions.json`. The binding and the guard need no change: an excluded region is `not_allowed` in the plan and
   its slivers are kept source faces (test: the excluded candidate binds with `e4_merged_regions 0`).
3. `tools/run_e4_replay_loop.py --root --floor --raw-name [--rounds 3] [--allow <class>]... [--no-allow-growth]
   --helper <tools/main_infra_candidate.py> --job-id --reviewer [--expected-revision] [--interior-poses <json>
   --interior-px-max 60]`: per round k, E4 (`--from-e5 --allow-growth [--exclude-regions]`) moved to
   `<root>/e4/<F>-round<k>`; the E4 independent guard (`independent-validator/e4-guard/<F>-round<k>`), a PASS recorded
   into the round's audit as `guard.passed` with the receipt's path and hash (the Validator's binding requires it; the
   loop is the reviewer's hand here); the Validator (`independent-validator/e4-validation/<F>-round<k>`). Check 3 PASS
   stops `pass` and copies the round to `<root>/e4/<F>` for the chain; otherwise the failures are mapped
   (`<F>-round<k>-explained.json`), an unexplained one stops the loop (`unexplained`), explained regions join the
   exclusions (`<F>-round<k+1>-exclude.json`) and E4 reruns. Other stops: `guard_failed`, `validator_failed`,
   `no_new_exclusions`, `rounds_exhausted`. `<root>/e4/<F>-replay-summary.json` records every round (candidate, guard,
   validation, nothing_deleted, failed_by, explained / unexplained, exclusions) and the stop reason. INTERIOR: this
   worktree holds no renderer (render_pair / the contact sheet live in the 4F-7F worktree), so `--interior-poses`
   records `interior: unavailable` and stops the loop with `interior_unavailable`; with an injected `render_interior`
   a view over `--interior-px-max` is recorded `unmapped` (the bbox-through-saved-camera projection is not implemented)
   and stops the loop `interior_unmapped`.

Tests `tools/tests/test_main_infra_e4_replay.py` (7, fixture chain, guard and Validator injected): three failure kinds
mapped to the one region by covering face, geometry and source face; an unexplained failure (the far facade, coplanar but
not overlapping) refused and listed; the runner's exclusion (audit, copied file, hash, `not_allowed 1`, the candidate
binds with 0 merged regions); the loop excludes the covering region and passes on round 2 (round dirs, exclusion file,
guard receipt in the audit, summary, final round copied to `e4/<F>`); an unexplained failure stops it after round 1;
interior poses without a renderer stop it; the CLI parses.

### Output (2026-10-24, worktree root, `PYTHONPATH` = it, `-p no:cacheprovider`)

```
pytest tools/tests/test_main_infra_e4_replay.py -> 1 failed, 6 passed in 35.58s (my test helper overwrote the guard
  receipt the loop had recorded), corrected -> 1 passed in 6.89s   (7 tests)
pytest tools/tests -> 365 passed in 210.36s (0:03:30), exit 0   (358 + 7)
```

### 7F command for the loop (NOT run here; move an existing `<root>/e4/7F` aside first)

```powershell
$env:PYTHONPATH=(Get-Location).Path
$PY='D:/PROJECTS/05-Corllenium-UC-Building-Repair-Engine/.venv/Scripts/python.exe'
& $PY -B -u tools/run_e4_replay_loop.py --root <claude run root> --floor 7F --raw-name "7th floor main infra.obj" --rounds 3 --allow coincident_backface_removed --helper D:/PROJECTS/05-Corllenium-UC-Building-Repair-Engine/.claude/worktrees/MAIN-INFRA-CLAUDE-4F-7F-20261023/tools/main_infra_candidate.py --job-id <id> --reviewer <name> --expected-revision <sha>
# one round by hand instead:
& $PY tools/main_infra_e4_replay.py --candidate <root>/e4/7F --validation <root>/independent-validator/e4-validation/7F/validation.json --interior <root>/independent-validator/e4-interior/7F/renders --out <root>/e4/7F-exclude.json
& $PY -B -u tools/run_checked_e4_floor.py --root <root> --floor 7F --raw-name "7th floor main infra.obj" --from-e5 --allow-growth --exclude-regions <root>/e4/7F-exclude.json
```

On run #3's own validation the replay would map faces 8384, 14087, 16674, 14059 (covered: their `covering_faces` name
the appended triangles) and 15438 (removed: its region's source faces) -- to be confirmed by running the mapper on the
artifacts, which this worker did not do.

### Open questions

1. The loop records the guard's PASS into the audit itself (`guard.recorded_by`); until now the reviewer did that by
   hand. The owner may want the hand step kept.
2. Excluding a region drops its merge entirely; a region failing by one sliver's 7 px could instead be split or
   re-judged. The replay keeps the whole region out.
3. The interior gate (466 px in two views along the trim band edges) stays outside this loop until the renderer and
   the camera projection are available here.
