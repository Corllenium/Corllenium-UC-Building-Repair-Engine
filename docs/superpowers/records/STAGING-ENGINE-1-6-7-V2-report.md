# MAIN INFRA floors 6, 7 and 1: engine run on FIXED-CUTS-V2, staged into ENGINE-STAGED

Brief: [briefs/STAGING-ENGINE-1-6-7-V2.md](briefs/STAGING-ENGINE-1-6-7-V2.md). Queue job `STAGING-ENGINE-1-6-7-V2`,
claimed by `claude-vertex-opus`. Artifacts live in
`D:/PROJECTS/04-Corllenium-Building-Model-Repair/02_STAGING_DEVELOPMENT/MAIN_INFRA-ALL-FLOORS-20261019/`.

## Setup (2026-10-19)

- Runner `run_engine_on_7_floors.py` sha256 `9b84a394…23bb` (the same file the 4-5 run used). Engine at
  `92fce36` plus the uncommitted `engine/fixes/building_repair.py` (sha256 `66a94b57…f94e2`); every hash is in
  `engine-7floors-v2/input-provenance.json`. No engine or runner edits.
- Runner regression suite:

```text
.venv/Scripts/python.exe -m pytest test_run_engine_on_7_floors.py -q -p no:cacheprovider
..........................                                               [100%]
26 passed in 10.99s
```

- The requested input is re-saved by a live Blender GUI session (PID 26224 has REVIEW.blend open; V2 and REVIEW
  were saved together at 20:42, 20:48, 20:51, 20:53 and 21:01). The runner opens `--input` twice (export, then
  stage-back), so the run reads a frozen copy made with a before/after hash check:

```text
src_before=10ceb8d75c33022ca4b400de1eef354ba72052088b03b57613f8289a49d9e9d6 frozen=10ceb8d75c33022ca4b400de1eef354ba72052088b03b57613f8289a49d9e9d6 src_after=10ceb8d75c33022ca4b400de1eef354ba72052088b03b57613f8289a49d9e9d6 mtime=2026-10-19 21:01:56.549701800 +0800 / 2026-10-19 21:01:56.549701800 +0800 size=20969316
```

- Launched hidden at 21:08:47 (orchestrator PID 41992), logs `engine-7floors-v2/run.log` and `run.err.log`:

```text
"D:/PROJECTS/05-Corllenium-UC-Building-Repair-Engine/.venv/Scripts/python.exe" run_engine_on_7_floors.py \
    --floors 6,7,1 --input MAIN-INFRA-ALL-FLOORS-FIXED-CUTS-V2.frozen-210156.blend \
    --output-blend MAIN-INFRA-ALL-FLOORS-ENGINE-STAGED.blend --work-dir engine-7floors-v2 --max-commit-wait 7200
```

  `--max-commit-wait 7200` only lets the runner wait longer (default 1800 s) for its 3,000 MB commit headroom
  before each step. Three other engine runs share the machine (2-3, 4-5, 6-7), and the first log line was:

```text
[21:08:49] blender export: only 1756 MB of commit free on the machine (need 3000); waiting up to 7200 s
```

## Export (21:24:55 - 21:24:59)

```text
[21:24:55] blender export: continuing with 3109 MB of commit free
EXPORTED 1F: 16,354 tris, 12,287 verts, 44 materials, 15 objects
EXPORTED 6F: 30,518 tris, 23,760 verts, 28 materials, 140 objects
EXPORTED 7F: 16,680 tris, 13,267 verts, 17 materials, 133 objects
EXPORT_OK
```

`export.json` names the frozen copy as `input_blend`. Caps among the objects: 1F 10, 6F 133, 7F 130. The export
log's `ModuleNotFoundError: No module named 'httpx'` is the `higgsfield_blender` add-on failing at Blender start
(the peer runs' export logs have it too); it does not touch the export. The runner runs the floors in sorted order:
1F, then 6F, then 7F.

## Results

No floor pass is claimed: a guard verdict is the runner's 26-view orthographic guard, not the Validator of
AGENTS.md §6. 6F and 7F pending.

### 1F (21:25:00 - 21:32:56)

```text
[21:25:00] MAIN_INFRA_1F: 16,354 input triangles, 12,287 vertices, 17 materials
[21:30:41] MAIN_INFRA_1F: engine done in 340s -> 7,217 triangles (hidden/liners 4292, soffits 554, notches 0, flipped 0, beige tile cover restored on 132 faces)
[21:32:56] MAIN_INFRA_1F: 26-view guard FAILED in 135s: holes 186, grown 0, material 46917, moved_other 0, moved_same_flat 3116, flicker 149, failing views 26
```

- Report invariants: area 6,670,407 -> 5,430,219 sq in (ratio 0.814, non-increasing); bbox unchanged (max delta
  0.0 in); material list unchanged, 12 of 17 still used.
- Guard: depth tolerance 0.15 in, border shift 0.15 in, flicker cap 0.0001. Every view fails, with 177 to 4,673
  failing pixels per view. In total 50,246 of 3,774,880 model pixels (1.3 %) fail, and 93 % of those are material
  changes.
- For comparison, the earlier 1F run on REVIEW.blend (`engine-7floors/1F`, 17,071 input triangles) had holes 27,
  material 29,559 and moved_same_flat 3,660.

Output files, checked with `checks/verify_fixed_outputs.py` (a byte copy of the 4-5 run's checker, sha256 `4657f76a…d663`):

```text
1F: files FAIL
  fixed.obj  16,354 -> 7,217 tris, 5,161 verts, 12 materials, area ratio 0.814076, bbox delta 0.0 in, zero-area 0, same-dir duplicates 14, opposite pairs 4, verts not in input 412 (492 faces)
  ngon.obj   3,946 faces (1,398 n-gons, 2,548 triangles, max 45 corners), total area diff 2.21e-07, vector 1.78e-16, planarity max 0.0384 in, read_obj refuses n-gons True
             replay: 3,946 lines -> 7,217 rows (1,424 ring lines over 4,695 rows, 21 decided by geometry); polygons off >1e-4: 3 area / 0 vector (worst 0.0 sq in, outline drift 0.0 in), >1%: 1; mixed-material polygons 10 (1475.429 sq in)
  ERROR   ngon: 1 polygons whose area or vector area differs from their fixed.obj rows by more than 1% (coverage or winding)
  warning fixed: 14 same-direction coincident duplicate faces (same three corner positions)
  warning ngon: 10 polygons carry one material over fixed.obj triangles of another (21 triangles, 1475.429 sq in)
```

- **The ERROR is n-gon 2418.** It is a vertical sliver 0.03-0.05 in wide and 39.2 in tall (z 1385.83-1425.0). The
  n-gon has 5 corners and an area of 1.239 sq in; its triangles add to 1.268 sq in.
  - In the sliver's plane, its three `.fixed.obj` triangles tile the ring exactly: union 1.2387 = ring 1.2387, no
    overlaps (`checks/inspect_ngon_polygon.py`).
  - The corners sit up to 0.0038 in off one plane, which is below the 0.01 in print step. So the triangles' 3D
    areas add to 1.2676 while their vector area is 1.2387, and the checker's vector-area difference is 0.0.
  - Coverage and winding agree. The 2.3 % comes from comparing the 3D areas of triangles that are not quite in one
    plane.
- **Mixed materials:** 10 n-gons (1,475 sq in) carry one material over triangles that `.fixed.obj` gives another.
  All of them pair FLOOR_TILES_BEIGE with a building material. The runner writes both files after
  `restore_tile_cover` has re-materialed 132 triangles, and the n-gons come from the engine's rings, built before
  that step. Staging reads `.fixed.obj`, so the staged .blend follows the triangle file.

Visual pass, `1F/guard/` (each image is BEFORE | AFTER | DIFF; red = hole, material change or moved surface;
amber = tolerated):

- `guard_-z` (looking down): AFTER loses the dark back-facing patches BEFORE showed: three rectangles mid-left and a
  hatched triangle fan in the lower-right corner. DIFF is red along the lower-right block's edges, with a few
  slivers mid-plan.
- `guard_+z` (looking up from below): AFTER shows a new light triangle, about 40 x 60 px, in the lower middle of
  the plan, with thin slivers fanning left. DIFF marks it red.
- `guard_fail_10` (level, along -y): a red cluster at the left end of the elevation and a red line along its base.
- `guard_fail_20` (oblique, from above): red clusters at the stair and lift tower at the right end, and thin red
  slivers across the middle floors. AFTER has a long thin light triangle across the corridor floor beside the lower
  stair that BEFORE lacks.

The source V2 .blend was saved again at 21:26:50 (23,337,754 bytes, sha256 `47ca5bcc…`). This run stays on the
21:01:56 copy.
