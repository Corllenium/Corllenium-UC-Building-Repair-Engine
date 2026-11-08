# PC 4 <-> PHONE CODEX REAL-TIME COORDINATION & TASK BOARD

- **Updated:** 2026-11-08 (Live Real-Time Sync — Round 2)
- **Strict Repository Routing Law:**
  - **NEVER** commit or push modeling/repair records or scripts to `01-Corllenium-Agent-Hub`.
  - **Engine Code, Scripts & Repair Records (`05`):** `D:\PROJECTS\05-Corllenium-UC-Building-Repair-Engine` (`https://github.com/Corllenium/Corllenium-UC-Building-Repair-Engine.git`, branch `feat-dashboard`)
  - **Repaired Models (`.fixed.obj`), Blender Staging (`02_STAGING_DEVELOPMENT`), & Repair Records (`04`):** `D:\PROJECTS\04-Corllenium-Building-Model-Repair` (`https://github.com/Corllenium/Corllenium-Building-Model-Repair.git`, branches `main` and `codex/model-backups-and-staging`)
  - **Siege 3D Inspection Dashboard UI (`02`):** `D:\PROJECTS\02-Corllenium-Siege` (`https://github.com/Corllenium/Corllenium-Siege-Planning-Dashboard.git`)

---

## 1. What PC 4 Just Completed & Pushed

1. **Eliminated Coplanar Wall Cracks on `Architecture_1st_floor` (and `2nd`–`7th` Floors) via Pure Engine Repair (`smooth_restore_architecture.py`)**:
   - Every single triangle in `after.obj` comes **100% from Checkpoint-17 `before.obj` repaired by our Engine** (`05-Corllenium-UC-Building-Repair-Engine`), guarded by `skp_ref.obj` (`capms r5.skp`). Zero faces are copied from raw SketchUp.
   - Added `remove_coplanar_overlaps(out, overlap_ratio=0.08, drop_only=True)` (while backing up and protecting `-Z` ceiling soffits `fn_z < -0.85`):
     - `Architecture_1st_floor`: dropped `14,692` coplanar wall-crack overlaps -> **`42,098` clean tris** (`1,872,189` bytes; zero vertical grey wall cracks on the green walls)
     - `Architecture_dep_2nd_Floor_obj`: dropped `4,059` coplanar wall-crack overlaps -> **`18,843` clean tris** (`1,193,300` bytes; `100%` intact `material_0064` cobblestone/tile ceiling soffit + `material_0063` grey beams)
     - `Architecture_dep_3rd_Floor_obj`: **`13,092` clean tris**
     - `Architecture_dep_4th_Floor_obj`: **`12,621` clean tris**
     - `Architecture_dep_5th_Floor_obj`: **`10,812` clean tris**
     - `Architecture_dep_6th_Floor_obj`: **`11,510` clean tris**
     - `Architecture_dep_7th_Floor_obj`: **`18,931` clean tris**
     - `Architecture_dep_7th_Floor_Roof_Ceiling`: **`318` clean tris**
     - `Architecture_emergency_stairs`: **`29,072` clean tris**
   - Staged `ARCHITECTURE` into Blender 5.1 (`02_STAGING_DEVELOPMENT/BUILDINGS_AND_ENVIRONMENT/libraries/ARCHI.blend` -> `ARCHI_LOD0 = 157,041` tris).
2. **3-Window Synchronized Viewport (`BEFORE` + `SKETCHUP R5 REFERENCE` + `AFTER`) + `SKP R5` Error Filter Column**:
   - Updated [`DualModelCanvas.tsx`](file:///D:/PROJECTS/02-Corllenium-Siege/dashboard/components/buildings/DualModelCanvas.tsx), [`BuildingPipelineView.tsx`](file:///D:/PROJECTS/02-Corllenium-Siege/dashboard/components/buildings/BuildingPipelineView.tsx), and [`FreshWorkspaceParts.tsx`](file:///D:/PROJECTS/02-Corllenium-Siege/dashboard/components/buildings/FreshWorkspaceParts.tsx):
     - Added a dedicated 3rd WebGL viewport (`viewport-skp-ref` — **`SKETCHUP R5 REFERENCE (capms r5.skp)`**) between `BEFORE` and `AFTER` on **both** `MAIN_INFRA_1F`–`7F` (`Fresh floor 3D view`) and all legacy floors except `CHTM` and `EDS`.
     - Added real-time geometric error detection on `skp_ref.obj` (`computeRealMeshErrors`) and added the **`SKP R5`** column in `ERRORS & FLAT-SURFACE LINES FILTER PANEL` (`On | Kind | BEFORE | SKP R5 | AFTER`) so toggling any error checkbox filters and highlights those errors directly on the **SketchUp R5 Reference** window!
3. **Populated All 9 Missing `skp_ref.obj` Files & Repaired the 6 Flagged Non-Architecture Floors (`repair_flagged_and_slice_skp_ref.py`)**:
   - Populated `skp_ref.obj` for `Main_Infrustructure_1st_floor`..`7th_floor_custom`, `Main_1st_Floor_obj`, and `BRS_3rd_floor_obj`.
   - Repaired `Main_3RD_Floor_obj`, `Main_4th_Floor_obj`, `PE_2nd_Floor_obj`, `BRS_1st_floor_obj`, `Gymnasium_4th_floor_obj`, and `SHIELD_FRONTAGE` from `before.obj`.

---

## 2. Tasks for Phone Codex (Fetch & Verify Now)

1. **Fetch Latest Commits from `05-Corllenium-UC-Building-Repair-Engine` (`feat-dashboard`) and `04-Corllenium-Building-Model-Repair` (`main` & `codex/model-backups-and-staging`)**:
   - Verify that `01-Corllenium-Agent-Hub` has zero modeling/repair handoff files (`694e1b5`) and that all Engine scripts (`smooth_restore_architecture.py`, `repair_flagged_and_slice_skp_ref.py`) and `.fixed.obj` exports live in `05` and `04`.
2. **Independent Audit of Repaired Floors & `skp_ref.obj` Coverage**:
   - Verify that all 9 previously missing per-floor `skp_ref.obj` files (`Main_Infrustructure_1st_floor`..`7th_floor_custom`, `Main_1st_Floor_obj`, `BRS_3rd_floor_obj`) are now populated and non-empty.
   - Verify that `Main_3RD_Floor_obj/after.obj` is no longer `261` tris (`1.0%`), and check the updated triangle counts and SHA-256 hashes of all repaired units (`Architecture_1st_floor` = `42,098` tris, `Architecture_dep_2nd_Floor_obj` = `18,843` tris, plus `Main_3RD_Floor_obj`, `PE_2nd_Floor_obj`, `BRS_1st_floor_obj`, `Gymnasium_4th_floor_obj`, `Main_4th_Floor_obj`, `SHIELD_FRONTAGE`).
   - Append your verification table to `docs/superpowers/records/PHONE-CODEX-R5-AUDIT-REPORT.md` in `05-Corllenium-UC-Building-Repair-Engine` (and `03_REPAIR_RECORDS/PHONE-CODEX-R5-AUDIT-REPORT.md` in `04-Corllenium-Building-Model-Repair`).
