# SketchUp export (K1, K2): report

Branch `feat/skp-export` (worktree `.claude/worktrees/skp-export`), from feat-dashboard `e57462d`.

| item | commit |
|---|---|
| K1 `feat(engine): SketchUp writer with polygon faces, inner loops, soft creases, materials` | `e97443e` |
| K2 `feat(engine): fix CLI writes the latest .skp for the user` | `d24da30` |
| this report | (the commit that adds this file) |

Engine suite from the worktree root: `353 passed` (345 after K1, plus 8 CLI tests in K2).

## What was built

**K1: `engine/io/skp_writer.py`.** This is the only module in `engine/` that imports ctypes, and a test enforces that. It writes the fixed mesh through SketchUp's own C API and reads files back through the same API.

- **Faces.** Each merged region becomes one SketchUp face. Rows are grouped by ring OBJECT identity, exactly as `write_obj_polygons` groups them. The outer loop is `rings[r]["outer"]` and each of `inners` becomes an inner loop via `SUGeometryInputFaceAddInnerLoop`. Every row not in a written region is its own triangle.
  - Ring ids are original row ids (the same numbering as `mesh.face_v`, lowest row per welded vertex).
  - They are welded with the engine's own `weld_exact(positions, coord_decimals)`, so vertex ids match `topo`'s edge table.
  - Each welded vertex keeps its original position, so coordinates pass through unchanged (inches, Z up).
  - `SUEntitiesFill` runs with `weld_vertices=true`.
- **Regions written as triangles instead,** each listed in `fallback_regions` with a reason:
  - `no_inner_loop_api`: the DLL lacks the inner-loop call.
  - `degenerate_loop`: a loop keeps fewer than 3 distinct vertices.
  - `nonplanar`: the loop vertices are more than `plane_tol` = 1e-3 in off their least-squares plane.
  - `rejected_by_sketchup`: SketchUp refuses or drops the polygon at the fill.
  - `split_by_sketchup`: SketchUp's save still splits it.
  - The last two are found by matching SketchUp's own faces against the plan, after the fill and again after the save. The model is then rebuilt from scratch.
- **Skipped faces.** A zero-area or collapsed triangle is skipped and counted (`degenerate_faces_skipped`). SketchUp would drop it silently and could leave stray edges.
- **Orientation.** After the fill, each face's normal is compared with the area-weighted normal of its own triangles. A backwards face is reversed with `SUFaceReverse` and its texture is re-positioned on both sides with `SUFacePositionMaterial`.
- **Hidden edges.** Every EDGE_SOFT and EDGE_REMOVABLE edge (class 5 and class 1 of `analyse_topology` on the SHIPPED mesh) that exists in the SketchUp model is set soft AND smooth. That excludes the diagonals inside one polygon face, which SketchUp does not have. Edges are matched by welded endpoint ids, and each endpoint is confirmed within 1e-6 in of the vertex it matches. Counts: `soft_edges`, `gridline_edges_softened`, `unmatched_edges`.
- **Materials.** There is one SketchUp material per `mesh.materials` entry.
  - It is textured from `<tex_dir>/<file name of map_Kd>` when that file exists. Otherwise it takes the `Kd` colour, or grey (204, 204, 204) when there is neither.
  - The material is applied to the FRONT and the BACK through `SUGeometryInputFaceSetFront/BackMaterial` (**material path: `geometry_input`**).
  - It is positioned with `SUMaterialInput` using 3 non-collinear loop vertices and their UVs. Each ring vertex's UV is taken from any of the region's triangles.
  - `uv_residual_regions` lists polygon faces whose triangles' UVs are not one affine map to within 1e-3.
- **Read-back functions.**
  - `read_skp` returns faces (loops, normal, front/back material, UVs on each side, SketchUp's own triangulation), edges (endpoints, soft, smooth, face count) and materials.
  - `read_skp_summary` is derived from `read_skp`.
  - `check_skp_validity` runs SketchUp's own `SUModelFixErrors` on the in-memory model and reports whether anything changed. It never saves.
  - All three open the file with `SUModelCreateFromFile`.
- **DLL.** The path comes from the `dll_path` argument, else `$FIXER_SKETCHUP_DLL`, else the SketchUp 2026 default. Every symbol is checked with `hasattr` on the loaded DLL before it is bound, and anything missing raises `SketchUpUnavailable` naming it.

**K2: `engine/cli.py`.**
- `fix` writes `<run dir>/<name>.fixed.skp` and copies it, replacing the previous copy, to `default_skp_dir()`, which is `<repo root>/OBJ FIXED RESULT`. The repo root is the folder holding the imported `engine` package.
- `--skp-dir` names another folder, and `--no-skp` skips the `.skp`.
- `main()` passes the default folder. A direct `cmd_fix(...)` call copies nowhere unless `skp_dir` is given, so the test suite never writes into the repo (verified: no `OBJ FIXED RESULT` folder after the suite).
- When SketchUp is unavailable or any API call fails, the run still succeeds, `report.json` `skp` is `{"written": false, "reason": ...}`, and no stale `.skp` is left in the run dir.
- On success, `skp` is the whole `write_skp` report plus `written`, `copied_to` (and `copy_error` if the copy failed, e.g. the file is locked) and `sketchup_check_changed`.
- `OBJ FIXED RESULT/` is git-ignored (`git check-ignore` confirms it).

### Deviations from the brief, and why

1. **Signature.** `write_skp(mesh, rings, face_region, topo, mtl_materials, path, *, tex_dir=None, dll_path=None, plane_tol=PLANE_TOL)`.
   - `topo` (the `analyse_topology` Topology of the shipped mesh) replaces `edge_class, edge_table`. The edge table indexes WELDED vertex ids and is only meaningful together with that weld, and `topo` carries both (`table`, `edge_class`, `positions_w`, `ok`).
   - `materials` became `mtl_materials` (the `parse_mtl` dict) plus `tex_dir`.
2. **Planarity fallback and post-save check** were not in the brief. Both are forced by a measurement: SketchUp's SAVE splits a non-planar polygon into triangles joined by HARD edges (see below). Without them, the owner would see diagonal lines on sloped and diagonal surfaces.
3. **`read_skp_summary` has extra keys** beyond the required six: `smooth_edges`, `edges_without_face`, `material_names`, `textured_materials`, `inner_loops`.
4. **Bbox.** For the fixtures the summary bbox equals `mesh.bbox()` exactly. For real data it equals the bbox of the vertices faces USE, exactly. The fixed OBJ keeps unused rows (corners of removed faces), so its all-rows bbox is lower in z for file B (1775.52 against 1779.53).
5. **One test was wrong and I corrected it.** `test_that_region_as_one_polygon_is_what_sketchups_own_check_would_split` expected `SUModelFixErrors` to split a polygon in a file saved as one face. Measured: the in-memory model had 1 face after the fill and 3 after `SUModelSaveToFile`, so the file already holds the split. The test now asserts the save-time split and the writer's rebuild (`test_polygon_sketchups_own_save_splits_is_rebuilt_as_soft_edged_triangles`). The writer now counts everything after the save.

## Measured facts about this DLL (SketchUpAPI.dll, API 14.2, SketchUp 2026)

These come from scratch probes (`scratchpad/skp/explore1..6.py`), never on a user file.

| question | measured | consequence |
|---|---|---|
| exports | all needed symbols, incl. `SUGeometryInputFaceAddInnerLoop`, `SUFacePositionMaterial`, `SUModelFixErrors`, `SUMeshHelper*` | inner loops written natively |
| face normal | follows the loop's winding (right-hand rule), also at z = 0 | reversal is a safety net (0 on real data) |
| `SUMaterialInput` UVs | tile units, like OBJ `vt`: the UV helper returns exactly the UVs given; `s/t_scale` of the texture does not change them | UVs passed through unchanged |
| `SUFaceReverse` | mirrors a positioned texture (u became -u) | re-position with `SUFacePositionMaterial`; restored exactly |
| repeated vertex in a loop | `SULoopInputAddVertexIndex` returns `SU_ERROR_INVALID_ARGUMENT` | consecutive repeats folded first |
| degenerate faces | `SUEntitiesFill` returns success but drops collinear or zero-area triangles and triangles with edges under 0.001 in; a collinear one left faceless edges | skipped and counted beforehand |
| duplicates | coincident faces, including opposite-wound ones, merge into one face | counted (`coincident_faces_merged`) |
| "faces from coplanar edge loops" (doc note) | not observed: an open box's rim and a triangulated hole's rim stay open | none |
| coordinates near 24,000 in | come back bit-identical | edge matching is exact |
| non-planar polygon | the fill keeps it as ONE face and moves no vertex (tried up to 0.3 in off); **the save splits it** into triangles with hard edges, as `SUModelFixErrors` does; the threshold is about 1.2e-3 in off the best-fit plane (a quad's corner lift splits it from 5.0e-3 in, which is 1.25e-3 off the fit, not at 4.0e-3; a 12-gon's single vertex splits from 1.6e-3 in), the same for faces from 10 in to 3000 in | `plane_tol` 1e-3 plus the post-save check |
| `SUInitialize`/`SUTerminate` | can be cycled repeatedly in one process | one session per call |
| persistence | soft and smooth flags, inner loops, unused materials survive save and reopen | none |

## Tests

- **`engine/tests/test_skp_writer.py`: 23 tests.**
  - Missing DLL, env-var DLL, default path, a DLL without the symbols (kernel32), and ctypes confined to the writer. These run without SketchUp.
  - `grid_slab` merged gives 1 face, 4 edges, 0 soft.
  - `slab_with_hole` gives 1 face with 1 inner loop, 8 edges.
  - The same slab with the inner-loop API switched off gives 8 triangles, `fallback_regions` `no_inner_loop_api`, and 8 soft diagonals.
  - `cube` gives 6 faces and 12 edges.
  - `creased_pair` at 3 degrees gives 2 faces and 7 edges, with the hinge soft and smooth.
  - Two coplanar copied-through triangles (`bare_top_quad`, no rings) give 2 faces, 5 edges, the shared edge soft.
  - A zero-area face is skipped.
  - Writing over an existing file replaces it.
  - A ring wound backwards is reversed, and the texture still reproduces the mesh UVs on both sides.
  - A non-planar region (new fixture `slab_with_lifted_corner`, appended at the end of `build.py`) is written as 3 soft-edged triangles, and SketchUp's fixer changes nothing.
  - With the pre-check off, the save's split is caught and rebuilt (`split_by_sketchup`).
  - A clean model gets no change from SketchUp's fixer.
  - The material count equals the mesh's; each material has its Kd colour on both sides.
  - A textured material reproduces the mesh UVs on both sides.
  - A missing texture file falls back to Kd.
  - The UV residual is reported for a bent UV map.
  - The bbox equals the mesh bbox at y = 24,000 in.
  - Writing twice gives equal summaries and equal reports.
- **`engine/tests/test_cli.py`: 8 new tests.** They cover the parser flags, `default_skp_dir`, `main` passing the folder, and the copy into a folder that does not exist yet. They also cover the replaced older copy, SketchUp missing (the run still exits 0 with the reason), and `--no-skp`. The one-line change to `test_main_dispatches_to_cmd_fix` lets its stub accept the new keyword arguments.
- **Mutation check** (scratch pytest plugin, one behaviour broken at a time): each of 10 mutations turned at least one test red. The mutations were: no softening, no reversal, no re-positioning, no plane check, no post-save check, no UV residual, no degenerate skip, no inner loops, front material only, and centred coordinates.

## Real data

Run from the worktree root with `.venv` python `-m engine.cli fix <snapshot> --out data/output --skp-dir "OBJ FIXED RESULT"`. Both runs exited 0 with `passed=True`: 76 s for file A and 81 s for file B.

| | A `CHTM_SIDE_WALK_2nd_floor` (ce26e0392ab0) | B `CHTM_2nd_to_3rd_building_sidewalk_outside` (0b290ec0bcb4) |
|---|---|---|
| pipeline | 4692 -> 2579 tris, merge **rolled back** (`guard_failed`, as expected on this branch) | 7227 -> 602 tris, 90 regions merged |
| faces written | 2579 triangles, 0 polygons | 248 = 81 polygons + 110 copied-through triangles + 40 triangles of 8 non-planar regions + 17 triangles of multi-piece regions |
| inner loops | 0 | 8, in 4 faces |
| fallback_regions | none | 8 `nonplanar` (0.0032 to 0.0259 in off-plane) |
| hidden edges | 8 soft + 2934 gridlines, 0 unmatched | 1 soft + 142 gridlines, 0 unmatched |
| reversed faces | 0 | 0 |
| uv_residual_regions | none | none |
| uv_unpositioned_faces | 1 (row 431: its three UVs share v = 0.999, a line in the export itself) | 0 |
| materials | 1, textured | 3, textured |
| SketchUp's own fixer changes | none | none |
| copy in `OBJ FIXED RESULT/` | byte-identical to the run file | byte-identical to the run file |

`read_skp_summary` of `OBJ FIXED RESULT/CHTM_SIDE_WALK_2nd_floor.fixed.skp`:

```json
{"faces": 2579, "edges": 4269, "soft_edges": 2942, "smooth_edges": 2942, "edges_without_face": 0, "materials": 1, "material_names": ["mumi_littletiles_ltstone_-7"], "textured_materials": 1, "loops_with_inners": 0, "inner_loops": 0, "bbox": [[1019.71, 22433.2, 1582.68], [2683.09, 23363.3, 1779.53]]}
```

`read_skp_summary` of `OBJ FIXED RESULT/CHTM_2nd_to_3rd_building_sidewalk_outside.fixed.skp`:

```json
{"faces": 248, "edges": 734, "soft_edges": 143, "smooth_edges": 143, "edges_without_face": 0, "materials": 3, "material_names": ["mumi_littletiles_ltstone_-5", "mumi_littletiles_ltstone_-3", "mumi_littletiles_ltstone_-8"], "textured_materials": 3, "loops_with_inners": 4, "inner_loops": 8, "bbox": [[980.11, 22651.0, 1779.53], [3293.33, 24204.9, 2114.17]]}
```

**Determinism on real data.** File B was written twice from one `fix_object` result. The summaries and the reports are equal, and the counts equal the CLI run's.

**Renders without the SketchUp GUI.** Each `.skp` was read back through the C API: SketchUp's own triangulation of every face, and only the edges that are neither soft nor smooth. They were drawn with `engine.guard.qa_render.write_qa_sheet` (scratch script `render_skp.py`). The output is 21 images per model in `data/output/<name>/skp_render/` (git-ignored); I looked at `obl_top_a.png` of each.
- **B:** flat faces with outline edges only. The pipeline's own `qa/obl_top_a.png` of the same mesh shows dense triangle fans on the sloped segment and diagonals on the lower right surface; the `.skp` shows neither. A few short edge stubs on the top surfaces appear in both pictures, so they come from the model.
- **A:** the triangulation is hidden, but lines remain on the flat areas. File A's 1327 visible edges break down as follows:
  - 565 real creases (539 over 30 degrees, 26 at 5 to 30 degrees);
  - 283 open;
  - 308 T-junction;
  - 171 non-manifold.

  No visible edge lies between faces within 1 degree of each other. The lines on the flat areas are the unmerged mesh's open, T-junction and non-manifold edges, which the brief leaves visible.

## Concerns

1. **File A's `.skp` is 2579 triangles**, because its merge rolls back on this branch. Its 762 open, T-junction and non-manifold edges stay visible as lines on flat areas in SketchUp; softening classes 2, 3 and 4 was outside the brief. feat-dashboard `022a67b` makes A's merge ship, so A's `.skp` has to be re-checked after the controller merges.
2. **8 regions of B are 3 to 26 thousandths of an inch off-plane** (sloped and diagonal surfaces printed at the 0.1 in Y step). They are written as 40 soft-edged triangles instead of 8 polygons: visually the same in SketchUp, but selecting such a surface selects one triangle.
3. **Nothing was checked in the SketchUp GUI,** by rule. The evidence is:
   - the C API read-back;
   - SketchUp's own fixer changing nothing;
   - UV values reproduced on both sides;
   - the renders.

   Not verified: the texture's on-screen orientation. UVs are passed in tile units with the same v-up convention as OBJ; the values are verified, but the image orientation has not been seen.
4. **Texture size.** Textures are created with `s_scale = t_scale = 1.0`. That only affects faces without UVs (1 face in A) or a later re-paint in SketchUp.
5. **Old prototype files.** The main checkout's `OBJ FIXED RESULT/` already holds the prototype's older files under other names (for example `CHTM_SIDE_WALK_2nd_floor.skp`). The CLI writes `<name>.fixed.skp` next to them and never deletes anything, so the owner should open the `.fixed.skp` files.
6. **Merge conflicts.** `engine/cli.py` changed in several places:
   - the module docstring;
   - one import;
   - a new section `SketchUp file` just before `cmd_fix`;
   - `cmd_fix`'s signature, docstring and tail;
   - two parser arguments;
   - `main`.

   `engine/tests/test_cli.py` has one changed lambda plus tests appended at the end. These may conflict with the other agent's edits to the same files.

## S1 lines inside surfaces

Branch `feat/skp-soften` (worktree `.claude/worktrees/skp-soften`), from feat-dashboard `8ffbda3`.

| item | commit |
|---|---|
| S1 `fix(engine): the SketchUp writer hides every line it would draw inside a flat surface` | `bcccca2` |
| this section | (the commit that adds it) |

Engine suite from the worktree root: `390 passed` (368 at `8ffbda3`, plus 21 in `test_skp_writer.py` and 1 in `test_cli.py`).

### What was built

After the fill and after the class 1/5 softening, and before the save, `_hide_lines_inside_surfaces` reads SketchUp's OWN model, not the topology:
- faces with unit normal, loops as positions and vertex ids, and front/back material;
- edges with end vertices, soft flag, and their faces through the newly bound `SUEdgeGetFaces`.

`_verdict` decides each edge in this order:
1. Soft already, no face, 3+ faces (non-manifold), or two faces more than `COPLANAR_ANGLE` apart (a shape edge; `COPLANAR_ANGLE` = 1 degree, reused from `engine/topo/edges.py`).
2. Two coplanar faces continuing across the edge with different materials: a material border.
3. **Angled**: a face at an angle holds both end points in its plane and the midpoint in its area, within `ON_FACE_TOL`. This is a wall standing on the line, and the edge is never hidden.
4. **Flat, rule (a), hidden**: two faces coplanar either way round that continue each other across the edge (their inward directions are opposite) and show the same material on each side (front with front, or front with back when wound against each other).
5. Otherwise every face of the edge lies on one side of it. **T-junction, rule (b), hidden**: the far side lies on coplanar faces of the same material along the edge's WHOLE length. The edge is cut wherever those faces' boundaries cross it or have a vertex within `ON_FACE_TOL` of its line, and each piece at least `ON_FACE_TOL` long is judged at its middle, `ON_FACE_TOL` across to the far side.
6. Covered along only part of its length: **partly inside**, kept drawn. Covered by another material's faces: a material border. Else: border.

- Hidden edges are set soft and smooth, or soft only when the two faces are wound against each other (`soft_only_edges`), because smoothing would average opposite normals to nothing.
- New keys in the returned dict and in `report.json`'s `skp` block:
  - `coplanar_edges_softened`, `tjunction_lines_softened`, `soft_only_edges`;
  - `visible_border_edges`, `visible_angled_edges`, `visible_shape_edges`, `visible_material_borders`, `visible_nonmanifold_edges`, `visible_lines_inside_surfaces` (the partly-inside ones), counted after the save.
  - The visible classes add up to `edges - soft - edges_without_face`; a test checks this on 10 fixtures.
- The CLI line now reads `N edges hidden, M lines left inside surfaces`, where N includes the two new counts.
- `ON_FACE_TOL` = 0.02 in. Sweep with the final code on the baseline files, T-junction lines found:
  - A: 69 at 0.001 in, 72 at 0.005 in, 73 from 0.01 to 0.05 in, 77 at 0.1 and 0.15 in;
  - B: 9 at every tolerance.
  - The four extra at 0.1 in run along a sliver-shaped hole in A's mesh up to 0.19 in wide.
- Cost: `write_skp` on A's `FixResult` takes 0.8 s with the two passes and 0.2 s without (two rounds each). The wall-clock runs took 94 s and 93 s against 61 s at baseline, but `fix_object` alone took 65 s in the timing run and other Python processes were loading the machine. The difference is machine load, not the writer.

### Deviations from the brief, and why

1. **Rule (b) checks the whole edge and its far side, not the midpoint.**
   - The midpoint rule hides an edge that lies inside a surface over only part of its length and is real outline over the rest: a notch, a hole's rim, a double layer's end, or staggered slabs.
   - It also hides an edge whose neighbour lies on the SAME side, a double layer: B's faces 37 and 38, where the audit's midpoint lands on face 38's vertex.
   - Such edges stay drawn and are reported as `visible_lines_inside_surfaces`.
2. **Angled first.** The first real-data run applied (a) and (b) before the angled check. It hid 10 edges the audit counts as "open edge lying on an angled face" (A: 328 -> 318). Deciding angled first keeps the audit's angled count at 328 and 150. The cost is that 12 edges in A and 2 in B, which also run inside a flat surface, stay drawn as `visible_angled_edges`. One per file was checked:
   - A (1334.67 -> 1374.04, 22748.2, 1622.05): the top of a wall panel meets slab face 714;
   - B (2397.43, 24195.0, 1976.38 -> 2015.75): wall face 17 meets the surface x = 2397.43 over 75 % of the edge.
3. **Either orientation counts as coplanar.** 17 of A's 21 baseline coplanar lines are between faces wound against each other. Those are set soft, not smooth: 15 in A and 1 in B.
4. **A coplanar same-material pair on the same side of its edge stays drawn.** Such a double layer ends at that edge. Examples: A's (2515.77, 22669.4, 1752.92 -> 1764.58), a triangle and a quad in the plane x = 2515.77; and 2 edges in B.
5. **Two of my own tests were wrong and I corrected them.** Neither came from the brief.
   - `test_outline_of_a_split_double_layer_stays_visible` first expected no hidden T-junction line. The 4 sloped sides of the upper layer run across the quad, which covers both of their sides, so the writer was right to hide them.
   - `test_edge_two_back_to_back_faces_both_end_on_stays_visible` first expected 5 border edges. Each triangle's sloped side runs through the other layer for part of its length, so the correct split is 3 border and 2 partly inside.

### Measured facts about this DLL

These come from scratch probes on fixtures.

- `SUEntitiesFill` does not split an edge at a T-vertex. The long edge and the two short edges along it stay three edges, each with one face.
- An outer loop is counter-clockwise about the face normal and an inner loop clockwise, so the face lies left of every loop side.
- Two coplanar faces wound against each other stay two faces sharing one edge. An overlapping second layer stays a separate face.
- A wall's bottom edge inside a merged slab face stays a separate edge with one face. The slab face is not split.

### Tests

- The five from the brief:
  - two regions of one material give a soft diagonal (a UV seam makes the topology class it 0);
  - two materials keep the line;
  - the T-junction strip hides the long edge and both short edges while its 7 outline edges stay (the topology classes all three 4);
  - a wall on a slab keeps the line where they meet;
  - the outline of a copied-through slab stays.
- Added:
  - a flipped pair becomes soft but not smooth;
  - staggered slabs keep both half-inside edges (2 lines inside surfaces);
  - back-to-back and split double layers keep their outline;
  - a wall standing on a coplanar line or on T-junction lines keeps them;
  - every visible edge falls in exactly one class (10 fixtures);
  - the CLI's `skp` block and printed line.
- New fixtures, appended at the end of `build.py`: `two_region_quad`, `t_junction_seam_strip`, `staggered_slabs`, `back_to_back_pair`, `split_double_layer` (helper `_with_wall`).
- **Mutation check** (a scratch pytest plugin re-executes the writer with one change at a time). Each of 11 mutations turned at least one test red. The mutations were:
  - no side test for pairs;
  - no angled check;
  - partial coverage counted as full;
  - no material check;
  - always smooth;
  - no far-side offset;
  - no hide pass;
  - no rule (a);
  - no rule (b);
  - signed angle;
  - the whole edge judged at its middle.

### Real data

Run from the worktree root with `-m engine.cli fix <snapshot> --out data/output --skp-dir "OBJ FIXED RESULT"` at `bcccca2`. Both runs exited 0 with `passed=True`. The copies are byte-identical, SketchUp's own check changes nothing, and a second run gave identical audit output and summaries. The baseline is the `8ffbda3` code, written in this worktree to `OBJ FIXED RESULT-base/`; the audit reproduces the controller's numbers on it.

| | A `CHTM_SIDE_WALK_2nd_floor` | B `CHTM_2nd_to_3rd_building_sidewalk_outside` |
|---|---|---|
| faces, edges | 731, 1618 | 248, 734 |
| soft edges at baseline -> S1 | 560 -> 648 (+15 coplanar, +73 T-junction) | 143 -> 153 (+1, +9) |
| soft only (wound against each other) | 15 | 1 |
| visible border / angled / shape / material / non-manifold | 213 / 340 / 330 / 0 / 65 | 197 / 152 / 158 / 27 / 30 |
| `visible_lines_inside_surfaces` | 22 (112.7 ft), all partly inside | 17 (40.1 ft), all partly inside |
| audit: coplanar lines | 21 (45.7 ft) -> 6 (3.7 ft) | 5 (7.4 ft) -> 4 (6.6 ft) |
| audit: T-junction lines | 100 (312.1 ft) -> 27 (123.7 ft) | 36 (74.9 ft) -> 28 (60.3 ft) |
| audit: border / angled / shape / non-manifold | 214 / 328 / 330 / 65, unchanged | 200 -> 199 / 150 / 158 / 30, material 12, unchanged |

Every edge the audit still flags, against the writer's verdict:

- **A:**
  - 20 T-junction lines are partly inside;
  - 7 T-junction lines and 5 coplanar lines are angled;
  - 1 coplanar line is a double layer's end.
  - The writer's 22 partly-inside edges are these 20 plus 2 that the audit calls border.
- **B:**
  - 15 T-junction lines are material borders; the face beside them has another material, and the audit does not compare materials;
  - 12 are partly inside;
  - 1 is border (faces 37 and 38 lie on the same side);
  - 2 coplanar lines are angled and 2 are double layers' ends.
  - The writer's 17 partly-inside edges are these 12 plus 5 that the audit calls border.
- **B's audit border count 200 -> 199:** the edge (3018.5 -> 3027.58, 22895.8, 1818.9), face 201's top.
  - Faces 198, 201 and 202 patch a hole in slab face 47, and this edge runs along the hole's rim, so its far side is face 47: a line inside the surface, hidden correctly.
  - The audit calls it border because the midpoint lies exactly on the rim and its even-odd test puts it inside the hole.

Audit output (`skp_edge_audit.py`) on the two S1 files:

```
CHTM_SIDE_WALK_2nd_floor.fixed.skp: 731 faces, 1618 edges
  VISIBLE LINE INSIDE A FLAT SURFACE (coplanar, same material)       6       3.7 ft
  hidden (soft)                                                    648    3458.2 ft
  visible, non-manifold (3+ faces)                                  65     120.4 ft
  visible, open border (1 face)                                    569    1272.3 ft
  visible, shape edge > 5 deg                                      330    1205.8 ft
  visible open edges split:
    open edge = real border of the model                                       214     509.9 ft
    open edge lying ON a coplanar face (T-junction line inside a surface)       27     123.7 ft
    open edge lying on an angled face (face meets a surface it does not split)   328     638.7 ft
CHTM_2nd_to_3rd_building_sidewalk_outside.fixed.skp: 248 faces, 734 edges
  VISIBLE LINE INSIDE A FLAT SURFACE (coplanar, same material)       4       6.6 ft
  hidden (soft)                                                    153    1864.5 ft
  visible, material border (coplanar)                               12     229.3 ft
  visible, non-manifold (3+ faces)                                  30      52.4 ft
  visible, open border (1 face)                                    377    1237.8 ft
  visible, shape edge > 5 deg                                      158    1722.5 ft
  visible open edges split:
    open edge = real border of the model                                       199     625.8 ft
    open edge lying ON a coplanar face (T-junction line inside a surface)       28      60.3 ft
    open edge lying on an angled face (face meets a surface it does not split)   150     551.8 ft
```

`read_skp_summary`:

```json
{"faces": 731, "edges": 1618, "soft_edges": 648, "smooth_edges": 633, "edges_without_face": 0, "materials": 1, "material_names": ["mumi_littletiles_ltstone_-7"], "textured_materials": 1, "loops_with_inners": 0, "inner_loops": 0, "bbox": [[1019.71, 22433.2, 1582.68], [2683.09, 23363.3, 1779.53]]}
{"faces": 248, "edges": 734, "soft_edges": 153, "smooth_edges": 152, "edges_without_face": 0, "materials": 3, "material_names": ["mumi_littletiles_ltstone_-5", "mumi_littletiles_ltstone_-3", "mumi_littletiles_ltstone_-8"], "textured_materials": 3, "loops_with_inners": 4, "inner_loops": 8, "bbox": [[980.11, 22651.0, 1779.53], [3293.33, 24204.9, 2114.17]]}
```

### Concerns

1. **Lines left inside surfaces: 22 in A (112.7 ft), 17 in B (40.1 ft).** Each lies inside a flat surface over part of its length and is outline over the rest. The largest is A's 551.3 in edge along the double-layer wall at x = 2515.77. Hiding them would hide that outline; removing them needs the edge split in the mesh (the T-junction repair).
2. **12 edges in A and 2 in B run inside a flat surface where a wall stands on them.** The line is drawn there anyway, but beyond the wall's ends a short stretch inside the surface stays drawn.
3. **The controller's audit will still print lines inside surfaces:** 6 + 27 in A and 4 + 28 in B, each accounted for above. The audit ignores which side a face lies on, and it ignores material for T-junction lines.
4. **Four edges along a 0.19 in sliver hole in A stay drawn** at `ON_FACE_TOL` = 0.02 in; they would be hidden from 0.1 in.
5. **Nothing was checked in the SketchUp GUI,** by rule, so two things are unverified:
   - how a soft-but-not-smooth edge between faces wound against each other looks;
   - whether hidden edges read as one surface on screen.
6. **Merge conflicts.**
   - `build.py` has a helper and 5 fixtures appended at the end, and `test_cli.py` has one test appended at the end; both are where the other agent appends too.
   - `engine/cli.py` changed only the printed `.skp` line.

## Public signatures

```python
# engine/io/skp_writer.py
DEFAULT_DLL: Path = Path(r"C:\Program Files\SketchUp\SketchUp 2026\SketchUp\SketchUpAPI.dll")
DLL_ENV = "FIXER_SKETCHUP_DLL"
PLANE_TOL = 1e-3            # in; polygon farther off its plane is written as triangles
EDGE_MATCH_TOL = 1e-6       # in; edge end point to vertex
ON_FACE_TOL = 0.02          # in; an edge lies on another face (its plane, its boundary) (S1)
UV_RESIDUAL_TOL = 1e-3
DEFAULT_RGB = (204, 204, 204)

class SketchUpError(RuntimeError): ...
class SketchUpUnavailable(SketchUpError): ...

def resolve_dll_path(dll_path=None) -> Path
def load_api(dll_path=None) -> _Api          # cached per path; raises SketchUpUnavailable

def write_skp(mesh: MeshData, rings: dict, face_region: np.ndarray, topo: Topology,
              mtl_materials: dict[str, MtlMaterial], path, *, tex_dir=None, dll_path=None,
              plane_tol: float = PLANE_TOL) -> dict
# returns: path, api_version, material_path ("geometry_input"), faces, faces_input,
#   polygon_faces, triangle_faces, inner_loops, faces_missing, faces_unexpected,
#   coincident_faces_merged, degenerate_faces_skipped, edges, edges_without_face, soft_edges,
#   gridline_edges_softened, unmatched_edges,
#   coplanar_edges_softened, tjunction_lines_softened, soft_only_edges,            (S1)
#   visible_border_edges, visible_angled_edges, visible_shape_edges,              (S1)
#   visible_material_borders, visible_nonmanifold_edges,                          (S1)
#   visible_lines_inside_surfaces,                                                (S1)
#   reversed_faces, reversed_faces_unpositioned,
#   uv_unpositioned_faces, fallback_regions [{region, reason[, deviation]}],
#   uv_residual_regions [{region, residual}], materials [{name, texture, color}]
#   (every count taken from the model as saved; the visible_* add up to
#    edges - soft_edges(read back) - edges_without_face)

def read_skp(path, *, dll_path=None, uvs: bool = True, triangles: bool = True) -> SkpModel
def read_skp_summary(path, *, dll_path=None) -> dict
# faces, edges, soft_edges, smooth_edges, edges_without_face, materials, material_names,
# textured_materials, loops_with_inners, inner_loops, bbox [[min xyz], [max xyz]]
def check_skp_validity(path, *, dll_path=None) -> dict   # {"changed", "before", "after"}

@dataclass class SkpModel:    faces: list[SkpFace]; edges: list[SkpEdge]; materials: list[SkpMaterial]
@dataclass class SkpFace:     outer: ndarray; inners: list[ndarray]; normal: ndarray;
                              front_material: str | None; back_material: str | None;
                              front_uv: ndarray | None; back_uv: ndarray | None; triangles: ndarray
@dataclass class SkpEdge:     start: ndarray; end: ndarray; soft: bool; smooth: bool; faces: int
@dataclass class SkpMaterial: name: str; textured: bool; color: tuple[int, int, int, int] | None

# engine/cli.py
def default_skp_dir() -> Path                      # <repo root>/OBJ FIXED RESULT
def cmd_fix(snapshot_dir: Path, out_root: Path, accept_slit: bool,
            profile: FixProfile | None = None, solidify: bool = True, fragments: bool = True,
            skp: bool = True, skp_dir: Path | None = None) -> int
# python -m engine.cli fix <snapshot_dir> [--accept-slit] [--no-solidify] [--keep-fragments]
#                          [--out DIR] [--no-skp] [--skp-dir DIR]
# report.json "skp": {"written": true, **write_skp report, "sketchup_check_changed", "copied_to"
#                     [, "copy_error"]}  or  {"written": false, "reason": str}
# printed: "  wrote <path>: <faces> faces, <hidden> edges hidden, <n> lines left inside surfaces,
#           copied to <folder>"   (hidden = soft + gridline + coplanar + tjunction; S1)

# engine/tests/fixtures/build.py (appended)
def slab_with_lifted_corner(nx=3, nz=2, cell=100.0, y=24000.0, step=0.1,
                            uv_per_unit=0.05) -> MeshData
def two_region_quad(size=40.0, seam=0.37, material=0, flip=False, wall=False,
                    uv_per_unit=0.05) -> MeshData                                 # S1
def t_junction_seam_strip(seam=0.37, wall=False, uv_per_unit=0.05) -> MeshData    # S1
def staggered_slabs(uv_per_unit=0.05) -> MeshData                                 # S1
def back_to_back_pair(size=40.0, uv_per_unit=0.05) -> MeshData                    # S1
def split_double_layer(uv_per_unit=0.05) -> MeshData                              # S1
```
