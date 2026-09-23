# UC MODEL FIXER — design

Approved 2026-09-21. Task-level plans live in `docs\superpowers\plans\`.

## Context

SketchUp campus model (CHECKPOINT-17) is exported to OBJ, split per SketchUp group, used in
**Unity 6000.4.7f1 / URP 17.4.0**. Exported objects carry modelling debris Unity renders badly:

- **Gridlines**: SketchUp edges cutting one flat slab into hundreds of tiny coplanar faces. In
  OBJ/Unity these are not lines. They are excess triangles, T-junction cracks (sparkling pixels),
  shading seams.
- **Interior geometry**: partition faces inside a slab, never visible from outside.
- **Texture hits texture**: coplanar faces, same plane, fighting for the same pixels (flicker).
- **Reversed faces**: 4-5 % of sidewalk area faces the wrong way (spike: 448 and 583 tris). The
  Unity project currently hides this by setting every campus material to `_Cull = 0`
  (`CampusDoubleSided.cs`), so today they are a lighting defect, and become holes the moment culling
  is switched back on. *Corrected 2026-09-21: an earlier draft said "Unity is single-sided".*

Goal: an engine that **removes** (not hides) what does not contribute to the outside, keeps the
facade exactly, plus a dashboard where every deletion is reviewed, BEFORE/AFTER is visible side by
side, and every method and decision is saved so the next export fixes itself.

## Decisions made with user

| Topic | Decision |
|---|---|
| Test set | `CHTM_SIDE_WALK_2nd_floor.obj` + `CHTM_2nd_to_3rd_building_sidewalk_outside.obj` in `...\01-MODEL-EXPORT\CKPT17\split\`. No buildings |
| Fix control | Detect -> highlight -> accept/reject -> apply. Nothing deleted unreviewed |
| Renderer | Unity |
| Preview | Side-by-side synced canvases, BEFORE / AFTER, edge overlay, issue overlay, tri counts |
| Engine input | Exported OBJ. `.skp` untouched, originals never overwritten |
| Preferences | All four: remembered accept/reject rules, overlap winner, detector profiles, hand tagging |
| Build where | New project in `D:\PROJECTS\UC MODEL FIXER`. Reuse knowledge from `D:\PROJECTS\UC`, `06-DASHBOARD` untouched |
| Stack | Vue 3 + three.js, FastAPI, PostgreSQL 16 (Docker), Python engine |
| Flat textures | When a texture's colour std is below a tunable threshold, UV seams do not delimit regions and the guard compares sampled texel colour instead of UV. Patterned textures still respect seams |
| Render semantics | **Default double-sided**, matching SketchUp and the Unity project (`_Cull = 0`): every face renders and blocks from both sides. Single-sided is a profile switch and a canvas diagnostic toggle, never the default (a one-sided view made intact geometry look destroyed during the spike) |
| Interior removal | Candidate only when no ray from either side escapes. Depth-aware guard over 26 views, and guard feedback puts back any face whose removal changes a pixel. Measured: 1,819 and 2,381 tris removable with 0 damaged pixels |

Spike evidence for the last two rows: `docs\spike\2026-09-21-phase0-results.md`.

## Measured facts (2026-09-21)

**Environment.** Python 3.12.10, Node 24.18, pnpm 11.20, Git 2.55, Docker 29.7 running, Blender 5.1,
SketchUp 2026. PostgreSQL absent, port 5432 free. Present: numpy 2.5.1, shapely 2.1.2 (GEOS 3.13.1,
has `constrained_delaunay_triangles`), networkx, fastapi, uvicorn. Missing: trimesh, scipy, embreex,
sqlalchemy, psycopg, alembic, pytest. `embreex` 4.4.0 has a `cp312-win_amd64` wheel (import under
numpy 2.5.1 **unverified**).

**Working dir** holds only the 142 MB `.skp` + `.skb`. No git.

**Source folder is live.** `CKPT17\` was rewritten three times during this planning session
(`split\` vanished and came back, `SRC-TEX\` 498 -> 590 files). Numbers below are from the previous
export and get re-measured in Phase 0.

| Measure | SIDE_WALK_2nd_floor | 2nd_to_3rd_outside |
|---|---|---|
| v / vt / vn / tris | 1,607 / 2,772 / 666 / 4,692 | 2,867 / 1,831 / 827 / 7,227 |
| materials | 1 | 3 |
| size (m) | 42.25 x 23.62 x 5.00 | 58.76 x 39.47 x 8.50 |
| edges shared by 1 / 2 / 3 / 4+ faces | 453 / 3,732 / 1,629 / 303 | 534 / 7,615 / 1,216 / 538 |
| edge-connected shells, closed | 7 (one holds 4,671 tris), 1 closed | 4, 0 closed |
| zero-area triangles | 217 (4.6 %) | 79 |
| exact duplicate faces | 11, all opposite winding | 31, all opposite winding, 24 with different front/back material |
| oblique (not axis-aligned) faces | 2,188 | 1,836 |
| adjacent coplanar same-material pairs: UV continuous / shifted whole tiles / discontinuous | 68.0 % / 16.5 % / 13.9 % | 50.1 % / 36.2 % / 12.7 % |

All faces triangulated, no `s` groups, units **inches** (scale contract 0.0254), shared
`../CKPT17-CLEAN.mtl`, textures in `SRC-TEX\` are 16x16 noise (colour std 3.04 / 255).
Exporter prints **6 significant digits**, so the coordinate step is **per axis**: 0.1 in on Y
(values near 22,000), 0.01 in on X and Z. Plane tolerance = `1.5 * sum(|n_i| * q_i)`.

Spike classification (culled occlusion): file A 448 reversed / 224 interior tris, file B 583 / 287.
Most visible faces have their back exposed too: the sidewalk is largely zero-thickness sheets.

What the numbers say: this is **one open non-manifold blob, not closed shells**. ~1,900 edges with
3+ faces are the interior partitions from the user's screenshots. Duplicates are all
opposite-winding, so they are two-sided faces, not z-fight duplicates.

## What exists already, what is reused

`D:\PROJECTS\UC\06-DASHBOARD` already **detects** (browser engine `src\lib\meshcheck\`, overlays,
fix-pin annotations, manifest JSON download). Verified missing there: apply loop, per-issue
accept/reject, BEFORE/AFTER, versions, facade guard, recipes, preference rules, per-face
visibility. That loop is the gap this project fills.

| Reused from | As |
|---|---|
| `meshcheck\types.ts` `IssueKind` + `04-DOCS\for-modeller\01-THE-DEFECTS.md` D1-D10 | vocabulary seeded into `issue_types` |
| `CLEANUP-SPEC.md`, `02-TOOL-GUIDE.md` tolerances | default detector profile |
| `cleanup-scripts\18-analyze-faces.py` rule (rear face >= 95 % covered by nearer same-direction faces) | cross-check for overlap detector |
| `CampusModelImporter.cs` contract (OBJ, scale 0.0254) | export target, v1 writes OBJ |

**Blocked operations** (each already damaged this model once, engine refuses, no UI override):
weld above 0.1 mm; Blender `select_interior_faces` delete (removed 88 %); Fill Holes; Make Manifold;
Decimate; dissolve angle above 5 degrees; treating opposite-normal coincident pairs as duplicates;
whole-campus jobs.

**Hard invariants after every apply**: merged region area must not grow (a bulk merge once bridged
openings, 14,943 -> 18,044 m2); material count unchanged; bounding box identical; facade guard pass.

## Engine design

### Foundations
- **Custom OBJ reader/writer** (~150 lines). Face `i` = the `i`-th `f` line, pinned by test. No
  trimesh loading (it reorders, merges, drops degenerates). trimesh only as a ray view:
  `Trimesh(vertices, faces, process=False)` over `embreex`, behind a `RayCaster` protocol, with a
  brute-force numpy Moller-Trumbore caster as test oracle.
- **Snapshot importer**: size stable across two reads -> copy -> sha256 -> parse -> tri count equals
  `_MANIFEST.txt`. Returns `409 source rebuilding` otherwise. Copies only the MTL entries and
  textures the object uses. Jobs never read the live folder.
- **Recentre** to bbox centre before float32 (coordinates sit near 24,000 in). Store `origin_offset`
  and detected `coord_quantum` per version. All thresholds defined in metres, floor = coord quantum.
- **Adjacency from overlapping collinear edges**, not shared vertex indices. Zero-area triangles are
  the stitching across T-junctions: use them as hints, drop them after adjacency is built.

### Oriented visibility (core detector)
Every face is classed `front_visible`, `back_only_visible` or `never_visible` under Unity culling.
Fixed Fibonacci direction set (64-128). Per direction, build a scene of only the triangles whose
front faces the viewer, then plain first-hit gives the culled answer. Samples: centroid + 3 interior
points, area-stratified for big faces. Views from below stay on (walkway underside is seen from
ground). `never_visible` needs zero escaping rays.
- Temporary **cap faces** over open boundary loops act as occluders only, never exported.
- Faces hidden only by a neighbour object are their own subtype `hidden_by_neighbour`, never share a
  trusted rule with self-hidden faces (neighbour can be streamed out in Unity).

### Planar region kernel (kills gridlines, replaces Blender dissolve)
Grow regions by **vertex distance to fitted plane** (normal-angle clustering fails on noisy oblique
faces), same material, and **same UV Jacobian with offsets equal modulo 1** (tolerance from the 0.01
tile UV step). This merges the 16-36 % whole-tile-shifted pairs Blender's UV delimit would block,
and keeps the ~13 % real texture seams as borders. Then: project -> shapely union ->
`constrained_delaunay_triangles` -> UV = `J*p + o` re-based near 0. Same kernel later clips partial
overlaps.

Spike-validated rules for this kernel:
- **UV delimits only patterned textures.** For flat textures (decision above) regions are plane +
  material, and UVs are re-projected from the largest member's fit.
- **UV fit needs iterative least-squares refit.** One triangle's Jacobian is too imprecise to
  extrapolate across a 40 m slab. Seed on the largest triangle, accept, refit on all accepted, repeat.
- **Border vertices**: a ring vertex survives only when some region needs it as a corner, decided
  globally, so both sides of a shared border drop the same vertices. No new T-junctions. A polygon
  with n ring vertices and h holes always costs n + 2h - 2 triangles, so this is where reduction lives.
- **Overlap handled per triangle, never per plane.** Overlapping faces are excluded from a region
  before union, because crossing edges make the union invent vertices (94 in from any input seen).
- Vertices are never moved. Regions are re-triangulated over existing vertices only.
- Measured full pipeline: file A 4,692 -> 3,111 (33.7 %), file B 7,227 -> 3,003 (58.45 %).

### Detectors, by phase
| Key | Finds | Phase |
|---|---|---|
| `degenerate` | zero-area, loose vertices, `vn` opposing winding | 2 |
| `excess_subdivision` | mergeable planar regions, faces before -> after | 2 |
| `oriented_visibility` | `never_visible` interior faces, `back_only_visible` reversed faces | 2 |
| `coplanar_overlap` | **same-facing** pairs only. Delete loser when >= 99 % covered, partial = report-only | 3b |
| `double_sided_pair` | opposite-facing coincident pairs, informational | 3b |
| `mesh_intersection`, normals rebuild | deferred, mesh is one blob so shell logic cannot work | later |

Fix order: degenerate -> orientation (pass A) -> recompute visibility with culling (pass B) ->
interior -> overlap -> region merge.

### Facade guard (built BEFORE the first fix)
- **Primary, sample guard**: every (sample, escaping direction) pair from `front_visible` BEFORE
  faces is re-cast into AFTER. Must match hit depth, material, UV modulo 1 (tol 0.02), shading normal.
- **Secondary, image guard**: orthographic views at 1 in/px for human-readable diff PNGs. Mismatch
  tolerated only within 1 px of a BEFORE depth edge and under 0.05 % of pixels.
- **Expected changes**: a flipped face or resolved z-fight legitimately changes the image. Each
  allowed change is tied to an accepted issue id and reported separately. Z-fight mask: where BEFORE
  has 2+ front hits within tolerance, AFTER must be one of those candidates.
- **Mutation tests prove the guard**: identity run = 0 differences. Three deliberate breaks must
  each fail with numbers: one visible face deleted, UVs shifted 0.5, one face flipped.

### Identity across re-exports
Face ids die on every re-export. Exporter rounding makes printed geometry a stable key.
`face_key` = hash(sorted rounded vertex triple, winding, material). `region_key` = group name +
rounded plane + material + rounded in-plane bbox + area (survives re-triangulation). `descriptor` =
area, orientation class, visibility fractions (feeds rules and "find similar", not identity).
On re-import, prior decisions join by group name + issue type + `region_key`, carried as
`source='carried'`. A hand tag re-anchors when >= 90 % of its `face_key`s match, else `stale`.

## Project layout

```
engine\   model.py  io\{obj_reader,obj_writer,mtl,snapshot}.py
          topo\{weld,adjacency,planes,edges}.py  rays\  detectors\  fixes\  guard\
          transport\meshbuf.py  tests\fixtures\
api\      main.py settings.py db.py models.py schemas.py routers\ services\{importer,jobs}.py alembic\
web\src\  three\{meshbuf,Viewport,picking,sync}.ts  views\  stores\  api\client.ts
spike\    data\ (git-ignored, also *.skp *.skb)   docker-compose.yml   docs\
```
`engine` imports no HTTP or SQL. `api` calls engine. `web` talks only to `api`.

**Canvas transport**: custom binary `meshbuf` (JSON header, recentred positions, UV, normals,
per-triangle material index, per-triangle `Uint32` face id, per-edge class flags). Non-indexed
geometry so three.js `faceIndex` k -> `faceId[k]`. AFTER triangles carry provenance so clicking one
highlights its BEFORE faces. Edge overlay draws two classes: *removable* (inside one region) and
*real* (region border, crease). BEFORE shows the grid, AFTER shows it gone.

**Database**: `postgres:16`, bound `127.0.0.1:5432`, named volume, `pg_dump` to `data\backups\`.
Tables arrive with the phase that uses them:

| Migration | Tables |
|---|---|
| 0001 (Phase 1) | `models`, `model_versions` (kind snapshot/preview/fixed, sha256, coord_quantum, origin_offset, immutable), `version_assets`, `runs` (engine commit, package versions), `issue_types` seeded |
| Phase 2 | `issues` (detector_version, profile snapshot, `region_key`, face ids), `decisions` append-only (who or which rule, when) |
| Phase 3 | `guard_results`, `fix_methods` |
| Phase 4 | `preference_rules`, `rule_hits` (trust computed from hits across 2+ versions), `overlap_winner_rules`, `detector_profiles`, `recipes` (steps reference detector/fix versions + selectors, never face ids) |
| Phase 5 | `custom_issue_types`, `user_tags` |

## Phases

| Phase | Delivers | Proof artefact |
|---|---|---|
| **0 Spike** (throwaway, `spike\`) | env check (`embreex` import, rays/s), snapshot, re-measure both files, merge the largest region once, front-hit trick vs brute-force oracle | `data\spike\results.json`. **Gates**: embreex imports, affine pass rate + merge reduction worth it, oracle 0 mismatches. Failed gate = redesign before building |
| **1 Infrastructure** | git, docker Postgres, migration 0001, snapshot importer, OBJ reader/writer, adjacency + regions + edge classes, meshbuf, API, one Vue page with two synced canvases + edge overlay + tri counts | pytest output, `alembic upgrade head` table list, DB sha256 = `certutil -hashfile`, tri count = manifest, screenshot showing grid, pick test (click -> face id -> `f` line -> matching vertices) |
| **2 Guard + first detectors** | guard with mutation tests, `degenerate`, `excess_subdivision`, `oriented_visibility`, issues + overlays, preview version (not exportable) | fixtures pass, SQL issue counts = UI counts, two runs same fingerprint hash, guard identity 0 diffs, 3 mutations fail with numbers |
| **3 Review + apply** | accept/reject per issue / type / filter, apply, fixed versions, invariants, guard verdict with diff PNGs, OBJ export to `data\output\` | BEFORE grid / AFTER clean screenshots, tri counts, guard numbers, fixed-camera image diff in Unity |
| **3b Overlap** | `coplanar_overlap`, `double_sided_pair`, overlap winner choice | flicker region masked area reported |
| **4 Methods + preferences** | rules, trust, profiles, recipes, "auto-applied by rule R" panel with one-click revert | file B fixed from file A's recipe; shuffle test (reorder faces + vertices) carries 100 % of decisions by fingerprint |
| **5 Hand tagging** | select faces, name a type, tag with metrics, find similar | tag on A finds faces on B, true/false positive counts stored |

Deferred: `mesh_intersection`, normals rebuild, neighbours as occluders, FBX/GLB export through
Blender, `.skp` write-back, inside-view clipping, camera bookmarks, `pathway_basement.obj`.

## Execution after approval

1. `git init`, `.gitignore` (`data\`, `*.skp`, `*.skb`), save this design as
   `docs\superpowers\specs\2026-09-21-uc-model-fixer-design.md`, commit.
2. `superpowers:writing-plans` -> task-level plan for **Phase 0 + Phase 1 only**. Later phases get
   their own plan once spike gates pass, since gate numbers decide the design.
3. Build with `superpowers:test-driven-development`. Synthetic fixtures with known answers: cube,
   gridded slab, box with partition, double-sided pair, T-junction strip, whole-tile-shifted UV slab.
4. Every "done" goes through `superpowers:verification-before-completion`: artefact produced that
   turn (screenshot, measured number, command output). Unrun code is not delivered.

## Open unknowns (labelled, not assumed)

- Resolved by spike: `embreex` 4.4.0 works under numpy 2.5.3 at 4.9 M rays/s. Culling trick matches
  brute force on 32,000 rays with 0 disagreements.
- Resolved by spike: tri reduction 33.7 % and 58.45 % with the flat-texture rule. With UV always
  respected it would be ~8 % and ~39 %.
- Guard depth tolerance (0.02 in) is tighter than the Y-axis coordinate step (0.1 in). Dropping a
  border vertex that is collinear within 1.5 quanta can move a boundary by up to 0.15 in. Guard
  tolerance must follow the per-axis quantum, set in Phase 2.
- Unity vertex compression on UVs near 1,000 (half-float step ~1): unchecked. UV re-basing near 0
  in the region kernel should remove the risk, verify in Phase 3 Unity diff.
- All model numbers above are from the previous export.

## Amendments (2026-09-23, from measured results; these override the sections above where they differ)

**Guard verdicts.** Depth is measured as surface displacement (`max(dist(P_before, plane(face_after)),
dist(P_after, plane(face_before)))`), never depth along the ray. Base classes per pixel: `hole`,
`material_changed`, `moved_same_flat` (a failure only when `strict`), `moved_other`. For a pixel whose base
class fails under the current strictness, three tolerances apply in this order: (1) **z-fight tie**: BEFORE's
and AFTER's hits within `depth_tol` of their first hit form tie sets; the pixel is a tie when each side's first
hit matches a member of the other side's set (same material, point within `depth_tol` of that member's plane);
never a failure, reported as `zfight_tie`. (2) **crack closed**: at least 12 of the 16 BEFORE ring rays
(radius `depth_tol` and `depth_tol/2` in the image plane) already reproduce AFTER's centre verdict; never a
failure, reported as `crack_closed`. (3) **ring flicker**: some AFTER ring ray reproduces BEFORE's centre verdict
and some BEFORE ring ray reproduces AFTER's; counted against `edge_flicker_cap`, 0.0 in every removal guard
and 1e-4 in the final merge guard. `depth_tol = 1.5 * max(axis quanta)`. Documented limit: damage narrower
than the ring radius cannot be told from a closed crack; a merge never deletes faces, so only boundary effects
reach the merge guard. Measured: file A's single rollback pixel was a 0.02 in crack the merge closed; file B's
12 changed pixels were coplanar faces of different materials at one depth (a real overlap defect for the
overlap detector, not guard damage).

**Degenerate faces** (relative area test) are removed only through the strict guard, like hidden faces;
restored ones are reported. Every BEFORE render uses all faces.

**Orientation.** A face is a thin sheet when both sides are exposed and `min/max >= sheet_ratio`; thin sheets
are never flipped. Otherwise a face is flipped when its back exposure exceeds its front. Flipping never changes
a double-sided render, so guard verdicts are identical with and without it.

**Merge.** Region planes are fitted by least squares over the growing region (a seed triangle's plane is too
noisy over a 40 m slab); ring vertices are dropped by Ramer-Douglas-Peucker with a global bound of
`1.5 * max(quanta)`, needed vertices forced to survive; a rolled-back merge keeps the failing guard report.
Edge classes gain `EDGE_SOFT` (crease between `coplanar_angle` 1 degree and `soft_angle` 5 degrees, kept
geometry, softened in SketchUp, not drawn as an outline). Merged regions keep their rings with inner loops;
hole-free regions are exported as single polygons in a second OBJ.

**Merge area rule (amended 2026-09-23, peer task d505241).** Per region, the merged area may exceed the
original by at most `1e-6 * area + collinear_tol * perimeter` (the boundary-movement bound the ring
simplification and the guard already accept); per merge pass, if the merged regions net more than `1e-6`
relative growth, every grower is fed back and copied through (the old rule), so the mesh never grows and no
opening wider than `2 * collinear_tol` can be bridged. Measured: file A 1,600 -> 1,490 triangles, file B
1,113 -> 956, guards unchanged.

**Solidify (new fix step, reviewed).** The only step allowed to invent vertices: for each top-surface region,
skirts along open outline edges down to the local skirt height, and a bottom at that depth where none exists,
under a cap guard (only pixels whose AFTER first hit is a new face may change, and only where BEFORE showed
background, a face that becomes hidden, or the back of a sheet). The solidified mesh becomes the reference
for the rest of the pipeline. Motivation: the sidewalk is a top sheet with partial skirts and almost no bottom,
so rib walls stay visible through side holes and from below; closing the slab makes them hidden and lets the
strict removal delete them without any slit acceptance.

**SketchUp export.** After every run the latest `<name>.fixed.skp` is written to `OBJ FIXED RESULT\`:
polygon faces with inner loops, `EDGE_SOFT` edges softened, materials with textures, world coordinates in inches.

**Dashboard.** Ports 5190 (web, strictPort), 8190 (API), 5490 (PostgreSQL). The API reads the live export
folder only through `engine.io.snapshot`; `SourceUnstable` -> 409 + `Retry-After: 5`, manifest mismatch ->
422, unknown file -> 404; every fix run records `merge_report`, all guard totals, provenance and the `.skp` path,
and the AFTER panel states a rollback when one happened.

**Overlap detector** (texture hits texture) moves up: file B shows 14 z-fight ties between different
materials; it runs after the SketchUp export, with the user's "which face wins" preference.
