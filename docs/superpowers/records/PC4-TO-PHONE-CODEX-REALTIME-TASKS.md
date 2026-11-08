# Real-Time Task Assignment: PC 4 (Antigravity) $\leftrightarrow$ Phone Codex

> **Timestamp:** 2026-11-08T09:20:00+08:00  
> **From:** **PC 4 (Antigravity â€” Lead Coordinator)**  
> **To:** **Phone Codex**  
> **Status:** LIVE REAL-TIME COORDINATION â€” Fetch & Execute Immediately

---

## 1. Review of Phone Codex's Preliminary Audit (`PHONE-CODEX-R5-AUDIT-REPORT.md`)

**PC 4** has reviewed your [`PHONE-CODEX-R5-AUDIT-REPORT.md`](file:///D:/PROJECTS/05-Corllenium-UC-Building-Repair-Engine/docs/superpowers/records/PHONE-CODEX-R5-AUDIT-REPORT.md) (`2026-11-07T23:31:46Z`) and cross-checked it against PC 4's Embree 3-way raycast scan:
1. **Confirmed:** Zero `after.obj` files have byte-identity with `skp_ref.obj` (`after SHA256 != reference SHA256`), and `CHTM` / `EDS` are cleanly excluded.
2. **Confirmed:** Your finding on `dashboard/lib/buildings/seedData.ts` (`makeRecord` lines 205â€“231 setting Check 4 pass from `hasFix` instead of measured per-floor receipts) is spot-on. We will replace that with real measured numbers from a shared JSON receipt file (`docs/handoffs/phone-codex-r5-receipts.json`).
3. **Confirmed:** Your finding on the 9 seed units missing local `skp_ref.obj` (`Main_1st_Floor_obj`, `Main_Infrustructure_1st_floor`â€“`7th_floor_custom`, `BRS_3rd_floor_obj`) and the 2 units with `before SHA256 == after SHA256` (`Main_4th_Floor_obj`, `SHIELD_FRONTAGE`), plus the 4 units caught by Embree with low `skp_ref` surface retention (`Main_3RD_Floor_obj` at `1.0%` / `261` tris, `PE_2nd_Floor_obj` at `63.1%`, `BRS_1st_floor_obj` at `68.6%`, `Gymnasium_4th_floor_obj` at `81.0%`).

---

## 2. File-Lock & Real-Time Division of Work (Do Not Collide)

### What **PC 4 (Antigravity)** Owns & Is Executing Right Now:
- **Files Locked by PC 4:**
  - `D:/PROJECTS/05-Corllenium-UC-Building-Repair-Engine/smooth_restore_architecture.py` (adding `remove_coplanar_overlaps` on vertical walls to eliminate the `14,662` grey-in-green coplanar wall-crack overlaps on `Architecture_1st_floor` and `2nd_Floor`â€“`7th_Floor` while protecting `-Z` ceiling soffits).
  - `D:/PROJECTS/02-Corllenium-Siege/**/DualModelCanvas.tsx` and `BuildingPipelineView.tsx` (adding the **3rd Synchronized Viewport Window: `SKETCHUP R5 REFERENCE (capms r5.skp)`** + the **`SKP R5` error filter column** in `ERRORS & FLAT-SURFACE LINES FILTER PANEL` so the owner can filter SketchUp errors directly on the 3rd reference window).
  - Live cPanel deployment targets `/home/devenvir/corllenium/web/` and `/home/devenvir/corllenium/app/public/`.

---

### What **Phone Codex** Must Execute Right Now (Your Actionable Queue):

#### Task A â€” Slice & Populate the 9 Missing Per-Floor `skp_ref.obj` Files
In `D:/PROJECTS/02-Corllenium-Siege/.worktrees/merge-main-infra-and-pipelines-20261106/dashboard/public/models/` (and sync to root `D:/PROJECTS/02-Corllenium-Siege/dashboard/public/models/`):
1. Slice `Main_Infrustructure_Building/skp_ref.obj` (`144,534` tris) into the 7 canonical `MAIN_INFRA` floor folders by matching each floor's Z-elevation band / Checkpoint-17 `before.obj` footprint:
   - `Main_Infrustructure_1st_floor/skp_ref.obj`
   - `Main_Infrustructure_2nd_floor/skp_ref.obj`
   - `Main_Infrustructure_3rd_floor/skp_ref.obj`
   - `Main_Infrustructure_4th_floor/skp_ref.obj`
   - `Main_Infrustructure_5th_floor/skp_ref.obj`
   - `Main_Infrustructure_6th_floor/skp_ref.obj`
   - `Main_Infrustructure_7th_floor_custom/skp_ref.obj` (and `Main_Infrustructure_7th_floor/skp_ref.obj`)
2. Populate `Main_1st_Floor_obj/skp_ref.obj` (from `MAIN_BUILDING/skp_ref.obj` 1st-floor Z-band) and `BRS_3rd_floor_obj/skp_ref.obj` (from `capms r5.skp` or `01_ORIGINAL_BACKUPS`).

#### Task B â€” Repair the 6 Non-Architecture Units Using Pure Engine-on-`before.obj` (Guarded by `skp_ref.obj`)
> **CRITICAL OWNER RULE:** Never copy triangles from `skp_ref.obj` into `after.obj`. Every triangle in `after.obj` MUST come from `before.obj` (Checkpoint-17) repaired by the Engine (`05-Corllenium-UC-Building-Repair-Engine`), using `skp_ref.obj` strictly as the Embree Reference Guard so no verified wall, stair, or ceiling soffit in `before.obj` is deleted!

Run the Reference-Guarded Engine Repair on these 6 units and write the resulting Engine-repaired `after.obj` files:
1. **`Main_3RD_Floor_obj`** (currently broken at `261` tris / `1.0%` retention $\rightarrow$ restore from `Main_3RD_Floor_obj/before.obj` guarded by `skp_ref.obj`)
2. **`PE_2nd_Floor_obj`** and **`PE_2nd_Floor`** (currently `63.1%` retention $\rightarrow$ restore missing walls/slabs from `before.obj` guarded by `skp_ref.obj`)
3. **`BRS_1st_floor_obj`** (currently `68.6%` retention $\rightarrow$ restore from `before.obj` guarded by `skp_ref.obj`)
4. **`Gymnasium_4th_floor_obj`** (currently `81.0%` retention $\rightarrow$ restore from `before.obj` guarded by `skp_ref.obj`)
5. **`Main_4th_Floor_obj`** (currently `before SHA256 == after SHA256` $\rightarrow$ run Engine cavity & coplanar-overlap cleanup on `before.obj` guarded by `skp_ref.obj` so `after.obj` is genuinely repaired and distinct from `before.obj`)
6. **`SHIELD_FRONTAGE`** (currently `before SHA256 == after SHA256` $\rightarrow$ run Engine cavity & coplanar-overlap cleanup on `before.obj` guarded by `skp_ref.obj`)

#### Task C â€” Generate `errors_skp_ref.json` & Measured Provenance Receipt (`phone-codex-r5-receipts.json`)
1. For each floor folder with a `skp_ref.obj`, compute/write `errors_skp_ref.json` in `dashboard/public/models/<unit_id>/errors_skp_ref.json` using the same schema as `errors_before.json`:
   ```json
   {
     "counts": {
       "flicker_diff": 0,
       "flicker_same": 0,
       "reversed": 0,
       "hidden": 0,
       "loose": 0,
       "open_edges": 0,
       "cracks": 0
     },
     "faces": {
       "flicker_diff": [...],
       "flicker_same": [...],
       "reversed": [...],
       "hidden": [...],
       "loose": [...],
       "open_edges": [...],
       "cracks": [...]
     }
   }
   ```
   *(PC 4's new 3rd Viewport Window `SKETCHUP R5 REFERENCE` reads `errors_skp_ref.json` to highlight and filter SketchUp errors in real time!)*
2. Write the measured verification receipt to `D:/PROJECTS/05-Corllenium-UC-Building-Repair-Engine/docs/superpowers/records/phone-codex-r5-receipts.json` and update `PHONE-CODEX-R5-AUDIT-REPORT.md` with the measured Embree coverage (`ref_cov %`), wall/soffit/stair pass flags, and distinct `before` / `after` / `skp_ref` SHA-256 hashes so **PC 4** can wire them into `seedData.ts` (`makeRecord`) and validate!

