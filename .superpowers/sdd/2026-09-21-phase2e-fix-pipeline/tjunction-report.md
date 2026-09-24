# T-junction repair (T1): report

Branch `feat-dashboard`, main checkout, from `8ee9e4d` (the controller's docs-only commits `b94b4f9`,
`6b1d3dd`, `e47b456` landed in between).

| item | commit |
|---|---|
| T1 `fix(engine): the merge threads T-junction vertices into the edges they lie on` | `28d63df` |
| `docs(engine): thread_tolerance says what lies just outside it, as measured` (a docstring claim I had not measured) | `03df53d` |
| this report | the commit that adds this file |

Engine suite at `03df53d`: `417 passed in 68.59s` (406 at `8ee9e4d`, plus 11 new tests).

## In one paragraph

The merge now threads every vertex the output uses into every output edge it lies on, at two points in the merge.
- **Before the corner pass,** each input vertex lying on a region's union-ring segment is inserted into that ring. The corner pass then keeps it wherever another face needs it, and a border two regions share stays identical on both sides.
- **After the output is decided,** a bounded fixed-point pass splits every triangle that still has a used vertex on one of its edges:
  - a copied-through triangle becomes a fan;
  - the two triangles beside a merged polygon's diagonal are split;
  - a vertex on a ring edge also goes into the ring.

Nothing is moved or invented. "On" means within `thread_tolerance`, 1e-5 times the coarsest print step, which is 1e-6 in on both files: every measured case is exact.

On the real files every T-vertex is gone (A 353 -> 0, B 363 -> 0). That costs 111 triangles on A (902 -> 1,013) and 46 on B (555 -> 601). Both guards pass with the same totals as before, and two runs give byte-identical reports.

In SketchUp the audit's T-junction lines fell from 8 to 2 on A and from 28 to 24 on B. No line left in either file has a vertex on it:
- **B's 24:** 15 are seams between two materials, which the audit does not tell apart from other lines. 5 of those have a vertex 0.00065 to 0.0046 in off the line, outside the tight tolerance. The other 9 are edges of one same-material layer lying over another.
- **A's 2:** both are edges of one layer lying over another.

Threading cannot remove either kind.

## What was built (`engine/fixes/merge.py`)

- **`thread_tolerance(quanta)`** is `THREAD_TOL_QUANTA * max(quanta)`, with `THREAD_TOL_QUANTA = 1e-5`. That is 1e-6 in on both files (Y is printed to 0.1 in).
  - Justification, measured on the merge outputs at `8ee9e4d`: of the used vertices within 0.15 in of an output edge's interior, 111 (A) and 65 (B) lie within 1e-9 in of it.
  - The nearest of the rest lie 6.1e-4 in off (B) and 1.2e-3 in off (A).
  - Threading moves a border onto the vertex, so only an exact vertex can be threaded without changing the surface. The tolerance sits a thousand times above the exact cases and six hundred times below the nearest non-exact one.
- **`_thread_union_rings(topo, plans, tol)`** runs once after `_plan_regions`.
  - For every ring segment of every plan's union, the vertices of the non-degenerate faces that lie within `tol` of the segment's interior are inserted in order along it (ties broken on id).
  - A vertex already in the piece is never inserted again, since that would pinch the ring.
  - Each plan's vertex arrays are extended in its own frame. `_Plan` now carries `origin`, `basis` and `threaded`. Rows already there stay bit-identical.
  - The corner pass then treats the vertex like any ring vertex. It keeps it when the vertex is `needed` (a copied face uses it, or it lies on an open or T-junction edge) and where rings diverge (`_divergent_vertices`).
- **`_thread_output(topo, builds, copied, kept, tol)`** runs after the fixed-point loop.
  - The output (every build's triangles plus every copied face) is scanned with `find_t_vertices` at `tol`.
  - Every non-degenerate triangle holding such an edge is cut into a fan from the corner opposite it (`_split`, recursive when vertices lie on several edges; winding kept).
  - A region's kept ring takes the vertices found on its own ring edges (`_thread_ring`).
  - Rounds repeat until none is found, at most `MAX_THREAD_ROUNDS = 8`. Measured on the real files: A has 42 vertex-edge pairs in round 1 and 0 in round 2; B has 14, then 0.
- **A used vertex on a merged region's diagonal** (for example a wall's foot inside the polygon) splits the two triangles beside the diagonal. The ring does not change, because the vertex is not on the border. The brief named only rings and copied triangles; this is the third case the output can contain (fixture `slab_with_a_wall_foot_on_its_diagonal`).
- **`_assemble`** writes a split copied face as its pieces, each with the face's own material, line and source face.
  - A corner of the original keeps its own `v`, `vt` and `vn`.
  - A threaded vertex gets its lowest original row. When the face carries them, it also gets a NEW `vt`, interpolated barycentrically in the face's own UVs so the texture lies exactly as before, and a `vn`: the face's own normal index when all three corners share one, otherwise an interpolated unit normal.
- **`_region_loops(plan, kept, welded_to_original)`** now takes the region's kept rings, exactly as triangulated and threaded, instead of re-deriving them from `needed`.
- **`merge_report`** gains three keys:
  - `t_vertices_before` and `t_vertices_after`: distinct vertices on the interior of an edge of the merge input, and of the output (`find_t_vertices` at `thread_tolerance`, over non-degenerate faces; a zero-area face covers nothing, so it opens no crack).
  - `edges_split`: distinct edges cut. That is every union-ring segment whose threaded vertex the kept ring still holds, plus every output edge the output pass split.

## Why file B's T-junction lines fell only 28 -> 24

The audit counts as a "T-junction line" any visible one-face edge whose middle lies on another coplanar face (within 0.02 in), whatever the materials and whether the two faces overlap.

I wrote HEAD's (`8ee9e4d`) and T1's merge output of the same captured merge input through the same writer. For every such line I measured the nearest vertex of the model to the line's interior, and the overlap area between the line's face and the face it lies on (scratch scripts `compare_skp.py` and `classify_lines.py` in the session scratchpad `tjunction/`).

| audit "T-junction lines" | A HEAD | A T1 | B HEAD | B T1 |
|---|---|---|---|---|
| total | 8 | 2 | 28 | 24 |
| a vertex within 1e-6 in of the line (a T-junction) | 3 | 0 | 4 | 0 |
| a vertex within 0.02 in only | 0 | 0 | 5 | 5 |
| no vertex within 0.02 in | 5 | 2 | 19 | 19 |

T1 removed every line that had a vertex on it. B's remaining 24 are these:
- **15 lie on a face of ANOTHER material.** The audit's T-junction class ignores material.
  - 8 run along the side wall at y = 24204.9, where the two materials' faces overlap by a 0.026 sq in sliver.
  - 2 have neither an overlap nor a vertex.
  - 5 have a vertex of the other material 0.00065 to 0.0046 in off the line (three 39.7 in lines, two 35.7 in lines).
  - SketchUp draws a material border whatever the mesh does. Split at those vertices, the 5 would become two-face material-border edges and would still be drawn.
- **9 are edges of one layer running over another layer of the SAME material.** They overlap 4.9 to 157 sq in, and the longest (45.5 in) is a back-to-back pair. Example: the 44.0 in hypotenuse of copied face 1187 on y = 24165.5. These are double layers with no vertex on the line.

A's 2 are the same kind:
- the 551.3 in hypotenuse of copied face 2546 (+x), lying over the back-to-back layer region 243 (-x) on x = 2515.77 (213 sq in overlap);
- a 19.7 in edge over a same-facing layer (72.9 sq in).

So the cause is not the writer's welding (no line has a vertex within 1e-6 in), nor an edge class the threading skips (it scans every non-degenerate output triangle, and neither output has a degenerate one). The tolerance explains only the 5 near vertices on B's material seams (concern 1). Removing the other lines means removing or cutting a layer. The merge must not do that (no vertex moved or invented); it belongs to the overlap removal and the side rebuild.

## Tests (TDD)

There are 11 new tests. All of them failed before the implementation, each for the expected reason:
- T-vertices {4, 5, 6} and {4} left in the output;
- a ring without the neighbour's vertices;
- the copied triangle still 1 row instead of 4;
- the diagonal case giving 2 slab triangles instead of 4;
- `KeyError: 't_vertices_before'` and `KeyError: 'edges_split'`;
- no `THREAD_TOL_QUANTA`;
- 5 one-face edges lying on a coplanar face in SketchUp.

All 11 pass after it.

- `engine/tests/test_merge.py`:
  - `test_a_merged_slab_threads_its_neighbours_border_vertices_into_its_ring` uses the new fixture `slab_beside_gridded_neighbour`. It checks: T-vertices 3 -> 0, the slab's ring `[0, 1, 2, 6, 5, 4, 3]`, 10 triangles, area unchanged, no position changed.
  - `test_the_t_junction_strip_threads_its_vertex_into_the_big_quads_ring` uses the existing `t_junction_seam_strip`.
  - `test_a_vertex_a_print_step_off_the_edge_is_left_alone`: a vertex 0.01 in off is not threaded; the two exact ones are.
  - `test_a_copied_through_triangle_with_vertices_on_its_edge_is_split_into_a_fan` uses `triangle_under_gridded_slab`: 4 pieces, winding and UVs kept, no new vertex.
  - `test_a_used_vertex_on_a_merged_regions_diagonal_splits_the_triangles_beside_it`.
  - `test_threading_is_deterministic`, 3 fixtures.
  - `test_the_thread_tolerance_is_a_hundred_thousandth_of_the_coarsest_print_step`.
- `engine/tests/test_skp_writer.py`: `test_threaded_t_junctions_leave_no_one_face_edge_on_a_coplanar_face`, the SketchUp round trip. It skips without the DLL and ran here. Written as exported, the fixture has 5 one-face edges lying on the coplanar neighbour. Merged, it has none, and the model is 2 faces.
- `engine/tests/test_pipeline.py`: `test_threading_the_t_junctions_of_a_slab_changes_nothing_the_guard_can_see`. It runs `fix_object` with the neighbour in material `m1`: 3 -> 0 T-vertices, 1 edge split, and the final guard passes with 0 holes and 0 moved pixels.

Two existing tests assumed a copied-through triangle is never split. The implementation is right, so the tests were updated and their counts now include the split:
- `test_overlapping_triangle_and_the_cells_it_overlaps_are_copied_through`: 13 -> 14 rows. Face 200's edge (2,2)-(4,2) runs through (3,2), a corner of the cells beside it.
- `test_a_triangle_whose_edge_crosses_a_neighbours_is_set_aside_and_the_rest_merges`: face 3 comes out as 2 rows, because vertex 9 lies on its edge 5-11. The test now asserts that no T-vertex is left; before, it asserted only that none was added.

Fixtures appended at the end of `engine/tests/fixtures/build.py`: `slab_beside_gridded_neighbour`, `triangle_under_gridded_slab`, `slab_with_a_wall_foot_on_its_diagonal`.

## Real data

Final runs were made at `03df53d`: `fix` twice for A and once for B, then `preview-data` for both. Every run exited 0, and each run copied its `.skp` to `OBJ FIXED RESULT/`. The "before" column is the `report.json` from the 14:00 runs at `8ee9e4d`.

| | A before | A after | B before | B after |
|---|---|---|---|---|
| triangles input -> reference -> shipped | 4692 -> 4846 -> 902 | 4692 -> 4846 -> **1013** | 7227 -> 7418 -> 555 | 7227 -> 7418 -> **601** |
| merge triangles in -> out | 2578 -> 902 | 2578 -> 1013 | 4738 -> 555 | 4738 -> 601 |
| t_vertices_before -> t_vertices_after | - | **353 -> 0** | - | **363 -> 0** |
| edges_split | - | 86 | - | 40 |
| regions merged / skipped | 178 / {} | 178 / {} | 89 / overlap 2 | 89 / overlap 2 |
| faces_copied | 87 | 87 | 66 | 66 |
| merge_rounds / keep_all_regions / converged / rolled back | 1 / 0 / yes / no | 1 / 0 / yes / no | 1 / 0 / yes / no | 1 / 0 / yes / no |
| vertices_dropped | 833 | 844 | 2168 | 2182 |
| guard_after_removal: passed; holes, material_changed, moved_same_flat, moved_other, edge_flicker, border_shift; zfight_tie, crack_closed, fragment_removed | True; 0,0,0,0,0,0; 0,0,24 | same | True; 0,0,0,0,0,0; 0,0,14 | same |
| guard_merge_attempt = guard_final, same columns | True; 0,0,0,0,0,106; 0,0,24 | same | True; 0,0,0,0,0,47; 2,0,14 | same |
| invariants (material_count_same, bbox_same, area_not_grown, cap_guard_passed, guard_passed) | all true | all true | all true | all true |
| passed | True | True | True | True |
| .skp faces (polygons + triangles; coincident merged) | 517 (159 + 358; 0) | 567 (159 + 411; 3) | 220 (79 + 141; 0) | 241 (79 + 162; 0) |
| .skp edges / hidden / visible | 1248 / 325 / 923 | 1281 / 362 / 919 | 680 / 112 / 568 | 681 / 131 / 550 |
| writer: tjunction_lines_softened, coplanar_edges_softened, visible_lines_inside_surfaces | 42, 15, 4 | 16, 33, 3 | 9, 1, 17 | 3, 3, 14 |
| writer visible: border, angled, shape, material, non-manifold | 219, 350, 301, 0, 49 | 239, 257, 344, 0, 76 | 200, 153, 143, 27, 28 | 209, 95, 158, 27, 47 |
| nonplanar fallbacks / SketchUp check changed the file | 19 / no | 19 / no | 9 / no | 9 / no |
| audit: lines inside a flat surface / T-junction lines | 6 (3.7 ft) / 8 (61.5 ft) | 7 (46.3 ft) / 2 (47.6 ft) | 4 (6.6 ft) / 28 (60.3 ft) | 3 (2.5 ft) / 24 (55.4 ft) |

**Determinism:** three runs of A wrote byte-identical `report.json` (sha256 `3b0089521dbefacd1a999681cad62847a946409e666edad1fca73017ea4422c5`). One run was at `28d63df` and two at `03df53d`; the code is identical, since the second commit is a docstring.

**Audit** (`docs/superpowers/records/scripts/skp_edge_audit.py` on the final files):

```
CHTM_SIDE_WALK_2nd_floor.fixed.skp: 567 faces, 1281 edges
  VISIBLE LINE INSIDE A FLAT SURFACE (coplanar, same material)       7      46.3 ft
  hidden (soft)                                                    362    2713.4 ft
  visible, non-manifold (3+ faces)                                  76     149.2 ft
  visible, open border (1 face)                                    492     961.0 ft
  visible, shape edge > 5 deg                                      344    1204.2 ft
    line inside a surface:   511.8 in  [2515.8, 23181.2, 1764.6] -> [2515.8, 22669.4, 1764.6]
    line inside a surface:    11.7 in  [2515.8, 22669.4, 1764.6] -> [2515.8, 22669.4, 1752.9]
    line inside a surface:     9.8 in  [1305.1, 22669.4, 1612.2] -> [1305.1, 22669.4, 1622.0]
    line inside a surface:     9.8 in  [1767.7, 22630.1, 1655.3] -> [1767.7, 22630.1, 1645.5]
    line inside a surface:     9.8 in  [1305.1, 22659.6, 1612.2] -> [1305.1, 22669.4, 1612.2]
    line inside a surface:     1.5 in  [2673.2, 23023.8, 1779.5] -> [2673.2, 23023.8, 1778.1]
  visible open edges split:
    open edge = real border of the model                                       240     518.1 ft
    open edge lying ON a coplanar face (T-junction line inside a surface)        2      47.6 ft
    open edge lying on an angled face (face meets a surface it does not split)   250     395.3 ft
      T-junction line:   551.3 in  [2515.8, 22669.4, 1752.9] -> [2515.8, 23220.6, 1764.6]
      T-junction line:    19.7 in  [1305.1, 22649.7, 1622.0] -> [1305.1, 22669.4, 1622.0]
CHTM_2nd_to_3rd_building_sidewalk_outside.fixed.skp: 241 faces, 681 edges
  VISIBLE LINE INSIDE A FLAT SURFACE (coplanar, same material)       3       2.5 ft
  hidden (soft)                                                    131    1503.4 ft
  visible, material border (coplanar)                               12     229.3 ft
  visible, non-manifold (3+ faces)                                  47      94.3 ft
  visible, open border (1 face)                                    330    1171.3 ft
  visible, shape edge > 5 deg                                      158    1769.9 ft
    line inside a surface:     9.8 in  [2870.1, 23437.1, 1807.2] -> [2870.1, 23437.1, 1817.1]
    line inside a surface:     9.8 in  [1610.0, 24008.0, 2104.3] -> [1610.0, 24008.0, 2114.2]
    line inside a surface:     9.8 in  [1491.9, 24165.5, 2104.3] -> [1491.9, 24165.5, 2094.5]
  visible open edges split:
    open edge = real border of the model                                       211     745.1 ft
    open edge lying ON a coplanar face (T-junction line inside a surface)       24      55.4 ft
    open edge lying on an angled face (face meets a surface it does not split)    95     370.8 ft
      T-junction line:    45.5 in  [2909.5, 23456.8, 1818.9] -> [2870.1, 23437.1, 1807.2]
      T-junction line:    44.0 in  [1413.2, 24165.5, 2094.5] -> [1373.8, 24165.5, 2114.2]
      T-junction line:    40.6 in  [1491.9, 24165.5, 2104.3] -> [1531.3, 24165.5, 2114.2]
      T-junction line:    39.7 in  [2121.8, 24204.9, 2042.2] -> [2082.5, 24204.9, 2047.4]
      T-junction line:    39.7 in  [2200.6, 24204.9, 2031.8] -> [2161.2, 24204.9, 2037.0]
```

**QA images** (`data/output/<name>/qa/top.png`, read after the final runs):
- **A:** seen from above, the stepped slab at the left (sawtooth stair outline, curved bend), the walkway, the diagonal ramp strip and the two-panel landing at the right are drawn as large clean faces. A few small rectangular and triangular outlines and short broken line fragments remain along the landing's right edge and lower-left corner.
- **B:** seen from above, the long walkway strip and the right-hand landing and ramp are a dozen or so large clean faces. The sloped panel at the lower left is drawn as a fan of about a dozen long thin triangles with a small knot of lines at its top corner. SketchUp hides that fan (concern 4).

## Concerns

1. **Near T-junctions left by the tight tolerance.** After T1, 3 (A) and 11 (B) pairs of a used vertex and an output edge lie 6.1e-4 to 4.6e-3 in apart. None lies between 0.005 and 0.01 in; the next are 0.0119 in (A) and 0.0164 in (B).
   - That is less than the 0.01 in print step, so the file cannot say whether the source had these vertices on the edge. Threading one would move a border by that much, so they are left, as the brief's "tight tolerance" asks.
   - Five of B's are the near-vertex T-junction lines the audit still shows. All five are seams between two materials, which SketchUp draws either way. Threading them would close a possible hairline crack in Unity along those seams, not a SketchUp line.
   - The decision is the controller's: keep the tolerance, or widen `thread_tolerance` to half a print step (0.005 in), which sits in the empty band.
2. **Double layers.** The remaining same-material lines (9 on B, 2 on A) are one layer's edge lying over another layer, with no vertex on the line. Examples: A's 551.3 in hypotenuse over the back-to-back pair on x = 2515.77 (regions 242/243), and B's 45.5 in, 44.0 in and 40.6 in lines. Only removing or rebuilding a layer can remove them (overlap removal, side rebuild).
3. **The audit script overstates lines inside surfaces.**
   - Its T-junction class ignores material: 15 of B's 24 lines are material seams.
   - Its "line inside a flat surface" class counts an edge that two coplanar same-material faces share even when both lie on the same side of it. A's new 511.8 in line is the top edge that the back-to-back pair of face 2546 (split by T1) and region 243 now share. Both layers end there, so the writer keeps it as outline. Before T1 the same line was drawn as two overlapping one-face edges (551.2 in and 511.8 in).
   - The writer's own `visible_lines_inside_surfaces` separates these cases: A 4 -> 3, B 17 -> 14.
4. **The QA sheet shows fans that SketchUp hides.**
   - T1 split B's lower-left sloped panel, made of copied-through triangles, into fans at the vertices along its edges. `qa/top.png` shows the fan because the QA sheet draws every edge of a row that has no ring; at HEAD it showed a few large triangles there.
   - The `.skp` rendered with only the edges SketchUp draws (`docs/superpowers/records/scripts/render_skp.py`) shows the panel clean at HEAD and at T1: the fan edges are soft.
   - The QA sheet does not model the writer's softening. That limitation is older than T1, but T1 makes it show.
5. **Coincident SketchUp faces.** A's `.skp` now has 3 coincident faces (`coincident_faces_merged: 3`, 570 planned -> 567 faces). They come from two double layers whose triangulations threading made identical:
   - the back-to-back pair of merge-input faces 164 (-x) and 2528 (+x) on x = 1536.44;
   - the same-facing pair 2215 and 2447 on y = 22630.1, which rule 3 had already excluded as an overlap.

   SketchUp merges each pair into one face; the OBJ keeps both layers, as before.
6. **Visible non-manifold edges rose** from 49 to 76 on A and from 28 to 47 on B. Of the new ones, 27 of 28 (A) and 20 of 23 (B) were drawn at HEAD as two or more overlapping edges along the same line. They are now one edge shared by every face meeting there. Visible edges overall went down: A 923 -> 919, B 568 -> 550.
7. **More triangles:** A +111 (+12.3 %), B +46 (+8.3 %). Each threaded vertex adds a ring vertex or splits a triangle. `vertices_dropped` also rose by 11 (A) and 14 (B). Presumably, threaded rings now agree on both sides of a former T-junction, so fewer vertices are forced by divergence; this was not traced vertex by vertex.
8. **Not done here:** the ledger entry and releasing the T1 claim, both listed in `docs/superpowers/records/briefs/01-T1-tjunction-repair.md`. My task limits edits to `engine/` and this report.

## Public signatures

```python
# engine/fixes/merge.py
THREAD_TOL_QUANTA = 1e-5          # new: "on an edge" is within this fraction of the coarsest print step
MAX_THREAD_ROUNDS = 8             # new: backstop for the output pass (measured: 1 round of splits, then 0)

def thread_tolerance(quanta: np.ndarray) -> float
    # THREAD_TOL_QUANTA * max(quanta); 1e-6 in on both real files

def merge_regions(mesh: MeshData, topo: Topology, flat_materials: Iterable[int] = frozenset(),
                  grid_size: float = GRID_SIZE, snap_tol: float = SNAP_TOL,
                  collinear_tol: float | None = None) -> MergeResult
    # signature unchanged; report gains "t_vertices_before", "t_vertices_after" (distinct vertices on an
    # edge's interior, find_t_vertices at thread_tolerance, non-degenerate faces) and "edges_split" (int)

class MergeResult:  # fields unchanged
    # source_faces: a copied-through face split at threaded vertices is several rows, each [face]
    # face_region: -1 for every piece of a split copied face
    # rings: a region's loops include every vertex threaded into its border; a vertex on a diagonal
    #        (inside the polygon) is used by the region's triangles but is in no loop

# private
class _Plan: ...; origin: np.ndarray; basis: np.ndarray   # new, required
             threaded: list = []    # new: (a, b, [vertices]) per union ring segment threaded
def _thread_union_rings(topo: Topology, plans: list[_Plan], tol: float) -> None
def _inside_segment(positions: np.ndarray, candidates: np.ndarray, a: int, b: int,
                    tol: float) -> np.ndarray
def _extend_plan(plan: _Plan, positions: np.ndarray, ids) -> None
def _thread_output(topo: Topology, builds: list, copied: list[int], kept: dict[int, list],
                   tol: float) -> tuple[list, dict[int, list], set[tuple[int, int]]]
    # (builds, copied_split {face: [welded triples]}, split_edges)
def _split(tri: tuple, on_edge: dict) -> list[tuple]
def _between(on_edge: dict, p: int, q: int) -> list[int]
def _thread_ring(ring: np.ndarray, on_edge: dict) -> np.ndarray
def _barycentric(point: np.ndarray, corners: np.ndarray) -> np.ndarray
def _kept_threads(builds: list, kept: dict[int, list]) -> set[tuple[int, int]]
def _count_t_vertices(positions: np.ndarray, face_w: np.ndarray, tol: float) -> int
def _region_loops(plan: _Plan, kept: list, welded_to_original: np.ndarray)   # was (plan, needed, keep_all_set, welded_to_original)
def _assemble(mesh, topo, welded_to_original, builds, copied, flat, region_rings=None,
              copied_split: dict[int, list] | None = None) -> MergeResult   # copied_split new

# engine/tests/fixtures/build.py (appended at the end)
def slab_beside_gridded_neighbour(seam=0.37, material=0, uv_per_unit=0.05) -> MeshData
def triangle_under_gridded_slab(uv_per_unit=0.05) -> MeshData
def slab_with_a_wall_foot_on_its_diagonal(uv_per_unit=0.05) -> MeshData
```
