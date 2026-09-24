# Solidify — brief (task S: close each slab so every interior face becomes hidden)

Repo `D:\PROJECTS\UC MODEL FIXER`, branch `feat-dashboard`. Bash, POSIX syntax, repo path
`/d/PROJECTS/UC MODEL FIXER`. Python ALWAYS `.venv/Scripts/python.exe`. Do not touch the running servers.
Leave untracked files alone. Prerequisite: the merge-quality task (`merge-quality-brief.md`) has landed
(`MergeResult.rings` with `outer` / `inners`, least-squares plane regions).

## Why (measured, spikes 14-16 in `spike/`)
The sidewalk is mostly a top sheet with partial skirts and almost no bottom: file A has 657 open edges
(2,113 ft); only 21 of its 182 open top edges have a bottom outline below. Interior rib walls are therefore
visible through side holes and from underneath, so the strict hidden-face removal keeps them. Closing the sides
alone hides 105 more faces; sides plus bottom hide 182, and a bottom at one uniform thickness leaks (a real
skirt varies 1.3-49 in). The user's target is a closed solid slab whose only edges are its real outline.
This step is the ONLY place in the engine allowed to invent vertices, and every new face is guarded.

## S1 `feat(engine): solidify slab regions with skirts and bottoms under a cap guard`
Create `engine/fixes/solidify.py` with `solidify(mesh, topo, profile) -> SolidifyResult(mesh, new_faces (bool
over the new mesh), report)` and wire it into `fix_object` BEFORE the exposure/removal passes when
`profile.solidify` is True (default True; CLI flag `--no-solidify`; the API exposes it as an option).

Per top-surface region R (faces with `n_z > profile.top_min_nz`, default 0.7, grouped by `topo.face_region`):
1. Outline = shapely union of R's triangles (same overlap exclusion and vertex mapping rules as the merge:
   every ring coordinate must map to an existing vertex, else skip the region and report `outline_unmappable`).
2. Open outline edges = outline edges whose edge-table count is 1. Edges with count >= 2 already meet another
   face (an existing skirt or a neighbouring region) and get nothing.
3. Local thickness per open edge = top z minus the lowest z of side faces (`|n_z| <= 0.7`) sharing either
   endpoint; else side faces whose centroid is within `profile.skirt_search_radius` (60 in) of the edge midpoint;
   else unresolved. Region thickness `h_R` = median of its resolved edges; if none, the file-wide median of all
   resolved edges; clamp to `[profile.min_thickness, profile.max_thickness]` (2 in, 36 in). Report h_R per region.
4. Skirt: for each open outline edge (a, b) add the vertical quad a, b, b - h_R z, a - h_R z (two triangles),
   wound so its normal points away from the region (test against the vector from the region centroid to the
   edge midpoint). New vertices are the shifted endpoints; reuse one shifted vertex per original vertex.
5. Bottom: cast a ray straight down from `EPS` below the top surface at each of R's face centroids; if a face is
   hit within `h_R + tol` for at least `profile.bottom_exists_fraction` (0.9) of them, R already has a bottom:
   add nothing, report `bottom_exists`. Otherwise add the outline polygon (outer + inners) shifted down by h_R,
   normal pointing down, triangulated with `shapely.constrained_delaunay_triangles` over the shifted vertices.
6. Materials: new faces take the material of the region's top faces. UVs: planar projection in the face's own
   plane with the same UV scale as the region's least-squares fit (`|J|`), origin at the face's first vertex.
7. Cap guard (`engine/guard/compare.py`, new mode): render BEFORE (original) and AFTER (solidified) over
   `VIEWS_26`; a changed pixel is allowed only when AFTER's first hit is a NEW face and BEFORE's hit was
   background, or a face on its BACK side (`n . view_dir > 0`), or a face whose exposure in the solidified mesh is
   0 (compute exposure on the solidified mesh once). Any other change marks the new face at that pixel; remove
   every marked new face and repeat until no pixel fails or 8 rounds. Report removed new faces per round.
8. `SolidifyResult.report`: regions processed, skirts added (count, total length), bottoms added, `bottom_exists`,
   `outline_unmappable`, thickness per region, invented vertices, cap-guard rounds and removals, faces newly
   hidden (exposure before vs after), runtime.

Pipeline order becomes: analyse -> solidify -> exposure on the solidified mesh -> hidden removal (strict) ->
slit (only if accepted) -> flip -> merge -> final guard. The final guard and `guard_after_removal` compare
against the SOLIDIFIED mesh (it is now the reference the user accepted); `FixResult` keeps the cap-guard report
against the original as `guard_solidify`. `n_hidden_candidates` etc. count on the solidified mesh.

Tests, written first: (a) `open_box_with_cells()` -> the missing side is added, both partitions become hidden and
are removed, the result is a closed box; (b) a slab with a skirt of height 8 on three sides, open on the fourth,
no bottom -> one skirt quad pair on the open side with h = 8 and a bottom at -8, closed solid; (c) a region whose
downward test finds an existing bottom -> no bottom added; (d) cap guard: force a new face that covers a
genuinely visible outside face (e.g. set `max_thickness` huge on a two-level fixture so a skirt would cover a
lower visible step) -> that face is removed by the feedback; (e) determinism; (f) `--no-solidify` reproduces the
previous numbers on `box_with_partition()`.

Real data, both files, `python -m engine.cli fix ...` default profile then `--no-solidify`: report skirts,
bottoms, thicknesses, faces newly hidden, hidden removed, final triangles, `one_sided_holes_after`, every guard
total, passed. Expectation from the spikes for file A: at least 182 faces newly hidden, ideally all rib walls
(the x-ray of the fixed mesh must show no interior faces). Write `solidify-report.md` next to this brief with
`## Public signatures`. Commit message as given, trailer `Co-Authored-By: Claude Fable 5.1 <noreply@anthropic.com>`.
Edit only files under `engine/`.
