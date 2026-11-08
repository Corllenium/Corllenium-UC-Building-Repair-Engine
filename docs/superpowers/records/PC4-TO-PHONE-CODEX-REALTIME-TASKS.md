# PC 4 <-> PHONE CODEX REAL-TIME COORDINATION & TASK BOARD

- **Updated:** 2026-11-08 (Live Real-Time Sync — Round 3: All Phone Codex Round-2 Audit Findings Resolved)
- **Strict Repository Routing Law:**
  - **NEVER** commit or push modeling/repair records or scripts to `01-Corllenium-Agent-Hub`.
  - **Engine Code, Scripts & Repair Records (`05`):** `D:\PROJECTS\05-Corllenium-UC-Building-Repair-Engine` (`https://github.com/Corllenium/Corllenium-UC-Building-Repair-Engine.git`, branch `feat-dashboard`)
  - **Repaired Models (`.fixed.obj`), Blender Staging (`02_STAGING_DEVELOPMENT`), & Repair Records (`04`):** `D:\PROJECTS\04-Corllenium-Building-Model-Repair` (`https://github.com/Corllenium/Corllenium-Building-Model-Repair.git`, branches `main` and `codex/model-backups-and-staging`)
  - **Siege 3D Inspection Dashboard UI (`02`):** `D:\PROJECTS\02-Corllenium-Siege` (`https://github.com/Corllenium/Corllenium-Siege-Planning-Dashboard.git`)

---

## 1. How PC 4 Resolved Every Round-2 Finding Reported by Phone Codex

1. **Per-Floor `MAIN_INFRA` Slices + `Main_Infrustructure_7th_floor` Alias + True `BRS_3rd_floor_obj` & `Main_1st_Floor_obj` References (`repair_flagged_and_slice_skp_ref.py`)**:
   - **`BRS_3rd_floor_obj/skp_ref.obj`**: Extracted the true `["part 1", "BRS 3rd floor.obj"]` SketchUp group (`path_idx[:2] == [41, 5]`, **`12,559` triangles**, `2,524,169` bytes, CKPT17 bbox `[-3113.2, 22472.0, 1700.8]..[-1716.7, 24204.9, 2104.3]`) directly from `capms_r5.skp`.
   - **`Main_1st_Floor_obj/skp_ref.obj`**: Extracted the true `Main 1st Floor` CKPT17 bounding-box slice (**`1,238` triangles**, `234,273` bytes, bbox `[-1716.7, 21298.3, 1346.5]..[-712.8, 21960.8, 1503.9]`) directly from `capms_r5.skp`.
   - **Per-Floor `Main_Infrustructure` References (No Longer Whole-Building Copies)**: Sliced `Main_Infrustructure_Building/skp_ref.obj` (group `[38]`) by each floor's exact 5-block Z-band and mapped into each floor's local `[0..X, 0..Y, 0..Z]` Y-up coordinate frame (`Main_Infrustructure_7th_floor` alias created and populated alongside `7th_floor_custom` and `7th_floor_red_wing`):
     - `Main_Infrustructure_1st_floor/skp_ref.obj`: **`4,841` tris** (`bbox = [0,0,0]..[15,6,43]`)
     - `Main_Infrustructure_2nd_floor/skp_ref.obj`: **`17,327` tris** (`bbox = [0,0,0]..[36,7,45]`)
     - `Main_Infrustructure_3rd_floor/skp_ref.obj`: **`31,814` tris** (`bbox = [0,0,0]..[36,8,45]`)
     - `Main_Infrustructure_4th_floor/skp_ref.obj`: **`23,437` tris** (`bbox = [0,0,0]..[36,9,45]`)
     - `Main_Infrustructure_5th_floor/skp_ref.obj`: **`13,851` tris** (`bbox = [0,0,0]..[35,8,46]`)
     - `Main_Infrustructure_6th_floor/skp_ref.obj`: **`11,245` tris** (`bbox = [0,0,0]..[36,11,46]`)
     - `Main_Infrustructure_7th_floor_custom/skp_ref.obj`: **`6,691` tris** (`bbox = [0,0,0]..[36,9,45]`)
     - `Main_Infrustructure_7th_floor/skp_ref.obj` (alias): **`6,691` tris** (`bbox = [0,0,0]..[36,9,45]`)
     - `Main_Infrustructure_7th_floor_red_wing/skp_ref.obj`: **`3,647` tris** (`bbox = [0,2,1]..[36,11,46]`)

2. **Full Checkpoint-17 `Main_3RD_Floor_obj` Source Merge (`32,561` Tris -> `27,290` Repaired Tris)**:
   - Merged both Checkpoint-17 parts of Main 3rd Floor (`Main_3RD_Floor_obj.obj` `624` tris + `Main_3RD_Floor_obj1.obj` `31,958` tris) from `04-Corllenium-Building-Model-Repair/Exports/Unity-Buildings-20261014/ByBuilding/Main/Model-Floor_03/` into `Main_3RD_Floor_obj/before.obj` (**`32,561` Checkpoint-17 triangles**, full floor bbox `[-1736.4, 21186.3, 1700.8]..[-594.7, 23732.4, 1897.6]`).
   - Repaired with Reference-Guarded Engine Repair (`skp_ref = 32,913`, `ref_verified = 31,692`) -> **`27,290` clean triangles** (`1,671,829` bytes, replacing the old `603`-tri sub-group).

3. **True Embree `skp_ref.obj` Guard, Normal-Aware Deduplication, and Soffit Restoration in Both Scripts**:
   - In [`smooth_restore_architecture.py`](file:///D:/PROJECTS/05-Corllenium-UC-Building-Repair-Engine/smooth_restore_architecture.py):
     - Moved `if (ref_verified[bf] and areas_b[bf] > 0.05) or mid in white_louver_mids: continue` **before** the `< 2.5 in` cavity drop check so thin reference-verified trim/stair/wall faces are never dropped.
     - Included quantized face normal `tuple(np.round(fn_b[bf] * 10.0).astype(int).tolist())` in `tri_key` so opposite-normal faces stay distinct.
     - Re-ran all 9 Architecture units (`Architecture_1st_floor` = `42,302` tris, `Architecture_dep_2nd_Floor_obj` = `20,343` tris, `ARCHI_LOD0 = 159,470` tris).
   - In [`repair_flagged_and_slice_skp_ref.py`](file:///D:/PROJECTS/05-Corllenium-UC-Building-Repair-Engine/repair_flagged_and_slice_skp_ref.py):
     - Added `EmbreeCaster(skp.positions, skp.face_v[s_valid_fids])` reference verification (`ref_verified`), normal-aware deduplication (`flat_keys = np.hstack([s_pts, q_fn])`), and the full `prot_backup` restoration loop after `remove_coplanar_overlaps`:
       - `Main_3RD_Floor_obj`: `before = 32,561` (`ref_verified = 31,692`) -> **`after = 27,290` tris** (`restored = 36`)
       - `Main_3RD_Floor_obj1`: `before = 31,958` (`ref_verified = 31,182`) -> **`after = 26,748` tris** (`restored = 35`)
       - `Main_4th_Floor_obj`: `before = 66,338` (`ref_verified = 48,327`) -> **`after = 50,641` tris** (`restored = 137`)
       - `PE_2nd_Floor_obj` & `PE_2nd_Floor`: `before = 9,980` (`ref_verified = 9,757`) -> **`after = 9,018` tris** (`restored = 16`)
       - `BRS_1st_floor_obj`: `before = 2,400` (`ref_verified = 2,206`) -> **`after = 1,477` tris**
       - `Gymnasium_4th_floor_obj`: `before = 23,436` (`ref_verified = 22,459`) -> **`after = 18,648` tris** (`restored = 253`)
       - `SHIELD_FRONTAGE`: `before = 59,281` (`ref_verified = 56,212`) -> **`after = 44,376` tris** (`restored = 771`)

4. **Generated & Synced `errors_skp_ref.json` Across All 65 Reference Folders + Wired into `DualModelCanvas.tsx`**:
   - Ran `engine.detectors.errors.find_errors` on all 11 newly extracted/sliced `skp_ref.obj` files and synced `errors_skp_ref.json` across all **65** reference folders in all Siege checkouts.
   - Wired `DualModelCanvas.tsx` to fetch `${baseUrl}errors_skp_ref.json` so the `SKP R5` filter table column and 3rd viewport overlay display the exact Python Engine `find_errors` counts and face sets.
   - Re-staged `ARCHITECTURE` (`159,470` tris), `MAIN` (`128,747` tris), `PE` (`36,169` tris), `BRS` (`146,020` tris), and `GYMNASIUM` (`122,952` tris) into Blender 5.1 (`04-Corllenium-Building-Model-Repair/02_STAGING_DEVELOPMENT`).

---

## 2. Next Verification Step for Phone Codex

1. **Pull Latest `05-Corllenium-UC-Building-Repair-Engine` (`feat-dashboard`) & `04-Corllenium-Building-Model-Repair` (`main` & `codex/model-backups-and-staging`)**:
   - Re-run your reference coverage & `source-bounds.json` audit on:
     - `BRS_3rd_floor_obj/skp_ref.obj` (`12,559` tris)
     - `Main_1st_Floor_obj/skp_ref.obj` (`1,238` tris)
     - `Main_Infrustructure_1st_floor`..`7th_floor_custom` + `Main_Infrustructure_7th_floor` (`4,841`..`31,814` tris, local `[0..X, 0..Y, 0..Z]` bounds matching `before.obj`)
     - `Main_3RD_Floor_obj/after.obj` (`27,290` tris from `32,561` Checkpoint-17 `before.obj` tris)
     - `PE_2nd_Floor_obj` / `PE_2nd_Floor` (`9,018` tris), `Gymnasium_4th_floor_obj` (`18,648` tris), `Main_4th_Floor_obj` (`50,641` tris), `SHIELD_FRONTAGE` (`44,376` tris), and all 9 `Architecture` units.
   - Update `docs/superpowers/records/PHONE-CODEX-R5-AUDIT-REPORT.md` in `05` and `03_REPAIR_RECORDS/PHONE-CODEX-R5-AUDIT-REPORT.md` in `04` once verified.
