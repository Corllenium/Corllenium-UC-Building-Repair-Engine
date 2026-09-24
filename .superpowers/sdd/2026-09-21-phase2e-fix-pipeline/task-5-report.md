# Task 5 report -- planar region merge kernel

Branch `phase2e-fix-pipeline`. Files created: `engine/fixes/merge.py`, `engine/tests/test_merge.py`.
Modified: `engine/tests/fixtures/build.py` (new fixtures only; existing fixtures untouched).

## What was implemented

`merge_regions(mesh, topo, flat_materials) -> MergeResult` in `engine/fixes/merge.py`.

Per region of `topo.face_region`, in ascending region id:

1. Regions of 1 face (and every zero-area face, `face_region == -1`) are copied through unchanged.
2. The region's welded vertices are projected with `plane_basis` of the AREA-WEIGHTED region
   normal (`normalize(sum of the members' un-normalised cross products)`), in a LOCAL frame
   (`positions_w - origin`, origin = the first member's first vertex) because the real model sits
   near 24,000 in and the union runs on a 1e-4 grid. One `{vertex id -> 2D}` map per region;
   member triangles become shapely polygons off that map.
3. Overlap is decided PER TRIANGLE: `shapely.STRtree` gives the candidate pairs, and a triangle
   whose intersection area with another of the same region exceeds `1e-9 + 1e-6 * its own area`
   is excluded from the merge and copied through. The rest are unioned. A region is only skipped
   (`overlap`) when nothing survives the exclusion.
4. `shapely.union_all(..., grid_size=1e-4)`. Every ring coordinate is mapped to an existing
   vertex id by nearest search within `1e-3` among the region's vertices; any miss skips the
   region with reason `new_vertex`.
5. Global corner pass, after rings exist for ALL regions (see "Reading of rule 5" below).
6. Each polygon is rebuilt from its kept ring vertices, at the vertices' EXACT 2D coordinates.
   If a rebuilt polygon is invalid, or its area differs from the union's by more than
   `1e-6 * union area + collinear_tol * union perimeter`, the whole region falls back to keeping
   all ring vertices.
7. `shapely.constrained_delaunay_triangles`, every output coordinate matched EXACTLY (float
   equality against a dict of the polygon's own coordinates) back to a vertex id; any miss skips
   the region with reason `new_vertex`. Triangles are wound to the region normal
   (`plane_basis` is right-handed, so `cross(e1, e2) == n` and CCW in `(e1, e2)` is `+n`).
8. UVs: `cluster_uv` on the region's members (largest member seeds, iterative refit), the fit of
   the class the largest member seeded. Flat material -> re-based so the region's minimum UV lies
   in `[0,1)`. Patterned material -> the fit's own offset kept (the region is one UV class by
   construction, so that offset already reproduces the original tiling exactly). One new `vn` per
   merged region. New `vt`/`vn` rows are APPENDED; `positions` is never touched.
9. Area check: merged area > original area * (1 + 1e-6) skips the region with reason `area_grew`.

Output faces index ORIGINAL vertex indices via a welded-id -> lowest-original-index map built
from `mesh.face_v` / `topo.face_w` (so it can never disagree with the topology it was given).
Faces are emitted ordered by the lowest original face index of their group, so a merged region
lands where its first member was and untouched faces keep their relative order.

### Reading of rule 5 ("lies on an edge classed OPEN, NONMANIFOLD or TJUNCTION")

Implemented as: the vertex lies in the INTERIOR of such an edge, i.e. it is one of
`topo.t_vertices[e]` -- not an endpoint of it.

Hand proof that the endpoint reading is wrong: `grid_slab(10,10)` has 40 boundary edges, all
`count == 1` and therefore `EDGE_OPEN`, whose endpoints are the 40 boundary vertices. Pinning
endpoints would keep all 40 ring vertices, giving `40 + 0 - 2 = 38` triangles and `121 - 40 = 81`
unused vertices. The brief requires **2** triangles and **117 of 121** unused. The same argument
kills it a second time on `slab_with_hole()`: the hole's 8 boundary vertices sit on `EDGE_OPEN`
edges, and keeping all of them gives `4 + 8 + 2 - 2 = 12` triangles, not the required 8.

### One addition beyond the literal algorithm: interior pins

Rule 5 governs RING membership ("dropped from every ring"), but the `slab_with_wall()` row of the
fixture table requires a wall foot standing on an **interior** grid vertex to "survive in the
slab's triangulation", and an interior vertex is in no ring. So after triangulating, any vertex of
the region that rule 5 marked needed and that no ring carries is inserted by splitting the output
triangle that contains it (3 sub-triangles when strictly inside, 2 when on an edge -- and because
every triangle containing the point is split, both sides of a shared edge stay consistent).
This uses only existing vertices and preserves area exactly. It is reported as
`interior_vertices_pinned`.

## TDD evidence

RED -- all 13 tests written first, against `engine/fixes/merge.py` which did not exist:

```
$ .venv/Scripts/python.exe -m pytest engine/tests/test_merge.py -q
ImportError while importing test module '...\engine\tests\test_merge.py'.
engine\tests\test_merge.py:3: in <module>
    from engine.fixes.merge import merge_regions
E   ModuleNotFoundError: No module named 'engine.fixes.merge'
1 error in 0.21s
```

GREEN -- after implementation (one test assertion of mine was wrong and was corrected, see
"Self-review" below):

```
$ .venv/Scripts/python.exe -m pytest engine/tests/test_merge.py -q
.............                                                            [100%]
13 passed in 0.56s
```

Full suite (82 before this task + 13 new):

```
$ .venv/Scripts/python.exe -m pytest -q -W error::DeprecationWarning
........................................................................ [ 75%]
.......................                                                  [100%]
95 passed in 2.86s
```

## Fixture table -- measured against the brief

| Fixture | Brief expects | Measured |
|---|---|---|
| `grid_slab(10,10)` | 200 -> 2 tris, 117 of 121 vertices unused, area equal | 200 -> **2**, `vertices_dropped` **117**, `max_area_rel_error` **0.0** |
| `l_shaped_slab()` | 4 tris (6 corners) | 150 -> **4**, 6 vertices used, area equal |
| `slab_with_hole()` | 8 tris (8 corners, 1 hole) | 192 -> **8**, 8 vertices used, area equal |
| `two_slabs_sharing_border()` | each -> 2 tris, all 9 border vertices dropped from both | 200 -> **4**, 2 regions merged, the 9 shared vertices used by NO output face, the 2 border ENDS kept |
| `slab_with_wall()` | the two wall-foot vertices survive in the slab | both survive; slab 200 -> 9 tris + 1 wall face, `interior_vertices_pinned` 3 |
| `overlapping_pair()` | overlapping tri + the cells it overlaps copied through, rest merged, `regions_skipped` empty | copied through = exactly faces `{44, 46, 47, 200}`, `regions_skipped == {}`, 201 -> **13** |
| `cube()` | 12 -> 12, nothing dropped | 12 -> **12**, `vertices_dropped` **0**, 6 regions merged |

Hand-check of `slab_with_wall`'s 9 slab triangles: the exterior ring keeps 4 corners + the border
foot `(0,50)` = 5 vertices -> `5 + 0 - 2 = 3` triangles; 3 interior pins (the foot `(30,50)` and
the two T-vertices `(10,50)`, `(20,50)` that lie on the wall's base edge, which is `EDGE_TJUNCTION`)
each split a triangle in three, +2 each -> `3 + 6 = 9`. Measured 9.

Hand-check of `overlapping_pair`'s 13: the extra triangle `E = (20,20)-(40,20)-(40,30)` (area 100)
overlaps grid triangle `A = (20,20)-(30,20)-(30,30)` by 25, contains `C = (30,20)-(40,20)-(40,30)`
entirely (50) and overlaps `D = (30,20)-(40,30)-(30,30)` by 25; it does NOT touch
`B = (20,20)-(30,30)-(20,30)` (0). So E, A, C, D are excluded and copied through (4 faces) and the
union is the 100x100 square with one pentagonal hole `(20,20),(30,20),(40,20),(40,30),(30,30)`
whose 5 vertices are all pinned by the copied-through faces: `n = 4 + 5 = 9`, `h = 1`,
`9 + 2 - 2 = 9` triangles. `9 + 4 = 13`. Measured 13.

## Step 4: real-data check (file A, `data/snapshots/ce26e0392ab0/CHTM_SIDE_WALK_2nd_floor.obj`)

Pipeline exactly as briefed: `read_obj` -> `analyse_topology(mesh, frozenset({0}))` -> recentre to
bbox centre -> `compute_exposure` -> `guard_feedback(strict=True, flat_materials={0},
depth_tol=0.15)` -> `remove_faces(removable | zero-area)` -> `analyse_topology` again ->
`merge_regions`.

| Stage | Number |
|---|---|
| input | 4,692 faces, 217 zero-area, 1,589 welded vertices, 888 regions |
| hidden candidates (exposure == 0, non-degenerate) | 1,853 |
| `guard_feedback` | round 0: 223 failing px, 34 restored; round 1: **0** failing px -> **1,819 removable** |
| `remove_faces` (1,819 + 217 zero-area) | 4,692 -> **2,656** faces, 380 regions |
| **`merge_regions`** | **2,656 -> 2,123 triangles** (-20.1 %) |
| regions merged | **273** |
| regions skipped | **`overlap` 8, `new_vertex` 1, `invalid_polygon` 2** (11 of 380) |
| faces copied through | 536 = 96 single-face regions + 78 overlap-excluded members + 168 faces of early-skipped regions + 194 faces of regions skipped after triangulation |
| vertices dropped | **301** of 1,589 welded vertices (no output face uses them) |
| interior vertices pinned | 37 |
| max relative area error | **1.98e-09** |
| runtime, `merge_regions` alone | **0.38 s** |
| runtime, whole check (read -> guard renders) | 15.5 s |
| determinism on real data | two runs produced bit-identical `face_v`/`face_vt`/`face_vn`/`face_material`/`face_line`/`uvs`/`normals` |

Total 3D area: original 1,393,867.74 in2; after removal 1,202,195.820 in2; after merge
1,202,195.822 in2 (relative change 2e-9).

### 2,123 vs the 2,073 floor -- investigated as the brief requires

The brief says a number above 2,073 means the corner pass is not working. **The corner pass is
working**; the excess is the interior-pin addition. Measured on the same input by disabling one
mechanism at a time:

| Configuration | tris_after |
|---|---|
| every ring vertex kept (`collinear_tol = -1`), no pins | 2,202 |
| every ring vertex kept, with pins | 2,452 |
| **corner pass on, no pins** | **2,051** |
| corner pass on, with pins (shipped) | **2,123** |

So the corner pass itself removes 151 triangles (2,202 -> 2,051, -6.9 %) and lands **below** the
2,073 floor. The remaining +72 is the 37 interior pins (about +2 triangles each) that
`slab_with_wall()` in the fixture table requires. Narrowing pins from "any needed vertex" to "a
vertex still used by a copied-through face" (see "interior pins" above) already cut them from 122
pins / 2,293 triangles to 37 pins / 2,123.

Note my keep-everything baseline is 2,202, not the spike's 2,073: the spike's figure is an
analytic `n + 2h - 2` estimate over plane-level regions with UV ignored and no copied-through
faces, so it is a different denominator, not a target this kernel can be measured against
directly. The 273-merged / 96-single-face split confirms the spike's own conclusion that file A
"is genuinely made of many small planar pieces".

Corner-pass inputs, for the record: 1,108 of 1,589 welded vertices are `needed` (458 from
copied-through faces, 359 from T-vertices on OPEN/NONMANIFOLD/TJUNCTION edges, 877 from being a
corner in some ring); 1,080 vertices appear on a ring, 987 of those are needed and **93 are
dropped from every ring**.

### Guard: MERGED mesh vs ORIGINAL mesh, `compare_views` over `VIEWS_26`, `strict=True`

Same `frame_points` as the original (the recentred welded positions), `depth_tol=0.15`,
`flat_materials={0}`.

| | count |
|---|---|
| model pixels | 2,059,414 |
| **holes** | **1** |
| material_changed | 0 |
| **moved_same_flat** | **676** (0.033 %) |
| moved_other | 0 |
| `passed` (strict) | **False** |

Attribution -- the removal contributes nothing, all of it is the merge:

| comparison | holes | moved_same_flat | moved_other |
|---|---|---|---|
| original -> after removal | 0 | 0 | 0 |
| after removal -> merged | 1 | 676 | 0 |
| original -> merged | 1 | 676 | 0 |

**Diagnosis of the 676 `moved_same_flat` pixels: grazing incidence, not a moved surface.**
Measured over all 676:

- The angle between the view ray and the after-face's own plane is **below 5 degrees for 675 of
  the 676** pixels (median `|cos(view, normal)| = 0.0089`, i.e. 0.51 degrees). The two heaviest
  views are `(0.013, +/-0.993, 0.011)` (342 and 333 px) and the surface involved is a ramp with
  normal `(-0.2095, 0, 0.9778)` -- exactly zero Y component, so those views see it edge-on.
- The BEFORE hit point lies **0.0049 in (median), 0.076 in (max)** from the AFTER face's
  supporting plane. The surface did not move: that 0.076 in is the merged regions' own
  out-of-plane span, which is what `cluster_planes` admits (`1.5 * |n| . quanta`, up to 0.15 in
  with `quanta = [0.01, 0.1, 0.01]`). Only 30 of 676 pixels exceed 0.01 in.
- `plane_gap / |cos|` reproduces the observed deltas (predicted max 7.1 in vs observed max
  0.742 in, median observed 0.343 in): a 0.005 in perpendicular offset at 0.51 degrees grazing is
  a 0.56 in change measured ALONG the ray. The guard measures depth along the view ray, so at
  edge-on views it amplifies a sub-hundredth-inch perpendicular difference by about 110x.

So the merge moves the visible surface by at most 0.076 in perpendicular -- half the 0.15 in
depth tolerance -- and the failures are the guard's own metric at near-edge-on views. Under
`strict=False` they would still be reported (the guard never drops them silently) but would not
fail on their own; the 1 hole pixel fails either way.

**The 1 hole pixel** (view `(0.013, -0.993, -0.989)`, pixel `(281, 430)` of 600x900) is a
silhouette pixel: its 3x3 after-neighbourhood is 4 hit / 5 miss, so it sits on the model outline,
and its before-face meets the ray at 39.6 degrees (not grazing). A frame pixel is about 2.1 in
here (bbox diagonal 1,916 in over 900 px) and the merge can move a boundary by at most the
collinearity tolerance, 1e-3 in -- about 1/2000 of a pixel. One knife-edge pixel in 2,059,414
(0.00005 %) is consistent with that; the spike accepted 4 see-through pixels on this same file as
negligible.

## Files changed

- `engine/fixes/merge.py` (new, 569 lines)
- `engine/tests/test_merge.py` (new, 14 tests)
- `engine/tests/fixtures/build.py` (added `_grid`, `l_shaped_slab`, `slab_with_hole`,
  `two_slabs_sharing_border`, `slab_with_wall`, `overlapping_pair`; existing fixtures untouched)

## Self-review findings (fixed before reporting)

1. A leftover dead statement in `_needed_vertices` (a `searchsorted` result immediately deleted)
   was removed.
2. `_plan_regions` took a `mesh` argument it never used; removed.
3. Two of my own test assertions were wrong, not the implementation, and were corrected after
   hand-checking which side was wrong:
   - `test_new_uv_and_normal_rows_are_appended_not_overwritten` asserted the UV minimum lies in
     `[0,1)` for a PATTERNED material. Rule 8 only re-bases flat materials, so the assertion was
     testing behaviour the spec does not ask for. Replaced by
     `test_patterned_material_keeps_the_fit_offset_flat_material_is_rebased`, which pins both
     branches (patterned: the fit reproduces `position * 0.05 + (7.5, -3.25)` exactly; flat: the
     minimum re-bases to `(0.5, 0.75)`).
   - `test_merged_mesh_round_trips_through_write_and_read` asserted every `face_vn == 0`. The
     copied-through wall face legitimately keeps its original `-1`. Corrected to compare against
     the merged mesh's own arrays.
4. Constraints verified by grep: nothing in `engine/` imports `api`, `spike`, `fastapi`,
   `sqlalchemy`, `trimesh`, `embreex` or `random` outside `engine/rays/`. No randomness anywhere
   in the new code; every iteration is over a sorted array, an index range, or an insertion-ordered
   list, and determinism is asserted both on a fixture and on the real model.

## Concerns

1. **2,123 > the brief's 2,073 expectation**, explained and decomposed above. Without interior
   pins the kernel lands at 2,051. Pins exist only because the `slab_with_wall()` row of the
   fixture table requires a wall foot on an interior vertex to survive, which rule 5 (which governs
   RING membership) cannot deliver on its own. If the controller prefers the triangle count to the
   fixture row, deleting `_insert_pins` and that row is a two-line change.
2. **The guard does not pass under `strict=True`** (1 hole + 676 moved_same_flat of 2,059,414).
   The evidence above says the surface is intact to 0.076 in perpendicular and the failures are
   grazing-incidence artefacts of measuring depth along the view ray, but this is a real
   `passed == False` and should not be papered over. If a later task wants a passing guard here,
   the honest fix is in the guard (measure depth perpendicular to the surface, or exempt pixels
   whose ray meets the surface below a few degrees), not in the merge.
3. **Late skips are not fed back into the corner pass.** A region skipped by rule 7 (`new_vertex`
   at CDT time) or rule 9 (`area_grew`) is copied through AFTER the global corner pass has already
   run, so its vertices were not pinned. This follows the brief's ordering. On file A it affects
   194 faces across at most 3 regions; no new T-junction showed up in the guard (holes = 1, on a
   silhouette), but the possibility is real and worth a second pass if it ever bites.
4. **`flat_materials` only changes UV re-basing.** Rule 8 gives flat and patterned materials the
   same fit, so the parameter's only behavioural effect here is whether the region's UVs are
   re-based into `[0,1)`. It is validated the same way `analyse_topology` validates it.

## Public signatures

```
engine/fixes/merge.py

GRID_SIZE: float = 1e-4        # precision grid the 2D union snaps to (local frame, inches)
SNAP_TOL: float = 1e-3         # max distance a union ring coordinate may sit from an existing vertex
COLLINEAR_TOL: float = 1e-3    # ring vertex further than this from its neighbours' chord is a corner

@dataclass
class MergeResult:
    mesh: MeshData
    source_faces: list[np.ndarray]          # one int64 array per NEW face -> original face indices
    report: dict                            # keys below

merge_regions(mesh: MeshData,
              topo: Topology,
              flat_materials: Iterable[int] = frozenset(),
              grid_size: float = GRID_SIZE,
              snap_tol: float = SNAP_TOL,
              collinear_tol: float = COLLINEAR_TOL) -> MergeResult

report: {
  "regions_merged": int,
  "regions_skipped": dict[str, int],   # only non-zero of overlap / new_vertex / invalid_polygon / area_grew
  "tris_before": int,                  # mesh.n_faces
  "tris_after": int,                   # result mesh n_faces
  "vertices_dropped": int,             # welded vertices used by an input face and by no output face
  "max_area_rel_error": float,
  "faces_copied": int,
  "interior_vertices_pinned": int,
}
```

```
engine/tests/fixtures/build.py  (new fixtures; all return MeshData)

l_shaped_slab(nx=10, ny=10, cell=10.0, cut=5, uv_per_unit=0.05) -> MeshData               # 150 tris
slab_with_hole(nx=10, ny=10, cell=10.0, lo=4, hi=6, uv_per_unit=0.05) -> MeshData         # 192 tris
two_slabs_sharing_border(nx=10, ny=10, cell=10.0, split=5, uv_per_unit=0.05) -> MeshData  # 200 tris, 2 materials
slab_with_wall(nx=10, ny=10, cell=10.0, uv_per_unit=0.05, foot_i=3, foot_j=5, height=25.0) -> MeshData  # 201 tris
overlapping_pair(nx=10, ny=10, cell=10.0, uv_per_unit=0.05) -> MeshData                   # 201 tris
```

## Fix round 1

Branch `phase2e-fix-pipeline`, four items from `task-5-fix1-brief.md`, one commit each, test first.

| | commit |
|---|---|
| G1 guard measures surface displacement, not depth along the ray | `dcb6d37` |
| G2 silhouette flicker is its own guard class | `310b270` |
| M1 no interior pins in merged regions | `ec502b5` |
| M2 late-skipped regions feed back into the corner pass | `f8afb45` |

Baseline re-measured on file A before touching anything, and it reproduced the Task 5 report
exactly: 2,656 -> **2,123** triangles, guard totals `holes 1 / moved_same_flat 676`, feedback
`1,853 candidates / 34 restored / 1,819 removable`. Suite: **96 passed**.

### G1 -- surface displacement instead of depth along the ray

For a pixel where BEFORE and AFTER both hit, "moved" is now

```
d = max( dist(P_before, plane(face_after)), dist(P_after, plane(face_before)) )
P = pixel ray origin + t * unit view direction
```

and the pixel is moved when `d > depth_tol`. Depth along the ray divides the real offset by the
sine of the grazing angle; at the 0.51 degree median measured in the Task 5 report that is a 110x
amplification, which is where all 676 `moved_same_flat` pixels came from.

`ortho_first_hit` now returns a `HitBuffers` dataclass: `depth` and `tri` as before, plus the
camera frame (`direction`, `right`, `up`, `xs`, `ys`, `standoff`) so any pixel's hit point is
recoverable. `origins` is a PROPERTY, rebuilt from the frame on access, not a stored array -- a
900x600 origins buffer is 13 MB and `guard_feedback` holds 26 renders at once, so storing it would
have added 337 MB of resident memory for nothing. `HitBuffers` iterates, indexes and `len()`s as
the `(depth, tri)` pair it used to be, so `depth, tri = ortho_first_hit(...)`, `before[0]` and
`save_triptych(path, before, after, codes)` all still work unchanged.

`face_planes(positions, faces) -> (F, 4)` gives each triangle's `[nx, ny, nz, d]`, all-zero for a
zero-area triangle. `classify_pixels` takes `origins` / `direction` / `plane_before` /
`plane_after` as keyword arguments; a pixel whose before- or after-face has no plane falls back to
`|t_before - t_after|`, and so does a caller that supplies no geometry at all (which is how the two
pure-classification tests stay unmodified). `compare_views` takes `plane_before` / `plane_after`
and passes the BEFORE render's origins and direction down; it raises if the two renders of a view
used different directions. `guard_feedback` builds the planes once from `positions_c`/`faces` and
uses them for both sides -- correct there because only face PRESENCE changes between its renders.

Verdict precedence is unchanged: hole, material_changed, moved_same_flat, moved_other.

RED:

```
$ .venv/Scripts/python.exe -m pytest engine/tests/test_guard.py -q
E   ImportError: cannot import name 'face_planes' from 'engine.guard.compare'
1 error in 0.71s
```

GREEN: `16 passed`, full suite `99 passed`.

Three tests added:

1. `test_grazing_view_does_not_report_a_coplanar_shift_as_moved` -- a 400x400 quad seen 1 degree
   above its own plane, AFTER shifted 0.01 along its normal, `depth_tol = 0.15`. The test first
   asserts 768 both-hit pixels and that the OLD metric would have fired
   (`max |t_after - t_before| = 0.573 > 0.15`), then asserts `moved_same_flat == moved_other == 0`.
2. `test_grazing_view_still_catches_a_face_removed_over_a_surface_behind_it` -- same view, the
   quad removed, a parallel quad 10 in behind it (long enough in x that a ray skimming the front
   quad still lands on it 573 in further along). 576 pixels come back `moved_same_flat`, and
   `passed` is False. Grazing views do not hide real damage.
3. `test_undefined_plane_falls_back_to_depth_along_the_ray` -- a degenerate face's all-zero plane
   row keeps the old `|t_before - t_after|` test for those pixels.

Existing tests: only call sites changed, never an assertion. `_render_views` builds
`(view, HitBuffers)` instead of `(view, depth, tri)`, and the five `compare_views` calls now pass
`plane_before` / `plane_after` so they exercise the new metric rather than the fallback.

### G2 -- silhouette flicker is its own class

`PX_EDGE_FLICKER = 5`: a would-be hole whose 3x3 neighbourhood in BEFORE contains a miss. The
neighbourhood is a separable dilation of the miss mask over the last two axes; a neighbour OUTSIDE
the image does NOT count as a miss, so a hole is only ever downgraded on evidence of real
background (and `ortho_first_hit` frames the model with a margin, so the silhouette never reaches
the border anyway). That choice also leaves `test_classify_pixels_priority_order`, which runs on a
1-D buffer, untouched.

`ViewVerdict` and `totals` gain `edge_flicker`. `compare_views(..., edge_flicker_cap: float = 0.0)`
judges it PER VIEW: that view's flicker pixels are tolerated only while
`edge_flicker <= edge_flicker_cap * model_px`, otherwise all of them count as failures. At the
default 0.0 each one fails exactly like a hole. An interior hole is never classed flicker and fails
at any cap. `guard_feedback` always uses 0.0 -- removing a face is not a change a person accepted --
and `_fail_mask` counts flicker as damage there. `save_triptych` paints flicker amber, next to
`moved_same_flat`: amber is "reported, tolerated by some caller", and whether it actually failed
depends on a cap that module is not given.

RED:

```
$ .venv/Scripts/python.exe -m pytest engine/tests/test_guard.py -q
E   ImportError: cannot import name 'PX_EDGE_FLICKER' from 'engine.guard.compare'
1 error in 0.68s
```

GREEN: full suite `103 passed`.

Four tests added, all on synthetic `HitBuffers` (a 150x150 block of model inside a 200x200 frame,
22,500 model pixels, so the 1e-4 cap allows 2.25 pixels and the arithmetic is exact):
classed flicker and failing at cap 0.0; 1 pixel passing at cap 1e-4; 4 pixels failing at cap 1e-4;
an interior hole failing at caps 0.0, 1e-4 and 1.0.

One existing assertion had to grow: `test_identity_all_counts_zero_and_passed` compares `totals`
against a literal dict, which now needs `"edge_flicker": 0`. Same assertion (everything zero), one
more key.

### M1 -- no interior pins

`_insert_pins` and `_split_at` are gone, `_needed_vertices` returns only `needed`, and
`report["interior_vertices_pinned"]` is gone with them. A wall standing on the INTERIOR of a slab
needs no shared vertex: the slab surface is continuous beneath it, perpendicular contact cannot
open a crack, and an interior vertex makes it impossible to export the region as one polygon later.
RING vertices another face uses are untouched -- still needed, still kept by the corner pass.

The `slab_with_wall()` row of the plan's fixture table was wrong and is corrected.

**Hand count, 3 slab triangles.** The slab is one 100x100 square region with no holes, so it
triangulates into `n + 2h - 2 = n - 2` triangles over its `n` surviving RING vertices. The corner
pass keeps the 4 square corners, plus `(0, 50)` -- the wall foot that lies ON the slab's border,
which the copied-through wall face still uses, so it is `needed` and cannot be dropped from the
ring. `n = 5` -> **3 triangles**: the 2 a bare slab gives, plus 1 for that surviving border vertex.
The other foot, `(30, 50)`, is interior to the slab, is on no ring, and is not re-inserted. It is
still used by the wall face, just not by the slab. Total mesh: 3 + 1 wall face = 4.

That same count is why `test_merged_mesh_round_trips_through_write_and_read` now expects 4 faces
instead of 6.

RED:

```
$ .venv/Scripts/python.exe -m pytest engine/tests/test_merge.py -q
FAILED test_wall_foot_on_the_slab_border_survives_and_the_interior_foot_does_not
FAILED test_merged_mesh_round_trips_through_write_and_read - assert 6 == 4
2 failed, 12 passed in 0.73s
```

GREEN: `14 passed`, full suite `103 passed`.

### M2 -- late skips feed back into the corner pass

Pass 2 is now a fixed-point loop in `merge_regions`:

```
fed_back = {}                       # region id -> reason, accumulated
repeat (at most MAX_ROUNDS = 10):
    needed  = _needed_vertices(topo, copied + faces of every fed_back region, plans, tol)
    builds, late, err = _build_regions(plans, needed, tol)      # every region, ascending id
    stop when set(late) <= set(fed_back)
    fed_back |= late
```

A late-skipped region's faces are handed to `_needed_vertices` exactly as if already copied
through, which is what marks all of its vertices needed -- and a late-skipped region IS copied
through with all of its vertices, so that is the truthful statement of the constraint. `needed`
only ever grows and `fed_back` only ever gains region ids, so the loop terminates; the cap is a
backstop, not the mechanism. Region order is `plans` order (ascending region id) every round, so
the result stays bit-identical between runs -- verified on the real model.

A region that fed back and then SUCCEEDED keeps its vertices needed for the rest of the loop. That
is deliberate: keeping a border vertex costs one triangle and can never open a T-junction, while
dropping one that a neighbour kept can.

`report["merge_rounds"]` is the number of rounds that ran (1 when nothing skips late).

RED:

```
$ .venv/Scripts/python.exe -m pytest engine/tests/test_merge.py -q
FAILED test_merge_rounds_is_one_when_no_region_skips_late  - KeyError: 'merge_rounds'
FAILED test_late_skipped_region_feeds_its_vertices_back_into_the_corner_pass - KeyError: 'merge_rounds'
2 failed, 14 passed in 0.73s
```

GREEN: `16 passed`, full suite `105 passed`.

The test monkeypatches `merge._triangulate` so the LEFT region of `two_slabs_sharing_border()`
always returns `(None, "invalid_polygon")` -- a late skip by construction -- and asserts:
`merge_rounds == 2` (round 1 finds the skip, round 2 confirms nothing new); the left slab's 100
faces copied through; the right slab keeps all 9 collinear shared-border vertices and so lands on
`13 - 2 = 11` triangles; and, by `vertices_inside_an_edge`, that not one vertex of the left slab
lies strictly inside an edge of the right slab's triangles without being one of their vertices.
Before the fix the right slab merged to 2 triangles whose shared edge ran straight past all 9.

### Real data after the four fixes

`data/snapshots/ce26e0392ab0/CHTM_SIDE_WALK_2nd_floor.obj`, same script and same pipeline as
Task 5 step 4 (`read_obj` -> `analyse_topology(mesh, {0})` -> recentre -> `compute_exposure` ->
`guard_feedback(strict=True, depth_tol=0.15)` -> `remove_faces` -> `analyse_topology` ->
`merge_regions`). Nothing was tuned to reach a number.

#### Hidden-face feedback, with the new metric

| | old metric | new metric |
|---|---|---|
| candidates (exposure 0, non-degenerate) | 1,853 | **1,853** |
| restored | 34 | **34** |
| removable | 1,819 | **1,819** |
| round 0 failing pixels / round 1 | 223 / 0 | **223 / 0** |

Identical. The 223 failing pixels of round 0 are real damage (a removed face over background), not
grazing artefacts, so the displacement metric reports them the same way -- which is the point: the
fix removes false positives without touching true ones.

#### Merge

| | baseline | after |
|---|---|---|
| faces in | 2,656 | 2,656 |
| **triangles after merge** | 2,123 | **2,062** (-22.4 % from 2,656) |
| regions merged | 273 | **273** |
| regions skipped | overlap 8, new_vertex 1, invalid_polygon 2 | **overlap 8, new_vertex 1, invalid_polygon 2** |
| faces copied through | 536 | **536** |
| vertices dropped | 301 | **301** |
| `merge_rounds` | n/a | **2** |
| `max_area_rel_error` | 1.98e-09 | **1.98e-09** |
| runtime, `merge_regions` | 0.38 s | 0.49 s |
| deterministic across two runs | yes | **yes** |

2,062 is below the 2,073 the brief expects. Decomposed by running the same input with
`MAX_ROUNDS = 1` (i.e. M1 only, no feedback):

| configuration | tris_after |
|---|---|
| baseline (pins on, no feedback) | 2,123 |
| M1 only -- pins removed | **2,051** |
| M1 + M2 -- pins removed, feedback on (shipped) | **2,062** |

So dropping the 37 interior pins removes 72 triangles and the feedback loop adds 11 back: those 11
are the border vertices that neighbours of the 3 late-skipped regions must now keep, and they are
exactly the T-junctions the old ordering left open.

Total 3D area: original 1,393,867.737 in2; after removal 1,202,195.820 in2; after merge
1,202,195.78 in2 (relative change 3.5e-8, within rule 6's `collinear_tol * perimeter` allowance,
and `max_area_rel_error` per region is 2e-9).

#### Guard: MERGED vs ORIGINAL, `compare_views` over `VIEWS_26`, `strict=True`

Same `frame_points` as the original (the recentred welded positions), `depth_tol = 0.15`,
`flat_materials = {0}`, `plane_before` / `plane_after` from `face_planes` of the two geometries.

| total | baseline | `edge_flicker_cap=0.0` | `edge_flicker_cap=1e-4` |
|---|---|---|---|
| model_px | 2,059,414 | 2,059,414 | 2,059,414 |
| holes | 1 | **0** | **0** |
| material_changed | 0 | **0** | **0** |
| moved_same_flat | 676 | **0** | **0** |
| moved_other | 0 | **0** | **0** |
| edge_flicker | n/a | **1** | **1** |
| `passed` | False | **False** | **True** |

The 676 `moved_same_flat` pixels are gone: they were the guard's own metric at near-edge-on views,
as the Task 5 report predicted, and the merge never moved a surface further than 0.076 in.

The 1 remaining pixel is the same silhouette pixel as before (view `(0.013, -0.993, -0.989)`,
106,091 model pixels in that view), now classed `edge_flicker` rather than `hole`. At the default
cap of 0.0 it still fails, so hidden-face removal keeps zero tolerance; at 1e-4 that view tolerates
up to 10.6 flicker pixels and the guard passes. Both numbers are reported; neither is hidden.

Whole run: 21.1 s (baseline 17.9 s -- the extra 3 s is the displacement metric and the 3x3
dilation over 26 views x 2 renders).

### Files changed in fix round 1

- `engine/guard/views.py` -- `HitBuffers`, `ortho_first_hit` returns it
- `engine/guard/compare.py` -- `face_planes`, `_displacement`, `_neighbour_miss`, `PX_EDGE_FLICKER`,
  `classify_pixels` / `compare_views` / `_fail_mask` / `guard_feedback`
- `engine/guard/render.py` -- flicker painted amber
- `engine/fixes/merge.py` -- `_insert_pins` / `_split_at` removed, `_build_regions` / `_late_faces`
  added, `merge_regions` fixed-point loop, `MAX_ROUNDS`
- `engine/tests/test_guard.py` -- 7 tests added, call sites updated, 1 literal-dict assertion grown
- `engine/tests/test_merge.py` -- 2 tests added, `slab_with_wall` expectations corrected

No fixture was changed. Nothing in `engine/` imports `api`, `spike`, `fastapi`, `sqlalchemy` or
`random`; `trimesh` appears only in `engine/rays/caster.py` (checked by grep after the last
commit). No vertex is moved or invented anywhere in the four changes.

### Concerns

1. **`passed` is still False at the default cap**, on 1 pixel of 2,059,414 (0.00005 %). It is a
   silhouette pixel, correctly classed now, and the caller decides: `edge_flicker_cap=1e-4` passes.
   Nothing about it was tuned -- the cap is a caller's parameter, and `guard_feedback` hard-wires
   0.0 as briefed.
2. **`classify_pixels` silently falls back to depth along the ray when no geometry is passed.**
   That is what keeps the two geometry-free classification tests honest, and it is documented, but
   a future caller who forgets the planes gets the old metric instead of an error. Both in-repo
   callers always pass them.
3. **The `MAX_ROUNDS` cap can end a run that has not converged.** `report["merge_rounds"] == 10`
   is the only signal, and in that case the last round's late skips were not fed back. File A
   converges in 2 rounds; no fixture needs more than 2.
4. **M2 costs 11 triangles on file A and can only cost more**, since a fed-back region's vertices
   stay needed even if it later succeeds. That is the deliberate trade: triangles for the promise
   that the kernel opens no T-junction.

## Public signatures

(fix round 1 -- everything whose signature or report changed; the round-0
signatures above still hold where they are not restated here)

```
engine/guard/views.py

@dataclass(frozen=True)
class HitBuffers:                    # behaves as the (depth, tri) pair it replaces:
    depth: np.ndarray                #   iterable, indexable, len() == 2
    tri: np.ndarray                  # (H, W) int64, face id, -1 = miss
    direction: np.ndarray            # (3,) unit view direction, shared by every pixel
    right: np.ndarray                # (3,) unit image x axis
    up: np.ndarray                   # (3,) unit image y axis
    xs: np.ndarray                   # (W,) offset along `right` of each pixel column
    ys: np.ndarray                   # (H,) offset along `up` of each pixel row
    standoff: np.ndarray             # (3,) constant every ray origin is pushed back by
    origins -> np.ndarray            # PROPERTY, (H, W, 3): xs[j]*right + ys[i]*up + standoff

ortho_first_hit(positions_c, faces, face_ids, view, frame_points, size=(900, 600),
                caster_factory=EmbreeCaster) -> HitBuffers      # was -> (depth, tri)
```

```
engine/guard/compare.py

PX_OK=0, PX_HOLE=1, PX_MATERIAL_CHANGED=2, PX_MOVED_SAME_FLAT=3, PX_MOVED_OTHER=4,
PX_EDGE_FLICKER=5                                               # NEW

RenderedView = tuple[Sequence[float], HitBuffers]               # was (view, depth, tri)

face_planes(positions, faces) -> (F, 4) float64                 # NEW: [nx, ny, nz, d], unit n,
                                                                # all-zero row = no plane

classify_pixels(before_depth, before_tri, after_depth, after_tri,
                material_before, material_after, flat_materials, depth_tol,
                *, origins=None, direction=None,
                plane_before=None, plane_after=None) -> uint8 codes
    # moved = max(dist(P_before, plane_after), dist(P_after, plane_before)) > depth_tol,
    # P = origins + depth * direction; falls back to |t_before - t_after| where a plane is
    # undefined or no geometry was passed.

ViewVerdict(view, model_px, holes, moved_same_flat, moved_other, material_changed, edge_flicker)
GuardReport(views, passed, totals)
    # totals keys: model_px, holes, material_changed, moved_same_flat, moved_other, edge_flicker

compare_views(before, after, face_material_before, face_material_after, flat_materials, depth_tol,
              strict=False, plane_before=None, plane_after=None,
              edge_flicker_cap=0.0) -> GuardReport
    # before/after: sequences of (view, HitBuffers).
    # edge_flicker_cap is per view: flicker tolerated while edge_flicker <= cap * model_px.

guard_feedback(candidates, positions_c, faces, face_material, flat_materials, depth_tol, strict,
               views=VIEWS_26, size=(900, 600), caster_factory=EmbreeCaster,
               max_rounds=8) -> (surviving mask, history list[dict])
    # signature unchanged; builds face_planes itself and always uses edge_flicker_cap = 0.0.
```

```
engine/guard/render.py

save_triptych(path, before=(depth, tri), after=(depth, tri), verdict_mask) -> None
    # signature unchanged; a HitBuffers may be passed for before/after.
    # PX_EDGE_FLICKER now paints amber alongside PX_MOVED_SAME_FLAT.
```

```
engine/fixes/merge.py

MAX_ROUNDS: int = 10           # NEW: most times pass 2 reruns after a late skip feeds back

merge_regions(mesh, topo, flat_materials=frozenset(), grid_size=GRID_SIZE, snap_tol=SNAP_TOL,
              collinear_tol=COLLINEAR_TOL) -> MergeResult        # signature unchanged

report: {
  "regions_merged": int,
  "regions_skipped": dict[str, int],
  "tris_before": int,
  "tris_after": int,
  "vertices_dropped": int,
  "max_area_rel_error": float,
  "faces_copied": int,
  "merge_rounds": int,                 # NEW
  # "interior_vertices_pinned" REMOVED
}
```

## Fix round 2

Branch `phase2e-fix-pipeline`, five reviewed items, one commit each, test first. Baseline before
touching anything: **105 passed**, and the fix-round-1 file A numbers reproduced exactly
(2,656 -> 2,062 triangles, guard `holes 0 / moved_same_flat 0 / edge_flicker 1`, feedback
`1,853 / 34 / 1,819`).

| | commit |
|---|---|
| C1 keep-all fallback feeds its vertices back into the corner pass | `e694d82` |
| I3 merge reports whether the corner pass converged | `32cb5dd` |
| I1 edge flicker needs a sub-pixel coverage check | `c99dbb1` |
| I2 guard refuses renders from different camera frames | `b62f4fa` |
| F1 depth-along-ray fallback must be asked for explicitly | `98311f6` |

### C1 -- a `keep_all` success is a feedback event

Rule 6's fallback keeps EVERY ring vertex of its region and the region was then accepted in
silence. That is the same damage a late skip does, for the same reason: the neighbour on the other
side of a shared border has already dropped those vertices, so they now lie strictly inside the
neighbour's edge.

Measured before the fix, with the left region of `two_slabs_sharing_border()` forced onto the
fallback (`_polygon` returns `None` for that region whenever any ring vertex was dropped):

```
report: tris_after 30, merge_rounds 1
left faces: 28   right faces: 2
T-junctions (left vertices inside right edges): [16, 27, 38, 49, 60, 71, 82, 93, 104]
```

Nine. The left slab held all 30 of its ring vertices while the right slab merged to 2 triangles
whose shared edge ran straight past all nine of them.

The fix threads `keep_all` through the same fixed-point loop M2 built for late skips, on a separate
channel because the two feed back different vertex sets:

- a late skip is copied through whole, so ALL of its vertices (interior included) become `needed`;
- a `keep_all` success emits triangles over its RING only, so only its ring vertices need to be.

`_triangulate` now returns `(triangles, note)` -- `note` is `None` for a clean success,
`"keep_all"` for a fallback success, and the skip reason when `triangles is None`. Keeping the
arity at 2 is deliberate: `test_late_skipped_region_feeds_its_vertices_back_into_the_corner_pass`
monkeypatches `_triangulate` with a two-tuple stub and did not have to change. `_build_regions`
collects the `keep_all` region ids, `merge_regions` accumulates them in `kept_whole`, and
`_needed_vertices(..., kept_whole)` marks every ring vertex of those regions needed.

The loop still terminates: `fed_back` and `kept_whole` only ever grow, and a region whose whole
ring is `needed` triangulates the same polygon on the non-fallback branch next round, so it leaves
the `keep_all` set for good (either a clean success, or -- if that polygon is genuinely invalid --
a late skip, which the other channel then handles).

`report["keep_all_regions"]` is how many distinct regions took the fallback in ANY round, not just
the last: after convergence the last round shows none, because they have all been fed back.

RED:

```
$ .venv/Scripts/python.exe -m pytest engine/tests/test_merge.py -q -k keep_all
E       KeyError: 'keep_all_regions'
1 failed, 16 deselected in 0.30s
```

GREEN: `17 passed`, full suite `106 passed`. The new test asserts `keep_all_regions == 1`,
`merge_rounds == 2`, that the right slab keeps all 9 shared border vertices (11 triangles, not 2),
and -- by `vertices_inside_an_edge`, in both directions -- that neither slab puts a vertex strictly
inside an edge of the other.

### I3 -- `converged`

`merge_rounds == 10` was the only sign that the loop had been cut off by `MAX_ROUNDS` rather than
ending by agreement, and in that case the last round's feedback was never fed back, so a neighbour
may still be holding a T-junction open. `report["converged"]` is now True only when a round turned
up no late skip and no `keep_all` that earlier rounds had not already fed back.

RED: `KeyError: 'converged'` on both new assertions. GREEN: full suite `107 passed`. The test runs
the same two-round case at `MAX_ROUNDS = 1` (`merge_rounds 1`, `converged False`) and at
`MAX_ROUNDS = 10` (`merge_rounds 2`, `converged True`).

### I1 -- flicker needs sub-pixel coverage, not just a 3x3 neighbourhood

"This would-be hole has a miss in its 3x3 BEFORE neighbourhood" cannot tell the OUTER silhouette
from a gap INSIDE the model, so with a non-zero `edge_flicker_cap` a genuine hole beside a
pre-existing opening is tolerated. Measured on a 2-pixel-wide strip removed next to a 20 in gap:
72 pixels, every one classed `edge_flicker`, `holes == 0`, and the guard **passed**.

Both tests of the pair are now applied. A candidate is supersampled with a 5x5 lattice of rays
through its own pixel footprint, in BEFORE and in AFTER, from the SAME camera frame, and stays
flicker only while `abs(coverage_after - coverage_before) <= 2/25`.

**Smallest signature change, and why that one.** The check needs both geometries inside the
classification, for a few dozen pixels per view. Rather than hand `classify_pixels` two meshes (it
is a pure per-pixel function and should stay one), it takes a `coverage` callable: the boolean mask
of candidates in, two coverage fractions out, ordered like `np.nonzero(mask)`. `compare_views`
builds one per view from two new `(positions, faces)` arguments -- `geometry_before` /
`geometry_after` -- plus a `caster_factory`, so the casters are built once for all 26 views and
only candidate pixels are ever cast. `HitBuffers.subpixel_origins(rows, cols, grid)` supplies the
sub-ray origins from the camera frame the render already carries, which keeps the camera math in
`views.py` and means the probe cannot drift out of step with the render. Nothing imports `trimesh`:
the probe calls `caster.any_hit`, through the `RayCaster` interface.

Why 5x5 and 2/25: the lattice is deterministic (sub-cell centres, no sampling noise) and its centre
ray is the pixel's own ray, so a pixel that flips at all changes coverage by at least 1/25. A
boundary moving a thousandth of an inch can carry one sub-ray, occasionally two; a removed face
carries all 25.

`guard_feedback` is deliberately NOT given the probe: it runs at `edge_flicker_cap = 0.0`, where
`_fail_mask` already counts a flicker pixel exactly like a hole, so the extra rays would change no
decision. Documented at the `coverage` argument.

RED:

```
$ .venv/Scripts/python.exe -m pytest engine/tests/test_guard.py -q -k "thousandth or pre_existing"
E           TypeError: compare_views() got an unexpected keyword argument 'geometry_before'
2 failed, 20 deselected in 0.67s
```

-- and in that same run the `blind` assertions of the second test passed, which is the defect
itself on record: 72 tolerated pixels, `holes == 0`, `passed is True`.

GREEN: full suite `109 passed`. Two tests:

1. `test_a_thousandth_of_an_inch_of_boundary_shift_is_edge_flicker` -- a plate whose right
   boundary is tilted off the pixel lattice (slope 0.037, so it crosses one sub-ray rather than a
   whole sub-column) and passes exactly through one pixel centre, shifted by 0.001 in between the
   two renders. The test first asserts that exactly ONE pixel flips hit->miss, then that it comes
   back `edge_flicker` with `holes == 0` -- and still fails at the default cap of 0.0.
2. `test_a_removed_face_beside_a_pre_existing_gap_is_a_hole_at_any_cap` -- the strip-beside-a-gap
   scene above, asserted both ways in one test: without the geometry the 72 pixels are flicker and
   the guard passes at `cap=1.0`; with it they are `holes`, `edge_flicker == 0`, and the guard
   fails at caps 0.0, 1e-4 AND 1.0.

### I2 -- the whole camera frame, not just the direction

`_displacement` takes the ray origins of BOTH hit points from the BEFORE buffer. A caller who
framed AFTER on a different bounding box was not comparing the same pixels at all, and every
displacement was measured from the wrong point -- silently, because only `direction` was checked.

`_frame_mismatch(b, a)` now compares image size, `direction`, `right`, `up`, `xs`, `ys` and
`standoff`, and returns the name of the first field that differs. Those six fields ARE the origins
grid (`origins[i, j] == xs[j] * right + ys[i] * up + standoff`), so the check compares the grid
without materialising 13 MB of it per view. `ValueError` names the view and the field.

RED: `Failed: DID NOT RAISE ValueError`. GREEN: full suite `110 passed`. The test renders AFTER on
a doubled bounding box and at a different image size, expects both to raise with "camera frame" and
the view's own coordinates in the message, and asserts a correctly framed pair still compares.

### F1 -- the depth fallback is now asked for by name

`classify_pixels` fell back to `|t_before - t_after|` for the WHOLE image whenever a caller passed
no geometry -- the metric that produced 676 false `moved` pixels on file A, handed out for
forgetting an argument. It now raises unless `allow_depth_fallback=True`, and `compare_views`
forwards the same flag. Partial geometry does not count: planes without origins cannot place a hit
point, so all four of `origins`, `direction`, `plane_before`, `plane_after` are required.

The PER-PIXEL fallback for a zero-area face with no plane is untouched and still silent -- that is
the geometry's doing, not a caller mistake, and
`test_undefined_plane_falls_back_to_depth_along_the_ray` still pins it.

RED: `Failed: DID NOT RAISE ValueError`, then, once implemented, exactly the seven geometry-free
tests failing with the new message. Each was given `allow_depth_fallback=True`; **not one
assertion changed**. GREEN: full suite `112 passed`.

### Real data after fix round 2

`data/snapshots/ce26e0392ab0/CHTM_SIDE_WALK_2nd_floor.obj`, same pipeline and same script shape as
fix round 1 (`read_obj` -> `analyse_topology(mesh, {0})` -> recentre -> `compute_exposure` ->
`guard_feedback(strict=True, depth_tol=0.15)` -> `remove_faces` -> `analyse_topology` ->
`merge_regions`), plus the guard of MERGED vs ORIGINAL. Script:
`C:\Users\Future26\AppData\Local\Temp\claude\D--PROJECTS-UC-MODEL-FIXER\5472478e-978d-426b-bab2-e7cf21699a70\scratchpad\realrun_round2.py`.
Nothing was tuned to reach a number; the run was repeated and printed the same numbers twice.

#### Hidden-face feedback

| | fix round 1 | fix round 2 |
|---|---|---|
| candidates (exposure 0, non-degenerate) | 1,853 | **1,853** |
| restored | 34 | **34** |
| removable | 1,819 | **1,819** |
| round 0 failing pixels / round 1 | 223 / 0 | **223 / 0** |

Unchanged, as expected: `guard_feedback` always ran at cap 0.0 and is not given the coverage probe,
and nothing in C1/I3/F1 touches it.

#### Merge

| | fix round 1 | fix round 2 |
|---|---|---|
| faces in | 2,656 | 2,656 |
| **triangles after merge** | 2,062 | **2,062** |
| regions merged | 273 | **273** |
| regions skipped | overlap 8, new_vertex 1, invalid_polygon 2 | **overlap 8, new_vertex 1, invalid_polygon 2** |
| faces copied through | 536 | **536** |
| vertices dropped | 301 | **301** |
| `merge_rounds` | 2 | **2** |
| `converged` | n/a | **True** |
| `keep_all_regions` | n/a | **0** |
| `max_area_rel_error` | 1.98e-09 | **1.98e-09** |
| runtime, `merge_regions` | 0.49 s | 0.62 s |
| deterministic across two runs | yes | **yes** |

**`keep_all_regions` is 0 on file A**: not one of its 273 merged regions needed rule 6's fallback,
so C1 changes nothing here and the triangle count is identical. C1 is a correctness fix for a path
this file does not take -- the fixture test is the evidence that it works, not this run. The 3
regions that DO feed back are late skips, which M2 already handled, and they are why
`merge_rounds` is 2 and `converged` True.

Total 3D area: original 1,393,867.737 in2; after removal 1,202,195.820 in2; after merge
1,202,195.78 in2 (relative change 3.5e-8, per-region `max_area_rel_error` 2e-9).

#### Guard: MERGED vs ORIGINAL, `compare_views` over `VIEWS_26`, `strict=True`

Same `frame_points` (the recentred welded positions) for both renders, `depth_tol = 0.15`,
`flat_materials = {0}`, planes from `face_planes` of both geometries, and now
`geometry_before` / `geometry_after` so the coverage check runs.

| total | `edge_flicker_cap=0.0` | `edge_flicker_cap=1e-4` |
|---|---|---|
| model_px | **2,059,414** | **2,059,414** |
| holes | **0** | **0** |
| material_changed | **0** | **0** |
| moved_same_flat | **0** | **0** |
| moved_other | **0** | **0** |
| edge_flicker | **1** | **1** |
| `passed` | **False** | **True** |

The same single pixel as fix round 1 (view `(0.013, -0.993, -0.989)`, 106,091 model pixels in that
view), and the coverage check now says WHY it is flicker rather than assuming it:

```
would-be holes in this view: 1 of which on the 3x3 silhouette: 1
  pixel (row 281, col 430): coverage before 13/25, after 12/25, |delta| = 1/25 (tolerance 2/25)
```

A pixel that was half covered before and is half covered after, one sub-ray different: a real
silhouette, not a hole. It still fails at the default cap of 0.0, which is the intended
zero-tolerance behaviour, and passes at 1e-4.

Cost of the coverage check on this file: `compare_views` took **1.31 s** both with and without it
(1 candidate pixel across all 26 views, plus two casters). Whole run 30.1 s.

### Files changed in fix round 2

- `engine/fixes/merge.py` -- `_triangulate` returns a note, `_build_regions` reports `keep_all`,
  `_needed_vertices` takes `kept_whole`, `merge_regions` loop + `keep_all_regions` / `converged`
- `engine/guard/views.py` -- `_pitch`, `HitBuffers.subpixel_origins`
- `engine/guard/compare.py` -- `_FLICKER_GRID` / `_FLICKER_COVERAGE_TOL`, `_coverage_probe`,
  `_frame_mismatch`, `classify_pixels` (`coverage`, `allow_depth_fallback`), `compare_views`
  (`geometry_before` / `geometry_after` / `caster_factory` / `allow_depth_fallback`, frame check)
- `engine/tests/test_merge.py` -- 2 tests added, 1 grown, 1 helper extracted
- `engine/tests/test_guard.py` -- 5 tests added, 7 call sites given `allow_depth_fallback=True`

Nothing outside `engine/` was edited. Nothing in `engine/` imports `api`, `spike`, `fastapi`,
`sqlalchemy` or `random` (checked by grep after the last commit); `trimesh`/`embreex` appear only
in `engine/rays/caster.py` -- the one hit in `engine/guard/views.py` is a docstring sentence saying
they are never imported there. No vertex is moved or invented. The 5x5 lattice is fixed sub-cell
centres, so two runs give identical output, verified on file A.

### Concerns

1. **The 3x3-only path is still reachable and still silent.** `compare_views` without
   `geometry_before` / `geometry_after` decides flicker on the neighbourhood test alone, which is
   exactly the defect I1 names -- it is safe only at `edge_flicker_cap = 0.0`. I did not make it an
   error the way F1 makes the depth fallback one: the brief asked for the second condition, not for
   a second flag, and the synthetic-buffer flicker tests have no geometry to give. If the next
   round wants it, the shape is the same as `allow_depth_fallback`.
2. **`keep_all_regions == 0` on file A**, so C1 is unexercised by the real model. The fixture test
   drives the path by monkeypatching `_polygon`, which means the trigger is simulated even though
   the feedback machinery under test is real.
3. **2/25 is a threshold, and a boundary CAN cross a whole sub-column.** If a straight boundary
   happens to land exactly between two sub-sample columns, a thousandth of an inch flips 5 sub-rays
   at once (5/25) and the pixel is called a hole. I hit that while writing test 1 and tilted the
   test boundary off the lattice rather than widen the tolerance. On real data the `VIEWS_26`
   nudges make the coincidence vanishingly unlikely, and erring toward "hole" is the safe
   direction, but it is a real knife-edge in the rule as specified.
4. **`converged` is reported, not acted on.** `merge_regions` still returns its mesh when the loop
   was cut off; the caller has to look. Nothing in the pipeline looks yet.
5. **C1 can only cost triangles**, like M2: a region that fed back keeps its whole ring needed even
   if a later round would have simplified it. Zero cost on file A, but that is because the path is
   never taken here.

## Public signatures

(fix round 2 -- everything whose signature or report changed; the round-0 and round-1 signatures
above still hold where they are not restated here)

```
engine/guard/views.py

HitBuffers.subpixel_origins(rows, cols, grid=5) -> (len(rows) * grid * grid, 3) float64   # NEW
    # Sub-cell-centre ray origins inside each named pixel's own footprint, row-major per pixel,
    # in the order rows/cols are given (np.nonzero order when they come from a mask).
    # The centre sub-ray is the pixel's own ray. A 1-pixel axis contributes no offsets.
```

```
engine/guard/compare.py

classify_pixels(before_depth, before_tri, after_depth, after_tri,
                material_before, material_after, flat_materials, depth_tol,
                *, origins=None, direction=None, plane_before=None, plane_after=None,
                coverage=None,                      # NEW
                allow_depth_fallback=False) -> uint8 codes    # NEW
    # coverage: callable(mask: bool ndarray) -> (before_fraction, after_fraction), each (N,) float
    #   ordered like np.nonzero(mask); a would-be hole on the 3x3 silhouette stays PX_EDGE_FLICKER
    #   only while abs(after - before) <= 2/25, else PX_HOLE. None = 3x3 test alone (safe only at
    #   edge_flicker_cap 0.0).
    # allow_depth_fallback: without all four of origins/direction/plane_before/plane_after, this
    #   now RAISES ValueError unless True. The per-pixel fallback for a zero-area face's undefined
    #   plane is unchanged and needs no flag.

compare_views(before, after, face_material_before, face_material_after, flat_materials, depth_tol,
              strict=False, plane_before=None, plane_after=None, edge_flicker_cap=0.0,
              geometry_before=None,               # NEW: (positions, faces) of the BEFORE render
              geometry_after=None,                # NEW: (positions, faces) of the AFTER render
              caster_factory=EmbreeCaster,        # NEW
              allow_depth_fallback=False) -> GuardReport      # NEW, forwarded
    # Raises ValueError naming the view when a before/after pair disagrees on ANY of image size,
    # direction, right, up, xs, ys, standoff (was: direction only).
    # Given both geometries, builds one caster per side and supersamples each flicker candidate
    # with 25 rays; omitted, the 3x3 neighbourhood test decides alone.

guard_feedback(...)   # signature unchanged; still no coverage probe -- it runs at cap 0.0, where
                      # PX_EDGE_FLICKER already fails exactly like PX_HOLE.
```

```
engine/fixes/merge.py

merge_regions(mesh, topo, flat_materials=frozenset(), grid_size=GRID_SIZE, snap_tol=SNAP_TOL,
              collinear_tol=COLLINEAR_TOL) -> MergeResult      # signature unchanged

report: {
  "regions_merged": int,
  "regions_skipped": dict[str, int],
  "tris_before": int,
  "tris_after": int,
  "vertices_dropped": int,
  "max_area_rel_error": float,
  "faces_copied": int,
  "merge_rounds": int,
  "keep_all_regions": int,             # NEW: regions that took rule 6's full-ring fallback in ANY
                                       # round; their ring vertices were fed back into the corner pass
  "converged": bool,                   # NEW: True only when a round added nothing new. False means
                                       # MAX_ROUNDS cut the loop off and the last round's feedback
                                       # was never fed back.
}

# internal, but load-bearing for anyone monkeypatching them:
_triangulate(plan, needed, collinear_tol) -> (triangles, note)
    # note: None = clean success, "keep_all" = full-ring fallback success (a feedback event),
    # or the skip reason when triangles is None. Arity unchanged.
_build_regions(plans, needed, collinear_tol) -> (builds, late, keep_all, max_area_rel_error)
_needed_vertices(topo, copied, plans, collinear_tol, kept_whole=()) -> bool ndarray
```
