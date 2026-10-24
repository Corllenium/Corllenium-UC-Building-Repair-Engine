# MAIN-INFRA-CLAUDE-4F-7F-20261023 — Claude Code repairs fresh MAIN INFRA floors 7F 6F 5F 4F

Owner decision 2026-10-23 (brief: `MAIN-INFRA-FLOOR-OWNERSHIP-20261023.md`): Codex owns 1F-3F, Claude Code owns
4F-7F, same engine, disjoint outputs. Owner acceptance bar for the repo 03 copy (chat, 2026-10-23 18:04 +08): a
candidate that passes invariants, the strict 26-view guard, textures and visible coverage is archived in 04 and
copied into 03 as a labelled candidate even while the signed flicker/crack targets fail; numbers travel with it.
Nothing here is acceptance.

Worktree `.claude/worktrees/MAIN-INFRA-CLAUDE-4F-7F-20261023`, branch `claude/MAIN-INFRA-CLAUDE-4F-7F-20261023`
(from `codex/main-infra-clean-20261023` 12ebb6d). Run root `data/main-infra-fresh/run-claude-4f-7f-20261023`
(frozen from Codex's hash-verified raw copy, same revision `7b2f7451…6511`, 36 files). Progress file
`data/main-infra-fresh/current-upper.json`, published only under the dashboard key `freshMainInfraUpper`
(`tools/publish_upper_status.py`); Codex's `current.json` and `freshMainInfra` are never written.

## Tools added on this branch
- `tools/main_infra_candidate.py`, `tools/main_infra_review.py`: `--floor` accepts all seven fresh floors.
- `tools/main_infra_qualify.py`: qualification-<F>.json, import-audit-<F>.json, materials-<F>.json from saved artifacts
  (hashes, render-pair PNG readback split into RGB and alpha, `engine.campus.materials.build_materials`). Reproduces
  Codex's reviewer-made 4F files byte for byte (test).
- `tools/run_checked_e3_floor.py`: Codex's 1F checked-E3 launch, parametrized; runs with the E3 worktree on PYTHONPATH.
- `tools/e3_independent_guard.py`, `tools/e3_camera_qualification.py`, `tools/blender/main_infra_render_pair.py --poses`:
  the 1F reviewer scripts without hard-coded floor/run/materials hash; interior gate = 16 certified walking poses
  (63 in eye height, >83 in headroom) from the Validator's `interior_probes()`.
- `tools/publish_upper_status.py`, `tools/publish_upper_evidence.py`, `tools/archive_upper_floor.py` (04 record + export,
  03 copy under `Repaired/Main-Infrastructure/Floor/Model-Floor_0N` so CampusModelImporter keeps scale 1).
- Tests: `tools/tests/test_main_infra_floor_choices.py`, `test_main_infra_qualify.py`, `test_publish_upper_status.py`,
  `test_archive_upper_floor.py`; full `tools/tests` suite 185 passed before the engine runs.

## Measured results

### 7F (2026-10-23)
| Step | Result |
|---|---|
| Reference / normalize | 13,529 polygons → 26,152 triangles, 0 corner moves, Blender 5.1.2 |
| Import qualification | PASS: source renders 0/30 px; engine-frame 917 RGB px, 0 alpha (one 1-px-wide interpolation wedge in eye_1) |
| Duplicate-only candidate | 0 exact duplicates, guard PASS (28 s); Validator textures PASS, coverage PASS, signed FAIL: flicker_diff 4518, flicker_same 7091, cracks 5429, hidden 10,988 |
| Checked E3 | 26,152 → 20,625 (5,527 removed), 1,319 sites, 1,227 kept, 92 rolled back, site check first FAIL (55) → final PASS, 1,993 s |
| Independent strict-26 guard | PASS: holes 0, material_changed 0, grown 0, zfight_tie 2 (`independent-validator/e3-guard/7F/independent-guard.json`) |
| Interior gate | fixed eye_1/eye_3 sit 0.10 m above a floor with 0.5 m clearance (cavity) → disqualified; 16 certified poses: 14 identical, one 1-px wall seam (51 px, grey 176→169), one floor-edge pixel; alpha 0 |
| Validator on E3 | FAIL on signed targets, textures PASS, nothing deleted PASS: flicker_diff 2310, flicker_same 3289, cracks 4705, hidden 5461, open_edges 4279→6432 (989 s) |
| Archived | 04 `03_REPAIR_RECORDS/MAIN_INFRA_MINECRAFT_20261023/upper-floors/7F/`, `Exports/Repaired-Buildings-20261023-fresh/ByBuilding/Main-Infrastructure/Model-Floor_07/`; 03 `Assets/Models/Campus/Repaired/Main-Infrastructure/Floor/Model-Floor_07/` (36 × 9 × 45 m, Y-up); Z mirror `MAIN INFRUSTRUCTURE - FIXED/7F/` |

Dashboard state 7F: `blocked`, evidence under `/models/main-infra/<rev>/7F/main-infra-claude-4f-7f-20261023/evidence/`.

### 6F (2026-10-23)
| Step | Result |
|---|---|
| Duplicate-only candidate | 0 exact duplicates, guard PASS (63 s) |
| Checked E3 | first attempt died with `_ArrayMemoryError` under four concurrent engine workers; rerun alone: 34,862 → 27,108 (7,754 removed), 1,497 sites, 1,319 kept, 178 rolled back, 2,990 s |
| Independent strict-26 guard | PASS: holes 0, material_changed 0, grown 0 |
| Interior gate | 16 certified poses (1,459 probes): 3 changed px total |
| Validator on E3 | FAIL on signed targets, textures PASS, nothing deleted PASS: flicker_diff 6918→3236, flicker_same 9922→4934, cracks 7480→6659, hidden 15,518→7,763 |
| Archived | 04 upper-floors/6F + Model-Floor_06; 03 Floor/Model-Floor_06; Z mirror 6F; Blender library 7F+6F |

### 5F (2026-10-24)
| Step | Result |
|---|---|
| Duplicate-only candidate | 0 exact duplicates; default Embree guard false-flagged 1.2 M moved px on an unchanged mesh, float64 oracle guard PASS (21 min) |
| Checked E3 | 56,368 → 38,113 (18,255 removed), 2,331 kept, 36 rolled back, 7,773 s |
| Independent strict-26 guard | PASS with `--original-oracle` (Embree default again false-flagged); holes 0, material_changed 0, grown 0 |
| Interior gate | 16 certified poses: 2 changed px |
| Validator on E3 | FAIL on signed targets, textures PASS, nothing deleted PASS: flicker_diff 14412→4976, flicker_same 16317→6500, cracks 12985→10623, reversed 0→1, hidden 29,067→10,810 (3,733 s) |
| Archived | 04 upper-floors/5F + Model-Floor_05; 03 Floor/Model-Floor_05; Z mirror 5F; Blender library 7F+6F+5F |

### 4F (2026-10-24)
| Step | Result |
|---|---|
| Duplicate-only candidate | 0 exact duplicates, float64 oracle guard PASS (29 min) |
| Checked E3 | 78,160 → 52,865 (25,295 removed), 3,053 kept, 266 rolled back, 14,940 s |
| Independent strict-26 guard | PASS with `--original-oracle`; holes 0, material_changed 0, grown 0 |
| Interior gate | 16 certified poses: 5 changed px |
| Validator on E3 | FAIL on signed targets, textures PASS, nothing deleted PASS: flicker_diff 21701→8868, flicker_same 24737→11223, cracks 17688→14425, hidden 45,967→20,672 (5,151 s) |
| Archived | 04 upper-floors/4F + Model-Floor_04; 03 Floor/Model-Floor_04; Z mirror 4F; Blender library 7F+6F+5F+4F |

- Import qualification PASS: 6F 253 RGB px / 0 alpha; 4F 190 / 0 (matches Codex's pilot); 5F refused at 512 px on one
  silhouette-edge pixel, re-rendered at 1024 px: 857 RGB px / 0 alpha → PASS (512 px record kept as `refused-512px-*`).
- 6F duplicate-only candidate: 0 duplicates, guard PASS; checked E3 running. 5F candidate running. 4F queued.

## Known limits
- Signed targets (flicker/cracks = 0) are not met by E3 alone on any floor so far (Codex 1F, Claude 7F). E3 removes
  roughly half of flicker and hidden faces; cracks barely move. The remaining defects need a different, guarded pass.
- Interior gate on 7F is not the exact zero Codex reached on its 1F rerun; 52 px across 16 views, no holes, recorded.
- Codex's live-site uploader rebuilds the status file without `freshMainInfraUpper`; the live page needs the merged
  dashboard build (repo 02 branch `claude/main-infra-fresh-live-20261023`, 6ba80fd) and a separate upload of this key
  and the `models/main-infra/.../main-infra-claude-4f-7f-20261023/` previews.

## E4 coplanar-merge trial on 7F (2026-10-24, branch claude/MAIN-INFRA-E4-MERGE-20261023)
Input: 7F E3 candidate (20,625 triangles). 1,243 coplanar regions; a full merge would give 7,339 triangles.
Site judge: first pass 1,096 failing (textures covered 194, nothing_deleted covered 194), confirm PASS with 275 kept
sites and 968 rolled back, every rollback reason `covered`; output 21,116 triangles (123 kept regions grew, 2 faces →
8-14 triangles). Wall 15,060 s. Renders E3 vs E4: at most 143 px per view. Conclusion: coincident twin layers (the
flicker defects) block the merge because the merged triangle covers the twin's samples; a coincident-layer culling
stage (E5) must run before E4, and E4 must refuse regions that grow. Candidate kept at `e4/7F/` as evidence only.

## E5 trial on 7F and owner decision (2026-10-24 05:15 +08)
E5 (coincident-layer cull, same-facing only) on the 7F E3 candidate: double_layers 4,783 pairs, all opposite-facing,
0 same-facing → 0 edits (16 s). Error census on that candidate: 5,556 flicker faces, 4,974 of them also `hidden`
(128-direction census): back-to-back coincident sheets, the solid-facing twin lying on its visible twin. E3 never
proposes them (shared-plane depth tie makes their samples "seen"); E5 skipped them by the opposite-facing rule.
Owner decision (chat): the engine may remove the solid-facing twin regardless of look, with an explicit, opt-in
Validator allowed-change class `coincident_backface_removed` (strict default unchanged). Implementation on branch
`claude/MAIN-INFRA-E4-MERGE-20261023`. The direct E4 run started from the unchanged E5 candidate was stopped.

## Stage 2 chain #2 on 7F (2026-10-24 07:00-09:30 +08, E4-MERGE branch 614794e)
E5 (backface_twin 497 + interior_twins 3,738 planned; 412 sites, 223 kept, 189 rolled back: deleted 18,191, uv 3,174,
look 1,861) 20,625 → 19,731. E4 --allow-growth (3,905 regions, 1,860 changed, refused uv_seam 636; 1,198 sites, 279 kept,
919 rolled back all `covered`) 19,731 → 20,222. E4 independent guard PASS (holes 0, zfight_tie 2). Validator with
`coincident_backface_removed`: textures PASS; nothing_deleted FAIL with all counters zero (bug under investigation);
flicker_diff 1,739, flicker_same 2,772, cracks 4,301 (better than E3-only 2,310 / 3,289 / 4,705); reversed 0 → 36, all
E4-appended triangles (winding bug). 16 walking-height interior pairs: 466 px (E3-only: 52). Not published.
Dashboard: stage kinds exported in the E3-candidate id space and attached to the published 7F candidate errors.json
(backface_twin 382, interior_seam 512, two_sided_sheet 6, e5_rolled_back 3,341, merge_region 1,080, merge_refused 1,145,
e4_rolled_back 3,170). 6F E5: 27,108 → 25,809 (374 kept, 242 rolled back).
