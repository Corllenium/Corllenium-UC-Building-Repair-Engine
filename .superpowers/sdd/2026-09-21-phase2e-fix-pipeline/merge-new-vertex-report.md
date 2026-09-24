# Merge: union corners no vertex explains (N1, N2, N3): report

Branch `feat-dashboard`, from `8ffbda3`. Only `engine/` was edited.

| item | commit |
|---|---|
| N1 `fix(engine): the merge snaps union corners within a measured precision bound` | `d6ef1a9` |
| N2 `fix(engine): a union corner no vertex can explain sets aside only the triangles that make it` | `b3b9ad3` |
| docstring measurements (no code change, AST-identical) | `1ee69e3` |
| docstring slip: the ramp fan's edges are 0.3 to 4.7 degrees apart, not 4.4 | `a03967d` |
| docstring slip: subset unions put the ramp's tips up to 0.0053 in out (no code change) | `e182922` |
| N3 | report only, no commit |

Engine suite at `a03967d`: `384 passed` (368 at `8ffbda3`; +5 N1 tests, +11 N2 tests). `e182922`
changes one docstring; merge tests re-run there: 54 passed.
This report file itself is not committed.

## In one paragraph

Both skipped regions now merge. File A's 274-triangle sloped underside and file B's ramp failed for the SAME
reason. Each triangulation has T-junctions (a vertex lying exactly on a neighbour's edge). The union's 1e-4 in
grid leaves slivers one grid cell wide along those lines. A sliver's corner either lands anywhere along the
line (7.87 in from every vertex on A) or snaps to three or four distinct collinear vertices (B), and a rebuilt
polygon cannot carry either one. The fix is at the source: a union ring narrower than two grid cells is closed,
whatever its corners snap to. The requested set-aside mechanism is in place as the general fallback. It is proven
on the real region with the slivers left open, but sets nothing aside on either file.

The brief's N1 hypothesis was wrong. Corners near a vertex are not moved by projecting off-plane vertices: they
are grid tips. N1's per-region tolerance, alone, changes nothing on either file (below).

## N1: the snap tolerance, measured

**Measurement** (merge inputs of both files, captured from `fix_object`; 271 regions of two or more faces; 3,441
union ring coordinates; distance to the nearest existing vertex, exactly what `_nearest_ids` compares):

| distance to nearest vertex | coordinates | what they are |
|---|---|---|
| < 7.1e-5 in (half a grid cell's diagonal) | 3,415 | the vertex itself, rounded to the grid |
| 7.1e-5 to 4.0e-4 in | 24 | 23 tips at a vertex, 1 T-junction sliver corner (A) |
| 0.0016 in | 1 | tip at the apex of B's ramp fan |
| (nothing between 0.0016 and 7.87 in) | 0 | |
| 7.87 in | 1 | T-junction sliver corner on A's underside (N2) |

- The 205 axis-aligned regions are exactly flat (thickness 0). Every coordinate of theirs is within 3e-12 in of a
  vertex: their vertices project ONTO the grid.
- The 66 other regions are 0.0081 in thick at the median and 0.1108 in at most. Thickness is the spread of a
  region's vertices along its own normal.
- All 25 tail coordinates lie on such regions, and none is farther than 0.19 of its region's thickness out
  (worst: B's ramp, 0.0016 / 0.0085).
- 24 of the 25 are tips AT a vertex: every triangle edge within 2e-4 in of them ends at that vertex. The narrowest
  angle between two edges at that vertex is 0.3 to 37 degrees.

**Mechanism.** Projection cannot do this: a shared vertex projects to one point and collinearity survives a
linear map. The union's grid does it. Where two of a vertex's edges meet at a narrow angle, the two snapped edges
part by a cell and meet again about `cell / sin(angle)` from the vertex. On B's ramp the fan edges are 0.3 to
4.7 degrees apart at the apex, which gives a 0.0016 in tip.

**Rule** (`snap_tolerance`): `tol = clamp(thickness, SNAP_TOL = 1e-3, SNAP_TOL_MAX = 0.01)`, per region.
- The thickness is the scale for two reasons. Exactly the regions the export could not print flat are the ones
  whose vertices land off the grid. And rebuilding such a region already moves its surface by up to its
  thickness.
- 0.01 in is one X/Z print step: 1/15 of the 0.15 in border tolerance and 1/787 of the 7.87 in coordinate.
- `region_outline` (solidify) uses the same tolerance. Rule 6 is unchanged.

**Tests (5):** the clamp; each region is planned with its own thickness (`grid_slab` 0.0 in; `printed_ramp`
0.0046 in); a corner 0.0016 in off its vertex merges; a corner 0.5 in off is never snapped (not even at the
ceiling); an exactly flat region keeps the floor.
- Deviation: the region-level test moves the union's first corner by 0.0016 in along its ring, by wrapping
  `_union`. It runs on a real-precision sloped fixture (`printed_ramp`: Z printed to 0.01 in, so 0.0046 in
  thick).
- Why: no small region reproduces a grid tip. The grid is anchored at the region's own first vertex, so any
  extracted subset re-anchors it. Ten-triangle subsets of the real ramp show outer-ring tips of 0.0011 to
  0.0020 in inside the full region's frame. The one I extracted as a standalone mesh showed none, and split
  into two regions.
- The whole real ramp is tested in N2.

**Effect on the real files: none by itself.**
- N1 alone moved B's ramp from `new_vertex` to `invalid_polygon`: its T-junction slivers remained.
- With N2 in place, the merge with N1 switched off (`SNAP_TOL_MAX = SNAP_TOL`) gives identical meshes and
  reports on both final inputs, because the 0.0016 in tip sits in a sliver hole that N2 closes.
- N1 is a margin for outer-ring tips. Unions of subsets of the same ramp put those tips up to 0.0053 in from
  their vertex, three of them beyond the 1e-3 in floor.

## N2: the cause on file A, the source fix, the set-aside

**Cause, with numbers.** A's region 70 (69 in the final run's numbering): 274 triangles, 218 vertices, normal
`[0.1465, 0, -0.9892]`, 0.0105 in thick.

It is not any of the brief's candidates:
- Not a fold or flip: all 274 projected triangles are wound positively.
- Not a remnant of a duplicate layer: none of them was an overlap-removal candidate, and none was invented by
  solidify.
- Not a sub-threshold partial overlap. Rule 3 excludes 4 triangles (147.2, 147.2, 73.6 and 48.7 sq in), but they
  are unrelated to the corner.

What it is:
- The triangulation is a T-junction lattice. 54 of its 218 vertices lie strictly inside an edge of another of its
  triangles, all at 0.000000 in, along 36 edges up to 629.9 in long.
- The 7.87 in coordinate is a corner of a union hole `[X, 1495, 1493]`, 71 in long and 5.6e-5 in wide
  (`4*area/perimeter`).
- Vertex 1497 at (2594.51, 23141.9, 1766.4) lies 0.000000 in off the 236.2 in edge of merge-input face 1588
  (snapshot OBJ line 8039). The 39.4 in edge of merge-input face 1612 (line 8069) ends on it.
- The grid snaps the long edge and the short one independently. They cross at about 4e-7 rad, so the crossing
  lands anywhere along the line: here 7.87 in from vertex 1497.
- The unsnapped (float) union has 14 zero-area sliver holes along such lines; the 1e-4 grid leaves 3:
  - one collapses to 2 vertices (already closed);
  - `[1420, 1300, 1467]` snaps to 3 distinct collinear vertices: a zero-width hole a rebuilt polygon cannot
    carry;
  - one has the 7.87 in corner.
- B's ramp is the same mechanism. `[1400, 1398, 1393, 1390]` (213.8 in by 7.4e-5 in) and `[1410, 1407, 1404]`
  snap to 4 and 3 collinear vertices.

**Fix at the source** (`_pieces` / `_is_sliver`): a union ring whose mean width `4*area/perimeter` is at most
`SLIVER_CELLS * GRID_SIZE` = 2e-4 in is a sliver. A sliver hole is closed and a sliver island is dropped, whatever
its corners snap to. Over every region of both files, 13 of the 33 union holes are slivers (5.0e-5 to 8.9e-5 in
wide), the other 20 are openings at least 0.25 in wide, and no outer ring is narrower than 0.75 in.

**The set-aside** (`_region_union`, the general fallback): a corner in a ring that is not a sliver, with no vertex
within the region's tolerance, is handled like this:
1. The kept triangles whose projected BOUNDARY passes within the tolerance of such a corner are set aside
   (`shapely.distance`). Every union ring coordinate lies on the snapped edges of the triangles that bound it, so
   a corner where two edges cross lies on both.
2. They are copied through exactly like rule-3 exclusions. Every vertex of a copied face is `needed`, so no
   T-junction opens.
3. The rest is unioned again, up to `MAX_SET_ASIDE_ROUNDS = 3` rounds.
4. The region is then given up whole as before (`new_vertex`) if a corner remains, or when every remaining
   triangle would go.

`new_vertex_triangles_set_aside` counts set-aside triangles in regions that merged. `regions_skipped` counts only
regions given up whole.

**Proof on the real region** (production code, slivers left open with `SLIVER_CELLS = 0`):
- One round. The corner is 4.6e-5 in from exactly two triangles, fixture faces 102 and 126 (merge-input faces
  1588 and 1612, snapshot OBJ lines 8039 and 8069; edges 236.2/239.5/39.8 and 56.0/39.4/39.8 in).
- No other triangle is within its tolerance (0.01 in: the region is 0.0105 in thick, so the ceiling applies), nor
  within 0.0055 in.
- After those two are set aside, the rest maps onto vertices.
- The region then builds only on the `keep_all` fallback, because the 3-vertex zero-width sliver makes its
  simplified polygon invalid: 148 triangles (6 copied), 2 rounds.
- With the source fix it is 102 triangles (4 copied, rule 3), 1 round and 12 real openings, and nothing is set
  aside.
- Whole file A (pre-change capture): with set-aside and no sliver rule, 956 triangles and 1 `keep_all` region;
  with the sliver rule, 905 (902 in the final pipeline run).

**Tests (11):**
- `_pieces`: a thin hole with a corner no vertex explains is closed; a thin hole bounded by three collinear
  vertices is closed; a hole one print step (0.01 in) wide is kept (this one passed before the change: it pins
  existing behaviour); a thin island is dropped.
- Real regions: `t_junction_lattice_region` (all 274 of A's triangles, OBJ fixture) merges whole with 12 inner
  loops, with a precondition that its union still has the 7.87 in corner and 15 holes. `ramp_fan_region` (all 49
  of B's) merges to one hole-free polygon, with preconditions on the 0.0016 in tip and the 1/3/4-vertex holes.
- Set-aside: `frame_with_crossed_seam` has two seam edges crossing 50 in from every vertex at 3.4e-4 degrees.
  Only the crossing pair (faces 0 and 3) is copied, the area is unchanged, and no vertex lies inside another
  triangle's edge except the input's own {9, 11}.
- Determinism (passed before the change too).
- With `MAX_SET_ASIDE_ROUNDS = 0` the region is given up whole, with nothing counted as set aside.
- `region_outline` sets aside the same triangles as the merge.
- An ordinary merge reports 0.

## N3: file B's two `overlap` regions (report only)

Final run: regions 38 and 79 (79 was 81 before the change; both already existed at `8ffbda3`). Together they are
5 triangles, every one excluded by rule 3, so they are copied through. The overlap removal never proposed any of
them (none is covered at least 0.99 by its region), and its guard restored nothing.

1. **Region 38**: material `mumi_littletiles_ltstone_-3`, a vertical side face at x = 1688.77 in, y 24008.0 to
   24012.9, z 2094.49 to 2108.99.
   - It holds 2 original triangles (OBJ lines 8174 and 8175; 11.4 + 35.5 sq in, together a trapezoid) and 1
     triangle solidify invented (35.5 sq in) over the same spot.
   - The overlaps are 8.0 and 17.8 sq in, and the covered fractions are 0.50 to 0.73.
   - Why the skirt is there: in solidify's input, the side face's top edge (vertices 1015 to 1033, welded 318 to
     320) belongs to that side triangle alone, so its edge-table count is 1. The edge also lies on the outline of
     the top surface above, so `_open_edges` took it for an open edge and hung a 14.5 in skirt down over a side
     face that already exists.
   - This is a solidify defect.
2. **Region 79**: material `mumi_littletiles_ltstone_-8`, a vertical wall on the diagonal (normal
   `[-0.4475, 0.8943, 0]`), x 2870.1 to 2909.47, y 23427.3 to 23447.0, z 1807.2 to 1818.9.
   - It holds 2 original triangles of 128.3 sq in each (OBJ lines 10834 and 11402, 568 lines apart, so two
     different pieces of the export).
   - They share their vertical edge and BOTH lie on the same side of it, with apexes at z 1817.08 and 1807.23: a
     fold. 47.7 sq in (37%) is covered twice. Covered fraction 0.37.

The set-aside does not apply. Rule 3 excludes both regions whole before any union: the overlaps are 8 to 48 sq in
against thresholds of 1e-5 to 1e-4 sq in (`1e-6 x` the smaller triangle's area). And region 79's only crossing is made by both of its triangles, so nothing
would be left. Nothing was extended.

## Real data

The final runs were made with the code of `b3b9ad3`; the later commits change comments only. Each file got
`python -m engine.cli fix <snapshot> --out data/output` (it also writes the `.skp` and copies it to
`OBJ FIXED RESULT/`) and then `preview-data <snapshot> --out preview/data`. Every run exited 0. The "before"
numbers are the `report.json` files at `8ffbda3`'s pipeline (written 04:03 today).

| | A before | A after | B before | B after |
|---|---|---|---|---|
| triangles input -> reference -> shipped | 4692 -> 4848 -> 1117 | 4692 -> 4846 -> **902** | 7227 -> 7434 -> 602 | 7227 -> 7418 -> **555** |
| merge triangles in -> out | 2579 -> 1117 | 2578 -> 902 | 4736 -> 602 | 4738 -> 555 |
| regions merged / of regions with 2+ faces | 177 / 178 | 178 / 178 | 90 / 93 | 89 / 91 |
| faces_copied | 358 | 87 | 110 | 66 |
| regions_skipped | new_vertex 1 | {} | overlap 2, new_vertex 1 | overlap 2 |
| new_vertex_triangles_set_aside | - | 0 | - | 0 |
| merge_rounds / keep_all_regions | 2 / 1 | 1 / 0 | 1 / 0 | 1 / 0 |
| converged / rolled back | yes / no | yes / no | yes / no | yes / no |
| guard_after_removal: holes, material_changed, moved (same_flat+other), edge_flicker, border_shift | 0,0,0,0,0 | 0,0,0,0,0 | 0,0,0,0,0 | 0,0,0,0,0 |
| guard_merge_attempt = guard_final: holes, material_changed, moved, edge_flicker, border_shift | 0,0,0,0,59 | 0,0,0,0,106 | 0,0,0,0,43 | 0,0,0,0,47 |
| zfight_tie / crack_closed / fragment_removed px (final) | 0 / 0 / 23 | 0 / 0 / 24 | 0 / 0 / 14 | 2 / 0 / 14 |
| invariants (material_count_same, bbox_same, area_not_grown, cap_guard_passed, guard_passed) | all true | all true | all true | all true |
| passed | True | True | True | True |
| solidify skirts / invented vertices / refused by cap guard / outline_unmappable | 99 / 142 / 134 / 1 | 98 / 142 / 134 / 1 | 42 / 208 / 69 / 1 | 46 / 228 / 93 / 0 |
| .skp faces (polygons + triangles), inner loops, nonplanar fallbacks | - | 517 (159 + 358), 0, 19 | - | 220 (79 + 141), 8, 9 |

**Determinism:** two `fix` runs of A wrote byte-identical `report.json` (sha256 `b0eb2247...6491144` both).

**QA images** (read from `data/output/.../qa/` after the final runs):
- A `obl_bot_a.png`: all of file A seen obliquely from below. The stepped sidewalk is at the upper left, then the
  ramp, and at the lower right the big sloped underside, drawn as two broad flat panels split by one ridge line
  with only a few small outlines and short line fragments on it. **It is no longer a triangle lattice.**
- A `chunk2_bottom.png`: a closer view from below of that right-hand underside. Two broad sloped panels meet at the
  ridge, the skirt rim runs along the far edge, and a handful of small rectangular outlines and a cluster of long
  thin slot-like lines sit near the right corner. There is no triangle lattice.
- B `top.png`: file B from above. The walkway and landing are a dozen or so large flat faces with clean borders.
  The sloped panel below the landing is still drawn as about 17 long triangles, with a small knot of
  copied-through triangles at its top corner (concern 4).

## Concerns

1. **N1 alone fixes nothing on these files.** The merge is identical with it switched off. The sliver rule is what
   merged both regions. N1 stays as a measured margin for outer-ring tips.
2. **Solidify reads the same outlines, so B's reference changed.** The ramp is no longer unmappable to solidify.
   It now gets skirts: 46 skirts (was 42), 228 invented vertices (was 208), 93 faces refused by the cap guard (was
   69), 28 newly hidden (was 23), reference 7418 triangles (was 7434). The cap guard passed.
   - On A one 29.5 in skirt is gone (98 skirts, was 99). Its edge bounded a 3-vertex sliver hole inside top
     region 51 (a T-junction line), not a real border.
3. **In the .skp, A's underside (final region 69) is 111 soft-edged triangles, not one polygon.** The SketchUp
   writer's planarity check sends any region more than 1e-3 in off its plane to triangles, and this one is 0.0052
   in off. That is 19 such regions on A and 9 on B.
   - The QA images draw the merge's rings. In SketchUp the diagonals are soft (hidden), but selecting shows
     triangles.
4. **B's region 74 (346 triangles, sloped 8 degrees) merges into 17 triangles but has no ring.** Rule 3 excludes 4
   of its triangles, which overlap each other by 0.01 to 1.62 sq in (OBJ lines 11185, 11342, 11371, 11372).
   Removing them cuts a 6.1 sq in island off the union, so it has two pieces.
   - Those 4 are the knot in `top.png`, and the 17 triangles are its long diagonals.
   - This predates the change and is out of scope.
5. **N3's region 38 is a solidify defect.** A skirt is hung on a side face's top edge because that edge's count is
   1. The fix belongs in solidify's `_open_edges`, not in the merge.
6. B's `zfight_tie` went from 0 to 2 pixels (tolerated, not a failure), after the reference changed (concern 2).
   The cause was not investigated.
7. `border_shift` pixels rose from 59 to 106 on A and from 43 to 47 on B. They are all excused as shifts of at most
   0.15 in, because more regions merged.

Scratch scripts (capture, measurements, proofs):
`C:\Users\Future26\AppData\Local\Temp\claude\D--PROJECTS-UC-MODEL-FIXER\5472478e-978d-426b-bab2-e7cf21699a70\scratchpad\merge-nv\`.

## Public signatures

```python
# engine/fixes/merge.py
GRID_SIZE = 1e-4                  # unchanged
SNAP_TOL = 1e-3                   # now the FLOOR of the per-region snap tolerance
SNAP_TOL_MAX = 1e-2               # new: its ceiling
SLIVER_CELLS = 2.0                # new: a ring <= SLIVER_CELLS * grid_size wide (4*area/perimeter) is a sliver
MAX_SET_ASIDE_ROUNDS = 3          # new

def snap_tolerance(thickness: float, floor: float = SNAP_TOL) -> float
    # min(max(floor, thickness), SNAP_TOL_MAX)

def merge_regions(mesh: MeshData, topo: Topology, flat_materials: Iterable[int] = frozenset(),
                  grid_size: float = GRID_SIZE, snap_tol: float = SNAP_TOL,
                  collinear_tol: float | None = None) -> MergeResult
    # signature unchanged; snap_tol is the floor; report gains
    # "new_vertex_triangles_set_aside" (int); regions_skipped counts whole regions only

def region_outline(topo: Topology, members: np.ndarray, grid_size: float = GRID_SIZE,
                   snap_tol: float = SNAP_TOL)
    # signature unchanged; same union as the merge (per-region tolerance, slivers closed,
    # set-aside triangles left out); None as before when it cannot be mapped

# private, used by tests
class _Plan: ...; snap_tol: float = SNAP_TOL; set_aside: np.ndarray  # original face ids, sorted
class _RegionUnion: normal, origin, basis, vertex_ids, vertex_xy, areas, excluded, set_aside,
                    pieces, snap_tol; keep (property)
def _region_union(topo, members, grid_size, snap_tol) -> _RegionUnion | None
def _corner_makers(boundaries: np.ndarray, corners: np.ndarray, tol: float) -> np.ndarray
def _pieces(union, vertex_xy, vertex_ids, snap_tol, grid_size=GRID_SIZE)
def _map_union(union, vertex_xy, vertex_ids, snap_tol, grid_size=GRID_SIZE) -> (pieces, unexplained)
def _is_sliver(coords: np.ndarray, grid_size: float) -> bool
def _nearest(coords, vertex_xy) -> (rows, distance)
def _thickness(offsets_3d: np.ndarray, normal: np.ndarray) -> float

# engine/tests/fixtures/build.py (appended at the end)
def printed_ramp(nx=4, ny=3, cell=40.0, slope_deg=23.2, x0=2870.0, y0=23700.0, z0=1931.38,
                 uv_per_unit=0.05) -> MeshData
def t_junction_lattice_region() -> MeshData        # reads t_junction_lattice_region.obj (274 tris)
def ramp_fan_region() -> MeshData                  # reads ramp_fan_region.obj (49 tris)
def frame_with_crossed_seam(size=1000.0, band=100.0, gap=6e-4, uv_per_unit=0.05) -> MeshData
```
