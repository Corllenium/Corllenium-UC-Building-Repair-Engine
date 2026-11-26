# Handoff: Why Post-Repair Triangle Issues Happen (Engine → Blender → Unity) & How to Fix Them Permanently

- **Date:** `2026-11-25`
- **Scope:** Universal across **ALL** UC campus buildings & floors (`CHTM`, `ARCHITECTURE`, `BRS`, `EDS`, `GYMNASIUM`, `MAIN`, `MAIN_INFRA`, `PE`, `SCIENCE_A`, `SITE`) — not Architecture-only.
- **Primary Engine Repo (`05`):** `D:/PROJECTS/05-Corllenium-UC-Building-Repair-Engine` (`feat-dashboard` @ `f938d082`)
- **Dashboard Repo (`02`):** `D:/PROJECTS/02-Corllenium-Siege/.worktrees/arch-whole-r5-20261122` (`feat/architecture-whole-r5-repair` @ `06437db6`, live at https://corllenium.ai.dev-environment.site/pipelines/jev-repair?building=ARCHITECTURE&unit=Architecture_Whole_Building_R5)
- **Agent Hub Skill Repo (`01`):** `D:/PROJECTS/01-Corllenium-Agent-Hub` (`main` @ `846cb46f` — `.agents/skills/uc-post-fix-visual-qa/SKILL.md`)
- **Reference Benchmark Output (`Architecture_Whole_Building_R5`):**
  - Frozen `BEFORE`: `D:/PROJECTS/05-Corllenium-UC-Building-Repair-Engine/data/architecture_whole_r5/before/before.obj` (`125,285` tris)
  - Repaired `AFTER`: `D:/PROJECTS/05-Corllenium-UC-Building-Repair-Engine/data/architecture_whole_r5/after/after.obj` (`70,780` tris, `-43.50%`, `flicker=0/0`, `reversed=0`, `zero_area=0`, `needle_slivers=0`, `9/10` Stage 5 checks passing)
  - Rebuilt Blender 5.1 File: `D:/PROJECTS/06-Environment-Authoring/.work/architecture-slope-removal-20261122/architecture_r5_engine_v2_fixed.blend` (`70,768` polys, `32` packed materials, `mesh.validate() == False`)
  - Official Building Record: `D:/PROJECTS/05-Corllenium-UC-Building-Repair-Engine/docs/superpowers/records/ARCHITECTURE-WHOLE-BUILDING-R5-RECORD.md`

---

## 1. Root Causes: Why Triangle Issues Still Appear After the Repair Engine Runs

Every post-fix visual defect observed across the 16-class Reference KB (`docs/defect-reference-kb/`, `D01`–`D16` + `G01`–`G02`) traces back to **6 exact geometric/pipeline root causes** inside the repair engine, plus **5 Unity-specific reasons** why broken triangles, hairline cracks, or unmerged seams still show up after importing into Unity 6 URP.

### A. Repair Engine Root Causes (Why Faces Break, Shred, or Stay Unmerged)

1. **Wrong Stage Order — Unmerged SketchUp Fragments Go Straight Into `Hidden` & `Flicker`**
   - **What happens:** Raw SketchUp / Minecraft LittleTiles exports deliver flat floors and walls as fragmented overlapping rectangles mixed with buried concrete wall-caps (`Red = Flicker Diff`, `Blue = Hidden Inside`).
   - **Why it breaks:** When `Hidden Inside` runs *before* flat coplanar tiles are merged and synced, it deletes overlapping cap strips (opening dark rectangular slots + leaving paper-thin vertical fins standing alone). When loopback restores missing faces and runs `iterative_flicker_convergence` without re-sealing notches or re-syncing floor islands, flat `quartz_block_top` floors stay sliced into separate rectangles with embedded grey concrete strips (`D09`).
   - **Mitigation already wired:** `pre_merge_coplanar`, `fill_wall_cap_notches`, and `heal_floor_material_islands` in `engine/fixes/building_repair.py`.

2. **The `merge_regions` Re-Triangulation Trap (Why Running Merge Last Breaks the Model!)**
   - **Measured proof (`Architecture_Whole_Building_R5`, `task-2214`):**
     - Immediately *before* `merge_regions`: `70,647` tris, **`0 / 0` flicker**.
     - Immediately *after* running `merge_regions` across all materials: mesh **grew `+1,878` tris (`70,647 → 72,525`)**, **re-introduced `94 diff / 109 same` overlapping flicker pairs**, and created **`778` razor-thin boundary needle slivers**!
   - **Why:** On complex multi-story non-convex regions with interior holes, T-junction vertices, or tiny near-collinear boundary steps, Earcut/Delaunay re-triangulation bridges across concave notches (creating overlapping triangles) and emits extreme-aspect boundary slivers (`width < 0.2 in`, `len > 150 in`).
   - **Hard Rule:** **NEVER leave `merge_regions` as the final geometry stage.** Always run `remove_coplanar_overlaps` / `iterative_flicker_convergence` *after* `merge_regions`, or restrict `merge_regions` to strictly simple/verified planar regions that pass a post-merge zero-overlap guard.

3. **`E5` Boolean Trimming Creates Hairline Slivers — and Blunt Sliver Deletion Shreds Railings & Walls (`D02`, `D03b`, `D16`)**
   - **What happens:** When `E5` boolean-trims overlapping coplanar surfaces (e.g., vertical balusters intersecting a `3 in × 120 in` horizontal black steel railing bar, or overlapping dark-green wall skins), it slices thin bars into acute triangles (`1–2.5 in` wide × `60–120 in` long, aspect `20–50`).
   - **Why blunt deletion failed:** Running `purge_piercing_needle_slivers(aspect_min=16, max_altitude_in=2.5, max_area_sqin=25)` deleted `1,043` triangles — mistaking real steel railing bars and coplanar dark-green wall strips for "slivers", slicing diagonal right-triangles out of bottom rails (`D16`) and ripping diagonal grey slits through dark-green exterior walls (`D03b`).
   - **Why blind `EXP_OUTSIDE` protection also failed:** Shielding every exterior face prevented deleting genuine `0.03 in × 71 in` and `0.11 in × 274 in` degenerate E5 spikes sitting on the outer shell.
   - **Hard Rule (Zero-Hole Safety Law — implemented in `engine/fixes/patch_protect.py`):**
     - Flag ONLY true degenerate spikes: **`min_altitude <= 0.35 in` (`< 9 mm`)**, **`aspect >= 50.0`**, **`area <= 12.0 sq in`**, AND **`~has_coplanar_neighbor`** (zero shared-edge coplanar same-material neighbors, `dot >= 0.98`).
     - Real railings, balusters, handrails, louver blades (`5.1 in × 1.19 in`), and coplanar wall strips are **100% immune** (`14/14` unit tests passing in `tests/test_facade_integrity.py`).

4. **Diagonal Missing Half-Quads, Baseboards & Column Cutouts (`D04`, `D06`, `D07`, `D12`, `D14`)**
   - **Why:** Embree ray visibility sampling can hit triangle `T1` of a rectangular wall/column/baseboard quad and narrowly miss its coplanar twin `T2` near a corner or stair junction, deleting `T2` along the 45° diagonal.
   - **Mitigation wired:** `propagate_coplanar_patch_reachability` (`max_hops=3, normal_dot_min=0.998`) in `engine/fixes/patch_protect.py` + conflict-safe mandatory in-run `restore_destroyed_facade_faces` in `engine/validate/diff_overlay.py` (clears buried coplanar duplicates *before* restoring lost visible faces so flicker convergence does not re-delete them).

5. **Zebra Diagonal Texture Swaps & Floor Concrete Overrides (`D08`, `D09`)**
   - **Why:** On `0.000 in` coplanar pairs (e.g., white `littletiles` louver walls over dark-green concrete, or `quartz_block_top` floor over concrete wall-caps), Embree `first_hit` tie-breaking flips triangles randomly into zebra stripes or concrete floor patches.
   - **Mitigation wired:** 2-pass coplanar reachability propagation + `_finish_tier` material priority + `heal_floor_material_islands` (with affine UV transfer) → reduced texture swaps on Architecture R5 from `1,601` down to **`4` (`0.04%`)**.

6. **Hollow Wall Cavities (`G01`) vs. Real Visible Holes (`D14`)**
   - **Why:** Cleaning trapped internal trash inside double-skin walls and floor slabs (`G01` Clean Wall Pipeline Law, keeping solid columns `G02` unbroken) removes buried wall-bottom/top caps, creating benign 90° `EDGE_OPEN` edges sealed behind perpendicular floors/columns.
   - **Mitigation wired:** `engine/validate/hole_detector.py` (`detect_new_mesh_holes(..., visible_only=True)`) requires **both** `covered_after == False` **and** `existed_before == True` on a **visible** (`EXP_OUTSIDE | room_visible`) host face — cutting cavity false positives by `80%` (`3,792 → 741` visible loops).

---

### B. Why Triangle Issues STILL Show Up Even After Importing Into Unity 6 (URP)

Even after a model looks clean in Blender solid view or passes `0/0` flicker in the engine, **5 Unity-specific behaviors** expose remaining triangle problems:

1. **Unity Always Re-Triangulates Everything + Exposes T-Junction Cracks (`cracks: 32,136` on Arch R5)**
   - Unity's GPU pipeline **never renders quads or N-gons** — FBX/OBJ import splits every polygon into triangles.
   - When a repaired wall or floor meets an adjacent slab/column without sharing the exact split vertex (**T-junction**), floating-point precision differences along the split edge vs. unsplit edge open **1-pixel shimmering pinhole/hairline cracks** showing skybox or dark interior void as the player moves in Unity.
   - **Why the engine hasn't eliminated all T-junctions yet:** `merge_regions` and `E5` planar trimming operate *per coplanar plane cluster*, not across orthogonal intersecting planes, so vertices introduced on a floor don't get inserted into the touching vertical wall edge (and vice versa).

2. **Single-Sided Backface Culling (`_Cull = Back`) in Unity URP**
   - SketchUp and Blender Workbench default to rendering both sides of a face (`DoubleSide`). Unity URP standard Lit shaders cull backfaces by default.
   - Any single remaining reversed normal (`E2`) or single-skin wall turns **completely invisible** from one side in Unity (which is why Stage 5 Check `#7` strictly enforces `reversed == 0`).

3. **Near-Coplanar Z-Fighting at Distance (`1–5 mm` Depth Buffer Precision)**
   - The repair engine resolves **exact coplanar overlaps** (`0.000 in` / `< 0.12 in`). However, two distinct surfaces spaced `2–10 mm` apart (e.g., a wall finish skin over a slightly recessed concrete slab, or a floor slab underside close to a ceiling below) look clean up close in Blender, then **z-fight/flicker violently** at 20–100 m in Unity (especially WebGL/URP with tight `Near Clip = 0.05` and large `Far Clip = 1000+`).

4. **Split Vertices Across Material / UV Seams & Unwelded Micro-Gaps (`open_edges: 16,690`)**
   - OBJ format separates vertex positions (`v`) from UV coordinates (`vt`), and Unity splits vertices whenever UVs, normals, or submesh material IDs differ. If two adjacent triangles have `0.1–0.5 mm` position drift (unwelded), Unity renders a visible seam crease, leaks light through baked/realtime shadows, and flags non-manifold edges.

5. **PhysX `MeshCollider` & Shadow Bias Artifacts on Remaining Thin/Sliver Triangles**
   - Even non-degenerate narrow triangles (`0.4–1.0 in` wide along long walls or stairs) can cause Unity PhysX `MeshCollider` cooking warnings, player foot snagging on stair treads, or dark shadow-acne triangles under URP directional shadows when `Normal Bias` pushes shadow rays past thin geometry.

---

## 2. Current Verified Pipeline State (Where We Left Off)

| Repo | Branch | Verified HEAD | Status |
| :--- | :--- | :--- | :--- |
| **`05-Corllenium-UC-Building-Repair-Engine`** | `feat-dashboard` | `f938d082` | `14/14` pytest passing (`test_facade_integrity.py` + `test_building_repair.py`); universal `building_repair.py`, `patch_protect.py`, `facade_integrity.py`, `diff_overlay.py`, `hole_detector.py`, `D01`–`D16` + `G01`–`G02` KB, and `ARCHITECTURE-WHOLE-BUILDING-R5-RECORD.md` pushed. |
| **`02-Corllenium-Siege`** | `feat/architecture-whole-r5-repair` *(unmerged to `main`)* | `06437db6` | Live on cPanel (`/api/health` verified); Pascal 3D Editor removed; 9 old per-floor Architecture units deleted (`Architecture_Whole_Building_R5` is sole Architecture unit); Merged 3D Ghost-Facade Diff + Skeleton X-Ray/Wireframe + 5 color filters (`Red` Missing Outer, `Orange` Missing Interior, `Cyan` Cleaned Trash, `Magenta` After Errors, `Yellow` Visible Void-Leak Holes) live. |
| **`01-Corllenium-Agent-Hub`** | `main` | `846cb46f` | `.agents/skills/uc-post-fix-visual-qa/SKILL.md` pushed. |

### `Architecture_Whole_Building_R5` Latest Verified Metrics
- **Triangles:** `125,285 → 70,780` (`-43.50%`) · **Rebuilt `.blend`:** `70,768` polys, `32` mats, `mesh.validate() == False`
- **Stage 5 Gate (`9 / 10 PASS`):**
  - **PASS:** `#1` Outer Facade (`99.96%`), `#3` Interior Visible (`99.09%`), `#4` Zero Needle Slivers (`0` slivers, `0` zero-area), `#5` Stair & Floor (`99.79%`), `#6` Zero Flicker (`0/0`), `#7` Zero Reversed (`0`), `#8` Texture Fidelity (`0.04%`), `#9` Blender Topology (`invalid=False`), `#10` AI Visual QA (`6` headless Blender 5.1 renders inspected, `0` blocking defects).
  - **Remaining Flag (`1`):** `#2` reports `2` `29.53 in` open edges at `[5500.7, -2019.7, 590.6]` & `[5503.8, -2029.1, 610.2]` — visually confirmed in `arch_r5_qa_05_seam_closeup.png` to be the clean open cutaway boundary against the adjacent Main building (not a wall crack).
- **Remaining Visible Diagnostics (`diff_overlay.json`):** `741` visible void-leak open-edge loops (`679` edge slits, `36` triangle holes, `16` quad notches, `10` polygon holes), `16,690` open edges, `32,136` T-junction cracks.

---

## 3. Exact Next Steps for the Next Agent / Unity-Ready Upgrade Phase

To make repaired buildings **100% clean not only in Blender/Dashboard, but ALSO rock-solid inside Unity 6 URP**, execute these 5 targeted engineering upgrades in `05-Corllenium-UC-Building-Repair-Engine`:

1. **Add Cross-Plane T-Junction Vertex Stitching (`engine/fixes/tjunction_stitch.py`)**
   - After final overlap convergence (when `flicker == 0/0`), snap vertices within `0.05 in` (`~1.2 mm`) and split any triangle edge that passes within `0.03 in` of a neighboring face's vertex (`T-vertex insertion`), reducing `cracks: 32,136 → ~0` so Unity never opens 1-pixel skybox pinholes along wall-floor-column junctions.
2. **Add Planar Visible-Hole Auto-Capper (`engine/fixes/cap_visible_holes.py`)**
   - Feed the `visible_only=True` closed planar loops from `detect_new_mesh_holes` (`36` triangle holes, `16` quad notches, `10` polygon holes on Arch R5) into a constrained planar triangulator that inherits host material + affine UV from the surrounding wall/floor and re-verifies `flicker == 0/0` + `reversed == 0`.
3. **Add Near-Coplanar Z-Fighting Guard for Unity Depth Buffer (`0.01–0.30 in` Parallel-Offset Check)**
   - Extend `find_errors` / `iterative_flicker_convergence` with an optional Unity-safe near-coplanar check (`dist <= 0.25 in`, `|dot(n)| > 0.99`, overlapping area `> 30%`, one face buried/non-visible) so thin double-layered wall skins don't shimmer at 50 m in Unity URP/WebGL.
4. **Add Unity Export Pre-Flight Check (`engine/validate/unity_export_gate.py`)**
   - Before shipping `.fbx`/`.glb` to `03-Corllenium-UC-Game`: verify (a) meter-scale transform (`1/39.37007874`), (b) `reversed == 0` under single-sided backface culling, (c) `zero_area == 0` & `min_alt >= 0.002 m` for clean PhysX `MeshCollider` cooking, (d) UV channels present on all textured submeshes, and (e) `mesh.validate() == False` in headless Blender.
5. **Decide Owner Sign-Off & Merge:**
   - Decide whether Stage 5 Check `#2` should exclude open cutaway boundary seams (where a building meets an adjacent building) so `Architecture_Whole_Building_R5` hits `10/10 PASS` and unlocks Stage 6 Blender Staging.
   - Owner approval to merge `02-Corllenium-Siege` branch `feat/architecture-whole-r5-repair` (`06437db6`) into `main`.
   - Separate open Blender GUI item: `SKP_Harrison_Sidewalk` ↔ `Arch_1F` doorway threshold in `D:/PROJECTS/06-Environment-Authoring/BLENDER/UC-Game-Merged-Buildings-Sidewalk-v3-20261119.blend`.
