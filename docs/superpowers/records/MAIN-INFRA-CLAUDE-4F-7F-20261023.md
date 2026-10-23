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

### 5F, 4F
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
