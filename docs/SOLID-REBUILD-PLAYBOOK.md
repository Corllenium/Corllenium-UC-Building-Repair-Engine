# Solid Cutaway Rebuild & Interior Studio Master Playbook

Authoritative engineering checklist distilled from the **CHTM 4F & 5F** pilot rebuild (`solid-rebuild` / Engine v2) for scaling across all remaining **78 repaired `.fixed.obj` floors across 9 UC buildings** and integrating directly into **Unity 6 URP (`03-Corllenium-UC-Game`)**.

---

## 1. End-to-End Pipeline Architecture

1. **Source Architectural Floor (`04-Corllenium-Building-Model-Repair`):**
   - `Exports/Repaired-Buildings-20261015/ByBuilding/<Building>/<Floor>/*.fixed.obj` (+ `.mtl` / textures)
   - Never modify `01_ORIGINAL_BACKUPS/`, `CHECKPOINT-17`, or `building_repair.py` / `engine/guard/**`.
2. **Engine v2 Solid Rebuild (`05-Corllenium-UC-Building-Repair-Engine`):**
   - Run `python tools/batch_solid_rebuild.py --building <Building>` (which calls `run_solid_rebuild(...)` and enforces all **8 automated QA gates**, excluding rooftops `Floor_RF`, `Sidewalk_*`, and basements `Floor_*B` by default; pass `--include-basements` only when rebuilding parking decks).
3. **Staged Output Packages (`04-Corllenium-Building-Model-Repair`):**
   - `02_STAGING_DEVELOPMENT/SolidRebuild/<Building>/<Floor>/`
     - `*.solid_rebuild.unity.obj` + `materials.mtl` + `textures/` — direct Unity 6 URP import package (metres Y-up)
     - `*.solid_rebuild.glb` — WebGL/Three.js asset for Siege Interior Studio
     - `rebuild_manifest.json` + `watertight_audit.json` + `<Building>/batch_qa_report.json`
4. **Target Consumers:**
   - **Primary Game Client (`03-Corllenium-UC-Game`):** Directly imports `.solid_rebuild.unity.obj` + `materials.mtl` + `textures/` into Unity prefabs (no rebuilding required inside Unity).
   - **Planning & Drafting (`02-Corllenium-Siege`):** Uses `.solid_rebuild.glb` + `*-interior-mask.png` + `*-rooms-color.json` in `dashboard/public/interior-studio/<Building>/`, with optional JSON blueprint export (`FloorRestorationBlueprint`).

---

## 2. Mandatory Engine v2 Rules & Lessons Learned (`solid_cutaway_rebuild.py`)

Every fix discovered during CHTM 4F & 5F QA is encoded as a **general, deterministic rule** (zero per-floor hacks):

- [ ] **One Authoritative Solid Model Only:** Never emit or toggle legacy non-solid `Real OBJ` meshes alongside solid rebuilds. Export tiered watertight Manifold prisms: `Floor_Slab`, `Stairs_*`, `Stairs_Upper_*`, `Stairs_Parapet_*`, `Column_*__Plinth/__Lower/__Upper`, `Wall_Ext_{W,E,N,S}_*__Plinth/__Lower/__Upper`, `Wall_Int_*__Plinth/__Lower/__Upper`, `Glass_Openings`, `OverheadBeams_And_Lintels`, and `Facade_Ext_{W,E,N,S}`.
- [ ] **Zero-Defect Watertight Gate:** Every rebuilt floor MUST pass `passed=True`, `all_watertight=True`, `total_open_edges=0`, `total_nonmanifold_edges=0`, `narrow_wall_gaps=0`, with the `Manifold.simplify(0.004)` zero-area altitude guard active in `_polygon_to_manifold`.
- [ ] **2-of-3 Slice Column & Wall Consensus:** Extract `S_base` via 2-of-3 majority across `(S_30 & S_60) | (S_60 & S_mid_raw) | (S_30 & S_mid_raw)` so full-height columns missing a single low face (like CHTM 4F `Column_11`) stay solid without losing genuine doorway openings.
- [ ] **No Stepped-Down Upper Walls/Columns in `Full` Mode:** Sample `S_high_raw` at `ceil_y - 0.25`, `ceil_y - 0.50`, and `y_hi_low` with `max_room_area=120.0`, and construct `up_top = p_mid | (p_base & S_high_wall)` inside `_add_tiered_solid` so standing mid-height walls/columns NEVER chop early at `lintel_y` (`STEPPED_UPPER == 0`).
- [ ] **Solid Floor Slab & Open Pits:** Fill non-stairwell interior `Floor_Slab` holes where `bot_fp` proves `>= 85%` underside coverage, while keeping real descending stairwell pits (`below_u`) and elevator shafts open.
- [ ] **Preserve Exterior Facades, Reject Protruding Canopies:** Keep wall-embedded `littletiles_trim` window grilles/mullions inside `wall_env = unary_union([floor_fp, S_base]).buffer(0.25)` (`Facade_Ext_{W,E,N,S}`), and drop detached white roof slabs (`area > 4.0 and min(dx, dz) > 1.2`).
- [ ] **Material Isolation:** Restrict `prismarine_dark` baseboards strictly below `y_bb_cut` (`floor_y + baseboard_h`), never let `stair_mat` bleed onto interior walls, and slice slanted concrete spines cleanly at `y_bb_cut`.
- [ ] **Slanted Railings & Green U-Parapets (0 Z-Fighting, 0 Ceiling Wedges):** Extract parapets largest-cluster-first with merged adjacent cluster ROIs (`<= 1.2 m`), separate dedicated railing materials (`iron_block`, `quartz_15574983`, `concrete_green`), clip `U` spans strictly to the stairwell envelope `[cu0 - 0.15, cu1 + 0.15]`, clamp `quartz_15574983` balustrades to the `1.32 m` downward sweep beneath matched `iron_block` handrails (rejecting ceiling-hung inverted soffit triangles), and subtract claimed XZ footprints (`spine_claim_boxes`) from `S_base`, `S_mid`, `S_high_wall`, and `lintel_kept` (`same-dir Z-fight overlaps == 0`, Gate 7 `parapet_bounds_clean == True`).
- [ ] **Stair Continuity, Flipped Normals & Embree Notches:**
  - Reject stair shells overlapped `>= 20%` by treads `0.15..0.65 m` above them from `raw.raised_levels` (never emit `Floor_Raised` on bottom stair treads).
  - Recover horizontal flipped-normal treads (`ny < -0.98`) in Pass 2 only when bridging lower & higher treads (`0.15..0.35 m` risers), then re-run top-down headroom dedup (`0.05..1.35 m`) to trim inner shells underneath.
  - Run `_repair_notched_stair_treads` so every single-step axis-aligned tread has crisp 90° rectangular corners (`non_ortho_steps == []`).

---

## 3. Interior Mask, Grid Line & Furniture Studio Rules (`02-Corllenium-Siege`)

- [ ] **Exclude All Non-Interior Zones from Grids & Placement:** Exclude rooftops (`Floor_RF` / `*Roof*`), exterior sidewalks (`Sidewalk_*`), **basements (`1B..4B` / `Floor_*B`)**, and `service` kinds (`elev.`, `elevator`, `shaft`, `stairs`) plus `main lobby`, `corridor`, `hallway`, `bridge`, `balcony`, `terrace`, `ramp`, `void`, `outside`, AND generic unlabeled `"Room"` / `"Room 2"` `circulation` catch-alls (CHTM 4F diagonal stepped balcony `id=18`). Audit `*-interior-mask.png` pixels against enclosing wall boundaries (`open_bnd`) on every new floor.
- [ ] **Cutaway Filter & Toggle Parity (`InteriorStudioCanvas.tsx`):**
  - Keep `Facade_Ext_*` synced with `Wall_Ext_*__Upper` and active-room occlusion.
  - Keep `__Plinth` wall/column traces **always visible** even when `Stairs` is toggled OFF (`entry.tier === "plinth"` separated from `isLowerStair`).
  - Ensure `Full` mode rises all tiers (`__Lower`, `__Upper`, `OverheadBeams`, `Glass_Openings`, `Facade_Ext_*`, `Stairs_Upper_*`) cleanly to `ceil_y`.
- [ ] **Flush Sidewall, Corner & Column Furniture Placement:**
  - Include columns (`role === 4`) alongside walls (`role === 1, 3`) in `wallColliders`.
  - Prevent grid snap from jumping across solid walls/columns (`snapDist` ray check before wall-hug) and push flush to `1.5 cm` (`0.015 m`).
  - Permit footprint corners inside the `5–12 cm` raster mask-to-wall margin ONLY when backed by a real solid 3D wall/column in the same room (`cId === 0` + inward room check + 3D wall raycast), blocking hallways, doorways, and balconies.
  - Preserve fine `Snap` cycling (`0.50m -> 0.25m -> 0.10m -> Free`).

---

## 4. Direct Unity 6 URP Integration vs. Optional Studio Draft Sync

- **Loading Directly in Unity (`03-Corllenium-UC-Game`):** Unity does NOT need to re-run geometry repair or rebuild inside C#. Import each floor's pre-verified `*.solid_rebuild.unity.obj` + `materials.mtl` + `textures/` directly into URP prefabs with mesh colliders on `Floor_Slab`, `Wall_*`, `Column_*`, and `Stairs_*`.
- **Optional Three.js Draft Sync:** If you also want drafted furniture layouts from the Siege Interior Studio imported into Unity, export `FloorRestorationBlueprint` JSON and convert Three.js floor-local coordinates `(x, y, z)` back to Unity world space via `(x + originX, y + originY, -(z + originZ))` with mirrored yaw (`-yaw`).

---

## 5. Mandatory Per-Floor Development & Sign-Off Checklist (10-Point Gate)

1. **Source & Asset Stack Lock:** Confirm `*.fixed.obj`, `output_4_3d_color_coded.png`, `*-polished.png` grid, As-Built PDF room schedule, and `*-rooms-color.json` / `*-colour-sheet.json` match the target floor.
2. **Zone Exclusion Check:** Exclude rooftops (`RF`), sidewalks (`Sidewalk_*`), basements (`1B..4B`), corridors/hallways, stairs, elevator shafts, and balconies.
3. **Engine v2 Watertight + 8-Gate Rebuild:** Pass `watertight`, `stepped_upper`, `non_ortho_steps`, `parapet_zfight`, `overhead_bounds`, `unity_outputs`, `parapet_bounds_clean` (`max_h <= 1.75 m`, zero ceiling-hung wedges or stairwell wall protrusions), and `doorways_unblocked` (cap-guided recovery requires `fresh_noded` support `>= 0.30` so narrow doorways under lintels never brick shut).
4. **Stacked Multi-Floor Wall & Column Continuity:** Pass `audit_stacked_continuity` across `(fl-1, fl, fl+1)` with `missing_m2 == 0`.
5. **Wall & Lintel Room Mask Tracing:** Trace `*-interior-mask.png` from `Floor_Slab - (Wall__Lower | Column__Lower | OverheadBeams | Stairs_Low)` + straight doorway closings + orthogonal column-grid splits (`0` curved watershed bleed).
6. **QA Mask Overlay Inspection:** Visually inspect `mask-qa-<LVL>.png` against `*-rooms-color.png` and `*-polished.png` to verify every designable room ID and wall-snapped border.
7. **Measured Elevation Sync:** Record exact `floorY`, `ceilY`, `ceilingHeight` from `rebuild_manifest.json` in `floor-elevations.json` and sync `.solid_rebuild.glb`.
8. **Single Clean Header & Filter Parity:** Verify `InteriorStudioApp.tsx` exposes only the clean `<select>` floor dropdown with strictly upper interior floors.
9. **Cutaway & Placement Parity Check:** Test `Auto`, `Low`, `Floor`, `Full`, `Stairs`, `Labels`, `Grid`, wall paint, and furniture snap on the floor.
10. **Live Browser Visual Walkthrough:** Capture and inspect live Three.js screenshots per floor (zooming into stairwells and exterior facades) with `0` console errors before sign-off.
