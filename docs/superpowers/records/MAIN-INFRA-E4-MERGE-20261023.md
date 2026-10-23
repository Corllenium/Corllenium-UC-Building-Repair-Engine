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
   `require_guard=False` when called from the guard itself. Left as asked.

## Follow-up (2026-10-24): the E4 binding and the E4 independent guard

- `tools/main_infra_e4_binding.py: bind_saved_e4(*, candidate, audit, before_engine, after_engine, before_source,
  after_source)`, modelled on `bind_saved_e3`: `cleanup_mode` in {`e4_merge_only` (`executed_stages == ["E4"]`),
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

Commands (worktree root, `PYTHONPATH` = it):

```powershell
& $PY -m pytest tools/tests/test_main_infra_e4_binding.py tools/tests/test_e4_independent_guard.py -q -p no:cacheprovider
# the independent guard on an E4 candidate (the audit's guard.passed must be set first; see open question 6):
& $PY -B -u tools/e4_independent_guard.py --root <root> --floor 7F --raw-name "7th floor main infra.obj" --candidate <root>/e4/7F --out <root>/e4/7F-independent-guard --helper D:/PROJECTS/05-Corllenium-UC-Building-Repair-Engine/.claude/worktrees/MAIN-INFRA-CLAUDE-4F-7F-20261023/tools/main_infra_candidate.py --job-id <id> --reviewer <name> [--original-oracle]
# the Validator on it (BEFORE = baseline, AFTER = <root>/e4/7F):
& $PY tools/main_infra_physical_validation.py --raw "<root>/raw/7th floor main infra.obj" --reference <root>/reference/7F.json --baseline <root>/normalized/7F --qualification <root>/independent-validator/import-audit/qualification-7F.json --candidate <root>/e4/7F --materials <root>/independent-validator/preflight/materials-7F.json --out <root>/e4/7F-validation
```
