# Phase 0 Spike Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to run this plan
> task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Answer three go/no-go questions on the real sidewalk files before any infrastructure is built.

**Architecture:** Five throwaway scripts in `spike\`, each prints its numbers and merges them into
`data\spike\results.json`. Nothing here is imported by the engine later. Validated algorithms get
re-implemented under TDD in Phase 1.

**Tech Stack:** Python 3.12 venv, numpy, shapely >= 2.1, trimesh, embreex.

**Spec:** `docs\superpowers\specs\2026-09-21-uc-model-fixer-design.md`

## Global Constraints

- Source folder `D:\PROJECTS\UC ENVIRONMENT BUILDING\REQUIREMENTS\01-MODEL-EXPORT\CKPT17` is
  **read-only and live**. Only `01_snapshot.py` touches it. Every other script reads `data\spike\snapshot\`.
- Test set: `CHTM_SIDE_WALK_2nd_floor.obj`, `CHTM_2nd_to_3rd_building_sidewalk_outside.obj`.
- Units are inches. Coordinate quantum is detected from printed decimals, not assumed.
- Blocked operations from the spec apply: no weld above 0.1 mm, no decimate, no hole filling.
- Spike code is throwaway: no tests, but **every script must be run** and its printed numbers
  recorded. A script that was not run does not count as done.
- All Python commands use `.venv\Scripts\python.exe`.

## Gates

| Gate | Question | Pass when |
|---|---|---|
| G1 | Does `embreex` work here? | imports under the venv's numpy, sphere test hit fraction > 0.999, rays/s reported |
| G2 | Is the planar region merge worth building, and is it safe? | tri reduction >= 40 % on at least one file, merged area relative error <= 1e-6, max UV residual modulo 1 <= 0.02 |
| G3 | Does "front-facing triangles only" + first hit equal Unity culling? | against brute-force oracle: hit/miss disagreement <= 0.1 % of rays, depth disagreement (> 1e-3 in) <= 0.1 % of rays both hit |

A failed gate stops the build and goes back to design.

---

### Task 1: Environment + G1

**Files:**
- Create: `requirements-spike.txt`, `spike\00_env_check.py`

- [ ] **Step 1:** Create venv: `py -3.12 -m venv .venv`
- [ ] **Step 2:** `requirements-spike.txt` = `numpy`, `shapely>=2.1`, `trimesh`, `embreex`. Install:
  `.venv\Scripts\python.exe -m pip install -r requirements-spike.txt`
- [ ] **Step 3:** Write `spike\00_env_check.py`: records python, numpy, shapely, GEOS, trimesh,
  embreex versions; builds `trimesh.creation.icosphere(subdivisions=5)`; casts 1,000,000 rays
  aimed at the origin from radius 3 through `trimesh.ray.ray_pyembree.RayMeshIntersector.intersects_first`;
  records `rays_per_s`, `hit_fraction`, `gate_G1`. Any exception sets `gate_G1=false` and records `repr(e)`.
- [ ] **Step 4:** Run `.venv\Scripts\python.exe spike\00_env_check.py`. Expected: `gate_G1: true`.
  If embreex fails to import under numpy 2.x, retry once with `numpy<2` and record which worked.
- [ ] **Step 5:** Commit.

### Task 2: Snapshot

**Files:**
- Create: `spike\_obj.py` (minimal loader: v, vt, vn, triangular f, usemtl, printed decimals; asserts
  on non-triangle faces), `spike\01_snapshot.py`

- [ ] **Step 1:** Write `01_snapshot.py`: for each test file, stat (size, mtime_ns), sleep 2 s, stat
  again; differing or zero size = abort with `source rebuilding`. Copy to `data\spike\snapshot\`,
  re-stat source, sha256 the copy. Parse the copy, compare tri count to `split\_MANIFEST.txt`
  (columns split on 2+ spaces, thousands commas stripped). Copy `CKPT17-CLEAN.mtl` and only the
  textures the two objects reference into `data\spike\snapshot\SRC-TEX\`.
- [ ] **Step 2:** Run it. Expected: two sha256 values, tri counts equal manifest, missing textures = 0.
- [ ] **Step 3:** Commit.

### Task 3: Re-measure

**Files:**
- Create: `spike\02_measure.py`

- [ ] **Step 1:** Write it. Per file: v/vt/vn/f counts; printed decimals and quantum; unique welded
  positions (exact, rounded to printed decimals); zero-area triangles (area <= 1e-7 * longest_edge^2);
  edge valence histogram 1 / 2 / 3 / 4+ on welded ids; exact duplicate faces split into same and
  opposite winding, and how many pairs differ in material; bbox in inches and metres.
- [ ] **Step 2:** Run it. Compare with spec table (previous export): valence 453/3,732/1,629/303 and
  534/7,615/1,216/538, zero-area 217 and 79, duplicates 11 and 31. Record any drift.
- [ ] **Step 3:** Commit.

### Task 4: Region merge + G2

**Files:**
- Create: `spike\03_region_merge_one.py`

Algorithm (this is what Phase 1 re-implements):
1. Weld exactly. Drop zero-area triangles.
2. **Plane clusters**, greedy by largest triangle: a triangle joins the seed's plane when same
   material, facing the same side (`n . n_seed > 0.9`), and all 3 vertices within
   `1.5 * quantum` of the seed plane.
3. **UV classes** inside a plane cluster, greedy by largest triangle with iterative refit: fit
   `uv = J*xy + o` on the seed, accept triangles whose 3 residuals round to the **same** integer
   vector and sit within 0.02 of it, refit by least squares over all accepted vertices with the
   integers removed, repeat until stable (max 6 rounds). Refit matters: one triangle's J is too
   imprecise to extrapolate across a 40 m slab.
4. Per (plane, UV class): shapely polygons -> `union_all(grid_size=quantum/100)`. If the union area
   is smaller than the triangle area sum by more than 1e-6 relative, the cluster holds overlapping
   faces: flag it, leave its triangles untouched.
5. Otherwise `constrained_delaunay_triangles` per polygon, count output triangles.
6. Write the largest region as `data\spike\region_before.obj` and `region_after.obj` with UVs from the fit.

Reports per file: plane clusters, UV classes, regions, flagged overlap clusters, faces admitted
with `n . n_seed < 0.999`, tris before -> after, reduction %, max relative area error, max UV
residual, holes in unions.

- [ ] **Step 1:** Write it.
- [ ] **Step 2:** Run it. Record numbers. Evaluate G2.
- [ ] **Step 3:** Commit.

### Task 5: Front-hit oracle + G3

**Files:**
- Create: `spike\04_front_hit_oracle.py`

- [ ] **Step 1:** Write it. Recentre to bbox centre. 8 Fibonacci directions, 2,000 random rays per
  direction, origins = random bbox points pushed back by the bbox diagonal. **Embree side:** mesh of
  only triangles with `n . d < 0`, `intersects_location(multiple_hits=False)`. **Oracle:** numpy
  Moller-Trumbore over all triangles, accept only `n . d < 0`, nearest `t`, float64, rays chunked by 256.
  Compare hit/miss and hit distance.
- [ ] **Step 2:** Run it. Record both disagreement rates. Evaluate G3.
- [ ] **Step 3:** Commit.

### Task 6: Gate report

**Files:**
- Create: `docs\spike\2026-09-21-phase0-results.md`

- [ ] **Step 1:** Write the report from `data\spike\results.json`: one table per gate with measured
  numbers, pass/fail, and for each failure what changes in the design. List drift against the
  spec's previous-export numbers.
- [ ] **Step 2:** Commit. Then write the Phase 1 plan using the validated region algorithm.
