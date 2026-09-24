# Merge quality — report (task M: one slab = one face)

Repo `D:\PROJECTS\UC MODEL FIXER`, branch `feat-dashboard`. Every number below was produced by a
command run in this round; nothing is carried over from an earlier report.

Baseline before any change: `.venv/Scripts/python.exe -m pytest engine/tests -q` → **190 passed**,
`git status` showing only the untracked files listed in the brief (none touched).

Measured quanta on both real files: `[0.01, 0.1, 0.01]` — Y really is printed to one tenth of an
inch, X/Z to one hundredth, which is the rounding the M1 fixture reproduces.

---

## M1 `fix(engine): plane regions grow with an iterative least-squares refit`

### What changed

`engine/topo/planes.py`

- New `fit_plane(points, orient_like) -> (normal, centroid)`: total-least-squares plane through
  the centred points (SVD, smallest singular vector), sign-fixed against `orient_like` so the
  result does not depend on LAPACK's arbitrary sign convention.
- `cluster_planes` grows each region iteratively instead of accepting one seed-plane pass:
  accept every unassigned same-material candidate with `n . n_region > facing_dot` whose three
  vertices are all within `tol` of the CURRENT region plane, refit the plane over the accepted
  vertices, re-test ALL unassigned candidates against the refit plane, repeat until the member
  set stops changing (`max_refit=8` rounds, a backstop rather than the mechanism). A face
  rejected by an earlier, worse plane can join later; one accepted by it can leave.
- `tol = tol_quanta * sum(|n_i| * q_i)` is unchanged in form but is evaluated with the CURRENT
  normal, so it tracks the plane as it turns.
- The seed is pinned into its own region every round (`cand[s] = True`), so a region can never
  empty itself out.
- Seeds are taken with a STABLE descending-area sort, so equal areas seed in ascending face id.
- `planes[i]` stays the `(n, p0, tol)` triple, now holding the FINAL fit; `build_regions`,
  `plane_basis`, the UV projection and `merge_regions` all consume that plane unchanged.
- `build_regions`, `merge_regions`, `classify_edges` and the edge classes keep their API.

### Tests (written first, watched fail)

`engine/tests/fixtures/build.py` gained two fixtures:

- `rounded_long_slab()` — a 60-vertex / 58-triangle strip at y ≈ 24,000 in (so `axis_quanta`
  gives Y the real file's 0.1 in quantum) whose two `x = 0` vertices are printed exactly one
  quantum high. Its largest triangle sits in the wide first cell at that end, so the seed plane
  is tilted by `0.1 / 300`; 1,700 in away that is 0.47 in against a 0.15 in tolerance.
- `creased_pair(angle_deg=3.0)` — two same-material quads hinged along `x = 0`, the second
  tilted 3°. `cos 3° = 0.9986 > facing_dot`, so only the plane-distance test separates them.

`engine/tests/test_regions.py` gained three tests:

- `test_rounded_long_slab_is_one_region_despite_seed_plane_rounding_noise` — **RED before the
  change: `assert 2 == 1`** (the strip split into two regions, exactly as predicted: the far end
  sits 0.47 in off the seed plane). Green after: one region holding all 58 faces.
- `test_three_degree_crease_stays_two_regions` — guards the other direction: refitting must not
  swallow a genuinely different plane. Green before and after (it is a no-regression guard).
- `test_region_growing_is_deterministic` — two independently built copies of each fixture give
  identical `face_region`.

### Result

`.venv/Scripts/python.exe -m pytest engine/tests -q` → **193 passed** (190 + 3), no existing test
modified.

Real-data effect, measured on the RAW snapshot meshes (`analyse_topology` only, before any
removal), old behaviour reproduced by pinning `max_refit=1`:

| file | regions, seed-only (old) | regions, refit (new) |
|---|---|---|
| A `ce26e0392ab0` | 888 | **865** |
| B `0b290ec0bcb4` | 874 | **866** |

Also measured on the raw meshes for context (the full post-removal numbers are in the Finish
section): file A 1,086 `EDGE_REAL` edges of which 108 are within 1° of coplanar; file B 1,470 of
which 211.

---

## M3 `fix(engine): ring simplification with a global deviation bound`

### What changed

`engine/fixes/merge.py`

- `COLLINEAR_TOL = 1e-3` is gone, replaced by `RING_TOL_QUANTA = 1.5`. `merge_regions`'
  `collinear_tol` now defaults to `None`, meaning "derive from the mesh's own print precision",
  `RING_TOL_QUANTA * max(topo.quanta)` — 0.15 in on both real files. An explicit value still
  wins, which is how the new test pins the bound.
- `_corner_mask` (the per-vertex collinearity test) is **removed**. In its place:
  - `_ring_keep(xy, ids, forced, tol)` — Ramer-Douglas-Peucker over one closed ring. `forced`
    vertices always survive and cut the ring into independently simplified runs; with fewer than
    two of them the ring anchors on its own lowest vertex id and the vertex farthest from it.
  - `_rdp` — iterative (no recursion limit), splitting at the farthest point while it is outside
    `tol`, ties broken on the lowest vertex id.
  - `_segment_distance` — distance to the SEGMENT, not its infinite line, so a boundary that
    doubles back is still "far", exactly as the old test's `along < 0 or > 1` check treated it.
  - `_divergent_vertices(rings)` — see below.
- `_needed_vertices` freezes the `forced` set BEFORE simplifying any ring, so no ring's result
  can move another ring's anchors: the decision stays global and independent of plan order.

### The one thing the brief did not mention, and why it is here

The old per-vertex test was **symmetric by accident**: a vertex's verdict depended only on itself
and its two ring neighbours, which are the same pair (reversed) in both rings sharing a border,
so both sides of a shared border always agreed and no T-junction could open. RDP is *not* local —
what it keeps along a stretch depends on that stretch's endpoints — so two regions only stay in
step if they simplify a shared stretch between the SAME endpoints. `_divergent_vertices` restores
the guarantee by forcing every vertex whose two ring neighbours are not identical in every ring
containing it (plus any vertex one ring visits twice). Without it, `two_slabs_sharing_border`
could have simplified its shared border differently from each side. Ties inside `_rdp` break on
the lowest vertex id, which is direction-independent, so a shared run simplifies identically
whichever way it is traversed.

### Tests (written first)

`engine/tests/fixtures/build.py` gained `arc_topped_strip()`: 12 quads between a straight bottom
edge and a 12-vertex parabolic arc, at y ≈ 24,000 in so `1.5 * max(q)` is the real 0.15 in bound.
The arc is scaled so the farthest top vertex is exactly **0.8 in** off the chord between the two
end vertices while each top vertex is only **0.0267 in** off the chord of its own two neighbours.

- `test_arc_ring_stays_within_the_bound_instead_of_drifting_off_it` — **RED before the change**.
  The first version of this test used the default tolerance and passed against the old code,
  because the old default (1e-3) is far tighter than the bound the rule is supposed to enforce
  and masked the defect; the test now names the bound it tests (`collinear_tol=1.5 * max(q)`).
  The actual red was `assert 24 < 24`, and the reason is worth recording: at a realistic bound
  the per-vertex rule proposes the four sharp corners, which loses 118 sq in of area — more than
  `_triangulate` allows — so the region takes the `keep_all` fallback and simplifies **nothing**.
  The per-vertex rule at this bound is not merely inaccurate, it is inert.
  Green after: the ring keeps between 5 and 23 vertices and no original ring vertex is farther
  than 0.15 in from the simplified ring.
- `test_ring_bound_defaults_to_one_and_a_half_axis_quanta` — **RED before** (the default gave a
  14-vertex ring, the explicit bound a 24-vertex one). Green after.

### Result

`.venv/Scripts/python.exe -m pytest engine/tests -q` → **195 passed** (193 + 2). Every pre-existing
merge, region, writer and pipeline test still passes unmodified at the looser default bound.

Real data after M1 + M3 (`fix_object`, default profile), against the state this round started from:

| | file A `ce26e0392ab0` | file B `0b290ec0bcb4` |
|---|---|---|
| triangles, round start → now | 1,891 → **1,674** | 1,278 → **1,173** |
| regions merged, round start → now | 176 → **169** | 95 → **91** |
| rolled back | no | no |
| guard passed | yes | yes |
| `keep_all` regions | 0 | 0 |

---

## M2 `feat(engine): EDGE_SOFT class and rings with inner loops`

### What changed

`engine/topo/edges.py`

- `EDGE_SOFT = 5`, plus module defaults `COPLANAR_ANGLE = 1.0` and `SOFT_ANGLE = 5.0` (degrees).
- `dihedral_degrees(n0, n1)` and `region_border_angles(table, face_region, normals)` — the
  latter gives `{edge: angle}` for every edge with exactly two faces in two DIFFERENT real
  regions (both `>= 0`; an edge touching a face in no region is not a border *between* regions).
- `classify_edges(table, face_region, t_vertices, normals=None, material=None, *,
  coplanar_angle=..., soft_angle=...)`. An edge is EDGE_SOFT when it has exactly two faces, of
  the same material, in different regions, with `coplanar_angle < dihedral <= soft_angle`. With
  `normals` or `material` omitted no edge is ever soft and the result is byte-for-byte what it
  always was. The later T-junction pass cannot overwrite a soft verdict: its `whole` branch
  requires every face in ONE region, which a soft edge never is.

`engine/topo/planes.py` — `face_normals(positions_w, face_w, ok)` extracted (it was inline in
`build_regions`, which now calls it) so `analyse_topology` can hand the same normals to
`classify_edges`.

`engine/pipeline.py`

- `Topology` gains `coplanar_angle` / `soft_angle` (the thresholds its `edge_class` was decided
  with), so `topology_stats` reports against the same threshold rather than the module default.
- `analyse_topology(mesh, flat_materials, *, coplanar_angle=..., soft_angle=...)`.
- New `coplanar_region_borders(t) -> int` and two new `topology_stats` keys, `soft_edges` and
  `coplanar_region_borders`.

`engine/fixes/pipeline.py` — `FixProfile.coplanar_angle` / `.soft_angle`, forwarded to both
`analyse_topology` calls inside `fix_object`.

`engine/fixes/merge.py` — `_region_ring` becomes `_region_loops`, returning
`{"outer": ids, "inners": [ids, ...]}` for EVERY single-piece merged region, holed ones
included. Outer CCW as seen from the region's outward side, inners CW. `MergeResult.rings` is now
`dict[int, dict]`.

`engine/io/obj_writer.py` — `write_obj_polygons` collapses a region into one `f` line only when
its entry is hole-free; a holed region keeps its triangles, because an OBJ `f` line is a single
loop. The identity (`id()`) dedup contract is unchanged, now on the dict.

`engine/cli.py` — `_soft_edges(topo, positions_c)`; `preview-data` analyses the SHIPPED mesh's
own topology and writes `edges.soft_after`, plus `stats.soft_edges` and
`stats.coplanar_region_borders`. `_profile_dict` reports both angles into `report.json`.

### Interpretation recorded

The brief writes `rings[region] = {...}`. The key is left as the OUTPUT FACE ROW INDEX, which is
what it already was ("Keyed by OUTPUT face row index" in the existing tests) and what
`write_obj_polygons(mesh, rings, path)` needs — it iterates output faces and has no face→region
map, and its `id()` dedup exists precisely because several rows share one entry. Only the VALUE
shape changed.

`coplanar_region_borders` deliberately does not test material, exactly as the brief words it. A
coplanar border between two MATERIALS is a real edge that must stay and is counted here too, so a
non-zero reading is a prompt to look rather than proof of a defect. This is called out because it
affects how the Finish numbers should be read.

### Tests (written first, watched fail)

`engine/tests/test_regions.py` (+5): `test_three_degree_crease_edge_is_soft` (hinge of
`creased_pair(3.0)` is EDGE_SOFT, `soft_edges == 1`, `coplanar_region_borders == 0`);
`..._half_degree_crease_is_a_coplanar_region_border_not_a_soft_edge` (0 / 1);
`..._ten_degree_crease_stays_a_real_edge`; `test_soft_and_coplanar_thresholds_are_settable`
(both travel from the keyword down to the stat); `test_a_cube_has_no_soft_edges_...`.
First red was the `EDGE_SOFT` ImportError, then the stat keys.

`engine/tests/test_merge.py`: `test_slab_with_hole_rings_has_an_outer_loop_and_one_inner_loop_of_four`
(one region, outer of 4, one inner of 4, disjoint vertex sets) and
`test_inner_loops_are_wound_opposite_to_the_outer_loop` (signed area > 0 outer, < 0 inner).
`grid_slab` keeps its shared-object assertion and now asserts `outer` of 4 with `inners == []`.

`engine/tests/test_cli.py`: `test_cmd_preview_data_writes_soft_creases_of_the_shipped_mesh`
(`len(edges.soft_after) == stats.soft_edges * 6`), plus the two new stat keys and `soft_after`
added to the shape test's key lists.

### Existing tests updated to the new contract (not weakened)

`MergeResult.rings` is a documented public shape, so the four tests that asserted the old one had
to move with it: `test_grid_slab_rings_...`, `test_two_slabs_sharing_border_rings_...`,
`test_ring_vertex_ids_index_into_mesh_positions_like_face_v_does` (test_merge.py),
`test_box_with_partition_removes_only_the_sealed_partition` (test_pipeline.py), and two in
test_obj_writer.py. Each kept every assertion it had and gained the `["outer"]` / `["inners"]`
indirection; `test_slab_with_hole_rings_is_empty` became
`..._has_an_outer_loop_and_one_inner_loop_of_four`, which asserts strictly more.

### Result

`.venv/Scripts/python.exe -m pytest engine/tests -q` → **202 passed** (195 + 7).

---

## R1b `fix(engine): unavoidable diagonals are classified by region id, not array identity`

### What changed

- `engine/fixes/merge.py` — `MergeResult.face_region`: int64 over OUTPUT faces, -1 for rows
  copied through unmerged. `_assemble` already carried the region on every emitted row; it is
  now returned instead of discarded.
- `engine/fixes/pipeline.py` — `FixResult.face_region_final`, the merge's `face_region` when the
  merge shipped and all -1 when it was rolled back (nothing merged, so no diagonals).
- `engine/cli.py` — `_after_edges` classifies an edge as a diagonal when both its faces carry
  the SAME region id `>= 0`.

### Why the old test could never fire

`_after_edges` tested `source_faces[a] is source_faces[b]` — the array identity
`engine.fixes.merge` sets up so every triangle of one region shares one object. But `fix_object`
rebuilds the list as `[source_from_removal[s].astype(np.int64) for s in merge_result.source_faces]`,
and `.astype` **copies**, so by the time a `FixResult` reaches the CLI no two rows share an
object. `tri_after` was always empty and every triangulation diagonal was drawn as a real shape
edge. A region id is data rather than an object address, so it survives being rebuilt.

### Test (written first)

`engine/tests/test_cli.py::test_cmd_preview_data_classifies_triangulation_diagonals_by_region` —
**RED before**: `edges.tri_after` empty, `unavoidable_diagonals_after` 0, `outline_edges_after`
18 (all 12 cube edges *and* all 6 quad diagonals). Green after: `tri_after` non-empty,
`unavoidable_diagonals_after` > 0, and `outline_edges_after` equals the number of distinct
undirected edges in the merged regions' outer rings (12 for the cube), computed in the test from
`result.rings` rather than hard-coded.

### Result

`.venv/Scripts/python.exe -m pytest engine/tests -q` → **203 passed** (202 + 1).

---

## M4b `fix(engine): tie sets are found by geometry, not vertex sharing`

### What changed

`engine/rays/caster.py` — `EmbreeCaster`'s coincident-hit recovery no longer looks only at the
triangles that SHARE A VERTEX with the one embree returned. `_vertex_face_table` /
`_vertex_faces` are gone; in their place `_face_bounds()` (a lazily built per-face bounding box,
still never paid for by a plain render) and a `_coincident_with(itri, points, tol)` that tests
each hit point against EVERY face of the mesh behind an axis-aligned bounding-box prefilter,
blocked at `_SEARCH_BLOCK` hit×face pairs so the numpy mask stays bounded. `_contains` takes its
tolerance as an argument instead of reading the instance attribute.

The documented LIMIT — "a coincident triangle sharing NO vertex is still missed" — is gone with
it. `BruteCaster` is unchanged: its analytic test never needed a recovery.

### Deviation from the brief, with the measurement behind it

The brief asks for the recovery tolerance to be the guard's `depth_tol`. **Measured, and not
done.** The recovery's whole job is the band embree's multi-hit walk *steps over*, which is
`max(1e-8, mesh.scale * 1e-6)` — 4e-5 in on this fixture. Casting the real file-B z-fight pair
at separations of 0, 0.001, 0.01, 0.05 and 0.2 in:

| separation | raw embree walk | after recovery |
|---|---|---|
| 0.0 (exactly coincident) | face 0 only | faces 0 and 1, Δt = 0 |
| 0.001 | faces 0 and 1 | faces 0 and 1, Δt = 0.0015 |
| 0.01 / 0.05 / 0.2 | faces 0 and 1 | unchanged |

Everything looser than an exact coincidence is already reported by embree itself, at its own
true depth. A `depth_tol`-wide (0.15 in) recovery would therefore find nothing new — it would
re-report a face embree had already returned, at the HIT face's depth rather than its own, i.e.
at a depth that face does not have, and feed that fabricated depth to `_matches_tie_set`'s
`|t - t_first| <= depth_tol` test. `_coincident_tol` (the width of the skipped band) is kept,
and the `coincident_tol` keyword I had first added to `all_hits` was removed rather than left as
a parameter nothing in production sets. `RayCaster.all_hits(origins, directions)` is therefore
unchanged from the last `## Public signatures`.

The in-plane containment margin is the same tolerance, so a hit landing exactly on a shared edge
is still attributed to both faces.

### Tests (written first, watched fail)

- `test_caster.py::test_all_hits_reports_a_coincident_face_that_shares_no_vertex` — the real
  file-B pair rebuilt on DISJOINT vertex ids (each triangle on its own copies of the positions,
  which is what two separately drawn SketchUp loops give). **RED before**: "EmbreeCaster reported
  1 hit(s), not 2". Green after, and `BruteCaster` agrees.
- `test_caster.py::test_all_hits_leaves_a_separated_face_to_embrees_own_walk` — pins the
  measurement above, so the tolerance choice cannot be quietly widened later.
- `test_guard.py::test_a_zfight_tie_is_found_between_faces_that_share_no_vertex` — the `_TWIN`
  z-fight scenario on disjoint vertex ids (`_SPLIT_FRAME` / `_SPLIT_TWIN`). **RED before**:
  `zfight_tie == 0` where 1,296 model pixels changed material. Green after: all 1,296 are ties,
  `material_changed == 0`, report passes.

### Result

`.venv/Scripts/python.exe -m pytest engine/tests -q` → **206 passed** (203 + 3).

---

## M0b `fix(engine): failing-view images only for real failures`

### What changed

- `engine/fixes/pipeline.py` — `FixResult.strict_final`: the strictness all three of the run's
  guards were run at (False when a person opted into a colour-tolerant slit removal AND slit
  faces were actually removed, so `moved_same_flat` is tolerated by construction).
- `engine/cli.py` — `_failing_view_indices(result, profile)` now reproduces
  `compare_views`' own per-view arithmetic instead of listing any view with any reportable
  pixel: `holes + material_changed + moved_other`, plus `moved_same_flat` only when
  `strict_final`, plus `edge_flicker` only when it exceeds that guard's own
  `edge_flicker_cap * model_px` — 0.0 for the post-removal guard, `edge_flicker_cap_final` for
  the merge attempt and the final guard. `report.json` gains `strict_final`, without which its
  own per-view counts cannot be read.
- `engine/guard/render.py` — `PX_ZFIGHT_TIE` gets violet `_TIE` and `PX_CRACK_CLOSED` green
  `_CRACK`, distinct from amber and red, with the full four-colour legend as a table in
  `save_triptych`'s docstring. Red is painted last so it always wins.

### Tests (written first, watched fail)

- `test_cli.py::test_tolerated_moved_same_flat_pixels_write_no_failing_view_image` — a
  non-strict run whose guards report 7 `moved_same_flat` pixels per view and nothing else:
  **RED before** (26 images), green after (0 images, and the 6 axis triptychs still written).
- `test_cli.py::test_the_same_pixels_do_write_failing_view_images_when_the_run_is_strict` — the
  counterpart, differing only in `strict_final`: 26 images.
- `test_cli.py::test_flicker_under_the_final_cap_writes_no_failing_view_image` and
  `..._over_the_final_cap_does_write_failing_view_images` — 1 vs 500 flicker pixels in a 10,000
  px view at a 1e-2 cap, with the post-removal guard clean so only the final cap decides.
  (My first attempt at this pair asserted 26 images under a name promising none, because the
  post-removal guard's 0.0 cap was also firing; the fixture now isolates the final cap, so the
  name and the assertion agree.)
- `test_guard.py::test_save_triptych_gives_ties_and_closed_cracks_their_own_diff_colours` — a
  six-pixel legend row, one per class, asserting five distinct colours. **RED before**:
  `module 'engine.guard.render' has no attribute '_TIE'`.

### Result

`.venv/Scripts/python.exe -m pytest engine/tests -q` → **211 passed** (206 + 5, since two of the
originally planned tests became pairs).
