# Engine v2 + Interior Studio Master Validation Checklist

> **Zero-Exception Quality Law:** Every automated and visual gate below is a hard blocker (`errors = exception`).  
> Do **not** proceed to additional buildings (`ARCHI`, `BRS`, `EDS`, `GYM`, `MAIN`, `MAIN_INFRA`, `PE`, `SCI-A`) until the golden building (**CHTM**) achieves **100% pass** across all Engine v2 checks, Studio 4-mode gates, rotated Blender/Browser close-ups, and **Jev Repair Gate** validation.

---

## 1. Per-Room & Per-Element Preparation Masterlist

Every room and structural assembly must satisfy **every row below across all 4 Studio filter modes (`Full`, `Auto`, `Low`, `Floor`)** as well as the full Engine v2 `.blend`/`.glb` export:

| # | Room / Structural Element | What Engine v2 + Studio Solidifier Must Preserve, Merge, Rebuild & Solidify | Hard Pass Criteria |
| :--- | :--- | :--- | :--- |
| **1** | **Outer Facade & Cladding** | Preserve 100% of `EXP_OUTSIDE` faces (`littletiles_*`, fascia, cornices, cladding) directly from RAW CHECKPOINT-17 via Strict Outer Facade Lock; never replace with 2D extrusion or shrink building footprint. | `outer_facade_completeness == 100.00%`, `outer_facade_zero_cracklines == 0`, `0` missing quads/half-triangles (`D04`, `D06`, `D07`). |
| **2** | **Thick Exterior Walls (`2m+`)** | Keep outer face, inner face, window frames/recesses, and horizontal top cap together as one solid architectural volume (`EXT_SOLID_DEPTH_M = 2.55m` + true 5-zone solid-volume slicing `_slice_mesh_by_zones`). Seal every vertical quadrant/cut seam with concrete end-caps (`Wall_Ext_{W,E,N,S}_01__Upper__cut_cap`). | Zero peeled half-walls, zero hollow single-sided black interiors, `S2_max_zone_overhang_m <= 0.08`, `S3_quadrant_mismatch == 0`. |
| **3** | **Interior Partition Walls & Doorways** | Preserve 99–100% of visible room walls and dark-green baseboards (`D12`, `D14`), strip buried `1-block (39.37 in)` internal voxel-stack plates (`D11`), keep narrow doorways (`>= 0.70m`) and corridors open, and seal solid wall cut tops (`Wall_*__Lower__cut_cap`, `Wall_*__Plinth__cut_cap`). | `interior_visible_retention >= 99.0%`, `doorways_unblocked == true`, `S1_corridor_cutcap_leak_m2 <= 0.35`, `0` punch-through holes (`D14`). |
| **4** | **Columns & Structural Piers (`2m x 2m`)** | Classify capped structural piers (`<= 40 m^2`, `top_cov >= 0.70`, `walk_cov < 0.25`) as solid filled volumes in `Low`, `Auto`, and `Floor` modes; protect wall-column junctions so adjacent walls never punch cutouts into columns (`G02`). | `S4_capped_piers_solid_pct >= 98.0%`, `0` pillar base cutouts (`D07`), flush `Plinth__cut_cap` + `Lower__cut_cap`. |
| **5** | **Walkable Floor Slabs & Corridors** | Keep continuous walkable floors strictly in `[slab_bottom_y, floor_y]` inside `Floor_Slab`; seal all narrow cracks, razor slits, and column-side notches (including RAW SketchUp defects) via `heal_walkable_floor_slab_cracks` (`earcut` + exact adjacent 2D-to-UV affine projection) without double-filling nearby thresholds (`±0.20m`). | `stair_and_floor_continuity >= 99.5%`, `zero_walkable_floor_cracks == 0` (Gate #11), `S6_walkable_floor_cracks == 0`, `S1 <= 0.35 m^2`. |
| **6** | **Stairwells, Treads & Landings** | Route complete stairwells (`0.03 <= hole <= 8.0 m^2`, `comp.area <= 120.0 m^2`) into `Stairs_01` / `Stairs_Upper_01`; preserve unbroken treads, risers, landings, and stringer returns; purge hanging underside spikes or debris (`D10`, `D13`). | `stair_and_floor_continuity >= 99.5%`, `0` floating stairwell shards, `0` sawtooth sidewalls (`D10`). |
| **7** | **Railings, Balustrades & Parapets** | Retain all thin exterior railings, stepped balustrades, and green U-parapets untouched (`use_backface_culling = False` two-sided where legitimately thin); clip lower parapet tails cleanly to stair/floor support (`parapet_bounds_clean`). | `outer_facade_completeness == 100.00%`, `parapet_zfight == 0`, `0` floating lower parapet tails. |
| **8** | **Windows, Mullions, Glass & Louvers** | Keep recessed windows, mullions, transparent glass (`Transparent` bucket), and thin doorway horizontal louvers attached inside their parent wall zone (`EXT_SOLID_DEPTH_M = 2.55m`); strip `Zebra` coplanar stripes (`D08`). | `0` detached/floating mullions in `Auto`/`Low`, `flicker_diff == 0`, `flicker_same == 0`. |
| **9** | **Ceilings, Roofs & Overhangs** | Strip only wide walkable-room ceiling decks (`wide_ceil_core`, intersecting `walkable_floor_2d`) before cutaway slicing so rooms open cleanly from above without deleting wall/pier top caps (`216.8 m^2` rule) or leaking giant slabs into `OverheadBeams_And_Lintels`. | `S5_overhead_top_area_m2 <= 65.0`, `0` hanging `solidify` air bridges (`phantom_tris_remaining == 0`). |
| **10** | **Textures & Mesh Baker 3.40.2 UVs** | Normalize integer UV tile offsets (`floor(min_uv)`) while preserving exact fractional LittleTiles tiling; prune unused material slots in Blender 5.1; keep Opaque vs Transparent (`Glass`) draw-call buckets clean (`<= 2` draw calls after Mesh Baker 3.40.2 Paid). | `original_texture_fidelity <= 1.0% swapped`, `blender_mesh_topology_valid == true`, textures packed, `Mesh Baker` 2 draw calls ready. |

---

## 2. Combined Engine v1 + Engine v2 Capabilities Matrix

| Capability | Engine v1 Heritage | Engine v2 Upgrade (`05`) | Combined Non-Regression Standard |
| :--- | :--- | :--- | :--- |
| **Internal Face & Debris Purge** | Stripped buried cube internals (`stage_hidden`) & tiny disconnected scraps (`stage_loose`). | Adds `detect_internal_voxel_stack_plates` + `purge_internal_voxel_stack_plates` (`39.37 in` internal filler plates) + 13-pt Embree `drop_phantom_bridges`. | Stripped internal bloat (45–60% tris reduction) with **`0` visible deletions**. |
| **Coplanar Overlap & Normal Fix** | Flagged `double_layers`, `reversed`, `open_edges`. | E5 `remove_coplanar_overlaps(rebuild=True, outer_priority=EXP_OUTSIDE)` + non-transitive `resolve_residual_double_layers` + 128-dir one-sided normal orientation. | `flicker_diff == 0`, `flicker_same == 0`, `reversed == 0`. |
| **Facade, Sliver & Crack Repair** | Could accidentally clip outer cladding/railings or leave torn seams (`D03`, `D04`). | Strict 100% Outer Facade Lock, 256-dir Interior Visible Retention, `purge_piercing_needle_slivers`, and `heal_walkable_floor_slab_cracks`. | `outer == 100.00%`, `torn_seams == 0`, `slivers == 0`, `floor_cracks == 0`. |
| **Studio 4-Mode Cutaway Packaging** | N/A (early `solid_cutaway_rebuild.py` lacked V2 frame detection & deck recovery). | Runs `solid_cutaway_rebuild.py` directly on Engine v2 `.v2.obj` (`engine_v2_metres_zup`) using `manifold3d` (`S7`/`S8`), wide horizontal-only deck/balcony recovery (`Floor_Deck_Supp` / `Facade_Deck_*`), shared-pivot rigid transitions (`InteriorStudioCanvas.tsx`), and V2 footprint parity (`S9`). | `S1`–`S9` all green (`S7=0`, `S8=True`, `S9_H>=98%`, `S9_V>=85%`); `0` vertical fin artifacts. |

---

## 3. Hard Automated Gates (11 Engine v2 + 9 Studio Cutaway)

### A. Engine v2 11 Automated & Signoff Gates (`engine/validate/facade_integrity.py`)
1. `outer_facade_completeness` (`>= 99.8%`; CHTM promotion requires **`100.00%`**)
2. `outer_facade_zero_cracklines` (`0` torn seams)
3. `interior_visible_retention` (`>= 99.0%`)
4. `zero_piercing_needle_slivers` (`0` slivers, `0` zero-area)
5. `stair_and_floor_continuity` (`>= 99.5%`)
6. `zero_flicker_convergence` (`0` diff / `0` same)
7. `zero_reversed_normals` (`0` reversed)
8. `original_texture_fidelity` (`<= 1.0%` finish swapped)
9. `blender_mesh_topology_valid` (`invalid=False`, textures packed)
10. `ai_visual_defect_inspector` (`0` blocking visual defects `D01`–`D10`, `D12`, `D14`)
11. `zero_walkable_floor_cracks` (**`0` narrow walkable floor cracks/slivers/notches**)

### B. Studio 4-Mode Cutaway 9 Hard QA Gates (`tools/package_real_v2_for_studio.py`)
- **`S1_corridor_cutcap_leak_m2`** `<= 0.35 m^2` (CutCap geometry must never bleed into open walkable corridors)
- **`S2_max_zone_overhang_m`** `<= 0.08 m` (zone-sliced walls/caps must never overhang across channel boundaries)
- **`S3_quadrant_mismatch`** `== 0` (all `Wall_Ext_{W,E,N,S}_01` centroids align 100% with Three.js quadrant sign)
- **`S4_capped_piers_solid_pct`** `>= 98.0%` (solid columns/piers stay capped across `Low`, `Auto`, and `Floor`)
- **`S5_overhead_top_area_m2`** `<= 65.0 m^2` (wide ceilings stripped before overhead classification)
- **`S6_walkable_floor_cracks`** `== 0` (zero walkable slab cracks/notches in final Studio GLB)
- **`S7_open_edges`** `== 0` (`manifold3d` weld check on every `(group, tier)` parent block including `__cut_cap`)
- **`S8_manifold3d_verified`** `== True` (`manifold3d.Manifold` `Error.NoError` on every solid block)
- **`S9_v2_footprint_coverage_pct` / `S9_v2_vertical_coverage_pct`** (`>= 98.0%` horizontal / `>= 85.0%` vertical vs Engine v2 `CHTM_Floor_<LVL>.glb`, keeping ONLY wide `>= 0.50-0.80 m^2`, `>= 0.40 m` wide horizontal decks — never buffer vertical stair/wall triangles)

### C. Three.js Rigid-Block Transition Contract (`InteriorStudioCanvas.tsx`)
- `Floor_Slab`, `Floor_Deck_Supp*`, and `Facade_Deck_*` stay permanently visible across `Full`, `Auto`, `Low`, and `Floor`.
- `Facade_Ext_*`, `Facade_Canopy_*`, `Stairs_Upper*`, `OverheadBeams_And_Lintels`, and `Glass_Openings` show ONLY in `Full` (`0.0` in `Auto`, `Low`, `Floor`) to eliminate floating slats/ribbons in cutaway views.
- Shared `pivotY` per tier (`sharedLowerPivotY` / `sharedUpperPivotY`) + explicit semantic `sideDirX`/`sideDirZ` per directional channel (`W: -1,0`, `E: +1,0`, `N: 0,-1`, `S: 0,+1`) keep every material submesh and cap locked as one rigid solid block during exponential-decay transitions.

---

## 4. 4-Mode 360° Rotated Visual QA Checklist

Before marking ANY floor ready for Jev or production:
1. Inspect headless **Blender 5.1** renders + live **Three.js Studio** (`design-studio-test` preview) captures across **ALL 4 modes**: `Full`, `Auto`, `Low`, `Floor`.
2. Orbit 360° and render **close-up views** aimed at:
   - Exterior walls and **recessed windows/mullions** in `Auto` (verify outer+inner skins stay attached, cut corners show vertical concrete end-caps, zero floating mullions, zero `> 0.08m` overhanging caps);
   - **Grand stairwells & landings** in `Auto` and `Low` (verify unbroken treads/risers/walls, zero floating tan shards);
   - **Corridor intersections** in `Low` and `Floor` (verify zero white concrete CutCap triangles filling narrow `1.0–1.5m` hallways);
   - **Column-to-floor seams** in `Floor` mode (verify zero diagonal cracks, zero corner notches, crisp Plinth caps).
3. Verify `0` browser console / WebGL / network errors.

---

## 5. Jev Repair Gate Co-Validation Protocol

1. `tools/sync_chtm_v2_to_dashboard.py` publishes **all 11 Engine v2 checks** + **`studioQaGates` (`S1`–`S6`)** + **3D error overlay hotspots** into `dashboard/public/models/engine-v2/index.json` with `allPassed` derived **strictly** from automated Engine v2 + Blender + Studio gate results (never hardcoded `True`).
2. Jev (human / independent validator on `/pipelines/model-repair/` and `/pipelines/jev-repair/`) reviews each floor's `v2Checks`, `studioQaGates`, 3D Before/After error overlay, and close-up evidence against this checklist.
3. Any failing gate or visual close-up defect immediately marks the floor `FAIL` and loops back to the root-cause module (`engine/fixes`, `tools/build_real_v2_floor.py`, or `tools/package_real_v2_for_studio.py`) + unit test before re-syncing.
