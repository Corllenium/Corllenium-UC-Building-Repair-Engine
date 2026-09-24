# UC MODEL FIXER — session record (2026-09-21 to 2026-09-24)

The durable record of what was built, why, what was measured, and what is still open. Written for
the owner and for any session that picks this up. Every number below was measured on the files, not
estimated. The working ledgers (every ruling, in order) are committed next to the reports under
`.superpowers/sdd/`; this page is the summary and the map.

## 1. The goal, in the owner's words (condensed)

- Clean the SketchUp OBJ exports of the CHTM sidewalk for Unity. Test files: `CHTM_SIDE_WALK_2nd_floor.obj`
  (file A) and `CHTM_2nd_to_3rd_building_sidewalk_outside.obj` (file B).
- **Remove, not hide**, everything that does not contribute to the outside: hidden inside faces,
  gridlines (triangle edges on flat surfaces), stacked duplicate layers ("texture hits texture"),
  stray fragments.
- **Do not delete the side meshes, only the inside. Build the side meshes where they are broken or
  missing.** The result is a clean solid slab.
- **Region outlines only on the edge line of the model**, never inside a slab. Toggling triangle
  edges or X-ray must show nothing extra.
- After every run, the latest `.skp` of each model in `OBJ FIXED RESULT/` to check in SketchUp 2026.
- Work visually: every round includes renders and a fix for what is seen, not only numbers.
- Dashboard on its own ports: web 5190, API 8190, PostgreSQL 5490.

## 2. Where everything is

| What | Where |
|---|---|
| Design spec (binding, with amendments) | `docs/superpowers/specs/2026-09-21-uc-model-fixer-design.md` |
| Plans | `docs/superpowers/plans/` |
| Ledgers (every ruling, measurement, dispatch, in order) | `.superpowers/sdd/2026-09-21-phase2e-fix-pipeline/progress.md`, `.superpowers/sdd/2026-09-22-dashboard-and-engine-continuation/progress.md` |
| Round reports (with `## Public signatures`) | `.superpowers/sdd/2026-09-21-phase2e-fix-pipeline/*-report.md` |
| Engine | `engine/` (entry point `python -m engine.cli fix <snapshot> --out data/output`) |
| Frozen input copies | `data/snapshots/ce26e0392ab0` (A), `data/snapshots/0b290ec0bcb4` (B) |
| Run outputs | `data/output/<name>/`: `.fixed.obj` (Unity), `.fixed.ngon.obj`, `report.json`, `qa/` (21 renders), `.fixed.skp` |
| Owner's SketchUp files | `OBJ FIXED RESULT/<name>.fixed.skp` (overwritten by every run) |
| Preview page | `preview/index.html`, served at http://127.0.0.1:5180 |
| Dashboard | web http://localhost:5190, API http://127.0.0.1:8190, PostgreSQL 127.0.0.1:5490 |
| Diagnostic scripts used in this session | `docs/superpowers/records/scripts/` (see section 8) |

## 3. Which engine file handles which error

`engine/fixes/pipeline.py::fix_object` runs every step in this order: load and weld, **solidify**,
**exposure**, **hidden-face removal**, **fragments**, **orientation**, **duplicate layers**,
topology again, **merge**, **final guard** (rolled back if it fails), invariants, outputs.
`engine/cli.py` writes the files.

| What you see | Detected by | Fixed by | Safety check | Status |
|---|---|---|---|---|
| Hidden inside faces (only visible with X-ray) | `engine/vis/exposure.py`: `compute_exposure`, `compute_side_exposure`, `classify_exposure` (128 ray directions x 4 samples per face) | `engine/fixes/remove.py::remove_faces`, called from `fix_object` | `engine/guard/compare.py::guard_feedback` (strict: a face whose removal changes any pixel is restored) | Working. A: 1,985 removed; B: 2,584. **Limit:** a face visible through an opening or slit in a broken side is kept. |
| Missing slab sides and bottoms | `engine/fixes/solidify.py::top_regions` | `engine/fixes/solidify.py::solidify` (walls at each edge's own measured height, bottoms at the shallowest measured depth) | `engine/guard/compare.py::solidify_feedback` (cap guard: a new face may only cover faces seen through openings, original exposure under 0.10) | Working for open edges. A: 99 walls, 9 bottoms; B: 42 and 8. **Limit:** a side that exists but is broken (jagged, partial, with gaps) is not replaced. That is the owner's sawtooth screenshot, and the next feature. |
| Gridlines, triangle edges on flat surfaces | `engine/topo/planes.py`: `cluster_planes`, `build_regions`, `cluster_uv`; `engine/topo/edges.py::classify_edges` (class 1 = removable gridline) | `engine/fixes/merge.py::merge_regions` (per flat region: union, then constrained triangulation over existing vertices only; border vertices within 0.15 in of a straight line dropped) | Final guard in `fix_object` (`compare_views` against the solidified reference; border shifts up to 0.15 in are measured and tolerated) | Working. A: 177 regions merged; B: 90. One region per file skipped, being fixed now (section 6). |
| Texture on texture (z-fighting, stacked duplicate layers) | `engine/fixes/overlap.py`: `find_overlaps`, `covered_fractions` | `engine/fixes/overlap.py`: `plan_overlap_removal`, `remove_overlaps` | Strict guard | Same material: working (A 49, B 23 removed). Different materials: reported only (B had 39 such pairs at b2134e9); the owner's "which face wins" preference step is not built. |
| Reversed faces (purple back side in SketchUp) | `engine/fixes/orient.py::classify_orientation` (flip when the back is more exposed than the front; "thin sheet" when both sides are) | `engine/fixes/orient.py::flip_faces` | Guard | Working for clear cases (A 780 flipped). **Limit:** thin sheets (A 79, B 16) are not flipped, and faces on open or broken sides count as thin sheets. Closing the sides fixes this. |
| Stray fragments and slivers | `engine/detectors/fragments.py::detect_fragments` | the fragment pass in `fix_object` | `engine/guard/compare.py::fragment_feedback` | Working. A: 3 fragments and 15 slivers removed; B: 12 slivers. |
| Zero-area faces | `engine/topo/adjacency.py::degenerate_mask` | removal in `fix_object` | Strict guard | Working. |
| T-junction lines (a line across a flat surface; cracks and sparkle in Unity) | `engine/topo/adjacency.py`: `find_t_vertices`, `t_junction_sub_edges` | **not repaired yet.** Planned: thread the neighbour's existing vertex into the merged outline in `engine/fixes/merge.py` | Guard | Open (section 6). |
| Lines inside flat surfaces in the `.skp` | measured on SketchUp's own model after writing | `engine/io/skp_writer.py::write_skp` (softens class 1 and 5 edges today; the running fix softens every edge SketchUp would draw inside a flat same-material surface) | `read_skp` / `read_skp_summary` read-back | In progress (section 6). |
| "Did anything visible change?" (safety net for all of the above) | `engine/guard/views.py::ortho_first_hit` (26 views), `engine/rays/caster.py` | n/a | `engine/guard/compare.py`: `classify_pixels`, `compare_views`. Pixel classes: hole, material changed, moved, edge flicker, z-fight tie, crack closed, fragment removed, border shift | Working. |
| Visual check of every run | n/a | `engine/guard/qa_render.py::write_qa_sheet` (21 renders into `data/output/<name>/qa/`) | n/a | Working. |
| The SketchUp file | n/a | `engine/io/skp_writer.py::write_skp` (one face per merged region with inner loops for openings, materials with textures on both sides) | `read_skp_summary`, `check_skp_validity` | Working; files in `OBJ FIXED RESULT/`. |

## 4. History: rounds, commits, measured results

Triangles out of the fixed file (input: A 4,692, B 7,227). "Passed" = every invariant true and the
final guard passed.

| When | Round | Commits | A | B |
|---|---|---|---|---|
| 09-21 | Phase 0 spike, Phase 1A foundations, Phase 2E tasks 1-9 (rays, exposure, guard, removal, merge kernel, pipeline, CLI, preview) | 819bb32 ... | | |
| 09-23 | Engine round, guard round (ties, cracks, flicker ring, reports) | ... a29688e | 1,891 | 1,278 |
| 09-23 | Merge quality (one slab one face) | 0eec601 ... 0d464e0 | 1,674 | 1,173 |
| 09-23 | Overlap removal + solidify | f0bea77 ... b2134e9 | 1,600 | 1,113 |
| 09-23/24 | Solidify fixes (original-exposure cover rule, local wall heights, shallowest bottoms, refused partial bottoms, cap guard invariant) + fragments + QA sheet | a528705 ... c0bbc98 | 1,590 | 1,128 |
| 09-24 03:30 | Peer fixes merged: rule 9 per pass (d505241), union slivers close (dee358d), asset-aware snapshot identity (F5) | 17939a4, ee840e9, e57462d | 2,579 (merge rolled back) | 602 |
| 09-24 04:10 | The merge guard measures border shifts instead of counting pixels | 022a67b | **1,117** | **602** |
| 09-24 08:50 | SketchUp export: `.skp` per run into `OBJ FIXED RESULT/` | e97443e, d24da30, merge 8ffbda3 | .skp 731 faces | .skp 248 faces |
| 09-24 09:25 | Merge: T-junction sliver rings closed at the source, a union corner no vertex explains sets aside only its triangles (N1, N2) | d6ef1a9, b3b9ad3 | **902** (0 regions skipped, 87 copied) | **555** |

Every commit since b2134e9, oldest last: `git log --first-parent b2134e9..HEAD`.

Why file A rolled back at 03:30 and how it was fixed: the merge made 1,117 triangles, but the final
guard failed on 14 "edge flicker" pixels in one of 26 views against a cap of 11. Every one of the
59 flagged pixels was measured: surface borders moved by at most 0.062 in (the merge may move a
border by 0.15 in), no surface missing. A pixel count cannot tell a 0.013 in shift along an edge that
lies on pixel centres from real damage, so the guard now measures the displacement instead
(022a67b); anything farther than 0.15 in still fails.

## 5. Measured state of the SketchUp files

Audit of every edge SketchUp draws, read back through the C API (`scripts/skp_edge_audit.py`).
First at 8ffbda3 (08:53), then after the merge fix (b3b9ad3, files written 09:29):

| | A at 8ffbda3 | A at b3b9ad3 | B at 8ffbda3 | B at b3b9ad3 |
|---|---|---|---|---|
| Faces / edges | 731 / 1,618 | 517 / 1,248 | 248 / 734 | 220 / 680 |
| Hidden (soft) edges | 560 | 268 | 143 | 102 |
| Visible lines inside a flat same-material surface | 21 | 21 | 5 | 5 |
| Visible T-junction lines lying on a flat surface | 100 (longest 551 in) | 50 | 36 | 36 |
| Real outer borders | 214 | 220 | 200 | 203 |
| Lines where a wall meets a surface | 328 | 339 | 150 | 151 |
| Shape edges above 5 degrees | 330 | 301 | 158 | 143 |
| Material borders | 0 | 0 | 12 | 12 |

## 6. Open problems (owner screenshots, 2026-09-24)

1. **Broken sides are kept, not rebuilt.** A slab side that exists but is jagged (sawtooth), has
   gaps you can see through, and shows the purple back side. Cause: solidify only adds walls where
   the side is missing, and its guard refuses to cover visible original faces, so a broken visible
   side is preserved. Needed: **side rebuild**, replacing a broken side with a clean wall along the
   slab outline, removing the broken pieces it replaces, faces pointing outward. Interior faces seen
   through those gaps then become hidden and are removed by the existing step. Next feature.
2. **Lines inside flat surfaces in the `.skp`** (section 5). Running: the writer hides every line
   SketchUp would draw inside a flat same-material surface (branch `feat/skp-soften`). Queued: repair
   the T-junctions in the geometry itself (merge), which also removes Unity cracks.
3. ~~File A's sloped underside is a triangle lattice~~ **fixed (b3b9ad3)**: the region's own
   T-junctions made a 71 in x 0.00006 in sliver in its union, whose corner sat 7.87 in from any
   vertex; such slivers are now closed at the source. In the `.skp` that underside is 111 soft-edged
   triangles, because it is 0.005 in off flat and SketchUp splits any face more than about 0.001 in
   off its plane (19 such regions on A, 9 on B); the edges are hidden. Leftovers found on the way:
   file B region 74 draws as 17 triangles (4 overlapping triangles cut an island off it); region 38 is
   a side face with a solidify wall laid over it (solidify took an existing side's top edge for an
   open edge); region 79 is two original triangles folded over their shared edge.
4. **Interior visible from inside the model** (owner's X-ray/inside screenshot): faces kept because
   they are visible through openings or slits in broken sides; follows item 1.
5. **Review** of everything since b2134e9 not yet done.
6. **Dashboard fix wave** (brief `.superpowers/sdd/2026-09-22-dashboard-and-engine-continuation/fix-wave-1-brief.md`,
   D1-D12) not started; D0 superseded by the F5 merge.
7. Different-material overlaps: the owner's preference step ("which face wins") not built.

## 7. Decisions that shape the engine (details in the ledger)

- Visibility is judged double-sided (SketchUp and the Unity shader draw both sides); a one-sided
  render is a diagnostic only. A culled render once faked holes in an intact sidewalk.
- Nothing visible may change unless a rule names the change and measures it: z-fight ties, closed
  cracks (capped), removed debris (by name), border shifts up to the merge's own 0.15 in tolerance.
- Only solidify may invent vertices; the merge never moves or invents one.
- Merge area rule amended (d505241): per region a bounded border movement, per pass no net growth.
- Peer-session work is accepted only after measurement in an isolated worktree and merged by the
  controller; foreign uncommitted edits are parked on `wip/` branches, never discarded
  (`wip/snapshot-alias-copy-master-plan`, `wip/footprint-heuristic`).

## 8. Diagnostic scripts (copied here from the session scratchpad)

Run from the repo root with `PYTHONPATH` set to the repo root and the project interpreter
`.venv/Scripts/python.exe`.

| Script | Answers |
|---|---|
| `scripts/diag_flicker.py <snapshot> <out>` | Where are the pixels that fail the merge guard, per view, with the faces under them |
| `scripts/diag_flicker_dist.py <out>` | How far did the surface really move at each of those pixels |
| `scripts/diag_new_vertex.py <snapshot>` | Which merge region is skipped for a new vertex, by which path, and how far off |
| `scripts/skp_edge_audit.py <file.skp>` | Every edge SketchUp draws, classed; lines inside flat surfaces and T-junction lines |
| `scripts/edge_audit.py <file.ngon.obj>` | The same for the polygon OBJ (overstates: holed regions are triangles there) |
| `scripts/render_skp.py <file.skp> <out dir>` | 21 renders of a `.skp` with only the edges SketchUp draws |

## 9. How to resume

```bash
.venv/Scripts/python.exe -m pytest engine/tests -q -p no:cacheprovider
.venv/Scripts/python.exe -m engine.cli fix data/snapshots/ce26e0392ab0 --out data/output
.venv/Scripts/python.exe -m engine.cli fix data/snapshots/0b290ec0bcb4 --out data/output
.venv/Scripts/python.exe -m engine.cli preview-data data/snapshots/ce26e0392ab0 --out preview/data
```

Then read `data/output/<name>/report.json`, look at `data/output/<name>/qa/*.png`, audit
`OBJ FIXED RESULT/<name>.fixed.skp` with `scripts/skp_edge_audit.py`, and read the tail of the
ledger for the current queue.

Lessons that cost time: agents are cut by the account session limit (resume them by message after
the reset, never re-dispatch blindly); on Windows a running agent's output file reads as empty, which
is not a hang; other sessions edit this same working tree, so workers use their own worktree or
branch and the controller merges; describe the work inline in agent prompts; run API tests only when
no other session is (they drop the shared test database).
