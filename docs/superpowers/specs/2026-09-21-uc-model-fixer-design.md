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
- **Reversed faces**: Unity is single-sided, they vanish.

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

All faces triangulated, no `s` groups, units **inches** (scale contract 0.0254), coordinates printed
to 0.1 in at magnitude ~22,000 in, shared `../CKPT17-CLEAN.mtl`, tile-atlas textures in `SRC-TEX\`.

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
`constrained_delaunay_triangles` keeping every border vertex an outside face uses (no new
T-junctions) -> UV = `J*p + o` re-based near 0. Same kernel later clips partial overlaps.

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

- `embreex` import under numpy 2.5.1: unverified, Phase 0 gate.
- How many regions pass the UV Jacobian test, final tri reduction: unmeasured, Phase 0 gate.
- Unity vertex compression on UVs near 1,000 (half-float step ~1): unchecked. UV re-basing near 0
  in the region kernel should remove the risk, verify in Phase 3 Unity diff.
- All model numbers above are from the previous export.
