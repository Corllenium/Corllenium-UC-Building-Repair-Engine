### Task 5: Planar region merge kernel

**Files:** Create `engine\fixes\merge.py`, `engine\tests\test_merge.py`. Modify fixtures.

**Interfaces — Consumes:** `analyse_topology`, `Topology`, `plane_basis`, `fit_uv` / `cluster_uv`.
**Produces:** `merge_regions(mesh, topo, flat_materials) -> MergeResult` with
`mesh: MeshData`, `source_faces: list[np.ndarray]` (new face -> original faces of its region, or the single
original face when untouched), `report: dict` (`regions_merged`, `regions_skipped` with reason counts
`overlap` / `new_vertex` / `invalid_polygon` / `area_grew`, `tris_before`, `tris_after`, `vertices_dropped`,
`max_area_rel_error`).

Algorithm (each numbered rule is a test):
1. Work per region of `topo.face_region`. Regions of 1 face are copied through.
2. Project the region's welded vertices with `plane_basis` of the area-weighted region normal. Build
   `{vertex id -> 2D}` once, triangles as shapely polygons.
3. **Overlap per triangle**: a triangle whose intersection area with another triangle of the same region exceeds
   `1e-9 + 1e-6 * its area` is excluded from the merge and copied through. The rest are unioned.
4. Union with `grid_size=1e-4`. Every ring coordinate must map to an existing vertex id within `1e-3` (nearest
   search among the region's vertices). Any miss -> skip the region, reason `new_vertex`.
5. **Global corner pass**, after rings exist for ALL regions: a welded vertex is *needed* when it is a corner
   (distance to the chord of its ring neighbours > collinearity tolerance, or the path doubles back) in any ring,
   or is used by any face that is copied through (overlap, single-face region, skipped region, degenerate-free
   unmerged face), or lies on an edge classed OPEN, NONMANIFOLD or TJUNCTION. Only vertices not needed are dropped,
   and they are dropped from every ring, so both sides of a shared border stay identical. No new T-junctions.
6. Rebuild each polygon from its kept ring vertices. If it is invalid or its area differs from the union area by
   more than `1e-6` relative plus `tol * perimeter`, fall back to keeping all ring vertices for that region.
7. `shapely.constrained_delaunay_triangles`, map every output vertex back to its id (exact 2D match against the
   kept ring vertices; any miss -> skip region, reason `new_vertex`). Wind triangles to the region normal.
8. UVs: flat material -> new `vt` entries from the region's least-squares UV fit (largest member seeds, iterative
   refit), re-based so the region's minimum UV lies in [0,1). Patterned material -> same fit (the region is one UV
   class by construction). One new `vn` per region.
9. Area check per region: merged area <= original area * (1 + 1e-6), else skip with reason `area_grew`.

New fixtures and exact expectations:
| Fixture | Expect |
|---|---|
| `grid_slab(10,10)` | 200 -> **2** tris, 117 of 121 vertices unused by faces, area equal |
| `l_shaped_slab()` (10x10 grid with a 5x5 corner removed) | -> **4** tris (6 corners) |
| `slab_with_hole()` (10x10 grid, 2x2 cells removed in the middle) | -> **8** tris (8 corners, 1 hole: n + 2h - 2) |
| `two_slabs_sharing_border()` (two coplanar 5x10 grids, different materials, shared border with 9 collinear vertices) | each -> 2 tris, all 9 border vertices dropped from both |
| `slab_with_wall()` (grid slab + one vertical wall triangle standing on an interior grid vertex and a border vertex) | the two wall-foot vertices survive in the slab's triangulation |
| `overlapping_pair()` (grid slab + one extra coplanar triangle overlapping two cells) | overlapping triangle and the cells it overlaps copied through, rest merged, `regions_skipped` empty |
| `cube()` | 12 -> 12 tris, nothing dropped |

- [ ] **Step 1:** write all fixture tests, run, see them fail. **Step 2:** implement. **Step 3:** pass.
- [ ] **Step 4: real-data check** on file A after hidden removal: report tris before/after, regions merged/skipped by
  reason, vertices dropped. Spike floor estimate was 2,073 with all border vertices kept, so expect **<= 2,073**.
  A number above that means the corner pass is not working: investigate before moving on.
- [ ] **Step 5:** Commit `feat(engine): planar region merge over existing vertices`.

