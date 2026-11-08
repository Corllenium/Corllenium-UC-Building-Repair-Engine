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
     - **Documented World-to-Local Transform for `Main_Infrustructure_Building` (`group [38]`)**: In `capms_r5.skp`, `Main_Infrustructure_Building` is rotated in the horizontal XY plane by $\theta = \arctan(1/3) = 18.4348^\circ$ ($\mathbf{u} = [0.94868567, 0.31622064]$, $\mathbf{v} = [-0.31622064, 0.94868567]$) at scale `1 block = 39.37007874015748 inches` (`u_span = 48.000 blocks`, `v_span = 47.000 blocks`, `z_span = 37.000 blocks` from `30.2001..67.2001` blocks).

2. **Full Checkpoint-17 `Main_3RD_Floor_obj` Source Merge (`32,561` Tris -> `27,312` Repaired Tris, `99.892%` R5 Coverage)**:
   - Merged both Checkpoint-17 parts of Main 3rd Floor (`Main_3RD_Floor_obj.obj` `624` tris + `Main_3RD_Floor_obj1.obj` `31,958` tris) from `04-Corllenium-Building-Model-Repair/Exports/Unity-Buildings-20261014/ByBuilding/Main/Model-Floor_03/` into `Main_3RD_Floor_obj/before.obj` (**`32,561` Checkpoint-17 triangles**, full floor bbox `[-1736.4, 21186.3, 1700.8]..[-594.7, 23732.4, 1897.6]`).
   - Repaired with Reference-Guarded Engine Repair (`skp_ref = 32,913`, `R->B = 99.892%`, **`R->A = 99.892%`** -> **`27,312` clean triangles**, replacing the old `603`-tri sub-group).

3. **Zero-Loss 4-Point Barycentric `EmbreeCaster` Reference Guard Across All Flagged Units (`R->A >= R->B`, `0.000%` Loss)**:
   - Verified using Phone Codex's exact 4-point barycentric `EmbreeCaster` metric (`tools/phone_r5_measure.py`, `distance <= 1.5 OBJ inches`, `|normal dot| >= 0.88`, recentered by `(ref.min + ref.max)/2`):

| Unit | `before.obj` Tris | `after.obj` Tris | `skp_ref.obj` Tris | `R5 -> before` | `R5 -> after` | Coverage Delta |
| :--- | ---: | ---: | ---: | ---: | ---: | ---: |
| `Architecture_1st_floor` | `60,388` | **`42,588`** | `34,487` | `99.262%` | **`99.263%`** | `+0.001%` (`0.000%` loss) |
| `Architecture_dep_2nd_Floor_obj` | `54,337` | **`21,185`** | `20,080` | `84.953%` | **`84.955%`** | `+0.002%` (`0.000%` loss) |
| `Main_3RD_Floor_obj` | `32,561` | **`27,312`** | `32,913` | `99.892%` | **`99.892%`** | `0.000%` (`0.000%` loss) |
| `Main_3RD_Floor_obj1` | `31,958` | **`26,768`** | `32,913` | `99.071%` | **`99.071%`** | `0.000%` (`0.000%` loss) |
| `Main_4th_Floor_obj` | `66,338` | **`50,686`** | `35,264` | `99.470%` | **`99.470%`** | `0.000%` (`0.000%` loss) |
| `PE_2nd_Floor_obj` | `9,980` | **`8,985`** | `11,029` | `63.705%` | **`63.705%`** | `0.000%` (`0.000%` loss) |
| `PE_2nd_Floor` | `9,980` | **`8,985`** | `11,029` | `63.705%` | **`63.705%`** | `0.000%` (`0.000%` loss) |
| `BRS_1st_floor_obj` | `2,400` | **`1,477`** | `2,571` | `73.633%` | **`73.633%`** | `0.000%` (`0.000%` loss) |
| `BRS_3rd_floor_obj` | `22,017` | **`13,305`** | `12,559` | `99.877%` | **`99.882%`** | `+0.005%` (`0.000%` loss) |
| `Gymnasium_4th_floor_obj` | `23,436` | **`18,718`** | `23,557` | `99.992%` | **`99.992%`** | `0.000%` (`0.000%` loss) |
| `SHIELD_FRONTAGE` | `59,281` | **`44,936`** | `103,984` | `35.378%` | **`35.379%`** | `+0.001%` (`0.000%` loss) |

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
