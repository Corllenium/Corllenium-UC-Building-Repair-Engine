# Phase 2E Fix Pipeline Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or
> superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Turn a snapshot of a sidewalk OBJ into a fixed OBJ whose inside is removed and whose flat surfaces are
single clean faces, with a guard that proves the outside did not change.

**Architecture:** Pure `engine\` library plus a thin CLI. Order is fixed by evidence: drop zero-area faces ->
exposure (double-sided ray casting) -> remove hidden faces under guard feedback -> optionally remove reviewed
slit faces -> re-analyse -> merge planar regions over **existing vertices only** -> final guard against the
original. Every step reports numbers. Runs before the dashboard (user decision 2026-09-21): the dashboard later
drives this same pipeline, with review in the browser instead of CLI flags.

**Tech Stack:** Python 3.12, numpy, shapely >= 2.1, trimesh + embreex (ray casting only), pillow, pytest.

**Spec:** `docs\superpowers\specs\2026-09-21-uc-model-fixer-design.md`.
**Evidence (every number below comes from here):** `docs\spike\2026-09-21-phase0-results.md`, scripts `spike\04`, `10`, `11`, `13`.

## Global Constraints

- `engine\` imports nothing from `api\`, `spike\`, fastapi, sqlalchemy. `trimesh` and `embreex` are imported only
  inside `engine\rays\`.
- **Occlusion is double-sided by default**: every non-degenerate face blocks and is visible from both sides.
  This matches SketchUp and the Unity project (`_Cull = 0`). A `sided="single"` switch may exist, never as default.
- **Vertices are never moved and never invented.** Merged regions are re-triangulated over existing welded
  vertices. If a union produces a coordinate that maps to no existing vertex, that region is left untouched and reported.
- **Blocked operations** stay blocked: tolerance weld, decimate, fill holes, make manifold, `select_interior_faces`.
- Hidden faces (exposure exactly 0) may be removed automatically **only** after guard feedback reaches 0 damage.
  Slit faces (0 < exposure < threshold) are genuinely visible: removed only when explicitly accepted.
- Hard invariants after every apply: region area must not grow (relative tolerance 1e-6), material count
  unchanged, bounding box identical, guard verdict pass.
- Determinism: fixed Fibonacci directions, fixed barycentric samples, no random numbers in production code.
  Two runs on the same input give byte-identical output OBJ.
- Tolerances follow the per-axis quantum. Plane tolerance `1.5 * sum(|n_i| * q_i)`. Collinearity tolerance for
  dropping a border vertex: distance to the chord <= `1.5 * max(q)`.
- Commands: `.venv\Scripts\python.exe -m pytest -q`. TDD. Commit trailer `Co-Authored-By: Claude Fable 5.1 <noreply@anthropic.com>`.
- Output goes to `data\output\` only. Snapshots are never modified.

## File Structure

| File | Responsibility |
|---|---|
| `engine\rays\caster.py` | `RayCaster` protocol, `EmbreeCaster`, `BruteCaster` (numpy oracle) |
| `engine\vis\exposure.py` | directions, samples, per-face exposure, classes |
| `engine\guard\views.py` | orthographic first-hit images, the 26 views |
| `engine\guard\compare.py` | pixel verdicts, `GuardReport`, guard feedback |
| `engine\guard\render.py` | PNG before / after / diff for humans |
| `engine\fixes\remove.py` | delete faces, keep provenance |
| `engine\fixes\merge.py` | planar region kernel |
| `engine\fixes\pipeline.py` | `fix_object`, invariants, `FixResult` |
| `engine\cli.py` | `fix` and `preview-data` commands |
| `engine\tests\fixtures\build.py` (modify) | new fixtures with known answers |

---

### Task 1: Ray casters

**Files:** Create `engine\rays\__init__.py`, `engine\rays\caster.py`, `engine\tests\test_caster.py`. Modify `pyproject.toml`
(add `trimesh>=4.5`, `embreex>=4.4` to dependencies).

**Interfaces — Produces:**
`class RayCaster(Protocol)`: `any_hit(origins (R,3), directions (R,3)) -> np.ndarray[bool]`,
`first_hit(origins, directions) -> tuple[np.ndarray[int64] tri (-1 = miss), np.ndarray[float64] t (inf = miss)]`.
`EmbreeCaster(positions (V,3) float64, faces (F,3))` and `BruteCaster(positions, faces)` both implement it.
`tri` indexes into the `faces` passed in. Callers recentre positions before constructing (float32 inside embree).

`BruteCaster` is the Moller-Trumbore implementation from `spike\04_front_hit_oracle.py` (`brute`), generalised to
per-ray directions, chunked by 256 rays, float64, hit when `t > 1e-9`.

- [ ] **Step 1: failing tests** — unit cube fixture: ray from (5,5,20) down hits top at `t = 10`; ray missing the cube
  returns `tri == -1`, `t == inf`; `any_hit` agrees with `first_hit >= 0`; and the oracle test: 2,000 deterministic rays
  (`np.random.default_rng(7)`, test code only) against `grid_slab(10,10)` + `cube()` stacked, `EmbreeCaster` and
  `BruteCaster` agree on hit/miss for >= 99.9 % of rays and on `t` within 1e-3 for every ray both hit.
- [ ] **Step 2:** implement. `EmbreeCaster` wraps `trimesh.ray.ray_pyembree.RayMeshIntersector(trimesh.Trimesh(vertices, faces, process=False))`;
  `first_hit` uses `intersects_location(..., multiple_hits=False)` and computes `t = (loc - o) . d`.
- [ ] **Step 3:** tests pass. Commit `feat(engine): ray casters with brute-force oracle`.

### Task 2: Exposure

**Files:** Create `engine\vis\__init__.py`, `engine\vis\exposure.py`, `engine\tests\test_exposure.py`. Modify fixtures.

**Interfaces — Produces:**
`fib_dirs(n: int) -> (n,3)`, `BARY` (4x3: centroid + three 0.6/0.2/0.2 points), `EPS_IN = 0.02`,
`compute_exposure(positions_c, face_w, ok, caster_factory=EmbreeCaster, n_dirs=128) -> np.ndarray[float64] (F,)`
= escaping rays / (`n_dirs` * 4), 0.0 for degenerate faces. For each direction `w`: faces with `n.w > 1e-6` cast
from `p + EPS*n`, faces with `n.w < -1e-6` cast from `p - EPS*n`, all along `w`, against one caster built from
**all** `ok` faces.
`classify_exposure(exposure, ok, slit_threshold=0.05) -> np.ndarray[uint8]` with
`EXP_DEGENERATE=0, EXP_HIDDEN=1, EXP_SLIT=2, EXP_OUTSIDE=3`.

New fixtures: `box_with_partition()` closed cube plus one inner quad (2 tris) spanning its middle -> the 2 inner
tris are `EXP_HIDDEN`, all 12 outer tris `EXP_OUTSIDE`. `open_box_with_cells()` box with one side missing and
two inner partitions parallel to the missing side, one near the opening, one deep -> deep partition exposure is
lower than the near one, both > 0, and the box's own faces are `EXP_OUTSIDE`.

- [ ] **Step 1:** failing tests for both fixtures, plus determinism (`compute_exposure` twice -> identical arrays).
- [ ] **Step 2:** implement (port of `escapes_double_sided` in `spike\10_ds_visibility.py`).
- [ ] **Step 3: real-data check** on `data\snapshots\ce26e0392ab0\CHTM_SIDE_WALK_2nd_floor.obj`: hidden count must be
  **1,853**, slit (< 5 %) **164**, outside **2,458** (spike numbers, same sampling). A different number means the port
  differs from the spike: find out why before moving on, report the cause.
- [ ] **Step 4:** Commit `feat(engine): double-sided exposure and classes`.

### Task 3: Guard

**Files:** Create `engine\guard\__init__.py`, `views.py`, `compare.py`, `render.py`, `engine\tests\test_guard.py`

**Interfaces — Produces:**
`VIEWS_26` (the 26 axis/diagonal directions, each nudged by `(0.013, 0.007, 0.011)`),
`ortho_first_hit(positions_c, faces, face_ids, view, frame_points, size=(900, 600), caster_factory=EmbreeCaster) -> tuple[depth (H,W) float64 inf=miss, tri (H,W) int64 -1=miss]` (`tri` holds `face_ids` values),
`@dataclass ViewVerdict(view, model_px, holes, moved_same_flat, moved_other, material_changed)`,
`@dataclass GuardReport(views: list[ViewVerdict], passed: bool, totals: dict)`,
`compare_views(before, after, face_material_before, face_material_after, flat_materials, depth_tol) -> GuardReport`,
`guard_feedback(candidates: bool (F,), render_after: Callable[[bool mask], list[(depth, tri)]], before, ...) -> tuple[bool mask, list[dict] history]`.

Pixel verdicts, in this order: **hole** = hit before, miss after. **material_changed** = both hit, material index
differs. **moved_same_flat** = both hit, same material, that material is flat, `|dt| > depth_tol`.
**moved_other** = both hit, same patterned material, `|dt| > depth_tol`. `passed` = holes + material_changed +
moved_other == 0. `moved_same_flat` is reported, never silently ignored, never a failure.
Default `depth_tol = 1.5 * max(axis_quanta)`.

`guard_feedback`: render, find failing pixels, every candidate face that is the BEFORE first hit at a failing pixel
is restored, repeat, stop at 0 failures or 8 rounds. Returns the surviving mask and per-round history.

`render.py`: `save_triptych(path, before, after, verdict_mask)` writes BEFORE | AFTER | DIFF (failures red,
`moved_same_flat` amber) as one PNG.

- [ ] **Step 1: failing mutation tests** on `box_with_partition()`:
  identity -> every count 0, `passed`; delete one outer face -> `holes > 0` or `moved_*` > 0, not passed;
  delete the 2 hidden inner tris -> all 0, passed; change one outer face's material to a second material ->
  `material_changed > 0`, not passed; flat vs patterned: on `open_box_with_cells()` deleting the near partition gives
  `moved_same_flat > 0` and passes when the material is flat, fails (`moved_other > 0`) when it is patterned.
  `guard_feedback`: candidates = hidden tris + one deliberately wrong outer face -> the outer face is restored in
  round 1, final mask keeps exactly the hidden tris.
- [ ] **Step 2:** implement. **Step 3:** tests pass.
- [ ] **Step 4: real-data check:** candidates = hidden faces of file A -> feedback ends with **1,819** removable,
  **34** restored, 0 failures over 26 views (spike numbers). Report the real history.
- [ ] **Step 5:** Commit `feat(engine): depth and colour aware facade guard with feedback`.

### Task 4: Remove faces with provenance

**Files:** Create `engine\fixes\__init__.py`, `engine\fixes\remove.py`, `engine\tests\test_remove.py`

**Interfaces — Produces:** `remove_faces(mesh: MeshData, drop: np.ndarray[bool]) -> tuple[MeshData, np.ndarray[int64]]`
returning the new mesh and `source_face` (new face index -> original face index). Positions, UVs, normals arrays are
kept unchanged (no re-indexing, no compaction) so vertex ids stay comparable across versions. `face_line` carries over.

- [ ] Tests: dropping nothing is identity; dropping faces keeps order of survivors; `source_face` maps back exactly;
  round trip through `write_obj` / `read_obj` preserves face count. Implement, pass, commit
  `feat(engine): face removal with provenance`.

### Task 5: Planar region merge kernel

**Files:** Create `engine\fixes\merge.py`, `engine\tests\test_merge.py`. Modify fixtures.

**Interfaces — Consumes:** `analyse_topology`, `Topology`, `plane_basis`, `fit_uv` / `cluster_uv`.
**Produces:** `merge_regions(mesh, topo, flat_materials) -> MergeResult` with
`mesh: MeshData`, `source_faces: list[np.ndarray]` (new face -> original faces of its region, or the single
original face when untouched), `report: dict` (`regions_merged`, `regions_skipped` with reason counts
`overlap` / `new_vertex` / `invalid_polygon` / `area_grew`, `tris_before`, `tris_after`, `vertices_dropped`,
`max_area_rel_error`).

Algorithm (each numbered rule is a test):
1. Work per region of `topo.face_region`. Regions of 1 face are copied through.
2. Project the region's welded vertices with `plane_basis` of the area-weighted region normal. Build
   `{vertex id -> 2D}` once, triangles as shapely polygons.
3. **Overlap per triangle**: a triangle whose intersection area with another triangle of the same region exceeds
   `1e-9 + 1e-6 * its area` is excluded from the merge and copied through. The rest are unioned.
4. Union with `grid_size=1e-4`. Every ring coordinate must map to an existing vertex id within `1e-3` (nearest
   search among the region's vertices). Any miss -> skip the region, reason `new_vertex`.
5. **Global corner pass**, after rings exist for ALL regions: a welded vertex is *needed* when it is a corner
   (distance to the chord of its ring neighbours > collinearity tolerance, or the path doubles back) in any ring,
   or is used by any face that is copied through (overlap, single-face region, skipped region, degenerate-free
   unmerged face), or lies on an edge classed OPEN, NONMANIFOLD or TJUNCTION. Only vertices not needed are dropped,
   and they are dropped from every ring, so both sides of a shared border stay identical. No new T-junctions.
6. Rebuild each polygon from its kept ring vertices. If it is invalid or its area differs from the union area by
   more than `1e-6` relative plus `tol * perimeter`, fall back to keeping all ring vertices for that region.
7. `shapely.constrained_delaunay_triangles`, map every output vertex back to its id (exact 2D match against the
   kept ring vertices; any miss -> skip region, reason `new_vertex`). Wind triangles to the region normal.
8. UVs: flat material -> new `vt` entries from the region's least-squares UV fit (largest member seeds, iterative
   refit), re-based so the region's minimum UV lies in [0,1). Patterned material -> same fit (the region is one UV
   class by construction). One new `vn` per region.
9. Area check per region: merged area <= original area * (1 + 1e-6), else skip with reason `area_grew`.

New fixtures and exact expectations:
| Fixture | Expect |
|---|---|
| `grid_slab(10,10)` | 200 -> **2** tris, 117 of 121 vertices unused by faces, area equal |
| `l_shaped_slab()` (10x10 grid with a 5x5 corner removed) | -> **4** tris (6 corners) |
| `slab_with_hole()` (10x10 grid, 2x2 cells removed in the middle) | -> **8** tris (8 corners, 1 hole: n + 2h - 2) |
| `two_slabs_sharing_border()` (two coplanar 5x10 grids, different materials, shared border with 9 collinear vertices) | each -> 2 tris, all 9 border vertices dropped from both |
| `slab_with_wall()` (grid slab + one vertical wall triangle standing on an interior grid vertex and a border vertex) | the two wall-foot vertices survive in the slab's triangulation |
| `overlapping_pair()` (grid slab + one extra coplanar triangle overlapping two cells) | overlapping triangle and the cells it overlaps copied through, rest merged, `regions_skipped` empty |
| `cube()` | 12 -> 12 tris, nothing dropped |

- [ ] **Step 1:** write all fixture tests, run, see them fail. **Step 2:** implement. **Step 3:** pass.
- [ ] **Step 4: real-data check** on file A after hidden removal: report tris before/after, regions merged/skipped by
  reason, vertices dropped. Spike floor estimate was 2,073 with all border vertices kept, so expect **<= 2,073**.
  A number above that means the corner pass is not working: investigate before moving on.
- [ ] **Step 5:** Commit `feat(engine): planar region merge over existing vertices`.

### Task 6: Pipeline + invariants

**Files:** Create `engine\fixes\pipeline.py`, `engine\tests\test_pipeline.py`

**Interfaces — Produces:**
`@dataclass FixProfile(n_dirs=128, slit_threshold=0.05, accept_slit=False, flat_texture_std=8.0, guard_size=(900,600))`,
`@dataclass FixResult(mesh, source_faces, exposure_class, removed_hidden, removed_slit, restored_by_guard, merge_report, guard_after_removal: GuardReport, guard_final: GuardReport, invariants: dict, passed: bool)`,
`fix_object(mesh: MeshData, flatness: dict[str, float], profile=FixProfile()) -> FixResult`.

Order: `analyse_topology` -> `compute_exposure` -> candidates = hidden (+ slit when `accept_slit`) ->
`guard_feedback` against the original -> `remove_faces` (also drops degenerate faces) -> `analyse_topology` on the
result -> `merge_regions` -> final guard of merged mesh against the ORIGINAL -> invariants
(`material_count_same`, `bbox_same`, `area_not_grown`, `guard_passed`). If the final guard fails, the result falls
back to the un-merged mesh (removal only), `merge_report["rolled_back"] = True`, and `passed` reflects the fallback's guard.

- [ ] Tests on `box_with_partition()` (partition removed, 12 outer tris stay 12, passed), on a gridded closed box
  built from `grid_slab` faces (hidden none, merges to 12 tris), determinism (two runs -> identical arrays).
  Implement, pass, commit `feat(engine): fix pipeline with invariants and rollback`.

### Task 7: CLI, fixed OBJ, report, preview data

**Files:** Create `engine\cli.py`, `engine\tests\test_cli.py`. Modify `spike\12_export_preview.py` **no** - leave the
spike alone; add `preview-data` to the CLI instead.

**Interfaces — Produces:**
`python -m engine.cli fix <snapshot_dir> [--accept-slit] [--out data/output]` writes
`<out>\<name>\<name>.fixed.obj`, copies `materials.mtl` + `tex\`, `report.json` (every `FixResult` number, both
guard reports per view, profile, input sha256), `guard_<view>.png` triptychs for 6 views, exit code 0 when
`passed`, 2 when not. `python -m engine.cli preview-data <snapshot_dir> --out preview/data` writes the JSON the
existing `preview\index.html` reads, with AFTER = the real fixed mesh and the real guard numbers in `stats`.

- [ ] Tests: CLI on a fixture snapshot dir produces the files, `report.json` parses, exit code 0; a fixture that
  must fail the guard (patched profile forcing removal of an outer face) exits 2.
- [ ] **Real-data acceptance, both files**, paste `report.json` summaries:

| | expect |
|---|---|
| hidden removed after feedback | A **1,819**, B **2,381** |
| guard after removal | 0 holes, 0 material_changed, 0 moved_other, all 26 views |
| final guard after merge | **passed**, with `moved_same_flat` reported. The spike's rough merge failed this (0.42 % px), the real kernel must not |
| tris | A **<= 2,073** from 4,692, B **<= 2,499** from 7,227 |
| invariants | material count same, bbox same, area not grown |
| `--accept-slit` run | A removes 164 more, B 193 more. B's 260 px `material_changed` must make that run **fail** unless guard feedback restores the responsible faces, in which case report how many were restored |

- [ ] Open `http://localhost:5180` after `preview-data`, screenshot BEFORE / AFTER, confirm no console errors.
- [ ] Commit `feat(engine): fix CLI, report, guard images, preview data`.

### Task 8: Outward orientation + one-sided completeness

Added 2026-09-21 after the user asked that the fixed object also be correct with one-sided rendering.
Measured on the real files (double-sided occlusion, each side of a face tested separately): file A has **727**
visible faces (18.1 % of visible area) whose only exposed side is the BACK, file B **800** (15.8 %). Another
330 / 561 faces have both sides exposed, of which only 82 / 107 are roughly equal-sided true thin sheets.

**Files:** Modify `engine\vis\exposure.py`, `engine\fixes\pipeline.py`, `engine\cli.py`. Create `engine\fixes\orient.py`,
`engine\tests\test_orient.py`.

**Interfaces — Produces:**
`compute_side_exposure(positions_c, face_w, ok, caster_factory=EmbreeCaster, n_dirs=128) -> tuple[np.ndarray, np.ndarray]`
(front, back fractions, each escaping rays / (`n_dirs` * 4); `compute_exposure` becomes their sum and keeps returning
exactly the same values as today, pinned by a test),
`ORIENT_OK=0, ORIENT_FLIP=1, ORIENT_THIN_SHEET=2`,
`classify_orientation(front, back, ok, sheet_ratio=0.5) -> np.ndarray[uint8]`: `FLIP` when `back > front`;
`THIN_SHEET` when both > 0 and `min/max >= sheet_ratio`; else `OK`. Hidden faces are `OK` (they get removed anyway).
`flip_faces(mesh, flip: bool mask) -> MeshData`: reverses vertex order of `face_v`, `face_vt`, `face_vn` for those faces
and negates nothing else. Vertices are not moved. Source `vn` of a flipped face is dropped (`-1`), so no normal points backwards.
`one_sided_holes(positions_c, faces, face_ids, views, size) -> int`: pixels that hit in a double-sided render but
whose first hit is back-facing to the camera. Reported BEFORE and AFTER.

Pipeline order becomes: exposure -> hidden removal under strict guard -> (accepted slit removal) -> **orientation flip** ->
merge -> final guard. Flipping never changes a double-sided render, so the guard verdict must be identical with and
without the flip step: that is a test. `FixResult` gains `flipped`, `thin_sheets`, `one_sided_holes_before`,
`one_sided_holes_after`. Thin sheets are reported, not changed: completing them one-sided means adding a second face,
which is new geometry and stays a reviewed, later fix.

- [ ] Tests: `compute_exposure` unchanged (exact array equality before/after this task on `box_with_partition`);
  a cube with 3 faces deliberately reversed -> exactly those 3 classed `FLIP`, after `flip_faces` all outward and
  `one_sided_holes == 0`; a single free-standing quad -> `THIN_SHEET`, untouched; guard report equal with and without flips.
- [ ] Real data: file A must class **727** faces `FLIP` (same sampling as the measurement above) and report
  `one_sided_holes` before and after over the 26 views. After must be lower than before. Paste both numbers.
- [ ] Commit `feat(engine): outward orientation and one-sided completeness`.

### Task 9: Polygon export + honest viewer data

The user wants the AFTER object to show only its real shape edges. OBJ for Unity must contain triangles, but each
merged flat region without holes can also be written as ONE polygon face.

**Files:** Modify `engine\fixes\merge.py` (keep each region's kept outer ring of vertex ids in `MergeResult.rings`),
`engine\io\obj_writer.py` (`write_obj_polygons(mesh, rings, path)`), `engine\cli.py`.

- `fix` additionally writes `<name>.fixed.ngon.obj`: one `f` line per hole-free merged region (any vertex count),
  triangles for regions with holes and for copied-through faces. The triangulated `<name>.fixed.obj` stays the Unity file.
- `preview-data` marks AFTER edges as: `outline` (real), `tri` (triangulation diagonals that exist only because OBJ
  needs triangles), and provides counts for both so the page can state "0 gridlines, N outline edges, M unavoidable diagonals".
- [ ] Tests: `grid_slab` -> ngon file has exactly 1 face with 4 vertices; `slab_with_hole` -> stays triangles (8);
  ngon file re-read fails loudly with `ObjFormatError` in `read_obj` (triangles only by design), which is asserted, and a
  tiny polygon-aware counter in the test confirms the face count.
- [ ] Commit `feat(engine): polygon export and viewer edge classes for the fixed mesh`.

---

## Phase 2E done when

- Full suite passes, real count pasted.
- Both real files produce a fixed OBJ with `passed: true` (hidden removal + merge), numbers within the table above.
- Fixed OBJ re-imports through `read_obj` with 0 zero-area faces and material count unchanged.
- Preview page shows the real fixed mesh.
- Any expectation that was not met is reported as not met, with the measured number. No expectation is edited to fit.
